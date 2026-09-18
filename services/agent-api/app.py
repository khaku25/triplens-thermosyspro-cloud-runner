"""TripLens Vercel Agent API — P0 migration service."""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from bridge import build_store, evidence_readiness, public_contract, sha256_files
from gemini_agent import run_gemini_analysis

MAX_DIRECT_UPLOAD_BYTES = 4_000_000

app = FastAPI(title="TripLens Agent API", version="0.1.0")

configured_origin = os.getenv("TRIPLENS_WEB_ORIGIN", "").strip()
origins = [configured_origin] if configured_origin else ["http://localhost:3000"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "triplens-agent-api",
        "read_only": True,
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY")),
    }


@app.get("/contract")
def contract():
    return public_contract()


async def _save_upload(upload: UploadFile, destination: Path, budget: int) -> int:
    size = 0
    with destination.open("wb") as stream:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > budget:
                raise HTTPException(
                    status_code=413,
                    detail="Direct upload exceeds the P0 safe limit. Use the Vercel Blob upload path.",
                )
            stream.write(chunk)
    return size


async def _prepare_dual_log(event: UploadFile, raw: UploadFile):
    folder = tempfile.TemporaryDirectory(prefix="triplens-vercel-")
    root = Path(folder.name)
    event_path = root / "EVENT.csv"
    raw_path = root / "RAW.csv"
    try:
        event_size = await _save_upload(event, event_path, MAX_DIRECT_UPLOAD_BYTES)
        raw_budget = MAX_DIRECT_UPLOAD_BYTES - event_size
        if raw_budget <= 0:
            raise HTTPException(status_code=413, detail="Combined EVENT + RAW direct upload limit exceeded.")
        await _save_upload(raw, raw_path, raw_budget)
        return folder, event_path, raw_path
    except Exception:
        folder.cleanup()
        raise


@app.post("/bootstrap")
async def bootstrap(event: UploadFile = File(...), raw: UploadFile = File(...)):
    folder, event_path, raw_path = await _prepare_dual_log(event, raw)
    try:
        run_id = f"RUN-{uuid.uuid4().hex[:12].upper()}"
        digest = sha256_files(event_path, raw_path)
        store = build_store(event_path, raw_path)
        return {
            "run_id": run_id,
            "data_digest": digest,
            "bootstrap": store.build_agent_bootstrap(run_id=run_id, data_digest=digest),
            "evidence_readiness": evidence_readiness(event_path, raw_path),
            "contract": public_contract(),
        }
    finally:
        folder.cleanup()


@app.post("/analyze")
async def analyze(event: UploadFile = File(...), raw: UploadFile = File(...)):
    if not os.getenv("GEMINI_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="GEMINI_API_KEY is not configured for this Preview environment.",
        )

    folder, event_path, raw_path = await _prepare_dual_log(event, raw)
    try:
        run_id = f"RUN-{uuid.uuid4().hex[:12].upper()}"
        digest = sha256_files(event_path, raw_path)
        store = build_store(event_path, raw_path)
        readiness = evidence_readiness(event_path, raw_path)
        analysis = run_gemini_analysis(store, run_id=run_id, data_digest=digest)
        return {
            "run_id": run_id,
            "data_digest": digest,
            "analysis": analysis,
            "evidence_readiness": readiness,
            "tool_contract": store.tool_manifest(),
        }
    finally:
        folder.cleanup()
