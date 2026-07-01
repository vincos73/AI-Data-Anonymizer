APP_STYLE = """
QMainWindow {
    background: #171d22;
}

QWidget {
    color: #edf3f6;
    font-family: "Helvetica Neue", "Arial", sans-serif;
    font-size: 13px;
}

QDialog#AboutDialog {
    background: #f7f8f7;
    color: #10161a;
}

QDialog#AboutDialog QLabel {
    background: transparent;
    color: #10161a;
}

QLabel#AboutDetails {
    color: #10161a;
    line-height: 1.45;
}

QMenuBar {
    background: #171d22;
    color: #edf3f6;
}

QStatusBar {
    background: #171d22;
    color: #9aa8b2;
}

QFrame#BrandPanel {
    background: #f7f8f7;
    border: 1px solid #d6dee2;
    border-radius: 0;
}

QLabel#BrandMark {
    background: transparent;
}

QLabel#BrandLogo {
    color: #0b0f12;
    font-size: 26px;
    font-weight: 760;
}

QLabel#Byline {
    color: #5b6770;
    font-size: 12px;
    font-weight: 560;
    padding-top: 8px;
}

QLabel#LocalNotice {
    background: #e6f6fa;
    color: #0b4b5d;
    border: 1px solid #b6dce5;
    border-radius: 0;
    padding: 7px 11px;
    font-size: 12px;
    font-weight: 640;
}

QLabel#VersionPill {
    background: #202a31;
    color: #d9e8ee;
    border: 1px solid #3f535e;
    border-radius: 0;
    padding: 6px 10px;
    font-family: "Menlo", "Monaco", monospace;
    font-size: 12px;
}

QFrame#CommandPanel {
    background: #202830;
    border: 1px solid #34414b;
    border-radius: 0;
}

QLabel#SectionTitle {
    color: #f4f8fa;
    font-size: 14px;
    font-weight: 700;
}

QLabel#ReportNotice {
    background: #172d36;
    color: #dff7fc;
    border: 1px solid #315c68;
    border-radius: 0;
    padding: 10px 12px;
    line-height: 1.35;
}

QLabel#DocumentNotice {
    background: #eef5f7;
    color: #14212a;
    border: 1px solid #bfd4dd;
    border-radius: 0;
    padding: 10px 12px;
    line-height: 1.35;
}

QFrame#Panel {
    background: #222c34;
    border: 1px solid #3d4b56;
    border-radius: 0;
}

QTextEdit {
    background: #f7f8f7;
    color: #10161a;
    border: 1px solid #11171b;
    border-radius: 0;
    padding: 11px;
    selection-background-color: #9edbed;
    selection-color: #061116;
    font-size: 13px;
    line-height: 1.45;
}

QTextEdit:focus {
    border: 1px solid #0089b8;
}

QPushButton {
    min-height: 34px;
    border: 1px solid #586875;
    border-radius: 0;
    background: #27313a;
    color: #edf3f6;
    padding: 0 13px;
    font-weight: 620;
}

QPushButton:hover {
    background: #303c45;
    border-color: #70828f;
}

QPushButton:pressed {
    background: #1c242b;
}

QPushButton:disabled {
    color: #71808a;
    background: #20282f;
    border-color: #34414b;
}

QPushButton#PrimaryButton {
    min-height: 38px;
    background: #0089b8;
    border-color: #1aa2cf;
    color: #ffffff;
    font-weight: 760;
}

QPushButton#PrimaryButton:hover {
    background: #0798c9;
}

QPushButton#PrimaryButton:pressed {
    background: #00749c;
}

QPushButton#PrimaryButton:disabled {
    background: #254451;
    border-color: #335767;
    color: #8ea7b1;
}

QPushButton#WorkflowButton {
    background: #222c34;
    border-color: #50606c;
    color: #eef5f8;
}

QPushButton#WorkflowButton:hover {
    background: #2c3740;
    border-color: #6d7f8b;
}

QPushButton#SecondaryButton {
    color: #c1cbd2;
    background: #202830;
    border-color: #3f4d57;
}

QPushButton#SecondaryButton:hover {
    background: #2a343d;
    color: #edf3f6;
}

QComboBox#ModeSelect {
    min-height: 34px;
    border: 1px solid #50606c;
    border-radius: 0;
    background: #1d252c;
    color: #edf3f6;
    padding: 0 10px;
    min-width: 244px;
}

QComboBox#ModeSelect:focus {
    border-color: #0089b8;
}

QFrame#CommandSeparator {
    background: #41515d;
    border: 0;
    margin-left: 12px;
    margin-right: 12px;
}

QTableWidget {
    background: #f7f8f7;
    color: #10161a;
    alternate-background-color: #eef3f5;
    border: 1px solid #11171b;
    border-radius: 0;
    gridline-color: #d8e1e5;
    selection-background-color: #b9e6f3;
    selection-color: #061116;
}

QHeaderView::section {
    background: #e4ecef;
    color: #18242b;
    border: 0;
    border-bottom: 1px solid #bdcbd2;
    padding: 8px;
    font-weight: 700;
}

QTableWidget::item {
    padding: 6px;
    border: 0;
}

QSplitter::handle {
    background: #171d22;
}
"""
