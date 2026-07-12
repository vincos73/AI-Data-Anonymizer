"""Headless smoke tests for the desktop (PySide6) MainWindow.

These tests exercise the Dark Pro rail/toolbar redesign without needing a real
display: they force QT_QPA_PLATFORM=offscreen before importing PySide6, and
skip cleanly if PySide6 or a usable Qt platform plugin isn't available.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from privacy_guardian.app import MainWindow
    from privacy_guardian.document_service import LoadedDocument
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
        self.window.close()
        self.window.deleteLater()

    def test_default_selected_mode_is_maximum(self) -> None:
        self.assertEqual(self.window._selected_mode(), "maximum")

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


@unittest.skipIf(_QT_IMPORT_ERROR is not None, f"PySide6/Qt not usable in this environment: {_QT_IMPORT_ERROR}")
class FindingsPanelIntegrationTests(unittest.TestCase):
    """Batch B: findings_panel.py + its bidirectional sync with the editor."""

    def setUp(self) -> None:
        _make_app()
        self.window = MainWindow()

    def tearDown(self) -> None:
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
        self.assertEqual(self.window.primary_button.text(), "Anonimizza 3 dati")

        email_index = next(i for i, f in enumerate(findings) if f.entity_type == "EMAIL_ADDRESS")
        item = self.window.findings_panel._index_to_item[email_index]
        item.setCheckState(Qt.Unchecked)

        self.assertEqual(len(self.window._checked_findings()), 2)
        self.assertEqual(self.window.primary_button.text(), "Anonimizza 2 dati")

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

    def test_extract_document_as_text_reenables_manual_filtering(self) -> None:
        loaded = LoadedDocument(
            path=Path("relazione.docx"),
            text="Mario Rossi lavora presso Acme S.p.A.",
            extension=".docx",
        )
        self.window.loaded_document = loaded
        self.window.input_text.setPlainText(loaded.text)
        self.assertFalse(self.window._manual_filter_supported())

        self.window._extract_document_as_text()

        self.assertIsNone(self.window.loaded_document)
        self.assertTrue(self.window._manual_filter_supported())


if __name__ == "__main__":
    unittest.main()
