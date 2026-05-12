APP_STYLE = """
QMainWindow {
    background: #303844;
}

QWidget {
    color: #eef2f5;
    font-family: "Helvetica Neue", "Arial", sans-serif;
    font-size: 13px;
}

QMenuBar {
    background: #303844;
    color: #eef2f5;
}

QStatusBar {
    background: #303844;
    color: #b8c2cc;
}

QLabel#AppTitle {
    font-family: "Bebas Neue", "Avenir Next Condensed", "Helvetica Neue", "Arial", sans-serif;
    font-size: 32px;
    font-weight: 500;
    color: #f5f7fa;
    letter-spacing: 0px;
}

QLabel#Byline {
    color: #b7c1cc;
    font-size: 12px;
    font-weight: 520;
    padding-top: 7px;
}

QLabel#VersionPill {
    background: #3b4654;
    color: #dce7ef;
    border: 1px solid #596677;
    border-radius: 2px;
    padding: 6px 10px;
    font-family: "Menlo", "Monaco", monospace;
    font-size: 12px;
}

QLabel#SectionTitle {
    color: #f0f4f7;
    font-size: 14px;
    font-weight: 650;
}

QFrame#Panel {
    background: #38414d;
    border: 1px solid #667384;
    border-radius: 2px;
}

QTextEdit {
    background: #f2f4f5;
    color: #151b22;
    border: 1px solid #1e252d;
    border-radius: 2px;
    padding: 10px;
    selection-background-color: #91d8ff;
    selection-color: #081016;
    font-size: 13px;
    line-height: 1.45;
}

QTextEdit:focus {
    border: 1px solid #7f98b4;
}

QPushButton {
    min-height: 34px;
    border: 1px solid #7a8797;
    border-radius: 2px;
    background: #3a4451;
    color: #f2f6f9;
    padding: 0 13px;
    font-weight: 560;
}

QPushButton:hover {
    background: #46515f;
    border-color: #9bacbc;
}

QPushButton:pressed {
    background: #2a333e;
}

QPushButton#PrimaryButton {
    background: #6f89a5;
    border-color: #8ba1b7;
    color: #07111a;
}

QPushButton#PrimaryButton:hover {
    background: #829bb5;
}

QPushButton#WorkflowButton {
    background: #34404d;
    border-color: #718092;
    color: #f2f6f9;
}

QPushButton#WorkflowButton:hover {
    background: #414d5b;
}

QPushButton#SecondaryButton {
    color: #c4cdd6;
    background: #303844;
    border-color: #667384;
}

QPushButton#SecondaryButton:hover {
    background: #3b4654;
}

QFrame#CommandSeparator {
    background: #6a7788;
    border: 0;
    margin-left: 12px;
    margin-right: 12px;
}

QTableWidget {
    background: #f2f4f5;
    color: #151b22;
    alternate-background-color: #e8ecef;
    border: 1px solid #1e252d;
    border-radius: 2px;
    gridline-color: #c7d0d8;
    selection-background-color: #b9e4ff;
    selection-color: #081016;
}

QHeaderView::section {
    background: #dce2e7;
    color: #1d2731;
    border: 0;
    border-bottom: 1px solid #9ba8b5;
    padding: 8px;
    font-weight: 650;
}

QTableWidget::item {
    padding: 6px;
}

QSplitter::handle {
    background: #303844;
}
"""
