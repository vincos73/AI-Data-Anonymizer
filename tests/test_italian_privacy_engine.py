from __future__ import annotations

import tempfile
import subprocess
import unittest
from pathlib import Path

from docx import Document
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from privacy_guardian.document_service import anonymize_loaded_document, load_document
from privacy_guardian.privacy_engine import PrivacyEngine


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

    def test_does_not_anonymize_dates(self) -> None:
        text = "Il sottoscritto Mario Rossi nato il 10/01/1980 e residente dal 5 maggio 2020."
        anonymized = self.engine.anonymize(text)
        self.assertIn("10/01/1980", anonymized)
        self.assertIn("5 maggio 2020", anonymized)

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


if __name__ == "__main__":
    unittest.main()
