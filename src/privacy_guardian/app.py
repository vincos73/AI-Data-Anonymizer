from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QSettings, QSignalBlocker, QSize, QThreadPool, QTimer, Qt, QUrl, Slot
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
    QComboBox,
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
    QSizePolicy,
    QSplitter,
    QStackedWidget,
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
    REVERSIBLE_DOCUMENT_EXTENSIONS,
    AnonymizedDocument,
    LoadedDocument,
    OcrUnavailableError,
    add_extra_value_findings,
    casefolded_literal_spans,
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
    PLACEHOLDER_PATTERN,
    ReversibleAnonymizer,
    ReversibleMapEntry,
    ReversibleMapError,
    read_encrypted_mapping,
    restore_text,
    write_encrypted_mapping,
)
from privacy_guardian.reporting import (
    ENTITY_LABELS,
    entity_label,
    finding_counts,
    mode_label,
    mode_note,
    report_text,
)
from privacy_guardian.styles import (
    APP_STYLE,
    EDITOR_BACKGROUND_COLOR,
    EDITOR_PLACEHOLDER_COLOR,
    EDITOR_SELECTION_BACKGROUND_COLOR,
    EDITOR_SELECTION_TEXT_COLOR,
    EDITOR_TEXT_COLOR,
    FINDING_HIGHLIGHT_ALPHA,
    FINDING_SELECTED_HIGHLIGHT_ALPHA,
    PAPER_EDITOR_BACKGROUND_COLOR,
    PAPER_EDITOR_PLACEHOLDER_COLOR,
    PAPER_EDITOR_SELECTION_BACKGROUND_COLOR,
    PAPER_EDITOR_SELECTION_TEXT_COLOR,
    PAPER_EDITOR_TEXT_COLOR,
    PAPER_FINDING_HIGHLIGHT_ALPHA,
    PAPER_FINDING_SELECTED_HIGHLIGHT_ALPHA,
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
DOCUMENT_APPEARANCE_SETTING = "document/appearance"
DOCUMENT_APPEARANCE_DARK = "dark"
DOCUMENT_APPEARANCE_PAPER = "paper"
DOCUMENT_APPEARANCES = frozenset(
    {DOCUMENT_APPEARANCE_DARK, DOCUMENT_APPEARANCE_PAPER}
)


def _ui_settings() -> QSettings:
    override_path = os.environ.get("OMISSIS_UI_SETTINGS_PATH", "").strip()
    if override_path:
        return QSettings(override_path, QSettings.IniFormat)
    return QSettings("Vincos", "OMISSIS")


def _apply_text_editor_appearance(editor: QTextEdit, appearance: str) -> None:
    if appearance == DOCUMENT_APPEARANCE_PAPER:
        colors = {
            QPalette.Base: PAPER_EDITOR_BACKGROUND_COLOR,
            QPalette.Text: PAPER_EDITOR_TEXT_COLOR,
            QPalette.PlaceholderText: PAPER_EDITOR_PLACEHOLDER_COLOR,
            QPalette.Highlight: PAPER_EDITOR_SELECTION_BACKGROUND_COLOR,
            QPalette.HighlightedText: PAPER_EDITOR_SELECTION_TEXT_COLOR,
        }
    else:
        appearance = DOCUMENT_APPEARANCE_DARK
        colors = {
            QPalette.Base: EDITOR_BACKGROUND_COLOR,
            QPalette.Text: EDITOR_TEXT_COLOR,
            QPalette.PlaceholderText: EDITOR_PLACEHOLDER_COLOR,
            QPalette.Highlight: EDITOR_SELECTION_BACKGROUND_COLOR,
            QPalette.HighlightedText: EDITOR_SELECTION_TEXT_COLOR,
        }

    editor.setProperty("documentAppearance", appearance)
    for target in (editor, editor.viewport()):
        palette = target.palette()
        for role, color in colors.items():
            palette.setColor(role, QColor(color))
        target.setPalette(palette)

    blocker = QSignalBlocker(editor)
    text_color = QColor(colors[QPalette.Text])
    editor.setTextColor(text_color)
    if not editor.document().isEmpty():
        cursor = QTextCursor(editor.document())
        cursor.select(QTextCursor.Document)
        text_format = QTextCharFormat()
        text_format.setForeground(text_color)
        cursor.mergeCharFormat(text_format)
    del blocker

    # Dynamic QSS properties are not automatically repolished by every native
    # Qt style. Refresh both surfaces so the change is immediate on macOS and
    # Windows without recreating the editors or losing their scroll position.
    for target in (editor, editor.viewport()):
        target.style().unpolish(target)
        target.style().polish(target)
        target.update()


def _configure_text_editor(
    editor: QTextEdit,
    *,
    reading_text: bool = False,
    appearance: str = DOCUMENT_APPEARANCE_DARK,
) -> None:
    """Make the dark editor palette explicit across native Qt styles.

    Qt stylesheets paint the expected colors on macOS, but on Windows the
    QTextDocument and its viewport can retain the native light-theme palette.
    That leaves plain text black even though the editor surface is dark.
    Setting both palettes and the document's current text format avoids that
    platform-dependent fallback. Rich-text paste is disabled so pasted source
    cannot reintroduce an unreadable foreground color.
    """

    editor.setAcceptRichText(False)
    if reading_text:
        # These are the document panes, not general-purpose form fields: a
        # larger type size and more leading make long legal texts practical to
        # compare without changing the scale of the surrounding interface.
        editor.setStyleSheet("font-size: 16px; line-height: 1.55;")
    _apply_text_editor_appearance(editor, appearance)


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


class _EntityTypeComboBox(QComboBox):
    """Branded combo box with a platform-independent painted chevron."""

    def paintEvent(self, event: QEvent) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = painter.pen()
        pen.setColor(QColor("#D8E6F0"))
        pen.setWidthF(2.2)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        center_x = self.width() - 19
        center_y = self.height() // 2
        painter.drawLine(center_x - 5, center_y - 3, center_x, center_y + 2)
        painter.drawLine(center_x, center_y + 2, center_x + 5, center_y - 3)
        painter.end()


class _WarningBadge(QWidget):
    """Small painted warning mark that does not depend on the native icon theme."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("DiscardWarningIcon")
        self.setFixedSize(42, 42)
        self.setAccessibleName("Avviso")

    def paintEvent(self, event: QEvent) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#D9A13B"))
        painter.drawEllipse(1, 1, self.width() - 2, self.height() - 2)
        painter.setPen(QColor("#0D1218"))
        font = painter.font()
        font.setPixelSize(25)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignCenter, "!")
        painter.end()


class _EntityTypeDialog(QDialog):
    """Compact, branded chooser for classifying a manually selected value."""

    def __init__(
        self,
        labels: list[str],
        selected_text: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("EntityTypeDialog")
        self.setWindowTitle("Tipo di dato")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self.setMinimumWidth(500)

        title = QLabel("Classifica il dato")
        title.setObjectName("DialogTitle")

        close_button = QPushButton("×")
        close_button.setObjectName("DialogCloseButton")
        close_button.setAccessibleName("Chiudi")
        close_button.setFixedSize(30, 30)
        close_button.clicked.connect(self.reject)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(12)
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(close_button)

        excerpt = " ".join(selected_text.split())
        if len(excerpt) > 64:
            excerpt = f"{excerpt[:61].rstrip()}…"
        description = QLabel(
            f"Scegli come proteggere «{excerpt}». La scelta verrà applicata anche "
            "alle occorrenze con maiuscole o minuscole diverse."
        )
        description.setObjectName("DialogDetails")
        description.setTextFormat(Qt.PlainText)
        description.setWordWrap(True)

        field_label = QLabel("Tipo di dato")
        field_label.setObjectName("FieldLabel")

        self.entity_combo = _EntityTypeComboBox()
        self.entity_combo.setObjectName("EntityTypeCombo")
        self.entity_combo.addItems(labels)
        self.entity_combo.setAccessibleName("Tipo di dato selezionato")

        cancel_button = QPushButton("Annulla")
        cancel_button.setObjectName("SecondaryButton")
        cancel_button.clicked.connect(self.reject)

        add_button = QPushButton("Aggiungi")
        add_button.setObjectName("PrimaryButton")
        add_button.setDefault(True)
        add_button.clicked.connect(self.accept)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 4, 0, 0)
        actions.setSpacing(10)
        actions.addStretch(1)
        actions.addWidget(cancel_button)
        actions.addWidget(add_button)

        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(26, 22, 26, 24)
        content_layout.setSpacing(12)
        content_layout.addLayout(header)
        content_layout.addWidget(description)
        content_layout.addSpacing(4)
        content_layout.addWidget(field_label)
        content_layout.addWidget(self.entity_combo)
        content_layout.addSpacing(4)
        content_layout.addLayout(actions)

        surface = QFrame()
        surface.setObjectName("EntityTypeDialogSurface")
        surface.setLayout(content_layout)

        window_layout = QVBoxLayout()
        window_layout.setContentsMargins(1, 1, 1, 1)
        window_layout.addWidget(surface)
        self.setLayout(window_layout)
        self.setAccessibleName("Classifica il dato selezionato")
        self.setAccessibleDescription(description.text())
        self.setStyleSheet(APP_STYLE)
        self.setTabOrder(self.entity_combo, cancel_button)
        self.setTabOrder(cancel_button, add_button)

    def selected_label(self) -> str:
        return self.entity_combo.currentText()


class _DiscardWorkDialog(QDialog):
    """Branded confirmation that keeps the safe action as the keyboard default."""

    def __init__(
        self,
        action_label: str,
        items: list[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("DiscardWorkDialog")
        self.setWindowTitle("Modifiche non salvate")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self.setMinimumWidth(540)

        title = QLabel("Modifiche non salvate")
        title.setObjectName("DialogTitle")

        close_button = QPushButton("×")
        close_button.setObjectName("DialogCloseButton")
        close_button.setAccessibleName("Chiudi senza scartare")
        close_button.setFixedSize(30, 30)
        close_button.clicked.connect(self.reject)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(12)
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(close_button)

        warning_mark = _WarningBadge()

        message = QLabel("Questa azione eliminerebbe del lavoro non salvato.")
        message.setObjectName("DiscardMessage")
        message.setWordWrap(True)

        items_label = QLabel("\n".join(f"• {item}" for item in items))
        items_label.setObjectName("DiscardItems")
        items_label.setTextFormat(Qt.PlainText)
        items_label.setWordWrap(True)

        warning_copy = QVBoxLayout()
        warning_copy.setContentsMargins(0, 0, 0, 0)
        warning_copy.setSpacing(8)
        warning_copy.addWidget(message)
        warning_copy.addWidget(items_label)

        warning_row = QHBoxLayout()
        warning_row.setContentsMargins(0, 4, 0, 4)
        warning_row.setSpacing(16)
        warning_row.addWidget(warning_mark, 0, Qt.AlignTop)
        warning_row.addLayout(warning_copy, 1)

        self.cancel_button = QPushButton("Annulla")
        self.cancel_button.setObjectName("SecondaryButton")
        self.cancel_button.setDefault(True)
        self.cancel_button.clicked.connect(self.reject)
        self.cancel_button.setAccessibleDescription(
            "Chiude la finestra e conserva tutto il lavoro corrente."
        )

        self.discard_button = QPushButton(action_label)
        self.discard_button.setObjectName("DestructiveButton")
        self.discard_button.setAutoDefault(False)
        self.discard_button.clicked.connect(self.accept)
        self.discard_button.setAccessibleDescription(
            "Conferma la perdita del lavoro non salvato elencato nella finestra."
        )

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 6, 0, 0)
        actions.setSpacing(10)
        actions.addStretch(1)
        actions.addWidget(self.discard_button)
        actions.addWidget(self.cancel_button)

        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(26, 22, 26, 24)
        content_layout.setSpacing(16)
        content_layout.addLayout(header)
        content_layout.addLayout(warning_row)
        content_layout.addLayout(actions)

        surface = QFrame()
        surface.setObjectName("DiscardWorkDialogSurface")
        surface.setLayout(content_layout)

        window_layout = QVBoxLayout()
        window_layout.setContentsMargins(1, 1, 1, 1)
        window_layout.addWidget(surface)
        self.setLayout(window_layout)
        self.setAccessibleName("Conferma perdita del lavoro non salvato")
        self.setAccessibleDescription(
            "Lavoro che verrebbe eliminato: " + ", ".join(items) + "."
        )
        self.setStyleSheet(APP_STYLE)
        self.setTabOrder(self.cancel_button, self.discard_button)
        self.setTabOrder(self.discard_button, close_button)
        QTimer.singleShot(0, lambda: self.cancel_button.setFocus(Qt.OtherFocusReason))


class _AdaptiveToolbar(QFrame):
    def __init__(
        self,
        load_button: QPushButton,
        document_label: QLabel,
        copy_button: QPushButton,
        save_button: QPushButton,
        clear_button: QPushButton,
        add_selection_button: QPushButton,
        appearance_selector: QFrame,
        primary_button: QPushButton,
    ) -> None:
        super().__init__()
        self.setObjectName("DocumentToolbar")
        self._document_label = document_label
        self._primary_button = primary_button
        self._appearance_selector = appearance_selector
        self._secondary_buttons = (save_button, clear_button, add_selection_button)
        # These legacy shortcuts remain available through menu actions, but their
        # duplicate toolbar buttons stay hidden and owned by the toolbar.
        load_button.setParent(self)
        copy_button.setParent(self)
        load_button.setVisible(False)
        copy_button.setVisible(False)

        self._secondary_widget = QWidget(self)
        secondary_layout = QHBoxLayout()
        secondary_layout.setContentsMargins(0, 0, 0, 0)
        secondary_layout.setSpacing(8)
        for button in self._secondary_buttons:
            secondary_layout.addWidget(button)
        self._secondary_widget.setLayout(secondary_layout)

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
        for widget in (
            self._document_label,
            self._secondary_widget,
            self._appearance_selector,
            self._primary_button,
        ):
            self._grid.removeWidget(widget)

        for column in range(4):
            self._grid.setColumnStretch(column, 0)
        if compact:
            self._grid.addWidget(self._document_label, 0, 0, 1, 1, Qt.AlignVCenter)
            self._grid.addWidget(self._primary_button, 0, 1, 1, 1, Qt.AlignRight | Qt.AlignVCenter)
            self._grid.addWidget(
                self._appearance_selector,
                1,
                0,
                1,
                1,
                Qt.AlignLeft | Qt.AlignVCenter,
            )
            self._grid.addWidget(
                self._secondary_widget,
                1,
                1,
                1,
                1,
                Qt.AlignRight | Qt.AlignVCenter,
            )
        else:
            self._grid.addWidget(self._document_label, 0, 0, 1, 1, Qt.AlignVCenter)
            self._grid.addWidget(self._secondary_widget, 0, 1, 1, 1, Qt.AlignVCenter)
            self._grid.addWidget(self._appearance_selector, 0, 2, 1, 1, Qt.AlignVCenter)
            self._grid.addWidget(self._primary_button, 0, 3, 1, 1, Qt.AlignVCenter)
        self._grid.setColumnStretch(0, 1)
        self.sync_secondary_visibility()

    def sync_secondary_visibility(self) -> None:
        has_visible_secondary = any(not button.isHidden() for button in self._secondary_buttons)
        self._secondary_widget.setVisible(has_visible_secondary)
        self.setMinimumHeight(94 if self._compact else 56)
        self.updateGeometry()


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
        self._syncing_text_scroll = False
        self._text_scroll_alignment_pending = False
        self._analysis_preview_active = False
        self.reversible_mapping: tuple[ReversibleMapEntry, ...] = ()
        self.loaded_reversible_entries: tuple[ReversibleMapEntry, ...] = ()
        self._selected_finding_index: int | None = None
        self._workflow_revision = 0
        self._output_provenance: OutputProvenance | None = None
        self._output_stale_reason = ""
        self._output_saved = True
        self._reversible_map_saved = True
        self._reversible_map_path: Path | None = None
        self._restore_mapping: tuple[ReversibleMapEntry, ...] = ()
        self._review_dirty = False
        self._review_confirmed = False
        self._result_used = False
        self._reversible_copy_copied = False
        self._restored_ai_response = ""
        self._show_original_in_restored_comparison = False
        self._compact_height = False
        self._last_primary_phase = ""
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
        self._settings = _ui_settings()
        saved_appearance = str(
            self._settings.value(
                DOCUMENT_APPEARANCE_SETTING,
                DOCUMENT_APPEARANCE_DARK,
            )
        )
        self._document_appearance = (
            saved_appearance
            if saved_appearance in DOCUMENT_APPEARANCES
            else DOCUMENT_APPEARANCE_DARK
        )

        self.setWindowTitle("OMISSIS")
        self.resize(1160, 760)
        self.setMinimumSize(QSize(960, 640))
        self.setAcceptDrops(True)

        self.input_text = QTextEdit()
        _configure_text_editor(
            self.input_text,
            reading_text=True,
            appearance=self._document_appearance,
        )
        self.input_text.setAcceptDrops(False)
        self.input_text.setPlaceholderText("Incolla qui il testo da controllare oppure carica un documento.")
        self.input_text.setAccessibleName("Testo originale")
        self.input_text.setAccessibleDescription("Testo o contenuto del documento da analizzare e anonimizzare.")
        self.input_text.textChanged.connect(self._handle_input_text_changed)
        self.input_text.selectionChanged.connect(self._sync_action_state)
        self._input_viewport = self.input_text.viewport()
        self.input_text.installEventFilter(self)
        self._input_viewport.installEventFilter(self)

        self.ai_response_text = QTextEdit()
        self.ai_response_text.setObjectName("AiResponseReference")
        _configure_text_editor(
            self.ai_response_text,
            reading_text=True,
            appearance=self._document_appearance,
        )
        self.ai_response_text.setAcceptDrops(False)
        self.ai_response_text.setReadOnly(True)
        self.ai_response_text.setTabChangesFocus(True)
        self.ai_response_text.setAccessibleName("Risposta dell’IA con segnaposti")
        self.ai_response_text.setAccessibleDescription(
            "Risposta ricevuta dall’IA prima del ripristino locale dei dati originali."
        )

        self.source_view_stack = QStackedWidget()
        self.source_view_stack.setObjectName("SourceViewStack")
        self.source_view_stack.addWidget(self.input_text)
        self.source_view_stack.addWidget(self.ai_response_text)

        self.source_view_notice = QLabel()
        self.source_view_notice.setObjectName("ComparisonSourceNotice")
        self.source_view_notice.setWordWrap(True)
        self.source_view_notice.setVisible(False)

        self.source_view_toggle = QPushButton("Mostra originale")
        self.source_view_toggle.setObjectName("LinkButton")
        self.source_view_toggle.setAccessibleName("Mostra documento originale")
        self.source_view_toggle.setAccessibleDescription(
            "Alterna la risposta dell’IA e il documento originale nel pannello di confronto."
        )
        self.source_view_toggle.clicked.connect(self._toggle_restored_comparison_source)
        self.source_view_toggle.setVisible(False)

        self.output_text = QTextEdit()
        _configure_text_editor(
            self.output_text,
            reading_text=True,
            appearance=self._document_appearance,
        )
        self.output_text.setAcceptDrops(False)
        self.output_text.setPlaceholderText(
            "Dopo l’analisi vedrai qui un’anteprima dei dati anonimizzati."
        )
        self.output_text.setAccessibleName("Testo anonimizzato")
        self.output_text.setAccessibleDescription(
            "Risultato prodotto da OMISSIS. Se diventa obsoleto viene disabilitato fino alla rigenerazione."
        )
        self.output_text.textChanged.connect(self._handle_output_text_changed)
        for source_editor in (self.input_text, self.ai_response_text):
            source_scroll_bar = source_editor.verticalScrollBar()
            source_scroll_bar.valueChanged.connect(
                lambda _value, editor=source_editor: self._sync_text_scroll_from(editor)
            )
            source_scroll_bar.rangeChanged.connect(self._handle_text_scroll_range_changed)
        output_scroll_bar = self.output_text.verticalScrollBar()
        output_scroll_bar.valueChanged.connect(
            lambda _value: self._sync_text_scroll_from(self.output_text)
        )
        output_scroll_bar.rangeChanged.connect(self._handle_text_scroll_range_changed)

        self.output_preview_notice = QLabel(
            "Anteprima di controllo: il documento definitivo verrà creato solo con "
            "«Crea copia protetta»."
        )
        self.output_preview_notice.setObjectName("OutputPreviewNotice")
        self.output_preview_notice.setWordWrap(True)
        self.output_preview_notice.setAccessibleName("Stato dell’anteprima")
        self.output_preview_notice.setVisible(False)

        self.output_preview_inline_notice = QLabel(
            "· provvisoria fino a «Crea copia protetta»"
        )
        self.output_preview_inline_notice.setObjectName("OutputPreviewInlineNotice")
        self.output_preview_inline_notice.setAccessibleName("Stato dell’anteprima")
        self.output_preview_inline_notice.setAccessibleDescription(
            "Il documento definitivo verrà creato solo con Crea copia protetta."
        )
        self.output_preview_inline_notice.setSizePolicy(
            QSizePolicy.Ignored,
            QSizePolicy.Preferred,
        )
        self.output_preview_inline_notice.setVisible(False)

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

        self.result_icon_label = QLabel("✓")
        self.result_icon_label.setObjectName("ResultIcon")
        self.result_icon_label.setAlignment(Qt.AlignCenter)
        self.result_icon_label.setFixedSize(30, 30)
        self.result_icon_label.setAccessibleName("Operazione completata")

        self.result_title_label = QLabel("Copia protetta pronta")
        self.result_title_label.setObjectName("ResultTitle")
        self.result_subtitle_label = QLabel()
        self.result_subtitle_label.setObjectName("ResultSubtitle")
        self.result_subtitle_label.setWordWrap(True)

        result_heading = QVBoxLayout()
        result_heading.setContentsMargins(0, 0, 0, 0)
        result_heading.setSpacing(2)
        result_heading.addWidget(self.result_title_label)
        result_heading.addWidget(self.result_subtitle_label)

        self.result_state_label = QLabel("PRONTA")
        self.result_state_label.setObjectName("ResultState")
        self.result_state_label.setAlignment(Qt.AlignCenter)

        result_top_row = QHBoxLayout()
        result_top_row.setContentsMargins(0, 0, 0, 0)
        result_top_row.setSpacing(10)
        result_top_row.addWidget(self.result_icon_label, 0, Qt.AlignTop)
        result_top_row.addLayout(result_heading, 1)
        result_top_row.addWidget(self.result_state_label, 0, Qt.AlignTop)

        self.result_metric_label = QLabel()
        self.result_metric_label.setObjectName("ResultMetric")
        self.result_meta_label = QLabel()
        self.result_meta_label.setObjectName("ResultMeta")
        self.result_meta_label.setWordWrap(True)

        result_metrics_row = QHBoxLayout()
        result_metrics_row.setContentsMargins(40, 0, 0, 0)
        result_metrics_row.setSpacing(10)
        result_metrics_row.addWidget(self.result_metric_label)
        result_metrics_row.addWidget(self.result_meta_label, 1)

        self.result_categories_label = QLabel()
        self.result_categories_label.setObjectName("ResultCategories")
        self.result_categories_label.setWordWrap(True)

        self.report_label = QLabel()
        self.report_label.setObjectName("ResultAttention")
        self.report_label.setWordWrap(True)
        self.report_label.setAccessibleName("Controlli prima di condividere")

        result_layout = QVBoxLayout()
        result_layout.setContentsMargins(14, 13, 14, 13)
        result_layout.setSpacing(7)
        result_layout.addLayout(result_top_row)
        result_layout.addLayout(result_metrics_row)
        result_layout.addWidget(self.result_categories_label)
        result_layout.addWidget(self.report_label)

        self.result_frame = QFrame()
        self.result_frame.setObjectName("ResultSummary")
        self.result_frame.setLayout(result_layout)
        self.result_frame.setAccessibleName("Riepilogo della copia protetta")
        self.result_frame.setVisible(False)

        self.reversible_flow_title = QLabel("Modalità Reversibile")
        self.reversible_flow_title.setObjectName("ReversibleFlowTitle")

        self.reversible_flow_intro = QLabel(
            "Completa questi passaggi nell’ordine indicato. Condividi solo la copia protetta: "
            "il File di ripristino resta sul tuo computer."
        )
        self.reversible_flow_intro.setObjectName("ReversibleFlowIntro")
        self.reversible_flow_intro.setWordWrap(True)

        self.reversible_help_button = QPushButton("Come funziona?")
        self.reversible_help_button.setObjectName("LinkButton")
        self.reversible_help_button.setAccessibleName("Come funziona la modalità Reversibile")
        self.reversible_help_button.setAccessibleDescription(
            "Apre una spiegazione dei tre passaggi senza modificare il documento."
        )
        self.reversible_help_button.clicked.connect(self.show_reversible_help_dialog)

        reversible_heading = QHBoxLayout()
        reversible_heading.setContentsMargins(0, 0, 0, 0)
        reversible_heading.setSpacing(12)
        reversible_heading.addWidget(self.reversible_flow_title)
        reversible_heading.addStretch(1)
        reversible_heading.addWidget(self.reversible_help_button, 0, Qt.AlignTop)

        self.reversible_step_frames: list[QFrame] = []
        self.reversible_step_dots: list[QLabel] = []
        self.reversible_step_state_labels: list[QLabel] = []
        self.reversible_step_description_labels: list[QLabel] = []
        reversible_steps_layout = QVBoxLayout()
        reversible_steps_layout.setContentsMargins(0, 0, 0, 0)
        reversible_steps_layout.setSpacing(6)
        self.reversible_steps_layout = reversible_steps_layout
        reversible_step_definitions = (
            (
                "Salva il File di ripristino",
                "Contiene i dati originali in forma cifrata. Scegli una password che ricorderai.",
            ),
            (
                "Copia la versione protetta per l’IA",
                "Condividi il testo con i segnaposti, mai il File di ripristino o la password.",
            ),
            (
                "Inserisci la risposta dell’IA",
                "Quando l’hai ricevuta, seleziona «Incolla qui»: i dati saranno reinseriti sul tuo computer.",
            ),
        )
        reversible_step_labels: list[QLabel] = []
        for index, (title, description) in enumerate(reversible_step_definitions, start=1):
            row, title_label = self._build_reversible_step(index, title, description)
            self.reversible_step_frames.append(row)
            reversible_step_labels.append(title_label)
            reversible_steps_layout.addWidget(row)

        (
            self.reversible_step_save_label,
            self.reversible_step_share_label,
            self.reversible_step_restore_label,
        ) = reversible_step_labels

        reversible_flow_layout = QVBoxLayout()
        reversible_flow_layout.setContentsMargins(14, 13, 14, 14)
        reversible_flow_layout.setSpacing(9)
        self.reversible_flow_layout = reversible_flow_layout
        reversible_flow_layout.addLayout(reversible_heading)
        reversible_flow_layout.addWidget(self.reversible_flow_intro)
        reversible_flow_layout.addLayout(reversible_steps_layout)

        self.reversible_flow_frame = QFrame()
        self.reversible_flow_frame.setObjectName("ReversibleFlow")
        self.reversible_flow_frame.setAccessibleName("Flusso della modalità Reversibile")
        self.reversible_flow_frame.setLayout(reversible_flow_layout)
        self.reversible_flow_frame.setVisible(False)

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

        self.save_button = QPushButton("Salva anche come file")
        self.save_button.clicked.connect(self.save_output)
        self.save_button.setObjectName("SecondaryButton")
        self.save_button.setToolTip("Salva il risultato corrente sul dispositivo.")
        self.save_button.setAccessibleDescription(
            "Salva il risultato nel formato prodotto oppure come testo se è stato modificato."
        )

        self.clear_button = QPushButton("Nuova sessione")
        self.clear_button.clicked.connect(self.clear_all)
        self.clear_button.setObjectName("SecondaryButton")
        self.clear_button.setToolTip("Avvia una nuova sessione dopo una conferma se esiste lavoro non salvato.")
        self.clear_button.setAccessibleDescription(
            "Azzera la sessione corrente senza eliminare lavoro non salvato per errore."
        )

        self.add_selection_button = QPushButton("Aggiungi dato mancante")
        self.add_selection_button.clicked.connect(self._review_secondary_action)
        self.add_selection_button.setObjectName("SecondaryButton")
        self.add_selection_button.setToolTip(
            "Seleziona una parola o frase nel pannello «Testo originale» non rilevata "
            "automaticamente, poi clicca qui per aggiungerla manualmente."
        )

        self.primary_button = QPushButton("Analizza dati")
        self.primary_button.setObjectName("PrimaryButton")
        self.primary_button.clicked.connect(self._primary_action)
        self.primary_button.setAccessibleDescription(
            "Esegue il solo passaggio disponibile nel flusso guidato."
        )
        self._primary_attention_timer = QTimer(self)
        self._primary_attention_timer.setSingleShot(True)
        self._primary_attention_timer.setInterval(760)
        self._primary_attention_timer.timeout.connect(lambda: self._set_primary_attention(False))

        self.pdf_choice_group = QButtonGroup(self)
        self.pdf_choice_group.setExclusive(True)
        self.pdf_choice_radios: dict[str, QRadioButton] = {}
        self.pdf_choice_cards: dict[str, QFrame] = {}
        pdf_choice_options = (
            (
                "pdf",
                "Mantieni il PDF",
                "Conserva impaginazione e pagine. La copia protetta sarà un PDF rasterizzato: "
                "oscuramenti permanenti, ma testo non ricercabile né copiabile.",
            ),
            (
                "text",
                "Trasforma in testo",
                "Ricompone righe e parole spezzate: può migliorare il riconoscimento e rende "
                "il contenuto più comodo da rileggere o usare con l’IA. L’uscita sarà .txt e "
                "perderà il layout originale.",
            ),
        )
        pdf_options_layout = QHBoxLayout()
        pdf_options_layout.setContentsMargins(0, 0, 0, 0)
        pdf_options_layout.setSpacing(10)
        for choice, title, description_text in pdf_choice_options:
            radio = QRadioButton(title)
            radio.setObjectName("PdfChoiceRadio")
            radio.setProperty("choice", choice)
            radio.setAccessibleDescription(description_text)

            description = QLabel(description_text)
            description.setObjectName("PdfChoiceDescription")
            description.setWordWrap(True)

            card = _ClickableCard(radio)
            card.setObjectName("PdfChoiceCard")
            card_layout = QVBoxLayout()
            card_layout.setContentsMargins(12, 10, 12, 10)
            card_layout.setSpacing(5)
            card_layout.addWidget(radio)
            card_layout.addWidget(description)
            card.setLayout(card_layout)
            card.setAccessibleName(title)
            card.setAccessibleDescription(description_text)

            self.pdf_choice_group.addButton(radio)
            self.pdf_choice_radios[choice] = radio
            self.pdf_choice_cards[choice] = card
            pdf_options_layout.addWidget(card, 1)

        self.pdf_choice_radios["pdf"].setChecked(True)
        for radio in self.pdf_choice_radios.values():
            radio.toggled.connect(self._handle_pdf_choice_toggled)

        pdf_choice_title = QLabel("Come vuoi usare questo PDF?")
        pdf_choice_title.setObjectName("PdfChoiceTitle")
        pdf_choice_help = QLabel(
            "La scelta resta modificabile fino alla creazione della copia protetta."
        )
        pdf_choice_help.setObjectName("PdfChoiceHelp")
        pdf_choice_help.setWordWrap(True)

        pdf_choice_layout = QVBoxLayout()
        pdf_choice_layout.setContentsMargins(14, 12, 14, 14)
        pdf_choice_layout.setSpacing(8)
        pdf_choice_layout.addWidget(pdf_choice_title)
        pdf_choice_layout.addWidget(pdf_choice_help)
        pdf_choice_layout.addLayout(pdf_options_layout)

        self.pdf_choice_frame = QFrame()
        self.pdf_choice_frame.setObjectName("PdfChoice")
        self.pdf_choice_frame.setLayout(pdf_choice_layout)
        self.pdf_choice_frame.setAccessibleName("Scelta del formato PDF")
        self.pdf_choice_frame.setVisible(False)

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
        self.step_dots: list[QLabel] = []
        step_definitions = [
            "Carica o incolla",
            "Analizza dati",
            "Rivedi i risultati",
            "Crea la copia protetta",
            "Usa il risultato",
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
            ("reversible", "Reversibile — ripristina i dati dopo"),
        ]
        protection_column = QVBoxLayout()
        protection_column.setSpacing(8)
        for mode, title in mode_options:
            radio = QRadioButton(title)
            radio.setObjectName("ModeCardRadio")
            radio.setAccessibleDescription(mode_note(mode))

            description = QLabel(mode_note(mode))
            description.setObjectName("ModeCardDescription")
            description.setTextFormat(Qt.PlainText)
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

        self.map_status_label = QLabel("Il File di ripristino verrà creato con la copia")
        self.map_status_label.setObjectName("MapStatus")
        self.map_status_label.setWordWrap(True)
        self.map_status_label.setAccessibleName("Stato del File di ripristino")
        self.map_section_label = self._rail_section_label("FILE DI RIPRISTINO")

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
        self.document_appearance_selector = self._build_document_appearance_selector()
        self.document_toolbar = _AdaptiveToolbar(
            self.load_button,
            self.document_label,
            self.copy_button,
            self.save_button,
            self.clear_button,
            self.add_selection_button,
            self.document_appearance_selector,
            self.primary_button,
        )

        self.input_panel, self.input_panel_title = self._panel(
            "Testo originale",
            self.source_view_stack,
            helper=self.source_view_notice,
            header_action=self.source_view_toggle,
        )
        self.output_panel, self.output_panel_title = self._panel(
            "Testo anonimizzato",
            self.output_text,
            helper=self.output_preview_notice,
            header_note=self.output_preview_inline_notice,
        )

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
        main_area_layout.setSpacing(13)
        main_area_layout.addWidget(self.document_toolbar)
        main_area_layout.addWidget(self.pdf_choice_frame)
        main_area_layout.addWidget(self.job_frame)
        main_area_layout.addWidget(self.result_frame)
        main_area_layout.addWidget(self.reversible_flow_frame)
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

    def resizeEvent(self, event: QResizeEvent) -> None:
        if hasattr(self, "reversible_step_description_labels"):
            compact_height = event.size().height() < 760
            compact_changed = compact_height != self._compact_height
            self._compact_height = compact_height
            self.reversible_flow_intro.setVisible(not compact_height)
            self.reversible_flow_layout.setContentsMargins(
                12 if compact_height else 14,
                8 if compact_height else 13,
                12 if compact_height else 14,
                8 if compact_height else 14,
            )
            self.reversible_flow_layout.setSpacing(5 if compact_height else 9)
            self.reversible_steps_layout.setSpacing(3 if compact_height else 6)
            for label in self.reversible_step_description_labels:
                label.setVisible(not compact_height)
            for row in self.reversible_step_frames:
                row.setMinimumHeight(34 if compact_height else 0)
                row.updateGeometry()
            self.reversible_flow_frame.updateGeometry()
            if compact_changed and hasattr(self, "result_frame"):
                self._update_report()
        super().resizeEvent(event)

    def _rail_section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("RailSectionLabel")
        return label

    def _build_step_row(self, index: int, title: str) -> QFrame:
        row = QFrame()
        row.setObjectName("StepRowPending")
        row.setAccessibleName(f"Passaggio {index}: {title}")

        dot = QLabel(str(index))
        dot.setObjectName("StepDot")
        dot.setAlignment(Qt.AlignCenter)
        dot.setFixedSize(20, 20)
        self.step_dots.append(dot)

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

    def _build_reversible_step(
        self,
        index: int,
        title: str,
        description: str,
    ) -> tuple[QFrame, QLabel]:
        row = QFrame()
        row.setObjectName("ReversibleStepPending")

        dot = QLabel(str(index))
        dot.setObjectName("ReversibleStepDot")
        dot.setAlignment(Qt.AlignCenter)
        dot.setFixedSize(22, 22)
        self.reversible_step_dots.append(dot)

        title_label = QLabel(title)
        title_label.setObjectName("ReversibleStepTitle")
        title_label.setWordWrap(True)

        description_label = QLabel(description)
        description_label.setObjectName("ReversibleStepDescription")
        description_label.setWordWrap(True)
        self.reversible_step_description_labels.append(description_label)

        copy = QVBoxLayout()
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(2)
        copy.addWidget(title_label)
        copy.addWidget(description_label)

        state_label = QLabel("BLOCCATO")
        state_label.setObjectName("ReversibleStepState")
        state_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.reversible_step_state_labels.append(state_label)

        inline_action: QPushButton | None = None
        if index == 3:
            inline_action = QPushButton("Incolla qui")
            inline_action.setObjectName("ReversibleInlineAction")
            inline_action.setAccessibleName("Incolla qui la risposta dell’IA")
            inline_action.setAccessibleDescription(
                "Apre lo spazio in cui incollare la risposta ricevuta dall’IA e ripristinare i dati localmente."
            )
            inline_action.clicked.connect(self.restore_with_reversible_map)
            inline_action.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            inline_action.setFixedHeight(24)
            inline_action.setVisible(False)
            self.reversible_restore_inline_button = inline_action

        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(10, 8, 10, 8)
        row_layout.setSpacing(10)
        row_layout.addWidget(dot, 0, Qt.AlignTop)
        row_layout.addLayout(copy, 1)
        row_layout.addWidget(state_label, 0, Qt.AlignVCenter)
        if inline_action is not None:
            row_layout.addWidget(inline_action, 0, Qt.AlignVCenter)
        row.setLayout(row_layout)
        row.setAccessibleName(f"Passaggio {index}: {title}")
        return row, title_label

    def _panel(
        self,
        title: str,
        widget: QWidget,
        *,
        helper: QLabel | None = None,
        header_action: QWidget | None = None,
        header_note: QLabel | None = None,
    ) -> tuple[QWidget, QLabel]:
        label = QLabel(title)
        label.setObjectName("SectionTitle")
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        header_layout.addWidget(label)
        if header_note is not None:
            header_layout.addWidget(header_note, 1)
        header_layout.addStretch(1)
        if header_action is not None:
            header_layout.addWidget(header_action)
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)
        layout.addLayout(header_layout)
        if helper is not None:
            layout.addWidget(helper)
        layout.addWidget(widget)
        panel = QFrame()
        panel.setObjectName("Panel")
        panel.setLayout(layout)
        return panel, label

    def _build_document_appearance_selector(self) -> QFrame:
        label = QLabel("Documento")
        label.setObjectName("DocumentAppearanceLabel")

        self.document_dark_button = QPushButton("Scuro")
        self.document_paper_button = QPushButton("Carta chiara")
        for button in (self.document_dark_button, self.document_paper_button):
            button.setObjectName("DocumentAppearanceButton")
            button.setCheckable(True)
            button.setAutoExclusive(True)

        self.document_dark_button.setAccessibleName("Documento su fondo scuro")
        self.document_dark_button.setAccessibleDescription(
            "Mostra originale, risposta dell’IA e risultato con testo chiaro su fondo scuro."
        )
        self.document_paper_button.setAccessibleName("Documento su carta chiara")
        self.document_paper_button.setAccessibleDescription(
            "Mostra originale, risposta dell’IA e risultato con inchiostro scuro su carta chiara."
        )
        self.document_dark_button.setToolTip("Testo chiaro su fondo scuro")
        self.document_paper_button.setToolTip("Inchiostro scuro su carta chiara")

        if self._document_appearance == DOCUMENT_APPEARANCE_PAPER:
            self.document_paper_button.setChecked(True)
        else:
            self.document_dark_button.setChecked(True)

        self.document_dark_button.clicked.connect(
            lambda: self._set_document_appearance(DOCUMENT_APPEARANCE_DARK)
        )
        self.document_paper_button.clicked.connect(
            lambda: self._set_document_appearance(DOCUMENT_APPEARANCE_PAPER)
        )

        layout = QHBoxLayout()
        layout.setContentsMargins(8, 2, 4, 2)
        layout.setSpacing(4)
        layout.addWidget(label)
        layout.addSpacing(4)
        layout.addWidget(self.document_dark_button)
        layout.addWidget(self.document_paper_button)

        selector = QFrame()
        selector.setObjectName("DocumentAppearanceSelector")
        selector.setAccessibleName("Aspetto del documento")
        selector.setFixedHeight(32)
        selector.setLayout(layout)
        return selector

    def _set_document_appearance(self, appearance: str, *, persist: bool = True) -> None:
        if appearance not in DOCUMENT_APPEARANCES:
            appearance = DOCUMENT_APPEARANCE_DARK
        changed = appearance != self._document_appearance
        self._document_appearance = appearance

        for button, checked in (
            (self.document_dark_button, appearance == DOCUMENT_APPEARANCE_DARK),
            (self.document_paper_button, appearance == DOCUMENT_APPEARANCE_PAPER),
        ):
            blocker = QSignalBlocker(button)
            button.setChecked(checked)
            del blocker

        for editor in (self.input_text, self.ai_response_text, self.output_text):
            _apply_text_editor_appearance(editor, appearance)

        if self.findings:
            self._highlight_findings()

        if persist:
            self._settings.setValue(DOCUMENT_APPEARANCE_SETTING, appearance)
            self._settings.sync()

        if changed:
            label = "Carta chiara" if appearance == DOCUMENT_APPEARANCE_PAPER else "Scuro"
            self.statusBar().showMessage(f"Aspetto documento: {label}.", 3000)

    def _build_menu(self) -> None:
        self.open_action = QAction("Carica documento...", self)
        self.open_action.setShortcut(QKeySequence.Open)
        self.open_action.triggered.connect(self.open_file)

        quit_action = QAction("Esci", self)
        quit_action.setShortcut(QKeySequence.Quit)
        quit_action.triggered.connect(self.close)

        self.copy_output_action = QAction("Copia per l’IA", self)
        self.copy_output_action.setShortcut(QKeySequence("Ctrl+Shift+C"))
        self.copy_output_action.triggered.connect(self.copy_output)

        self.save_output_action = QAction("Salva copia protetta...", self)
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

        self.save_map_action = QAction("Salva il File di ripristino...", self)
        self.save_map_action.triggered.connect(self.save_reversible_map)

        # Conservato per compatibilità interna: il riuso tra più documenti è una
        # funzione avanzata e non fa parte del percorso ordinario di questa build.
        self.load_map_action = QAction("Continua con un File di ripristino esistente...", self)
        self.load_map_action.triggered.connect(self.load_reversible_map)

        self.restore_map_action = QAction("Incolla la risposta dell’IA e ripristina...", self)
        self.restore_map_action.triggered.connect(self.restore_with_reversible_map)

        self.tools_menu = self.menuBar().addMenu("Strumenti")
        self.tools_menu.addAction(self.primary_action)
        self.tools_menu.addAction(self.focus_search_action)
        self.tools_menu.addAction(self.toggle_rail_action)
        self.tools_menu.addSeparator()
        self.tools_menu.addAction(self.activity_action)
        self.tools_menu.addSeparator()
        self.tools_menu.addAction(self.save_map_action)
        self.tools_menu.addAction(self.restore_map_action)

        security_action = QAction("Sicurezza e privacy", self)
        security_action.triggered.connect(self.show_security_dialog)

        self.review_help_action = QAction("Come rivedere i dati rilevati", self)
        self.review_help_action.setShortcut(QKeySequence.HelpContents)
        self.review_help_action.triggered.connect(self.show_review_help_dialog)

        self.reversible_help_action = QAction("Come funziona la modalità Reversibile", self)
        self.reversible_help_action.triggered.connect(self.show_reversible_help_dialog)

        about_action = QAction("Informazioni su OMISSIS", self)
        about_action.triggered.connect(self.show_about_dialog)

        help_menu = self.menuBar().addMenu("Aiuto")
        help_menu.addAction(self.review_help_action)
        help_menu.addAction(self.reversible_help_action)
        help_menu.addSeparator()
        help_menu.addAction(security_action)
        help_menu.addSeparator()
        help_menu.addAction(about_action)

    def _configure_accessibility(self) -> None:
        self.load_button.setAccessibleName("Carica documento")
        self.copy_button.setAccessibleName("Copia per l’IA")
        self.save_button.setAccessibleName("Salva anche come file")
        self.clear_button.setAccessibleName("Nuova sessione")
        self.add_selection_button.setAccessibleName("Aggiungi dato mancante")
        self.primary_button.setAccessibleName("Esegui passaggio corrente")
        self.setTabOrder(self.load_button, self.document_dark_button)
        self.setTabOrder(self.document_dark_button, self.document_paper_button)
        self.setTabOrder(self.document_paper_button, self.input_text)
        self.setTabOrder(self.input_text, self.source_view_toggle)
        self.setTabOrder(self.source_view_toggle, self.ai_response_text)
        self.setTabOrder(self.ai_response_text, self.add_selection_button)
        self.setTabOrder(self.add_selection_button, self.findings_panel.search_edit)
        self.setTabOrder(self.findings_panel.search_edit, self.findings_panel.tree)
        self.setTabOrder(self.findings_panel.tree, self.primary_button)
        self.setTabOrder(self.primary_button, self.reversible_help_button)
        self.setTabOrder(self.reversible_help_button, self.reversible_restore_inline_button)
        self.setTabOrder(self.reversible_restore_inline_button, self.output_text)
        self.setTabOrder(self.output_text, self.save_button)
        self.setTabOrder(self.save_button, self.clear_button)

    def focus_findings_search(self) -> None:
        if self.findings:
            self.findings_panel.search_edit.setVisible(True)
        self.findings_panel.search_edit.setFocus(Qt.ShortcutFocusReason)
        self.findings_panel.search_edit.selectAll()

    def _focus_review_workspace(self) -> None:
        """Keep review central without forcing focus or a native table scroll."""
        self._selected_finding_index = None

    def _show_result_workspace(self) -> None:
        self.output_text.ensureCursorVisible()

    def _show_input_workspace(self) -> None:
        self.input_text.ensureCursorVisible()

    def _visible_source_editor(self) -> QTextEdit:
        if self.source_view_stack.currentWidget() is self.ai_response_text:
            return self.ai_response_text
        return self.input_text

    def _sync_text_scroll_from(self, source_editor: QTextEdit) -> None:
        """Keep the two visible text panes at the same relative document position."""
        if (
            self._syncing_text_scroll
            or self._updating_output_text
            or self._loading_document_text
        ):
            return

        visible_source = self._visible_source_editor()
        if source_editor is self.output_text:
            target_editor = visible_source
        elif source_editor is visible_source:
            target_editor = self.output_text
        else:
            return

        source_bar = source_editor.verticalScrollBar()
        target_bar = target_editor.verticalScrollBar()
        source_range = source_bar.maximum() - source_bar.minimum()
        target_range = target_bar.maximum() - target_bar.minimum()
        position = (
            0.0
            if source_range <= 0
            else (source_bar.value() - source_bar.minimum()) / source_range
        )
        target_value = target_bar.minimum() + round(position * max(0, target_range))

        self._syncing_text_scroll = True
        try:
            target_bar.setValue(target_value)
        finally:
            self._syncing_text_scroll = False

    def _align_output_scroll_to_source(self) -> None:
        source_editor = self._visible_source_editor()
        source_bar = source_editor.verticalScrollBar()
        output_bar = self.output_text.verticalScrollBar()
        source_range = source_bar.maximum() - source_bar.minimum()
        output_range = output_bar.maximum() - output_bar.minimum()
        if source_range <= 0 < output_range:
            return
        self._sync_text_scroll_from(source_editor)

    def _align_visible_source_scroll_to_output(self) -> None:
        self._sync_text_scroll_from(self.output_text)

    def _handle_text_scroll_range_changed(self, *_args: object) -> None:
        """Realign immediately and once more after Qt finishes laying out text."""
        if not (
            self._syncing_text_scroll
            or self._updating_output_text
            or self._loading_document_text
        ):
            self._align_output_scroll_to_source()
        self._schedule_text_scroll_alignment()

    def _schedule_text_scroll_alignment(self, *_args: object) -> None:
        """Coalesce late Qt layout changes before realigning the text panes."""
        if self._text_scroll_alignment_pending:
            return
        self._text_scroll_alignment_pending = True
        QTimer.singleShot(0, self._run_scheduled_text_scroll_alignment)

    def _run_scheduled_text_scroll_alignment(self) -> None:
        self._text_scroll_alignment_pending = False
        if (
            self._syncing_text_scroll
            or self._updating_output_text
            or self._loading_document_text
        ):
            self._schedule_text_scroll_alignment()
            return
        self._align_output_scroll_to_source()

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
            "«Aggiungi dato mancante». Puoi cercare o filtrare l'elenco senza cambiare le spunte.<br><br>"
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

    def show_reversible_help_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setObjectName("InfoDialog")
        dialog.setWindowTitle("Come funziona la modalità Reversibile")
        dialog.setModal(True)
        dialog.setMinimumWidth(590)

        title = QLabel("Proteggi, usa con l’IA, ripristina")
        title.setObjectName("DialogTitle")

        details = QLabel(
            "La modalità Reversibile sostituisce i dati con etichette numerate, per esempio "
            "<b>Mario Rossi → &lt;PERSONA_1&gt;</b>. OMISSIS crea anche un File di ripristino "
            "cifrato che conserva la corrispondenza.<br><br>"
            "<b>1. Salva il File di ripristino.</b> Resta sul tuo computer ed è protetto dalla "
            "password che scegli. Se perdi il file o la password, OMISSIS non potrà reinserire "
            "i dati.<br><br>"
            "<b>2. Invia soltanto la copia protetta.</b> Non allegare mai il File di ripristino "
            "e non comunicare la password a servizi di IA o ad altri servizi esterni.<br><br>"
            "<b>3. Incolla la risposta nell’app.</b> Quando hai la risposta, usa il pulsante "
            "<b>Incolla qui la risposta dell’IA</b>. OMISSIS riconosce le stesse etichette e "
            "reinserisce localmente i dati originali.<br><br>"
            "Reversibile è disponibile nell’app desktop per testo incollato, TXT e DOCX. "
            "Non modificare o eliminare etichette come &lt;PERSONA_1&gt;: OMISSIS non potrà "
            "reinserire quel dato."
        )
        details.setObjectName("DialogDetails")
        details.setTextFormat(Qt.RichText)
        details.setWordWrap(True)

        close_button = QPushButton("Ho capito")
        close_button.setObjectName("PrimaryButton")
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
        dialog.setAccessibleName("Guida alla modalità Reversibile")
        dialog.setAccessibleDescription(
            "Spiega come salvare il File di ripristino, condividere solo la copia protetta e reinserire i dati."
        )
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
            "permanenti oppure scegliere Trasforma in testo per ricomporre righe e sillabazioni, "
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
            items.append(
                "testo ricostruito con dati personali non salvato"
                if self._is_restored_output()
                else "risultato anonimizzato non salvato"
            )
        if include_map and self.reversible_mapping and not self._reversible_map_saved:
            items.append("File di ripristino non salvato")
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

        dialog = _DiscardWorkDialog(action_label, items, self)
        return dialog.exec() == QDialog.Accepted

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
        self._reversible_map_path = None
        self._restore_mapping = ()
        self._output_provenance = None
        self._output_stale_reason = ""
        self._output_saved = True
        self._review_dirty = False
        self._review_confirmed = False
        self._result_used = False
        self._reversible_copy_copied = False
        self._reset_restored_comparison_state()
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
        switched_from_reversible = (
            self._selected_mode() == "reversible" and not self._reversible_mode_available()
        )
        if switched_from_reversible:
            self.mode_radios["maximum"].setChecked(True)
        self._update_mode_notice()
        self._update_report()
        if self.loaded_document.extension == ".pdf":
            self.pdf_choice_radios["pdf"].setChecked(True)
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
                    "Se vuoi un testo più comodo da rileggere o usare con l’IA, scegli Trasforma in testo.",
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
        if switched_from_reversible:
            self.statusBar().showMessage(
                "La modalità Reversibile non è disponibile per questo formato: "
                "è stata attivata Massima protezione. Usa testo incollato, TXT o DOCX per poter ripristinare i dati.",
                9000,
            )
        self.findings_panel.set_document_notice(
            "unsupported"
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
        self._review_confirmed = False
        self._findings_source_text = outcome.source_text
        self._findings_mode = outcome.mode
        self._fill_table()
        self._highlight_findings()
        self._refresh_analysis_preview()
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
                "Rigenera senza il File di ripristino",
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
                    f"Salva il File di ripristino prima di usarlo con l’IA.{unsupported_note}",
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
                "Copia protetta pronta. Salva il File di ripristino prima di usare l’IA.",
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
        if self._is_restored_output():
            self.statusBar().showMessage(
                "Il testo contiene nuovamente dati personali. Salvalo sul dispositivo invece di inviarlo all’IA.",
                7000,
            )
            return
        if self._is_current_reversible_output() and not self._reversible_map_saved:
            self.statusBar().showMessage(
                "Salva prima il File di ripristino. La copia protetta non è stata copiata.",
                7000,
            )
            return
        QApplication.clipboard().setText(self.output_text.toPlainText())
        if self._is_current_reversible_output():
            self._reversible_copy_copied = True
        self._result_used = True
        self._update_report()
        self._sync_action_state()
        self.statusBar().showMessage(
            "Copia protetta negli appunti: ora puoi incollarla nello strumento di IA che preferisci.",
            5000,
        )

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
        if self._is_current_reversible_output() and not self._reversible_map_saved:
            self.statusBar().showMessage(
                "Salva prima il File di ripristino. La copia protetta non è stata salvata.",
                7000,
            )
            return
        use_document_binary = self.anonymized_document is not None and not self.output_text_dirty
        if self._is_restored_output():
            use_document_binary = False
            default_name = "testo_ricostruito.txt"
            dialog_title = "Salva testo ricostruito"
        else:
            default_name = self.anonymized_document.filename if use_document_binary else "testo_anonimizzato.txt"
            dialog_title = "Salva versione anonimizzata"
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
            dialog_title,
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
        if not self._is_current_reversible_output():
            self._result_used = True
        self._record_activity(
            "save",
            output_path=target_path,
            mode=self._output_provenance.mode if self._output_provenance is not None else None,
        )
        self._update_report()
        self._sync_action_state()
        self.statusBar().showMessage(f"Salvato: {target_path}", 4000)

    def save_reversible_map(self) -> bool:
        if not self.reversible_mapping:
            self.statusBar().showMessage("Non c’è ancora un File di ripristino da salvare.", 5000)
            return False

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Salva il File di ripristino",
            str(Path.home() / self._default_map_filename()),
            "File di ripristino OMISSIS (*.omissis-map)",
        )
        if not filename:
            return False
        target_path = Path(filename)
        if target_path.suffix.lower() != MAP_EXTENSION:
            target_path = target_path.with_suffix(MAP_EXTENSION)

        passphrase = self._ask_passphrase(
            "Password del File di ripristino",
            "Scegli una password per cifrare il File di ripristino:",
            confirm=True,
        )
        if passphrase is None:
            return False
        try:
            write_encrypted_mapping(target_path, self.reversible_mapping, passphrase)
        except ReversibleMapError as exc:
            self.statusBar().showMessage(str(exc), 7000)
            return False

        self._reversible_map_saved = True
        self._reversible_map_path = target_path
        self._restore_mapping = self.reversible_mapping
        self._update_report()
        self._sync_action_state()
        self.statusBar().showMessage(
            f"File di ripristino salvato: {target_path}. Non condividerlo con servizi esterni.",
            7000,
        )
        return True

    def load_reversible_map(self) -> None:
        if not self._confirm_discard_work(
            "Sostituisci File di ripristino",
            include_source=False,
            include_review=False,
            include_output=False,
        ):
            return
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Continua con un File di ripristino esistente",
            str(Path.home()),
            "File di ripristino OMISSIS (*.omissis-map);;Tutti i file (*.*)",
        )
        if not filename:
            return

        passphrase = self._ask_passphrase(
            "Password del File di ripristino",
            "Inserisci la password del File di ripristino:",
        )
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
        self._reversible_map_path = Path(filename)
        self._restore_mapping = entries
        if self._selected_mode() == "reversible":
            self._mark_workflow_changed("il File di ripristino")
        self._sync_action_state()
        self.statusBar().showMessage(
            f"File di ripristino caricato: {len(entries)} voci pronte per i prossimi documenti.", 7000
        )

    def _reversible_placeholder_status(
        self,
        text: str,
        mapping: tuple[ReversibleMapEntry, ...],
    ) -> tuple[int, int, tuple[str, ...]]:
        known = {entry.placeholder for entry in mapping}
        tokens = {match.group(0) for match in PLACEHOLDER_PATTERN.finditer(text)}
        matched = len(tokens & known)
        missing = len(known - tokens)
        unknown = tuple(sorted(tokens - known))
        return matched, missing, unknown

    def restore_with_reversible_map(self) -> None:
        dialog = QDialog(self)
        dialog.setObjectName("InfoDialog")
        dialog.setWindowTitle("Incolla qui la risposta dell’IA")
        dialog.setWindowModality(Qt.WindowModal)
        dialog.setModal(True)
        dialog.resize(690, 560)
        dialog.setAccessibleName("Incolla qui la risposta dell’IA")
        dialog.setAccessibleDescription(
            "Incolla una risposta con segnaposti e usa il File di ripristino per reinserire i dati sul computer."
        )

        title = QLabel("Incolla qui la risposta dell’IA")
        title.setObjectName("DialogTitle")

        details = QLabel(
            "Copia la risposta ricevuta dall’IA e incollala nel riquadro qui sotto. "
            "I dati originali saranno reinseriti soltanto sul tuo computer."
        )
        details.setObjectName("DialogDetails")
        details.setWordWrap(True)

        response_label = QLabel("Risposta ricevuta dall’IA")
        response_label.setObjectName("FieldLabel")
        response_editor = QTextEdit()
        response_editor.setObjectName("RestoreResponseEditor")
        _configure_text_editor(response_editor)
        response_editor.setPlaceholderText(
            "Incolla qui l’intera risposta dell’IA. Lascia invariati segnaposti come <PERSONA_1>."
        )
        response_editor.setAccessibleName("Risposta dell’IA da ricostruire")
        response_editor.setAccessibleDescription(
            "Il testo resta sul computer e non viene inviato a servizi esterni."
        )
        response_editor.setMinimumHeight(220)
        response_label.setBuddy(response_editor)

        selected_mapping = {
            "entries": self._restore_mapping,
            "path": self._reversible_map_path,
        }
        map_label = QLabel()
        map_label.setObjectName("RestoreMapStatus")
        map_label.setWordWrap(True)
        map_label.setAccessibleName("File di ripristino selezionato")

        choose_map_button = QPushButton()
        choose_map_button.setObjectName("SecondaryButton")
        choose_map_button.setAccessibleName("Scegli il File di ripristino")

        password_label = QLabel("Password del File di ripristino")
        password_label.setObjectName("FieldLabel")
        password_edit = QLineEdit()
        password_edit.setObjectName("RestorePasswordEdit")
        password_edit.setEchoMode(QLineEdit.Password)
        password_edit.setPlaceholderText("Inserisci la password usata al salvataggio")
        password_edit.setAccessibleName("Password del File di ripristino")
        password_label.setBuddy(password_edit)

        validation_label = QLabel()
        validation_label.setObjectName("RestoreValidation")
        validation_label.setWordWrap(True)
        validation_label.setAccessibleName("Controllo dei segnaposti")

        restore_button = QPushButton("Ripristina i dati")
        restore_button.setObjectName("PrimaryButton")
        restore_button.setAccessibleDescription(
            "Reinserisce localmente i dati originali nei segnaposti riconosciuti."
        )
        cancel_button = QPushButton("Annulla")
        cancel_button.setObjectName("SecondaryButton")
        cancel_button.clicked.connect(dialog.reject)

        def using_session_mapping() -> bool:
            return bool(selected_mapping["entries"])

        def refresh_map_controls() -> None:
            path = selected_mapping["path"]
            if using_session_mapping():
                location = f" · {Path(path).name}" if path else ""
                map_label.setText(f"File di ripristino pronto per questa sessione{location}")
                choose_map_button.setText("Scegli un altro File di ripristino…")
                password_label.setVisible(False)
                password_edit.setVisible(False)
            elif path:
                map_label.setText(f"File selezionato: {Path(path).name}")
                choose_map_button.setText("Scegli un altro File di ripristino…")
                password_label.setVisible(True)
                password_edit.setVisible(True)
            else:
                map_label.setText(
                    "Per continuare, scegli il File di ripristino salvato insieme alla copia protetta."
                )
                choose_map_button.setText("Scegli il File di ripristino…")
                password_label.setVisible(False)
                password_edit.setVisible(False)

        def refresh_validation() -> None:
            text = response_editor.toPlainText()
            entries = selected_mapping["entries"]
            path = selected_mapping["path"]
            ready = False
            if not text.strip():
                message = "Incolla la risposta dell’IA per controllare i segnaposti."
                style = "RestoreValidation"
            elif entries:
                matched, missing, unknown = self._reversible_placeholder_status(text, entries)
                if unknown:
                    noun = "segnaposto non appartiene" if len(unknown) == 1 else "segnaposti non appartengono"
                    message = (
                        f"{len(unknown)} {noun} a questo File di ripristino: "
                        f"{', '.join(unknown)}. Controlla il testo o scegli il file corretto."
                    )
                    style = "RestoreValidationError"
                elif matched == 0:
                    message = (
                        "Non sono stati trovati segnaposti di questo File di ripristino. "
                        "Controlla il testo o scegli il file corretto."
                    )
                    style = "RestoreValidationError"
                else:
                    total = matched + missing
                    message = f"Segnaposti pronti: {matched} di {total}."
                    if missing == 1:
                        message += (
                            " 1 elemento non compare nella risposta e non verrà ripristinato."
                        )
                    elif missing:
                        message += (
                            f" {missing} elementi non compaiono nella risposta e non verranno ripristinati."
                        )
                    style = "RestoreValidationReady"
                    ready = True
            elif path:
                message = "Inserisci la password del File di ripristino."
                style = "RestoreValidation"
                ready = bool(text.strip() and password_edit.text())
            else:
                message = "Scegli il File di ripristino prima di continuare."
                style = "RestoreValidation"
            self._set_styled_object_name(validation_label, style)
            validation_label.setText(message)
            validation_label.setAccessibleDescription(message)
            restore_button.setEnabled(ready)

        def choose_map() -> None:
            filename, _ = QFileDialog.getOpenFileName(
                dialog,
                "Scegli il File di ripristino",
                str(Path.home()),
                "File di ripristino OMISSIS (*.omissis-map);;Tutti i file (*.*)",
            )
            if not filename:
                return
            selected_mapping["entries"] = ()
            selected_mapping["path"] = Path(filename)
            password_edit.clear()
            refresh_map_controls()
            refresh_validation()
            password_edit.setFocus(Qt.OtherFocusReason)

        def apply_restore() -> None:
            source_text = response_editor.toPlainText()
            mapping = selected_mapping["entries"]
            path = selected_mapping["path"]
            if not mapping:
                if not path or not password_edit.text():
                    refresh_validation()
                    return
                try:
                    mapping = read_encrypted_mapping(path, password_edit.text())
                except ReversibleMapError:
                    message = (
                        "Non riesco ad aprire questo File di ripristino. "
                        "Controlla password e file, poi riprova."
                    )
                    self._set_styled_object_name(validation_label, "RestoreValidationError")
                    validation_label.setText(message)
                    validation_label.setAccessibleDescription(message)
                    self.statusBar().showMessage(message, 8000)
                    password_edit.selectAll()
                    password_edit.setFocus(Qt.OtherFocusReason)
                    return
                selected_mapping["entries"] = mapping
                refresh_map_controls()

            matched, missing, unknown = self._reversible_placeholder_status(source_text, mapping)
            if matched == 0 or unknown:
                refresh_validation()
                return

            restored = restore_text(source_text, mapping)
            self._restore_mapping = mapping
            self._reversible_map_path = Path(path) if path else self._reversible_map_path
            self.anonymized_document = None
            self.reversible_mapping = ()
            self.loaded_reversible_entries = ()
            self._reversible_map_saved = True
            self._set_restored_comparison_source(source_text)
            self._set_output_text(restored)
            self._mark_output_generated(
                "reversible",
                total_findings=matched + missing,
                included_findings=matched,
                kind="restored",
            )
            dialog.accept()
            self.primary_button.setFocus(Qt.OtherFocusReason)
            if missing:
                noun = "elemento non compariva" if missing == 1 else "elementi non comparivano"
                self.statusBar().showMessage(
                    f"Dati ripristinati sul computer. {missing} {noun} nella risposta e non "
                    f"{'è stato reinserito' if missing == 1 else 'sono stati reinseriti'}.",
                    9000,
                )
            else:
                self.statusBar().showMessage(
                    "Dati ripristinati sul computer. Il testo contiene nuovamente informazioni personali.",
                    7000,
                )

        choose_map_button.clicked.connect(choose_map)
        response_editor.textChanged.connect(refresh_validation)
        password_edit.textChanged.connect(refresh_validation)
        restore_button.clicked.connect(apply_restore)

        map_row = QHBoxLayout()
        map_row.setContentsMargins(0, 0, 0, 0)
        map_row.setSpacing(10)
        map_row.addWidget(map_label, 1)
        map_row.addWidget(choose_map_button)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(cancel_button)
        button_row.addWidget(restore_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(11)
        layout.addWidget(title)
        layout.addWidget(details)
        layout.addWidget(response_label)
        layout.addWidget(response_editor, 1)
        layout.addLayout(map_row)
        layout.addWidget(password_label)
        layout.addWidget(password_edit)
        layout.addWidget(validation_label)
        layout.addLayout(button_row)
        dialog.setLayout(layout)
        dialog.setStyleSheet(APP_STYLE)
        dialog.setTabOrder(response_editor, choose_map_button)
        dialog.setTabOrder(choose_map_button, password_edit)
        dialog.setTabOrder(password_edit, cancel_button)
        dialog.setTabOrder(cancel_button, restore_button)

        refresh_map_controls()
        refresh_validation()
        QTimer.singleShot(
            0,
            lambda: response_editor.setFocus(Qt.OtherFocusReason)
            if using_session_mapping()
            else choose_map_button.setFocus(Qt.OtherFocusReason),
        )
        dialog.exec()

    def clear_all(self, force: bool = False) -> None:
        if not force and not self._confirm_discard_work("Pulisci e scarta"):
            return
        self._output_provenance = None
        self._output_stale_reason = ""
        self._output_saved = True
        self._reversible_map_saved = True
        self._reversible_map_path = None
        self._restore_mapping = ()
        self._review_dirty = False
        self._review_confirmed = False
        self._result_used = False
        self._reversible_copy_copied = False
        self._reset_restored_comparison_state()
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

        dialog = _EntityTypeDialog(labels, self.input_text.textCursor().selectedText(), self)
        ok = dialog.exec() == QDialog.Accepted
        if not ok:
            return
        label = dialog.selected_label()
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
        # Espandi la selezione a ogni variante di maiuscole/minuscole del valore:
        # "STELLANTIS", "Stellantis" e "stellantis" sono lo stesso dato scelto
        # dall'utente. Gli span restano riferiti alla grafia originale, indispensabile
        # per ricostruire esattamente il testo in modalità Reversibile.
        matching_spans = set(casefolded_literal_spans(source_text, value))
        automatic_findings = [
            finding
            for finding in self.findings
            if (finding.start, finding.end) not in matching_spans
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
        self._review_confirmed = False
        self._mark_workflow_changed("le selezioni manuali")
        self._refresh_analysis_preview()
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
            if not self._manual_add_supported():
                notice_kind = "unsupported"
        self.findings_panel.set_document_notice(notice_kind)

    def _highlight_findings(self) -> None:
        selections = []
        for row, finding in enumerate(self.findings):
            if not self._is_row_checked(row):
                continue
            cursor = QTextCursor(self.input_text.document())
            cursor.setPosition(finding.start)
            cursor.setPosition(finding.end, QTextCursor.KeepAnchor)
            selection = QTextEdit.ExtraSelection()
            selection.cursor = cursor
            selection.format = self._finding_highlight_format(
                finding,
                selected=row == self._selected_finding_index,
            )
            selections.append(selection)
        self.input_text.setExtraSelections(selections)
        self._highlight_preview_findings()

    def _finding_highlight_format(
        self,
        finding: Finding,
        *,
        selected: bool,
    ) -> QTextCharFormat:
        paper = self._document_appearance == DOCUMENT_APPEARANCE_PAPER
        color = QColor(entity_color(finding.entity_type))
        if paper:
            color.setAlpha(
                PAPER_FINDING_SELECTED_HIGHLIGHT_ALPHA
                if selected
                else PAPER_FINDING_HIGHLIGHT_ALPHA
            )
            foreground = PAPER_EDITOR_TEXT_COLOR
        else:
            color.setAlpha(
                FINDING_SELECTED_HIGHLIGHT_ALPHA if selected else FINDING_HIGHLIGHT_ALPHA
            )
            foreground = EDITOR_SELECTION_TEXT_COLOR
        char_format = QTextCharFormat()
        char_format.setBackground(color)
        char_format.setForeground(QColor(foreground))
        return char_format

    def _preview_output_spans(self) -> dict[int, tuple[int, int]]:
        """Map every checked source finding to its replacement in the current preview."""
        if not self._analysis_preview_active:
            return {}

        source_text = self.input_text.toPlainText()
        if self.findings_stale or self._findings_source_text != source_text:
            return {}

        ordered_findings = sorted(
            (
                (row, finding)
                for row, finding in enumerate(self.findings)
                if self._is_row_checked(row)
            ),
            key=lambda item: item[1].start,
        )
        accepted_findings: list[tuple[int, Finding]] = []
        source_cursor = 0
        for row, finding in ordered_findings:
            if finding.start < source_cursor:
                continue
            accepted_findings.append((row, finding))
            source_cursor = finding.end
        mode = self._selected_mode()
        reversible_anonymizer = ReversibleAnonymizer() if mode == "reversible" else None
        if reversible_anonymizer is not None:
            reversible_anonymizer.reserve_placeholders(source_text)

        chunks: list[str] = []
        preview_spans: dict[int, tuple[int, int]] = {}
        source_cursor = 0
        output_cursor = 0
        for row, finding in accepted_findings:
            unchanged = source_text[source_cursor : finding.start]
            chunks.append(unchanged)
            output_cursor += len(unchanged)

            value = source_text[finding.start : finding.end]
            if reversible_anonymizer is not None:
                replacement = reversible_anonymizer.placeholder_for(
                    finding.entity_type,
                    value,
                )
            else:
                replacement = self.engine._recognizer._replacement(
                    value,
                    finding.entity_type,
                    mode,
                )
            replacement_start = output_cursor
            chunks.append(replacement)
            output_cursor += len(replacement)
            preview_spans[row] = (replacement_start, output_cursor)
            source_cursor = finding.end
            if (
                reversible_anonymizer is None
                and replacement.endswith(".")
                and source_cursor < len(source_text)
                and source_text[source_cursor] == "."
            ):
                source_cursor += 1

        chunks.append(source_text[source_cursor:])
        if "".join(chunks) != self.output_text.toPlainText():
            return {}
        return preview_spans

    def _highlight_preview_findings(self) -> None:
        selections: list[QTextEdit.ExtraSelection] = []
        for index, output_span in self._preview_output_spans().items():
            finding = self.findings[index]
            cursor = QTextCursor(self.output_text.document())
            cursor.setPosition(output_span[0])
            cursor.setPosition(output_span[1], QTextCursor.KeepAnchor)
            selection = QTextEdit.ExtraSelection()
            selection.cursor = cursor
            selection.format = self._finding_highlight_format(
                finding,
                selected=index == self._selected_finding_index,
            )
            selections.append(selection)
        self.output_text.setExtraSelections(selections)

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
        self._review_confirmed = False
        self._mark_workflow_changed("i dati selezionati")
        self._refresh_analysis_preview()
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
        self._reversible_map_path = None
        self._restore_mapping = ()
        self._output_provenance = None
        self._output_stale_reason = ""
        self._output_saved = True
        self._review_dirty = False
        self._review_confirmed = False
        self._result_used = False
        self._reversible_copy_copied = False
        self._reset_restored_comparison_state()
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
        """Il bottone "Aggiungi dato mancante" è supportato per i formati testuali e per
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
        if self._analysis_preview_active:
            return False
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

    def _is_current_reversible_output(self) -> bool:
        provenance = self._output_provenance
        return bool(
            provenance is not None
            and provenance.mode == "reversible"
            and provenance.kind == "anonymized"
            and self.reversible_mapping
            and self._output_is_usable()
        )

    def _is_restored_output(self) -> bool:
        provenance = self._output_provenance
        return bool(
            provenance is not None
            and provenance.kind == "restored"
            and self._output_is_usable()
        )

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
            map_required=bool(self.reversible_mapping) and kind == "anonymized",
            kind=kind,
        )
        self._output_stale_reason = ""
        self._output_saved = False
        if kind != "restored":
            self._reset_restored_comparison_state()
        self._reversible_map_saved = (
            not bool(self.reversible_mapping)
            or self.reversible_mapping == self.loaded_reversible_entries
        )
        if kind == "anonymized" and self.reversible_mapping and not self._reversible_map_saved:
            self._reversible_map_path = None
            self._restore_mapping = ()
        self._review_dirty = False
        self._result_used = False
        self._reversible_copy_copied = False
        self._update_report()
        self._sync_action_state()

    def _clear_output_state(self) -> None:
        self._output_provenance = None
        self._output_stale_reason = ""
        self._output_saved = True
        self._result_used = False
        self._reversible_copy_copied = False
        self.anonymized_document = None
        self._reset_restored_comparison_state()
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
            self._review_confirmed = False
            self._result_used = False
            self._reversible_copy_copied = False
            self._mark_workflow_changed("la modalità di protezione")
        self._refresh_analysis_preview()
        self._update_mode_notice()
        self._sync_action_state()

    def _refresh_mode_cards(self) -> None:
        reversible_available = self._reversible_mode_available()
        unavailable_description = (
            "Reversibile non è disponibile per questo formato. "
            "Usa testo incollato, TXT o DOCX."
        )
        for mode, card in self.mode_cards.items():
            selected = self.mode_radios[mode].isChecked()
            unavailable = mode == "reversible" and not reversible_available
            object_name = "ModeCardSelected" if selected else "ModeCard"
            if card.objectName() != object_name:
                card.setObjectName(object_name)
                card.style().unpolish(card)
                card.style().polish(card)
            description = unavailable_description if unavailable else mode_note(mode)
            self.mode_descriptions[mode].setText(description)
            self.mode_descriptions[mode].setVisible(selected or unavailable)
            self.mode_radios[mode].setAccessibleDescription(description)

    def _update_mode_notice(self, *args) -> None:
        self._refresh_mode_cards()
        if self._output_provenance is None:
            self.result_frame.setVisible(False)

    def _update_report(self) -> None:
        provenance = self._output_provenance
        if provenance is None or not self._has_output():
            self.report_label.setText("")
            self.report_label.setAccessibleDescription("")
            self.report_label.setVisible(False)
            self.result_frame.setVisible(False)
            return

        if self._managed_output_is_stale():
            reason = self._output_stale_reason or "i dati di partenza"
            self._set_result_style("stale")
            self.result_title_label.setText("Risultato da rigenerare")
            self.result_subtitle_label.setText(
                f"Hai modificato {reason}. La copia precedente non è più coerente con le scelte correnti."
            )
            self.result_state_label.setText("NON UTILIZZABILE")
            self.result_metric_label.setVisible(False)
            self.result_meta_label.setVisible(False)
            self.result_categories_label.setVisible(False)
            self.report_label.setText(
                "Rianalizza i dati e crea una nuova copia protetta prima di copiarla o salvarla."
            )
            self.report_label.setVisible(True)
        elif provenance.kind == "restored":
            self._set_result_style("restored")
            self.result_title_label.setText("Dati personali ripristinati")
            self.result_subtitle_label.setText(
                "Confronta la risposta dell’IA con il testo ricostruito prima di salvarlo. "
                "I dati sono stati reinseriti soltanto sul tuo computer."
            )
            self.result_state_label.setText("ATTENZIONE · DATI PERSONALI")
            if provenance.excluded_findings:
                self.result_metric_label.setText(
                    f"Ripristinati {provenance.included_findings} di {provenance.total_findings} elementi"
                )
            else:
                self.result_metric_label.setText("File di ripristino applicato")
            self.result_meta_label.setText("Modalità Reversibile")
            self.result_metric_label.setVisible(True)
            self.result_meta_label.setVisible(True)
            self.result_categories_label.setVisible(False)
            missing_note = ""
            if provenance.excluded_findings == 1:
                missing_note = (
                    "Un elemento del File di ripristino non compariva nella risposta e non è stato reinserito. "
                )
            elif provenance.excluded_findings:
                missing_note = (
                    f"{provenance.excluded_findings} elementi del File di ripristino non comparivano "
                    "nella risposta e non sono stati reinseriti. "
                )
            self.report_label.setText(
                f"{missing_note}Questo testo contiene nuovamente dati personali. "
                "Non inviarlo a servizi di IA. Se devi condividerlo, crea una nuova copia protetta."
            )
            self.report_label.setVisible(True)
        else:
            self._set_result_style("ready")
            source_label = (
                "Il documento originale non è stato modificato."
                if self.loaded_document is not None and not self.document_text_dirty
                else "Il testo di partenza è rimasto invariato."
            )
            self.result_title_label.setText("Copia protetta pronta")
            self.result_subtitle_label.setText(
                f"{source_label} Elaborazione completata interamente sul tuo computer."
            )
            use_document_binary = self.anonymized_document is not None and not self.output_text_dirty
            if provenance.mode == "reversible" and not self._reversible_map_saved:
                result_state = "FILE DA SALVARE"
            elif self._output_saved:
                result_state = "SALVATA"
            elif self._result_used:
                result_state = "COPIATA"
            elif use_document_binary:
                result_state = "DA SALVARE"
            else:
                result_state = "PRONTA DA COPIARE"
            self.result_state_label.setText(result_state)
            included = provenance.included_findings
            protected_label = "dato protetto" if included == 1 else "dati protetti"
            self.result_metric_label.setText(f"{included} {protected_label}")
            current_format = self._output_format_label() if self.output_text_dirty else provenance.output_format
            self.result_meta_label.setText(
                f"Modalità {mode_label(provenance.mode)} · Formato {current_format}"
            )
            self.result_metric_label.setVisible(True)
            self.result_meta_label.setVisible(True)
            categories_text = self._result_categories_text()
            self.result_categories_label.setText(categories_text)
            self.result_categories_label.setVisible(bool(categories_text))
            attention_text, needs_attention = self._result_attention_text(provenance)
            self._set_styled_object_name(
                self.report_label,
                "ResultAttentionWarning" if needs_attention else "ResultAttention",
            )
            self.report_label.setText(attention_text)
            self.report_label.setVisible(bool(attention_text))

        accessible_summary = " ".join(
            part
            for part in (
                self.result_title_label.text(),
                self.result_subtitle_label.text(),
                self.result_metric_label.text() if not self.result_metric_label.isHidden() else "",
                self.result_meta_label.text() if not self.result_meta_label.isHidden() else "",
                self.result_categories_label.text() if not self.result_categories_label.isHidden() else "",
                self.report_label.text() if not self.report_label.isHidden() else "",
            )
            if part
        )
        self.result_frame.setAccessibleDescription(accessible_summary)
        self.report_label.setAccessibleDescription(self.report_label.text())
        self.result_frame.setVisible(True)
        if self._compact_height:
            self.result_subtitle_label.setVisible(False)
            self.result_categories_label.setVisible(False)

    def _set_styled_object_name(self, widget: QWidget, object_name: str) -> None:
        if widget.objectName() == object_name:
            return
        widget.setObjectName(object_name)
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _set_result_style(self, state: str) -> None:
        warning = state in {"stale", "restored"}
        self._set_styled_object_name(
            self.result_frame,
            "ResultSummaryStale"
            if state == "stale"
            else "ResultSummaryRestored"
            if state == "restored"
            else "ResultSummary",
        )
        self._set_styled_object_name(
            self.result_icon_label,
            "ResultIconWarning" if warning else "ResultIcon",
        )
        self._set_styled_object_name(
            self.result_state_label,
            "ResultStateWarning" if warning else "ResultState",
        )
        self._set_styled_object_name(
            self.report_label,
            "ResultAttentionWarning" if warning else "ResultAttention",
        )
        self.result_icon_label.setText("!" if warning else "✓")
        self.result_icon_label.setAccessibleName(
            "Richiede attenzione" if warning else "Operazione completata"
        )

    def _result_categories_text(self) -> str:
        counts = finding_counts(self._checked_findings())
        if not counts:
            return ""
        ordered = sorted(
            counts.items(),
            key=lambda item: (-item[1], entity_label(item[0], item[1])),
        )
        visible = ordered[:5]
        parts = [
            f"{count} {entity_label(entity_type, count)}"
            for entity_type, count in visible
        ]
        remaining = len(ordered) - len(visible)
        if remaining:
            category_label = "categoria" if remaining == 1 else "categorie"
            parts.append(f"+{remaining} {category_label}")
        return "Protetti: " + " · ".join(parts)

    def _result_attention_text(self, provenance: OutputProvenance) -> tuple[str, bool]:
        items: list[str] = []
        needs_attention = False
        if provenance.total_findings == 0:
            items.append("Nessun dato è stato riconosciuto automaticamente")
            needs_attention = True
        if provenance.excluded_findings:
            count = provenance.excluded_findings
            noun = "rilevamento resterà" if count == 1 else "rilevamenti resteranno"
            items.append(f"{count} {noun} leggibile per tua scelta")
            needs_attention = True
        low_confidence = sum(
            1 for finding in self._checked_findings() if finding.score < 0.8
        )
        if low_confidence:
            noun = "rilevamento ha" if low_confidence == 1 else "rilevamenti hanno"
            items.append(f"{low_confidence} {noun} affidabilità da verificare")
            needs_attention = True
        if provenance.used_ocr:
            items.append("È stato usato l’OCR locale: confronta l’anteprima con il documento")
            needs_attention = True
        if provenance.map_required and not self._reversible_map_saved:
            items.append("Salva il File di ripristino prima di usare il risultato")
            needs_attention = True
        elif provenance.mode == "reversible" and provenance.kind == "anonymized":
            if self._reversible_copy_copied:
                items.append(
                    "Prossimo passo: dopo aver usato l’IA, torna qui e seleziona "
                    "«Incolla la risposta dell’IA»"
                )
            else:
                items.append("Invia all’IA soltanto la copia protetta, mai il File di ripristino o la password")
        if self.output_text_dirty:
            items.append("Il risultato è stato modificato: il salvataggio sarà in TXT")
            needs_attention = True
        if provenance.mode == "standard":
            items.append("Standard conserva iniziali e parte del contesto")
        items.append("Rileggi il risultato prima di condividerlo")
        return ". ".join(items) + ".", needs_attention

    def _pdf_choice_available(self) -> bool:
        return (
            self.loaded_document is not None
            and self.loaded_document.extension == ".pdf"
            and not self.document_text_dirty
            and not self._output_is_usable()
        )

    def _reversible_mode_available(self) -> bool:
        if self.loaded_document is None or self.document_text_dirty:
            return True
        return self.loaded_document.extension in REVERSIBLE_DOCUMENT_EXTENSIONS

    def _pdf_conversion_requested(self) -> bool:
        return self._pdf_choice_available() and self.pdf_choice_radios["text"].isChecked()

    def _refresh_pdf_choice_cards(self) -> None:
        for choice, card in self.pdf_choice_cards.items():
            object_name = (
                "PdfChoiceCardSelected"
                if self.pdf_choice_radios[choice].isChecked()
                else "PdfChoiceCard"
            )
            if card.objectName() != object_name:
                card.setObjectName(object_name)
                card.style().unpolish(card)
                card.style().polish(card)

    def _handle_pdf_choice_toggled(self, checked: bool) -> None:
        if not checked:
            return
        self._review_confirmed = False
        self._result_used = False
        self._reversible_copy_copied = False
        self._refresh_pdf_choice_cards()
        self._sync_action_state()

    def _primary_state(self) -> tuple[str, str, bool]:
        """Return (action_kind, button_label, enabled) for the single step-aware primary button."""
        input_has_text = bool(self.input_text.toPlainText().strip())
        output_has_text = bool(self.output_text.toPlainText().strip())
        if self._pdf_conversion_requested():
            return "convert_pdf", "Trasforma e analizza", input_has_text
        if self._output_is_usable():
            if self._is_restored_output():
                label = "Salva di nuovo" if self._output_saved else "Salva testo ricostruito"
                return "save_restored", label, output_has_text
            if self._is_current_reversible_output():
                if not self._reversible_map_saved:
                    return "save_map", "Salva il file di ripristino", True
                if self._reversible_copy_copied:
                    return "restore", "Incolla la risposta dell’IA", True
                return "copy", "Copia per l’IA", output_has_text
            use_document_binary = self.anonymized_document is not None and not self.output_text_dirty
            if use_document_binary:
                label = "Salva di nuovo" if self._result_used else "Salva copia protetta"
                return "save", label, True
            label = "Copia di nuovo" if self._result_used else "Copia per l’IA"
            return "copy", label, output_has_text
        if not input_has_text:
            return "load", "Carica documento", True
        if self._findings_ready_for_filtering() and input_has_text:
            if not self._review_confirmed:
                return "review", "Ho controllato, continua", True
            return "anonymize", "Crea copia protetta", True
        label = "Rianalizza dati" if self._managed_output_is_stale() else "Analizza dati"
        return "analyze", label, input_has_text

    def _primary_action(self) -> None:
        kind, _label, _enabled = self._primary_state()
        if kind == "load":
            self.open_file()
        elif kind == "convert_pdf":
            self._extract_document_as_text()
        elif kind in {"save", "save_restored"}:
            self.save_output()
        elif kind == "save_map":
            self.save_reversible_map()
        elif kind == "copy":
            self.copy_output()
        elif kind == "restore":
            self.restore_with_reversible_map()
        elif kind == "review":
            self._review_confirmed = True
            self.statusBar().showMessage(
                "Revisione confermata. Ora puoi creare la copia protetta.",
                4000,
            )
            self._sync_action_state()
        elif kind == "anonymize":
            self.anonymize_text()
        else:
            self.analyze_text()

    def _review_secondary_action(self) -> None:
        kind, _label, _enabled = self._primary_state()
        if (
            kind in {"save_map", "copy", "save", "restore"}
            and self._output_provenance is not None
            and self._output_provenance.kind == "anonymized"
        ):
            self._review_confirmed = False
            self._mark_workflow_changed("la revisione riaperta")
            self.statusBar().showMessage(
                "Revisione riaperta. Controlla le selezioni e crea di nuovo la copia protetta.",
                5000,
            )
            self._sync_action_state()
            return
        if kind == "anonymize":
            self._review_confirmed = False
            self.statusBar().showMessage(
                "Revisione riaperta. Controlla o aggiungi i dati mancanti.",
                4000,
            )
            self._sync_action_state()
            return
        self.add_manual_finding()

    def _set_primary_attention(self, active: bool) -> None:
        self.primary_button.setProperty("attention", active)
        self.primary_button.style().unpolish(self.primary_button)
        self.primary_button.style().polish(self.primary_button)

    def _cue_primary_action(self) -> None:
        if not self.primary_button.isEnabled():
            return
        self._primary_attention_timer.stop()
        self._set_primary_attention(True)
        self._primary_attention_timer.start()

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
        self._refresh_text_panel_presentation()
        self.source_view_toggle.setEnabled(
            self._restored_comparison_active() and not busy
        )
        pdf_choice_available = self._pdf_choice_available()
        self.pdf_choice_frame.setVisible(pdf_choice_available)
        self._refresh_pdf_choice_cards()
        for radio in self.pdf_choice_radios.values():
            radio.setEnabled(pdf_choice_available and not busy)
        kind, label, primary_enabled = self._primary_state()
        self.primary_button.setText(label)
        self.primary_button.setAccessibleName(label)
        primary_descriptions = {
            "load": "Apre un documento locale. In alternativa puoi incollare il testo nel riquadro Originale.",
            "convert_pdf": "Trasforma il PDF in testo normalizzato e avvia una nuova analisi locale.",
            "analyze": "Analizza il testo corrente e prepara i dati rilevati per la revisione.",
            "review": "Conferma che hai controllato le evidenziazioni e le spunte dei dati rilevati.",
            "anonymize": "Conferma le spunte correnti e genera un nuovo risultato anonimizzato.",
            "copy": "Copia la versione protetta negli appunti per usarla con lo strumento di IA che preferisci.",
            "save": "Salva sul dispositivo una nuova copia protetta senza modificare il documento originale.",
            "save_map": (
                "Salva e cifra il File di ripristino prima che la copia protetta possa essere condivisa."
            ),
            "restore": "Apre lo spazio dedicato in cui incollare la risposta dell’IA e ripristinare i dati localmente.",
            "save_restored": "Salva sul dispositivo il testo che contiene nuovamente i dati personali.",
        }
        self.primary_button.setAccessibleDescription(primary_descriptions[kind])
        if hasattr(self, "primary_action"):
            self.primary_action.setText(label)
        self.primary_button.setEnabled(primary_enabled and not busy)
        self.load_button.setEnabled(not busy)
        self.load_button.setVisible(False)
        copy_allowed = (
            output_has_text
            and output_usable
            and not self._is_restored_output()
            and (not self._is_current_reversible_output() or self._reversible_map_saved)
        )
        copy_blocked_by_map = (
            self._is_current_reversible_output() and not self._reversible_map_saved
        )
        copy_description = (
            "Disponibile dopo aver salvato il File di ripristino."
            if copy_blocked_by_map
            else "Copia la versione protetta negli appunti per usarla con lo strumento di IA che preferisci."
        )
        self.copy_button.setAccessibleDescription(copy_description)
        self.copy_button.setToolTip(copy_description)
        save_allowed = (
            output_usable
            and (not self._is_current_reversible_output() or self._reversible_map_saved)
        )
        self.copy_button.setEnabled(copy_allowed and not busy)
        secondary_save_label = (
            "Salva copia protetta" if self._is_current_reversible_output() else "Salva anche come file"
        )
        self.save_button.setText(secondary_save_label)
        self.save_button.setAccessibleName(secondary_save_label)
        self.save_button.setVisible(kind == "copy" and output_usable)
        self.save_button.setEnabled(kind == "copy" and output_usable and not busy)
        self.clear_button.setVisible(has_anything)
        self.clear_button.setEnabled(has_anything and not busy)
        reviewing = kind == "review"
        can_return_to_review = kind == "anonymize"
        final_anonymized_result = (
            kind in {"save_map", "copy", "save", "restore"}
            and output_usable
            and self._output_provenance is not None
            and self._output_provenance.kind == "anonymized"
        )
        has_manual_selection = self.input_text.textCursor().hasSelection()
        if final_anonymized_result:
            self.add_selection_button.setText("Modifica selezioni")
            self.add_selection_button.setAccessibleName("Modifica selezioni")
            self.add_selection_button.setAccessibleDescription(
                "Riapre i dati rilevati e richiede di rigenerare la copia protetta."
            )
            self.add_selection_button.setToolTip(
                "Torna ai dati rilevati per modificare le scelte e creare una nuova copia protetta."
            )
        elif can_return_to_review:
            self.add_selection_button.setText("Torna alla revisione")
            self.add_selection_button.setAccessibleName("Torna alla revisione")
            self.add_selection_button.setAccessibleDescription(
                "Riapre il controllo dei dati rilevati prima di creare la copia protetta."
            )
            self.add_selection_button.setToolTip(
                "Torna ai dati rilevati per correggere spunte o aggiungere un dato mancante."
            )
        else:
            self.add_selection_button.setText("Aggiungi dato mancante")
            self.add_selection_button.setAccessibleName("Aggiungi dato mancante")
            self.add_selection_button.setAccessibleDescription(
                "Aggiunge ai dati rilevati la parola o frase selezionata nel testo originale."
            )
            self.add_selection_button.setToolTip(
                "Seleziona una parola o frase nel pannello «Testo originale» non rilevata "
                "automaticamente, poi clicca qui per aggiungerla manualmente."
            )
        self.add_selection_button.setVisible(
            reviewing or can_return_to_review or final_anonymized_result
        )
        self.add_selection_button.setEnabled(
            not busy
            and (
                final_anonymized_result
                or can_return_to_review
                or (
                    reviewing
                    and has_manual_selection
                    and input_has_text
                    and self._manual_add_supported()
                )
            )
        )
        self.findings_panel.setVisible(not output_usable)
        self.document_toolbar.sync_secondary_visibility()
        self.input_text.setReadOnly(busy or self._is_restored_output())
        self.output_text.setEnabled(not output_stale and not busy)
        self.output_text.setReadOnly(self._analysis_preview_active)
        self.findings_panel.setEnabled(not busy)
        reversible_available = self._reversible_mode_available()
        for mode, radio in self.mode_radios.items():
            radio.setEnabled(not busy and (mode != "reversible" or reversible_available))
        self._refresh_mode_cards()
        self.mode_cards["reversible"].setToolTip(
            ""
            if reversible_available
            else "Reversibile è disponibile per testo incollato, TXT e DOCX."
        )
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
            self.copy_output_action.setEnabled(copy_allowed and not busy)
            self.copy_output_action.setToolTip(copy_description)
            self.copy_output_action.setStatusTip(copy_description)
            self.save_output_action.setText(
                "Salva testo ricostruito..." if self._is_restored_output() else "Salva copia protetta..."
            )
            self.save_output_action.setEnabled(save_allowed and not busy)
            self.primary_action.setEnabled(primary_enabled and not busy)
            self.focus_search_action.setEnabled(
                bool(self.findings) and self._findings_ready_for_filtering() and not busy
            )
            self.activity_action.setEnabled(not busy)
        self._update_reversible_flow()
        self._update_map_status()
        self._update_workflow_steps()
        if kind != self._last_primary_phase and not busy:
            self._last_primary_phase = kind
            QTimer.singleShot(0, self._cue_primary_action)

    def _update_map_status(self) -> None:
        if self.reversible_mapping and not self._reversible_map_saved:
            label = f"File di ripristino da salvare · {len(self.reversible_mapping)} voci"
            object_name = "MapStatusWarning"
        elif self.reversible_mapping and self.loaded_reversible_entries == self.reversible_mapping:
            label = f"File di ripristino caricato · {len(self.reversible_mapping)} voci"
            object_name = "MapStatusReady"
        elif self.reversible_mapping:
            label = f"File di ripristino salvato · {len(self.reversible_mapping)} voci"
            object_name = "MapStatusReady"
        elif self._restore_mapping:
            label = f"File di ripristino disponibile · {len(self._restore_mapping)} voci"
            object_name = "MapStatusReady"
        else:
            label = "Il File di ripristino verrà creato con la copia"
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
            or bool(self._restore_mapping)
        )
        self.map_section_label.setVisible(show_map_status)
        self.map_status_label.setVisible(show_map_status)

    def _update_reversible_flow(self) -> None:
        visible = self._is_current_reversible_output()
        self.reversible_flow_frame.setVisible(visible)
        self.reversible_help_button.setEnabled(self._active_job is None)
        if not visible:
            self.reversible_restore_inline_button.setVisible(False)
            return

        if not self._reversible_map_saved:
            current = 0
            state_labels = ("DA SALVARE", "BLOCCATO", "BLOCCATO")
        elif not self._reversible_copy_copied:
            current = 1
            state_labels = ("SALVATO", "PRONTA", "BLOCCATO")
        else:
            current = 2
            state_labels = ("SALVATO", "COPIATO", "PRONTO")

        restore_ready = current == 2
        self.reversible_restore_inline_button.setVisible(restore_ready)
        self.reversible_restore_inline_button.setEnabled(
            restore_ready and self._active_job is None
        )

        object_names = {
            "pending": "ReversibleStepPending",
            "current": "ReversibleStepCurrent",
            "done": "ReversibleStepDone",
        }
        accessible_parts: list[str] = []
        for index, row in enumerate(self.reversible_step_frames):
            step_state = "done" if index < current else "current" if index == current else "pending"
            state_text = state_labels[index]
            self.reversible_step_dots[index].setText("✓" if step_state == "done" else str(index + 1))
            self.reversible_step_state_labels[index].setText(state_text)
            self.reversible_step_state_labels[index].setVisible(
                not (index == 2 and restore_ready)
            )
            action_hint = (
                " Usa il pulsante Incolla qui la risposta dell’IA."
                if index == 2 and restore_ready
                else ""
            )
            row.setAccessibleDescription(
                f"{state_text}. {'Passaggio corrente.' if step_state == 'current' else ''}{action_hint}"
            )
            accessible_parts.append(f"Passaggio {index + 1}: {state_text}")
            object_name = object_names[step_state]
            if row.objectName() != object_name:
                row.setObjectName(object_name)
                row.style().unpolish(row)
                row.style().polish(row)
                for child in row.findChildren(QLabel):
                    child.style().unpolish(child)
                    child.style().polish(child)
                    child.updateGeometry()
                row.updateGeometry()

        self.reversible_flow_frame.setAccessibleDescription(". ".join(accessible_parts))

    def _workflow_step_states(self) -> list[str]:
        phase, _label, _enabled = self._primary_state()
        phase_index = {
            "load": 0,
            "convert_pdf": 1,
            "analyze": 1,
            "review": 2,
            "anonymize": 3,
            "save_map": 4,
            "copy": 4,
            "save": 4,
            "restore": 4,
            "save_restored": 4,
        }[phase]
        ordinary_result_done = (
            phase in {"copy", "save"}
            and self._result_used
            and not (
                self._output_provenance is not None
                and self._output_provenance.mode == "reversible"
            )
        )
        restored_result_done = phase == "save_restored" and self._output_saved
        if ordinary_result_done or restored_result_done:
            return ["done"] * len(self.step_rows)
        return [
            "done" if index < phase_index else "current" if index == phase_index else "pending"
            for index in range(len(self.step_rows))
        ]

    def _update_workflow_steps(self) -> None:
        object_names = {"pending": "StepRowPending", "current": "StepRowCurrent", "done": "StepRowDone"}
        for index, (row, step_state) in enumerate(
            zip(self.step_rows, self._workflow_step_states()),
            start=1,
        ):
            self.step_dots[index - 1].setText("✓" if step_state == "done" else str(index))
            row.setAccessibleDescription(
                "Completato" if step_state == "done" else "Passaggio corrente" if step_state == "current" else "Da fare"
            )
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
                self._review_confirmed = False
                self._result_used = False
                self._reversible_copy_copied = False
                self._mark_workflow_changed("il testo sorgente")
                self._refresh_analysis_preview()
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
        self._analysis_preview_active = False
        self._set_output_presentation(preview=False)
        self._updating_output_text = True
        try:
            self.output_text.setPlainText(text)
        finally:
            self._updating_output_text = False
        self.output_text.setExtraSelections([])
        self.output_text_dirty = False
        if text.strip():
            self._show_result_workspace()
        elif not self._findings_ready_for_filtering():
            self._show_input_workspace()
        self._align_output_scroll_to_source()
        self._schedule_text_scroll_alignment()
        self._sync_action_state()

    def _set_analysis_preview(self, text: str) -> None:
        self._analysis_preview_active = True
        self._set_output_presentation(preview=True)
        self._updating_output_text = True
        try:
            self.output_text.setPlainText(text)
        finally:
            self._updating_output_text = False
        self.output_text_dirty = False
        self._highlight_preview_findings()
        if text.strip():
            self._show_result_workspace()
        self._align_output_scroll_to_source()
        self._schedule_text_scroll_alignment()
        self._sync_action_state()

    def _refresh_analysis_preview(self) -> None:
        if self._output_provenance is not None:
            return
        if not self._findings_ready_for_filtering():
            if self._analysis_preview_active:
                self._set_output_text("")
            return
        source_text = self.input_text.toPlainText()
        if not source_text.strip():
            if self._analysis_preview_active:
                self._set_output_text("")
            return
        preview_text = self.engine.anonymize(
            source_text,
            self._checked_findings(),
            self._selected_mode(),
        )
        self._set_analysis_preview(preview_text)

    def _set_restored_comparison_source(self, text: str) -> None:
        self._restored_ai_response = text
        self._show_original_in_restored_comparison = False
        self.ai_response_text.setPlainText(text)
        cursor = self.ai_response_text.textCursor()
        cursor.movePosition(QTextCursor.Start)
        self.ai_response_text.setTextCursor(cursor)

    def _reset_restored_comparison_state(self) -> None:
        self._restored_ai_response = ""
        self._show_original_in_restored_comparison = False
        if hasattr(self, "ai_response_text"):
            self.ai_response_text.clear()

    def _restored_comparison_active(self) -> bool:
        return bool(self._restored_ai_response and self._is_restored_output())

    def _toggle_restored_comparison_source(self) -> None:
        if not self._restored_comparison_active():
            return
        self._show_original_in_restored_comparison = (
            not self._show_original_in_restored_comparison
        )
        self._refresh_text_panel_presentation()
        self._align_visible_source_scroll_to_output()
        visible_editor = (
            self.input_text
            if self._show_original_in_restored_comparison
            else self.ai_response_text
        )
        visible_editor.setFocus(Qt.OtherFocusReason)

    def _refresh_text_panel_presentation(self) -> None:
        if not hasattr(self, "output_panel_title"):
            return

        restored_output = self._is_restored_output()
        comparison_active = restored_output and bool(self._restored_ai_response)
        if comparison_active:
            self.source_view_toggle.setVisible(True)
            self.source_view_notice.setVisible(True)
            if self._show_original_in_restored_comparison:
                self.source_view_stack.setCurrentWidget(self.input_text)
                self.input_panel_title.setText("Documento originale")
                self.source_view_notice.setText(
                    "Documento di partenza · conservato senza modifiche"
                )
                self.source_view_toggle.setText("Mostra risposta IA")
                self.source_view_toggle.setAccessibleName("Mostra risposta dell’IA")
            else:
                self.source_view_stack.setCurrentWidget(self.ai_response_text)
                self.input_panel_title.setText("Risposta dell’IA")
                self.source_view_notice.setText(
                    "Prima del ripristino locale · testo incollato senza modifiche"
                )
                self.source_view_toggle.setText("Mostra originale")
                self.source_view_toggle.setAccessibleName("Mostra documento originale")
            self.source_view_notice.setAccessibleName("Testo mostrato nel confronto")
            self.source_view_notice.setAccessibleDescription(
                self.source_view_notice.text()
            )
        else:
            self._show_original_in_restored_comparison = False
            self.source_view_stack.setCurrentWidget(self.input_text)
            self.input_panel_title.setText("Testo originale")
            self.source_view_notice.setVisible(False)
            self.source_view_toggle.setVisible(False)

        if restored_output:
            self.output_panel_title.setText("Testo ricostruito")
            self.output_preview_inline_notice.setVisible(False)
            self._set_styled_object_name(
                self.output_preview_notice,
                "RestoredOutputNotice",
            )
            self.output_preview_notice.setText(
                "Contiene dati personali. Salvalo sul dispositivo e non inviarlo all’IA."
            )
            self.output_preview_notice.setAccessibleName("Avviso dati personali")
            self.output_preview_notice.setAccessibleDescription(
                self.output_preview_notice.text()
            )
            self.output_preview_notice.setVisible(True)
            self.output_text.setAccessibleName("Testo ricostruito con dati personali")
            self.output_text.setAccessibleDescription(
                "Risposta ricostruita localmente da OMISSIS. Contiene nuovamente i dati personali originali."
            )
            return

        self._set_styled_object_name(self.output_preview_notice, "OutputPreviewNotice")
        self.output_preview_notice.setAccessibleName("Stato dell’anteprima")
        if self._analysis_preview_active:
            self.output_panel_title.setText("Anteprima anonimizzata")
            self.output_preview_inline_notice.setVisible(True)
            self.output_preview_notice.setVisible(False)
            self.output_text.setAccessibleName("Anteprima anonimizzata")
            self.output_text.setAccessibleDescription(
                "Anteprima aggiornata in base ai dati selezionati. Non è ancora il documento definitivo."
            )
            return
        self.output_panel_title.setText("Testo anonimizzato")
        self.output_preview_inline_notice.setVisible(False)
        self.output_preview_notice.setVisible(False)
        self.output_text.setAccessibleName("Testo anonimizzato")
        self.output_text.setAccessibleDescription(
            "Risultato prodotto da OMISSIS. Se diventa obsoleto viene disabilitato fino alla rigenerazione."
        )

    def _set_output_presentation(self, *, preview: bool) -> None:
        self._analysis_preview_active = preview
        self._refresh_text_panel_presentation()

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
            return f"{self.loaded_document.path.stem}-ripristino{MAP_EXTENSION}"
        return f"omissis-ripristino{MAP_EXTENSION}"

    def _ask_passphrase(self, title: str, label: str, *, confirm: bool = False) -> str | None:
        dialog = QDialog(self)
        dialog.setObjectName("InfoDialog")
        dialog.setWindowTitle(title)
        dialog.setWindowModality(Qt.WindowModal)
        dialog.setModal(True)
        dialog.setFixedWidth(520)
        dialog.setAccessibleName(title)
        dialog.setAccessibleDescription(label)

        heading = QLabel(title)
        heading.setObjectName("DialogTitle")

        details = QLabel(label)
        details.setObjectName("DialogDetails")
        details.setWordWrap(True)

        password_label = QLabel("Password")
        password_label.setObjectName("FieldLabel")
        password_edit = QLineEdit()
        password_edit.setObjectName("PassphraseEdit")
        password_edit.setEchoMode(QLineEdit.Password)
        password_edit.setPlaceholderText("Inserisci la password")
        password_edit.setAccessibleName("Password del File di ripristino")
        password_label.setBuddy(password_edit)

        confirmation_label = QLabel("Ripeti la password")
        confirmation_label.setObjectName("FieldLabel")
        confirmation_edit = QLineEdit()
        confirmation_edit.setObjectName("PassphraseConfirmationEdit")
        confirmation_edit.setEchoMode(QLineEdit.Password)
        confirmation_edit.setPlaceholderText("Inserisci di nuovo la password")
        confirmation_edit.setAccessibleName("Conferma la password del File di ripristino")
        confirmation_label.setBuddy(confirmation_edit)

        validation_label = QLabel()
        validation_label.setObjectName("RestoreValidationError")
        validation_label.setWordWrap(True)
        validation_label.setAccessibleName("Controllo della password")
        validation_label.setVisible(False)

        cancel_button = QPushButton("Annulla")
        cancel_button.setObjectName("SecondaryButton")
        cancel_button.setAutoDefault(False)
        confirm_button = QPushButton("Conferma")
        confirm_button.setObjectName("PrimaryButton")
        confirm_button.setAutoDefault(False)

        def show_validation_error(message: str, field: QLineEdit) -> None:
            validation_label.setText(message)
            validation_label.setAccessibleDescription(message)
            validation_label.setVisible(True)
            field.selectAll()
            field.setFocus(Qt.OtherFocusReason)

        def validate_and_accept() -> None:
            password = password_edit.text()
            if not password.strip():
                show_validation_error(
                    "Inserisci una password per proteggere il File di ripristino.",
                    password_edit,
                )
                return
            if confirm and not confirmation_edit.text():
                show_validation_error(
                    "Ripeti la password nel secondo campo.",
                    confirmation_edit,
                )
                return
            if confirm and password != confirmation_edit.text():
                show_validation_error(
                    "Le password non coincidono. Controllale e riprova.",
                    confirmation_edit,
                )
                return
            dialog.accept()

        cancel_button.clicked.connect(dialog.reject)
        confirm_button.clicked.connect(validate_and_accept)
        if confirm:
            password_edit.returnPressed.connect(
                lambda: confirmation_edit.setFocus(Qt.OtherFocusReason)
            )
            confirmation_edit.returnPressed.connect(validate_and_accept)
        else:
            password_edit.returnPressed.connect(validate_and_accept)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(cancel_button)
        button_row.addWidget(confirm_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(11)
        layout.addWidget(heading)
        layout.addWidget(details)
        layout.addWidget(password_label)
        layout.addWidget(password_edit)
        if confirm:
            layout.addWidget(confirmation_label)
            layout.addWidget(confirmation_edit)
        layout.addWidget(validation_label)
        layout.addLayout(button_row)
        dialog.setLayout(layout)
        dialog.setStyleSheet(APP_STYLE)
        if confirm:
            dialog.setTabOrder(password_edit, confirmation_edit)
            dialog.setTabOrder(confirmation_edit, cancel_button)
        else:
            dialog.setTabOrder(password_edit, cancel_button)
        dialog.setTabOrder(cancel_button, confirm_button)

        QTimer.singleShot(0, lambda: password_edit.setFocus(Qt.OtherFocusReason))
        if dialog.exec() != QDialog.Accepted:
            return None
        return password_edit.text()


def main() -> int:
    app = QApplication(sys.argv)
    _load_app_fonts()
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
