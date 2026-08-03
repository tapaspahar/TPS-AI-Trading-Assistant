def get_dark_theme():
    """A calm, high-contrast trading workspace with restrained signal colours."""
    return """
QWidget {
    background: #0b1220;
    color: #e7eefb;
    font-family: "Segoe UI";
    font-size: 9.5pt;
}
QToolTip { background: #17233a; color: #f8fafc; border: 1px solid #334155; padding: 6px; }
QFrame#header {
    background: #101b30;
    border-bottom: 1px solid #243552;
}
QFrame#sidebar {
    background: #101a2d;
    border-right: 1px solid #243552;
}
QLabel#title { color: #f8fafc; font-size: 23px; font-weight: 800; letter-spacing: .2px; }
QLabel#subtitle { color: #8fa3c2; font-size: 9.5pt; }
QLabel#appBadge { background: #2563eb; color: white; border: 1px solid #60a5fa; border-radius: 12px; font-size: 13pt; font-weight: 800; qproperty-alignment: AlignCenter; }
QLabel#status {
    color: #5ee9a3;
    background: #102a2a;
    border: 1px solid #1c5548;
    border-radius: 8px;
    padding: 7px 11px;
    min-width: 245px;
}
QLabel#clock { color: #7dd3fc; font-weight: 700; }
QLabel#user { color: #c4b5fd; font-weight: 600; }
QPushButton {
    background: #1a2942;
    color: #e8f0ff;
    border: 1px solid #2b3d5b;
    border-radius: 8px;
    padding: 9px 14px;
    min-height: 18px;
}
QPushButton:hover { background: #243b64; border-color: #4f8cff; }
QPushButton:pressed { background: #1d4ed8; }
QPushButton:disabled { background: #172238; color: #64748b; border-color: #23324b; }
QPushButton#menuButton {
    background: transparent;
    color: #bdcbe1;
    border: 1px solid transparent;
    border-radius: 9px;
    padding: 11px 13px;
    text-align: left;
    font-size: 9.5pt;
    font-weight: 600;
}
QPushButton#menuButton:hover { background: #172841; color: #f8fbff; border-color: #294363; }
QPushButton#menuButton:checked { background: #1d4ed8; color: white; border-color: #5590ff; }
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit, QTableWidget {
    background: #101a2d;
    color: #edf4ff;
    border: 1px solid #30435f;
    border-radius: 7px;
    padding: 3px 9px;
    selection-background-color: #2563eb;
}
QLineEdit, QComboBox, QSpinBox { min-height: 24px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus, QTextEdit:focus {
    border: 1px solid #4f8cff;
    background: #13213a;
}
QComboBox::drop-down { border: none; width: 26px; }
QSpinBox::up-button, QSpinBox::down-button { width: 20px; }
QComboBox QAbstractItemView { background: #17243b; color: #edf4ff; border: 1px solid #3a5276; selection-background-color: #2563eb; }
QGroupBox {
    border: 1px solid #2d405e;
    border-radius: 10px;
    margin-top: 12px;
    padding: 15px 11px 10px 11px;
    color: #cbdaf1;
    font-weight: 700;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
QHeaderView::section { background: #17243b; color: #bcd1ed; border: none; border-bottom: 1px solid #344b6d; padding: 8px; font-weight: 700; }
QTableWidget { gridline-color: #263a57; alternate-background-color: #0e192b; }
QScrollBar:vertical { background: #0e192b; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #3a5276; min-height: 25px; border-radius: 5px; }
QScrollBar::handle:vertical:hover { background: #5685c5; }
QFrame#dashboardCard {
    background: #121f35;
    border: 1px solid #2c4161;
    border-radius: 11px;
    padding: 7px;
}
QFrame#dashboardCard:hover { background: #162640; border: 1px solid #4f8cff; }
QLabel#cardTitle { color: #91a8c7; font-size: 8.5pt; font-weight: 600; }
QLabel#cardValue { color: #f8fbff; font-size: 22px; font-weight: 800; }
QLabel#cardValue[density="compact"] { color: #d9e7ff; font-size: 13px; font-weight: 700; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #49617f; border-radius: 4px; background: #101a2d; }
QCheckBox::indicator:checked { background: #2563eb; border-color: #60a5fa; }
"""
