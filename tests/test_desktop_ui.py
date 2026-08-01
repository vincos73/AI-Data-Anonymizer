"""Headless smoke tests for the desktop (PySide6) MainWindow.

These tests exercise the Dark Pro rail/toolbar redesign without needing a real
display: they force QT_QPA_PLATFORM=offscreen before importing PySide6, and
skip cleanly if PySide6 or a usable Qt platform plugin isn't available.
"""

from __future__ import annotations

import atexit
import os
import tempfile
import time
import unittest
from pathlib import Path
from threading import Event
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OMISSIS_SYNC_JOBS", "1")
_ACTIVITY_TEST_DIR = tempfile.TemporaryDirectory(prefix="omissis-desktop-tests-")
atexit.register(_ACTIVITY_TEST_DIR.cleanup)
os.environ["OMISSIS_ACTIVITY_LOG_PATH"] = str(Path(_ACTIVITY_TEST_DIR.name) / "activity-log.jsonl")
os.environ["OMISSIS_ACTIVITY_SETTINGS_PATH"] = str(
    Path(_ACTIVITY_TEST_DIR.name) / "activity-settings.json"
)

try:
    from PySide6.QtCore import QThread, Qt
    from PySide6.QtGui import QCloseEvent, QKeySequence, QPalette
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QDialog, QLabel, QMessageBox

    from privacy_guardian.app import MainWindow
    from privacy_guardian.desktop_workflows import AnalysisOutcome
    from privacy_guardian.document_service import AnonymizedDocument, LoadedDocument, OcrUnavailableError
    from privacy_guardian.findings_panel import ROLE_IS_GROUP
    from privacy_guardian.models import Finding

    _QT_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - exercised only when PySide6/Qt is unavailable
    QApplication = None  # type: ignore[assignment]
    MainWindow = None  # type: ignore[assignment]
    _QT_IMPORT_ERROR = exc


def _make_app() -> "QApplication":
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@unittest.skipIf(_QT_IMPORT_ERROR is not None, f"PySide6/Qt not usable in this environment: {_QT_IMPORT_ERROR}")
class DesktopMainWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        _make_app()
        self.window = MainWindow()

    def tearDown(self) -> None:
        self.window.clear_all(force=True)
        self.window.close()
        self.window.deleteLater()

    def test_default_selected_mode_is_standard(self) -> None:
        self.assertEqual(self.window._selected_mode(), "standard")

    def test_selecting_standard_radio_updates_selected_mode(self) -> None:
        self.window.mode_radios["standard"].setChecked(True)
        self.assertEqual(self.window._selected_mode(), "standard")

    def test_selecting_reversible_radio_updates_selected_mode(self) -> None:
        self.window.mode_radios["reversible"].setChecked(True)
        self.assertEqual(self.window._selected_mode(), "reversible")

    def test_primary_button_prompts_to_analyze_when_input_pending(self) -> None:
        self.window.input_text.setPlainText("Mario Rossi, telefono 333 1234567.")
        self.assertEqual(self.window.primary_button.text(), "Analizza dati")
        self.assertTrue(self.window.primary_button.isEnabled())

    def test_guided_primary_starts_with_load_and_keeps_paste_available(self) -> None:
        self.assertEqual(self.window.primary_button.text(), "Carica documento")
        self.assertTrue(self.window.primary_button.isEnabled())
        self.assertTrue(self.window.load_button.isHidden())
        self.assertTrue(self.window.save_button.isHidden())
        self.assertTrue(self.window.clear_button.isHidden())
        self.assertTrue(self.window.add_selection_button.isHidden())
        self.assertEqual(
            [row.objectName() for row in self.window.step_rows],
            ["StepRowCurrent"] + ["StepRowPending"] * 4,
        )

        with mock.patch.object(self.window, "open_file") as open_file:
            self.window._primary_action()

        open_file.assert_called_once_with()
        self.window.input_text.setPlainText("Testo incollato nell'Originale.")
        self.assertEqual(self.window.input_text.toPlainText(), "Testo incollato nell'Originale.")
        self.assertEqual(self.window.primary_button.text(), "Analizza dati")
        self.assertTrue(self.window.load_button.isHidden())
        self.assertFalse(self.window.clear_button.isHidden())
        self.assertTrue(self.window.save_button.isHidden())
        self.assertTrue(self.window.add_selection_button.isHidden())

    def test_loaded_document_populates_original_before_analysis(self) -> None:
        document = LoadedDocument(
            path=Path("documento-prova.docx"),
            text="Mario Rossi scrive a mario@example.com.",
            extension=".docx",
        )

        self.window._apply_loaded_document(document)

        self.assertEqual(self.window.input_text.toPlainText(), document.text)
        self.assertEqual(self.window.document_label.text(), "Documento caricato: documento-prova.docx")
        self.assertEqual(self.window.primary_button.text(), "Analizza dati")
        self.assertTrue(self.window.report_label.isHidden())
        self.assertEqual(
            [row.objectName() for row in self.window.step_rows],
            ["StepRowDone", "StepRowCurrent", "StepRowPending", "StepRowPending", "StepRowPending"],
        )

    def test_guided_review_preserves_original_and_highlights_before_protection(self) -> None:
        text = "Mario Rossi scrive a mario@example.com."
        self.window.input_text.setPlainText(text)
        person = Finding("PERSON", 0, len("Mario Rossi"), 0.95)

        with mock.patch.object(self.window.engine, "analyze", return_value=[person]):
            self.window._primary_action()

        self.assertEqual(self.window.input_text.toPlainText(), text)
        self.assertEqual(len(self.window.input_text.extraSelections()), 1)
        self.assertTrue(self.window._analysis_preview_active)
        self.assertTrue(self.window.output_text.toPlainText())
        self.assertNotIn("Mario Rossi", self.window.output_text.toPlainText())
        self.assertEqual(self.window.output_panel_title.text(), "Anteprima anonimizzata")
        self.assertFalse(self.window.output_preview_notice.isHidden())
        self.assertTrue(self.window.output_text.isReadOnly())
        self.assertEqual(self.window.primary_button.text(), "Ho controllato, continua")
        self.assertFalse(self.window.add_selection_button.isHidden())
        self.assertFalse(self.window.add_selection_button.isEnabled())
        self.assertEqual(
            [row.objectName() for row in self.window.step_rows],
            ["StepRowDone", "StepRowDone", "StepRowCurrent", "StepRowPending", "StepRowPending"],
        )

        self.window._primary_action()

        self.assertEqual(self.window.input_text.toPlainText(), text)
        self.assertEqual(len(self.window.input_text.extraSelections()), 1)
        self.assertTrue(self.window._analysis_preview_active)
        self.assertTrue(self.window.output_text.toPlainText())
        self.assertEqual(self.window.primary_button.text(), "Crea copia protetta")
        self.assertFalse(self.window.add_selection_button.isHidden())
        self.assertTrue(self.window.add_selection_button.isEnabled())
        self.assertEqual(self.window.add_selection_button.text(), "Torna alla revisione")
        self.assertEqual(
            [row.objectName() for row in self.window.step_rows],
            ["StepRowDone", "StepRowDone", "StepRowDone", "StepRowCurrent", "StepRowPending"],
        )

        self.window._primary_action()

        self.assertEqual(self.window.input_text.toPlainText(), text)
        self.assertTrue(self.window.output_text.toPlainText())
        self.assertFalse(self.window._analysis_preview_active)
        self.assertEqual(self.window.output_panel_title.text(), "Testo anonimizzato")
        self.assertTrue(self.window.output_preview_notice.isHidden())
        self.assertFalse(self.window.output_text.isReadOnly())
        self.assertEqual(self.window.primary_button.text(), "Copia per ChatGPT")
        self.assertFalse(self.window.save_button.isHidden())
        self.assertEqual(self.window.save_button.text(), "Salva anche come file")
        self.assertEqual(
            [row.objectName() for row in self.window.step_rows],
            ["StepRowDone"] * 4 + ["StepRowCurrent"],
        )
        self.window.clear_all(force=True)

    def test_review_can_be_reopened_before_creating_the_protected_copy(self) -> None:
        text = "Mario Rossi"
        self.window.input_text.setPlainText(text)
        with mock.patch.object(
            self.window.engine,
            "analyze",
            return_value=[Finding("PERSON", 0, len(text), 0.95)],
        ):
            self.window.analyze_text()

        self.window._primary_action()
        self.assertEqual(self.window.primary_button.text(), "Crea copia protetta")
        self.window._review_secondary_action()

        self.assertEqual(self.window.primary_button.text(), "Ho controllato, continua")
        self.assertEqual(self.window.add_selection_button.text(), "Aggiungi dato mancante")
        self.assertFalse(self.window.add_selection_button.isEnabled())
        self.assertIn("Revisione riaperta", self.window.statusBar().currentMessage())

    def test_primary_attention_is_brief(self) -> None:
        self.window.input_text.setPlainText("Mario Rossi")
        QApplication.processEvents()
        self.assertTrue(self.window.primary_button.property("attention"))

        QTest.qWait(800)

        self.assertFalse(self.window.primary_button.property("attention"))

    def test_toolbar_adapts_and_main_actions_have_shortcuts(self) -> None:
        self.window.show()
        self.window.resize(960, 640)
        self.window.input_text.setPlainText("Testo di prova")
        QApplication.processEvents()
        self.assertTrue(self.window.document_toolbar._compact)
        self.assertFalse(self.window.clear_button.isHidden())
        clear_right = self.window.clear_button.mapToGlobal(
            self.window.clear_button.rect().bottomRight()
        ).x()
        primary_right = self.window.primary_button.mapToGlobal(
            self.window.primary_button.rect().bottomRight()
        ).x()
        self.assertLessEqual(abs(clear_right - primary_right), 2)
        self.window.resize(1400, 760)
        QApplication.processEvents()
        self.assertFalse(self.window.document_toolbar._compact)
        self.assertEqual(self.window.open_action.shortcut(), QKeySequence.Open)
        self.assertEqual(self.window.save_output_action.shortcut(), QKeySequence.Save)
        self.assertEqual(self.window.focus_search_action.shortcut(), QKeySequence.Find)
        self.assertEqual(self.window.review_help_action.shortcut(), QKeySequence.HelpContents)

    def test_accessible_names_explain_the_main_controls(self) -> None:
        self.assertEqual(self.window.input_text.accessibleName(), "Testo originale")
        self.assertEqual(self.window.output_text.accessibleName(), "Testo anonimizzato")
        self.assertEqual(
            self.window.findings_panel.selection_help_label.accessibleName(),
            "Istruzioni per la revisione",
        )

    def test_text_editors_keep_light_text_on_dark_background_across_native_styles(self) -> None:
        for editor in (self.window.input_text, self.window.output_text):
            with self.subTest(editor=editor.accessibleName()):
                self.assertFalse(editor.acceptRichText())
                self.assertEqual(editor.palette().color(QPalette.Base).name(), "#12181f")
                self.assertEqual(editor.palette().color(QPalette.Text).name(), "#e8edf2")
                self.assertEqual(editor.viewport().palette().color(QPalette.Base).name(), "#12181f")
                self.assertEqual(editor.viewport().palette().color(QPalette.Text).name(), "#e8edf2")

                editor.setPlainText("Testo leggibile")
                cursor = editor.textCursor()
                cursor.select(cursor.SelectionType.Document)
                self.assertEqual(cursor.charFormat().foreground().color().name(), "#e8edf2")

    def test_tab_moves_focus_without_inserting_a_character_in_the_source(self) -> None:
        self.window.show()
        self.window.input_text.setPlainText("Mario Rossi")
        self.window.input_text.setFocus(Qt.OtherFocusReason)
        QApplication.processEvents()

        QTest.keyClick(self.window.input_text, Qt.Key_Tab)
        QApplication.processEvents()

        self.assertEqual(self.window.input_text.toPlainText(), "Mario Rossi")
        self.assertNotIn(
            QApplication.focusWidget(),
            (self.window.input_text, self.window.input_text.viewport()),
        )
        self.window.clear_all(force=True)

    def test_control_return_runs_the_primary_action_without_editing_the_source(self) -> None:
        self.window.show()
        self.window.input_text.setPlainText("Mario Rossi")
        self.window.input_text.setFocus(Qt.OtherFocusReason)
        QApplication.processEvents()

        with mock.patch.object(self.window, "_primary_action") as primary_action:
            QTest.keyClick(self.window.input_text, Qt.Key_Return, Qt.ControlModifier)
            QApplication.processEvents()

        primary_action.assert_called_once_with()
        self.assertEqual(self.window.input_text.toPlainText(), "Mario Rossi")
        self.window.clear_all(force=True)

    def test_dynamic_primary_and_report_states_are_accessible(self) -> None:
        self.window.input_text.setPlainText("Mario Rossi")
        self.assertEqual(self.window.primary_button.accessibleName(), "Analizza dati")
        self.assertIn("Analizza il testo", self.window.primary_button.accessibleDescription())

        self.window.findings = [Finding("PERSON", 0, 11, 0.95, "Mario Rossi")]
        self.window.findings_stale = False
        self.window._findings_source_text = self.window.input_text.toPlainText()
        self.window._findings_mode = self.window._selected_mode()
        self.window._fill_table()
        self.window._sync_action_state()

        self.assertEqual(
            self.window.primary_button.accessibleName(),
            "Ho controllato, continua",
        )
        self.assertIn("evidenziazioni", self.window.primary_button.accessibleDescription())

        self.window._primary_action()
        self.assertEqual(self.window.primary_button.accessibleName(), "Crea copia protetta")

        self.window.anonymize_text()
        self.assertEqual(
            self.window.result_frame.accessibleName(),
            "Riepilogo della copia protetta",
        )
        self.assertTrue(self.window.result_frame.accessibleDescription())
        self.assertEqual(
            self.window.report_label.accessibleName(),
            "Controlli prima di condividere",
        )
        self.assertEqual(
            self.window.report_label.accessibleDescription(),
            self.window.report_label.text(),
        )
        self.assertEqual(self.window.primary_button.accessibleName(), "Copia per ChatGPT")
        self.window.clear_all(force=True)

    def test_message_box_text_has_contrast_on_native_light_surface(self) -> None:
        dialog = QMessageBox(self.window)
        dialog.setText("Questa azione eliminerebbe del lavoro non salvato.")
        dialog.setInformativeText("Verrà eliminato il risultato anonimizzato.")
        dialog.show()
        QApplication.processEvents()

        main_label = dialog.findChild(QLabel, "qt_msgbox_label")
        informative_label = dialog.findChild(QLabel, "qt_msgbox_informativelabel")
        self.assertIsNotNone(main_label)
        self.assertIsNotNone(informative_label)
        self.assertEqual(main_label.palette().color(QPalette.WindowText).name(), "#12181f")
        self.assertEqual(informative_label.palette().color(QPalette.WindowText).name(), "#2f3d4b")
        self.assertEqual(dialog.palette().color(QPalette.Window).name(), "#f4f6f8")
        dialog.close()

    def test_zero_findings_is_a_completed_analysis(self) -> None:
        self.window.input_text.setPlainText("Testo privo di dati riconoscibili.")
        with mock.patch.object(self.window.engine, "analyze", return_value=[]):
            self.window.analyze_text()

        self.assertFalse(self.window.findings_stale)
        self.assertEqual(self.window.primary_button.text(), "Ho controllato, continua")

    def test_analysis_prioritizes_the_review_workspace(self) -> None:
        text = "Mario Rossi"
        self.window.show()
        self.window.input_text.setPlainText(text)
        with mock.patch.object(
            self.window.engine,
            "analyze",
            return_value=[Finding("PERSON", 0, len(text), 0.95)],
        ):
            self.window.analyze_text()
        QApplication.processEvents()

        self.assertFalse(self.window.output_panel.isHidden())
        self.assertGreater(self.window.text_splitter.sizes()[1], 0)
        review_sizes = self.window.workspace_splitter.sizes()
        self.assertGreater(review_sizes[1], review_sizes[0])
        self.assertIsNone(self.window.findings_panel.selected_finding())
        self.assertFalse(self.window.findings_panel.tree.currentIndex().isValid())
        self.assertEqual(
            self.window.primary_button.text(),
            "Ho controllato, continua",
        )
        self.window.clear_all(force=True)


@unittest.skipIf(_QT_IMPORT_ERROR is not None, f"PySide6/Qt not usable in this environment: {_QT_IMPORT_ERROR}")
class OutputSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        _make_app()
        self.window = MainWindow()

    def tearDown(self) -> None:
        self.window.clear_all(force=True)
        self.window.close()
        self.window.deleteLater()

    def _prepare_output(self, *, exclude_email: bool = False) -> None:
        text = "Mario Rossi scrive a mario.rossi@example.com."
        person_end = len("Mario Rossi")
        email_start = text.index("mario.rossi@example.com")
        findings = [
            Finding("PERSON", 0, person_end, 0.95),
            Finding("EMAIL_ADDRESS", email_start, email_start + len("mario.rossi@example.com"), 0.98),
        ]
        self.window.input_text.setPlainText(text)
        self.window.findings = findings
        self.window.findings_stale = False
        self.window._findings_source_text = text
        self.window._findings_mode = self.window._selected_mode()
        self.window._fill_table()
        if exclude_email:
            self.window.findings_panel._index_to_item[1].setCheckState(Qt.Unchecked)
        self.window.anonymize_text()

    def test_generated_output_shows_visible_final_report(self) -> None:
        self._prepare_output(exclude_email=True)

        self.assertIsNotNone(self.window._output_provenance)
        self.assertFalse(self.window.result_frame.isHidden())
        self.assertFalse(self.window.output_panel.isHidden())
        self.assertGreater(self.window.text_splitter.sizes()[1], 0)
        self.assertEqual(self.window.result_title_label.text(), "Copia protetta pronta")
        self.assertIn("testo di partenza", self.window.result_subtitle_label.text())
        self.assertEqual(self.window.result_metric_label.text(), "1 dato protetto")
        self.assertIn("Modalità Standard", self.window.result_meta_label.text())
        self.assertIn("Formato TXT", self.window.result_meta_label.text())
        self.assertIn("1 persona", self.window.result_categories_label.text())
        self.assertIn("1 rilevamento resterà leggibile", self.window.report_label.text())
        self.assertEqual(self.window.result_state_label.text(), "PRONTA DA COPIARE")
        self.assertTrue(self.window.copy_button.isEnabled())
        self.assertTrue(self.window.copy_button.isHidden())
        self.assertEqual(self.window.primary_button.text(), "Copia per ChatGPT")
        self.assertTrue(self.window.save_button.isEnabled())
        self.assertFalse(self.window.save_button.isHidden())
        self.assertTrue(self.window.findings_panel.isHidden())
        self.assertFalse(self.window.add_selection_button.isHidden())
        self.assertEqual(self.window.add_selection_button.text(), "Modifica selezioni")

        self.window.copy_output()

        self.assertEqual(self.window.result_state_label.text(), "COPIATA")
        self.assertIn("ChatGPT", self.window.statusBar().currentMessage())

    def test_document_result_uses_save_as_the_single_primary_action(self) -> None:
        self._prepare_output()
        self.window.anonymized_document = AnonymizedDocument(
            filename="documento_anonimizzato.docx",
            data=b"PK",
            text=self.window.output_text.toPlainText(),
            findings=[],
        )
        self.window.output_text_dirty = False
        self.window._sync_action_state()

        self.assertEqual(self.window.primary_button.text(), "Salva copia protetta")
        self.assertTrue(self.window.primary_button.isEnabled())
        self.assertTrue(self.window.save_button.isHidden())

        with mock.patch.object(self.window, "save_output") as save_output:
            self.window._primary_action()

        save_output.assert_called_once_with()

        self.window._result_used = True
        self.window._sync_action_state()
        self.assertEqual(self.window.primary_button.text(), "Salva di nuovo")
        self.assertEqual(
            [row.objectName() for row in self.window.step_rows],
            ["StepRowDone"] * 5,
        )

    def test_final_result_can_reopen_the_review_without_reusing_stale_output(self) -> None:
        self._prepare_output()

        self.assertTrue(self.window.findings_panel.isHidden())

        self.window._review_secondary_action()

        self.assertFalse(self.window.findings_panel.isHidden())
        self.assertTrue(self.window._managed_output_is_stale())
        self.assertEqual(self.window.result_title_label.text(), "Risultato da rigenerare")
        self.assertEqual(self.window.primary_button.text(), "Ho controllato, continua")
        self.assertIn("revisione riaperta", self.window.result_subtitle_label.text())

    def test_pdf_result_explains_original_format_ocr_and_save_state(self) -> None:
        text = "Mario Rossi"
        finding = Finding("PERSON", 0, len(text), 0.95)
        self.window.loaded_document = LoadedDocument(
            path=Path("scansione.pdf"),
            text=text,
            extension=".pdf",
            ocr_pages=(1,),
        )
        self.window.input_text.setPlainText(text)
        self.window.document_text_dirty = False
        self.window.findings = [finding]
        self.window.findings_stale = False
        self.window._findings_source_text = text
        self.window._findings_mode = self.window._selected_mode()
        self.window._fill_table()

        document = AnonymizedDocument(
            filename="scansione_anonimizzato.pdf",
            data=b"%PDF-1.4",
            text="M. R.",
            findings=[finding],
        )
        with mock.patch(
            "privacy_guardian.desktop_workflows.anonymize_loaded_document",
            return_value=document,
        ):
            self.window.anonymize_text()

        self.assertEqual(self.window.result_title_label.text(), "Copia protetta pronta")
        self.assertIn("documento originale", self.window.result_subtitle_label.text())
        self.assertEqual(self.window.result_metric_label.text(), "1 dato protetto")
        self.assertIn("PDF rasterizzato", self.window.result_meta_label.text())
        self.assertIn("OCR locale", self.window.report_label.text())
        self.assertEqual(self.window.report_label.objectName(), "ResultAttentionWarning")
        self.assertEqual(self.window.result_state_label.text(), "DA SALVARE")
        self.assertEqual(self.window.primary_button.text(), "Salva copia protetta")

        with mock.patch(
            "privacy_guardian.app.QFileDialog.getSaveFileName",
            return_value=("/tmp/scansione_anonimizzato.pdf", ""),
        ), mock.patch("privacy_guardian.app.atomic_write_bytes"):
            self.window.save_output()

        self.assertEqual(self.window.result_state_label.text(), "SALVATA")

    def test_zero_findings_final_state_requires_extra_attention(self) -> None:
        text = "Testo senza dati riconosciuti."
        self.window.input_text.setPlainText(text)
        self.window.findings = []
        self.window.findings_stale = False
        self.window._findings_source_text = text
        self.window._findings_mode = self.window._selected_mode()
        self.window._fill_table()

        self.window.anonymize_text()

        self.assertEqual(self.window.result_metric_label.text(), "0 dati protetti")
        self.assertTrue(self.window.result_categories_label.isHidden())
        self.assertIn("Nessun dato", self.window.report_label.text())
        self.assertEqual(self.window.report_label.objectName(), "ResultAttentionWarning")

    def test_default_rail_hides_reversible_map_status(self) -> None:
        self.assertTrue(self.window.map_section_label.isHidden())
        self.assertTrue(self.window.map_status_label.isHidden())
        self.assertIn("Elaborazione locale", self.window.local_notice.text())
        self.assertNotIn("RICONOSCIMENTO", self.window.local_notice.text())

    def test_mode_change_makes_existing_output_unusable(self) -> None:
        self._prepare_output()

        self.window.mode_radios["maximum"].setChecked(True)

        self.assertTrue(self.window._managed_output_is_stale())
        self.assertFalse(self.window.copy_button.isEnabled())
        self.assertFalse(self.window.save_button.isEnabled())
        self.assertFalse(self.window.output_text.isEnabled())
        self.assertEqual(self.window.primary_button.text(), "Rianalizza dati")
        self.assertEqual(self.window.result_title_label.text(), "Risultato da rigenerare")
        self.assertEqual(self.window.result_state_label.text(), "NON UTILIZZABILE")
        self.assertIn("modalità di protezione", self.window.result_subtitle_label.text())

    def test_source_change_makes_existing_output_unusable(self) -> None:
        self._prepare_output()

        self.window.input_text.setPlainText(self.window.input_text.toPlainText() + " Nuovo contenuto.")

        self.assertTrue(self.window._managed_output_is_stale())
        self.assertFalse(self.window.copy_button.isEnabled())
        self.assertFalse(self.window.save_button.isEnabled())
        self.assertIn("testo sorgente", self.window.result_subtitle_label.text())

    def test_selection_change_requires_regeneration(self) -> None:
        self._prepare_output()

        self.window.findings_panel._index_to_item[0].setCheckState(Qt.Unchecked)

        self.assertTrue(self.window._managed_output_is_stale())
        self.assertEqual(self.window.primary_button.text(), "Ho controllato, continua")
        self.assertFalse(self.window.copy_button.isEnabled())
        self.assertFalse(self.window.save_button.isEnabled())

    def test_stale_output_is_guarded_even_if_actions_are_called_directly(self) -> None:
        self._prepare_output()
        self.window.mode_radios["maximum"].setChecked(True)

        self.window.copy_output()
        self.assertIn("Rigeneralo prima di copiarlo", self.window.statusBar().currentMessage())

        with mock.patch("privacy_guardian.app.QFileDialog.getSaveFileName") as save_dialog:
            self.window.save_output()

        save_dialog.assert_not_called()
        self.assertIn("Rigeneralo prima di salvarlo", self.window.statusBar().currentMessage())

    def test_reversible_report_warns_until_map_is_saved(self) -> None:
        self.window.mode_radios["reversible"].setChecked(True)
        self._prepare_output()

        self.assertTrue(self.window.reversible_mapping)
        self.assertFalse(self.window.map_section_label.isHidden())
        self.assertFalse(self.window.map_status_label.isHidden())
        self.assertFalse(self.window._reversible_map_saved)
        self.assertIn("Salva la mappa cifrata", self.window.report_label.text())
        self.assertEqual(self.window.map_status_label.objectName(), "MapStatusWarning")

        with mock.patch(
            "privacy_guardian.app.QFileDialog.getSaveFileName",
            return_value=("/tmp/test-output.omissis-map", ""),
        ), mock.patch.object(self.window, "_ask_passphrase", return_value="password locale"), mock.patch(
            "privacy_guardian.app.write_encrypted_mapping"
        ):
            self.window.save_reversible_map()

        self.assertTrue(self.window._reversible_map_saved)
        self.assertNotIn("Salva la mappa cifrata", self.window.report_label.text())
        self.assertEqual(self.window.map_status_label.objectName(), "MapStatusReady")

    def test_failed_regeneration_preserves_previous_output(self) -> None:
        self._prepare_output()
        previous_output = self.window.output_text.toPlainText()
        self.window.findings_panel._index_to_item[0].setCheckState(Qt.Unchecked)

        with mock.patch(
            "privacy_guardian.app.anonymize_workflow",
            side_effect=RuntimeError("errore sintetico"),
        ):
            self.window.anonymize_text()

        self.assertEqual(self.window.output_text.toPlainText(), previous_output)
        self.assertTrue(self.window._managed_output_is_stale())
        self.assertIn("errore sintetico", self.window.statusBar().currentMessage())

    def test_async_cancellation_preserves_previous_output(self) -> None:
        self._prepare_output()
        previous_output = self.window.output_text.toPlainText()
        self.window.findings_panel._index_to_item[0].setCheckState(Qt.Unchecked)
        self.window._run_jobs_synchronously = False
        started = Event()
        release = Event()

        def slow_workflow(engine, request, context):
            started.set()
            release.wait(timeout=3)
            context.check_cancelled()
            raise AssertionError("Il job cancellato non deve produrre un risultato.")

        with mock.patch("privacy_guardian.app.anonymize_workflow", side_effect=slow_workflow):
            self.window.anonymize_text()
            self.assertTrue(started.wait(timeout=2))
            self.assertIsNotNone(self.window._active_job)
            self.assertFalse(self.window.job_frame.isHidden())
            self.window.cancel_active_job()
            release.set()

            deadline = time.monotonic() + 3
            while self.window._active_job is not None and time.monotonic() < deadline:
                QApplication.processEvents()
                time.sleep(0.01)

        self.assertIsNone(self.window._active_job)
        self.assertEqual(self.window.output_text.toPlainText(), previous_output)
        self.assertTrue(self.window._managed_output_is_stale())
        self.assertIn("annullata", self.window.statusBar().currentMessage().lower())

    def test_async_analysis_applies_the_result_on_the_ui_thread(self) -> None:
        self.window._run_jobs_synchronously = False
        self.window.input_text.setPlainText("Mario Rossi")
        outcome = AnalysisOutcome(
            source_text="Mario Rossi",
            mode="standard",
            findings=(Finding("PERSON", 0, 11, 0.95),),
        )
        callback_threads = []
        original_apply = self.window._apply_analysis_outcome

        def record_thread(result):
            callback_threads.append(QThread.currentThread())
            original_apply(result)

        with (
            mock.patch("privacy_guardian.app.analyze_text_workflow", return_value=outcome),
            mock.patch.object(self.window, "_apply_analysis_outcome", side_effect=record_thread),
        ):
            self.window.analyze_text()
            deadline = time.monotonic() + 3
            while self.window._active_job is not None and time.monotonic() < deadline:
                QApplication.processEvents()
                time.sleep(0.01)

        self.assertIsNone(self.window._active_job)
        self.assertEqual(callback_threads, [self.window.thread()])
        self.assertEqual(len(self.window.findings), 1)

    def test_clear_can_be_cancelled_when_work_is_unsaved(self) -> None:
        self._prepare_output()
        original_output = self.window.output_text.toPlainText()

        with mock.patch.object(self.window, "_confirm_discard_work", return_value=False):
            self.window.clear_all()

        self.assertEqual(self.window.output_text.toPlainText(), original_output)
        self.assertIsNotNone(self.window._output_provenance)

    def test_loading_can_be_cancelled_before_current_work_is_replaced(self) -> None:
        self.window.input_text.setPlainText("Testo incollato non salvato.")

        with mock.patch.object(self.window, "_confirm_discard_work", return_value=False), mock.patch(
            "privacy_guardian.app.load_document"
        ) as load_mock:
            self.window._load_document_from_path("nuovo-documento.txt")

        load_mock.assert_not_called()
        self.assertEqual(self.window.input_text.toPlainText(), "Testo incollato non salvato.")

    def test_close_event_respects_discard_cancellation(self) -> None:
        self.window.input_text.setPlainText("Testo incollato non salvato.")
        event = QCloseEvent()

        with mock.patch.object(self.window, "isVisible", return_value=True), mock.patch.object(
            self.window, "_confirm_discard_work", return_value=False
        ):
            self.window.closeEvent(event)

        self.assertFalse(event.isAccepted())


@unittest.skipIf(_QT_IMPORT_ERROR is not None, f"PySide6/Qt not usable in this environment: {_QT_IMPORT_ERROR}")
class FindingsPanelIntegrationTests(unittest.TestCase):
    """Batch B: findings_panel.py + its bidirectional sync with the editor."""

    def setUp(self) -> None:
        _make_app()
        self.window = MainWindow()

    def tearDown(self) -> None:
        self.window.clear_all(force=True)
        self.window.close()
        self.window.deleteLater()

    def _set_synthetic_findings(self, text: str, findings: list[Finding]) -> None:
        """Puts the window in the same state _run_analysis() would, without depending
        on the real recognizer (useful for deterministic, hand-built Finding lists)."""
        self.window.input_text.setPlainText(text)
        self.window.findings = findings
        self.window.findings_stale = False
        self.window._findings_source_text = text
        self.window._findings_mode = self.window._selected_mode()
        self.window._fill_table()

    def test_excluding_a_finding_shrinks_checked_findings_and_updates_primary_label(self) -> None:
        text = "Mario Rossi, email mario.rossi@example.com, tel 333 1234567."
        findings = [
            Finding("PERSON", 0, 11, 0.95),
            Finding("EMAIL_ADDRESS", 19, 42, 0.9),
            Finding("PHONE_NUMBER", 48, 60, 0.9),
        ]
        self._set_synthetic_findings(text, findings)
        self.window._sync_action_state()
        self.assertEqual(len(self.window._checked_findings()), 3)
        self.assertEqual(self.window.primary_button.text(), "Ho controllato, continua")

        email_index = next(i for i, f in enumerate(findings) if f.entity_type == "EMAIL_ADDRESS")
        item = self.window.findings_panel._index_to_item[email_index]
        item.setCheckState(Qt.Unchecked)

        self.assertEqual(len(self.window._checked_findings()), 2)
        self.assertEqual(self.window.primary_button.text(), "Ho controllato, continua")

    def test_entity_highlights_are_bright_and_keep_readable_text(self) -> None:
        text = "Mario Rossi"
        self._set_synthetic_findings(text, [Finding("PERSON", 0, len(text), 0.95)])

        self.window._highlight_findings()
        highlight_selection = self.window.input_text.extraSelections()[0]
        highlight = highlight_selection.format
        self.assertEqual(highlight.background().color().alpha(), 96)
        self.assertEqual(highlight.foreground().color().name(), "#ffffff")

        self.window._selected_finding_index = 0
        self.window._highlight_findings()
        selected_selection = self.window.input_text.extraSelections()[0]
        selected_highlight = selected_selection.format
        self.assertEqual(selected_highlight.background().color().alpha(), 144)
        self.assertEqual(selected_highlight.foreground().color().name(), "#ffffff")

    def test_filter_pill_reduces_visible_rows_without_touching_inclusion(self) -> None:
        text = "Mario Rossi, email mario.rossi@example.com, tel 333 1234567."
        findings = [
            Finding("PERSON", 0, 11, 0.95),
            Finding("EMAIL_ADDRESS", 19, 42, 0.9),
            Finding("PHONE_NUMBER", 48, 60, 0.9),
        ]
        self._set_synthetic_findings(text, findings)
        panel = self.window.findings_panel

        self.assertEqual(panel._model.rowCount(), 3)
        panel._pill_buttons["Persone"].setChecked(True)
        self.assertEqual(panel._model.rowCount(), 1)
        self.assertEqual(len(self.window._checked_findings()), 3)

    def test_filter_pills_show_only_categories_present_in_the_review(self) -> None:
        text = "Mario Rossi vive a Potenza il 12/06/2026 presso Acme S.p.A."
        person_start = text.index("Mario Rossi")
        location_start = text.index("Potenza")
        date_start = text.index("12/06/2026")
        organization_start = text.index("Acme S.p.A.")
        findings = [
            Finding("PERSON", person_start, person_start + len("Mario Rossi"), 0.95),
            Finding("LOCATION", location_start, location_start + len("Potenza"), 0.9),
            Finding("DATE", date_start, date_start + len("12/06/2026"), 0.9),
            Finding("ORGANIZATION", organization_start, organization_start + len("Acme S.p.A."), 0.9),
        ]
        self._set_synthetic_findings(text, findings)
        panel = self.window.findings_panel

        for category in ("Tutti", "Persone", "Luoghi", "Date", "Enti"):
            self.assertGreater(panel._pill_buttons[category].maximumWidth(), 0)
            self.assertTrue(panel._pill_buttons[category].isEnabled())
        for category in ("Contatti", "Finanziari", "Documenti", "Altro"):
            self.assertEqual(panel._pill_buttons[category].maximumWidth(), 0)
            self.assertFalse(panel._pill_buttons[category].isEnabled())

        panel._pill_buttons["Luoghi"].setChecked(True)
        self.assertEqual(panel._model.rowCount(), 1)
        self.assertEqual(panel._model.item(0, 1).text(), "Potenza")

    def test_filters_appear_only_when_results_make_them_useful(self) -> None:
        panel = self.window.findings_panel
        self.assertTrue(panel.pill_scroll.isHidden())
        self.assertTrue(panel.search_edit.isHidden())

        self._set_synthetic_findings(
            "Mario Rossi",
            [Finding("PERSON", 0, 11, 0.95)],
        )
        self.assertFalse(panel.pill_scroll.isHidden())
        self.assertTrue(panel.search_edit.isHidden())

        text = " ".join(f"Nome{i}" for i in range(8))
        findings: list[Finding] = []
        start = 0
        for value in text.split():
            findings.append(Finding("PERSON", start, start + len(value), 0.95))
            start += len(value) + 1
        self._set_synthetic_findings(text, findings)
        self.assertFalse(panel.search_edit.isHidden())

    def test_search_filters_rows_by_value(self) -> None:
        text = "Mario Rossi, email mario.rossi@example.com, tel 333 1234567."
        findings = [
            Finding("PERSON", 0, 11, 0.95),
            Finding("EMAIL_ADDRESS", 19, 42, 0.9),
            Finding("PHONE_NUMBER", 48, 60, 0.9),
        ]
        self._set_synthetic_findings(text, findings)
        panel = self.window.findings_panel

        panel.search_edit.setText("mario.rossi@")
        self.assertEqual(panel._model.rowCount(), 1)
        panel.search_edit.clear()
        self.assertEqual(panel._model.rowCount(), 3)

    def test_review_labels_explain_action_and_reliability(self) -> None:
        text = "Mario Rossi"
        self._set_synthetic_findings(text, [Finding("PERSON", 0, 11, 0.95)])
        panel = self.window.findings_panel

        self.assertEqual(panel._model.headerData(0, Qt.Horizontal), "Anonimizza")
        self.assertEqual(panel._model.headerData(2, Qt.Horizontal), "Affidabilità")
        self.assertEqual(panel._model.item(0, 2).text(), "Alta")
        self.assertIn("Spuntato", panel.selection_help_label.text())

    def test_clicking_a_row_moves_editor_cursor_to_finding_start(self) -> None:
        text = "Mario Rossi, email mario.rossi@example.com, tel 333 1234567."
        findings = [
            Finding("PERSON", 0, 11, 0.95),
            Finding("EMAIL_ADDRESS", 19, 42, 0.9),
            Finding("PHONE_NUMBER", 48, 60, 0.9),
        ]
        self._set_synthetic_findings(text, findings)

        self.window.findings_panel.finding_selected.emit(1)

        self.assertEqual(self.window.input_text.textCursor().position(), findings[1].start)
        self.assertEqual(self.window._selected_finding_index, 1)

    def test_select_finding_from_editor_position_selects_matching_row(self) -> None:
        text = "Mario Rossi, email mario.rossi@example.com, tel 333 1234567."
        findings = [
            Finding("PERSON", 0, 11, 0.95),
            Finding("EMAIL_ADDRESS", 19, 42, 0.9),
            Finding("PHONE_NUMBER", 48, 60, 0.9),
        ]
        self._set_synthetic_findings(text, findings)

        position = 3  # inside "Mario Rossi"
        index = self.window._finding_at_position(position)
        self.assertEqual(index, 0)

        self.window.findings_panel.select_finding(index)
        self.assertEqual(self.window.findings_panel.selected_finding(), 0)
        expected_item = self.window.findings_panel._index_to_item[0]
        self.assertEqual(self.window.findings_panel.tree.currentIndex(), expected_item.index())

    def test_many_findings_switch_to_grouped_view_with_correct_counts(self) -> None:
        text = ""
        findings = []
        pos = 0
        for i in range(35):
            value = f"user{i}@example.com"
            text += value + " "
            findings.append(Finding("EMAIL_ADDRESS", pos, pos + len(value), 0.9))
            pos += len(value) + 1

        self._set_synthetic_findings(text, findings)
        panel = self.window.findings_panel

        self.assertEqual(panel._model.rowCount(), 1)
        group_item = panel._model.item(0, 0)
        self.assertTrue(group_item.data(ROLE_IS_GROUP))
        self.assertEqual(group_item.rowCount(), 35)
        self.assertIn("35 occorrenze", group_item.text())
        self.assertIn("35 valori distinti", group_item.text())
        self.assertIn("0 esclusi", group_item.text())

    def test_group_checkbox_excludes_all_occurrences_of_the_type(self) -> None:
        text = ""
        findings = []
        pos = 0
        for i in range(35):
            value = f"user{i}@example.com"
            text += value + " "
            findings.append(Finding("EMAIL_ADDRESS", pos, pos + len(value), 0.9))
            pos += len(value) + 1

        self._set_synthetic_findings(text, findings)
        panel = self.window.findings_panel
        group_item = panel._model.item(0, 0)

        group_item.setCheckState(Qt.Unchecked)

        self.assertTrue(all(not included for included in panel.included_mask()))
        self.assertEqual(len(self.window._checked_findings()), 0)
        self.assertIn("35 esclusi", group_item.text())

    def test_extract_document_as_text_switches_docx_to_occurrence_selection(self) -> None:
        """Su .docx la selezione manuale è già attiva (extra_values); estrarre come testo
        toglie solo la modalità di esclusione per valore, passando a quella per occorrenza."""
        loaded = LoadedDocument(
            path=Path("relazione.docx"),
            text="Mario Rossi lavora presso Acme S.p.A.",
            extension=".docx",
        )
        self.window.loaded_document = loaded
        self.window.input_text.setPlainText(loaded.text)
        self.assertTrue(self.window._manual_add_supported())
        self.assertTrue(self.window._selection_filter_supported())
        self.assertTrue(self.window._value_level_selection_active())

        self.window._extract_document_as_text()

        self.assertIsNone(self.window.loaded_document)
        self.assertTrue(self.window._manual_add_supported())
        self.assertFalse(self.window._value_level_selection_active())

    def test_extract_document_as_text_reenables_manual_add_for_doc(self) -> None:
        """Il formato .doc legacy resta l'unico senza selezione manuale né esclusioni:
        estrarre come testo la sblocca."""
        loaded = LoadedDocument(
            path=Path("relazione.doc"),
            text="Mario Rossi lavora presso Acme S.p.A.",
            extension=".doc",
        )
        self.window.loaded_document = loaded
        self.window.input_text.setPlainText(loaded.text)
        self.assertFalse(self.window._manual_add_supported())

        self.window._extract_document_as_text()

        self.assertIsNone(self.window.loaded_document)
        self.assertTrue(self.window._manual_add_supported())

    def test_extract_pdf_as_text_normalizes_and_reanalyzes(self) -> None:
        loaded = LoadedDocument(
            path=Path("atto.pdf"),
            text="Università degli Studi della Basili-\ncata\n\nMario Ros-\nsi",
            extension=".pdf",
        )
        self.window.loaded_document = loaded
        self.window.input_text.setPlainText(loaded.text)

        self.window._extract_document_as_text()

        converted = self.window.input_text.toPlainText()
        self.assertIsNone(self.window.loaded_document)
        self.assertEqual(
            converted,
            "Università degli Studi della Basilicata\n\nMario Rossi",
        )
        values = [
            (finding.entity_type, converted[finding.start : finding.end])
            for finding in self.window.findings
        ]
        self.assertIn(
            ("ORGANIZATION", "Università degli Studi della Basilicata"),
            values,
        )
        self.assertIn(("PERSON", "Mario Rossi"), values)
        self.assertIn("PDF convertito in testo", self.window.document_label.text())
        self.assertTrue(self.window.findings_panel.notice_frame.isHidden())

    def test_pdf_choice_persists_after_analysis_and_explains_the_tradeoff(self) -> None:
        self._load_fake_document_with_findings(
            ".pdf",
            "Mario Rossi",
            [Finding("PERSON", 0, 11, 0.9)],
        )

        self.assertTrue(self.window.findings_panel.notice_frame.isHidden())
        self.assertFalse(self.window.pdf_choice_frame.isHidden())
        self.assertTrue(self.window.pdf_choice_radios["pdf"].isChecked())
        self.assertTrue(self.window._analysis_preview_active)
        self.assertTrue(self.window.output_text.toPlainText())
        self.assertNotIn("Mario Rossi", self.window.output_text.toPlainText())
        self.assertEqual(self.window.output_panel_title.text(), "Anteprima anonimizzata")
        self.assertIn(
            "PDF rasterizzato",
            self.window.pdf_choice_radios["pdf"].accessibleDescription(),
        )
        self.assertIn(
            "può migliorare il riconoscimento",
            self.window.pdf_choice_radios["text"].accessibleDescription(),
        )

        finding_item = self.window.findings_panel._index_to_item[0]
        finding_item.setCheckState(Qt.Unchecked)
        self.assertIn("Mario Rossi", self.window.output_text.toPlainText())
        finding_item.setCheckState(Qt.Checked)
        self.assertNotIn("Mario Rossi", self.window.output_text.toPlainText())

        self.window.pdf_choice_radios["text"].setChecked(True)

        self.assertEqual(self.window.primary_button.text(), "Trasforma e analizza")
        self.assertFalse(self.window.pdf_choice_frame.isHidden())
        with mock.patch.object(self.window, "_extract_document_as_text") as extract_as_text:
            self.window._primary_action()
        extract_as_text.assert_called_once_with()

        self.window.pdf_choice_radios["pdf"].setChecked(True)
        self.assertEqual(self.window.primary_button.text(), "Ho controllato, continua")

    def _load_fake_document_with_findings(
        self, extension: str, text: str, findings: list[Finding]
    ) -> None:
        """Puts the window in the state _load_document_from_path + analysis would leave,
        without touching the filesystem or the real recognizer."""
        self.window.loaded_document = LoadedDocument(
            path=Path(f"documento{extension}"), text=text, extension=extension
        )
        self.window.input_text.setPlainText(text)
        self.window.document_text_dirty = False
        self.window.findings = findings
        self.window.findings_stale = False
        self.window._findings_source_text = text
        self.window._findings_mode = self.window._selected_mode()
        self.window._fill_table()
        self.window._refresh_analysis_preview()
        self.window._sync_action_state()

    def test_docx_value_level_toggle_propagates_to_same_value_rows(self) -> None:
        email = "mario@example.com"
        text = f"{email} scrive a laura@example.com poi ancora {email}"
        second = text.index(email, 1)
        other = text.index("laura@example.com")
        findings = [
            Finding("EMAIL_ADDRESS", 0, len(email), 0.98),
            Finding("EMAIL_ADDRESS", other, other + len("laura@example.com"), 0.98),
            Finding("EMAIL_ADDRESS", second, second + len(email), 0.98),
        ]
        self._load_fake_document_with_findings(".docx", text, findings)
        panel = self.window.findings_panel

        self.assertTrue(self.window._value_level_selection_active())
        first_item = panel._index_to_item[0]
        self.assertTrue(first_item.flags() & Qt.ItemIsUserCheckable)
        self.assertEqual(self.window.primary_button.text(), "Ho controllato, continua")
        # Il .docx supporta sia le esclusioni sia le selezioni manuali: l'avviso (riservato
        # ai formati non supportati come .doc) resta nascosto.
        self.assertTrue(panel.notice_frame.isHidden())

        first_item.setCheckState(Qt.Unchecked)

        self.assertEqual(panel.included_mask(), [False, True, False])
        self.assertEqual(len(self.window._checked_findings()), 1)
        self.assertEqual(self.window.primary_button.text(), "Ho controllato, continua")

    def test_plain_text_toggle_stays_per_occurrence(self) -> None:
        email = "mario@example.com"
        text = f"{email} e di nuovo {email}"
        second = text.index(email, 1)
        findings = [
            Finding("EMAIL_ADDRESS", 0, len(email), 0.98),
            Finding("EMAIL_ADDRESS", second, second + len(email), 0.98),
        ]
        self._set_synthetic_findings(text, findings)
        panel = self.window.findings_panel

        self.assertFalse(self.window._value_level_selection_active())
        panel._index_to_item[0].setCheckState(Qt.Unchecked)

        self.assertEqual(panel.included_mask(), [False, True])
        self.assertEqual(len(self.window._checked_findings()), 1)

    def test_anonymize_passes_extra_values_for_checked_manual_finding_on_pdf(self) -> None:
        text = "Documento numero ABC9988 rilasciato oggi."
        manual_start = text.index("ABC9988")
        manual_end = manual_start + len("ABC9988")
        findings = [Finding("IDENTITY_DOCUMENT", manual_start, manual_end, 1.0, source="manual")]
        self._load_fake_document_with_findings(".pdf", text, findings)

        captured: dict = {}

        def fake_anonymize(document, engine, mode, **kwargs):
            captured.update(kwargs)
            return AnonymizedDocument(filename="documento_anonimizzato.pdf", data=b"%PDF-1.4", text=text, findings=[])

        with mock.patch("privacy_guardian.desktop_workflows.anonymize_loaded_document", side_effect=fake_anonymize):
            self.window.anonymize_text()

        self.assertEqual(captured.get("extra_values"), frozenset({("IDENTITY_DOCUMENT", "ABC9988")}))

    def test_anonymize_passes_extra_values_for_checked_manual_finding_on_docx(self) -> None:
        text = "Documento numero ABC9988 rilasciato oggi."
        manual_start = text.index("ABC9988")
        manual_end = manual_start + len("ABC9988")
        findings = [Finding("IDENTITY_DOCUMENT", manual_start, manual_end, 1.0, source="manual")]
        self._load_fake_document_with_findings(".docx", text, findings)

        captured: dict = {}

        def fake_anonymize(document, engine, mode, **kwargs):
            captured.update(kwargs)
            return AnonymizedDocument(filename="documento_anonimizzato.docx", data=b"PK", text=text, findings=[])

        with mock.patch("privacy_guardian.desktop_workflows.anonymize_loaded_document", side_effect=fake_anonymize):
            self.window.anonymize_text()

        self.assertEqual(captured.get("extra_values"), frozenset({("IDENTITY_DOCUMENT", "ABC9988")}))

    def test_anonymize_omits_extra_values_when_manual_finding_unchecked(self) -> None:
        text = "Documento numero ABC9988 rilasciato oggi."
        manual_start = text.index("ABC9988")
        manual_end = manual_start + len("ABC9988")
        findings = [Finding("IDENTITY_DOCUMENT", manual_start, manual_end, 1.0, source="manual")]
        self._load_fake_document_with_findings(".docx", text, findings)
        self.window.findings_panel._index_to_item[0].setCheckState(Qt.Unchecked)

        captured: dict = {}

        def fake_anonymize(document, engine, mode, **kwargs):
            captured.update(kwargs)
            return AnonymizedDocument(filename="documento_anonimizzato.docx", data=b"PK", text=text, findings=[])

        with mock.patch("privacy_guardian.desktop_workflows.anonymize_loaded_document", side_effect=fake_anonymize):
            self.window.anonymize_text()

        self.assertIsNone(captured.get("extra_values"))

    def test_add_missing_data_is_available_during_review_for_pdf_and_docx(self) -> None:
        from PySide6.QtGui import QTextCursor

        for extension in (".pdf", ".docx"):
            with self.subTest(extension=extension):
                self.window.loaded_document = LoadedDocument(
                    path=Path(f"documento{extension}"), text="Testo di prova", extension=extension
                )
                self.window.document_text_dirty = False
                self.window.input_text.setPlainText("Testo di prova")
                self.window.findings = []
                self.window.findings_stale = False
                self.window._findings_source_text = "Testo di prova"
                self.window._findings_mode = self.window._selected_mode()
                self.window._fill_table()
                self.window._sync_action_state()

                self.assertEqual(self.window.primary_button.text(), "Ho controllato, continua")
                self.assertFalse(self.window.add_selection_button.isHidden())
                self.assertFalse(self.window.add_selection_button.isEnabled())

                cursor = self.window.input_text.textCursor()
                cursor.setPosition(0)
                cursor.setPosition(len("Testo"), QTextCursor.KeepAnchor)
                self.window.input_text.setTextCursor(cursor)

                self.assertTrue(self.window.add_selection_button.isEnabled())
                self.assertEqual(self.window.add_selection_button.text(), "Aggiungi dato mancante")
                self.window.clear_all(force=True)

    def test_manual_selection_expands_to_every_occurrence_in_plain_text(self) -> None:
        from PySide6.QtGui import QTextCursor

        from privacy_guardian.app import QInputDialog

        text = "La sede di Potenza e la filiale di Potenza sono chiuse."
        self.window.input_text.setPlainText(text)
        first = text.index("Potenza")
        cursor = self.window.input_text.textCursor()
        cursor.setPosition(first)
        cursor.setPosition(first + len("Potenza"), QTextCursor.KeepAnchor)
        self.window.input_text.setTextCursor(cursor)

        with mock.patch.object(QInputDialog, "exec", return_value=QInputDialog.Accepted), mock.patch.object(
            QInputDialog, "textValue", return_value="ente territoriale"
        ):
            self.window.add_manual_finding()

        potenza_findings = [
            f for f in self.window.findings if text[f.start : f.end] == "Potenza" and f.source == "manual"
        ]
        self.assertEqual(len(potenza_findings), 2)

        self.window.anonymize_text()
        self.assertNotIn("Potenza", self.window.output_text.toPlainText())

    def test_ocr_unavailable_error_opens_guided_dialog_instead_of_status_bar(self) -> None:
        calls: list[Path] = []
        self.window._show_ocr_setup_dialog = lambda path: calls.append(path)

        with mock.patch(
            "privacy_guardian.app.load_document",
            side_effect=OcrUnavailableError("Il PDF contiene immagini. Installa Tesseract OCR."),
        ):
            self.window._load_document_from_path("scansione.pdf")

        self.assertEqual(calls, [Path("scansione.pdf")])
        self.assertIsNone(self.window.loaded_document)

    def test_ocr_dialog_accept_retries_loading_the_same_path(self) -> None:
        calls: list[Path] = []
        self.window._load_document_from_path = lambda path: calls.append(Path(path))

        with mock.patch.object(QDialog, "exec", return_value=QDialog.Accepted):
            self.window._show_ocr_setup_dialog(Path("scansione.pdf"))

        self.assertEqual(calls, [Path("scansione.pdf")])

    def test_ocr_dialog_reject_does_not_retry_loading(self) -> None:
        calls: list[Path] = []
        self.window._load_document_from_path = lambda path: calls.append(Path(path))

        with mock.patch.object(QDialog, "exec", return_value=QDialog.Rejected):
            self.window._show_ocr_setup_dialog(Path("scansione.pdf"))

        self.assertEqual(calls, [])

    def test_ocr_dialog_builds_without_error_on_every_platform(self) -> None:
        for system in ("Darwin", "Windows", "Linux"):
            with mock.patch("privacy_guardian.app.platform.system", return_value=system), \
                    mock.patch.object(QDialog, "exec", return_value=QDialog.Rejected):
                self.window._show_ocr_setup_dialog(Path("scansione.pdf"))

    def test_tesseract_install_command_is_platform_specific(self) -> None:
        self.assertEqual(
            self.window._tesseract_install_command("Darwin"),
            "brew install tesseract tesseract-lang",
        )
        self.assertEqual(
            self.window._tesseract_install_command("Linux"),
            "sudo apt install tesseract-ocr tesseract-ocr-ita",
        )


if __name__ == "__main__":
    unittest.main()
