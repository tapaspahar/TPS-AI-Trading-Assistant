import sys
import multiprocessing
from core.database_manager import Database
from core.settings_store import SettingsStore
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QCursor

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
    window.setWindowTitle(f"{APP_NAME} — {DISPLAY_VERSION}")
    # Anchor startup to the monitor currently in use. A fixed-size normal
    # window can otherwise be placed partly outside the desktop after an
    # installer upgrade, DPI change or monitor switch, clipping the native
    # title bar, TPS header or footer.
    screen = app.screenAt(QCursor.pos()) or app.primaryScreen()
    if screen is not None:
        window.setGeometry(screen.availableGeometry())
    else:
        window.resize(1300, 750)
    window.showMaximized()

    return app.exec()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
