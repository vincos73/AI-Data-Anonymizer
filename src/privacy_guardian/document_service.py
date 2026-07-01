from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import subprocess
import sys
import tempfile
from textwrap import wrap
import xml.etree.ElementTree as ET
import zipfile

from privacy_guardian.models import AnonymizationMode, Finding
from privacy_guardian.privacy_engine import PrivacyEngine


BASE_SUPPORTED_EXTENSIONS = {".txt", ".md", ".csv", ".docx", ".pdf"}
LEGACY_DOC_SUPPORTED = sys.platform == "darwin" and Path("/usr/bin/textutil").exists()
SUPPORTED_EXTENSIONS = BASE_SUPPORTED_EXTENSIONS | ({".doc"} if LEGACY_DOC_SUPPORTED else set())
OOXML_NAMESPACES = {
    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "dcmitype": "http://purl.org/dc/dcmitype/",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "v": "urn:schemas-microsoft-com:vml",
    "vt": "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes",
}
TEXT_NODE_NAMES = {"t", "delText", "instrText"}
PERSONAL_ATTRIBUTE_NAMES = {"author", "initials", "lastModifiedBy"}
HIDDEN_TEXT_CONTAINER_NAMES = {"txbxContent", "del", "moveFrom"}

for prefix, uri in OOXML_NAMESPACES.items():
    ET.register_namespace(prefix, uri)


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


def anonymize_loaded_document(
    document: LoadedDocument,
    engine: PrivacyEngine,
    mode: AnonymizationMode = "standard",
) -> AnonymizedDocument:
    findings = engine.analyze(document.text, mode)
    anonymized_text = engine.anonymize(document.text, findings, mode)
    output_name = f"{document.path.stem}_anonimizzato{_output_extension(document.extension)}"

    if document.extension in {".txt", ".md", ".csv"}:
        data = anonymized_text.encode("utf-8")
    elif document.extension == ".doc":
        data = _anonymize_legacy_doc(document.path, engine, mode)
    elif document.extension == ".docx":
        data = _anonymize_docx(document.path, engine, mode)
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


def _anonymize_docx(path: Path, engine: PrivacyEngine, mode: AnonymizationMode) -> bytes:
    from docx import Document

    document = Document(path)

    for paragraph in _iter_docx_standalone_paragraphs(document):
        _anonymize_paragraph_runs(paragraph, engine, mode)
    for table in _iter_docx_tables(document):
        _anonymize_table_rows(table, engine, mode)

    output = BytesIO()
    document.save(output)
    return _sanitize_docx_package(output.getvalue(), engine, mode)


def _read_legacy_doc(path: Path) -> str:
    result = _run_textutil("-convert", "txt", "-stdout", str(path))
    return result.stdout.decode("utf-8", errors="replace").strip()


def _anonymize_legacy_doc(path: Path, engine: PrivacyEngine, mode: AnonymizationMode) -> bytes:
    with tempfile.TemporaryDirectory() as tmpdir:
        converted_path = Path(tmpdir) / f"{path.stem}.docx"
        _run_textutil("-convert", "docx", "-output", str(converted_path), str(path))
        return _anonymize_docx(converted_path, engine, mode)


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


def _iter_docx_standalone_paragraphs(document):
    yield from document.paragraphs
    for section in document.sections:
        yield from section.header.paragraphs
        yield from section.footer.paragraphs


def _iter_docx_tables(document):
    yield from document.tables
    for table in document.tables:
        yield from _iter_nested_tables(table)
    for section in document.sections:
        yield from section.header.tables
        for table in section.header.tables:
            yield from _iter_nested_tables(table)
        yield from section.footer.tables
        for table in section.footer.tables:
            yield from _iter_nested_tables(table)


def _iter_nested_tables(table):
    for row in table.rows:
        for cell in row.cells:
            yield from cell.tables
            for nested_table in cell.tables:
                yield from _iter_nested_tables(nested_table)


def _iter_table_paragraphs(table):
    for row in table.rows:
        for cell in row.cells:
            yield from cell.paragraphs
            for nested_table in cell.tables:
                yield from _iter_table_paragraphs(nested_table)


def _anonymize_table_rows(table, engine: PrivacyEngine, mode: AnonymizationMode) -> None:
    for row in table.rows:
        paragraph_offsets = []
        row_parts: list[str] = []
        cursor = 0

        for cell in row.cells:
            for paragraph in cell.paragraphs:
                text = "".join(run.text for run in paragraph.runs)
                if row_parts:
                    row_parts.append("\n")
                    cursor += 1
                start = cursor
                row_parts.append(text)
                cursor += len(text)
                paragraph_offsets.append((paragraph, start, cursor, text))

        row_text = "".join(row_parts)
        if not row_text:
            continue

        findings = engine.analyze(row_text, mode)
        if not findings:
            continue

        for paragraph, paragraph_start, paragraph_end, paragraph_text in paragraph_offsets:
            local_findings = [
                Finding(
                    finding.entity_type,
                    finding.start - paragraph_start,
                    finding.end - paragraph_start,
                    finding.score,
                )
                for finding in findings
                if paragraph_start <= finding.start and finding.end <= paragraph_end
            ]
            if local_findings:
                _replace_paragraph_findings(paragraph, paragraph_text, local_findings, engine, mode)


def _anonymize_paragraph_runs(paragraph, engine: PrivacyEngine, mode: AnonymizationMode) -> None:
    if not paragraph.runs:
        return

    text = "".join(run.text for run in paragraph.runs)
    if not text:
        return

    findings = engine.analyze(text, mode)
    if not findings:
        return

    _replace_paragraph_findings(paragraph, text, findings, engine, mode)


def _replace_paragraph_findings(
    paragraph,
    text: str,
    findings: list[Finding],
    engine: PrivacyEngine,
    mode: AnonymizationMode,
) -> None:
    replacements = [
        (
            finding.start,
            finding.end,
            engine.anonymize(
                text[finding.start : finding.end],
                [Finding(finding.entity_type, 0, finding.end - finding.start, finding.score)],
                mode,
            ),
        )
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


def _sanitize_docx_package(data: bytes, engine: PrivacyEngine, mode: AnonymizationMode) -> bytes:
    source_buffer = BytesIO(data)
    output = BytesIO()

    with zipfile.ZipFile(source_buffer, "r") as source, zipfile.ZipFile(output, "w") as target:
        for item in source.infolist():
            payload = source.read(item.filename)
            if not item.is_dir():
                payload = _sanitize_docx_part(item.filename, payload, engine, mode)
            target.writestr(item, payload)

    return output.getvalue()


def _sanitize_docx_part(name: str, data: bytes, engine: PrivacyEngine, mode: AnonymizationMode) -> bytes:
    if _is_docx_metadata_part(name):
        return _scrub_metadata_xml(data)
    if _is_docx_text_part(name):
        return _anonymize_ooxml_text(data, engine, mode, hidden_only=_is_docx_primary_story_part(name))
    return data


def _is_docx_metadata_part(name: str) -> bool:
    return name.startswith("docProps/") and name.endswith(".xml")


def _is_docx_text_part(name: str) -> bool:
    if name.startswith("word/") and name.endswith(".xml"):
        filename = Path(name).name
        return (
            filename == "document.xml"
            or filename.startswith("comments")
            or filename.startswith("header")
            or filename.startswith("footer")
            or filename in {"footnotes.xml", "endnotes.xml"}
            or name.startswith("word/glossary/")
        )
    return name.startswith("customXml/") and name.endswith(".xml")


def _is_docx_primary_story_part(name: str) -> bool:
    filename = Path(name).name
    return name.startswith("word/") and (
        filename == "document.xml" or filename.startswith("header") or filename.startswith("footer")
    )


def _scrub_metadata_xml(data: bytes) -> bytes:
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return data

    for element in root.iter():
        if element.text and element.text.strip():
            element.text = ""
        for attr_name in list(element.attrib):
            local_name = _local_name(attr_name)
            if local_name in PERSONAL_ATTRIBUTE_NAMES:
                element.attrib[attr_name] = ""
            elif local_name in {"name", "linkTarget"}:
                element.attrib[attr_name] = "Anonymized"

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _anonymize_ooxml_text(
    data: bytes,
    engine: PrivacyEngine,
    mode: AnonymizationMode,
    *,
    hidden_only: bool,
) -> bytes:
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return data

    _strip_personal_ooxml_attributes(root)
    for container in _iter_text_containers(root, hidden_only=hidden_only):
        _anonymize_text_nodes(list(_iter_text_nodes(container)), engine, mode)

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _strip_personal_ooxml_attributes(root: ET.Element) -> None:
    for element in root.iter():
        for attr_name in list(element.attrib):
            if _local_name(attr_name) in PERSONAL_ATTRIBUTE_NAMES:
                element.attrib[attr_name] = ""


def _iter_text_containers(root: ET.Element, *, hidden_only: bool):
    search_roots = list(_iter_hidden_text_roots(root)) if hidden_only else [root]
    seen: set[int] = set()

    for search_root in search_roots:
        for container in _iter_containers_below(search_root):
            identity = id(container)
            if identity not in seen:
                seen.add(identity)
                yield container


def _iter_hidden_text_roots(root: ET.Element):
    for element in root.iter():
        if _local_name(element.tag) in HIDDEN_TEXT_CONTAINER_NAMES:
            yield element


def _iter_containers_below(root: ET.Element):
    found_container = False
    if _local_name(root.tag) in {"p", "comment", "footnote", "endnote"}:
        found_container = True
        yield root
    for element in root.iter():
        if element is not root and _local_name(element.tag) in {"p", "comment", "footnote", "endnote"}:
            found_container = True
            yield element
    if not found_container and any(True for _ in _iter_text_nodes(root)):
        yield root


def _iter_text_nodes(container: ET.Element):
    for element in container.iter():
        if _local_name(element.tag) in TEXT_NODE_NAMES:
            yield element


def _anonymize_text_nodes(nodes: list[ET.Element], engine: PrivacyEngine, mode: AnonymizationMode) -> None:
    if not nodes:
        return

    text = "".join(node.text or "" for node in nodes)
    if not text:
        return

    findings = engine.analyze(text, mode)
    if not findings:
        return

    replacements = [
        (
            finding.start,
            finding.end,
            engine.anonymize(
                text[finding.start : finding.end],
                [Finding(finding.entity_type, 0, finding.end - finding.start, finding.score)],
                mode,
            ),
        )
        for finding in findings
    ]
    cursor = 0

    for node in nodes:
        node_text = node.text or ""
        node_start = cursor
        node_end = node_start + len(node_text)
        cursor = node_end
        pieces: list[str] = []
        text_cursor = node_start

        for start, end, replacement in replacements:
            if end <= node_start or start >= node_end:
                continue
            if start >= text_cursor:
                pieces.append(text[text_cursor:start])
            if node_start <= start < node_end:
                pieces.append(replacement)
            text_cursor = max(text_cursor, min(end, node_end))

        pieces.append(text[text_cursor:node_end])
        node.text = "".join(pieces)


def _local_name(name: str) -> str:
    if "}" in name:
        return name.rsplit("}", 1)[1]
    return name


def _read_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(path)
    pages: list[str] = []
    image_only_pages: list[int] = []

    for page_number, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append(text)
        elif _pdf_page_has_images(page):
            image_only_pages.append(page_number)

    if image_only_pages:
        pages_label = ", ".join(str(page_number) for page_number in image_only_pages)
        raise ValueError(
            "Il PDF contiene pagine immagine o scansionate senza testo selezionabile "
            f"(pagine: {pages_label}). Esegui prima l'OCR e poi riprova."
        )

    if not pages:
        raise ValueError("Il PDF non contiene testo estraibile. Se è una scansione, esegui prima l'OCR e poi riprova.")

    return "\n\n".join(pages)


def _pdf_page_has_images(page) -> bool:
    resources = _pdf_object(page.get("/Resources"))
    return _pdf_resources_have_images(resources)


def _pdf_resources_have_images(resources, depth: int = 0) -> bool:
    if not resources or depth > 4:
        return False

    xobjects = _pdf_object(resources.get("/XObject")) if hasattr(resources, "get") else None
    if not xobjects:
        return False

    for item in xobjects.values():
        xobject = _pdf_object(item)
        if not hasattr(xobject, "get"):
            continue
        subtype = str(xobject.get("/Subtype"))
        if subtype == "/Image":
            return True
        if subtype == "/Form" and _pdf_resources_have_images(_pdf_object(xobject.get("/Resources")), depth + 1):
            return True

    return False


def _pdf_object(value):
    if hasattr(value, "get_object"):
        return value.get_object()
    return value


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
