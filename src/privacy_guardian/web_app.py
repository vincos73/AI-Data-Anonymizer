from __future__ import annotations

import argparse
import base64
import logging
from importlib import resources
from pathlib import Path
import tempfile

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from privacy_guardian import __version__
from privacy_guardian.document_service import SUPPORTED_EXTENSIONS, anonymize_loaded_document, load_document
from privacy_guardian.models import ANONYMIZATION_MODES, AnonymizationMode, Finding
from privacy_guardian.privacy_engine import PrivacyEngine
from privacy_guardian.reporting import mode_note, report_payload

MAX_TEXT_LENGTH = 100_000
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_REQUEST_BYTES = MAX_FILE_BYTES + 512 * 1024
DOCUMENT_MEDIA_TYPES = {
    ".csv": "text/csv; charset=utf-8",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".md": "text/markdown; charset=utf-8",
    ".pdf": "application/pdf",
    ".txt": "text/plain; charset=utf-8",
}

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
    text: str
    mode: AnonymizationMode = "standard"


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
    content_length = request.headers.get("content-length")
    if request.url.path.startswith("/api/") and content_length:
        try:
            request_bytes = int(content_length)
        except ValueError:
            request_bytes = 0
        if request_bytes > MAX_REQUEST_BYTES:
            return JSONResponse(
                status_code=413,
                content={"detail": f"Richiesta troppo grande. Limite massimo: {_format_bytes(MAX_FILE_BYTES)}."},
            )

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
    return {
        "ok": True,
        "engine_status": engine.status,
        "max_text_length": MAX_TEXT_LENGTH,
        "max_file_bytes": MAX_FILE_BYTES,
        "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
        "modes": ANONYMIZATION_MODES,
        "mode_notes": {mode: mode_note(mode) for mode in ANONYMIZATION_MODES},
    }


@app.post("/api/analyze")
async def analyze(payload: TextPayload):
    _validate_text_length(payload.text)
    if not payload.text.strip():
        return {"findings": [], "report": report_payload([], payload.mode), "engine_status": engine.status}
    findings = engine.analyze(payload.text, payload.mode)
    return {
        "findings": [serialize_finding(finding, payload.text) for finding in findings],
        "report": report_payload(findings, payload.mode),
        "engine_status": engine.status,
    }


@app.post("/api/anonymize")
async def anonymize(payload: TextPayload):
    _validate_text_length(payload.text)
    if not payload.text.strip():
        return {"text": "", "findings": [], "report": report_payload([], payload.mode), "engine_status": engine.status}
    findings = engine.analyze(payload.text, payload.mode)
    return {
        "text": engine.anonymize(payload.text, findings, payload.mode),
        "findings": [serialize_finding(finding, payload.text) for finding in findings],
        "report": report_payload(findings, payload.mode),
        "engine_status": engine.status,
    }


@app.post("/api/anonymize-document")
async def anonymize_document(
    mode: AnonymizationMode = Form("standard"),
    file: UploadFile = File(...),
):
    filename = _safe_upload_filename(file.filename)
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise HTTPException(status_code=400, detail=f"Formato non supportato. Usa uno di questi: {supported}")

    content = await _read_upload(file)
    if not content:
        raise HTTPException(status_code=400, detail="Il file caricato è vuoto.")

    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = Path(tmpdir) / filename
        input_path.write_bytes(content)
        try:
            loaded = load_document(input_path)
            _validate_text_length(loaded.text)
            result = anonymize_loaded_document(loaded, engine, mode)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "filename": result.filename,
        "media_type": DOCUMENT_MEDIA_TYPES.get(Path(result.filename).suffix.lower(), "application/octet-stream"),
        "content_base64": base64.b64encode(result.data).decode("ascii"),
        "findings": [serialize_finding(finding, loaded.text) for finding in result.findings],
        "report": report_payload(result.findings, mode),
        "engine_status": engine.status,
    }


def _validate_text_length(text: str) -> None:
    if len(text) > MAX_TEXT_LENGTH:
        raise HTTPException(
            status_code=413,
            detail=f"Testo troppo lungo. Limite massimo: {MAX_TEXT_LENGTH:,} caratteri.".replace(",", "."),
        )


async def _read_upload(file: UploadFile) -> bytes:
    content = await file.read(MAX_FILE_BYTES + 1)
    await file.close()
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File troppo grande. Limite massimo: {_format_bytes(MAX_FILE_BYTES)}.",
        )
    return content


def _safe_upload_filename(filename: str | None) -> str:
    normalized = (filename or "documento.txt").replace("\\", "/")
    name = Path(normalized).name.strip()
    return name or "documento.txt"


def _format_bytes(value: int) -> str:
    if value >= 1024 * 1024 and value % (1024 * 1024) == 0:
        return f"{value // (1024 * 1024)} MB"
    if value >= 1024 and value % 1024 == 0:
        return f"{value // 1024} KB"
    return f"{value} byte"


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
