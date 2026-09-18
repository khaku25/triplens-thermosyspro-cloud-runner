# TripLens Vercel Migration P0

This branch is a non-production migration target. The current GPT.site remains untouched.

## Frontend

`apps/web` reproduces the current TripLens shell:

- Dual Log intake
- five-stage analysis navigation
- dynamic Current V8 Logic Master summary
- Hybrid Agent cause view
- evidence view
- recovery review with human approval
- synthetic `/demo`

Run locally:

```bash
cd apps/web
npm install
npm run dev
```

Set `NEXT_PUBLIC_TRIPLENS_API_BASE` to the Python service URL.

## Agent API

`services/agent-api` is a FastAPI service using the existing repository evidence layer.

Endpoints:

- `GET /health`
- `GET /contract`
- `POST /bootstrap`
- `POST /analyze`

The service reuses:

- `scripts/triplens_agent_tools.py`
- `scripts/triplens_dual_log_analyzer.py`
- `docs/triplens_hybrid_agent_prompt.md`
- `config/alarm_registry_v1.csv`

Gemini uses the current Interactions API in stateless mode (`store=false`) and the six bounded TripLens tools. The service preserves the 8-call tool budget.

P0 is deliberately fail-closed: returned Gemini analysis remains `Verification Gate = HOLD` until the full deterministic Verification Gate is ported.

## Deployment shape

Recommended Vercel Services setup:

- Web service root: `apps/web`
- Python service source: repository root with entrypoint `services/agent-api/app.py`, or an equivalent service configuration that includes the root `scripts/`, `config/`, and `docs/` dependencies.

Do not deploy Modelica, MATLAB, OPC UA control paths, or plant-write functionality to the web runtime.

## Direct-upload limit

P0 caps combined EVENT + RAW upload at 4,000,000 bytes to stay below the Vercel Function payload limit. Larger RAW logs must use a later private Vercel Blob client-upload path.

## Required environment

Copy `.env.vercel.example` values into the Vercel projects/services. Never commit a Gemini key.
