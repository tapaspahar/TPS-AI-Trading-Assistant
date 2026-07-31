import sys
from core.database_manager import Database
from PySide6.QtWidgets import QApplication

from ui.screens.dashboard_screen import DashboardScreen
from ui.themes.dark_theme import get_dark_theme


app = QApplication(sys.argv)
db = Database()
app.setStyleSheet(get_dark_theme())

window = DashboardScreen()
window.resize(1300, 750)
window.setWindowTitle("TPS AI Trading Assistant")
window.show()

sys.exit(app.exec())