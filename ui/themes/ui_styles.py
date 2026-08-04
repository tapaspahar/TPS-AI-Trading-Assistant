"""Visual-language overlays applied on top of the selected colour palette."""

UI_STYLE_NAMES = {
    "skeuomorphism": "Skeuomorphism",
    "neomorphism": "Neomorphism",
    "glassmorphism": "Glassmorphism",
    "claymorphism": "Claymorphism",
    "minimalism": "Minimalism",
    "maximalism": "Maximalism",
    "brutalism": "Brutalism",
    "liquid_glass": "Liquid Glass",
    "bento_grid": "Bento Grid",
    "spatial_ui": "Spatial UI",
}


STYLE_OVERLAYS = {
    "glassmorphism": """
QFrame#header, QFrame#sidebar, QFrame#dashboardCard, QGroupBox { border-radius: 16px; }
""",
    "skeuomorphism": """
QWidget#dashboardScreen { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #29384f,stop:1 #0a101b); }
QFrame#header, QFrame#sidebar, QGroupBox, QFrame#dashboardCard, QStackedWidget#contentStack {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(72,91,119,235),stop:0.48 rgba(35,51,75,230),stop:1 rgba(17,27,43,240));
    border: 2px outset rgba(190,210,238,150); border-radius: 8px;
}
QPushButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(108,132,166,240),stop:0.5 rgba(61,83,116,240),stop:1 rgba(35,52,78,245)); border: 2px outset rgba(198,217,241,165); border-radius: 7px; }
QPushButton:pressed { border-style: inset; padding-top: 11px; }
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit, QTableWidget { border: 2px inset rgba(184,204,230,135); border-radius: 6px; }
""",
    "neomorphism": """
QWidget#dashboardScreen { background: #17243a; }
QFrame#header, QFrame#sidebar, QGroupBox, QFrame#dashboardCard, QStackedWidget#contentStack { background: #1b2a43; border: 1px solid #253a5a; border-radius: 18px; }
QPushButton, QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit, QTableWidget { background: #1b2a43; border: 1px solid #2d4364; border-radius: 14px; }
QPushButton:hover { background: #20324f; }
QPushButton#menuButton:checked { background: #243c61; border: 1px solid #3e5f8e; }
""",
    "claymorphism": """
QWidget#dashboardScreen { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #20183c,stop:1 #102a46); }
QFrame#header, QFrame#sidebar, QGroupBox, QFrame#dashboardCard, QStackedWidget#contentStack { background: rgba(52,61,105,235); border: 3px solid rgba(135,151,231,115); border-radius: 24px; }
QPushButton { background: #5267d7; border: 3px solid #7185ef; border-radius: 18px; padding: 10px 16px; }
QPushButton:hover { background: #6679e6; border-color: #9aa8ff; }
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit, QTableWidget { background: rgba(28,37,72,230); border: 3px solid rgba(115,133,211,105); border-radius: 16px; }
QLabel#appBadge { border-radius: 20px; }
""",
    "minimalism": """
QWidget#dashboardScreen { background: #0d1117; }
QFrame#header, QFrame#sidebar, QStackedWidget#contentStack, QFrame#informationPanel { background: #0d1117; border: none; border-radius: 0; }
QFrame#dashboardCard, QGroupBox { background: transparent; border: 1px solid #30363d; border-radius: 6px; }
QPushButton { background: transparent; border: 1px solid #30363d; border-radius: 5px; font-weight: 500; }
QPushButton:hover { background: #161b22; }
QPushButton#menuButton:checked { background: transparent; color: #58a6ff; border: none; border-left: 3px solid #58a6ff; border-radius: 0; }
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit, QTableWidget { background: #0d1117; border: 1px solid #30363d; border-radius: 4px; }
""",
    "maximalism": """
QWidget#dashboardScreen { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #230b49,stop:0.35 #102a6d,stop:0.7 #6b174d,stop:1 #c2410c); }
QFrame#header, QFrame#sidebar, QGroupBox, QFrame#dashboardCard, QStackedWidget#contentStack { background: rgba(24,14,59,215); border: 2px solid #f59e0b; border-radius: 18px; }
QPushButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #7c3aed,stop:1 #db2777); border: 2px solid #fbbf24; border-radius: 13px; color: white; font-weight: 800; }
QPushButton:hover { background: #ec4899; border-color: #67e8f9; }
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit, QTableWidget { background: rgba(17,11,48,225); border: 2px solid #a78bfa; border-radius: 11px; }
QLabel#title, QLabel#cardValue { color: #fef08a; }
""",
    "brutalism": """
QWidget#dashboardScreen { background: #f4e900; color: #050505; }
QFrame#header, QFrame#sidebar, QGroupBox, QFrame#dashboardCard, QStackedWidget#contentStack, QFrame#informationPanel { background: #f8f8ef; color: #050505; border: 4px solid #050505; border-radius: 0; }
QLabel, QLabel#title, QLabel#subtitle, QLabel#cardTitle, QLabel#cardValue, QLabel#informationLabel, QLabel#informationBrand { color: #050505; }
QPushButton { background: #ff4d00; color: #050505; border: 4px solid #050505; border-radius: 0; font-weight: 900; }
QPushButton:hover { background: #00d9ff; color: #050505; border-color: #050505; }
QPushButton#menuButton { color: #050505; border-radius: 0; }
QPushButton#menuButton:checked { background: #00d9ff; color: #050505; border: 4px solid #050505; border-radius: 0; }
QLabel#status { background: #ffffff; color: #050505; border: 3px solid #050505; border-radius: 0; }
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit, QTableWidget { background: white; color: #050505; border: 4px solid #050505; border-radius: 0; }
QHeaderView::section { background: #00d9ff; color: #050505; border: 2px solid #050505; }
""",
    "liquid_glass": """
QWidget#dashboardScreen { background: qradialgradient(cx:.2,cy:.1,radius:1.1,fx:.2,fy:.1,stop:0 #22577a,stop:.35 #16324f,stop:1 #090f24); }
QFrame#header, QFrame#sidebar, QGroupBox, QFrame#dashboardCard, QStackedWidget#contentStack { background: rgba(181,220,255,42); border: 1px solid rgba(224,244,255,155); border-radius: 26px; }
QPushButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(224,244,255,80),stop:.5 rgba(111,174,236,75),stop:1 rgba(201,145,255,70)); border: 1px solid rgba(235,249,255,175); border-radius: 22px; }
QPushButton:hover { background: rgba(200,232,255,105); }
QPushButton#menuButton:checked { border-radius: 22px; background: rgba(129,190,255,115); }
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit, QTableWidget { background: rgba(218,239,255,40); border: 1px solid rgba(225,245,255,145); border-radius: 20px; }
""",
    "bento_grid": """
QWidget#dashboardScreen { background: #0a0d14; }
QFrame#header, QFrame#sidebar, QStackedWidget#contentStack { background: #101620; border: 1px solid #293342; border-radius: 14px; }
QFrame#dashboardCard, QGroupBox { background: #161e2a; border: 1px solid #334155; border-radius: 20px; padding: 12px; }
QFrame#dashboardCard:hover, QGroupBox:hover { border-color: #60a5fa; background: #1a2534; }
QPushButton { background: #1e293b; border: 1px solid #475569; border-radius: 10px; }
QPushButton#menuButton:checked { background: #f8fafc; color: #0f172a; border-color: #f8fafc; }
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit, QTableWidget { background: #0f172a; border: 1px solid #334155; border-radius: 10px; }
""",
    "spatial_ui": """
QWidget#dashboardScreen { background: qradialgradient(cx:.5,cy:.35,radius:.8,fx:.5,fy:.35,stop:0 #1b2f59,stop:.55 #0c1831,stop:1 #030711); }
QFrame#header, QFrame#sidebar, QGroupBox, QFrame#dashboardCard, QStackedWidget#contentStack { background: rgba(15,31,61,205); border: 1px solid rgba(103,176,255,125); border-radius: 21px; }
QFrame#dashboardCard { margin: 4px; padding: 12px; }
QPushButton { background: rgba(24,67,116,205); border: 1px solid rgba(113,196,255,155); border-radius: 15px; padding: 11px 16px; }
QPushButton:hover { background: rgba(43,103,164,225); }
QPushButton#menuButton:checked { background: rgba(42,118,194,210); border-color: #8dd6ff; }
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit, QTableWidget { background: rgba(5,16,36,215); border: 1px solid rgba(102,168,232,110); border-radius: 13px; }
QLabel#status { border-radius: 15px; }
""",
}


def get_ui_style_overlay(style_name):
    return STYLE_OVERLAYS.get(style_name, STYLE_OVERLAYS["glassmorphism"])
