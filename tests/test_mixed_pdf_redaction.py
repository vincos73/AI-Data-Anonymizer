from __future__ import annotations

from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from privacy_guardian import document_service
from privacy_guardian.document_service import OcrPageText, OcrWord, anonymize_loaded_document, load_document
from privacy_guardian.privacy_engine import PrivacyEngine


class MixedPdfRedactionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = PrivacyEngine()
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_mixed_page_runs_native_and_ocr_redactions(self) -> None:
        pdf_path = self._mixed_pdf("mixed.pdf")
        ocr_text = self._ocr_text()

        with patch.object(document_service, "_tesseract_available", return_value=True):
            with patch.object(document_service, "_ocr_pdfium_page", return_value=ocr_text):
                loaded = load_document(pdf_path)
            with patch.object(document_service, "_ocr_image", return_value=ocr_text) as ocr_image:
                with patch.object(
                    document_service,
                    "_draw_pdf_redactions",
                    wraps=document_service._draw_pdf_redactions,
                ) as native_redactions:
                    result = anonymize_loaded_document(loaded, self.engine, mode="maximum")

        self.assertEqual(loaded.ocr_pages, (1,))
        self.assertIn("Mario Rossi", loaded.text)
        self.assertIn("mario@example.com", loaded.text)
        self.assertEqual(loaded.text.count("Mario Rossi"), 1)
        self.assertEqual(native_redactions.call_count, 1)
        ocr_image.assert_called_once()
        self.assertTrue(self._rendered_pixel(result.data, 300, 315) < 10)

    def test_mixed_page_is_rejected_without_ocr(self) -> None:
        pdf_path = self._mixed_pdf("mixed-no-ocr.pdf")

        with patch.object(document_service, "_tesseract_available", return_value=False):
            with self.assertRaisesRegex(ValueError, "testo selezionabile"):
                load_document(pdf_path)

    def test_text_only_pdf_does_not_require_ocr(self) -> None:
        pdf_path = self.base / "text-only.pdf"
        pdf = canvas.Canvas(str(pdf_path), pagesize=(200, 200))
        pdf.drawString(36, 160, "Il sottoscritto Mario Rossi")
        pdf.save()

        with patch.object(document_service, "_tesseract_available", return_value=False):
            loaded = load_document(pdf_path)
            result = anonymize_loaded_document(loaded, self.engine, mode="maximum")

        self.assertEqual(loaded.ocr_pages, ())
        self.assertTrue(result.data.startswith(b"%PDF"))

    def _mixed_pdf(self, filename: str) -> Path:
        image = Image.new("RGB", (20, 20), "white")
        image_data = BytesIO()
        image.save(image_data, format="PNG")
        image_data.seek(0)

        pdf_path = self.base / filename
        pdf = canvas.Canvas(str(pdf_path), pagesize=(200, 200))
        pdf.drawString(36, 160, "Il sottoscritto Mario Rossi")
        pdf.drawImage(ImageReader(image_data), 20, 20, width=80, height=80)
        pdf.save()
        return pdf_path

    @staticmethod
    def _ocr_text() -> OcrPageText:
        return OcrPageText(
            text="Il sottoscritto Mario Rossi mario@example.com",
            words=[OcrWord("mario@example.com", 28, 45, 250, 300, 340, 330)],
        )

    @staticmethod
    def _rendered_pixel(pdf_data: bytes, x: int, y: int) -> int:
        import pypdfium2 as pdfium

        document = pdfium.PdfDocument(pdf_data)
        bitmap = document[0].render(scale=2)
        try:
            pixel = bitmap.to_pil().convert("RGB").getpixel((x, y))
        finally:
            close = getattr(bitmap, "close", None)
            if close:
                close()
            close = getattr(document, "close", None)
            if close:
                close()
        return max(pixel)
