"""Independent semantic reviewer for TripLens analysis/report placement.

The reviewer is a separate Gemini interaction. It receives only the evidence package,
analysis output, and report rows. It never receives hidden scenario labels or expected answers.
"""
from __future__ import annotations
import json
import os
from typing import Any

DEFAULT_REVIEWER_MODEL = "gemini-3.8-flash"
REPORT_SECTIONS = [
    "개요",
    "사고 발생 전 운전 현황",
    "장애 현상",
    "시간대별 조치사항",
    "발생 원인",
    "조치 결과",
    "추정 원인 및 미확인 사항",
    "재발방지 대책 — 검토 권고사항",
    "증거자료",
]

FINDING_SCHEMA = {
    "type": "object",
    "properties": {
        "severity": {"type": "string", "enum": ["INFO", "WARNING", "CRITICAL"]},
        "category": {"type": "string", "enum": ["CONTENT", "PLACEMENT", "EVIDENCE", "CHRONOLOGY", "UNCERTAINTY", "SAFETY"]},
        "row_index": {"type": ["integer", "null"]},
        "current_section": {"type": ["string", "null"]},
        "expected_section": {"type": ["string", "null"]},
        "finding": {"type": "string"},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["severity", "category", "row_index", "current_section", "expected_section", "finding", "evidence_ids"],
    "additionalProperties": False,
}

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "review_status": {"type": "string", "enum": ["PASS", "REVIEW_REQUIRED", "FAIL"]},
        "summary_ko": {"type": "string"},
        "findings": {"type": "array", "items": FINDING_SCHEMA},
        "missing_required_sections": {"type": "array", "items": {"type": "string"}},
        "human_review_focus": {"type": "array", "items": {"type": "string"}},
        "content_score": {"type": "integer", "minimum": 0, "maximum": 5},
        "placement_score": {"type": "integer", "minimum": 0, "maximum": 5},
        "evidence_score": {"type": "integer", "minimum": 0, "maximum": 5},
    },
    "required": [
        "review_status", "summary_ko", "findings", "missing_required_sections",
        "human_review_focus", "content_score", "placement_score", "evidence_score",
    ],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """당신은 발전소 고장보고서를 검토하는 독립 Engineering Reviewer입니다.
분석 Agent의 답을 그대로 믿지 말고 제공된 EVENT/RAW 실제 근거, 등록 Logic, 분석 결과, 보고서 행 배치를 서로 대조하십시오.

검토 범위:
1) 내용: Primary Cause, Direct Trigger, Propagation, Causal Chain이 실제 근거와 시간관계에 맞게 표현됐는가.
2) 배치: 아래 9개 사람용 고장보고서 섹션에 의미상 맞게 들어갔는가.
3) 근거성: 주장마다 인용 Evidence ID가 실제 catalog에 존재하고 해당 태그/값/시간을 뒷받침하는가.
4) 불확실성: RAW 표본 구간, 동일시각 사건, UNKNOWN/HOLD를 과도한 확정 표현으로 바꾸지 않았는가.
5) 안전: 설비 조작 명령이나 자동 복구 승인을 만들지 않았는가.

중요:
- 숨은 시나리오 정답은 제공되지 않으며 추정하지 마십시오.
- Logic 등록은 설계관계 확인이지 해당 사고의 실제 원인 확정이 아닙니다.
- RAW에서 외부 명령이 관측되어도 인간 운전자의 의도/승인/계획정지를 추론하지 마십시오.
- GT/ST가 동시에 동작하면 공통 입력 병렬동작과 intertrip을 구분하십시오.
- 86GT 등 제공 근거에 없는 태그를 만들지 마십시오.
- 보고서 배치가 잘못되면 내용이 맞더라도 PLACEMENT finding을 내십시오.
- 사람이 반드시 봐야 하는 불확실성이 남아 있으면 REVIEW_REQUIRED가 정상입니다.
- 최종 공학적 승인 권한은 사람에게 있습니다.
"""

def _json_from_text(text: str) -> dict[str, Any]:
    value = json.loads((text or "").strip())
    if not isinstance(value, dict):
        raise ValueError("reviewer output must be an object")
    return value

def run_engineering_review(package: dict[str, Any], *, client=None, model: str | None = None) -> dict[str, Any]:
    if client is None:
        key = os.getenv("GEMINI_API_KEY", "").strip()
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        from google import genai
        client = genai.Client(api_key=key, http_options={"timeout": 60000})
    model_name = model or os.getenv("TRIPLENS_REVIEWER_MODEL") or os.getenv("TRIPLENS_GEMINI_MODEL") or DEFAULT_REVIEWER_MODEL
    safe_package = {
        "report_sections": REPORT_SECTIONS,
        "analysis": package.get("analysis", {}),
        "report_rows": package.get("report_rows", []),
        "evidence_catalog": package.get("evidence_catalog", []),
        "events": package.get("events", []),
        "logic_rows": package.get("logic_rows", []),
        "validation": package.get("validation", {}),
    }
    interaction = client.interactions.create(
        model=model_name,
        store=False,
        input=[{
            "type": "user_input",
            "content": [{"type": "text", "text": "다음 TripLens 사고분석과 보고서 배치를 검토하십시오.\n" + json.dumps(safe_package, ensure_ascii=False)}],
        }],
        system_instruction=SYSTEM_PROMPT,
        response_format={"type": "text", "mime_type": "application/json", "schema": REVIEW_SCHEMA},
    )
    result = _json_from_text(interaction.output_text or "")
    result["reviewer_model"] = model_name
    result["reviewer_role"] = "INDEPENDENT_SEMANTIC_REVIEW_NOT_FINAL_ENGINEERING_APPROVAL"
    return result
