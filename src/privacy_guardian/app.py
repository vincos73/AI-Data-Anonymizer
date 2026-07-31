from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QSignalBlocker, QSize, QThreadPool, Qt, QUrl, Slot
from PySide6.QtGui import (
    QAction,
    QColor,
    QCloseEvent,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QFontDatabase,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPalette,
    QPixmap,
    QResizeEvent,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
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
    clear_activity_log,
    export_activity_log_csv,
    load_activity_entries,
    load_activity_settings,
    record_activity,
    set_activity_logging_enabled,
    set_activity_retention,
)
from privacy_guardian.document_service import (
    LEGACY_DOC_SUPPORTED,
    AnonymizedDocument,
    LoadedDocument,
    OcrUnavailableError,
    add_extra_value_findings,
    excluded_value_pairs,
    load_document,
    normalize_pdf_text_for_llm,
)
from privacy_guardian.desktop_jobs import DesktopJob, JobContext
from privacy_guardian.desktop_workflows import (
    AnalysisOutcome,
    AnonymizationOutcome,
    AnonymizationRequest,
    analyze_text as analyze_text_workflow,
    anonymize as anonymize_workflow,
)
from privacy_guardian.entity_categories import entity_color
from privacy_guardian.findings_panel import FindingsPanel
from privacy_guardian.models import AnonymizationMode, Finding, validate_anonymization_mode
from privacy_guardian.persistence import atomic_write_bytes, atomic_write_text
from privacy_guardian.privacy_engine import PrivacyEngine
from privacy_guardian.reversible import (
    MAP_EXTENSION,
    ReversibleMapEntry,
    ReversibleMapError,
    read_encrypted_mapping,
    restore_text,
    write_encrypted_mapping,
)
from privacy_guardian.reporting import ENTITY_LABELS, entity_label, mode_label, mode_note, report_text
from privacy_guardian.styles import (
    APP_STYLE,
    EDITOR_BACKGROUND_COLOR,
    EDITOR_PLACEHOLDER_COLOR,
    EDITOR_SELECTION_BACKGROUND_COLOR,
    EDITOR_SELECTION_TEXT_COLOR,
    EDITOR_TEXT_COLOR,
    FINDING_HIGHLIGHT_ALPHA,
    FINDING_SELECTED_HIGHLIGHT_ALPHA,
)
from privacy_guardian.workflow_state import (
    OutputProvenance,
    selection_fingerprint,
    source_fingerprint,
)


PROJECT_REPO_URL = "https://github.com/vincos73/AI-Data-Anonymizer"
PROJECT_RELEASES_URL = f"{PROJECT_REPO_URL}/releases"
TESSERACT_WINDOWS_DOWNLOAD_URL = "https://github.com/UB-Mannheim/tesseract/wiki"
PROJECT_SECURITY_URL = f"{PROJECT_REPO_URL}/blob/main/SICUREZZA.md"


def _configure_text_editor(editor: QTextEdit) -> None:
    """Make the dark editor palette explicit across native Qt styles.

    Qt stylesheets paint the expected colors on macOS, but on Windows the
    QTextDocument and its viewport can retain the native light-theme palette.
    That leaves plain text black even though the editor surface is dark.
    Setting both palettes and the document's current text format avoids that
    platform-dependent fallback. Rich-text paste is disabled so pasted source
    cannot reintroduce an unreadable foreground color.
    """

    palette_roles = {
        QPalette.Base: EDITOR_BACKGROUND_COLOR,
        QPalette.Text: EDITOR_TEXT_COLOR,
        QPalette.PlaceholderText: EDITOR_PLACEHOLDER_COLOR,
        QPalette.Highlight: EDITOR_SELECTION_BACKGROUND_COLOR,
        QPalette.HighlightedText: EDITOR_SELECTION_TEXT_COLOR,
    }
    for target in (editor, editor.viewport()):
        palette = target.palette()
        for role, color in palette_roles.items():
            palette.setColor(role, QColor(color))
        target.setPalette(palette)

    editor.setAcceptRichText(False)
    editor.setTextColor(QColor(EDITOR_TEXT_COLOR))


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


class _AdaptiveToolbar(QFrame):
    def __init__(
        self,
        load_button: QPushButton,
        document_label: QLabel,
        copy_button: QPushButton,
        save_button: QPushButton,
        clear_button: QPushButton,
        add_selection_button: QPushButton,
        primary_button: QPushButton,
    ) -> None:
        super().__init__()
        self.setObjectName("DocumentToolbar")
        self._widgets = (
            load_button,
            document_label,
            copy_button,
            save_button,
            clear_button,
            add_selection_button,
            primary_button,
        )
        self._grid = QGridLayout()
        self._grid.setContentsMargins(16, 8, 16, 8)
        self._grid.setHorizontalSpacing(8)
        self._grid.setVerticalSpacing(8)
        self.setLayout(self._grid)
        self._compact: bool | None = None
        self._relayout(compact=False)

    def resizeEvent(self, event: QResizeEvent) -> None:
        self._relayout(compact=event.size().width() < 900)
        super().resizeEvent(event)

    def _relayout(self, *, compact: bool) -> None:
        if self._compact == compact:
            return
        self._compact = compact
        for widget in self._widgets:
            self._grid.removeWidget(widget)

        load_button, document_label, copy_button, save_button, clear_button, add_button, primary_button = self._widgets
        copy_button.setVisible(False)
        if compact:
            save_button.setMaximumWidth(112)
            clear_button.setMaximumWidth(96)
            add_button.setMaximumWidth(180)
            self._grid.addWidget(load_button, 0, 0, 1, 1, Qt.AlignVCenter)
            self._grid.addWidget(document_label, 0, 1, 1, 4, Qt.AlignVCenter)
            self._grid.addWidget(primary_button, 0, 5, 1, 1, Qt.AlignVCenter)
            self._grid.addWidget(save_button, 1, 2, 1, 1, Qt.AlignRight | Qt.AlignVCenter)
            self._grid.addWidget(clear_button, 1, 3, 1, 1, Qt.AlignRight | Qt.AlignVCenter)
            self._grid.addWidget(add_button, 1, 4, 1, 2, Qt.AlignRight | Qt.AlignVCenter)
            self.setMinimumHeight(96)
        else:
            save_button.setMaximumWidth(16_777_215)
            clear_button.setMaximumWidth(16_777_215)
            add_button.setMaximumWidth(16_777_215)
            self._grid.addWidget(load_button, 0, 0, 1, 1, Qt.AlignVCenter)
            self._grid.addWidget(document_label, 0, 1, 1, 1, Qt.AlignVCenter)
            self._grid.addWidget(save_button, 0, 2, 1, 1, Qt.AlignVCenter)
            self._grid.addWidget(clear_button, 0, 3, 1, 1, Qt.AlignVCenter)
            self._grid.addWidget(add_button, 0, 4, 1, 1, Qt.AlignVCenter)
            self._grid.addWidget(primary_button, 0, 5, 1, 1, Qt.AlignVCenter)
            self.setMinimumHeight(56)
        self._grid.setColumnStretch(1, 1)


class MainWindow(QMainWindow):
    def __init__(self, *, run_jobs_synchronously: bool | None = None) -> None:
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
        self._workflow_revision = 0
        self._output_provenance: OutputProvenance | None = None
        self._output_stale_reason = ""
        self._output_saved = True
        self._reversible_map_saved = True
        self._review_dirty = False
        self._last_selected_mode: AnonymizationMode = "standard"
        self._thread_pool = QThreadPool.globalInstance()
        self._active_job: DesktopJob | None = None
        self._active_job_kind = ""
        self._active_job_success_callback = None
        self._active_job_failure_callback = None
        self._close_when_idle = False
        self._run_jobs_synchronously = (
            os.environ.get("OMISSIS_SYNC_JOBS") == "1"
            if run_jobs_synchronously is None
            else run_jobs_synchronously
        )

        self.setWindowTitle("OMISSIS")
        self.resize(1160, 760)
        self.setMinimumSize(QSize(960, 640))
        self.setAcceptDrops(True)

        self.input_text = QTextEdit()
        _configure_text_editor(self.input_text)
        self.input_text.setAcceptDrops(False)
        self.input_text.setPlaceholderText("Incolla qui il testo da controllare oppure carica un documento.")
        self.input_text.setAccessibleName("Testo originale")
        self.input_text.setAccessibleDescription("Testo o contenuto del documento da analizzare e anonimizzare.")
        self.input_text.textChanged.connect(self._handle_input_text_changed)
        self._input_viewport = self.input_text.viewport()
        self.input_text.installEventFilter(self)
        self._input_viewport.installEventFilter(self)

        self.output_text = QTextEdit()
        _configure_text_editor(self.output_text)
        self.output_text.setAcceptDrops(False)
        self.output_text.setPlaceholderText("Il testo anonimizzato apparirà qui.")
        self.output_text.setAccessibleName("Testo anonimizzato")
        self.output_text.setAccessibleDescription(
            "Risultato prodotto da OMISSIS. Se diventa obsoleto viene disabilitato fino alla rigenerazione."
        )
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

        local_engine = "Regole + NER" if self.engine.ner_active else "Regole attive"
        self.local_notice = QLabel(
            f"Elaborazione locale · {local_engine} · i dati restano sul dispositivo"
        )
        self.local_notice.setObjectName("LocalNotice")
        self.local_notice.setWordWrap(True)

        self.document_label = QLabel("Nessun documento caricato. Puoi incollare testo o trascinare un file nella finestra.")
        self.document_label.setObjectName("DocumentNotice")
        self.document_label.setWordWrap(True)

        # Rail hint shown only when the optional local NER model is not installed.
        self.ner_notice = QLabel("NER facoltativo non disponibile · vedi README")
        self.ner_notice.setObjectName("NerHint")
        self.ner_notice.setWordWrap(True)
        self.ner_notice.setVisible(not self.engine.ner_active)

        self.report_label = QLabel()
        self.report_label.setObjectName("ReportNotice")
        self.report_label.setWordWrap(True)
        self.report_label.setAccessibleName("Verifica finale")

        self.load_button = QPushButton("Carica")
        self.load_button.clicked.connect(self.open_file)
        self.load_button.setObjectName("SecondaryButton")
        self.load_button.setToolTip("Carica un documento oppure trascinalo nella finestra.")
        self.load_button.setAccessibleDescription("Apre un documento locale senza inviarlo a servizi esterni.")

        self.copy_button = QPushButton("Copia")
        self.copy_button.clicked.connect(self.copy_output)
        self.copy_button.setObjectName("SecondaryButton")
        self.copy_button.setToolTip("Copia il risultato corrente negli appunti.")
        self.copy_button.setAccessibleDescription(
            "Copia il risultato solo se è ancora coerente con testo, modalità e selezioni correnti."
        )

        self.save_button = QPushButton("Salva")
        self.save_button.clicked.connect(self.save_output)
        self.save_button.setObjectName("SecondaryButton")
        self.save_button.setToolTip("Salva il risultato corrente sul dispositivo.")
        self.save_button.setAccessibleDescription(
            "Salva il risultato nel formato prodotto oppure come testo se è stato modificato."
        )

        self.clear_button = QPushButton("Pulisci")
        self.clear_button.clicked.connect(self.clear_all)
        self.clear_button.setObjectName("SecondaryButton")
        self.clear_button.setToolTip("Pulisce la sessione dopo una conferma se esiste lavoro non salvato.")
        self.clear_button.setAccessibleDescription("Azzera la sessione senza eliminare lavoro non salvato per errore.")

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
        self.primary_button.setAccessibleDescription(
            "Esegue il passaggio successivo: analisi, anonimizzazione oppure copia del risultato."
        )

        self.job_status_label = QLabel("Elaborazione in corso")
        self.job_status_label.setObjectName("JobStatus")
        self.job_status_label.setWordWrap(True)
        self.job_progress = QProgressBar()
        self.job_progress.setObjectName("JobProgress")
        self.job_progress.setRange(0, 100)
        self.job_progress.setValue(0)
        self.job_progress.setTextVisible(False)
        self.job_progress.setAccessibleName("Avanzamento elaborazione")
        self.cancel_job_button = QPushButton("Annulla")
        self.cancel_job_button.setObjectName("SecondaryButton")
        self.cancel_job_button.setAccessibleDescription("Richiede l'annullamento al prossimo punto sicuro.")
        self.cancel_job_button.clicked.connect(self.cancel_active_job)

        job_row = QHBoxLayout()
        job_row.setContentsMargins(12, 8, 12, 8)
        job_row.setSpacing(10)
        job_row.addWidget(self.job_status_label, 1)
        job_row.addWidget(self.job_progress, 1)
        job_row.addWidget(self.cancel_job_button)
        self.job_frame = QFrame()
        self.job_frame.setObjectName("JobFrame")
        self.job_frame.setLayout(job_row)
        self.job_frame.setVisible(False)

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
            ("standard", "Standard (più leggibile)"),
            ("maximum", "Massima protezione"),
            ("reversible", "Reversibile con mappa locale"),
        ]
        protection_column = QVBoxLayout()
        protection_column.setSpacing(8)
        for mode, title in mode_options:
            radio = QRadioButton(title)
            radio.setObjectName("ModeCardRadio")
            radio.setAccessibleDescription(mode_note(mode))

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

        self.mode_radios["standard"].setChecked(True)
        for radio in self.mode_radios.values():
            radio.toggled.connect(self._handle_mode_toggled)

        self.map_status_label = QLabel("Nessuna mappa attiva")
        self.map_status_label.setObjectName("MapStatus")
        self.map_status_label.setWordWrap(True)
        self.map_status_label.setAccessibleName("Stato della mappa reversibile")
        self.map_section_label = self._rail_section_label("MAPPA REVERSIBILE")

        rail_content_layout = QVBoxLayout()
        rail_content_layout.setContentsMargins(20, 20, 20, 16)
        rail_content_layout.setSpacing(10)
        rail_content_layout.addLayout(brand_column)
        rail_content_layout.addSpacing(8)
        rail_content_layout.addWidget(self._rail_section_label("FLUSSO"))
        rail_content_layout.addLayout(stepper_column)
        rail_content_layout.addWidget(self._rail_section_label("PROTEZIONE"))
        rail_content_layout.addLayout(protection_column)
        rail_content_layout.addWidget(self.map_section_label)
        rail_content_layout.addWidget(self.map_status_label)
        rail_content_layout.addStretch(1)
        rail_content_layout.addWidget(self.ner_notice)
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

        self.rail = QFrame()
        self.rail.setObjectName("Rail")
        self.rail.setFixedWidth(288)
        self.rail.setLayout(rail_outer_layout)

        # ---- Main area: document toolbar ----
        self.document_toolbar = _AdaptiveToolbar(
            self.load_button,
            self.document_label,
            self.copy_button,
            self.save_button,
            self.clear_button,
            self.add_selection_button,
            self.primary_button,
        )

        self.input_panel = self._panel("Testo originale", self.input_text)
        self.output_panel = self._panel("Testo anonimizzato", self.output_text)

        self.text_splitter = QSplitter(Qt.Horizontal)
        self.text_splitter.setHandleWidth(14)
        self.text_splitter.addWidget(self.input_panel)
        self.text_splitter.addWidget(self.output_panel)
        self.text_splitter.setCollapsible(0, False)
        self.text_splitter.setCollapsible(1, False)
        self.text_splitter.setSizes([540, 540])

        self.workspace_splitter = QSplitter(Qt.Vertical)
        self.workspace_splitter.setObjectName("WorkspaceSplitter")
        self.workspace_splitter.setHandleWidth(10)
        self.workspace_splitter.addWidget(self.text_splitter)
        self.workspace_splitter.addWidget(self.findings_panel)
        self.workspace_splitter.setStretchFactor(0, 2)
        self.workspace_splitter.setStretchFactor(1, 3)
        self.workspace_splitter.setCollapsible(0, False)
        self.workspace_splitter.setCollapsible(1, False)
        self.workspace_splitter.setSizes([300, 420])

        main_area_layout = QVBoxLayout()
        main_area_layout.setContentsMargins(22, 18, 22, 16)
        main_area_layout.setSpacing(14)
        main_area_layout.addWidget(self.document_toolbar)
        main_area_layout.addWidget(self.job_frame)
        main_area_layout.addWidget(self.report_label)
        main_area_layout.addWidget(self.workspace_splitter, 1)

        main_area = QWidget()
        main_area.setLayout(main_area_layout)

        root_layout = QHBoxLayout()
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self.rail, 0)
        root_layout.addWidget(main_area, 1)

        container = QWidget()
        container.setLayout(root_layout)
        self.setCentralWidget(container)
        self.setStyleSheet(APP_STYLE)
        self._build_menu()
        self._configure_accessibility()
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
        self.open_action = QAction("Carica documento...", self)
        self.open_action.setShortcut(QKeySequence.Open)
        self.open_action.triggered.connect(self.open_file)

        quit_action = QAction("Esci", self)
        quit_action.setShortcut(QKeySequence.Quit)
        quit_action.triggered.connect(self.close)

        self.copy_output_action = QAction("Copia risultato", self)
        self.copy_output_action.setShortcut(QKeySequence("Ctrl+Shift+C"))
        self.copy_output_action.triggered.connect(self.copy_output)

        self.save_output_action = QAction("Salva risultato...", self)
        self.save_output_action.setShortcut(QKeySequence.Save)
        self.save_output_action.triggered.connect(self.save_output)

        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction(self.open_action)
        file_menu.addSeparator()
        file_menu.addAction(self.copy_output_action)
        file_menu.addAction(self.save_output_action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)

        self.activity_action = QAction("Registro attività", self)
        self.activity_action.triggered.connect(self.show_activity_log_dialog)

        self.primary_action = QAction("Esegui passaggio corrente", self)
        self.primary_action.setShortcut(QKeySequence("Ctrl+Return"))
        self.primary_action.triggered.connect(self._primary_action)

        self.focus_search_action = QAction("Cerca nei dati rilevati", self)
        self.focus_search_action.setShortcut(QKeySequence.Find)
        self.focus_search_action.triggered.connect(self.focus_findings_search)

        self.toggle_rail_action = QAction("Mostra barra laterale", self)
        self.toggle_rail_action.setShortcut(QKeySequence("Ctrl+Shift+L"))
        self.toggle_rail_action.setCheckable(True)
        self.toggle_rail_action.setChecked(True)
        self.toggle_rail_action.toggled.connect(self.rail.setVisible)

        self.save_map_action = QAction("Salva mappa reversibile...", self)
        self.save_map_action.triggered.connect(self.save_reversible_map)

        self.load_map_action = QAction("Carica mappa reversibile...", self)
        self.load_map_action.triggered.connect(self.load_reversible_map)

        self.restore_map_action = QAction("Ricostruisci testo con mappa...", self)
        self.restore_map_action.triggered.connect(self.restore_with_reversible_map)

        tools_menu = self.menuBar().addMenu("Strumenti")
        tools_menu.addAction(self.primary_action)
        tools_menu.addAction(self.focus_search_action)
        tools_menu.addAction(self.toggle_rail_action)
        tools_menu.addSeparator()
        tools_menu.addAction(self.activity_action)
        tools_menu.addSeparator()
        tools_menu.addAction(self.load_map_action)
        tools_menu.addAction(self.save_map_action)
        tools_menu.addAction(self.restore_map_action)

        security_action = QAction("Sicurezza e privacy", self)
        security_action.triggered.connect(self.show_security_dialog)

        self.review_help_action = QAction("Come rivedere i dati rilevati", self)
        self.review_help_action.setShortcut(QKeySequence.HelpContents)
        self.review_help_action.triggered.connect(self.show_review_help_dialog)

        about_action = QAction("Informazioni su OMISSIS", self)
        about_action.triggered.connect(self.show_about_dialog)

        help_menu = self.menuBar().addMenu("Aiuto")
        help_menu.addAction(self.review_help_action)
        help_menu.addSeparator()
        help_menu.addAction(security_action)
        help_menu.addSeparator()
        help_menu.addAction(about_action)

    def _configure_accessibility(self) -> None:
        self.load_button.setAccessibleName("Carica documento")
        self.copy_button.setAccessibleName("Copia risultato")
        self.save_button.setAccessibleName("Salva risultato")
        self.clear_button.setAccessibleName("Pulisci sessione")
        self.add_selection_button.setAccessibleName("Aggiungi selezione manuale")
        self.primary_button.setAccessibleName("Esegui passaggio corrente")
        self.setTabOrder(self.load_button, self.input_text)
        self.setTabOrder(self.input_text, self.add_selection_button)
        self.setTabOrder(self.add_selection_button, self.findings_panel.search_edit)
        self.setTabOrder(self.findings_panel.search_edit, self.findings_panel.tree)
        self.setTabOrder(self.findings_panel.tree, self.primary_button)
        self.setTabOrder(self.primary_button, self.output_text)
        self.setTabOrder(self.output_text, self.save_button)
        self.setTabOrder(self.save_button, self.clear_button)

    def focus_findings_search(self) -> None:
        self.findings_panel.search_edit.setFocus(Qt.ShortcutFocusReason)
        self.findings_panel.search_edit.selectAll()

    def _focus_review_workspace(self) -> None:
        """Keep review central without forcing focus or a native table scroll."""
        self._selected_finding_index = None

    def _show_result_workspace(self) -> None:
        self.output_text.ensureCursorVisible()

    def _show_input_workspace(self) -> None:
        self.input_text.ensureCursorVisible()

    def show_review_help_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setObjectName("InfoDialog")
        dialog.setWindowTitle("Come rivedere i dati rilevati")
        dialog.setModal(True)
        dialog.setMinimumWidth(560)

        title = QLabel("Rivedi prima di anonimizzare")
        title.setObjectName("DialogTitle")

        details = QLabel(
            "<b>1. Controlla le righe.</b> Spuntato significa che il valore sarà anonimizzato; "
            "non spuntato significa che resterà leggibile.<br><br>"
            "<b>2. Usa Affidabilità e Origine come aiuto.</b> Affidabilità indica quanto è "
            "forte la regola che ha trovato il valore, non è una probabilità statistica. "
            "Origine distingue regole locali, NER e selezioni manuali.<br><br>"
            "<b>3. Correggi le mancanze.</b> Seleziona una parola nel testo originale e usa "
            "«Aggiungi selezione». Puoi cercare o filtrare l'elenco senza cambiare le spunte.<br><br>"
            "<b>4. Conferma.</b> Il pulsante principale indica quanti dati verranno anonimizzati. "
            "Dopo ogni modifica il vecchio risultato viene bloccato finché non lo rigeneri.<br><br>"
            "<b>Tastiera:</b> Tab sposta il focus, Spazio include o esclude una riga, "
            "Ctrl+Invio esegue il passaggio corrente e Ctrl+F apre la ricerca."
        )
        details.setObjectName("DialogDetails")
        details.setTextFormat(Qt.RichText)
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
            "<b>PDF:</b> puoi conservarne il layout come pagine rasterizzate con oscuramenti "
            "permanenti oppure scegliere Converti PDF in testo per ricomporre righe e sillabazioni, "
            "migliorare il riconoscimento e ottenere un file .txt per un LLM. I PDF scansionati "
            "possono essere letti con Tesseract OCR locale; non vengono usati servizi esterni.<br><br>"
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
            "nessun testo anonimizzato, nessun valore rilevato. Puoi disattivarlo o cancellarlo "
            "in qualsiasi momento."
        )
        description.setObjectName("DialogDetails")
        description.setWordWrap(True)

        settings_label = QLabel()
        settings_label.setObjectName("ActivitySettings")
        settings_label.setWordWrap(True)

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

        empty_notice = QLabel("Nessuna attività registrata.")
        empty_notice.setObjectName("DialogDetails")
        empty_notice.setVisible(not entries)

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
            try:
                export_activity_log_csv(filename)
            except OSError as exc:
                self.statusBar().showMessage(f"Esportazione non riuscita: {exc}", 8000)
                return
            self.statusBar().showMessage(f"Registro esportato: {filename}", 5000)

        export_button.clicked.connect(export_log)
        export_button.setEnabled(bool(entries))

        toggle_button = QPushButton()
        toggle_button.setObjectName("SecondaryButton")

        retention_button = QPushButton("Conservazione...")
        retention_button.setObjectName("SecondaryButton")

        clear_button = QPushButton("Svuota registro")
        clear_button.setObjectName("SecondaryButton")
        clear_button.setEnabled(bool(entries))

        def refresh_settings_label() -> None:
            current = load_activity_settings()
            state = "attivo" if current.enabled else "disattivato"
            settings_label.setText(
                f"Stato: registro {state} · conservazione: ultime {current.retention_entries} operazioni"
            )
            toggle_button.setText("Disattiva registro" if current.enabled else "Attiva registro")

        def toggle_logging() -> None:
            current = load_activity_settings()
            try:
                set_activity_logging_enabled(not current.enabled)
            except OSError as exc:
                self.statusBar().showMessage(f"Impostazione non salvata: {exc}", 8000)
                return
            refresh_settings_label()

        def change_retention() -> None:
            current = load_activity_settings()
            value, accepted = QInputDialog.getInt(
                dialog,
                "Conservazione del registro",
                "Numero massimo di operazioni da conservare:",
                current.retention_entries,
                50,
                10_000,
                50,
            )
            if not accepted:
                return
            try:
                set_activity_retention(value)
            except OSError as exc:
                self.statusBar().showMessage(f"Conservazione non aggiornata: {exc}", 8000)
                return
            refresh_settings_label()
            self.statusBar().showMessage(f"Conservazione impostata a {value} operazioni.", 5000)

        def clear_log() -> None:
            answer = QMessageBox.question(
                dialog,
                "Svuota registro attività",
                "Eliminare definitivamente tutte le voci del registro locale?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
            try:
                clear_activity_log()
            except OSError as exc:
                self.statusBar().showMessage(f"Registro non cancellato: {exc}", 8000)
                return
            entries.clear()
            table.setRowCount(0)
            empty_notice.setVisible(True)
            export_button.setEnabled(False)
            clear_button.setEnabled(False)
            self.statusBar().showMessage("Registro attività svuotato.", 5000)

        toggle_button.clicked.connect(toggle_logging)
        retention_button.clicked.connect(change_retention)
        clear_button.clicked.connect(clear_log)
        refresh_settings_label()

        close_button = QPushButton("Chiudi")
        close_button.setObjectName("SecondaryButton")
        close_button.clicked.connect(dialog.accept)

        button_row = QHBoxLayout()
        button_row.addWidget(export_button)
        button_row.addWidget(toggle_button)
        button_row.addWidget(retention_button)
        button_row.addWidget(clear_button)
        button_row.addStretch(1)
        button_row.addWidget(close_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(description)
        layout.addWidget(settings_label)
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

    def _discardable_work_items(
        self,
        *,
        include_source: bool = True,
        include_review: bool = True,
        include_output: bool = True,
        include_map: bool = True,
    ) -> list[str]:
        items: list[str] = []
        source_text = self.input_text.toPlainText().strip()
        if include_source and source_text and (self.loaded_document is None or self.document_text_dirty):
            items.append("testo sorgente modificato")
        if include_review and self._review_dirty:
            items.append("selezioni di anonimizzazione non ancora applicate")
        if include_output and self._has_output() and not self._output_saved:
            items.append("risultato anonimizzato non salvato")
        if include_map and self.reversible_mapping and not self._reversible_map_saved:
            items.append("mappa reversibile non salvata")
        return items

    def _confirm_discard_work(
        self,
        action_label: str,
        *,
        include_source: bool = True,
        include_review: bool = True,
        include_output: bool = True,
        include_map: bool = True,
    ) -> bool:
        items = self._discardable_work_items(
            include_source=include_source,
            include_review=include_review,
            include_output=include_output,
            include_map=include_map,
        )
        if not items:
            return True

        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Warning)
        dialog.setWindowTitle("Modifiche non salvate")
        dialog.setText("Questa azione eliminerebbe del lavoro non salvato.")
        dialog.setInformativeText("Verranno eliminati: " + ", ".join(items) + ".")
        cancel_button = dialog.addButton("Annulla", QMessageBox.RejectRole)
        discard_button = dialog.addButton(action_label, QMessageBox.DestructiveRole)
        dialog.setDefaultButton(cancel_button)
        dialog.exec()
        return dialog.clickedButton() is discard_button

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._active_job is not None:
            self._close_when_idle = True
            self.cancel_active_job()
            event.ignore()
            return
        # An invisible window is normally a headless test or a window already being
        # disposed; prompting there would leave no usable parent for the dialog.
        if not self.isVisible() or self._confirm_discard_work("Esci e scarta"):
            event.accept()
            return
        event.ignore()

    def _start_job(
        self,
        kind: str,
        title: str,
        work,
        on_success,
        on_failure=None,
    ) -> bool:
        if self._active_job is not None:
            self.statusBar().showMessage("Attendi o annulla l'operazione già in corso.", 4000)
            return False

        job = DesktopJob(work)
        self._active_job = job
        self._active_job_kind = kind
        self._active_job_success_callback = on_success
        self._active_job_failure_callback = on_failure
        self.job_status_label.setText(title)
        self.job_progress.setValue(0)
        self.cancel_job_button.setEnabled(True)
        self.cancel_job_button.setText("Annulla")
        self.job_frame.setVisible(True)

        job.signals.progress.connect(self._handle_job_progress)
        job.signals.succeeded.connect(self._handle_active_job_succeeded)
        job.signals.failed.connect(self._handle_active_job_failed)
        job.signals.cancelled.connect(self._handle_active_job_cancelled)
        job.signals.finished.connect(self._handle_active_job_finished)
        self._sync_action_state()

        if self._run_jobs_synchronously:
            job.run()
        else:
            self._thread_pool.start(job)
        return True

    @Slot(int, str)
    def _handle_job_progress(self, value: int, message: str) -> None:
        if self._active_job is None:
            return
        self.job_progress.setValue(value)
        self.job_status_label.setText(message)

    def _job_for_signal_sender(self) -> DesktopJob | None:
        job = self._active_job
        if job is None or self.sender() is not job.signals:
            return None
        return job

    @Slot(object)
    def _handle_active_job_succeeded(self, result: object) -> None:
        job = self._job_for_signal_sender()
        if job is None or job.token.is_cancelled:
            return
        callback = self._active_job_success_callback
        self._finish_job(job)
        callback(result)

    @Slot(object)
    def _handle_active_job_failed(self, error: Exception) -> None:
        job = self._job_for_signal_sender()
        if job is None:
            return
        callback = self._active_job_failure_callback
        self._finish_job(job)
        if callback is not None:
            callback(error)
        else:
            self.statusBar().showMessage(str(error), 9000)

    @Slot()
    def _handle_active_job_cancelled(self) -> None:
        job = self._job_for_signal_sender()
        if job is None:
            return
        self._finish_job(job)
        self.statusBar().showMessage("Operazione annullata. Il lavoro precedente è rimasto invariato.", 5000)

    @Slot()
    def _handle_active_job_finished(self) -> None:
        job = self._job_for_signal_sender()
        if job is not None:
            self._finish_job(job)

    def _finish_job(self, job: DesktopJob) -> None:
        if self._active_job is not job:
            return
        self._active_job = None
        self._active_job_kind = ""
        self._active_job_success_callback = None
        self._active_job_failure_callback = None
        self.job_frame.setVisible(False)
        self._sync_action_state()
        if self._close_when_idle:
            self._close_when_idle = False
            self.close()

    def cancel_active_job(self) -> None:
        if self._active_job is None:
            return
        self._active_job.cancel()
        self.cancel_job_button.setEnabled(False)
        self.cancel_job_button.setText("Annullamento...")
        self.job_status_label.setText("Annullamento richiesto: attendo un punto sicuro")

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
        if event.type() == QEvent.KeyPress and obj in (
            self.input_text,
            self._input_viewport,
        ):
            modifiers = event.modifiers()
            if event.key() in (Qt.Key_Return, Qt.Key_Enter) and modifiers & (
                Qt.ControlModifier | Qt.MetaModifier
            ):
                if self.primary_button.isEnabled():
                    self._primary_action()
                event.accept()
                return True
            if event.key() in (Qt.Key_Tab, Qt.Key_Backtab) and modifiers in (
                Qt.NoModifier,
                Qt.ShiftModifier,
            ):
                if event.key() == Qt.Key_Backtab or modifiers & Qt.ShiftModifier:
                    self.focusPreviousChild()
                else:
                    self.focusNextChild()
                event.accept()
                return True
        if event.type() == QEvent.MouseButtonRelease and obj is self._input_viewport:
            if event.button() == Qt.LeftButton and not self.input_text.textCursor().hasSelection():
                position = self.input_text.cursorForPosition(event.pos()).position()
                index = self._finding_at_position(position)
                if index is not None:
                    self._selected_finding_index = index
                    self.findings_panel.select_finding(index)
                else:
                    self._selected_finding_index = None
                self._highlight_findings()
        elif event.type() == QEvent.KeyPress and obj is self.input_text and event.key() == Qt.Key_Escape:
            self._selected_finding_index = None
            self._highlight_findings()
        return super().eventFilter(obj, event)

    def _load_document_from_path(self, filename: str | Path) -> None:
        if not self._confirm_discard_work("Carica e scarta"):
            return
        document_path = Path(filename)

        def work(context: JobContext) -> LoadedDocument:
            return load_document(
                document_path,
                progress_callback=context.progress,
                cancel_check=context.check_cancelled,
            )

        def failed(exc: Exception) -> None:
            if isinstance(exc, OcrUnavailableError):
                self._show_ocr_setup_dialog(document_path)
                return
            self.statusBar().showMessage(self._friendly_error_message(exc), 9000)

        self._start_job(
            "load",
            f"Caricamento di {document_path.name}",
            work,
            self._apply_loaded_document,
            failed,
        )

    def _apply_loaded_document(self, document: LoadedDocument) -> None:
        self.loaded_document = document
        self.anonymized_document = None
        self.reversible_mapping = ()
        self._reversible_map_saved = True
        self._output_provenance = None
        self._output_stale_reason = ""
        self._output_saved = True
        self._review_dirty = False
        self._workflow_revision += 1
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
        self._set_output_text("")
        self.document_text_dirty = False
        self.output_text_dirty = False
        self._update_mode_notice()
        self._update_report()
        if self.loaded_document.extension == ".pdf":
            if self.loaded_document.ocr_pages:
                pages = ", ".join(str(page) for page in self.loaded_document.ocr_pages)
                self.document_label.setText(
                    f"PDF letto con OCR locale: {self.loaded_document.path.name} (pagine {pages}). "
                    "L'export creerà un PDF rasterizzato con oscuramenti permanenti."
                )
                self.statusBar().showMessage(
                    "PDF scansionato letto con OCR locale. Controlla sempre il risultato OCR prima di condividere. "
                    "Puoi escludere i dati rilevati con le caselle e aggiungere selezioni manuali; sulle scansioni "
                    "alcune esclusioni possono non applicarsi e il dato resta anonimizzato.",
                    8000,
                )
            else:
                self.document_label.setText(
                    f"PDF caricato: {self.loaded_document.path.name}. "
                    "Puoi mantenere il layout oppure convertirlo in testo."
                )
                self.statusBar().showMessage(
                    "PDF caricato. L'anonimizzazione salverà una copia redatta non selezionabile. "
                    "Per migliorare il riconoscimento usa Converti PDF in testo nel pannello dei dati.",
                    7000,
                )
        elif self.loaded_document.extension == ".docx":
            self.document_label.setText(f"Documento caricato: {self.loaded_document.path.name}")
            self.statusBar().showMessage(
                "Documento caricato. Puoi escludere i dati rilevati con le caselle e aggiungere selezioni manuali.",
                7000,
            )
        elif self.loaded_document.extension == ".doc":
            self.document_label.setText(f"Documento caricato: {self.loaded_document.path.name}")
            self.statusBar().showMessage(
                "Documento caricato. Per il formato .doc la selezione non è supportata: "
                "verrà anonimizzato tutto ciò che viene rilevato.",
                7000,
            )
        else:
            self.document_label.setText(f"Documento caricato: {self.loaded_document.path.name}")
            self.statusBar().showMessage(
                "Documento caricato. Modalità Standard attiva: rivedi i dati rilevati prima di condividere il risultato.",
                5000,
            )
        self.findings_panel.set_document_notice(
            "pdf"
            if self.loaded_document.extension == ".pdf"
            else "unsupported"
            if not self._manual_add_supported()
            else None
        )
        self._sync_action_state()

    def _tesseract_install_command(self, system: str) -> str:
        if system == "Darwin":
            return "brew install tesseract tesseract-lang"
        return "sudo apt install tesseract-ocr tesseract-ocr-ita"

    def _show_ocr_setup_dialog(self, path: Path) -> None:
        system = platform.system()
        dialog = QDialog(self)
        dialog.setObjectName("InfoDialog")
        dialog.setWindowTitle("Serve OCR locale per leggere questo PDF")
        dialog.setModal(True)
        dialog.setMinimumWidth(460)

        heading = QLabel("Questo PDF contiene immagini")
        heading.setObjectName("AboutDetails")
        heading.setStyleSheet("font-weight: 700; font-size: 15px;")

        explanation = QLabel(
            "Un'immagine nel documento (una scansione, un timbro, un logo) potrebbe contenere dati "
            "personali. Per controllarla in sicurezza OMISSIS usa Tesseract, un motore OCR che gira "
            "interamente sul tuo computer: nessun contenuto lascia il dispositivo."
        )
        explanation.setObjectName("AboutDetails")
        explanation.setWordWrap(True)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(14)
        layout.addWidget(heading)
        layout.addWidget(explanation)

        if system == "Windows":
            instructions = QLabel(
                "1. Scarica l'installer di Tesseract per Windows dalla pagina ufficiale UB Mannheim.<br>"
                "2. Esegui l'installer (impostazioni predefinite vanno bene; includi la lingua italiana "
                "se richiesto).<br>"
                "3. Riavvia OMISSIS e riprova a caricare il PDF."
            )
            instructions.setObjectName("AboutDetails")
            instructions.setTextFormat(Qt.RichText)
            instructions.setWordWrap(True)
            layout.addWidget(instructions)

            download_button = QPushButton("Apri pagina di download")
            download_button.setObjectName("SecondaryButton")
            download_button.clicked.connect(
                lambda: QDesktopServices.openUrl(QUrl(TESSERACT_WINDOWS_DOWNLOAD_URL))
            )
            layout.addWidget(download_button)
        else:
            command = self._tesseract_install_command(system)
            step_label = (
                "1. Apri il Terminale e incolla questo comando:"
                if system == "Darwin"
                else "1. Apri un terminale e incolla questo comando:"
            )
            instructions = QLabel(step_label)
            instructions.setObjectName("AboutDetails")
            instructions.setWordWrap(True)
            layout.addWidget(instructions)

            command_field = QLineEdit(command)
            command_field.setObjectName("CommandField")
            command_field.setReadOnly(True)
            layout.addWidget(command_field)

            copy_button = QPushButton("Copia comando")
            copy_button.setObjectName("SecondaryButton")

            def _copy_command() -> None:
                QApplication.clipboard().setText(command)
                copy_button.setText("Copiato ✓")

            copy_button.clicked.connect(_copy_command)
            layout.addWidget(copy_button)

            final_step = QLabel("2. Riavvia OMISSIS e riprova a caricare il PDF.")
            final_step.setObjectName("AboutDetails")
            final_step.setWordWrap(True)
            layout.addWidget(final_step)

        button_row = QHBoxLayout()
        close_button = QPushButton("Chiudi")
        close_button.setObjectName("SecondaryButton")
        close_button.clicked.connect(dialog.reject)

        retry_button = QPushButton("Ho installato, riprova")
        retry_button.setObjectName("PrimaryButton")
        retry_button.clicked.connect(dialog.accept)

        button_row.addWidget(close_button)
        button_row.addStretch(1)
        button_row.addWidget(retry_button)
        layout.addLayout(button_row)

        dialog.setLayout(layout)
        dialog.setStyleSheet(APP_STYLE)
        if dialog.exec() == QDialog.Accepted:
            self._load_document_from_path(path)

    def analyze_text(self) -> None:
        self._start_analysis(record_activity=True)

    def _start_analysis(self, *, after_success=None, record_activity: bool = False) -> bool:
        text = self.input_text.toPlainText()
        if not text.strip():
            self.statusBar().showMessage("Incolla un testo o carica un documento prima di analizzare.", 5000)
            return False
        mode = self._selected_mode()

        def work(context: JobContext) -> AnalysisOutcome:
            return analyze_text_workflow(self.engine, text, mode, context)

        def succeeded(outcome: AnalysisOutcome) -> None:
            if self.input_text.toPlainText() != outcome.source_text or self._selected_mode() != outcome.mode:
                self.statusBar().showMessage(
                    "Il testo o la modalità sono cambiati: il risultato dell'analisi è stato ignorato.",
                    6000,
                )
                return
            self._apply_analysis_outcome(outcome)
            if record_activity:
                self._record_activity("analysis", mode=outcome.mode)
            self.statusBar().showMessage(f"Elementi rilevati: {len(self.findings)}.", 4000)
            if after_success is not None:
                after_success()

        return self._start_job(
            "analysis",
            "Analisi dei dati sensibili",
            work,
            succeeded,
            lambda exc: self.statusBar().showMessage(
                f"Non riesco ad analizzare il testo: {exc}",
                9000,
            ),
        )

    def _apply_analysis_outcome(self, outcome: AnalysisOutcome) -> None:
        self.findings = list(outcome.findings)
        self.findings_stale = False
        self._findings_source_text = outcome.source_text
        self._findings_mode = outcome.mode
        self._fill_table()
        self._highlight_findings()
        self._focus_review_workspace()
        self._update_report()
        self._sync_action_state()

    def anonymize_text(self) -> None:
        mode = self._selected_mode()
        source_text = self.input_text.toPlainText()
        if not source_text.strip():
            self.statusBar().showMessage("Incolla un testo o carica un documento prima di anonimizzare.", 5000)
            return
        if self.reversible_mapping and not self._reversible_map_saved:
            if not self._confirm_discard_work(
                "Rigenera senza la mappa",
                include_source=False,
                include_review=False,
                include_output=False,
            ):
                return
        if not self._findings_ready_for_filtering():
            self._start_analysis(after_success=self.anonymize_text)
            return

        loaded_document = self.loaded_document if self.loaded_document and not self.document_text_dirty else None
        manual_add_supported = self._manual_add_supported()
        filtered_findings = self._checked_findings()
        excluded_values: frozenset[tuple[str, str]] | None = None
        if loaded_document is not None and self._value_level_selection_active():
            pairs = excluded_value_pairs(
                source_text,
                self.findings,
                self.findings_panel.included_mask(),
            )
            excluded_values = pairs or None
        manual_pairs = frozenset(
            (finding.entity_type, source_text[finding.start : finding.end])
            for row, finding in enumerate(self.findings)
            if finding.source == "manual" and self._is_row_checked(row)
        )
        request = AnonymizationRequest(
            source_text=source_text,
            mode=mode,
            loaded_document=loaded_document,
            reversible_entries=self.loaded_reversible_entries,
            findings=tuple(filtered_findings),
            findings_were_reviewed=True,
            selected_total=len(self.findings),
            selected_included=len(filtered_findings),
            excluded_values=excluded_values,
            extra_values=manual_pairs or None,
        )
        source_revision = self._workflow_revision

        def work(context: JobContext) -> AnonymizationOutcome:
            return anonymize_workflow(self.engine, request, context)

        def succeeded(outcome: AnonymizationOutcome) -> None:
            if self._workflow_revision != source_revision:
                self.statusBar().showMessage(
                    "Le scelte sono cambiate: il risultato dell'anonimizzazione è stato ignorato.",
                    6000,
                )
                return
            self._apply_anonymization_outcome(
                outcome,
                source_text=source_text,
                used_document=loaded_document is not None,
                manual_add_supported=manual_add_supported,
            )

        def failed(exc: Exception) -> None:
            if isinstance(exc, OcrUnavailableError) and loaded_document is not None:
                self._show_ocr_setup_dialog(loaded_document.path)
                return
            self.statusBar().showMessage(self._friendly_processing_error_message(exc), 10000)

        self._start_job(
            "anonymization",
            "Anonimizzazione in corso",
            work,
            succeeded,
            failed,
        )

    def _apply_anonymization_outcome(
        self,
        outcome: AnonymizationOutcome,
        *,
        source_text: str,
        used_document: bool,
        manual_add_supported: bool,
    ) -> None:
        self.anonymized_document = outcome.document
        self.reversible_mapping = outcome.mapping
        if used_document:
            self.findings = list(outcome.findings)
            self.findings_stale = False
            self._findings_source_text = source_text
            self._findings_mode = outcome.mode
            self._fill_table()
            self._highlight_findings()
        else:
            self.loaded_document = None
            self.document_text_dirty = False
        self._set_output_text(outcome.output_text)
        self._mark_output_generated(
            outcome.mode,
            total_findings=outcome.total_findings,
            included_findings=outcome.included_findings,
        )
        self._record_activity("anonymization", output_data=outcome.output_data, mode=outcome.mode)

        if outcome.document is not None:
            unsupported_note = (
                " Per aggiungere selezioni manuali usa Estrai come testo." if not manual_add_supported else ""
            )
            if self.reversible_mapping:
                self.statusBar().showMessage(
                    f"Documento pronto: {outcome.document.filename}. "
                    f"Salva anche la mappa reversibile.{unsupported_note}",
                    7000,
                )
            else:
                self.statusBar().showMessage(
                    f"Documento pronto: {outcome.document.filename}. "
                    f"Elementi rilevati: {len(self.findings)}.{unsupported_note}",
                    5000,
                )
        elif self.reversible_mapping:
            self.statusBar().showMessage(
                "Testo reversibile pronto. Salva la mappa locale prima di usare ChatGPT.",
                7000,
            )
        else:
            self.statusBar().showMessage("Testo anonimizzato pronto.", 4000)
        self._sync_action_state()

    def copy_output(self) -> None:
        if self._managed_output_is_stale():
            self.statusBar().showMessage(
                "Il risultato non è più coerente con le scelte correnti. Rigeneralo prima di copiarlo.",
                6000,
            )
            return
        if not self.output_text.toPlainText().strip():
            self.statusBar().showMessage("Anonimizza prima un testo o un documento.", 4000)
            return
        QApplication.clipboard().setText(self.output_text.toPlainText())
        self.statusBar().showMessage("Risultato copiato negli appunti.", 3000)

    def save_output(self) -> None:
        if self._managed_output_is_stale():
            self.statusBar().showMessage(
                "Il risultato non è più coerente con le scelte correnti. Rigeneralo prima di salvarlo.",
                6000,
            )
            return
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
        try:
            if use_document_binary and (expected_suffix not in {".txt", ".csv"} or not output_pane_text.strip()):
                atomic_write_bytes(target_path, self.anonymized_document.data)
            else:
                atomic_write_text(target_path, output_pane_text)
        except OSError as exc:
            self.statusBar().showMessage(f"Salvataggio non riuscito: {exc}", 8000)
            return

        self._output_saved = True
        self._record_activity(
            "save",
            output_path=target_path,
            mode=self._output_provenance.mode if self._output_provenance is not None else None,
        )
        self._update_report()
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

        self._reversible_map_saved = True
        self._update_report()
        self._sync_action_state()
        self.statusBar().showMessage(f"Mappa reversibile salvata: {target_path}", 6000)

    def load_reversible_map(self) -> None:
        if not self._confirm_discard_work(
            "Sostituisci mappa",
            include_source=False,
            include_review=False,
            include_output=False,
        ):
            return
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
        self._reversible_map_saved = True
        if self._selected_mode() == "reversible":
            self._mark_workflow_changed("la mappa reversibile")
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

        self.anonymized_document = None
        self.reversible_mapping = ()
        self._reversible_map_saved = True
        self._set_output_text(restore_text(source_text, mapping))
        self._mark_output_generated(
            "reversible",
            total_findings=0,
            included_findings=0,
            kind="restored",
        )
        self.statusBar().showMessage("Testo ricostruito localmente dalla mappa.", 5000)

    def clear_all(self, force: bool = False) -> None:
        if not force and not self._confirm_discard_work("Pulisci e scarta"):
            return
        self._output_provenance = None
        self._output_stale_reason = ""
        self._output_saved = True
        self._reversible_map_saved = True
        self._review_dirty = False
        self._workflow_revision += 1
        self.input_text.clear()
        self._set_output_text("")
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
        self._update_report()
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
        entity_type = entity_by_label[label]

        if not self._findings_ready_for_filtering():
            self._start_analysis(
                after_success=lambda: self._apply_manual_finding(start, end, entity_type),
            )
            return
        self._apply_manual_finding(start, end, entity_type)

    def _apply_manual_finding(self, start: int, end: int, entity_type: str) -> None:
        source_text = self.input_text.toPlainText()
        if not (0 <= start < end <= len(source_text)):
            self.statusBar().showMessage("La selezione non è più valida: seleziona di nuovo il testo.", 5000)
            return
        value = source_text[start:end]
        # Espandi la selezione a ogni occorrenza letterale del valore: una selezione
        # manuale (es. "Potenza") va redatta ovunque compaia, non solo dove è stata
        # evidenziata. Se l'intervallo era già stato rilevato automaticamente, la
        # scelta esplicita dell'utente prevale senza ridurre un finding più ampio.
        exact_spans: set[tuple[int, int]] = set()
        occurrence_start = 0
        while True:
            occurrence_start = source_text.find(value, occurrence_start)
            if occurrence_start == -1:
                break
            exact_spans.add((occurrence_start, occurrence_start + len(value)))
            occurrence_start += 1
        automatic_findings = [
            finding
            for finding in self.findings
            if (finding.start, finding.end) not in exact_spans
        ]
        expanded = add_extra_value_findings(
            source_text,
            automatic_findings,
            frozenset({(entity_type, value)}),
        )
        self.findings = self.engine._recognizer.dedupe(expanded)
        self.findings_stale = False
        self._findings_source_text = source_text
        self._findings_mode = self._selected_mode()
        self._fill_table()
        self._highlight_findings()
        self._review_dirty = True
        self._mark_workflow_changed("le selezioni manuali")
        self._update_report()
        self._sync_action_state()
        self.statusBar().showMessage(f"Aggiunto manualmente: {entity_label(entity_type)}.", 4000)

    def _fill_table(self) -> None:
        source_text = self.input_text.toPlainText()
        self.findings_panel.set_findings(
            self.findings,
            source_text,
            self._selection_filter_supported(),
            value_level=self._value_level_selection_active(),
        )
        self.setTabOrder(self.findings_panel.search_edit, self.findings_panel.tree)
        self.setTabOrder(self.findings_panel.tree, self.primary_button)
        notice_kind = None
        if self.loaded_document is not None and not self.document_text_dirty:
            if self.loaded_document.extension == ".pdf":
                notice_kind = "pdf"
            elif not self._manual_add_supported():
                notice_kind = "unsupported"
        self.findings_panel.set_document_notice(notice_kind)

    def _highlight_findings(self) -> None:
        selections = []
        for row, finding in enumerate(self.findings):
            if not self._is_row_checked(row):
                continue
            color = QColor(entity_color(finding.entity_type))
            color.setAlpha(
                FINDING_SELECTED_HIGHLIGHT_ALPHA
                if row == self._selected_finding_index
                else FINDING_HIGHLIGHT_ALPHA
            )
            char_format = QTextCharFormat()
            char_format.setBackground(color)
            char_format.setForeground(QColor(EDITOR_SELECTION_TEXT_COLOR))
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
            len(self.findings_panel.included_mask()) == len(self.findings)
            and not self.findings_stale
            and self._findings_source_text == self.input_text.toPlainText()
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
        self._review_dirty = True
        self._mark_workflow_changed("i dati selezionati")
        self._sync_action_state()
        self._highlight_findings()

    def _handle_selection_cleared(self) -> None:
        self._selected_finding_index = None
        self._highlight_findings()

    def _extract_document_as_text(self) -> None:
        if not self._confirm_discard_work(
            "Converti e scarta",
            include_source=False,
        ):
            return
        loaded_document = self.loaded_document
        source_text = self.input_text.toPlainText()
        converted_pdf = loaded_document is not None and loaded_document.extension == ".pdf"
        if converted_pdf:
            source_text = normalize_pdf_text_for_llm(source_text)

        self.loaded_document = None
        self.anonymized_document = None
        self.document_text_dirty = False
        self.output_text_dirty = False
        self.reversible_mapping = ()
        self._reversible_map_saved = True
        self._output_provenance = None
        self._output_stale_reason = ""
        self._output_saved = True
        self._review_dirty = False
        self._workflow_revision += 1
        self.findings = []
        self.findings_stale = True
        self._findings_source_text = None
        self._findings_mode = None
        signal_blocker = QSignalBlocker(self.input_text)
        try:
            self.input_text.setPlainText(source_text)
        finally:
            del signal_blocker
        self._set_output_text("")
        self.document_label.setText(
            "PDF convertito in testo: righe e sillabazioni ricomposte; "
            "il salvataggio sarà in .txt."
            if converted_pdf
            else "Contenuto estratto come testo: la selezione manuale è attiva, "
            "il salvataggio sarà in .txt."
        )
        if source_text.strip():
            self._start_analysis()
        else:
            self.findings_panel.clear()
        self.findings_panel.set_document_notice(None)
        self._update_report()
        self._sync_action_state()
        self.statusBar().showMessage(
            "PDF convertito e rianalizzato come testo. Il risultato verrà salvato in .txt."
            if converted_pdf
            else "Contenuto estratto come testo modificabile.",
            5000,
        )

    def _selection_filter_supported(self) -> bool:
        """Le caselle di esclusione sono attive: per testo/testo estratto (per occorrenza)
        e per .docx/.pdf caricati (per valore esatto)."""
        if self.loaded_document is None or self.document_text_dirty:
            return True
        return self.loaded_document.extension in {".txt", ".md", ".csv", ".docx", ".pdf"}

    def _manual_add_supported(self) -> bool:
        """Il bottone "Aggiungi selezione" è supportato per i formati testuali e per
        .docx/.pdf: la pipeline documento redige ogni occorrenza letterale del valore
        selezionato tramite extra_values. Resta escluso il solo .doc legacy."""
        if self.loaded_document is None or self.document_text_dirty:
            return True
        return self.loaded_document.extension in {".txt", ".md", ".csv", ".docx", ".pdf"}

    def _value_level_selection_active(self) -> bool:
        """True quando le esclusioni si applicano per valore esatto (documento .docx/.pdf caricato)."""
        return (
            self.loaded_document is not None
            and not self.document_text_dirty
            and self.loaded_document.extension in {".docx", ".pdf"}
        )

    def _document_filter(self) -> str:
        extensions = "*.txt *.md *.csv *.docx *.pdf"
        if LEGACY_DOC_SUPPORTED:
            extensions = "*.txt *.md *.csv *.doc *.docx *.pdf"
        return f"Documenti supportati ({extensions});;Tutti i file (*.*)"

    def _source_fingerprint(self) -> str:
        return source_fingerprint(self.input_text.toPlainText())

    def _selection_fingerprint(self) -> str:
        return selection_fingerprint(self.findings, self.findings_panel.included_mask())

    def _has_output(self) -> bool:
        if self.output_text.toPlainText().strip():
            return True
        return self.anonymized_document is not None and not self.output_text_dirty

    def _managed_output_is_stale(self) -> bool:
        return (
            self._output_provenance is not None
            and self._has_output()
            and self._output_provenance.revision != self._workflow_revision
        )

    def _output_is_usable(self) -> bool:
        return self._has_output() and not self._managed_output_is_stale()

    def _mark_workflow_changed(self, reason: str) -> None:
        self._workflow_revision += 1
        if self._output_provenance is not None and self._has_output():
            self._output_stale_reason = reason
        self._update_report()

    def _output_format_label(self) -> str:
        if self.anonymized_document is None or self.output_text_dirty:
            return "TXT"
        suffix = Path(self.anonymized_document.filename).suffix.lower()
        return {
            ".csv": "CSV",
            ".docx": "DOCX",
            ".pdf": "PDF rasterizzato",
            ".txt": "TXT",
        }.get(suffix, suffix.removeprefix(".").upper() or "TXT")

    def _mark_output_generated(
        self,
        mode: AnonymizationMode,
        *,
        total_findings: int,
        included_findings: int,
        kind: str = "anonymized",
    ) -> None:
        used_ocr = bool(self.loaded_document and self.loaded_document.ocr_pages)
        self._output_provenance = OutputProvenance(
            revision=self._workflow_revision,
            mode=mode,
            source_sha256=self._source_fingerprint(),
            selection_sha256=self._selection_fingerprint(),
            total_findings=total_findings,
            included_findings=included_findings,
            output_format=self._output_format_label(),
            used_ocr=used_ocr,
            map_required=bool(self.reversible_mapping),
            kind=kind,
        )
        self._output_stale_reason = ""
        self._output_saved = False
        self._reversible_map_saved = (
            not bool(self.reversible_mapping)
            or self.reversible_mapping == self.loaded_reversible_entries
        )
        self._review_dirty = False
        self._update_report()
        self._sync_action_state()

    def _clear_output_state(self) -> None:
        self._output_provenance = None
        self._output_stale_reason = ""
        self._output_saved = True
        self.anonymized_document = None
        self._set_output_text("")
        self._update_report()

    def _selected_mode(self) -> AnonymizationMode:
        for mode, radio in self.mode_radios.items():
            if radio.isChecked():
                return validate_anonymization_mode(mode)
        return "standard"

    def _handle_mode_toggled(self, checked: bool) -> None:
        if not checked:
            return
        selected_mode = self._selected_mode()
        if selected_mode != self._last_selected_mode:
            self._last_selected_mode = selected_mode
            self._mark_workflow_changed("la modalità di protezione")
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
        self._refresh_mode_cards()
        if self._output_provenance is None:
            self.report_label.setText(mode_note(self._selected_mode()))

    def _update_report(self) -> None:
        provenance = self._output_provenance
        if provenance is None or not self._has_output():
            self.report_label.setObjectName("ReportNotice")
            self.report_label.setText("")
            self.report_label.setAccessibleName("Verifica finale")
            self.report_label.setAccessibleDescription("")
            return

        if self._managed_output_is_stale():
            reason = self._output_stale_reason or "i dati di partenza"
            self.report_label.setObjectName("ReportNoticeStale")
            self.report_label.setAccessibleName("Risultato da rigenerare")
            self.report_label.setText(
                f"Risultato da rigenerare: hai modificato {reason}. "
                "Questa anteprima non può essere copiata o salvata finché non esegui di nuovo "
                "l'analisi e l'anonimizzazione."
            )
        elif provenance.kind == "restored":
            self.report_label.setObjectName("ReportNotice")
            self.report_label.setAccessibleName("Testo ricostruito")
            self.report_label.setText(
                "Testo ricostruito localmente con una mappa cifrata. "
                "Contiene nuovamente i dati originali: conservalo e condividilo con cautela."
            )
        else:
            excluded = provenance.excluded_findings
            details: list[str] = []
            if provenance.map_required:
                details.append(
                    "Mappa reversibile salvata"
                    if self._reversible_map_saved
                    else "Mappa reversibile ancora da salvare"
                )
            if provenance.used_ocr:
                details.append("OCR locale usato: verifica anche il testo riconosciuto")
            if self.output_text_dirty:
                details.append("Risultato modificato manualmente: il salvataggio sarà in TXT")
            state_label = "salvato" if self._output_saved else "da salvare"
            self.report_label.setObjectName("ReportNotice")
            self.report_label.setAccessibleName("Verifica finale")
            detail_line = f"\nAttenzione: {' · '.join(details)}." if details else ""
            self.report_label.setText(
                "Verifica finale\n"
                f"Anonimizzati: {provenance.included_findings}/{provenance.total_findings} "
                f"· Esclusi: {excluded} · Modalità: {mode_label(provenance.mode)} "
                f"· Formato: {provenance.output_format} · Stato: {state_label}."
                f"{detail_line}\n"
                "Rileggi il risultato prima di condividerlo."
            )
        self.report_label.setAccessibleDescription(self.report_label.text())
        self.report_label.style().unpolish(self.report_label)
        self.report_label.style().polish(self.report_label)

    def _primary_state(self) -> tuple[str, str, bool]:
        """Return (action_kind, button_label, enabled) for the single step-aware primary button."""
        input_has_text = bool(self.input_text.toPlainText().strip())
        output_has_text = bool(self.output_text.toPlainText().strip())
        if self._output_is_usable():
            return "copy", "Copia risultato", output_has_text
        if self._findings_ready_for_filtering() and input_has_text:
            count = len(self._checked_findings())
            if count == 0:
                label = "Conferma e genera senza sostituzioni"
            elif self._managed_output_is_stale():
                label = f"Conferma e rigenera {count} dato" if count == 1 else f"Conferma e rigenera {count} dati"
            else:
                label = (
                    f"Conferma selezione e anonimizza {count} dato"
                    if count == 1
                    else f"Conferma selezione e anonimizza {count} dati"
                )
            return "anonymize", label, input_has_text
        label = "Rianalizza dati" if self._managed_output_is_stale() else "Analizza dati"
        return "analyze", label, input_has_text

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
        has_anything = (
            input_has_text
            or output_has_text
            or self.loaded_document is not None
            or bool(self.reversible_mapping)
        )
        output_usable = self._output_is_usable()
        output_stale = self._managed_output_is_stale()
        busy = self._active_job is not None
        kind, label, primary_enabled = self._primary_state()
        self.primary_button.setText(label)
        self.primary_button.setAccessibleName(label)
        primary_descriptions = {
            "analyze": "Analizza il testo corrente e prepara i dati rilevati per la revisione.",
            "anonymize": "Conferma le spunte correnti e genera un nuovo risultato anonimizzato.",
            "copy": "Copia negli appunti il risultato anonimizzato verificato.",
        }
        self.primary_button.setAccessibleDescription(primary_descriptions[kind])
        if hasattr(self, "primary_action"):
            self.primary_action.setText(label)
        self.primary_button.setEnabled(primary_enabled and not busy)
        self.load_button.setEnabled(not busy)
        self.copy_button.setEnabled(output_has_text and output_usable and not busy)
        self.save_button.setEnabled(output_usable and not busy)
        self.clear_button.setEnabled(has_anything and not busy)
        self.add_selection_button.setEnabled(input_has_text and self._manual_add_supported() and not busy)
        self.input_text.setReadOnly(busy)
        self.output_text.setEnabled(not output_stale and not busy)
        self.findings_panel.setEnabled(not busy)
        for radio in self.mode_radios.values():
            radio.setEnabled(not busy)
        self.output_text.setToolTip(
            "Il risultato è obsoleto: rianalizza e rigenera prima di copiarlo o salvarlo."
            if output_stale
            else ""
        )
        if hasattr(self, "save_map_action"):
            self.save_map_action.setEnabled(bool(self.reversible_mapping) and not busy)
            self.load_map_action.setEnabled(not busy)
            self.restore_map_action.setEnabled(not busy)
            self.open_action.setEnabled(not busy)
            self.copy_output_action.setEnabled(output_has_text and output_usable and not busy)
            self.save_output_action.setEnabled(output_usable and not busy)
            self.primary_action.setEnabled(primary_enabled and not busy)
            self.focus_search_action.setEnabled(input_has_text and not busy)
            self.activity_action.setEnabled(not busy)
        self._update_map_status()
        self._update_workflow_steps()

    def _update_map_status(self) -> None:
        if self.reversible_mapping and not self._reversible_map_saved:
            label = f"Mappa da salvare · {len(self.reversible_mapping)} voci"
            object_name = "MapStatusWarning"
        elif self.reversible_mapping and self.loaded_reversible_entries == self.reversible_mapping:
            label = f"Mappa caricata · {len(self.reversible_mapping)} voci"
            object_name = "MapStatusReady"
        elif self.reversible_mapping:
            label = f"Mappa salvata · {len(self.reversible_mapping)} voci"
            object_name = "MapStatusReady"
        else:
            label = "Nessuna mappa attiva"
            object_name = "MapStatus"
        self.map_status_label.setText(label)
        self.map_status_label.setAccessibleDescription(label)
        if self.map_status_label.objectName() != object_name:
            self.map_status_label.setObjectName(object_name)
            self.map_status_label.style().unpolish(self.map_status_label)
            self.map_status_label.style().polish(self.map_status_label)
        show_map_status = (
            self._selected_mode() == "reversible"
            or bool(self.reversible_mapping)
            or bool(self.loaded_reversible_entries)
        )
        self.map_section_label.setVisible(show_map_status)
        self.map_status_label.setVisible(show_map_status)

    def _workflow_step_states(self) -> list[str]:
        step1_done = self.loaded_document is not None or bool(self.input_text.toPlainText().strip())
        step2_done = (
            step1_done
            and not self.findings_stale
            and self._findings_source_text == self.input_text.toPlainText()
            and self._findings_mode == self._selected_mode()
        )
        has_manual_finding = any(finding.source == "manual" for finding in self.findings)
        step4_done = self._output_is_usable()

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
                self._mark_workflow_changed("il testo sorgente")
        self._sync_action_state()

    def _handle_output_text_changed(self) -> None:
        if not self._updating_output_text:
            self.output_text_dirty = True
            self._output_saved = not bool(self.output_text.toPlainText().strip())
            if not self._has_output():
                self._output_provenance = None
                self._output_stale_reason = ""
            self._update_report()
        self._sync_action_state()

    def _set_output_text(self, text: str) -> None:
        self._updating_output_text = True
        try:
            self.output_text.setPlainText(text)
        finally:
            self._updating_output_text = False
        self.output_text_dirty = False
        if text.strip():
            self._show_result_workspace()
        elif not self._findings_ready_for_filtering():
            self._show_input_workspace()
        self._sync_action_state()

    def _record_activity(
        self,
        action: ActivityAction,
        *,
        output_path: str | Path | None = None,
        output_data: bytes | None = None,
        mode: AnonymizationMode | None = None,
    ) -> None:
        if not load_activity_settings().enabled:
            return
        source_is_document = self.loaded_document is not None and not self.document_text_dirty
        try:
            entry = build_activity_entry(
                action=action,
                source_kind="document" if source_is_document else "pasted_text",
                mode=mode or self._selected_mode(),
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
