from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel

from release_info import FOOTER_UPDATE_TEXT


class InformationPanel(QFrame):
    """Persistent attribution panel shown below the application workspace."""

    def __init__(self):
        super().__init__()
        self.setObjectName("informationPanel")
        self.setFixedHeight(38)

        developer = QLabel("Developer: Tapas Kumar Pahar")
        developer.setObjectName("informationLabel")
        design = QLabel("UI Design: Pooja Pandey")
        design.setObjectName("informationLabel")
        divider = QLabel("|")
        divider.setObjectName("informationDivider")
        brand = QLabel(FOOTER_UPDATE_TEXT)
        brand.setObjectName("informationBrand")
        brand.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        brand.setToolTip("Open Help → Release Notes to review everything included in this development update.")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 6, 16, 6)
        layout.setSpacing(10)
        layout.addWidget(developer)
        layout.addWidget(divider)
        layout.addWidget(design)
        layout.addStretch()
        layout.addWidget(brand)
