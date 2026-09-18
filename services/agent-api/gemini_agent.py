"""Gemini Interactions API loop for bounded TripLens evidence tools."""

from __future__ import annotations

import json
import os
from typing import Any

from pathlib import Path

from triplens.agent_tools import AgentToolSession, EvidenceStore

SERVICE_ROOT = Path(__file__).resolve().parent

DEFAULT_MODEL = "gemini-3.8-flash"

TOOL_DECLARATIONS = [
    {
        "type": "function",
        "name": "search_events",
        "description": "Search filtered EVENT evidence. Returns at most 20 evidence-linked rows.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "equipment": {"type": "string"},
                "event_class": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer"},
            },
        },
    },
    {
        "type": "function",
        "name": "get_event_window",
        "description": "Read chronological EVENT evidence around a model-time center.",
        "parameters": {
            "type": "object",
            "properties": {
                "center_time_s": {"type": "number"},
                "before_s": {"type": "number"},
                "after_s": {"type": "number"},
                "limit": {"type": "integer"},
            },
            "required": ["center_time_s"],
        },
    },
    {
        "type": "function",
        "name": "get_raw_window",
        "description": "Read only explicitly requested RAW tags in a bounded time window.",
        "parameters": {
            "type": "object",
            "properties": {
                "tags": {"type": "array", "items": {"type": "string"}},
                "start_time_s": {"type": "number"},
                "end_time_s": {"type": "number"},
                "max_rows": {"type": "integer"},
            },
            "required": ["tags", "start_time_s", "end_time_s"],
        },
    },
    {
        "type": "function",
        "name": "get_tag_series",
        "description": "Read one RAW tag with bounded points plus numeric summary.",
        "parameters": {
            "type": "object",
            "properties": {
                "tag": {"type": "string"},
                "start_time_s": {"type": "number"},
                "end_time_s": {"type": "number"},
                "max_points": {"type": "integer"},
            },
            "required": ["tag", "start_time_s", "end_time_s"],
        },
    },
    {
        "type": "function",
        "name": "get_logic_context",
        "description": "Return exact Logic Master matches only. Never infer unregistered logic.",
        "parameters": {
            "type": "object",
            "properties": {
                "tags": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer"},
            },
            "required": ["tags"],
        },
    },
    {
        "type": "function",
        "name": "get_equipment_state",
        "description": "Return nearby equipment events and only explicitly requested RAW tags.",
        "parameters": {
            "type": "object",
            "properties": {
                "equipment": {"type": "string"},
                "at_time_s": {"type": "number"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["equipment", "at_time_s"],
        },
    },
]


def _system_prompt() -> str:
    path = SERVICE_ROOT / "triplens" / "hybrid_agent_prompt.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return (
        "You are the TripLens read-only incident analysis agent. "
        "Use tools for evidence. Return only structured JSON. "
        "Unsupported claims must be UNKNOWN."
    )


def _json_from_text(text: str) -> dict[str, Any]:
    candidate = (text or "").strip()
    fence = chr(96) * 3
    if candidate.startswith(fence):
        lines = candidate.splitlines()
        if lines and lines[0].startswith(fence):
            lines = lines[1:]
        if lines and lines[-1].strip() == fence:
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start >= 0 and end >= start:
        candidate = candidate[start : end + 1]
    value = json.loads(candidate)
    if not isinstance(value, dict):
        raise ValueError("Gemini output must be a JSON object")
    return value


def fail_closed_contract(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    source = dict(raw or {})
    source.setdefault("critical_events", [])
    source.setdefault(
        "primary_cause",
        {"status": "UNKNOWN", "claim": "", "evidence_ids": [], "related_tags": []},
    )
    source.setdefault(
        "direct_trigger",
        {"status": "UNKNOWN", "claim": "", "evidence_ids": [], "related_tags": []},
    )
    source.setdefault("propagation", [])
    source.setdefault("causal_chain", [])
    source.setdefault("counter_evidence", [])
    source.setdefault("additional_evidence_required", [])
    source.setdefault("review_recommendations", [])
    source["verification_gate"] = "HOLD"
    source["verification_notes"] = [
        "Vercel P0: Gemini result returned; deterministic final Verification Gate not yet promoted to PASS."
    ]
    return source


def run_gemini_analysis(
    store: EvidenceStore,
    *,
    run_id: str,
    data_digest: str,
    model: str | None = None,
) -> dict[str, Any]:
    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY is not configured")

    from google import genai

    api_key = os.environ["GEMINI_API_KEY"].strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is empty")
    client = genai.Client(api_key=api_key)
    session = AgentToolSession(store)
    model_name = model or os.getenv("TRIPLENS_GEMINI_MODEL", DEFAULT_MODEL)
    bootstrap = store.build_agent_bootstrap(run_id=run_id, data_digest=data_digest)

    initial_text = (
        "Analyze this TripLens incident using only the provided tools. "
        "Do not assume a hidden scenario answer. Seek counter-evidence before finalizing. "
        "After tool use, return the required structured JSON object only.\n\n"
        f"BOOTSTRAP:\n{json.dumps(bootstrap, ensure_ascii=False)}"
    )
    history: list[dict[str, Any]] = [
        {
            "type": "user_input",
            "content": [{"type": "text", "text": initial_text}],
        }
    ]

    for _turn in range(12):
        interaction = client.interactions.create(
            model=model_name,
            store=False,
            input=history,
            tools=TOOL_DECLARATIONS,
            system_instruction=_system_prompt(),
        )
        for step in interaction.steps:
            history.append(step.model_dump())

        function_calls = [step for step in interaction.steps if step.type == "function_call"]
        if not function_calls:
            return fail_closed_contract(_json_from_text(interaction.output_text or ""))

        for step in function_calls:
            if session.calls_used >= session.max_calls:
                history.append(
                    {
                        "type": "user_input",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "The tool-call budget is exhausted. "
                                    "Return the structured result now. Use UNKNOWN and Additional Evidence Required "
                                    "for unsupported conclusions."
                                ),
                            }
                        ],
                    }
                )
                final_interaction = client.interactions.create(
                    model=model_name,
                    store=False,
                    input=history,
                    system_instruction=_system_prompt(),
                )
                return fail_closed_contract(_json_from_text(final_interaction.output_text or ""))

            try:
                result = session.call(step.name, dict(step.arguments or {}))
            except Exception as exc:
                result = {"status": "TOOL_ERROR", "tool": step.name, "error": str(exc)}

            history.append(
                {
                    "type": "function_result",
                    "name": step.name,
                    "call_id": step.id,
                    "result": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                }
            )

    return fail_closed_contract(
        {
            "additional_evidence_required": [
                "Agent interaction turn limit reached before a structured conclusion was produced."
            ]
        }
    )
