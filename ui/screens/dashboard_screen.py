from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout
)

from ui.widgets.header import Header
from ui.widgets.navigation.sidebar import Sidebar
from ui.pages.dashboard_page import DashboardPage


class DashboardScreen(QWidget):

    def __init__(self):
        super().__init__()

        mainLayout = QVBoxLayout(self)

        # Header
        mainLayout.addWidget(Header())

        # Body
        bodyLayout = QHBoxLayout()

        # Sidebar
        sidebar = Sidebar()
        bodyLayout.addWidget(sidebar)

        # Dashboard Page
        dashboard = DashboardPage()
        bodyLayout.addWidget(dashboard, 1)

        mainLayout.addLayout(bodyLayout)