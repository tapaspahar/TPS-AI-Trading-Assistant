def get_light_theme():
    return """
QWidget { background: #f8fafc; color: #172033; font-family: Segoe UI; font-size: 11pt; }
QFrame#sidebar { background: #e7edf5; border-right: 1px solid #cbd5e1; }
QFrame#header { background: #ffffff; border-bottom: 1px solid #cbd5e1; }
QLabel#title { font-size: 22px; font-weight: bold; color: #102a43; }
QLabel#subtitle, QLabel#cardTitle { color: #52657a; }
QLabel#status { color: #15803d; font-size: 12pt; }
QLabel#clock { color: #0369a1; font-weight: bold; }
QLabel#user { color: #172033; }
QPushButton { background: transparent; border: none; padding: 10px; text-align: left; }
QPushButton:hover { background: #dbeafe; border-radius: 8px; }
QPushButton#menuButton { color: #172033; padding: 12px; border: none; border-radius: 8px; text-align: left; font-size: 11pt; }
QPushButton#menuButton:hover { background: #dbeafe; }
QPushButton#menuButton:pressed { background: #93c5fd; }
QFrame#dashboardCard { background: #ffffff; border: 1px solid #cbd5e1; border-radius: 18px; padding: 15px; }
QFrame#dashboardCard:hover { border: 2px solid #2563eb; }
QLabel#cardValue { font-size: 30px; font-weight: bold; color: #102a43; }
"""
