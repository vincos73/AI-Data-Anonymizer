from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from privacy_guardian.models import AnonymizationMode, Finding
from privacy_guardian.privacy_engine import PrivacyEngine


BASE_SUPPORTED_EXTENSIONS = {".txt", ".md", ".csv", ".docx", ".pdf"}
LEGACY_DOC_SUPPORTED = sys.platform == "darwin" and Path("/usr/bin/textutil").exists()
SUPPORTED_EXTENSIONS = BASE_SUPPORTED_EXTENSIONS | ({".doc"} if LEGACY_DOC_SUPPORTED else set())
PDF_REDACTION_SCALE = 2.0
PDF_REDACTION_PADDING = 1.75
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


@dataclass(frozen=True)
class PdfRedactionRect:
    left: float
    bottom: float
    right: float
    top: float


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
        data = _anonymize_pdf(document.path, engine, mode)

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
    return _sanitize_docx_package(path.read_bytes(), engine, mode)


def _read_legacy_doc(path: Path) -> str:
    result = _run_textutil("-convert", "txt", "-stdout", str(path))
    return result.stdout.decode("utf-8", errors="replace").strip()


def _anonymize_legacy_doc(path: Path, engine: PrivacyEngine, mode: AnonymizationMode) -> bytes:
    with tempfile.TemporaryDirectory() as tmpdir:
        converted_path = Path(tmpdir) / f"{path.stem}.docx"
        _run_textutil("-convert", "docx", "-output", str(converted_path), str(path))
        return _anonymize_docx(converted_path, engine, mode)


def _anonymize_pdf(path: Path, engine: PrivacyEngine, mode: AnonymizationMode) -> bytes:
    import pypdfium2 as pdfium
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    source_pdf = pdfium.PdfDocument(str(path))
    output = BytesIO()
    redacted_pdf = canvas.Canvas(output)

    try:
        for page_index in range(len(source_pdf)):
            page = source_pdf[page_index]
            width, height = page.get_size()
            text_page = page.get_textpage()
            page_text = text_page.get_text_range()
            findings = engine.analyze(page_text, mode)
            redaction_rects = _pdf_redaction_rects(text_page, page_text, findings, page_index)
            bitmap = page.render(scale=PDF_REDACTION_SCALE)
            try:
                image = bitmap.to_pil().convert("RGB")
            finally:
                close = getattr(bitmap, "close", None)
                if close:
                    close()
            _draw_pdf_redactions(image, (width, height), redaction_rects)
            redacted_pdf.setPageSize((width, height))
            redacted_pdf.drawImage(ImageReader(image), 0, 0, width=width, height=height)
            redacted_pdf.showPage()
    finally:
        close = getattr(source_pdf, "close", None)
        if close:
            close()

    redacted_pdf.save()
    return output.getvalue()


def _pdf_redaction_rects(
    text_page,
    page_text: str,
    findings: list[Finding],
    page_index: int,
) -> list[PdfRedactionRect]:
    rects: list[PdfRedactionRect] = []
    unmapped_findings: list[str] = []

    for finding in findings:
        finding_rects = _pdf_finding_rects(text_page, page_text, finding)
        if not finding_rects:
            unmapped_findings.append(finding.entity_type)
            continue
        rects.extend(finding_rects)

    if unmapped_findings:
        entities = ", ".join(sorted(set(unmapped_findings)))
        raise ValueError(
            "Non riesco a redigere il PDF in modo sicuro: alcuni dati rilevati non hanno coordinate affidabili "
            f"nella pagina {page_index + 1} ({entities})."
        )

    return rects


def _pdf_finding_rects(text_page, page_text: str, finding: Finding) -> list[PdfRedactionRect]:
    char_boxes = []
    for index in range(finding.start, finding.end):
        if index >= len(page_text) or page_text[index].isspace():
            continue
        try:
            box = text_page.get_charbox(index, loose=True)
        except Exception:
            continue
        if _is_valid_pdf_box(box):
            char_boxes.append(PdfRedactionRect(*box))

    return _merge_pdf_char_boxes(char_boxes)


def _is_valid_pdf_box(box) -> bool:
    if not box or len(box) != 4:
        return False
    left, bottom, right, top = box
    return right > left and top > bottom


def _merge_pdf_char_boxes(boxes: list[PdfRedactionRect]) -> list[PdfRedactionRect]:
    lines: list[list[PdfRedactionRect]] = []

    for box in sorted(boxes, key=lambda item: (-(item.bottom + item.top) / 2, item.left)):
        box_center = (box.bottom + box.top) / 2
        box_height = box.top - box.bottom
        for line in lines:
            line_bottom = min(item.bottom for item in line)
            line_top = max(item.top for item in line)
            line_center = (line_bottom + line_top) / 2
            line_height = line_top - line_bottom
            if abs(box_center - line_center) <= max(box_height, line_height, 1.0) * 0.7:
                line.append(box)
                break
        else:
            lines.append([box])

    return [
        PdfRedactionRect(
            min(box.left for box in line),
            min(box.bottom for box in line),
            max(box.right for box in line),
            max(box.top for box in line),
        )
        for line in lines
    ]


def _draw_pdf_redactions(image, page_size: tuple[float, float], rects: list[PdfRedactionRect]) -> None:
    from PIL import ImageDraw

    _, page_height = page_size
    draw = ImageDraw.Draw(image)
    image_width, image_height = image.size

    for rect in rects:
        left = max(0, int((rect.left - PDF_REDACTION_PADDING) * PDF_REDACTION_SCALE))
        top = max(0, int((page_height - rect.top - PDF_REDACTION_PADDING) * PDF_REDACTION_SCALE))
        right = min(image_width, int((rect.right + PDF_REDACTION_PADDING) * PDF_REDACTION_SCALE) + 1)
        bottom = min(image_height, int((page_height - rect.bottom + PDF_REDACTION_PADDING) * PDF_REDACTION_SCALE) + 1)
        if right > left and bottom > top:
            draw.rectangle((left, top, right, bottom), fill=(0, 0, 0))


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
        return _anonymize_ooxml_text(data, engine, mode, use_table_context=_is_docx_primary_story_part(name))
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
    use_table_context: bool,
) -> bytes:
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return data

    _strip_personal_ooxml_attributes(root)
    processed_nodes: set[int] = set()

    if use_table_context:
        for table_row in _iter_elements_by_local_name(root, "tr"):
            nodes = list(_iter_text_nodes(table_row))
            _anonymize_text_nodes(nodes, engine, mode)
            processed_nodes.update(id(node) for node in nodes)

    for container in _iter_text_containers(root):
        nodes = [node for node in _iter_text_nodes(container) if id(node) not in processed_nodes]
        _anonymize_text_nodes(nodes, engine, mode)
        processed_nodes.update(id(node) for node in nodes)

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _strip_personal_ooxml_attributes(root: ET.Element) -> None:
    for element in root.iter():
        for attr_name in list(element.attrib):
            if _local_name(attr_name) in PERSONAL_ATTRIBUTE_NAMES:
                element.attrib[attr_name] = ""


def _iter_text_containers(root: ET.Element):
    seen: set[int] = set()
    for container in _iter_containers_below(root):
        identity = id(container)
        if identity not in seen:
            seen.add(identity)
            yield container


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


def _iter_elements_by_local_name(root: ET.Element, local_name: str):
    for element in root.iter():
        if _local_name(element.tag) == local_name:
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
    replacements.sort(key=lambda replacement: replacement[0])
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
