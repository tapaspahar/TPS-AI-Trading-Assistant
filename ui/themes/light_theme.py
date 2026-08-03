def get_light_theme():
    """Bright alternative that preserves the same trading information hierarchy."""
    return """
QWidget { background: #f4f7fb; color: #13233a; font-family: "Segoe UI"; font-size: 9.5pt; }
QFrame#header { background: #ffffff; border-bottom: 1px solid #d7e1ef; }
QFrame#sidebar { background: #edf3fa; border-right: 1px solid #d7e1ef; }
QLabel#title { color: #102a43; font-size: 23px; font-weight: 800; }
QLabel#subtitle { color: #58708c; font-size: 9.5pt; }
QLabel#appBadge { background: #2563eb; color: white; border: 1px solid #60a5fa; border-radius: 12px; font-size: 13pt; font-weight: 800; qproperty-alignment: AlignCenter; }
QLabel#status { color: #087443; background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 8px; padding: 7px 11px; min-width: 245px; }
QLabel#clock { color: #075985; font-weight: 700; }
QLabel#user { color: #5b21b6; font-weight: 600; }
QPushButton { background: #ffffff; color: #173456; border: 1px solid #c9d8eb; border-radius: 8px; padding: 9px 14px; min-height: 18px; }
QPushButton:hover { background: #e7f0ff; border-color: #4f8cff; }
QPushButton:pressed { background: #2563eb; color: white; }
QPushButton:disabled { background: #eef2f7; color: #94a3b8; }
QPushButton#menuButton { background: transparent; color: #46617f; border: 1px solid transparent; border-radius: 9px; padding: 9px 12px; text-align: left; font-size: 9.5pt; font-weight: 600; }
QPushButton#menuButton:hover { background: #e0ecff; color: #173456; border-color: #c4d9f7; }
QPushButton#menuButton:checked { background: #2563eb; color: white; border-color: #2563eb; }
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit, QTableWidget { background: #ffffff; color: #13233a; border: 1px solid #c9d8eb; border-radius: 7px; padding: 3px 9px; selection-background-color: #2563eb; selection-color: white; }
QLineEdit, QComboBox, QSpinBox { min-height: 24px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus, QTextEdit:focus { border: 1px solid #377cf6; background: #fbfdff; }
QComboBox::drop-down { border: none; width: 26px; }
QSpinBox::up-button, QSpinBox::down-button { width: 20px; }
QComboBox QAbstractItemView { background: white; color: #13233a; border: 1px solid #c9d8eb; selection-background-color: #dbeafe; }
QGroupBox { border: 1px solid #d1ddeb; border-radius: 10px; margin-top: 12px; padding: 15px 11px 10px 11px; color: #294b70; font-weight: 700; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
QHeaderView::section { background: #eaf1fa; color: #33516f; border: none; border-bottom: 1px solid #cedbea; padding: 8px; font-weight: 700; }
QTableWidget { gridline-color: #dce5ef; alternate-background-color: #f8fbff; }
QScrollBar:vertical { background: #eef3f9; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #9cb7d6; min-height: 25px; border-radius: 5px; }
QScrollBar::handle:vertical:hover { background: #608fc8; }
QFrame#dashboardCard { background: #ffffff; border: 1px solid #d1ddeb; border-radius: 11px; padding: 7px; }
QFrame#dashboardCard:hover { background: #fbfdff; border: 1px solid #4f8cff; }
QLabel#cardTitle { color: #6380a0; font-size: 8.5pt; font-weight: 600; }
QLabel#cardValue { color: #102f55; font-size: 22px; font-weight: 800; }
QLabel#cardValue[density="compact"] { color: #173f70; font-size: 13px; font-weight: 700; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #91a8c2; border-radius: 4px; background: white; }
QCheckBox::indicator:checked { background: #2563eb; border-color: #2563eb; }
"""
