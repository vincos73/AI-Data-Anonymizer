from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
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
from privacy_guardian.document_service import AnonymizedDocument, LoadedDocument, anonymize_loaded_document, load_document
from privacy_guardian.models import Finding
from privacy_guardian.privacy_engine import PrivacyEngine
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

        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("Incolla qui il testo da controllare...")

        self.output_text = QTextEdit()
        self.output_text.setPlaceholderText("Il testo anonimizzato apparira qui.")

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Tipo", "Intervallo", "Confidenza", "Origine"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        self.version_label = QLabel(f"v{__version__}")
        self.version_label.setObjectName("VersionPill")

        load_button = QPushButton("01  Carica documento")
        load_button.clicked.connect(self.open_file)
        load_button.setObjectName("WorkflowButton")

        analyze_button = QPushButton("02  Analizza")
        analyze_button.clicked.connect(self.analyze_text)
        analyze_button.setObjectName("WorkflowButton")

        anonymize_button = QPushButton("03  Anonimizza")
        anonymize_button.clicked.connect(self.anonymize_text)
        anonymize_button.setObjectName("PrimaryButton")

        copy_button = QPushButton("Copia")
        copy_button.clicked.connect(self.copy_output)
        copy_button.setObjectName("SecondaryButton")

        save_button = QPushButton("Salva")
        save_button.clicked.connect(self.save_output)
        save_button.setObjectName("SecondaryButton")

        clear_button = QPushButton("Pulisci")
        clear_button.clicked.connect(self.clear_all)
        clear_button.setObjectName("SecondaryButton")

        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        for button in (load_button, analyze_button, anonymize_button):
            button_row.addWidget(button)
        button_row.addStretch(1)
        separator = QFrame()
        separator.setObjectName("CommandSeparator")
        separator.setFrameShape(QFrame.VLine)
        separator.setFixedWidth(1)
        button_row.addWidget(separator)
        for button in (copy_button, save_button, clear_button):
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
        layout.addWidget(text_splitter, 4)
        layout.addWidget(findings_title)
        layout.addWidget(self.table, 2)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
        self.setStyleSheet(APP_STYLE)
        self._build_menu()

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
            "Documenti supportati (*.txt *.md *.csv *.doc *.docx *.pdf);;Tutti i file (*.*)",
        )
        if not filename:
            return
        try:
            self.loaded_document = load_document(filename)
        except Exception as exc:
            self.statusBar().showMessage(f"Non riesco a caricare il documento: {exc}", 6000)
            return

        self.anonymized_document = None
        self.input_text.setPlainText(self.loaded_document.text)
        self.output_text.clear()
        self.statusBar().showMessage("Documento caricato. Puoi analizzarlo o anonimizzarlo.", 4000)

    def analyze_text(self) -> None:
        text = self.input_text.toPlainText()
        self.findings = self.engine.analyze(text)
        self._fill_table()
        self._highlight_findings()
        self.statusBar().showMessage(f"Elementi rilevati: {len(self.findings)}.", 4000)

    def anonymize_text(self) -> None:
        if self.loaded_document and self.input_text.toPlainText() == self.loaded_document.text:
            self.anonymized_document = anonymize_loaded_document(self.loaded_document, self.engine)
            self.findings = self.anonymized_document.findings
            self.output_text.setPlainText(self.anonymized_document.text)
            self._fill_table()
            self._highlight_findings()
            self.statusBar().showMessage(
                f"Documento pronto: {self.anonymized_document.filename}. Elementi rilevati: {len(self.findings)}.",
                5000,
            )
            return

        self.loaded_document = None
        self.anonymized_document = None
        self.analyze_text()
        text = self.input_text.toPlainText()
        self.output_text.setPlainText(self.engine.anonymize(text, self.findings))

    def copy_output(self) -> None:
        QApplication.clipboard().setText(self.output_text.toPlainText())
        self.statusBar().showMessage("Risultato copiato negli appunti.", 3000)

    def save_output(self) -> None:
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

    def _fill_table(self) -> None:
        self.table.setRowCount(len(self.findings))
        for row, finding in enumerate(self.findings):
            values = [
                finding.entity_type,
                finding.text_range,
                f"{finding.score:.2f}",
                finding.source,
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


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
