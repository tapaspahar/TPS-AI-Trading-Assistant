"""Shared glassmorphism stylesheet factory for every TPS colour theme."""


def build_glass_theme(p):
    return f"""
QWidget {{
    background: transparent;
    color: {p['text']};
    font-family: "Segoe UI Variable", "Segoe UI";
    font-size: 9.5pt;
}}
QWidget#dashboardScreen {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {p['backdrop_a']}, stop:0.48 {p['backdrop_b']}, stop:1 {p['backdrop_c']});
}}
QStackedWidget#contentStack {{
    background: {p['content_glass']};
    border: 1px solid {p['border_soft']};
    border-radius: 18px;
}}
QScrollArea, QScrollArea > QWidget > QWidget, QAbstractScrollArea::viewport {{ background: transparent; border: none; }}
QToolTip {{ background: {p['popup']}; color: {p['text_strong']}; border: 1px solid {p['border']}; border-radius: 7px; padding: 7px; }}
QFrame#header {{
    background: {p['glass_strong']};
    border: 1px solid {p['border_soft']};
    border-radius: 18px;
}}
QFrame#sidebar {{
    background: {p['glass']};
    border: 1px solid {p['border_soft']};
    border-radius: 18px;
}}
QLabel#title {{ color: {p['text_strong']}; font-size: 23px; font-weight: 800; letter-spacing: .4px; }}
QLabel#pageTitle {{ color: {p['text_strong']}; font-size: 15px; font-weight: 750; }}
QLabel#subtitle {{ color: {p['text_muted']}; font-size: 9.5pt; }}
QFrame#informationPanel {{ background: {p['glass']}; border: 1px solid {p['border_soft']}; border-radius: 13px; }}
QLabel#informationLabel {{ color: {p['text']}; font-size: 9pt; font-weight: 600; }}
QLabel#informationDivider {{ color: {p['accent_soft']}; }}
QLabel#informationBrand {{ color: {p['text_muted']}; font-size: 8.5pt; }}
QLabel#appBadge {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {p['accent']}, stop:1 {p['accent_deep']});
    color: white; border: 1px solid {p['accent_bright']}; border-radius: 14px;
    font-size: 13pt; font-weight: 800; qproperty-alignment: AlignCenter;
}}
QLabel#status {{
    color: {p['success']}; background: {p['success_glass']}; border: 1px solid {p['success_border']};
    border-radius: 11px; padding: 7px 11px; min-width: 245px;
}}
QLabel#clock {{ color: {p['clock']}; font-weight: 700; }}
QLabel#user {{ color: {p['user']}; font-weight: 600; }}
QPushButton#headerSettingsButton {{
    min-width: 34px; max-width: 34px; min-height: 34px; max-height: 34px;
    padding: 0; border-radius: 10px; font-size: 16px; font-weight: 700;
}}
QPushButton {{
    background: {p['control']}; color: {p['text']}; border: 1px solid {p['border']};
    border-radius: 11px; padding: 9px 14px; min-height: 18px; font-weight: 600;
}}
QPushButton:hover {{ background: {p['control_hover']}; border-color: {p['accent_bright']}; color: {p['text_strong']}; }}
QPushButton:pressed {{ background: {p['accent_deep']}; color: white; }}
QPushButton:disabled {{ background: {p['disabled']}; color: {p['disabled_text']}; border-color: {p['border_soft']}; }}
QPushButton#menuButton {{
    background: transparent; color: {p['text_muted']}; border: 1px solid transparent;
    border-radius: 12px; padding: 11px 13px; text-align: left; font-size: 9.5pt; font-weight: 650;
}}
QPushButton#menuButton:hover {{ background: {p['control']}; color: {p['text_strong']}; border-color: {p['border_soft']}; }}
QPushButton#menuButton:checked {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {p['accent_deep']}, stop:1 {p['accent']});
    color: white; border-color: {p['accent_bright']};
}}
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit, QTableWidget {{
    background: {p['input']}; color: {p['text_strong']}; border: 1px solid {p['border']};
    border-radius: 10px; padding: 4px 9px; selection-background-color: {p['accent']}; selection-color: white;
}}
QLineEdit, QComboBox, QSpinBox {{ min-height: 25px; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border: 1px solid {p['accent_bright']}; background: {p['input_focus']};
}}
QComboBox::drop-down {{ border: none; width: 28px; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 21px; border: none; }}
QComboBox QAbstractItemView {{ background: {p['popup']}; color: {p['text_strong']}; border: 1px solid {p['border']}; selection-background-color: {p['accent']}; }}
QTabWidget::pane {{
    background: transparent; border: 1px solid {p['border_soft']}; border-radius: 10px; top: -1px;
}}
QTabBar::tab {{
    background: {p['control']}; color: {p['text']}; border: 1px solid {p['border_soft']};
    border-bottom: none; padding: 9px 16px; margin-right: 4px; min-width: 92px;
    border-top-left-radius: 9px; border-top-right-radius: 9px; font-weight: 650;
}}
QTabBar::tab:hover {{ background: {p['control_hover']}; color: {p['text_strong']}; border-color: {p['accent_bright']}; }}
QTabBar::tab:selected {{ background: {p['accent_deep']}; color: white; border-color: {p['accent_bright']}; font-weight: 800; }}
QTabBar::tab:disabled {{ background: {p['disabled']}; color: {p['disabled_text']}; }}
QGroupBox {{
    background: {p['glass']}; border: 1px solid {p['border_soft']}; border-radius: 16px;
    margin-top: 13px; padding: 17px 12px 11px 12px; color: {p['text']}; font-weight: 700;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 14px; padding: 1px 7px; color: {p['text_strong']}; }}
QHeaderView::section {{ background: {p['table_header']}; color: {p['text']}; border: none; border-bottom: 1px solid {p['border']}; padding: 9px; font-weight: 700; }}
QTableWidget {{ gridline-color: {p['border_soft']}; alternate-background-color: {p['table_alt']}; }}
QTableWidget::item {{ padding: 5px; }}
QTableWidget::item:selected {{ background: {p['accent']}; color: white; }}
QScrollBar:vertical {{ background: transparent; width: 16px; margin: 20px 3px 20px 3px; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 3px; }}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{ background: {p['scroll']}; min-height: 26px; min-width: 26px; border-radius: 4px; }}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{ background: {p['accent_soft']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QFrame#dashboardCard {{ background: {p['glass']}; border: 1px solid {p['border_soft']}; border-radius: 16px; padding: 8px; }}
QFrame#dashboardCard:hover {{ background: {p['glass_strong']}; border: 1px solid {p['accent_bright']}; }}
QLabel#cardTitle {{ color: {p['text_muted']}; font-size: 8.5pt; font-weight: 600; }}
QLabel#cardValue {{ color: {p['text_strong']}; font-size: 22px; font-weight: 800; }}
QLabel#cardValue[density="compact"] {{ color: {p['text']}; font-size: 13px; font-weight: 700; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 17px; height: 17px; border: 1px solid {p['border']}; border-radius: 5px; background: {p['input']}; }}
QCheckBox::indicator:hover {{ border-color: {p['accent_bright']}; }}
QCheckBox::indicator:checked {{ background: {p['accent']}; border-color: {p['accent_bright']}; }}
"""


DARK_GLASS = {
    "backdrop_a": "#07111f", "backdrop_b": "#0b1730", "backdrop_c": "#111b36",
    "content_glass": "rgba(12, 24, 46, 205)", "glass": "rgba(24, 42, 70, 168)", "glass_strong": "rgba(29, 50, 84, 210)",
    "control": "rgba(47, 70, 108, 165)", "control_hover": "rgba(64, 96, 151, 205)",
    "input": "rgba(8, 19, 38, 185)", "input_focus": "rgba(18, 36, 68, 225)", "popup": "#142542",
    "table_header": "rgba(40, 64, 101, 220)", "table_alt": "rgba(10, 23, 44, 145)",
    "border": "rgba(126, 170, 231, 105)", "border_soft": "rgba(126, 170, 231, 55)",
    "text": "#e4edfb", "text_strong": "#ffffff", "text_muted": "#9eb4d2",
    "accent": "#3b82f6", "accent_deep": "#1d4ed8", "accent_bright": "#7db4ff", "accent_soft": "#5e8fca",
    "success": "#65f2b2", "success_glass": "rgba(13, 88, 68, 105)", "success_border": "rgba(82, 225, 169, 120)",
    "clock": "#7dd3fc", "user": "#c4b5fd", "disabled": "rgba(31, 45, 70, 125)", "disabled_text": "#687a94", "scroll": "rgba(104, 139, 188, 150)",
}

EMERALD_GLASS = {**DARK_GLASS,
    "backdrop_a": "#041613", "backdrop_b": "#082720", "backdrop_c": "#0b3028",
    "content_glass": "rgba(7, 35, 30, 210)", "glass": "rgba(18, 67, 57, 165)", "glass_strong": "rgba(21, 82, 68, 205)",
    "control": "rgba(29, 92, 77, 165)", "control_hover": "rgba(32, 121, 96, 205)", "input": "rgba(4, 30, 26, 190)", "input_focus": "rgba(8, 58, 48, 225)", "popup": "#0c352d",
    "border": "rgba(110, 231, 183, 105)", "border_soft": "rgba(110, 231, 183, 55)", "accent": "#10b981", "accent_deep": "#047857", "accent_bright": "#6ee7b7", "accent_soft": "#4baa8a",
}

LIGHT_GLASS = {**DARK_GLASS,
    "backdrop_a": "#dce9fb", "backdrop_b": "#edf4ff", "backdrop_c": "#e4e7ff",
    "content_glass": "rgba(255, 255, 255, 190)", "glass": "rgba(255, 255, 255, 155)", "glass_strong": "rgba(255, 255, 255, 220)",
    "control": "rgba(255, 255, 255, 175)", "control_hover": "rgba(226, 238, 255, 225)", "input": "rgba(255, 255, 255, 205)", "input_focus": "rgba(255, 255, 255, 245)", "popup": "#f8fbff",
    "table_header": "rgba(226, 236, 250, 230)", "table_alt": "rgba(236, 243, 252, 155)",
    "border": "rgba(69, 105, 153, 100)", "border_soft": "rgba(69, 105, 153, 52)",
    "text": "#183451", "text_strong": "#0b2038", "text_muted": "#58718f",
    "success": "#087443", "success_glass": "rgba(209, 250, 229, 180)", "success_border": "rgba(16, 185, 129, 115)",
    "clock": "#075985", "user": "#5b21b6", "disabled": "rgba(225, 231, 240, 150)", "disabled_text": "#8493a7", "scroll": "rgba(91, 126, 170, 125)",
}

SUNSET_GLASS = {**LIGHT_GLASS,
    "backdrop_a": "#ffe7d1", "backdrop_b": "#fff4ea", "backdrop_c": "#fce7f3",
    "content_glass": "rgba(255, 250, 245, 195)", "glass": "rgba(255, 250, 245, 165)", "glass_strong": "rgba(255, 252, 248, 225)",
    "control_hover": "rgba(255, 232, 207, 225)", "table_header": "rgba(255, 232, 207, 230)", "table_alt": "rgba(255, 244, 234, 165)",
    "border": "rgba(183, 100, 45, 95)", "border_soft": "rgba(183, 100, 45, 48)",
    "accent": "#f97316", "accent_deep": "#c2410c", "accent_bright": "#fb923c", "accent_soft": "#d68a55",
}
