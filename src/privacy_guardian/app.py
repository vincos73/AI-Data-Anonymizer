from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from privacy_guardian import __version__
from privacy_guardian.document_service import (
    LEGACY_DOC_SUPPORTED,
    AnonymizedDocument,
    LoadedDocument,
    anonymize_loaded_document,
    load_document,
)
from privacy_guardian.models import AnonymizationMode, Finding, validate_anonymization_mode
from privacy_guardian.privacy_engine import PrivacyEngine
from privacy_guardian.reporting import entity_label, mode_note, report_text, source_label
from privacy_guardian.styles import APP_STYLE


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.engine = PrivacyEngine()
        self.findings: list[Finding] = []
        self.loaded_document: LoadedDocument | None = None
        self.anonymized_document: AnonymizedDocument | None = None

        self.setWindowTitle("AI Data Anonymizer")
        self.resize(1160, 760)
        self.setMinimumSize(QSize(940, 640))
        self.setAcceptDrops(True)

        self.input_text = QTextEdit()
        self.input_text.setAcceptDrops(False)
        self.input_text.setPlaceholderText("Incolla qui il testo da controllare oppure carica un documento.")
        self.input_text.textChanged.connect(self._sync_action_state)

        self.output_text = QTextEdit()
        self.output_text.setAcceptDrops(False)
        self.output_text.setPlaceholderText("Il testo anonimizzato apparirà qui.")
        self.output_text.textChanged.connect(self._sync_action_state)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Tipo", "Valore trovato", "Intervallo", "Confidenza", "Origine"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        self.version_label = QLabel(f"v{__version__}")
        self.version_label.setObjectName("VersionPill")

        self.mode_select = QComboBox()
        self.mode_select.addItem("Massima protezione (consigliata)", "maximum")
        self.mode_select.addItem("Standard (più leggibile)", "standard")
        self.mode_select.setObjectName("ModeSelect")
        self.mode_select.currentIndexChanged.connect(self._update_mode_notice)

        self.document_label = QLabel("Nessun documento caricato. Puoi incollare testo o trascinare un file nella finestra.")
        self.document_label.setObjectName("DocumentNotice")
        self.document_label.setWordWrap(True)

        self.report_label = QLabel()
        self.report_label.setObjectName("ReportNotice")
        self.report_label.setWordWrap(True)

        self.load_button = QPushButton("01  Carica o trascina file")
        self.load_button.clicked.connect(self.open_file)
        self.load_button.setObjectName("WorkflowButton")

        self.analyze_button = QPushButton("02  Analizza dati")
        self.analyze_button.clicked.connect(self.analyze_text)
        self.analyze_button.setObjectName("WorkflowButton")

        self.anonymize_button = QPushButton("03  Anonimizza")
        self.anonymize_button.clicked.connect(self.anonymize_text)
        self.anonymize_button.setObjectName("PrimaryButton")

        self.copy_button = QPushButton("Copia risultato")
        self.copy_button.clicked.connect(self.copy_output)
        self.copy_button.setObjectName("SecondaryButton")

        self.save_button = QPushButton("Salva risultato")
        self.save_button.clicked.connect(self.save_output)
        self.save_button.setObjectName("SecondaryButton")

        self.clear_button = QPushButton("Pulisci")
        self.clear_button.clicked.connect(self.clear_all)
        self.clear_button.setObjectName("SecondaryButton")

        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        for button in (self.load_button, self.analyze_button, self.anonymize_button):
            button_row.addWidget(button)
        button_row.addWidget(self.mode_select)
        button_row.addStretch(1)
        separator = QFrame()
        separator.setObjectName("CommandSeparator")
        separator.setFrameShape(QFrame.VLine)
        separator.setFixedWidth(1)
        button_row.addWidget(separator)
        for button in (self.copy_button, self.save_button, self.clear_button):
            button_row.addWidget(button)

        text_splitter = QSplitter(Qt.Horizontal)
        text_splitter.addWidget(self._panel("Testo originale", self.input_text))
        text_splitter.addWidget(self._panel("Testo anonimizzato", self.output_text))
        text_splitter.setSizes([540, 540])

        title = QLabel("AI DATA ANONYMIZER")
        title.setObjectName("AppTitle")
        byline = QLabel("by vincos")
        byline.setObjectName("Byline")

        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(0, 0, 0, 0)
        brand_row.setSpacing(10)
        brand_row.addWidget(title, 0, Qt.AlignBaseline)
        brand_row.addWidget(byline, 0, Qt.AlignBaseline)
        brand_row.addStretch(1)

        header = QHBoxLayout()
        header.addLayout(brand_row, 1)
        header.addWidget(self.version_label, 0, Qt.AlignTop)

        findings_title = QLabel("Dati rilevati")
        findings_title.setObjectName("SectionTitle")

        layout = QVBoxLayout()
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)
        layout.addLayout(header)
        layout.addLayout(button_row)
        layout.addWidget(self.document_label)
        layout.addWidget(self.report_label)
        layout.addWidget(text_splitter, 4)
        layout.addWidget(findings_title)
        layout.addWidget(self.table, 2)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
        self.setStyleSheet(APP_STYLE)
        self._build_menu()
        self._update_mode_notice()
        self._sync_action_state()

    def _panel(self, title: str, widget: QTextEdit) -> QWidget:
        label = QLabel(title)
        label.setObjectName("SectionTitle")
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(label)
        layout.addWidget(widget)
        panel = QFrame()
        panel.setObjectName("Panel")
        panel.setLayout(layout)
        return panel

    def _build_menu(self) -> None:
        open_action = QAction("Carica documento...", self)
        open_action.triggered.connect(self.open_file)

        quit_action = QAction("Esci", self)
        quit_action.triggered.connect(self.close)

        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction(open_action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)

    def open_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Carica documento",
            str(Path.home()),
            self._document_filter(),
        )
        if not filename:
            return
        self._load_document_from_path(filename)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._first_local_drop_path(event):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        path = self._first_local_drop_path(event)
        if path is None:
            super().dropEvent(event)
            return
        self._load_document_from_path(path)
        event.acceptProposedAction()

    def _load_document_from_path(self, filename: str | Path) -> None:
        try:
            self.loaded_document = load_document(filename)
        except Exception as exc:
            self.statusBar().showMessage(self._friendly_error_message(exc), 9000)
            return

        self.anonymized_document = None
        self.input_text.setPlainText(self.loaded_document.text)
        self.output_text.clear()
        self._update_mode_notice()
        self.document_label.setText(f"Documento caricato: {self.loaded_document.path.name}")
        self.statusBar().showMessage("Documento caricato. Massima protezione è pronta per ChatGPT e altri strumenti IA.", 5000)
        self._sync_action_state()

    def analyze_text(self) -> None:
        text = self.input_text.toPlainText()
        if not text.strip():
            self.statusBar().showMessage("Incolla un testo o carica un documento prima di analizzare.", 5000)
            return
        self.findings = self.engine.analyze(text, self._selected_mode())
        self._fill_table()
        self._highlight_findings()
        self._update_report()
        self.statusBar().showMessage(f"Elementi rilevati: {len(self.findings)}.", 4000)

    def anonymize_text(self) -> None:
        mode = self._selected_mode()
        if not self.input_text.toPlainText().strip():
            self.statusBar().showMessage("Incolla un testo o carica un documento prima di anonimizzare.", 5000)
            return
        if self.loaded_document and self.input_text.toPlainText() == self.loaded_document.text:
            self.anonymized_document = anonymize_loaded_document(self.loaded_document, self.engine, mode)
            self.findings = self.anonymized_document.findings
            self.output_text.setPlainText(self.anonymized_document.text)
            self._fill_table()
            self._highlight_findings()
            self._update_report()
            self.statusBar().showMessage(
                f"Documento pronto: {self.anonymized_document.filename}. Elementi rilevati: {len(self.findings)}.",
                5000,
            )
            return

        self.loaded_document = None
        self.anonymized_document = None
        self.analyze_text()
        text = self.input_text.toPlainText()
        self.output_text.setPlainText(self.engine.anonymize(text, self.findings, mode))
        self._update_report()

    def copy_output(self) -> None:
        if not self.output_text.toPlainText().strip():
            self.statusBar().showMessage("Anonimizza prima un testo o un documento.", 4000)
            return
        QApplication.clipboard().setText(self.output_text.toPlainText())
        self.statusBar().showMessage("Risultato copiato negli appunti.", 3000)

    def save_output(self) -> None:
        if not self.output_text.toPlainText().strip() and not self.anonymized_document:
            self.statusBar().showMessage("Anonimizza prima un testo o un documento.", 4000)
            return
        default_name = self.anonymized_document.filename if self.anonymized_document else "testo_anonimizzato.txt"
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Salva versione anonimizzata",
            str(Path.home() / default_name),
            "Documenti (*.txt *.docx *.pdf);;Tutti i file (*.*)",
        )
        if not filename:
            return

        if self.anonymized_document:
            Path(filename).write_bytes(self.anonymized_document.data)
        else:
            Path(filename).write_text(self.output_text.toPlainText(), encoding="utf-8")

        self.statusBar().showMessage(f"Salvato: {filename}", 4000)

    def clear_all(self) -> None:
        self.input_text.clear()
        self.output_text.clear()
        self.table.setRowCount(0)
        self.findings = []
        self.loaded_document = None
        self.anonymized_document = None
        self.document_label.setText("Nessun documento caricato. Puoi incollare testo o trascinare un file nella finestra.")
        self._update_mode_notice()
        self._sync_action_state()

    def _fill_table(self) -> None:
        source_text = self.input_text.toPlainText()
        self.table.setRowCount(len(self.findings))
        for row, finding in enumerate(self.findings):
            values = [
                entity_label(finding.entity_type),
                self._finding_preview(source_text, finding),
                finding.text_range,
                f"{finding.score:.2f}",
                source_label(finding.source),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() ^ Qt.ItemIsEditable)
                self.table.setItem(row, col, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _highlight_findings(self) -> None:
        cursor = self.input_text.textCursor()
        cursor.select(QTextCursor.Document)
        cursor.setCharFormat(QTextCharFormat())

        highlight = QTextCharFormat()
        highlight.setBackground(Qt.GlobalColor.yellow)

        for finding in self.findings:
            cursor = self.input_text.textCursor()
            cursor.setPosition(finding.start)
            cursor.setPosition(finding.end, QTextCursor.KeepAnchor)
            cursor.setCharFormat(highlight)

    def _document_filter(self) -> str:
        extensions = "*.txt *.md *.csv *.docx *.pdf"
        if LEGACY_DOC_SUPPORTED:
            extensions = "*.txt *.md *.csv *.doc *.docx *.pdf"
        return f"Documenti supportati ({extensions});;Tutti i file (*.*)"

    def _selected_mode(self) -> AnonymizationMode:
        return validate_anonymization_mode(str(self.mode_select.currentData()))

    def _update_mode_notice(self, *args) -> None:
        self.report_label.setText(mode_note(self._selected_mode()))

    def _update_report(self) -> None:
        self.report_label.setText(report_text(self.findings, self._selected_mode()))

    def _friendly_error_message(self, exc: Exception) -> str:
        message = str(exc)
        if "OCR" in message or "testo estraibile" in message or "scansionate" in message:
            return f"{message} Questo evita di considerare sicuro un PDF che l'app non può leggere."
        return f"Non riesco a caricare il documento: {message}"

    def _first_local_drop_path(self, event: QDragEnterEvent | QDropEvent) -> Path | None:
        mime_data = event.mimeData()
        if not mime_data.hasUrls():
            return None
        for url in mime_data.urls():
            if url.isLocalFile():
                return Path(url.toLocalFile())
        return None

    def _finding_preview(self, source_text: str, finding: Finding) -> str:
        preview = source_text[finding.start : finding.end].replace("\n", " ").strip()
        if len(preview) > 80:
            return f"{preview[:77]}..."
        return preview

    def _sync_action_state(self) -> None:
        input_has_text = bool(self.input_text.toPlainText().strip())
        output_has_text = bool(self.output_text.toPlainText().strip())
        has_anything = input_has_text or output_has_text or self.loaded_document is not None
        self.analyze_button.setEnabled(input_has_text)
        self.anonymize_button.setEnabled(input_has_text)
        self.copy_button.setEnabled(output_has_text)
        self.save_button.setEnabled(output_has_text or self.anonymized_document is not None)
        self.clear_button.setEnabled(has_anything)


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
