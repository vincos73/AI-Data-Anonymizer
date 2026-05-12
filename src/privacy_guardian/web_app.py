from __future__ import annotations

import argparse
import logging
from importlib import resources

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from privacy_guardian import __version__
from privacy_guardian.models import Finding
from privacy_guardian.privacy_engine import PrivacyEngine

MAX_TEXT_LENGTH = 100_000

logging.getLogger("uvicorn.access").disabled = True

app = FastAPI(
    title="AI Data Anonymizer Web",
    description="Privacy-first web interface for Italian text anonymization.",
    version=__version__,
    docs_url=None,
    redoc_url=None,
)
engine = PrivacyEngine()
static_dir = resources.files("privacy_guardian").joinpath("web_static")
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


class TextPayload(BaseModel):
    text: str = Field(max_length=MAX_TEXT_LENGTH)


def serialize_finding(finding: Finding, text: str) -> dict[str, object]:
    return {
        "entity_type": finding.entity_type,
        "start": finding.start,
        "end": finding.end,
        "score": round(finding.score, 4),
        "source": finding.source,
        "preview": text[finding.start : finding.end],
    }


@app.middleware("http")
async def privacy_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": "Errore durante l'elaborazione."})


@app.get("/")
async def index():
    return FileResponse(static_dir.joinpath("index.html"))


@app.get("/api/health")
async def health():
    return {"ok": True, "engine_status": engine.status, "max_text_length": MAX_TEXT_LENGTH}


@app.post("/api/analyze")
async def analyze(payload: TextPayload):
    if not payload.text.strip():
        return {"findings": [], "engine_status": engine.status}
    findings = engine.analyze(payload.text)
    return {
        "findings": [serialize_finding(finding, payload.text) for finding in findings],
        "engine_status": engine.status,
    }


@app.post("/api/anonymize")
async def anonymize(payload: TextPayload):
    if not payload.text.strip():
        return {"text": "", "findings": [], "engine_status": engine.status}
    findings = engine.analyze(payload.text)
    return {
        "text": engine.anonymize(payload.text, findings),
        "findings": [serialize_finding(finding, payload.text) for finding in findings],
        "engine_status": engine.status,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AI Data Anonymizer Web.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    uvicorn.run(
        "privacy_guardian.web_app:app",
        host=args.host,
        port=args.port,
        access_log=False,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
