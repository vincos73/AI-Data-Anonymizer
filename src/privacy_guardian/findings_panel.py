"""Standalone "Dati rilevati" panel: a filterable/searchable tree of findings.

Replaces the old flat QTableWidget with a QTreeView that can present findings either
as a flat list (one row per finding) or, once there are many, grouped by entity type
with one child row per distinct value. See findings_panel design notes in the Batch B
redesign brief for the exact behaviour this widget must implement.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QModelIndex, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from privacy_guardian.entity_categories import (
    CHECKSUM_TYPES,
    FILTER_CATEGORIES,
    entity_color,
    filter_category,
)
from privacy_guardian.models import Finding
from privacy_guardian.reporting import entity_label, source_label


GROUP_THRESHOLD = 30
ROW_HEIGHT = 33

# Custom item-data roles used to carry finding state alongside the display text.
ROLE_FINDING_INDICES = Qt.UserRole + 1
ROLE_IS_GROUP = Qt.UserRole + 2
ROLE_ENTITY_TYPE = Qt.UserRole + 3
ROLE_SCORE = Qt.UserRole + 4
ROLE_INCLUDED = Qt.UserRole + 5


class _FindingsDelegate(QStyledItemDelegate):
    """Paints the colored type badge, the value column (+ checksum mark) and the
    confidence bar. Columns 0-2 are custom-painted; column 3 (Origine) and group
    rows use the default rendering."""

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        size = super().sizeHint(option, index)
        return QSize(size.width(), max(size.height(), ROW_HEIGHT))

    def paint(self, painter, option: QStyleOptionViewItem, index: QModelIndex) -> None:  # noqa: ANN001
        column = index.column()
        is_group = bool(index.data(ROLE_IS_GROUP))
        if is_group or column not in (0, 1, 2):
            super().paint(painter, option, index)
            return

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        widget = opt.widget
        style = widget.style() if widget is not None else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, widget)

        type_index = index.sibling(index.row(), 0)
        included = bool(type_index.data(ROLE_INCLUDED))
        text_rect = style.subElementRect(QStyle.SE_ItemViewItemText, opt, widget)

        painter.save()
        if not included:
            painter.setOpacity(0.7)

        if column == 0:
            self._paint_type_badge(painter, option, text_rect, index)
        elif column == 1:
            self._paint_value(painter, text_rect, index)
        elif column == 2:
            self._paint_confidence(painter, text_rect, index)
        painter.restore()

    def _paint_type_badge(self, painter, option: QStyleOptionViewItem, text_rect: QRect, index: QModelIndex) -> None:  # noqa: ANN001
        entity_type = index.data(ROLE_ENTITY_TYPE) or ""
        text = index.data(Qt.DisplayRole) or ""
        color = QColor(entity_color(entity_type))

        if option.state & QStyle.State_Selected:
            stripe = QRect(option.rect.left(), option.rect.top() + 2, 2, option.rect.height() - 4)
            painter.fillRect(stripe, color)

        badge_rect = text_rect.adjusted(0, 5, -2, -5)
        background = QColor(color)
        background.setAlpha(31)  # ~12% opacity
        painter.setPen(Qt.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(badge_rect, 5, 5)

        font = QFont(painter.font())
        font.setPixelSize(11)
        font.setWeight(QFont.DemiBold)
        painter.setFont(font)
        painter.setPen(color)
        painter.drawText(badge_rect, Qt.AlignCenter, text)

    def _paint_value(self, painter, text_rect: QRect, index: QModelIndex) -> None:  # noqa: ANN001
        entity_type = index.data(ROLE_ENTITY_TYPE) or ""
        text = index.data(Qt.DisplayRole) or ""
        is_checksum = entity_type in CHECKSUM_TYPES

        font = QFont(painter.font())
        if is_checksum:
            font.setFamily("IBM Plex Mono")
            font.setPixelSize(11)
        painter.setFont(font)

        if is_checksum:
            metrics = painter.fontMetrics()
            base_width = metrics.horizontalAdvance(text)
            painter.setPen(QColor("#E8EDF2"))
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, text)
            check_rect = QRect(
                text_rect.left() + base_width, text_rect.top(), max(0, text_rect.width() - base_width), text_rect.height()
            )
            painter.setPen(QColor("#4CC38A"))
            painter.drawText(check_rect, Qt.AlignVCenter | Qt.AlignLeft, " ✓")
        else:
            painter.setPen(QColor("#E8EDF2"))
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, text)

    def _paint_confidence(self, painter, text_rect: QRect, index: QModelIndex) -> None:  # noqa: ANN001
        score = index.data(ROLE_SCORE)
        if score is None:
            return
        bar_w, bar_h = 44, 4
        bar_x = text_rect.left()
        bar_y = text_rect.top() + (text_rect.height() - bar_h) // 2
        bg_rect = QRect(bar_x, bar_y, bar_w, bar_h)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#232D38"))
        painter.drawRoundedRect(bg_rect, 2, 2)

        fill_color = QColor("#4CC38A") if score >= 0.8 else QColor("#D9A13B")
        fill_w = max(0, min(bar_w, round(bar_w * score)))
        if fill_w:
            painter.setBrush(fill_color)
            painter.drawRoundedRect(QRect(bar_x, bar_y, fill_w, bar_h), 2, 2)

        font = QFont(painter.font())
        font.setFamily("IBM Plex Mono")
        font.setPixelSize(11)
        painter.setFont(font)
        painter.setPen(QColor("#AABBCB"))
        score_rect = QRect(bar_x + bar_w + 8, text_rect.top(), max(0, text_rect.width() - bar_w - 8), text_rect.height())
        painter.drawText(score_rect, Qt.AlignVCenter | Qt.AlignLeft, f"{score:.2f}")


class FindingsPanel(QFrame):
    """Self-contained "Dati rilevati" panel: header (title/counter/filters/search),
    an optional PDF/DOCX notice bar, and the findings tree itself."""

    finding_selected = Signal(int)
    inclusion_changed = Signal()
    extract_as_text_requested = Signal()
    selection_cleared = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Panel")

        self._findings: list[Finding] = []
        self._source_text: str = ""
        self._checkable: bool = True
        self._included: list[bool] = []
        self._selected_index: int | None = None
        self._filter_category: str = "Tutti"
        self._search_text: str = ""
        self._updating_model: bool = False
        self._index_to_item: dict[int, QStandardItem] = {}
        self._pill_buttons: dict[str, QPushButton] = {}

        self._build_ui()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        self.title_label = QLabel("Dati rilevati")
        self.title_label.setObjectName("SectionTitle")

        self.counter_label = QLabel("0 elementi")
        self.counter_label.setObjectName("FindingsCounter")

        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("FindingsSearch")
        self.search_edit.setPlaceholderText("Cerca valore…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setFixedWidth(220)
        self.search_edit.textChanged.connect(self._handle_search_changed)

        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        top_row.addWidget(self.title_label)
        top_row.addWidget(self.counter_label)
        top_row.addStretch(1)
        top_row.addWidget(self.search_edit)

        self.pill_group = QButtonGroup(self)
        self.pill_group.setExclusive(True)
        pill_row = QHBoxLayout()
        pill_row.setSpacing(6)
        for category in FILTER_CATEGORIES:
            button = QPushButton(category)
            button.setObjectName("FilterPill")
            button.setCheckable(True)
            button.setProperty("category", category)
            self.pill_group.addButton(button)
            self._pill_buttons[category] = button
            pill_row.addWidget(button)
        pill_row.addStretch(1)
        # Set the default checked state before wiring the signal: at this point
        # the tree/model below don't exist yet, so a triggered _handle_pill_toggled
        # would blow up trying to rebuild a model that isn't there.
        self._pill_buttons["Tutti"].setChecked(True)
        for button in self._pill_buttons.values():
            button.toggled.connect(self._handle_pill_toggled)

        header_layout = QVBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        header_layout.addLayout(top_row)
        header_layout.addLayout(pill_row)

        # ---- Unsupported-format notice (PDF/DOCX) ----
        self.notice_frame = QFrame()
        self.notice_frame.setObjectName("UnsupportedNotice")
        self.notice_label = QLabel(
            "La selezione manuale non è disponibile su PDF e DOCX: viene anonimizzato tutto ciò "
            "che è rilevato. Per scegliere manualmente, estrai il contenuto come testo (il "
            "salvataggio sarà in .txt)."
        )
        self.notice_label.setObjectName("UnsupportedNoticeLabel")
        self.notice_label.setWordWrap(True)
        self.notice_button = QPushButton("Estrai come testo →")
        self.notice_button.setObjectName("UnsupportedNoticeButton")
        self.notice_button.clicked.connect(self.extract_as_text_requested)
        notice_layout = QHBoxLayout()
        notice_layout.setContentsMargins(12, 8, 12, 8)
        notice_layout.setSpacing(10)
        notice_layout.addWidget(self.notice_label, 1)
        notice_layout.addWidget(self.notice_button, 0, Qt.AlignVCenter)
        self.notice_frame.setLayout(notice_layout)
        self.notice_frame.setVisible(False)

        # ---- Tree ----
        self._model = QStandardItemModel(0, 4, self)
        self._model.setHorizontalHeaderLabels(["Tipo", "Valore", "Confidenza", "Origine"])
        self._model.itemChanged.connect(self._on_item_changed)

        self.tree = QTreeView()
        self.tree.setObjectName("FindingsTree")
        self.tree.setModel(self._model)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree.setAlternatingRowColors(False)
        self.tree.setRootIsDecorated(False)
        self.tree.setItemDelegate(_FindingsDelegate(self.tree))
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.tree.clicked.connect(self._handle_clicked)
        self.tree.installEventFilter(self)

        layout = QVBoxLayout()
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(8)
        layout.addLayout(header_layout)
        layout.addWidget(self.notice_frame)
        layout.addWidget(self.tree, 1)
        self.setLayout(layout)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    # ------------------------------------------------------------- public API

    def set_findings(self, findings: list[Finding], source_text: str, checkable: bool) -> None:
        self._findings = list(findings)
        self._source_text = source_text
        self._checkable = checkable
        self._included = [True] * len(self._findings)
        self._selected_index = None
        self._filter_category = "Tutti"
        self._search_text = ""
        blocker_was = self.search_edit.blockSignals(True)
        self.search_edit.clear()
        self.search_edit.blockSignals(blocker_was)
        pill_blocker = self._pill_buttons["Tutti"].blockSignals(True)
        self._pill_buttons["Tutti"].setChecked(True)
        self._pill_buttons["Tutti"].blockSignals(pill_blocker)
        self._update_pill_labels()
        self._rebuild_model()

    def included_mask(self) -> list[bool]:
        return list(self._included)

    def clear(self) -> None:
        self._findings = []
        self._source_text = ""
        self._included = []
        self._selected_index = None
        self._filter_category = "Tutti"
        self._search_text = ""
        blocker_was = self.search_edit.blockSignals(True)
        self.search_edit.clear()
        self.search_edit.blockSignals(blocker_was)
        pill_blocker = self._pill_buttons["Tutti"].blockSignals(True)
        self._pill_buttons["Tutti"].setChecked(True)
        self._pill_buttons["Tutti"].blockSignals(pill_blocker)
        self._update_pill_labels()
        self._rebuild_model()

    def select_finding(self, index: int) -> None:
        if index is None or not (0 <= index < len(self._findings)):
            return
        item = self._index_to_item.get(index)
        if item is None:
            changed = False
            if self._filter_category != "Tutti":
                self._filter_category = "Tutti"
                pill_blocker = self._pill_buttons["Tutti"].blockSignals(True)
                self._pill_buttons["Tutti"].setChecked(True)
                self._pill_buttons["Tutti"].blockSignals(pill_blocker)
                changed = True
            if self._search_text:
                self._search_text = ""
                blocker_was = self.search_edit.blockSignals(True)
                self.search_edit.clear()
                self.search_edit.blockSignals(blocker_was)
                changed = True
            if changed:
                self._rebuild_model()
                item = self._index_to_item.get(index)
        if item is None:
            return
        self._selected_index = index
        model_index = item.index()
        parent = model_index.parent()
        if parent.isValid():
            self.tree.expand(parent)
        self.tree.setCurrentIndex(model_index)
        self.tree.scrollTo(model_index)
        self.tree.viewport().update()

    def selected_finding(self) -> int | None:
        return self._selected_index

    def set_unsupported_notice(self, visible: bool) -> None:
        self.notice_frame.setVisible(visible)

    # ------------------------------------------------------------- internals

    def _handle_search_changed(self, text: str) -> None:
        self._search_text = text
        self._rebuild_model()

    def _handle_pill_toggled(self, checked: bool) -> None:
        if not checked:
            return
        button = self.sender()
        category = button.property("category") if button is not None else "Tutti"
        self._filter_category = category
        self._rebuild_model()

    def _handle_clicked(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        col0 = index.sibling(index.row(), 0)
        item = self._model.itemFromIndex(col0)
        if item is None:
            return
        if item.data(ROLE_IS_GROUP):
            return
        indices = item.data(ROLE_FINDING_INDICES) or []
        if not indices:
            return
        self._selected_index = indices[0]
        self.finding_selected.emit(indices[0])

    def eventFilter(self, obj, event) -> bool:  # noqa: ANN001
        if obj is self.tree and event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            self.tree.clearSelection()
            self.tree.setCurrentIndex(QModelIndex())
            self._selected_index = None
            self.selection_cleared.emit()
            return True
        return super().eventFilter(obj, event)

    def _pill_counts(self) -> dict[str, int]:
        counts = {category: 0 for category in FILTER_CATEGORIES}
        counts["Tutti"] = len(self._findings)
        for finding in self._findings:
            category = filter_category(finding.entity_type)
            counts[category] = counts.get(category, 0) + 1
        return counts

    def _update_pill_labels(self) -> None:
        counts = self._pill_counts()
        for category, button in self._pill_buttons.items():
            button.setText(f"{category} {counts.get(category, 0)}")

    def _value_text(self, index: int) -> str:
        finding = self._findings[index]
        return self._source_text[finding.start : finding.end].replace("\n", " ").strip()

    def _visible_indices(self) -> list[int]:
        search = self._search_text.strip().lower()
        result: list[int] = []
        for i, finding in enumerate(self._findings):
            if self._filter_category != "Tutti" and filter_category(finding.entity_type) != self._filter_category:
                continue
            if search and search not in self._value_text(i).lower():
                continue
            result.append(i)
        return result

    def _build_row_items(self, indices: list[int]) -> list[QStandardItem]:
        findings = [self._findings[i] for i in indices]
        entity_type = findings[0].entity_type
        included_all = all(self._included[i] for i in indices)
        included_any = any(self._included[i] for i in indices)

        type_item = QStandardItem(entity_label(entity_type, 1))
        type_item.setEditable(False)
        type_item.setData(list(indices), ROLE_FINDING_INDICES)
        type_item.setData(False, ROLE_IS_GROUP)
        type_item.setData(entity_type, ROLE_ENTITY_TYPE)
        type_item.setData(included_any, ROLE_INCLUDED)
        if self._checkable:
            type_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
            state = Qt.Checked if included_all else (Qt.PartiallyChecked if included_any else Qt.Unchecked)
            type_item.setData(state, Qt.CheckStateRole)
        else:
            type_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)

        base_value = self._value_text(indices[0])
        value_text = f"{base_value} ×{len(indices)}" if len(indices) > 1 else base_value
        value_item = QStandardItem(value_text)
        value_item.setEditable(False)
        value_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        value_item.setData(list(indices), ROLE_FINDING_INDICES)
        value_item.setData(entity_type, ROLE_ENTITY_TYPE)

        max_score = max(f.score for f in findings)
        score_item = QStandardItem(f"{max_score:.2f}")
        score_item.setEditable(False)
        score_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        score_item.setData(max_score, ROLE_SCORE)

        sources = {f.source for f in findings}
        origin_text = source_label(next(iter(sources))) if len(sources) == 1 else "Multipli"
        origin_item = QStandardItem(origin_text)
        origin_item.setEditable(False)
        origin_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)

        return [type_item, value_item, score_item, origin_item]

    def _refresh_group_item(self, group_item: QStandardItem) -> None:
        indices = group_item.data(ROLE_FINDING_INDICES) or []
        if not indices:
            return
        included_all = all(self._included[i] for i in indices)
        included_any = any(self._included[i] for i in indices)
        entity_type = group_item.data(ROLE_ENTITY_TYPE)
        excluded_count = sum(1 for i in indices if not self._included[i])
        distinct_values = group_item.rowCount()
        total = len(indices)
        group_item.setText(
            f"{entity_label(entity_type, 2)} — {total} occorrenze · "
            f"{distinct_values} valori distinti · {excluded_count} esclusi"
        )
        group_item.setData(included_any, ROLE_INCLUDED)
        if self._checkable:
            state = Qt.Checked if included_all else (Qt.PartiallyChecked if included_any else Qt.Unchecked)
            group_item.setData(state, Qt.CheckStateRole)

    def _populate_flat(self, visible: list[int]) -> None:
        for i in visible:
            row_items = self._build_row_items([i])
            self._model.appendRow(row_items)
            self._index_to_item[i] = row_items[0]

    def _populate_grouped(self, visible: list[int]) -> None:
        groups: dict[str, list[int]] = {}
        for i in visible:
            groups.setdefault(self._findings[i].entity_type, []).append(i)

        ordered_types = sorted(groups.keys(), key=lambda et: (-len(groups[et]), entity_label(et, 2)))

        for entity_type in ordered_types:
            indices = groups[entity_type]
            values: dict[str, list[int]] = {}
            for i in indices:
                values.setdefault(self._value_text(i), []).append(i)

            included_all = all(self._included[i] for i in indices)
            included_any = any(self._included[i] for i in indices)
            excluded_count = sum(1 for i in indices if not self._included[i])

            group_item = QStandardItem(
                f"{entity_label(entity_type, 2)} — {len(indices)} occorrenze · "
                f"{len(values)} valori distinti · {excluded_count} esclusi"
            )
            group_item.setEditable(False)
            group_font = QFont(group_item.font())
            group_font.setBold(True)
            group_item.setFont(group_font)
            group_item.setData(list(indices), ROLE_FINDING_INDICES)
            group_item.setData(True, ROLE_IS_GROUP)
            group_item.setData(entity_type, ROLE_ENTITY_TYPE)
            group_item.setData(included_any, ROLE_INCLUDED)
            if self._checkable:
                group_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
                state = Qt.Checked if included_all else (Qt.PartiallyChecked if included_any else Qt.Unchecked)
                group_item.setData(state, Qt.CheckStateRole)
            else:
                group_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)

            blanks = []
            for _ in range(3):
                blank = QStandardItem("")
                blank.setEditable(False)
                blank.setFlags(Qt.ItemIsEnabled)
                blanks.append(blank)

            self._model.appendRow([group_item] + blanks)
            row = self._model.rowCount() - 1
            self.tree.setFirstColumnSpanned(row, QModelIndex(), True)

            ordered_values = sorted(values.keys(), key=lambda value: (-len(values[value]), value.lower()))
            for value_text in ordered_values:
                child_indices = values[value_text]
                row_items = self._build_row_items(child_indices)
                group_item.appendRow(row_items)
                for idx in child_indices:
                    self._index_to_item[idx] = row_items[0]

            self.tree.setExpanded(group_item.index(), True)

    def _rebuild_model(self) -> None:
        self._updating_model = True
        try:
            self._model.removeRows(0, self._model.rowCount())
            self._index_to_item = {}
            visible = self._visible_indices()
            grouped = len(visible) > GROUP_THRESHOLD
            self.tree.setRootIsDecorated(grouped)
            if grouped:
                self._populate_grouped(visible)
            else:
                self._populate_flat(visible)
        finally:
            self._updating_model = False
        total = len(self._findings)
        item_label = "elemento" if total == 1 else "elementi"
        self.counter_label.setText(f"{total} {item_label}")

    def _on_item_changed(self, item: QStandardItem) -> None:
        if self._updating_model or item.column() != 0:
            return
        indices = item.data(ROLE_FINDING_INDICES) or []
        if not indices:
            return
        new_state = item.checkState()
        included_value = new_state != Qt.Unchecked
        self._updating_model = True
        try:
            for idx in indices:
                self._included[idx] = included_value
            if item.data(ROLE_IS_GROUP):
                for row in range(item.rowCount()):
                    child = item.child(row, 0)
                    if child is None:
                        continue
                    if self._checkable:
                        child.setData(Qt.Checked if included_value else Qt.Unchecked, Qt.CheckStateRole)
                    child.setData(included_value, ROLE_INCLUDED)
                self._refresh_group_item(item)
            else:
                parent = item.parent()
                if parent is not None:
                    self._refresh_group_item(parent)
            item.setData(included_value, ROLE_INCLUDED)
        finally:
            self._updating_model = False
        self.tree.viewport().update()
        self.inclusion_changed.emit()
