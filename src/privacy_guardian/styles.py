"""Dark Pro theme for the OMISSIS desktop app (QSS)."""

# Design tokens (kept here as a comment for reference — QSS below uses literal values
# because Qt's QSS engine does not support variables):
#   bg            #12181F   bg-rail        #0D1218
#   surface       #1A222B   surface-dim    #161D25   surface-selected #14202B
#   border        #232D38   border-strong  #35414E
#   text          #E8EDF2   text-title     #FFFFFF
#   text-2        #AABBCB   text-3         #8899AA   muted #5F6F7F
#   accent        #4FB8E7   on-accent      #0D1218
#   success       #4CC38A   warning        #D9A13B   map-gold #E5C368
#   step-done bg  #1A2E24   step-done border #2E6B4A  step-done text #7DD8A8
#   mode-selected bg #14202B   mode-selected border #2B6D8F

APP_STYLE = """
QMainWindow {
    background: #12181F;
}

QWidget {
    color: #E8EDF2;
    font-family: "IBM Plex Sans", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}

QDialog#InfoDialog {
    background: #12181F;
    color: #E8EDF2;
}

QDialog#InfoDialog QLabel {
    background: transparent;
    color: #E8EDF2;
}

QLabel#AboutDetails {
    color: #AABBCB;
    line-height: 1.5;
}

QLabel#AboutDetails a, QLabel#DialogDetails a, QLabel#NerHint a {
    color: #4FB8E7;
}

QLabel#DialogTitle {
    color: #FFFFFF;
    font-size: 18px;
    font-weight: 700;
}

QLabel#DialogDetails {
    color: #AABBCB;
    line-height: 1.5;
}

QMenuBar {
    background: #0D1218;
    color: #E8EDF2;
    border-bottom: 1px solid #232D38;
}

QMenuBar::item:selected {
    background: #1A222B;
}

QMenu {
    background: #1A222B;
    color: #E8EDF2;
    border: 1px solid #232D38;
}

QMenu::item:selected {
    background: #14202B;
    color: #4FB8E7;
}

QStatusBar {
    background: #0D1218;
    color: #8899AA;
    border-top: 1px solid #232D38;
}

QStatusBar QLabel {
    color: #8899AA;
    background: transparent;
}

/* ---------- Rail (left navigation column) ---------- */

QFrame#Rail {
    background: #0D1218;
    border: 0;
    border-right: 1px solid #232D38;
}

QScrollArea#RailScroll {
    background: transparent;
    border: 0;
}

QScrollArea#RailScroll > QWidget > QWidget {
    background: transparent;
}

QLabel#BrandMark {
    background: transparent;
}

QLabel#BrandLogo {
    color: #FFFFFF;
    font-size: 17px;
    font-weight: 700;
}

QLabel#Byline {
    color: #8899AA;
    font-size: 11px;
    font-weight: 500;
    padding-top: 2px;
}

QLabel#RailSectionLabel {
    color: #5F6F7F;
    font-size: 10.5px;
    font-weight: 700;
    letter-spacing: 1px;
    padding-top: 6px;
}

QLabel#LocalNotice {
    background: #161D25;
    color: #AABBCB;
    border: 1px solid #232D38;
    border-radius: 10px;
    padding: 10px 12px;
    font-size: 11.5px;
    line-height: 1.4;
}

QLabel#VersionPill {
    background: transparent;
    color: #5F6F7F;
    border: 0;
    padding: 2px 2px;
    font-family: "IBM Plex Mono", "Menlo", monospace;
    font-size: 11px;
}

/* ---------- Vertical stepper ---------- */

QFrame#StepRowPending, QFrame#StepRowCurrent, QFrame#StepRowDone {
    border-radius: 10px;
    border: 1px solid transparent;
    background: transparent;
}

QFrame#StepRowPending QLabel#StepTitle {
    color: #5F6F7F;
    font-size: 13px;
    font-weight: 500;
}

QFrame#StepRowPending QLabel#StepDot {
    color: #5F6F7F;
    background: #161D25;
    border: 1px solid #232D38;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 700;
}

QFrame#StepRowCurrent {
    background: #14202B;
    border: 1px solid #2B6D8F;
}

QFrame#StepRowCurrent QLabel#StepTitle {
    color: #E8EDF2;
    font-size: 13px;
    font-weight: 700;
}

QFrame#StepRowCurrent QLabel#StepDot {
    color: #0D1218;
    background: #4FB8E7;
    border: 1px solid #4FB8E7;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 700;
}

QFrame#StepRowDone {
    background: #1A2E24;
    border: 1px solid #2E6B4A;
}

QFrame#StepRowDone QLabel#StepTitle {
    color: #7DD8A8;
    font-size: 13px;
    font-weight: 600;
}

QFrame#StepRowDone QLabel#StepDot {
    color: #1A2E24;
    background: #7DD8A8;
    border: 1px solid #7DD8A8;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 700;
}

/* ---------- Protection mode radio cards ---------- */

QFrame#ModeCard {
    background: #161D25;
    border: 1px solid #232D38;
    border-radius: 10px;
}

QFrame#ModeCard:hover {
    border-color: #35414E;
}

QFrame#ModeCardSelected {
    background: #14202B;
    border: 1px solid #2B6D8F;
    border-radius: 10px;
}

QRadioButton#ModeCardRadio {
    color: #E8EDF2;
    font-size: 12.5px;
    font-weight: 600;
    spacing: 8px;
    background: transparent;
}

QRadioButton#ModeCardRadio::indicator {
    width: 14px;
    height: 14px;
    border-radius: 8px;
    border: 1px solid #35414E;
    background: #12181F;
}

QRadioButton#ModeCardRadio::indicator:checked {
    border: 1px solid #4FB8E7;
    background: #4FB8E7;
}

QLabel#ModeCardDescription {
    color: #AABBCB;
    font-size: 11px;
    line-height: 1.4;
    padding-left: 22px;
}

/* ---------- Recognition status ---------- */

QLabel#StatusOk {
    color: #4CC38A;
    font-size: 12px;
    font-weight: 600;
}

QLabel#StatusWarning {
    color: #D9A13B;
    font-size: 12px;
    font-weight: 600;
}

QLabel#NerHint {
    color: #8899AA;
    font-size: 11px;
    padding-left: 2px;
}

/* ---------- Main area ---------- */

QFrame#DocumentToolbar {
    background: #161D25;
    border: 1px solid #232D38;
    border-radius: 10px;
}

QLabel#DocumentNotice {
    background: transparent;
    color: #AABBCB;
    border: 0;
    padding: 0;
    line-height: 1.35;
    font-size: 12.5px;
}

QLabel#ReportNotice {
    background: #161D25;
    color: #AABBCB;
    border: 1px solid #232D38;
    border-radius: 10px;
    padding: 10px 12px;
    line-height: 1.35;
}

QLabel#NerNotice {
    background: #241B0C;
    color: #D9A13B;
    border: 1px solid #4A3A18;
    border-radius: 10px;
    padding: 10px 12px;
    line-height: 1.35;
}

QLabel#SectionTitle {
    color: #FFFFFF;
    font-size: 14px;
    font-weight: 700;
}

QFrame#Panel {
    background: #1A222B;
    border: 1px solid #232D38;
    border-radius: 10px;
}

QTextEdit {
    background: #12181F;
    color: #E8EDF2;
    border: 1px solid #232D38;
    border-radius: 7px;
    padding: 11px;
    selection-background-color: #2B6D8F;
    selection-color: #FFFFFF;
    font-size: 13px;
    line-height: 1.45;
}

QTextEdit:focus {
    border: 1px solid #4FB8E7;
}

QPushButton {
    min-height: 32px;
    border: 1px solid #35414E;
    border-radius: 7px;
    background: #1A222B;
    color: #E8EDF2;
    padding: 0 13px;
    font-weight: 600;
    font-size: 12.5px;
}

QPushButton:hover {
    background: #232D38;
    border-color: #4FB8E7;
}

QPushButton:pressed {
    background: #161D25;
}

QPushButton:disabled {
    color: #5F6F7F;
    background: #161D25;
    border-color: #232D38;
}

QPushButton#PrimaryButton {
    min-height: 36px;
    background: #4FB8E7;
    border-color: #4FB8E7;
    color: #0D1218;
    font-weight: 700;
}

QPushButton#PrimaryButton:hover {
    background: #6bc5ec;
}

QPushButton#PrimaryButton:pressed {
    background: #3fa2cf;
}

QPushButton#PrimaryButton:disabled {
    background: #223038;
    border-color: #232D38;
    color: #5F6F7F;
}

QPushButton#SecondaryButton {
    color: #AABBCB;
    background: #1A222B;
    border-color: #232D38;
}

QPushButton#SecondaryButton:hover {
    background: #232D38;
    color: #E8EDF2;
    border-color: #35414E;
}

QSplitter::handle {
    background: #12181F;
    width: 14px;
}

QSplitter#WorkspaceSplitter::handle {
    height: 10px;
    background: qlineargradient(
        x1: 0, y1: 0, x2: 0, y2: 1,
        stop: 0 transparent, stop: 0.46 transparent,
        stop: 0.5 #232D38,
        stop: 0.54 transparent, stop: 1 transparent
    );
}

/* Registro attività dialog still uses a plain QTableWidget. */
QTableWidget {
    background: #1A222B;
    color: #E8EDF2;
    alternate-background-color: #161D25;
    border: 1px solid #232D38;
    border-radius: 10px;
    gridline-color: #232D38;
    selection-background-color: #14202B;
    selection-color: #E8EDF2;
}

QHeaderView {
    background: #161D25;
}

QHeaderView::section {
    background: #161D25;
    color: #8899AA;
    border: 0;
    border-bottom: 1px solid #232D38;
    padding: 8px;
    font-weight: 700;
    font-size: 11px;
}

QTableWidget::item {
    padding: 6px;
    border: 0;
}

QTableWidget::item:selected {
    background: #14202B;
    color: #E8EDF2;
}

/* ---------- Findings panel (Dati rilevati) ---------- */

QLabel#FindingsCounter {
    color: #5F6F7F;
    font-size: 12px;
    font-weight: 500;
}

QPushButton#FilterPill {
    background: transparent;
    color: #AABBCB;
    border: 1px solid #35414E;
    border-radius: 99px;
    padding: 3px 12px;
    min-height: 22px;
    font-size: 11.5px;
    font-weight: 600;
}

QPushButton#FilterPill:hover {
    border-color: #4FB8E7;
    color: #E8EDF2;
}

QPushButton#FilterPill:checked {
    background: #4FB8E7;
    border-color: #4FB8E7;
    color: #0D1218;
}

QLineEdit#FindingsSearch {
    background: #12181F;
    color: #E8EDF2;
    border: 1px solid #232D38;
    border-radius: 7px;
    padding: 5px 10px;
    min-height: 22px;
    font-size: 12px;
}

QLineEdit#FindingsSearch:focus {
    border: 1px solid #4FB8E7;
}

QFrame#UnsupportedNotice {
    background: #241F10;
    border: 1px solid #6B5A2B;
    border-radius: 10px;
}

QLabel#UnsupportedNoticeLabel {
    background: transparent;
    color: #E5C368;
    font-size: 12px;
    line-height: 1.4;
}

QPushButton#UnsupportedNoticeButton {
    background: transparent;
    color: #E5C368;
    border: 1px solid #6B5A2B;
    font-size: 12px;
    font-weight: 700;
}

QPushButton#UnsupportedNoticeButton:hover {
    background: #2E2712;
    border-color: #E5C368;
}

QTreeView#FindingsTree {
    background: #161D25;
    color: #E8EDF2;
    border: 1px solid #232D38;
    border-radius: 10px;
    outline: 0;
    show-decoration-selected: 1;
}

QTreeView#FindingsTree::item {
    height: 33px;
    padding: 0 2px;
    border: 0;
    border-bottom: 1px solid #1D2531;
}

QTreeView#FindingsTree::item:hover {
    background: #1A222B;
}

QTreeView#FindingsTree::item:selected {
    background: #14202B;
    color: #E8EDF2;
}

QTreeView#FindingsTree::branch {
    background: transparent;
    border: 0;
}

QTreeView#FindingsTree QHeaderView::section {
    background: #161D25;
    color: #8899AA;
    border: 0;
    border-bottom: 1px solid #232D38;
    padding: 7px 8px;
    font-weight: 700;
    font-size: 10.5px;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #35414E;
    border-radius: 5px;
    min-height: 24px;
}

QScrollBar::handle:vertical:hover {
    background: #4FB8E7;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 0;
}

QScrollBar::handle:horizontal {
    background: #35414E;
    border-radius: 5px;
    min-width: 24px;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}
"""
