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
from privacy_guardian.reporting import entity_label, mode_note, report_payload, source_label
from privacy_guardian.reversible import (
    MAP_EXTENSION,
    ReversibleMapError,
    decrypt_mapping,
    encrypt_mapping,
    restore_text,
)

MAX_TEXT_LENGTH = 100_000
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_MAP_BYTES = 2 * 1024 * 1024
MAX_REQUEST_BYTES = MAX_FILE_BYTES + 512 * 1024
WEB_SUPPORTED_MODES = tuple(mode for mode in ANONYMIZATION_MODES if mode != "reversible")
REVERSIBLE_DOCUMENT_EXTENSIONS = {".txt", ".docx"}
DOCUMENT_MEDIA_TYPES = {
    ".csv": "text/csv; charset=utf-8",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".md": "text/markdown; charset=utf-8",
    ".pdf": "application/pdf",
    ".txt": "text/plain; charset=utf-8",
}

logging.getLogger("uvicorn.access").disabled = True

app = FastAPI(
    title="OMISSIS Web",
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
    mode: AnonymizationMode = "maximum"
    passphrase: str | None = None


def serialize_finding(finding: Finding, text: str) -> dict[str, object]:
    return {
        "entity_type": finding.entity_type,
        "label": entity_label(finding.entity_type),
        "start": finding.start,
        "end": finding.end,
        "score": round(finding.score, 4),
        "source": finding.source,
        "source_label": source_label(finding.source),
        "preview": text[finding.start : finding.end],
    }


@app.middleware("http")
async def privacy_headers(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.method == "POST":
        content_length = request.headers.get("content-length")
        if content_length is None:
            # Chunked bodies would bypass the size check below.
            return JSONResponse(
                status_code=411,
                content={"detail": "Richiesta senza Content-Length non supportata."},
            )
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
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
        "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    )
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
        "ner_active": engine.ner_active,
        "max_text_length": MAX_TEXT_LENGTH,
        "max_file_bytes": MAX_FILE_BYTES,
        "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
        "modes": WEB_SUPPORTED_MODES,
        "mode_notes": {mode: mode_note(mode) for mode in WEB_SUPPORTED_MODES},
        "reversible_document_extensions": sorted(REVERSIBLE_DOCUMENT_EXTENSIONS),
    }


@app.post("/api/analyze")
async def analyze(payload: TextPayload):
    _reject_web_reversible(payload.mode)
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
    _reject_web_reversible(payload.mode)
    _validate_text_length(payload.text)
    passphrase = _required_passphrase(payload.mode, payload.passphrase)
    if not payload.text.strip():
        response = {
            "text": "",
            "findings": [],
            "report": report_payload([], payload.mode),
            "engine_status": engine.status,
        }
        if payload.mode == "reversible":
            response.update(_mapping_payload((), passphrase, "testo_anonimizzato"))
        return response
    findings = engine.analyze(payload.text, payload.mode)
    response = {
        "text": "",
        "findings": [serialize_finding(finding, payload.text) for finding in findings],
        "report": report_payload(findings, payload.mode),
        "engine_status": engine.status,
    }
    if payload.mode == "reversible":
        reversible_result = engine.anonymize_reversible(payload.text, findings)
        response["text"] = reversible_result.text
        response.update(_mapping_payload(reversible_result.mapping, passphrase, "testo_anonimizzato"))
    else:
        response["text"] = engine.anonymize(payload.text, findings, payload.mode)
    return response


@app.post("/api/anonymize-document")
async def anonymize_document(
    mode: AnonymizationMode = Form("maximum"),
    passphrase: str = Form(""),
    file: UploadFile = File(...),
):
    _reject_web_reversible(mode)
    filename = _safe_upload_filename(file.filename)
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise HTTPException(status_code=400, detail=f"Formato non supportato. Usa uno di questi: {supported}")
    _validate_document_mode(mode, extension)
    passphrase = _required_passphrase(mode, passphrase)

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

    response = {
        "filename": result.filename,
        "media_type": DOCUMENT_MEDIA_TYPES.get(Path(result.filename).suffix.lower(), "application/octet-stream"),
        "content_base64": base64.b64encode(result.data).decode("ascii"),
        "findings": [serialize_finding(finding, loaded.text) for finding in result.findings],
        "report": report_payload(result.findings, mode),
        "engine_status": engine.status,
    }
    if mode == "reversible":
        response.update(_mapping_payload(result.reversible_mapping, passphrase, Path(result.filename).stem))
    return response


@app.post("/api/analyze-document")
async def analyze_document(
    mode: AnonymizationMode = Form("maximum"),
    file: UploadFile = File(...),
):
    _reject_web_reversible(mode)
    filename = _safe_upload_filename(file.filename)
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise HTTPException(status_code=400, detail=f"Formato non supportato. Usa uno di questi: {supported}")
    _validate_document_mode(mode, extension)

    content = await _read_upload(file)
    if not content:
        raise HTTPException(status_code=400, detail="Il file caricato è vuoto.")

    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = Path(tmpdir) / filename
        input_path.write_bytes(content)
        try:
            loaded = load_document(input_path)
            _validate_text_length(loaded.text)
            findings = engine.analyze(loaded.text, mode)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "filename": filename,
        "findings": [serialize_finding(finding, loaded.text) for finding in findings],
        "report": report_payload(findings, mode),
        "engine_status": engine.status,
    }


@app.post("/api/restore")
async def restore(
    text: str = Form(""),
    passphrase: str = Form(""),
    mapping: UploadFile = File(...),
):
    raise HTTPException(
        status_code=400,
        detail="Il ripristino reversibile non è disponibile nella web app. Usa l'app desktop OMISSIS.",
    )

    # Kept below as the shared implementation for a future browser-local flow.
    _validate_text_length(text)
    if not text:
        raise HTTPException(status_code=400, detail="Inserisci il testo anonimizzato da ricostruire.")
    passphrase = _required_passphrase("reversible", passphrase)
    mapping_data = await _read_mapping_upload(mapping)
    try:
        entries = decrypt_mapping(mapping_data, passphrase)
    except ReversibleMapError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail="File mappa reversibile non valido.") from exc

    return {
        "text": restore_text(text, entries),
        "entries": len(entries),
        "engine_status": engine.status,
    }


def _validate_text_length(text: str) -> None:
    if len(text) > MAX_TEXT_LENGTH:
        raise HTTPException(
            status_code=413,
            detail=f"Testo troppo lungo. Limite massimo: {MAX_TEXT_LENGTH:,} caratteri.".replace(",", "."),
        )


def _required_passphrase(mode: AnonymizationMode, passphrase: str | None) -> str:
    normalized = passphrase.strip() if isinstance(passphrase, str) else ""
    if mode == "reversible" and not normalized:
        raise HTTPException(status_code=400, detail="Per la modalità reversibile inserisci una passphrase.")
    return normalized


def _reject_web_reversible(mode: AnonymizationMode) -> None:
    if mode == "reversible":
        raise HTTPException(
            status_code=400,
            detail="La modalità reversibile è disponibile solo nell'app desktop OMISSIS.",
        )


def _validate_document_mode(mode: AnonymizationMode, extension: str) -> None:
    if mode != "reversible":
        return
    if extension == ".pdf":
        raise HTTPException(
            status_code=400,
            detail="La modalità reversibile è rifiutata per i PDF. Usa Massima protezione per creare un PDF redatto.",
        )
    if extension not in REVERSIBLE_DOCUMENT_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="La modalità reversibile è disponibile solo per testo incollato, file TXT e DOCX.",
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


async def _read_mapping_upload(file: UploadFile) -> bytes:
    content = await file.read(MAX_MAP_BYTES + 1)
    await file.close()
    if len(content) > MAX_MAP_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"La mappa reversibile è troppo grande. Limite massimo: {_format_bytes(MAX_MAP_BYTES)}.",
        )
    if not content:
        raise HTTPException(status_code=400, detail="Il file mappa reversibile è vuoto.")
    return content


def _mapping_payload(mapping, passphrase: str, base_name: str) -> dict[str, object]:
    encrypted = encrypt_mapping(mapping, passphrase)
    return {
        "mapping_filename": f"{base_name}{MAP_EXTENSION}",
        "mapping_media_type": "application/json",
        "mapping_base64": base64.b64encode(encrypted).decode("ascii"),
    }


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
    parser = argparse.ArgumentParser(description="Run OMISSIS Web.")
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
