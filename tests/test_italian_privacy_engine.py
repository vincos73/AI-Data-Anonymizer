from __future__ import annotations

import base64
from io import BytesIO
import tempfile
import subprocess
import unittest
import zipfile
from pathlib import Path

from docx import Document
from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from privacy_guardian.document_service import anonymize_loaded_document, load_document
from privacy_guardian.privacy_engine import PrivacyEngine
from privacy_guardian.reporting import report_payload, report_text


class ItalianPrivacyEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = PrivacyEngine()

    def findings_for(self, text: str) -> list[tuple[str, str]]:
        return [(finding.entity_type, text[finding.start : finding.end]) for finding in self.engine.analyze(text)]

    def test_does_not_anonymize_common_italian_legal_words(self) -> None:
        self.assertEqual(self.findings_for("Premesso che il contratto viene firmato oggi."), [])
        self.assertEqual(self.findings_for("La società ha premesso quanto segue."), [])

    def test_detects_person_only_with_strong_context(self) -> None:
        findings = self.findings_for("Il sottoscritto Mario Rossi nato a Roma il 10/01/1980.")
        self.assertIn(("PERSON", "Mario Rossi"), findings)
        self.assertNotIn(("DATE_TIME", "10/01/1980"), findings)
        self.assertEqual(self.findings_for("Mario andrà domani a Milano."), [])

    def test_detects_person_when_strong_context_follows_name(self) -> None:
        findings = self.findings_for("Mario Rossi, nato a Roma il 10/01/1980.")
        self.assertIn(("PERSON", "Mario Rossi"), findings)

        findings = self.findings_for("Maria Bianchi residente in Via Appia 12.")
        self.assertIn(("PERSON", "Maria Bianchi"), findings)

        findings = self.findings_for("Bonifico intestato a Mario Rossi.")
        self.assertIn(("PERSON", "Mario Rossi"), findings)

        self.assertEqual(self.findings_for("Mario Rossi andrà domani a Milano."), [])

    def test_does_not_anonymize_dates(self) -> None:
        text = "Il sottoscritto Mario Rossi nato il 10/01/1980 e residente dal 5 maggio 2020."
        anonymized = self.engine.anonymize(text)
        self.assertIn("10/01/1980", anonymized)
        self.assertIn("5 maggio 2020", anonymized)

    def test_maximum_protection_redacts_dates_and_initials(self) -> None:
        text = (
            "Il sottoscritto Mario Rossi nato il 10/01/1980 lavora per "
            "Alfa Beta S.r.l. in Via Appia 12."
        )
        anonymized = self.engine.anonymize(text, mode="maximum")

        self.assertIn("<PERSON>", anonymized)
        self.assertIn("<DATE>", anonymized)
        self.assertIn("<ORGANIZATION>", anonymized)
        self.assertIn("<ADDRESS>", anonymized)
        self.assertNotIn("M. R.", anonymized)
        self.assertNotIn("10/01/1980", anonymized)

    def test_dates_are_findings_only_in_maximum_protection(self) -> None:
        text = "Il sottoscritto Mario Rossi nato il 5 maggio 2020."

        standard_findings = self.findings_for(text)
        maximum_findings = [
            (finding.entity_type, text[finding.start : finding.end])
            for finding in self.engine.analyze(text, mode="maximum")
        ]

        self.assertNotIn(("DATE", "5 maggio 2020"), standard_findings)
        self.assertIn(("DATE", "5 maggio 2020"), maximum_findings)

    def test_detects_italian_organizations(self) -> None:
        findings = self.findings_for("Alfa Beta S.r.l. invierà la fattura.")
        self.assertIn(("ORGANIZATION", "Alfa Beta S.r.l."), findings)

        findings = self.findings_for("società Rossi Consulting spa con sede in Via Garibaldi 12, Milano.")
        self.assertIn(("ORGANIZATION", "società Rossi Consulting spa"), findings)
        self.assertIn(("ADDRESS", "Via Garibaldi 12, Milano"), findings)

        findings = self.findings_for("ditta individuale Mario Rossi P.IVA 12345678903")
        self.assertIn(("ORGANIZATION", "ditta individuale Mario Rossi"), findings)
        self.assertIn(("PARTITA_IVA", "12345678903"), findings)

    def test_keeps_initials_for_people_organizations_and_places(self) -> None:
        text = "Il sottoscritto Mario Rossi lavora per Alfa Beta S.r.l. nella Provincia di Potenza."
        anonymized = self.engine.anonymize(text)
        self.assertIn("M. R.", anonymized)
        self.assertIn("A. B. S. r. l.", anonymized)
        self.assertIn("P. d. P.", anonymized)
        self.assertNotIn("<PERSON>", anonymized)
        self.assertNotIn("<ORGANIZATION>", anonymized)

    def test_detects_territorial_bodies(self) -> None:
        findings = self.findings_for("Provincia di Potenza, regione Basilicata e Comune di Roma.")
        self.assertIn(("TERRITORIAL_BODY", "Provincia di Potenza"), findings)
        self.assertIn(("TERRITORIAL_BODY", "regione Basilicata"), findings)
        self.assertIn(("TERRITORIAL_BODY", "Comune di Roma"), findings)

    def test_detects_addresses_without_house_number(self) -> None:
        findings = self.findings_for("Residente in Via Appia e domiciliato in Viale Europa 10.")
        self.assertIn(("ADDRESS", "Via Appia"), findings)
        self.assertIn(("ADDRESS", "Viale Europa 10"), findings)

    def test_detects_structured_italian_data(self) -> None:
        text = "IBAN IT60X0542811101000000123456 CF RSSMRA80A01H501U email mario.rossi@example.com tel +39 333 123 4567"
        anonymized = self.engine.anonymize(text)
        self.assertIn("<IBAN>", anonymized)
        self.assertIn("<CODICE_FISCALE>", anonymized)
        self.assertIn("<EMAIL_ADDRESS>", anonymized)
        self.assertIn("<PHONE_NUMBER>", anonymized)

    def test_detects_common_italian_number_formats(self) -> None:
        text = "IBAN IT60 X054 2811 1010 0000 0123 456 tel 06/12345678 cell +39 333/1234567"
        findings = self.findings_for(text)
        anonymized = self.engine.anonymize(text)

        self.assertIn(("IBAN", "IT60 X054 2811 1010 0000 0123 456"), findings)
        self.assertIn(("PHONE_NUMBER", "06/12345678"), findings)
        self.assertIn(("PHONE_NUMBER", "+39 333/1234567"), findings)
        self.assertIn("<IBAN>", anonymized)
        self.assertEqual(anonymized.count("<PHONE_NUMBER>"), 2)
        self.assertNotIn("IT60 X054", anonymized)
        self.assertNotIn("0123 456", anonymized)

    def test_report_summarizes_mode_counts_and_review_warning(self) -> None:
        text = "Il sottoscritto Mario Rossi email mario@example.com nato il 10/01/1980."
        findings = self.engine.analyze(text, mode="maximum")
        report = report_payload(findings, "maximum")

        self.assertEqual(report["mode_label"], "Massima protezione")
        self.assertEqual(report["counts"]["PERSON"], 1)
        self.assertEqual(report["counts"]["EMAIL_ADDRESS"], 1)
        self.assertEqual(report["counts"]["DATE"], 1)
        self.assertIn("Rileggi sempre", report["summary"])
        self.assertIn("1 persona", report["summary"])
        self.assertIn("1 data", report["summary"])
        self.assertIn("3 dati riconosciuti", report_text(findings, "maximum"))

    def test_standard_report_warns_about_initials_and_dates(self) -> None:
        report = report_text([], "standard")

        self.assertIn("Standard conserva iniziali e date", report)
        self.assertIn("0 dati riconosciuti", report)


class DocumentAnonymizationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = PrivacyEngine()
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_anonymizes_txt_docx_and_pdf_documents(self) -> None:
        txt_path = self.base / "test.txt"
        txt_path.write_text("Il sottoscritto Mario Rossi lavora per Alfa Beta S.r.l.", encoding="utf-8")

        docx_path = self.base / "test.docx"
        doc = Document()
        doc.add_paragraph("signora Maria Bianchi email maria@example.com")
        doc.save(docx_path)

        pdf_path = self.base / "test.pdf"
        pdf = canvas.Canvas(str(pdf_path))
        pdf.drawString(72, 720, "società Rossi Consulting spa tel +39 333 123 4567")
        pdf.save()

        for path in (txt_path, docx_path, pdf_path):
            loaded = load_document(path)
            result = anonymize_loaded_document(loaded, self.engine)
            self.assertGreaterEqual(len(result.findings), 1)
            self.assertTrue(result.data)

        pdf_result = anonymize_loaded_document(load_document(pdf_path), self.engine)
        out_pdf = self.base / pdf_result.filename
        out_pdf.write_bytes(pdf_result.data)
        self.assertEqual(len(PdfReader(out_pdf).pages), 1)

    def test_docx_anonymization_preserves_run_formatting(self) -> None:
        docx_path = self.base / "formatted.docx"
        doc = Document()
        paragraph = doc.add_paragraph("Il sottoscritto ")
        first_name = paragraph.add_run("Mario")
        first_name.bold = True
        last_name = paragraph.add_run(" Rossi")
        last_name.italic = True
        paragraph.add_run(" lavora in Via Appia.")
        doc.save(docx_path)

        result = anonymize_loaded_document(load_document(docx_path), self.engine)
        out_docx = self.base / result.filename
        out_docx.write_bytes(result.data)

        output_paragraph = Document(out_docx).paragraphs[0]
        self.assertIn("M. R.", output_paragraph.text)
        self.assertIn("V. A.", output_paragraph.text)
        self.assertTrue(any(run.text == "M. R." and run.bold for run in output_paragraph.runs))

    def test_docx_maximum_protection_uses_full_placeholders(self) -> None:
        docx_path = self.base / "maximum.docx"
        doc = Document()
        doc.add_paragraph("Il sottoscritto Mario Rossi nato il 10/01/1980.")
        doc.save(docx_path)

        result = anonymize_loaded_document(load_document(docx_path), self.engine, mode="maximum")
        out_docx = self.base / result.filename
        out_docx.write_bytes(result.data)

        output_text = Document(out_docx).paragraphs[0].text
        self.assertIn("<PERSON>", output_text)
        self.assertIn("<DATE>", output_text)
        self.assertNotIn("Mario Rossi", output_text)
        self.assertNotIn("10/01/1980", output_text)

    def test_docx_anonymization_sanitizes_hidden_ooxml_and_metadata(self) -> None:
        docx_path = self.base / "hidden.docx"
        doc = Document()
        doc.add_paragraph("Relazione senza dati personali visibili.")
        doc.core_properties.author = "Mario Rossi"
        doc.core_properties.title = "Contratto Mario Rossi"
        doc.core_properties.comments = "Email mario@example.com"
        doc.save(docx_path)
        _add_hidden_docx_content(docx_path)

        result = anonymize_loaded_document(load_document(docx_path), self.engine)
        out_docx = self.base / result.filename
        out_docx.write_bytes(result.data)

        xml_text = _docx_xml_text(out_docx)
        output_doc = Document(out_docx)
        self.assertNotIn("Mario Rossi", xml_text)
        self.assertNotIn("Maria Bianchi", xml_text)
        self.assertNotIn("mario@example.com", xml_text)
        self.assertNotIn("06/12345678", xml_text)
        self.assertIn("M. R.", xml_text)
        self.assertIn("M. B.", xml_text)
        self.assertIn("&lt;EMAIL_ADDRESS&gt;", xml_text)
        self.assertIn("&lt;PHONE_NUMBER&gt;", xml_text)
        self.assertNotIn("Mario Rossi", output_doc.core_properties.author or "")
        self.assertNotIn("Mario Rossi", output_doc.core_properties.title or "")
        self.assertNotIn("mario@example.com", output_doc.core_properties.comments or "")

    def test_rejects_image_only_pdf_before_anonymization(self) -> None:
        pdf_path = self.base / "scanned.pdf"
        image = ImageReader(BytesIO(base64.b64decode(_ONE_PIXEL_PNG_BASE64)))
        pdf = canvas.Canvas(str(pdf_path))
        pdf.drawImage(image, 72, 720, width=120, height=40)
        pdf.save()

        with self.assertRaisesRegex(ValueError, "pagine: 1"):
            load_document(pdf_path)

    def test_rejects_pdf_without_extractable_text(self) -> None:
        pdf_path = self.base / "blank.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        with pdf_path.open("wb") as output:
            writer.write(output)

        with self.assertRaisesRegex(ValueError, "non contiene testo estraibile"):
            load_document(pdf_path)

    @unittest.skipUnless(Path("/usr/bin/textutil").exists(), "textutil is required for .doc support")
    def test_accepts_legacy_doc_and_outputs_docx(self) -> None:
        source_txt = self.base / "legacy-source.txt"
        source_txt.write_text("Il sottoscritto Mario Rossi lavora per Alfa Beta S.r.l.", encoding="utf-8")
        doc_path = self.base / "legacy.doc"
        subprocess.run(
            ["/usr/bin/textutil", "-convert", "doc", "-output", str(doc_path), str(source_txt)],
            check=True,
            capture_output=True,
        )

        result = anonymize_loaded_document(load_document(doc_path), self.engine)

        self.assertEqual(result.filename, "legacy_anonimizzato.docx")
        self.assertIn("M. R.", result.text)
        self.assertTrue(result.data)


_ONE_PIXEL_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def _add_hidden_docx_content(path: Path) -> None:
    with zipfile.ZipFile(path, "r") as source:
        files = {name: source.read(name) for name in source.namelist()}

    content_types = files["[Content_Types].xml"].decode("utf-8")
    if "/word/comments.xml" not in content_types:
        content_types = content_types.replace(
            "</Types>",
            '<Override PartName="/word/comments.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/></Types>',
        )
    files["[Content_Types].xml"] = content_types.encode("utf-8")

    rels = files["word/_rels/document.xml.rels"].decode("utf-8")
    if "relationships/comments" not in rels:
        rels = rels.replace(
            "</Relationships>",
            '<Relationship Id="rIdHiddenComments" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" '
            'Target="comments.xml"/></Relationships>',
        )
    files["word/_rels/document.xml.rels"] = rels.encode("utf-8")

    document_xml = files["word/document.xml"].decode("utf-8")
    hidden_textbox = (
        '<w:p><w:r><w:pict><v:shape xmlns:v="urn:schemas-microsoft-com:vml">'
        "<v:textbox><w:txbxContent><w:p><w:r>"
        "<w:t>Textbox signora Maria Bianchi tel 06/12345678</w:t>"
        "</w:r></w:p></w:txbxContent></v:textbox></v:shape></w:pict></w:r></w:p>"
    )
    document_xml = document_xml.replace("</w:body>", f"{hidden_textbox}</w:body>")
    files["word/document.xml"] = document_xml.encode("utf-8")

    files["word/comments.xml"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:comment w:id="0" w:author="Mario Rossi" w:initials="MR">'
        "<w:p><w:r><w:t>Commento di Mario</w:t></w:r>"
        "<w:r><w:t> Rossi email mario@example.com</w:t></w:r></w:p>"
        "</w:comment></w:comments>"
    ).encode("utf-8")

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as target:
        for name, data in files.items():
            target.writestr(name, data)


def _docx_xml_text(path: Path) -> str:
    with zipfile.ZipFile(path, "r") as archive:
        return "\n".join(
            archive.read(name).decode("utf-8", errors="replace")
            for name in archive.namelist()
            if name.endswith(".xml")
        )


if __name__ == "__main__":
    unittest.main()
