from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel

from ui.widgets.sidebar import SideBar
from ui.widgets.header import Header


class DashboardScreen(QWidget):

    def __init__(self):
        super().__init__()

        main_layout = QHBoxLayout(self)

        sidebar = SideBar()

        right_layout = QVBoxLayout()

        header = Header()

        content = QLabel("📈 Dashboard Area")
        content.setStyleSheet("font-size:24px;")

        right_layout.addWidget(header)
        right_layout.addWidget(content)

        main_layout.addWidget(sidebar)
        main_layout.addLayout(right_layout)