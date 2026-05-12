from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import subprocess
import sys
import tempfile
from textwrap import wrap

from privacy_guardian.models import Finding
from privacy_guardian.privacy_engine import PrivacyEngine


BASE_SUPPORTED_EXTENSIONS = {".txt", ".md", ".csv", ".docx", ".pdf"}
LEGACY_DOC_SUPPORTED = sys.platform == "darwin" and Path("/usr/bin/textutil").exists()
SUPPORTED_EXTENSIONS = BASE_SUPPORTED_EXTENSIONS | ({".doc"} if LEGACY_DOC_SUPPORTED else set())


@dataclass(frozen=True)
class LoadedDocument:
    path: Path
    text: str
    extension: str


@dataclass(frozen=True)
class AnonymizedDocument:
    filename: str
    data: bytes
    text: str
    findings: list[Finding]


def load_document(path: str | Path) -> LoadedDocument:
    document_path = Path(path)
    extension = document_path.suffix.lower()

    if extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(f"Formato non supportato. Usa uno di questi: {supported}")

    if extension in {".txt", ".md", ".csv"}:
        text = document_path.read_text(encoding="utf-8", errors="replace")
    elif extension == ".doc":
        text = _read_legacy_doc(document_path)
    elif extension == ".docx":
        text = _read_docx(document_path)
    else:
        text = _read_pdf(document_path)

    return LoadedDocument(path=document_path, text=text, extension=extension)


def anonymize_loaded_document(document: LoadedDocument, engine: PrivacyEngine) -> AnonymizedDocument:
    findings = engine.analyze(document.text)
    anonymized_text = engine.anonymize(document.text, findings)
    output_name = f"{document.path.stem}_anonimizzato{_output_extension(document.extension)}"

    if document.extension in {".txt", ".md", ".csv"}:
        data = anonymized_text.encode("utf-8")
    elif document.extension == ".doc":
        data = _anonymize_legacy_doc(document.path, engine)
    elif document.extension == ".docx":
        data = _anonymize_docx(document.path, engine)
    else:
        data = _write_pdf(anonymized_text)

    return AnonymizedDocument(filename=output_name, data=data, text=anonymized_text, findings=findings)


def _output_extension(extension: str) -> str:
    if extension == ".pdf":
        return ".pdf"
    if extension in {".doc", ".docx"}:
        return ".docx"
    return ".txt"


def _read_docx(path: Path) -> str:
    from docx import Document

    document = Document(path)
    parts: list[str] = []
    parts.extend(paragraph.text for paragraph in _iter_docx_paragraphs(document) if paragraph.text)

    return "\n".join(parts)


def _anonymize_docx(path: Path, engine: PrivacyEngine) -> bytes:
    from docx import Document

    document = Document(path)

    for paragraph in _iter_docx_paragraphs(document):
        _anonymize_paragraph_runs(paragraph, engine)

    output = BytesIO()
    document.save(output)
    return output.getvalue()


def _read_legacy_doc(path: Path) -> str:
    result = _run_textutil("-convert", "txt", "-stdout", str(path))
    return result.stdout.decode("utf-8", errors="replace").strip()


def _anonymize_legacy_doc(path: Path, engine: PrivacyEngine) -> bytes:
    with tempfile.TemporaryDirectory() as tmpdir:
        converted_path = Path(tmpdir) / f"{path.stem}.docx"
        _run_textutil("-convert", "docx", "-output", str(converted_path), str(path))
        return _anonymize_docx(converted_path, engine)


def _run_textutil(*args: str) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["/usr/bin/textutil", *args],
            check=True,
            capture_output=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Conversione .doc disponibile solo su macOS con textutil.") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode("utf-8", errors="replace").strip()
        message = f"Conversione documento non riuscita: {detail}" if detail else "Conversione documento non riuscita."
        raise RuntimeError(message) from exc


def _iter_docx_paragraphs(document):
    yield from document.paragraphs
    for table in document.tables:
        yield from _iter_table_paragraphs(table)
    for section in document.sections:
        yield from section.header.paragraphs
        yield from section.footer.paragraphs
        for table in section.header.tables:
            yield from _iter_table_paragraphs(table)
        for table in section.footer.tables:
            yield from _iter_table_paragraphs(table)


def _iter_table_paragraphs(table):
    for row in table.rows:
        for cell in row.cells:
            yield from cell.paragraphs
            for nested_table in cell.tables:
                yield from _iter_table_paragraphs(nested_table)


def _anonymize_paragraph_runs(paragraph, engine: PrivacyEngine) -> None:
    if not paragraph.runs:
        return

    text = "".join(run.text for run in paragraph.runs)
    if not text:
        return

    findings = engine.analyze(text)
    if not findings:
        return

    replacements = [
        (finding.start, finding.end, engine.anonymize(text[finding.start : finding.end], [Finding(finding.entity_type, 0, finding.end - finding.start, finding.score)]))
        for finding in findings
    ]
    cursor = 0
    for run in paragraph.runs:
        run_start = cursor
        run_end = run_start + len(run.text)
        cursor = run_end
        pieces: list[str] = []
        text_cursor = run_start

        for start, end, replacement in replacements:
            if end <= run_start or start >= run_end:
                continue
            if start >= text_cursor:
                pieces.append(text[text_cursor:start])
            if run_start <= start < run_end:
                pieces.append(replacement)
            text_cursor = max(text_cursor, min(end, run_end))

        pieces.append(text[text_cursor:run_end])
        run.text = "".join(pieces)


def _read_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(page.strip() for page in pages if page.strip())


def _write_pdf(text: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    width, height = A4
    x = 20 * mm
    y = height - 22 * mm
    line_height = 13

    for paragraph in text.splitlines() or [""]:
        lines = wrap(paragraph, width=92) if paragraph else [""]
        for line in lines:
            if y < 22 * mm:
                pdf.showPage()
                y = height - 22 * mm
            pdf.drawString(x, y, line)
            y -= line_height
        y -= 4

    pdf.save()
    return output.getvalue()
