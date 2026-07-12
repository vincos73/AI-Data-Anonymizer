"""Headless smoke tests for the desktop (PySide6) MainWindow.

These tests exercise the Dark Pro rail/toolbar redesign without needing a real
display: they force QT_QPA_PLATFORM=offscreen before importing PySide6, and
skip cleanly if PySide6 or a usable Qt platform plugin isn't available.
"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication

    from privacy_guardian.app import MainWindow

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


if __name__ == "__main__":
    unittest.main()
