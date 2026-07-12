from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QSignalBlocker, QSize, Qt
from PySide6.QtGui import (
    QAction,
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QFontDatabase,
    QMouseEvent,
    QPainter,
    QPixmap,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from privacy_guardian import __version__
from privacy_guardian.activity_log import (
    ActivityAction,
    build_activity_entry,
    export_activity_log_csv,
    load_activity_entries,
    record_activity,
)
from privacy_guardian.document_service import (
    LEGACY_DOC_SUPPORTED,
    AnonymizedDocument,
    LoadedDocument,
    anonymize_loaded_document,
    load_document,
)
from privacy_guardian.entity_categories import entity_color
from privacy_guardian.findings_panel import FindingsPanel
from privacy_guardian.models import AnonymizationMode, Finding, validate_anonymization_mode
from privacy_guardian.privacy_engine import PrivacyEngine
from privacy_guardian.reversible import (
    MAP_EXTENSION,
    ReversibleMapEntry,
    ReversibleMapError,
    read_encrypted_mapping,
    restore_text,
    write_encrypted_mapping,
)
from privacy_guardian.reporting import ENTITY_LABELS, entity_label, mode_note, report_text
from privacy_guardian.styles import APP_STYLE


PROJECT_REPO_URL = "https://github.com/vincos73/AI-Data-Anonymizer"
PROJECT_RELEASES_URL = f"{PROJECT_REPO_URL}/releases"
PROJECT_SECURITY_URL = f"{PROJECT_REPO_URL}/blob/main/SICUREZZA.md"


def _asset_path(filename: str) -> Path:
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        bundle_temp = getattr(sys, "_MEIPASS", "")
        if bundle_temp:
            candidates.append(Path(bundle_temp) / "privacy_guardian" / "assets" / filename)
        candidates.append(
            Path(sys.executable).resolve().parents[1] / "Resources" / "privacy_guardian" / "assets" / filename
        )
    candidates.append(Path(__file__).with_name("assets") / filename)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _tinted_pixmap(pixmap: QPixmap, color: QColor) -> QPixmap:
    """Recolor a pixmap's opaque pixels to a flat color, keeping its alpha mask.

    The bundled wordmark SVG renders dark text meant for a light background; on the
    Dark Pro theme it would be nearly invisible, so we re-tint it (e.g. to white)
    while preserving its silhouette.
    """
    if pixmap.isNull():
        return pixmap
    tinted = QPixmap(pixmap.size())
    tinted.setDevicePixelRatio(pixmap.devicePixelRatio())
    tinted.fill(Qt.transparent)
    painter = QPainter(tinted)
    painter.drawPixmap(0, 0, pixmap)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(tinted.rect(), color)
    painter.end()
    return tinted


def _load_app_fonts() -> None:
    """Register the bundled IBM Plex fonts with Qt's font database."""
    fonts_dir = _asset_path("fonts")
    if not fonts_dir.is_dir():
        return
    for font_file in sorted(fonts_dir.glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(_asset_path(f"fonts/{font_file.name}")))


class _ClickableCard(QFrame):
    """A QFrame that forwards left-clicks to an embedded checkable widget (e.g. a radio card)."""

    def __init__(self, target: QRadioButton) -> None:
        super().__init__()
        self._target = target

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton and self._target.isEnabled():
            self._target.setChecked(True)
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.engine = PrivacyEngine()
        self.findings: list[Finding] = []
        self.findings_stale = True
        self._findings_source_text: str | None = ""
        self._findings_mode: AnonymizationMode | None = None
        self.loaded_document: LoadedDocument | None = None
        self.anonymized_document: AnonymizedDocument | None = None
        self.document_text_dirty = False
        self.output_text_dirty = False
        self._loading_document_text = False
        self._updating_output_text = False
        self.reversible_mapping: tuple[ReversibleMapEntry, ...] = ()
        self.loaded_reversible_entries: tuple[ReversibleMapEntry, ...] = ()
        self._selected_finding_index: int | None = None

        self.setWindowTitle("OMISSIS")
        self.resize(1160, 760)
        self.setMinimumSize(QSize(1120, 660))
        self.setAcceptDrops(True)

        self.input_text = QTextEdit()
        self.input_text.setAcceptDrops(False)
        self.input_text.setPlaceholderText("Incolla qui il testo da controllare oppure carica un documento.")
        self.input_text.textChanged.connect(self._handle_input_text_changed)
        self.input_text.installEventFilter(self)
        self.input_text.viewport().installEventFilter(self)

        self.output_text = QTextEdit()
        self.output_text.setAcceptDrops(False)
        self.output_text.setPlaceholderText("Il testo anonimizzato apparirà qui.")
        self.output_text.textChanged.connect(self._handle_output_text_changed)

        self.findings_panel = FindingsPanel()
        self.findings_panel.finding_selected.connect(self._scroll_editor_to_finding)
        self.findings_panel.inclusion_changed.connect(self._handle_inclusion_changed)
        self.findings_panel.selection_cleared.connect(self._handle_selection_cleared)
        self.findings_panel.extract_as_text_requested.connect(self._extract_document_as_text)

        self.version_label = QLabel(f"v{__version__}")
        self.version_label.setObjectName("VersionPill")

        self.logo_mark_label = QLabel()
        self.logo_mark_label.setObjectName("BrandMark")
        logo_mark_pixmap = QPixmap(str(_asset_path("omissis-logo.svg")))
        if not logo_mark_pixmap.isNull():
            self.logo_mark_label.setPixmap(logo_mark_pixmap.scaledToHeight(30, Qt.SmoothTransformation))
        self.logo_mark_label.setFixedHeight(32)

        self.logo_label = QLabel("OMISSIS")
        self.logo_label.setObjectName("BrandLogo")
        logo_pixmap = QPixmap(str(_asset_path("omissis-logotype.svg")))
        if not logo_pixmap.isNull():
            self.logo_label.setText("")
            tinted_logo = _tinted_pixmap(logo_pixmap, QColor("#FFFFFF"))
            self.logo_label.setPixmap(tinted_logo.scaledToHeight(30, Qt.SmoothTransformation))
        self.logo_label.setFixedHeight(32)

        byline = QLabel("by vincos")
        byline.setObjectName("Byline")

        self.local_notice = QLabel("Elaborazione locale · i dati restano sul dispositivo")
        self.local_notice.setObjectName("LocalNotice")
        self.local_notice.setWordWrap(True)

        self.document_label = QLabel("Nessun documento caricato. Puoi incollare testo o trascinare un file nella finestra.")
        self.document_label.setObjectName("DocumentNotice")
        self.document_label.setWordWrap(True)

        # Rail hint shown only when the optional local NER model is not installed.
        self.ner_notice = QLabel("Installa il modello — vedi README")
        self.ner_notice.setObjectName("NerHint")
        self.ner_notice.setWordWrap(True)
        self.ner_notice.setVisible(not self.engine.ner_active)

        # Kept as internal state (not added to the layout): callers update it via
        # _update_report()/_update_mode_notice() and it can be surfaced again later.
        self.report_label = QLabel()
        self.report_label.setObjectName("ReportNotice")
        self.report_label.setWordWrap(True)

        self.load_button = QPushButton("Carica")
        self.load_button.clicked.connect(self.open_file)
        self.load_button.setObjectName("SecondaryButton")
        self.load_button.setToolTip("Carica un documento oppure trascinalo nella finestra.")

        self.copy_button = QPushButton("Copia")
        self.copy_button.clicked.connect(self.copy_output)
        self.copy_button.setObjectName("SecondaryButton")

        self.save_button = QPushButton("Salva")
        self.save_button.clicked.connect(self.save_output)
        self.save_button.setObjectName("SecondaryButton")

        self.clear_button = QPushButton("Pulisci")
        self.clear_button.clicked.connect(self.clear_all)
        self.clear_button.setObjectName("SecondaryButton")

        self.add_selection_button = QPushButton("Aggiungi selezione")
        self.add_selection_button.clicked.connect(self.add_manual_finding)
        self.add_selection_button.setObjectName("SecondaryButton")
        self.add_selection_button.setToolTip(
            "Seleziona una parola o frase nel pannello «Testo originale» non rilevata "
            "automaticamente, poi clicca qui per aggiungerla manualmente."
        )

        self.primary_button = QPushButton("Analizza dati")
        self.primary_button.setObjectName("PrimaryButton")
        self.primary_button.clicked.connect(self._primary_action)

        # ---- Rail: brand block ----
        brand_top_row = QHBoxLayout()
        brand_top_row.setSpacing(8)
        brand_top_row.addWidget(self.logo_mark_label, 0, Qt.AlignVCenter)
        brand_top_row.addWidget(self.logo_label, 0, Qt.AlignVCenter)
        brand_top_row.addStretch(1)

        brand_column = QVBoxLayout()
        brand_column.setSpacing(2)
        brand_column.addLayout(brand_top_row)
        brand_column.addWidget(byline)

        # ---- Rail: vertical workflow stepper ----
        self.step_rows: list[QFrame] = []
        step_definitions = [
            "Carica documento",
            "Analizza dati",
            "Rivedi selezione",
            "Anonimizza",
        ]
        stepper_column = QVBoxLayout()
        stepper_column.setSpacing(6)
        for index, title in enumerate(step_definitions, start=1):
            row = self._build_step_row(index, title)
            self.step_rows.append(row)
            stepper_column.addWidget(row)

        # ---- Rail: protection mode radio cards ----
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_radios: dict[str, QRadioButton] = {}
        self.mode_cards: dict[str, QFrame] = {}
        self.mode_descriptions: dict[str, QLabel] = {}
        mode_options: list[tuple[AnonymizationMode, str]] = [
            ("maximum", "Massima protezione (consigliata)"),
            ("reversible", "Reversibile con mappa locale"),
            ("standard", "Standard (più leggibile)"),
        ]
        protection_column = QVBoxLayout()
        protection_column.setSpacing(8)
        for mode, title in mode_options:
            radio = QRadioButton(title)
            radio.setObjectName("ModeCardRadio")

            description = QLabel(mode_note(mode))
            description.setObjectName("ModeCardDescription")
            description.setWordWrap(True)

            card = _ClickableCard(radio)
            card_layout = QVBoxLayout()
            card_layout.setContentsMargins(12, 10, 12, 10)
            card_layout.setSpacing(6)
            card_layout.addWidget(radio)
            card_layout.addWidget(description)
            card.setLayout(card_layout)

            self.mode_group.addButton(radio)
            self.mode_radios[mode] = radio
            self.mode_cards[mode] = card
            self.mode_descriptions[mode] = description
            protection_column.addWidget(card)

        self.mode_radios["maximum"].setChecked(True)
        for radio in self.mode_radios.values():
            radio.toggled.connect(self._handle_mode_toggled)

        # ---- Rail: recognition status ----
        rules_status = QLabel("Regole ✓")
        rules_status.setObjectName("StatusOk")

        self.ner_status_label = QLabel("NER attivo" if self.engine.ner_active else "NER non attivo")
        self.ner_status_label.setObjectName("StatusOk" if self.engine.ner_active else "StatusWarning")

        recognition_column = QVBoxLayout()
        recognition_column.setSpacing(4)
        recognition_column.addWidget(rules_status)
        recognition_column.addWidget(self.ner_status_label)
        recognition_column.addWidget(self.ner_notice)

        rail_content_layout = QVBoxLayout()
        rail_content_layout.setContentsMargins(20, 20, 20, 16)
        rail_content_layout.setSpacing(10)
        rail_content_layout.addLayout(brand_column)
        rail_content_layout.addSpacing(8)
        rail_content_layout.addWidget(self._rail_section_label("FLUSSO"))
        rail_content_layout.addLayout(stepper_column)
        rail_content_layout.addWidget(self._rail_section_label("PROTEZIONE"))
        rail_content_layout.addLayout(protection_column)
        rail_content_layout.addWidget(self._rail_section_label("RICONOSCIMENTO"))
        rail_content_layout.addLayout(recognition_column)
        rail_content_layout.addStretch(1)
        rail_content_layout.addWidget(self.local_notice)
        rail_content_layout.addWidget(self.version_label)

        rail_content = QWidget()
        rail_content.setLayout(rail_content_layout)

        rail_scroll = QScrollArea()
        rail_scroll.setObjectName("RailScroll")
        rail_scroll.setWidget(rail_content)
        rail_scroll.setWidgetResizable(True)
        rail_scroll.setFrameShape(QFrame.NoFrame)
        rail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        rail_outer_layout = QVBoxLayout()
        rail_outer_layout.setContentsMargins(0, 0, 0, 0)
        rail_outer_layout.addWidget(rail_scroll)

        rail = QFrame()
        rail.setObjectName("Rail")
        rail.setFixedWidth(288)
        rail.setLayout(rail_outer_layout)

        # ---- Main area: document toolbar ----
        toolbar_row = QHBoxLayout()
        toolbar_row.setContentsMargins(16, 0, 16, 0)
        toolbar_row.setSpacing(8)
        toolbar_row.addWidget(self.load_button, 0, Qt.AlignVCenter)
        toolbar_row.addWidget(self.document_label, 1, Qt.AlignVCenter)
        toolbar_row.addWidget(self.copy_button, 0, Qt.AlignVCenter)
        toolbar_row.addWidget(self.save_button, 0, Qt.AlignVCenter)
        toolbar_row.addWidget(self.clear_button, 0, Qt.AlignVCenter)
        toolbar_row.addWidget(self.add_selection_button, 0, Qt.AlignVCenter)
        toolbar_row.addWidget(self.primary_button, 0, Qt.AlignVCenter)

        document_toolbar = QFrame()
        document_toolbar.setObjectName("DocumentToolbar")
        document_toolbar.setMinimumHeight(56)
        document_toolbar.setLayout(toolbar_row)

        text_splitter = QSplitter(Qt.Horizontal)
        text_splitter.setHandleWidth(14)
        text_splitter.addWidget(self._panel("Testo originale", self.input_text))
        text_splitter.addWidget(self._panel("Testo anonimizzato", self.output_text))
        text_splitter.setSizes([540, 540])

        self.workspace_splitter = QSplitter(Qt.Vertical)
        self.workspace_splitter.setObjectName("WorkspaceSplitter")
        self.workspace_splitter.setHandleWidth(10)
        self.workspace_splitter.addWidget(text_splitter)
        self.workspace_splitter.addWidget(self.findings_panel)
        self.workspace_splitter.setStretchFactor(0, 4)
        self.workspace_splitter.setStretchFactor(1, 2)
        self.workspace_splitter.setCollapsible(0, False)
        self.workspace_splitter.setCollapsible(1, False)
        self.workspace_splitter.setSizes([560, 280])

        main_area_layout = QVBoxLayout()
        main_area_layout.setContentsMargins(22, 18, 22, 16)
        main_area_layout.setSpacing(14)
        main_area_layout.addWidget(document_toolbar)
        main_area_layout.addWidget(self.workspace_splitter, 1)

        main_area = QWidget()
        main_area.setLayout(main_area_layout)

        root_layout = QHBoxLayout()
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(rail, 0)
        root_layout.addWidget(main_area, 1)

        container = QWidget()
        container.setLayout(root_layout)
        self.setCentralWidget(container)
        self.setStyleSheet(APP_STYLE)
        self._build_menu()
        self._update_mode_notice()
        self._sync_action_state()

    def _rail_section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("RailSectionLabel")
        return label

    def _build_step_row(self, index: int, title: str) -> QFrame:
        row = QFrame()
        row.setObjectName("StepRowPending")

        dot = QLabel(str(index))
        dot.setObjectName("StepDot")
        dot.setAlignment(Qt.AlignCenter)
        dot.setFixedSize(20, 20)

        title_label = QLabel(title)
        title_label.setObjectName("StepTitle")
        title_label.setWordWrap(True)

        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(10, 10, 10, 10)
        row_layout.setSpacing(10)
        row_layout.addWidget(dot, 0, Qt.AlignTop)
        row_layout.addWidget(title_label, 1)
        row.setLayout(row_layout)
        return row

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

        activity_action = QAction("Registro attività", self)
        activity_action.triggered.connect(self.show_activity_log_dialog)

        self.save_map_action = QAction("Salva mappa reversibile...", self)
        self.save_map_action.triggered.connect(self.save_reversible_map)

        self.load_map_action = QAction("Carica mappa reversibile...", self)
        self.load_map_action.triggered.connect(self.load_reversible_map)

        self.restore_map_action = QAction("Ricostruisci testo con mappa...", self)
        self.restore_map_action.triggered.connect(self.restore_with_reversible_map)

        tools_menu = self.menuBar().addMenu("Strumenti")
        tools_menu.addAction(activity_action)
        tools_menu.addSeparator()
        tools_menu.addAction(self.load_map_action)
        tools_menu.addAction(self.save_map_action)
        tools_menu.addAction(self.restore_map_action)

        security_action = QAction("Sicurezza e privacy", self)
        security_action.triggered.connect(self.show_security_dialog)

        about_action = QAction("Informazioni su OMISSIS", self)
        about_action.triggered.connect(self.show_about_dialog)

        help_menu = self.menuBar().addMenu("Aiuto")
        help_menu.addAction(security_action)
        help_menu.addSeparator()
        help_menu.addAction(about_action)

    def show_security_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setObjectName("InfoDialog")
        dialog.setWindowTitle("Sicurezza e privacy")
        dialog.setModal(True)
        dialog.setMinimumWidth(560)

        title = QLabel("Sicurezza e privacy")
        title.setObjectName("DialogTitle")

        details = QLabel(
            "OMISSIS lavora in locale: l'app desktop non invia documenti, testo o dati rilevati "
            "a OpenAI, Google, Anthropic, servizi OCR, analytics o altre API esterne.<br><br>"
            "<b>Registro attività:</b> salva solo metadati locali come data, modalità, conteggi, "
            "estensione, dimensione e hash dei file. Non salva testo originale, testo anonimizzato "
            "o valori trovati.<br><br>"
            "<b>PDF:</b> i PDF con testo selezionabile vengono esportati come pagine rasterizzate "
            "con oscuramenti permanenti. I PDF scansionati possono essere letti con Tesseract OCR locale "
            "quando è installato; non vengono usati servizi OCR esterni.<br><br>"
            f'<a style="color:#4FB8E7;" href="{PROJECT_SECURITY_URL}">Apri la pagina sicurezza su GitHub</a>'
        )
        details.setObjectName("DialogDetails")
        details.setTextFormat(Qt.RichText)
        details.setTextInteractionFlags(Qt.TextBrowserInteraction)
        details.setOpenExternalLinks(True)
        details.setWordWrap(True)

        close_button = QPushButton("Chiudi")
        close_button.setObjectName("SecondaryButton")
        close_button.clicked.connect(dialog.accept)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(close_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(14)
        layout.addWidget(title)
        layout.addWidget(details)
        layout.addLayout(button_row)
        dialog.setLayout(layout)
        dialog.setStyleSheet(APP_STYLE)
        dialog.exec()

    def show_activity_log_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setObjectName("InfoDialog")
        dialog.setWindowTitle("Registro attività")
        dialog.setModal(True)
        dialog.resize(920, 520)

        title = QLabel("Registro attività locale")
        title.setObjectName("DialogTitle")

        description = QLabel(
            "Il registro resta sul dispositivo e contiene solo metadati: nessun testo originale, "
            "nessun testo anonimizzato, nessun valore rilevato."
        )
        description.setObjectName("DialogDetails")
        description.setWordWrap(True)

        entries = list(reversed(load_activity_entries(limit=300)))
        table = QTableWidget(len(entries), 7)
        table.setHorizontalHeaderLabels(["Data", "Operazione", "Origine", "Modalità", "Dati", "Tipi", "Hash file"])
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        for row, entry in enumerate(entries):
            values = [
                self._activity_timestamp(entry),
                str(entry.get("action_label") or entry.get("action") or ""),
                self._activity_source_text(entry),
                str(entry.get("mode_label") or entry.get("mode") or ""),
                str(entry.get("total_findings") or 0),
                self._activity_counts_text(entry.get("finding_counts")),
                self._short_hash(entry.get("source_sha256")),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() ^ Qt.ItemIsEditable)
                table.setItem(row, col, item)

        empty_notice = QLabel("Nessuna attività registrata.") if not entries else QLabel("")
        empty_notice.setObjectName("DialogDetails")

        export_button = QPushButton("Esporta CSV")
        export_button.setObjectName("SecondaryButton")

        def export_log() -> None:
            filename, _ = QFileDialog.getSaveFileName(
                dialog,
                "Esporta registro attività",
                str(Path.home() / "omissis-registro-attivita.csv"),
                "CSV (*.csv)",
            )
            if not filename:
                return
            export_activity_log_csv(filename)
            self.statusBar().showMessage(f"Registro esportato: {filename}", 5000)

        export_button.clicked.connect(export_log)
        export_button.setEnabled(bool(entries))

        close_button = QPushButton("Chiudi")
        close_button.setObjectName("SecondaryButton")
        close_button.clicked.connect(dialog.accept)

        button_row = QHBoxLayout()
        button_row.addWidget(export_button)
        button_row.addStretch(1)
        button_row.addWidget(close_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(description)
        if not entries:
            layout.addWidget(empty_notice)
        layout.addWidget(table, 1)
        layout.addLayout(button_row)
        dialog.setLayout(layout)
        dialog.setStyleSheet(APP_STYLE)
        dialog.exec()

    def show_about_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setObjectName("InfoDialog")
        dialog.setWindowTitle("Informazioni su OMISSIS")
        dialog.setModal(True)
        dialog.setMinimumWidth(420)

        logo = QLabel("OMISSIS")
        logo.setObjectName("BrandLogo")
        logo_pixmap = QPixmap(str(_asset_path("omissis-logotype.svg")))
        if not logo_pixmap.isNull():
            logo.setText("")
            tinted_logo = _tinted_pixmap(logo_pixmap, QColor("#FFFFFF"))
            logo.setPixmap(tinted_logo.scaledToHeight(34, Qt.SmoothTransformation))

        details = QLabel(
            f"<b>Versione:</b> {__version__}<br>"
            f"<b>Build:</b> {__version__}<br>"
            "<b>Autore:</b> Vincenzo Cosenza aka Vincos<br>"
            '<b>Sito web:</b> <a style="color:#4FB8E7;" href="https://vincos.it">vincos.it</a><br>'
            f'<b>Repository:</b> <a style="color:#4FB8E7;" href="{PROJECT_REPO_URL}">GitHub</a><br>'
            f'<b>Nuove versioni:</b> <a style="color:#4FB8E7;" href="{PROJECT_RELEASES_URL}">pagina Releases</a><br><br>'
            "Anonimizzatore locale per documenti italiani."
        )
        details.setObjectName("AboutDetails")
        details.setTextFormat(Qt.RichText)
        details.setTextInteractionFlags(Qt.TextBrowserInteraction)
        details.setOpenExternalLinks(True)
        details.setWordWrap(True)

        close_button = QPushButton("Chiudi")
        close_button.setObjectName("SecondaryButton")
        close_button.clicked.connect(dialog.accept)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(close_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(16)
        layout.addWidget(logo)
        layout.addWidget(details)
        layout.addLayout(button_row)
        dialog.setLayout(layout)
        dialog.setStyleSheet(APP_STYLE)
        dialog.exec()

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

    def eventFilter(self, obj: QWidget, event) -> bool:  # noqa: ANN001
        if obj is self.input_text.viewport() and event.type() == QEvent.MouseButtonRelease:
            if event.button() == Qt.LeftButton and not self.input_text.textCursor().hasSelection():
                position = self.input_text.cursorForPosition(event.pos()).position()
                index = self._finding_at_position(position)
                if index is not None:
                    self._selected_finding_index = index
                    self.findings_panel.select_finding(index)
                else:
                    self._selected_finding_index = None
                self._highlight_findings()
        elif obj is self.input_text and event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            self._selected_finding_index = None
            self._highlight_findings()
        return super().eventFilter(obj, event)

    def _load_document_from_path(self, filename: str | Path) -> None:
        try:
            self.loaded_document = load_document(filename)
        except Exception as exc:
            self.statusBar().showMessage(self._friendly_error_message(exc), 9000)
            return

        self.anonymized_document = None
        self.reversible_mapping = ()
        self.document_text_dirty = False
        self.output_text_dirty = False
        self.findings = []
        self.findings_stale = True
        self._findings_source_text = None
        self._findings_mode = None
        self.findings_panel.clear()
        self._loading_document_text = True
        try:
            signal_blocker = QSignalBlocker(self.input_text)
            try:
                self.input_text.setPlainText(self.loaded_document.text)
            finally:
                del signal_blocker
        finally:
            self._loading_document_text = False
        self.output_text.clear()
        self.document_text_dirty = False
        self.output_text_dirty = False
        self._update_mode_notice()
        if self.loaded_document.extension == ".pdf":
            if self.loaded_document.ocr_pages:
                pages = ", ".join(str(page) for page in self.loaded_document.ocr_pages)
                self.document_label.setText(
                    f"PDF letto con OCR locale: {self.loaded_document.path.name} (pagine {pages}). "
                    "L'export creerà un PDF rasterizzato con oscuramenti permanenti."
                )
                self.statusBar().showMessage(
                    "PDF scansionato letto con OCR locale. Controlla sempre il risultato OCR prima di condividere. "
                    "Per questo formato la selezione manuale non è ancora supportata.",
                    8000,
                )
            else:
                self.document_label.setText(
                    f"PDF caricato: {self.loaded_document.path.name}. "
                    "L'export creerà un PDF rasterizzato con oscuramenti permanenti."
                )
                self.statusBar().showMessage(
                    "PDF caricato. L'anonimizzazione salverà una copia redatta non selezionabile. "
                    "Per questo formato la selezione manuale non è ancora supportata.",
                    7000,
                )
        elif self.loaded_document.extension in {".docx", ".doc"}:
            self.document_label.setText(f"Documento caricato: {self.loaded_document.path.name}")
            self.statusBar().showMessage(
                "Documento caricato. Per questo formato la selezione manuale non è ancora supportata: "
                "verrà anonimizzato tutto ciò che viene rilevato.",
                7000,
            )
        else:
            self.document_label.setText(f"Documento caricato: {self.loaded_document.path.name}")
            self.statusBar().showMessage(
                "Documento caricato. Massima protezione è pronta per ChatGPT e altri strumenti IA.",
                5000,
            )
        self._sync_action_state()

    def analyze_text(self) -> None:
        if not self._run_analysis():
            return
        self._record_activity("analysis")
        self.statusBar().showMessage(f"Elementi rilevati: {len(self.findings)}.", 4000)

    def _run_analysis(self) -> bool:
        text = self.input_text.toPlainText()
        if not text.strip():
            self.statusBar().showMessage("Incolla un testo o carica un documento prima di analizzare.", 5000)
            return False
        self.findings = self.engine.analyze(text, self._selected_mode())
        self.findings_stale = False
        self._findings_source_text = text
        self._findings_mode = self._selected_mode()
        self._fill_table()
        self._highlight_findings()
        self._update_report()
        # Extra selections don't mutate the document, so unlike the old setCharFormat-based
        # highlight, _highlight_findings() no longer re-triggers textChanged -> _sync_action_state().
        # Refresh explicitly so the step-aware primary button/label reflect the new findings.
        self._sync_action_state()
        return True

    def anonymize_text(self) -> None:
        mode = self._selected_mode()
        self.reversible_mapping = ()
        if not self.input_text.toPlainText().strip():
            self.statusBar().showMessage("Incolla un testo o carica un documento prima di anonimizzare.", 5000)
            return
        if self.loaded_document and not self.document_text_dirty:
            manual_filter_supported = self._manual_filter_supported()
            filtered_findings = (
                self._checked_findings() if self._findings_ready_for_filtering() else None
            )
            try:
                self.anonymized_document = anonymize_loaded_document(
                    self.loaded_document,
                    self.engine,
                    mode,
                    reversible_entries=self.loaded_reversible_entries,
                    findings=filtered_findings,
                )
            except Exception as exc:
                self.anonymized_document = None
                self.output_text.clear()
                self.statusBar().showMessage(self._friendly_processing_error_message(exc), 10000)
                self._sync_action_state()
                return
            self.findings = self.anonymized_document.findings
            self.findings_stale = False
            self._findings_source_text = self.input_text.toPlainText()
            self._findings_mode = mode
            self.reversible_mapping = self.anonymized_document.reversible_mapping
            self._set_output_text(self.anonymized_document.text)
            self._fill_table()
            self._highlight_findings()
            self._update_report()
            self._record_activity("anonymization", output_data=self.anonymized_document.data)
            unsupported_note = (
                " Per questo formato la selezione manuale non è ancora supportata." if not manual_filter_supported else ""
            )
            if self.reversible_mapping:
                self.statusBar().showMessage(
                    f"Documento pronto: {self.anonymized_document.filename}. "
                    f"Salva anche la mappa reversibile.{unsupported_note}",
                    7000,
                )
            else:
                self.statusBar().showMessage(
                    f"Documento pronto: {self.anonymized_document.filename}. "
                    f"Elementi rilevati: {len(self.findings)}.{unsupported_note}",
                    5000,
                )
            self._sync_action_state()
            return

        self.loaded_document = None
        self.anonymized_document = None
        self.document_text_dirty = False
        if self._findings_ready_for_filtering():
            findings = self._checked_findings()
        else:
            self._run_analysis()
            findings = list(self.findings)
        text = self.input_text.toPlainText()
        if mode == "reversible":
            reversible_result = self.engine.anonymize_reversible(
                text, findings, entries=self.loaded_reversible_entries
            )
            self.reversible_mapping = reversible_result.mapping
            self._set_output_text(reversible_result.text)
        else:
            self._set_output_text(self.engine.anonymize(text, findings, mode))
        self._update_report()
        self._record_activity("anonymization", output_data=self.output_text.toPlainText().encode("utf-8"))
        if self.reversible_mapping:
            self.statusBar().showMessage("Testo reversibile pronto. Salva la mappa locale prima di usare ChatGPT.", 7000)
        self._sync_action_state()

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
        use_document_binary = self.anonymized_document is not None and not self.output_text_dirty
        default_name = self.anonymized_document.filename if use_document_binary else "testo_anonimizzato.txt"
        expected_suffix = Path(default_name).suffix.lower() or ".txt"
        save_filters = {
            ".csv": "CSV (*.csv)",
            ".docx": "Documento Word (*.docx)",
            ".pdf": "PDF redatto (*.pdf)",
            ".txt": "File di testo (*.txt)",
        }
        save_filter = save_filters.get(expected_suffix, "Tutti i file (*.*)")
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Salva versione anonimizzata",
            str(Path.home() / default_name),
            save_filter,
        )
        if not filename:
            return

        target_path = Path(filename)
        if target_path.suffix:
            if target_path.suffix.lower() != expected_suffix:
                self.statusBar().showMessage(
                    f"Formato di salvataggio non supportato per questo risultato. Usa {expected_suffix}.",
                    7000,
                )
                return
        else:
            target_path = target_path.with_suffix(expected_suffix)

        output_pane_text = self.output_text.toPlainText()
        if use_document_binary and (expected_suffix not in {".txt", ".csv"} or not output_pane_text.strip()):
            target_path.write_bytes(self.anonymized_document.data)
        else:
            target_path.write_text(output_pane_text, encoding="utf-8")

        self._record_activity("save", output_path=target_path)
        self.statusBar().showMessage(f"Salvato: {target_path}", 4000)

    def save_reversible_map(self) -> None:
        if not self.reversible_mapping:
            self.statusBar().showMessage("Non c'è ancora una mappa reversibile da salvare.", 5000)
            return

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Salva mappa reversibile",
            str(Path.home() / self._default_map_filename()),
            "Mappa OMISSIS (*.omissis-map)",
        )
        if not filename:
            return
        target_path = Path(filename)
        if target_path.suffix.lower() != MAP_EXTENSION:
            target_path = target_path.with_suffix(MAP_EXTENSION)

        passphrase = self._ask_passphrase("Password mappa", "Scegli una password per cifrare la mappa:", confirm=True)
        if passphrase is None:
            return
        try:
            write_encrypted_mapping(target_path, self.reversible_mapping, passphrase)
        except ReversibleMapError as exc:
            self.statusBar().showMessage(str(exc), 7000)
            return

        self.statusBar().showMessage(f"Mappa reversibile salvata: {target_path}", 6000)

    def load_reversible_map(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Carica mappa reversibile",
            str(Path.home()),
            "Mappa OMISSIS (*.omissis-map);;Tutti i file (*.*)",
        )
        if not filename:
            return

        passphrase = self._ask_passphrase("Password mappa", "Inserisci la password della mappa:")
        if passphrase is None:
            return
        try:
            entries = read_encrypted_mapping(filename, passphrase)
        except ReversibleMapError as exc:
            self.statusBar().showMessage(str(exc), 8000)
            return

        self.loaded_reversible_entries = entries
        self.reversible_mapping = entries
        self._sync_action_state()
        self.statusBar().showMessage(
            f"Mappa reversibile caricata: {len(entries)} voci pronte per i prossimi documenti.", 7000
        )

    def restore_with_reversible_map(self) -> None:
        source_text = self.output_text.toPlainText().strip() or self.input_text.toPlainText().strip()
        if not source_text:
            self.statusBar().showMessage("Incolla nel risultato il testo da ricostruire, poi scegli la mappa.", 6000)
            return

        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Apri mappa reversibile",
            str(Path.home()),
            "Mappa OMISSIS (*.omissis-map);;Tutti i file (*.*)",
        )
        if not filename:
            return

        passphrase = self._ask_passphrase("Password mappa", "Inserisci la password della mappa:")
        if passphrase is None:
            return
        try:
            mapping = read_encrypted_mapping(filename, passphrase)
        except ReversibleMapError as exc:
            self.statusBar().showMessage(str(exc), 8000)
            return

        self.output_text.setPlainText(restore_text(source_text, mapping))
        self.statusBar().showMessage("Testo ricostruito localmente dalla mappa.", 5000)

    def clear_all(self) -> None:
        self.input_text.clear()
        self.output_text.clear()
        self.findings_panel.clear()
        self.findings = []
        self.findings_stale = True
        self._findings_source_text = ""
        self._findings_mode = None
        self._selected_finding_index = None
        self.loaded_document = None
        self.anonymized_document = None
        self.document_text_dirty = False
        self.output_text_dirty = False
        self.reversible_mapping = ()
        self.loaded_reversible_entries = ()
        self.document_label.setText("Nessun documento caricato. Puoi incollare testo o trascinare un file nella finestra.")
        self._update_mode_notice()
        self._sync_action_state()

    def add_manual_finding(self) -> None:
        cursor = self.input_text.textCursor()
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        if start == end:
            self.statusBar().showMessage(
                "Seleziona il testo da aggiungere nel pannello Testo originale prima di continuare.", 6000
            )
            return

        entity_by_label = {singular: entity_type for entity_type, (singular, _plural) in ENTITY_LABELS.items()}
        labels = sorted(entity_by_label)

        dialog = QInputDialog(self)
        dialog.setWindowTitle("Tipo di dato")
        dialog.setLabelText("Che tipo di dato è la selezione?")
        dialog.setComboBoxItems(labels)
        dialog.setStyleSheet(APP_STYLE)

        ok = dialog.exec() == QInputDialog.Accepted
        if not ok:
            return
        label = dialog.textValue()

        if not self._findings_ready_for_filtering() and not self._run_analysis():
            return

        finding = Finding(entity_by_label[label], start, end, 1.0, source="manual")
        self.findings = self.engine._recognizer.dedupe(self.findings + [finding])
        self.findings_stale = False
        self._findings_source_text = self.input_text.toPlainText()
        self._findings_mode = self._selected_mode()
        self._fill_table()
        self._highlight_findings()
        self._update_report()
        self._sync_action_state()
        self.statusBar().showMessage(f"Aggiunto manualmente: {entity_label(finding.entity_type)}.", 4000)

    def _fill_table(self) -> None:
        source_text = self.input_text.toPlainText()
        manual_filter_supported = self._manual_filter_supported()
        self.findings_panel.set_findings(self.findings, source_text, manual_filter_supported)
        self.findings_panel.set_unsupported_notice(
            not manual_filter_supported and self.loaded_document is not None
        )

    def _highlight_findings(self) -> None:
        selections = []
        for row, finding in enumerate(self.findings):
            if not self._is_row_checked(row):
                continue
            color = QColor(entity_color(finding.entity_type))
            color.setAlpha(72 if row == self._selected_finding_index else 40)
            char_format = QTextCharFormat()
            char_format.setBackground(color)
            cursor = QTextCursor(self.input_text.document())
            cursor.setPosition(finding.start)
            cursor.setPosition(finding.end, QTextCursor.KeepAnchor)
            selection = QTextEdit.ExtraSelection()
            selection.cursor = cursor
            selection.format = char_format
            selections.append(selection)
        self.input_text.setExtraSelections(selections)

    def _is_row_checked(self, row: int) -> bool:
        mask = self.findings_panel.included_mask()
        return row >= len(mask) or mask[row]

    def _checked_findings(self) -> list[Finding]:
        return [finding for row, finding in enumerate(self.findings) if self._is_row_checked(row)]

    def _findings_ready_for_filtering(self) -> bool:
        return (
            bool(self.findings)
            and len(self.findings_panel.included_mask()) == len(self.findings)
            and not self.findings_stale
            and self._findings_mode == self._selected_mode()
        )

    def _finding_at_position(self, position: int) -> int | None:
        candidates = [
            (finding.end - finding.start, index)
            for index, finding in enumerate(self.findings)
            if finding.start <= position < finding.end
        ]
        if not candidates:
            return None
        candidates.sort()
        return candidates[0][1]

    def _scroll_editor_to_finding(self, index: int) -> None:
        if not (0 <= index < len(self.findings)):
            return
        self._selected_finding_index = index
        cursor = self.input_text.textCursor()
        cursor.setPosition(self.findings[index].start)
        self.input_text.setTextCursor(cursor)
        self.input_text.ensureCursorVisible()
        self._highlight_findings()

    def _handle_inclusion_changed(self) -> None:
        self._sync_action_state()
        self._highlight_findings()

    def _handle_selection_cleared(self) -> None:
        self._selected_finding_index = None
        self._highlight_findings()

    def _extract_document_as_text(self) -> None:
        self.loaded_document = None
        self.anonymized_document = None
        self.document_text_dirty = False
        self.document_label.setText(
            "Contenuto estratto come testo: la selezione manuale è attiva, il salvataggio sarà in .txt."
        )
        if self.findings:
            self._fill_table()
        self._sync_action_state()
        self.statusBar().showMessage("Contenuto estratto come testo modificabile.", 4000)

    def _manual_filter_supported(self) -> bool:
        if self.loaded_document is None or self.document_text_dirty:
            return True
        return self.loaded_document.extension in {".txt", ".md", ".csv"}

    def _document_filter(self) -> str:
        extensions = "*.txt *.md *.csv *.docx *.pdf"
        if LEGACY_DOC_SUPPORTED:
            extensions = "*.txt *.md *.csv *.doc *.docx *.pdf"
        return f"Documenti supportati ({extensions});;Tutti i file (*.*)"

    def _selected_mode(self) -> AnonymizationMode:
        for mode, radio in self.mode_radios.items():
            if radio.isChecked():
                return validate_anonymization_mode(mode)
        return "maximum"

    def _handle_mode_toggled(self, checked: bool) -> None:
        if not checked:
            return
        self._update_mode_notice()
        self._sync_action_state()

    def _refresh_mode_cards(self) -> None:
        for mode, card in self.mode_cards.items():
            selected = self.mode_radios[mode].isChecked()
            object_name = "ModeCardSelected" if selected else "ModeCard"
            if card.objectName() != object_name:
                card.setObjectName(object_name)
                card.style().unpolish(card)
                card.style().polish(card)
            self.mode_descriptions[mode].setVisible(selected)

    def _update_mode_notice(self, *args) -> None:
        self.report_label.setText(mode_note(self._selected_mode()))
        self._refresh_mode_cards()

    def _update_report(self) -> None:
        self.report_label.setText(report_text(self.findings, self._selected_mode()))

    def _primary_state(self) -> tuple[str, str, bool]:
        """Return (action_kind, button_label, enabled) for the single step-aware primary button."""
        input_has_text = bool(self.input_text.toPlainText().strip())
        output_has_text = bool(self.output_text.toPlainText().strip())
        output_ready = output_has_text or self.anonymized_document is not None
        if output_ready:
            return "copy", "Copia risultato", output_has_text
        if self._findings_ready_for_filtering() and input_has_text:
            count = len(self._checked_findings())
            label = "Anonimizza 1 dato" if count == 1 else f"Anonimizza {count} dati"
            return "anonymize", label, input_has_text
        return "analyze", "Analizza dati", input_has_text

    def _primary_action(self) -> None:
        kind, _label, _enabled = self._primary_state()
        if kind == "copy":
            self.copy_output()
        elif kind == "anonymize":
            self.anonymize_text()
        else:
            self.analyze_text()

    def _friendly_error_message(self, exc: Exception) -> str:
        message = str(exc)
        if "OCR" in message or "testo estraibile" in message or "scansionate" in message:
            return f"{message} Questo evita di considerare sicuro un PDF che l'app non può leggere."
        return f"Non riesco a caricare il documento: {message}"

    def _friendly_processing_error_message(self, exc: Exception) -> str:
        message = str(exc)
        if "PDF" in message:
            return message
        return f"Non riesco ad anonimizzare il documento: {message}"

    def _first_local_drop_path(self, event: QDragEnterEvent | QDropEvent) -> Path | None:
        mime_data = event.mimeData()
        if not mime_data.hasUrls():
            return None
        for url in mime_data.urls():
            if url.isLocalFile():
                return Path(url.toLocalFile())
        return None

    def _sync_action_state(self) -> None:
        input_has_text = bool(self.input_text.toPlainText().strip())
        output_has_text = bool(self.output_text.toPlainText().strip())
        has_anything = input_has_text or output_has_text or self.loaded_document is not None
        _kind, label, primary_enabled = self._primary_state()
        self.primary_button.setText(label)
        self.primary_button.setEnabled(primary_enabled)
        self.copy_button.setEnabled(output_has_text)
        self.save_button.setEnabled(output_has_text or self.anonymized_document is not None)
        self.clear_button.setEnabled(has_anything)
        self.add_selection_button.setEnabled(input_has_text and self._manual_filter_supported())
        if hasattr(self, "save_map_action"):
            self.save_map_action.setEnabled(bool(self.reversible_mapping))
        self._update_workflow_steps()

    def _workflow_step_states(self) -> list[str]:
        step1_done = self.loaded_document is not None or bool(self.input_text.toPlainText().strip())
        step2_done = bool(self.findings) and not self.findings_stale and self._findings_mode == self._selected_mode()
        has_manual_finding = any(finding.source == "manual" for finding in self.findings)
        step4_done = bool(self.output_text.toPlainText().strip()) or self.anonymized_document is not None

        def state(done: bool, reachable: bool) -> str:
            if done:
                return "done"
            return "current" if reachable else "pending"

        return [
            state(step1_done, True),
            state(step2_done, step1_done),
            state(has_manual_finding or step4_done, step2_done),
            state(step4_done, step2_done),
        ]

    def _update_workflow_steps(self) -> None:
        object_names = {"pending": "StepRowPending", "current": "StepRowCurrent", "done": "StepRowDone"}
        for row, step_state in zip(self.step_rows, self._workflow_step_states()):
            object_name = object_names[step_state]
            if row.objectName() != object_name:
                row.setObjectName(object_name)
                row.style().unpolish(row)
                row.style().polish(row)
                for child in row.findChildren(QLabel):
                    child.style().unpolish(child)
                    child.style().polish(child)
                    # The title's font weight changes with state (e.g. bolder when
                    # done/current), which can change its wrapped height. Without
                    # invalidating the cached size hints here, the QVBoxLayout keeps
                    # the geometry computed before the restyle and rows can overlap.
                    child.updateGeometry()
                row.updateGeometry()

    def _handle_input_text_changed(self) -> None:
        if not self._loading_document_text:
            current_text = self.input_text.toPlainText()
            if self.loaded_document and current_text != self.loaded_document.text:
                self.document_text_dirty = True
                self.anonymized_document = None
            # Il testo cambia identità (non solo formattazione) solo quando differisce
            # dall'ultimo testo effettivamente analizzato: _highlight_findings tocca la
            # formattazione e riemette textChanged senza alterare il contenuto.
            if current_text != self._findings_source_text:
                self.findings_stale = True
        self._sync_action_state()

    def _handle_output_text_changed(self) -> None:
        if not self._updating_output_text:
            self.output_text_dirty = True
        self._sync_action_state()

    def _set_output_text(self, text: str) -> None:
        self._updating_output_text = True
        try:
            self.output_text.setPlainText(text)
        finally:
            self._updating_output_text = False
        self.output_text_dirty = False
        self._sync_action_state()

    def _record_activity(
        self,
        action: ActivityAction,
        *,
        output_path: str | Path | None = None,
        output_data: bytes | None = None,
    ) -> None:
        source_is_document = self.loaded_document is not None and not self.document_text_dirty
        try:
            entry = build_activity_entry(
                action=action,
                source_kind="document" if source_is_document else "pasted_text",
                mode=self._selected_mode(),
                findings=self.findings,
                source_path=self.loaded_document.path if source_is_document and self.loaded_document else None,
                output_path=output_path,
                output_data=output_data,
                app_version=__version__,
            )
            record_activity(entry)
        except Exception:
            self.statusBar().showMessage("Registro attività non aggiornato.", 4000)

    def _activity_timestamp(self, entry: dict[str, object]) -> str:
        timestamp = str(entry.get("timestamp") or "")
        return timestamp.replace("T", " ").replace("+00:00", " UTC")

    def _activity_source_text(self, entry: dict[str, object]) -> str:
        source = str(entry.get("source_label") or entry.get("source_kind") or "")
        extension = entry.get("source_extension")
        size = entry.get("source_size_bytes")
        parts = [source]
        if extension:
            parts.append(str(extension))
        if isinstance(size, int):
            parts.append(self._format_bytes(size))
        return " · ".join(parts)

    def _activity_counts_text(self, counts: object) -> str:
        if not isinstance(counts, dict) or not counts:
            return "nessun tipo"
        parts = []
        for entity_type, count in sorted(counts.items(), key=lambda item: entity_label(str(item[0]), 2)):
            if isinstance(count, int):
                parts.append(f"{count} {entity_label(str(entity_type), count)}")
        return ", ".join(parts) if parts else "nessun tipo"

    def _short_hash(self, value: object) -> str:
        if not isinstance(value, str) or not value:
            return ""
        return f"{value[:12]}..."

    def _format_bytes(self, value: int) -> str:
        if value >= 1024 * 1024:
            return f"{value / (1024 * 1024):.1f} MB"
        if value >= 1024:
            return f"{value / 1024:.1f} KB"
        return f"{value} byte"

    def _default_map_filename(self) -> str:
        if self.loaded_document:
            return f"{self.loaded_document.path.stem}{MAP_EXTENSION}"
        return f"omissis-mappa{MAP_EXTENSION}"

    def _ask_passphrase(self, title: str, label: str, *, confirm: bool = False) -> str | None:
        first, ok = QInputDialog.getText(self, title, label, QLineEdit.Password)
        if not ok:
            return None
        if not first.strip():
            self.statusBar().showMessage("La password non può essere vuota.", 5000)
            return None
        if not confirm:
            return first

        second, ok = QInputDialog.getText(self, title, "Ripeti la password:", QLineEdit.Password)
        if not ok:
            return None
        if first != second:
            self.statusBar().showMessage("Le password non coincidono.", 6000)
            return None
        return first


def main() -> int:
    app = QApplication(sys.argv)
    _load_app_fonts()
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
