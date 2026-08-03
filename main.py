import sys
from core.database_manager import Database
from core.settings_store import SettingsStore
from PySide6.QtWidgets import QApplication

from ui.screens.dashboard_screen import DashboardScreen
from ui.themes.theme_manager import apply_theme


app = QApplication(sys.argv)
db = Database()
apply_theme(app, SettingsStore().load()["theme"])

window = DashboardScreen()
window.resize(1300, 750)
window.setWindowTitle("TPS AI Trading Assistant")
window.show()

sys.exit(app.exec())
