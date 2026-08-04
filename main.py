import sys
import multiprocessing
from core.database_manager import Database
from core.settings_store import SettingsStore
from PySide6.QtWidgets import QApplication

from release_info import APP_NAME, DISPLAY_VERSION
from ui.screens.dashboard_screen import DashboardScreen
from ui.themes.theme_manager import apply_theme


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(DISPLAY_VERSION)
    Database()
    visual = SettingsStore().load()
    apply_theme(app, visual["theme"], visual["ui_style"])

    window = DashboardScreen()
    window.resize(1300, 750)
    window.setWindowTitle(f"{APP_NAME} — {DISPLAY_VERSION}")
    window.show()

    return app.exec()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
