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
os.environ["OMISSIS_UI_SETTINGS_PATH"] = str(
    Path(_ACTIVITY_TEST_DIR.name) / "ui-settings.ini"
)

try:
    from PySide6.QtCore import QPoint, QSettings, QThread, Qt
    from PySide6.QtGui import QCloseEvent, QKeySequence, QPalette
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QTextEdit

    from privacy_guardian.app import MainWindow, _DiscardWorkDialog, _EntityTypeDialog
    from privacy_guardian.desktop_workflows import AnalysisOutcome
    from privacy_guardian.document_service import AnonymizedDocument, LoadedDocument, OcrUnavailableError
    from privacy_guardian.findings_panel import ROLE_IS_GROUP
    from privacy_guardian.models import Finding
    from privacy_guardian.reversible import ReversibleMapEntry, ReversibleMapError
    from scripts.create_app_icon import build_icon

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


def _clear_ui_settings() -> None:
    settings = QSettings(os.environ["OMISSIS_UI_SETTINGS_PATH"], QSettings.IniFormat)
    settings.clear()
    settings.sync()


@unittest.skipIf(_QT_IMPORT_ERROR is not None, f"PySide6/Qt not usable in this environment: {_QT_IMPORT_ERROR}")
class DesktopMainWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        _make_app()
        _clear_ui_settings()
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
        self.assertFalse(self.window.output_preview_inline_notice.isHidden())
        self.assertIn("Crea copia protetta", self.window.output_preview_inline_notice.text())
        self.assertTrue(self.window.output_preview_notice.isHidden())
        self.assertEqual(len(self.window.output_text.extraSelections()), 1)
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
        self.assertTrue(self.window.output_preview_inline_notice.isHidden())
        self.assertTrue(self.window.output_preview_notice.isHidden())
        self.assertFalse(self.window.output_text.isReadOnly())
        self.assertEqual(self.window.primary_button.text(), "Copia per l’IA")
        self.assertFalse(self.window.save_button.isHidden())
        self.assertEqual(self.window.save_button.text(), "Salva anche come file")
        self.assertEqual(
            [row.objectName() for row in self.window.step_rows],
            ["StepRowDone"] * 4 + ["StepRowCurrent"],
        )
        self.window.clear_all(force=True)

    def test_preview_editors_start_at_the_same_vertical_position(self) -> None:
        text = "Mario Rossi scrive a mario@example.com."
        self.window.input_text.setPlainText(text)
        with mock.patch.object(
            self.window.engine,
            "analyze",
            return_value=[Finding("PERSON", 0, len("Mario Rossi"), 0.95)],
        ):
            self.window.analyze_text()

        self.window.resize(1400, 820)
        self.window.show()
        QApplication.processEvents()

        source_top = self.window.input_text.viewport().mapToGlobal(QPoint(0, 0)).y()
        preview_top = self.window.output_text.viewport().mapToGlobal(QPoint(0, 0)).y()
        self.assertLessEqual(abs(source_top - preview_top), 1)

    def test_entity_type_dialog_uses_the_branded_compact_design(self) -> None:
        dialog = _EntityTypeDialog(
            ["località", "organizzazione", "persona"],
            "Corte di Appello di Potenza",
            self.window,
        )

        self.assertEqual(dialog.objectName(), "EntityTypeDialog")
        self.assertTrue(dialog.windowFlags() & Qt.FramelessWindowHint)
        self.assertEqual(dialog.entity_combo.objectName(), "EntityTypeCombo")
        self.assertEqual(dialog.entity_combo.count(), 3)
        self.assertIn(
            "Corte di Appello di Potenza",
            dialog.accessibleDescription(),
        )
        self.assertEqual(
            {button.text() for button in dialog.findChildren(QPushButton)},
            {"×", "Annulla", "Aggiungi"},
        )
        dialog.show()
        QApplication.processEvents()
        combo_image = dialog.entity_combo.grab().toImage()
        arrow_pixels = 0
        for x in range(max(0, combo_image.width() - 30), combo_image.width() - 8):
            for y in range(max(0, combo_image.height() // 2 - 8), min(combo_image.height(), combo_image.height() // 2 + 8)):
                color = combo_image.pixelColor(x, y)
                if color.red() > 170 and color.green() > 185 and color.blue() > 195:
                    arrow_pixels += 1
        self.assertGreater(arrow_pixels, 4)
        dialog.deleteLater()

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

    def test_document_panes_use_larger_reading_typography(self) -> None:
        for editor in (
            self.window.input_text,
            self.window.ai_response_text,
            self.window.output_text,
        ):
            with self.subTest(editor=editor.accessibleName()):
                self.assertIn("font-size: 16px", editor.styleSheet())
                self.assertIn("line-height: 1.55", editor.styleSheet())

    def test_document_appearance_switches_all_reading_panes_to_paper(self) -> None:
        self.window.input_text.setPlainText("Mario Rossi")
        self.window.document_paper_button.click()

        self.assertTrue(self.window.document_paper_button.isChecked())
        self.assertFalse(self.window.document_dark_button.isChecked())
        for editor in (
            self.window.input_text,
            self.window.ai_response_text,
            self.window.output_text,
        ):
            with self.subTest(editor=editor.accessibleName()):
                self.assertEqual(editor.property("documentAppearance"), "paper")
                self.assertEqual(editor.palette().color(QPalette.Base).name(), "#f7f8f7")
                self.assertEqual(editor.palette().color(QPalette.Text).name(), "#10161a")
                self.assertEqual(
                    editor.viewport().palette().color(QPalette.Base).name(),
                    "#f7f8f7",
                )

        cursor = self.window.input_text.textCursor()
        cursor.select(cursor.SelectionType.Document)
        self.assertEqual(cursor.charFormat().foreground().color().name(), "#10161a")

        self.window.document_dark_button.click()
        self.assertEqual(
            self.window.input_text.palette().color(QPalette.Base).name(),
            "#12181f",
        )
        self.assertEqual(
            self.window.input_text.palette().color(QPalette.Text).name(),
            "#e8edf2",
        )

    def test_document_appearance_preference_is_persisted_locally(self) -> None:
        self.window.document_paper_button.click()

        reopened = MainWindow()
        try:
            self.assertTrue(reopened.document_paper_button.isChecked())
            self.assertEqual(reopened._document_appearance, "paper")
            self.assertEqual(
                reopened.output_text.palette().color(QPalette.Base).name(),
                "#f7f8f7",
            )
        finally:
            reopened.close()
            reopened.deleteLater()

    def test_flat_omissis_icon_has_no_blurred_alpha_halo(self) -> None:
        icon = build_icon(256)
        alpha_histogram = icon.getchannel("A").histogram()
        self.assertEqual(sum(alpha_histogram[1:255]), 0)
        self.assertGreater(alpha_histogram[0], 0)
        self.assertGreater(alpha_histogram[255], 0)
        self.assertEqual(icon.getpixel((0, 0))[3], 0)

        logo_svg = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "privacy_guardian"
            / "assets"
            / "omissis-logo.svg"
        ).read_text(encoding="utf-8")
        self.assertNotIn("softGlow", logo_svg)
        self.assertNotIn("feGaussianBlur", logo_svg)

    def test_original_and_anonymized_text_scroll_proportionally_together(self) -> None:
        self.window.show()
        source = "\n".join(f"Riga originale {index}: Mario Rossi" for index in range(180))
        output = "\n".join(f"Riga anonimizzata {index}: <PERSONA>" for index in range(180))
        self.window.input_text.setPlainText(source)
        self.window._set_output_text(output)
        QApplication.processEvents()

        source_bar = self.window.input_text.verticalScrollBar()
        output_bar = self.window.output_text.verticalScrollBar()
        self.assertGreater(source_bar.maximum(), 0)
        self.assertGreater(output_bar.maximum(), 0)

        source_bar.setValue(source_bar.maximum() // 2)
        QApplication.processEvents()
        expected_output = round(
            source_bar.value() / source_bar.maximum() * output_bar.maximum()
        )
        self.assertAlmostEqual(output_bar.value(), expected_output, delta=1)

        output_bar.setValue(output_bar.maximum() * 3 // 4)
        QApplication.processEvents()
        expected_source = round(
            output_bar.value() / output_bar.maximum() * source_bar.maximum()
        )
        self.assertAlmostEqual(source_bar.value(), expected_source, delta=1)

        source_position = source_bar.value()
        refreshed_output = "\n".join(
            f"Anteprima aggiornata {index}: <PERSONA>" for index in range(160)
        )
        self.window._set_analysis_preview(refreshed_output)
        QApplication.processEvents()
        self.assertAlmostEqual(source_bar.value(), source_position, delta=1)
        expected_output = round(
            source_bar.value() / source_bar.maximum() * output_bar.maximum()
        )
        self.assertAlmostEqual(output_bar.value(), expected_output, delta=1)

    def test_ai_response_and_reconstructed_text_scroll_proportionally_together(self) -> None:
        self.window.show()
        original = "\n".join(f"Riga originale {index}: Mario Rossi" for index in range(180))
        response = "\n".join(f"Risposta IA {index}: <PERSONA_1>" for index in range(180))
        restored = "\n".join(f"Testo ricostruito {index}: Mario Rossi" for index in range(180))
        self.window.input_text.setPlainText(original)
        self.window._set_restored_comparison_source(response)
        self.window._set_output_text(restored)
        self.window._mark_output_generated(
            "reversible",
            total_findings=1,
            included_findings=1,
            kind="restored",
        )
        QApplication.processEvents()

        self.assertIs(self.window.source_view_stack.currentWidget(), self.window.ai_response_text)
        response_bar = self.window.ai_response_text.verticalScrollBar()
        output_bar = self.window.output_text.verticalScrollBar()
        self.assertGreater(response_bar.maximum(), 0)
        self.assertGreater(output_bar.maximum(), 0)

        response_bar.setValue(response_bar.maximum() // 3)
        QApplication.processEvents()
        expected_output = round(
            response_bar.value() / response_bar.maximum() * output_bar.maximum()
        )
        self.assertAlmostEqual(output_bar.value(), expected_output, delta=1)

        output_bar.setValue(output_bar.maximum() * 2 // 3)
        QApplication.processEvents()
        expected_response = round(
            output_bar.value() / output_bar.maximum() * response_bar.maximum()
        )
        self.assertAlmostEqual(response_bar.value(), expected_response, delta=1)

    def test_long_output_keeps_position_when_source_cannot_scroll(self) -> None:
        self.window.show()
        self.window.input_text.setPlainText("Testo originale breve")
        self.window._set_output_text(
            "\n".join(f"Riga anonimizzata {index}: <PERSONA>" for index in range(180))
        )
        QApplication.processEvents()

        source_bar = self.window.input_text.verticalScrollBar()
        output_bar = self.window.output_text.verticalScrollBar()
        self.assertEqual(source_bar.maximum(), 0)
        self.assertGreater(output_bar.maximum(), 0)

        output_bar.setValue(output_bar.maximum() // 2)
        output_position = output_bar.value()
        self.window._handle_text_scroll_range_changed()
        QApplication.processEvents()

        self.assertEqual(output_bar.value(), output_position)

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
        self.assertEqual(self.window.primary_button.accessibleName(), "Copia per l’IA")
        self.window.clear_all(force=True)

    def test_discard_dialog_uses_dark_theme_and_keeps_cancel_as_default(self) -> None:
        dialog = _DiscardWorkDialog(
            "Esci e scarta",
            ["selezioni di anonimizzazione non ancora applicate"],
            self.window,
        )
        dialog.show()
        QApplication.processEvents()

        self.assertEqual(dialog.objectName(), "DiscardWorkDialog")
        self.assertTrue(dialog.windowFlags() & Qt.FramelessWindowHint)
        self.assertTrue(dialog.cancel_button.isDefault())
        self.assertTrue(dialog.cancel_button.hasFocus())
        self.assertEqual(dialog.discard_button.objectName(), "DestructiveButton")
        self.assertIn(
            "selezioni di anonimizzazione non ancora applicate",
            dialog.accessibleDescription(),
        )
        dialog.discard_button.click()
        self.assertEqual(dialog.result(), QDialog.Accepted)
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
        _clear_ui_settings()
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
        self.assertEqual(self.window.primary_button.text(), "Copia per l’IA")
        self.assertTrue(self.window.save_button.isEnabled())
        self.assertFalse(self.window.save_button.isHidden())
        self.assertTrue(self.window.findings_panel.isHidden())
        self.assertFalse(self.window.add_selection_button.isHidden())
        self.assertEqual(self.window.add_selection_button.text(), "Modifica selezioni")

        self.window.copy_output()

        self.assertEqual(self.window.result_state_label.text(), "COPIATA")
        self.assertIn("IA", self.window.statusBar().currentMessage())

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
        self.assertIn("Salva il File di ripristino", self.window.report_label.text())
        self.assertEqual(self.window.map_status_label.objectName(), "MapStatusWarning")

        with mock.patch(
            "privacy_guardian.app.QFileDialog.getSaveFileName",
            return_value=("/tmp/test-output.omissis-map", ""),
        ), mock.patch.object(self.window, "_ask_passphrase", return_value="password locale"), mock.patch(
            "privacy_guardian.app.write_encrypted_mapping"
        ):
            self.window.save_reversible_map()

        self.assertTrue(self.window._reversible_map_saved)
        self.assertNotIn("Salva il File di ripristino", self.window.report_label.text())
        self.assertEqual(self.window.map_status_label.objectName(), "MapStatusReady")

    def test_passphrase_confirmation_uses_one_consistent_dialog(self) -> None:
        executions = 0

        def complete_dialog(dialog: QDialog) -> int:
            nonlocal executions
            executions += 1
            self.assertEqual(dialog.minimumWidth(), 520)
            self.assertEqual(dialog.maximumWidth(), 520)

            fields = {field.objectName(): field for field in dialog.findChildren(QLineEdit)}
            self.assertEqual(
                set(fields),
                {"PassphraseEdit", "PassphraseConfirmationEdit"},
            )
            self.assertTrue(
                all(field.echoMode() == QLineEdit.Password for field in fields.values())
            )
            fields["PassphraseEdit"].setText("password locale")
            fields["PassphraseConfirmationEdit"].setText("password locale")

            confirm_button = next(
                button for button in dialog.findChildren(QPushButton) if button.text() == "Conferma"
            )
            confirm_button.click()
            return dialog.result()

        with mock.patch("privacy_guardian.app.QDialog.exec", new=complete_dialog):
            passphrase = self.window._ask_passphrase(
                "Password del File di ripristino",
                "Scegli una password per cifrare il File di ripristino:",
                confirm=True,
            )

        self.assertEqual(executions, 1)
        self.assertEqual(passphrase, "password locale")

    def test_passphrase_confirmation_recovers_inline_from_a_mismatch(self) -> None:
        def complete_dialog(dialog: QDialog) -> int:
            password = dialog.findChild(QLineEdit, "PassphraseEdit")
            confirmation = dialog.findChild(QLineEdit, "PassphraseConfirmationEdit")
            validation = dialog.findChild(QLabel, "RestoreValidationError")
            confirm_button = next(
                button for button in dialog.findChildren(QPushButton) if button.text() == "Conferma"
            )

            password.setText("password corretta")
            confirmation.setText("password diversa")
            confirm_button.click()

            self.assertEqual(dialog.result(), QDialog.Rejected)
            self.assertFalse(validation.isHidden())
            self.assertIn("non coincidono", validation.text())

            confirmation.setText("password corretta")
            confirm_button.click()
            return dialog.result()

        with mock.patch("privacy_guardian.app.QDialog.exec", new=complete_dialog):
            passphrase = self.window._ask_passphrase(
                "Password del File di ripristino",
                "Scegli una password per cifrare il File di ripristino:",
                confirm=True,
            )

        self.assertEqual(passphrase, "password corretta")

    def test_reversible_result_exposes_a_contextual_three_step_flow_only_in_that_mode(self) -> None:
        """The routine result must not teach the extra reversible workflow."""
        self._prepare_output()
        self.assertTrue(self.window.reversible_flow_frame.isHidden())

        self.window.clear_all(force=True)
        self.window.mode_radios["reversible"].setChecked(True)
        self._prepare_output()

        self.assertFalse(self.window.reversible_flow_frame.isHidden())
        self.assertIn("file di ripristino", self.window.reversible_step_save_label.text().lower())
        self.assertIn("l’ia", self.window.reversible_step_share_label.text().lower())
        self.assertIn("risposta dell’ia", self.window.reversible_step_restore_label.text().lower())
        self.assertEqual(self.window._primary_state()[0], "save_map")
        self.assertEqual(self.window.primary_button.text(), "Salva il file di ripristino")

    def test_reversible_copy_is_blocked_until_the_restoration_file_is_saved(self) -> None:
        self.window.mode_radios["reversible"].setChecked(True)
        self._prepare_output()
        protected_text = self.window.output_text.toPlainText()

        self.window.copy_output()

        self.assertFalse(self.window._result_used)
        self.assertEqual(self.window.output_text.toPlainText(), protected_text)
        self.assertIn("file di ripristino", self.window.statusBar().currentMessage().lower())
        self.assertFalse(self.window.copy_output_action.isEnabled())
        self.assertIn("dopo aver salvato", self.window.copy_button.accessibleDescription().lower())
        self.assertIn("dopo aver salvato", self.window.copy_output_action.statusTip().lower())
        self.assertEqual(self.window._primary_state()[0], "save_map")

    def test_reversible_primary_action_follows_save_share_restore_sequence(self) -> None:
        self.window.mode_radios["reversible"].setChecked(True)
        self._prepare_output()

        def mark_map_as_saved() -> None:
            self.window._reversible_map_saved = True
            self.window._sync_action_state()

        with mock.patch.object(self.window, "save_reversible_map", side_effect=mark_map_as_saved) as save_map:
            self.window._primary_action()

        save_map.assert_called_once_with()
        self.assertEqual(self.window._primary_state()[0], "copy")
        self.assertEqual(self.window.primary_button.text(), "Copia per l’IA")
        self.assertTrue(self.window.copy_output_action.isEnabled())

        def mark_protected_copy_as_shared() -> None:
            self.window._reversible_copy_copied = True
            self.window._result_used = True
            self.window._sync_action_state()

        with mock.patch.object(self.window, "copy_output", side_effect=mark_protected_copy_as_shared) as copy_output:
            self.window._primary_action()

        copy_output.assert_called_once_with()
        self.assertEqual(self.window._primary_state()[0], "restore")
        self.assertEqual(self.window.primary_button.text(), "Incolla la risposta dell’IA")
        self.assertIn("risposta dell’ia", self.window.reversible_step_restore_label.text().lower())
        self.assertFalse(self.window.reversible_restore_inline_button.isHidden())
        self.assertEqual(
            self.window.reversible_restore_inline_button.text(),
            "Incolla qui",
        )

        with mock.patch.object(self.window, "restore_with_reversible_map") as restore:
            self.window.reversible_restore_inline_button.click()
            self.window._primary_action()

        self.assertEqual(restore.call_count, 2)

    def test_same_session_restore_uses_the_saved_mapping_without_reopening_the_file(self) -> None:
        self.window.mode_radios["reversible"].setChecked(True)
        self._prepare_output()
        self.window._reversible_map_saved = True
        self.window._restore_mapping = self.window.reversible_mapping
        self.window._sync_action_state()
        self.window.copy_output()
        protected = self.window.output_text.toPlainText()
        original = self.window.input_text.toPlainText()
        response = f"Risposta dell’IA: {protected}"

        def complete_dialog(dialog: QDialog) -> int:
            editor = dialog.findChild(QTextEdit, "RestoreResponseEditor")
            self.assertEqual(dialog.windowTitle(), "Incolla qui la risposta dell’IA")
            self.assertIn("Incolla qui l’intera risposta", editor.placeholderText())
            restore = next(
                button for button in dialog.findChildren(QPushButton) if button.text() == "Ripristina i dati"
            )
            editor.setPlainText(response)
            self.assertTrue(restore.isEnabled())
            restore.click()
            return dialog.result()

        with mock.patch("privacy_guardian.app.QDialog.exec", new=complete_dialog), mock.patch(
            "privacy_guardian.app.QFileDialog.getOpenFileName"
        ) as open_file:
            self.window.restore_with_reversible_map()

        open_file.assert_not_called()
        self.assertIn("Mario Rossi", self.window.output_text.toPlainText())
        self.assertIn("mario.rossi@example.com", self.window.output_text.toPlainText())
        self.assertEqual(self.window._primary_state()[0], "save_restored")
        self.assertEqual(self.window.result_title_label.text(), "Dati personali ripristinati")
        self.assertEqual(self.window.input_text.toPlainText(), original)
        self.assertEqual(self.window.ai_response_text.toPlainText(), response)
        self.assertIs(self.window.source_view_stack.currentWidget(), self.window.ai_response_text)
        self.assertEqual(self.window.input_panel_title.text(), "Risposta dell’IA")
        self.assertEqual(self.window.output_panel_title.text(), "Testo ricostruito")
        self.assertFalse(self.window.source_view_toggle.isHidden())
        self.assertEqual(self.window.source_view_toggle.text(), "Mostra originale")
        self.assertFalse(self.window.output_preview_notice.isHidden())
        self.assertEqual(self.window.output_preview_notice.objectName(), "RestoredOutputNotice")
        self.assertIn("dati personali", self.window.output_preview_notice.text().lower())
        self.assertTrue(self.window.input_text.isReadOnly())
        self.assertTrue(self.window.ai_response_text.isReadOnly())
        self.assertFalse(self.window.output_text.isReadOnly())

    def test_restored_comparison_can_toggle_original_without_changing_any_text(self) -> None:
        original = "Mario Rossi scrive a mario@example.com."
        response = "Gentile <PERSONA_1>, Mario Rossi è in copia con <EMAIL_1>."
        restored = "Gentile Mario Rossi, Mario Rossi è in copia con mario@example.com."
        self.window.input_text.setPlainText(original)
        self.window._set_restored_comparison_source(response)
        self.window._set_output_text(restored)
        self.window._mark_output_generated(
            "reversible",
            total_findings=2,
            included_findings=2,
            kind="restored",
        )

        self.assertEqual(self.window.source_view_stack.count(), 2)
        self.assertIs(self.window.source_view_stack.currentWidget(), self.window.ai_response_text)
        self.assertEqual(
            self.window.source_view_notice.text(),
            "Prima del ripristino locale · testo incollato senza modifiche",
        )
        self.assertNotIn("protett", self.window.source_view_notice.text().lower())

        self.window.source_view_toggle.click()

        self.assertIs(self.window.source_view_stack.currentWidget(), self.window.input_text)
        self.assertEqual(self.window.input_panel_title.text(), "Documento originale")
        self.assertEqual(self.window.source_view_toggle.text(), "Mostra risposta IA")
        self.assertEqual(self.window.input_text.toPlainText(), original)
        self.assertEqual(self.window.ai_response_text.toPlainText(), response)
        self.assertEqual(self.window.output_text.toPlainText(), restored)
        self.assertTrue(self.window.input_text.isReadOnly())

        self.window.source_view_toggle.click()

        self.assertIs(self.window.source_view_stack.currentWidget(), self.window.ai_response_text)
        self.assertEqual(self.window.input_panel_title.text(), "Risposta dell’IA")
        self.assertEqual(self.window.source_view_toggle.text(), "Mostra originale")

    def test_partial_restore_reports_placeholders_missing_from_the_ai_response(self) -> None:
        self.window._restore_mapping = (
            ReversibleMapEntry("<PERSONA_1>", "PERSON", "Mario Rossi"),
            ReversibleMapEntry("<EMAIL_1>", "EMAIL", "mario@example.com"),
        )

        def complete_dialog(dialog: QDialog) -> int:
            editor = dialog.findChild(QTextEdit, "RestoreResponseEditor")
            restore = next(
                button for button in dialog.findChildren(QPushButton) if button.text() == "Ripristina i dati"
            )
            editor.setPlainText("Gentile <PERSONA_1>, la pratica è pronta.")
            self.assertTrue(restore.isEnabled())
            restore.click()
            return dialog.result()

        with mock.patch("privacy_guardian.app.QDialog.exec", new=complete_dialog):
            self.window.restore_with_reversible_map()

        self.assertEqual(self.window.output_text.toPlainText(), "Gentile Mario Rossi, la pratica è pronta.")
        self.assertIn("Ripristinati 1 di 2", self.window.result_metric_label.text())
        self.assertIn("non è stato reinserito", self.window.report_label.text())
        self.assertIn("1 elemento non compariva", self.window.statusBar().currentMessage())

    def test_placeholder_validation_rejects_tokens_from_another_restoration_file(self) -> None:
        mapping = (
            ReversibleMapEntry("<PERSONA_1>", "PERSON", "Mario Rossi"),
            ReversibleMapEntry("<EMAIL_1>", "EMAIL", "mario@example.com"),
        )

        matched, missing, unknown = self.window._reversible_placeholder_status(
            "Gentile <PERSONA_1>, chiama <TELEFONO_1>.",
            mapping,
        )

        self.assertEqual(matched, 1)
        self.assertEqual(missing, 1)
        self.assertEqual(unknown, ("<TELEFONO_1>",))

    def test_reversible_docx_keeps_copy_primary_and_protected_file_secondary(self) -> None:
        self.window.mode_radios["reversible"].setChecked(True)
        self._prepare_output()
        self.window.anonymized_document = AnonymizedDocument(
            filename="documento_anonimizzato.docx",
            data=b"PK",
            text=self.window.output_text.toPlainText(),
            findings=[],
        )
        self.window.output_text_dirty = False
        self.window._reversible_map_saved = True
        self.window._restore_mapping = self.window.reversible_mapping
        self.window._sync_action_state()

        self.assertEqual(self.window._primary_state()[0], "copy")
        self.assertEqual(self.window.primary_button.text(), "Copia per l’IA")
        self.assertFalse(self.window.save_button.isHidden())
        self.assertEqual(self.window.save_button.text(), "Salva copia protetta")

    def test_restore_error_preserves_the_pasted_response(self) -> None:
        """A bad password or map must not make the user paste the AI answer again."""
        response = "Gentile <PERSONA_1>, la richiesta è stata elaborata."
        previous_output = "La copia protetta corrente non deve essere sostituita."
        self.window.output_text.setPlainText(previous_output)
        self.window.reversible_mapping = ()

        def exercise_dialog(dialog: QDialog) -> int:
            editor = dialog.findChild(QTextEdit, "RestoreResponseEditor")
            password = dialog.findChild(QLineEdit, "RestorePasswordEdit")
            buttons = dialog.findChildren(QPushButton)
            choose_file = next(button for button in buttons if button.accessibleName() == "Scegli il File di ripristino")
            restore = next(button for button in buttons if button.text() == "Ripristina i dati")
            editor.setPlainText(response)
            choose_file.click()
            password.setText("password errata")
            restore.click()
            self.assertEqual(editor.toPlainText(), response)
            self.assertEqual(dialog.result(), QDialog.Rejected)
            return QDialog.Rejected

        with mock.patch(
            "privacy_guardian.app.QFileDialog.getOpenFileName",
            return_value=("/tmp/mappa.omissis-map", ""),
        ), mock.patch("privacy_guardian.app.QDialog.exec", new=exercise_dialog), mock.patch(
            "privacy_guardian.app.read_encrypted_mapping",
            side_effect=ReversibleMapError("Password non valida"),
        ):
            self.window.restore_with_reversible_map()

        self.assertEqual(self.window.output_text.toPlainText(), previous_output)
        self.assertIn("password", self.window.statusBar().currentMessage().lower())
        self.assertEqual(self.window._restored_ai_response, "")
        self.assertIs(self.window.source_view_stack.currentWidget(), self.window.input_text)
        self.assertTrue(self.window.source_view_toggle.isHidden())
        self.assertTrue(self.window.output_preview_notice.isHidden())

    def test_restored_text_can_only_be_saved_and_is_never_offered_to_ai(self) -> None:
        self.window.mode_radios["reversible"].setChecked(True)
        self.window._set_output_text("Gentile Mario Rossi, la richiesta è stata elaborata.")
        self.window.reversible_mapping = ()
        self.window._mark_output_generated(
            "reversible",
            total_findings=0,
            included_findings=0,
            kind="restored",
        )

        self.assertEqual(self.window._primary_state()[0], "save_restored")
        self.assertEqual(self.window.primary_button.text(), "Salva testo ricostruito")
        self.assertFalse(self.window.copy_output_action.isEnabled())
        self.assertNotIn("l’ia", self.window.primary_button.text().lower())

        with mock.patch.object(self.window, "save_output") as save_output:
            self.window._primary_action()

        save_output.assert_called_once_with()

    def test_unsaved_restored_text_is_named_as_personal_data_before_discard(self) -> None:
        self.window._set_output_text("Gentile Mario Rossi, la richiesta è stata elaborata.")
        self.window.reversible_mapping = ()
        self.window._mark_output_generated(
            "reversible",
            total_findings=1,
            included_findings=1,
            kind="restored",
        )

        items = self.window._discardable_work_items(
            include_source=False,
            include_review=False,
            include_map=False,
        )

        self.assertEqual(
            items,
            ["testo ricostruito con dati personali non salvato"],
        )

    def test_reversible_menu_uses_the_guided_restore_action_and_hides_advanced_map_loading(self) -> None:
        self.assertEqual(
            self.window.restore_map_action.text(),
            "Incolla la risposta dell’IA e ripristina...",
        )
        self.assertNotIn(self.window.load_map_action, self.window.tools_menu.actions())
        self.assertIn(self.window.save_map_action, self.window.tools_menu.actions())

    def test_cancelling_restoration_file_save_keeps_sharing_blocked(self) -> None:
        self.window.mode_radios["reversible"].setChecked(True)
        self._prepare_output()
        mapping = self.window.reversible_mapping

        with mock.patch(
            "privacy_guardian.app.QFileDialog.getSaveFileName",
            return_value=("", ""),
        ):
            saved = self.window.save_reversible_map()

        self.assertFalse(saved)
        self.assertEqual(self.window.reversible_mapping, mapping)
        self.assertFalse(self.window._reversible_map_saved)
        self.assertFalse(self.window._reversible_copy_copied)
        self.assertEqual(self.window._primary_state()[0], "save_map")
        self.assertFalse(self.window.copy_output_action.isEnabled())

    def test_saving_protected_copy_does_not_unlock_the_restore_step(self) -> None:
        self.window.mode_radios["reversible"].setChecked(True)
        self._prepare_output()
        self.window._reversible_map_saved = True
        self.window._restore_mapping = self.window.reversible_mapping
        self.window._sync_action_state()

        with mock.patch(
            "privacy_guardian.app.QFileDialog.getSaveFileName",
            return_value=("/tmp/copia-protetta.txt", ""),
        ), mock.patch("privacy_guardian.app.atomic_write_text") as write_text:
            self.window.save_output()

        write_text.assert_called_once()
        self.assertFalse(self.window._result_used)
        self.assertFalse(self.window._reversible_copy_copied)
        self.assertEqual(self.window._primary_state()[0], "copy")
        self.assertEqual(self.window.primary_button.text(), "Copia per l’IA")

    def test_reopening_with_file_and_password_restores_response_whitespace(self) -> None:
        mapping = (ReversibleMapEntry("<PERSONA_1>", "PERSON", "Mario Rossi"),)
        response = "  Gentile <PERSONA_1>,\nla pratica è pronta.  \n"
        self.window.output_text.setPlainText("Copia protetta precedente")
        self.window.reversible_mapping = ()
        self.window._restore_mapping = ()
        self.window._reversible_map_path = None

        def complete_dialog(dialog: QDialog) -> int:
            editor = dialog.findChild(QTextEdit, "RestoreResponseEditor")
            password = dialog.findChild(QLineEdit, "RestorePasswordEdit")
            choose_file = next(
                button
                for button in dialog.findChildren(QPushButton)
                if button.accessibleName() == "Scegli il File di ripristino"
            )
            restore = next(
                button for button in dialog.findChildren(QPushButton) if button.text() == "Ripristina i dati"
            )
            editor.setPlainText(response)
            choose_file.click()
            password.setText("password corretta")
            self.assertTrue(restore.isEnabled())
            restore.click()
            return dialog.result()

        with mock.patch(
            "privacy_guardian.app.QFileDialog.getOpenFileName",
            return_value=("/tmp/pratica-ripristino.omissis-map", ""),
        ), mock.patch(
            "privacy_guardian.app.read_encrypted_mapping",
            return_value=mapping,
        ) as read_mapping, mock.patch("privacy_guardian.app.QDialog.exec", new=complete_dialog):
            self.window.restore_with_reversible_map()

        read_mapping.assert_called_once_with(Path("/tmp/pratica-ripristino.omissis-map"), "password corretta")
        self.assertEqual(
            self.window.output_text.toPlainText(),
            "  Gentile Mario Rossi,\nla pratica è pronta.  \n",
        )
        self.assertEqual(self.window.ai_response_text.toPlainText(), response)
        self.assertIs(self.window.source_view_stack.currentWidget(), self.window.ai_response_text)
        self.assertEqual(self.window._primary_state()[0], "save_restored")

    def test_new_session_clears_the_restored_comparison(self) -> None:
        self.window.input_text.setPlainText("Mario Rossi")
        self.window._set_restored_comparison_source("Gentile <PERSONA_1>")
        self.window._set_output_text("Gentile Mario Rossi")
        self.window._mark_output_generated(
            "reversible",
            total_findings=1,
            included_findings=1,
            kind="restored",
        )
        self.assertTrue(self.window._restored_comparison_active())

        self.window.clear_all(force=True)

        self.assertEqual(self.window._restored_ai_response, "")
        self.assertEqual(self.window.ai_response_text.toPlainText(), "")
        self.assertIs(self.window.source_view_stack.currentWidget(), self.window.input_text)
        self.assertEqual(self.window.input_panel_title.text(), "Testo originale")
        self.assertTrue(self.window.source_view_toggle.isHidden())
        self.assertTrue(self.window.source_view_notice.isHidden())
        self.assertTrue(self.window.output_preview_notice.isHidden())

    def test_unsupported_document_formats_show_accessible_reversible_fallback(self) -> None:
        for extension in (".md", ".csv", ".pdf"):
            with self.subTest(extension=extension):
                self.window.clear_all(force=True)
                self.window.mode_radios["reversible"].setChecked(True)
                self.window._apply_loaded_document(
                    LoadedDocument(
                        path=Path(f"documento{extension}"),
                        text="Mario Rossi",
                        extension=extension,
                    )
                )

                self.assertEqual(self.window._selected_mode(), "maximum")
                self.assertFalse(self.window.mode_radios["reversible"].isEnabled())
                self.assertIn("testo incollato, TXT e DOCX", self.window.mode_cards["reversible"].toolTip())
                self.assertIn(
                    "testo incollato, TXT o DOCX",
                    self.window.mode_radios["reversible"].accessibleDescription(),
                )
                self.assertFalse(self.window.mode_descriptions["reversible"].isHidden())
                self.assertIn("Massima protezione", self.window.statusBar().currentMessage())

    def test_reversible_flow_compacts_without_hiding_step_titles_or_statuses(self) -> None:
        self.window.mode_radios["reversible"].setChecked(True)
        self._prepare_output()
        self.window.show()
        self.window.resize(960, 640)
        QApplication.processEvents()

        self.assertTrue(self.window.reversible_flow_intro.isHidden())
        self.assertTrue(all(label.isHidden() for label in self.window.reversible_step_description_labels))
        self.assertTrue(all(not label.isHidden() for label in (
            self.window.reversible_step_save_label,
            self.window.reversible_step_share_label,
            self.window.reversible_step_restore_label,
            *self.window.reversible_step_state_labels,
        )))

        self.window._reversible_map_saved = True
        self.window._restore_mapping = self.window.reversible_mapping
        self.window._sync_action_state()
        self.window.copy_output()
        QApplication.processEvents()

        self.assertFalse(self.window.reversible_restore_inline_button.isHidden())
        self.assertTrue(self.window.reversible_restore_inline_button.isEnabled())
        self.assertEqual(
            self.window.reversible_restore_inline_button.accessibleName(),
            "Incolla qui la risposta dell’IA",
        )
        self.assertEqual(
            self.window.reversible_restore_inline_button.visibleRegion().boundingRect(),
            self.window.reversible_restore_inline_button.rect(),
        )
        self.assertTrue(self.window.result_subtitle_label.isHidden())
        self.assertTrue(self.window.reversible_step_state_labels[2].isHidden())

        self.window.resize(1180, 800)
        QApplication.processEvents()
        self.assertFalse(self.window.reversible_flow_intro.isHidden())
        self.assertTrue(all(not label.isHidden() for label in self.window.reversible_step_description_labels))

    def test_default_restoration_filename_names_document_or_pasted_text(self) -> None:
        self.window.loaded_document = LoadedDocument(
            path=Path("pratica.rossi.docx"),
            text="Mario Rossi",
            extension=".docx",
        )
        self.assertEqual(self.window._default_map_filename(), "pratica.rossi-ripristino.omissis-map")

        self.window.loaded_document = None
        self.assertEqual(self.window._default_map_filename(), "omissis-ripristino.omissis-map")

    def test_restored_text_saves_as_plain_text_with_a_dedicated_name(self) -> None:
        restored = "Gentile Mario Rossi, la pratica è pronta."
        self.window._set_output_text(restored)
        self.window.reversible_mapping = ()
        self.window._mark_output_generated(
            "reversible",
            total_findings=1,
            included_findings=1,
            kind="restored",
        )

        with mock.patch(
            "privacy_guardian.app.QFileDialog.getSaveFileName",
            return_value=("/tmp/testo-ricostruito.txt", ""),
        ) as save_dialog, mock.patch("privacy_guardian.app.atomic_write_text") as write_text, mock.patch(
            "privacy_guardian.app.atomic_write_bytes"
        ) as write_bytes:
            self.window.save_output()

        self.assertEqual(save_dialog.call_args.args[1], "Salva testo ricostruito")
        self.assertIn("testo_ricostruito.txt", save_dialog.call_args.args[2])
        write_text.assert_called_once_with(Path("/tmp/testo-ricostruito.txt"), restored)
        write_bytes.assert_not_called()

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
        _clear_ui_settings()
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
        self.assertEqual(highlight.background().color().alpha(), 112)
        self.assertEqual(highlight.foreground().color().name(), "#ffffff")

        self.window._selected_finding_index = 0
        self.window._highlight_findings()
        selected_selection = self.window.input_text.extraSelections()[0]
        selected_highlight = selected_selection.format
        self.assertEqual(selected_highlight.background().color().alpha(), 160)
        self.assertEqual(selected_highlight.foreground().color().name(), "#ffffff")

    def test_entity_highlights_remain_readable_on_paper(self) -> None:
        text = "Mario Rossi"
        self._set_synthetic_findings(text, [Finding("PERSON", 0, len(text), 0.95)])
        self.window.document_paper_button.click()

        self.window._highlight_findings()
        highlight_selection = self.window.input_text.extraSelections()[0]
        highlight = highlight_selection.format
        self.assertEqual(highlight.background().color().alpha(), 96)
        self.assertEqual(highlight.foreground().color().name(), "#10161a")

        self.window._selected_finding_index = 0
        self.window._highlight_findings()
        selected_selection = self.window.input_text.extraSelections()[0]
        selected = selected_selection.format
        self.assertEqual(selected.background().color().alpha(), 176)
        self.assertEqual(selected.foreground().color().name(), "#10161a")

    def test_preview_highlights_every_replacement_and_strengthens_the_selected_one(self) -> None:
        text = "Mario Rossi scrive a mario.rossi@example.com."
        email_start = text.index("mario.rossi@example.com")
        findings = [
            Finding("PERSON", 0, len("Mario Rossi"), 0.95),
            Finding(
                "EMAIL_ADDRESS",
                email_start,
                email_start + len("mario.rossi@example.com"),
                0.98,
            ),
        ]
        self._set_synthetic_findings(text, findings)
        self.window._refresh_analysis_preview()

        initial_selections = self.window.output_text.extraSelections()
        self.assertEqual(len(initial_selections), 2)
        self.assertEqual(
            {selection.cursor.selectedText() for selection in initial_selections},
            {"M. R.", "<EMAIL>"},
        )
        self.assertEqual(
            {selection.format.background().color().alpha() for selection in initial_selections},
            {112},
        )

        self.window.findings_panel.finding_selected.emit(1)

        preview_selections = self.window.output_text.extraSelections()
        self.assertEqual(len(preview_selections), 2)
        selected_email = next(
            selection
            for selection in preview_selections
            if selection.cursor.selectedText() == "<EMAIL>"
        )
        selected_person = next(
            selection
            for selection in preview_selections
            if selection.cursor.selectedText() == "M. R."
        )
        self.assertEqual(selected_email.format.background().color().alpha(), 160)
        self.assertEqual(selected_person.format.background().color().alpha(), 112)
        self.assertEqual(
            selected_email.format.foreground().color().name(),
            "#ffffff",
        )

        self.window._handle_selection_cleared()
        cleared_selections = self.window.output_text.extraSelections()
        self.assertEqual(len(cleared_selections), 2)
        self.assertEqual(
            {selection.format.background().color().alpha() for selection in cleared_selections},
            {112},
        )

    def test_reversible_preview_highlights_the_matching_numbered_placeholder(self) -> None:
        self.window.mode_radios["reversible"].setChecked(True)
        text = "Mario Rossi incontra Mario Rossi."
        second_start = text.rindex("Mario Rossi")
        findings = [
            Finding("PERSON", 0, len("Mario Rossi"), 0.95),
            Finding("PERSON", second_start, second_start + len("Mario Rossi"), 0.95),
        ]
        self._set_synthetic_findings(text, findings)
        self.window._refresh_analysis_preview()

        initial_selections = self.window.output_text.extraSelections()
        self.assertEqual(len(initial_selections), 2)
        self.assertEqual(
            [selection.cursor.selectedText() for selection in initial_selections],
            ["<PERSONA_1>", "<PERSONA_1>"],
        )

        self.window.findings_panel.finding_selected.emit(1)

        preview_selections = self.window.output_text.extraSelections()
        self.assertEqual(len(preview_selections), 2)
        self.assertEqual(
            sorted(selection.format.background().color().alpha() for selection in preview_selections),
            [112, 160],
        )

        self.window._set_output_text("Risultato finale")
        self.assertEqual(self.window.output_text.extraSelections(), [])

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

        text = "La sede di Potenza e la filiale di Potenza sono chiuse."
        self.window.input_text.setPlainText(text)
        first = text.index("Potenza")
        cursor = self.window.input_text.textCursor()
        cursor.setPosition(first)
        cursor.setPosition(first + len("Potenza"), QTextCursor.KeepAnchor)
        self.window.input_text.setTextCursor(cursor)

        with mock.patch.object(_EntityTypeDialog, "exec", return_value=QDialog.Accepted), mock.patch.object(
            _EntityTypeDialog, "selected_label", return_value="ente territoriale"
        ):
            self.window.add_manual_finding()

        potenza_findings = [
            f for f in self.window.findings if text[f.start : f.end] == "Potenza" and f.source == "manual"
        ]
        self.assertEqual(len(potenza_findings), 2)

        self.window.anonymize_text()
        self.assertNotIn("Potenza", self.window.output_text.toPlainText())

    def test_manual_selection_expands_across_case_variants(self) -> None:
        from PySide6.QtGui import QTextCursor

        text = "STELLANTIS, Stellantis e stellantis."
        self.window.input_text.setPlainText(text)
        first = text.index("STELLANTIS")
        cursor = self.window.input_text.textCursor()
        cursor.setPosition(first)
        cursor.setPosition(first + len("STELLANTIS"), QTextCursor.KeepAnchor)
        self.window.input_text.setTextCursor(cursor)

        with mock.patch.object(_EntityTypeDialog, "exec", return_value=QDialog.Accepted), mock.patch.object(
            _EntityTypeDialog, "selected_label", return_value="organizzazione"
        ):
            self.window.add_manual_finding()

        manual_values = [
            text[finding.start : finding.end]
            for finding in self.window.findings
            if finding.source == "manual"
            and text[finding.start : finding.end].casefold() == "stellantis"
        ]
        self.assertEqual(manual_values, ["STELLANTIS", "Stellantis", "stellantis"])

        self.window.anonymize_text()
        self.assertNotIn("stellantis", self.window.output_text.toPlainText().casefold())

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
