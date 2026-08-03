from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel


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
        brand = QLabel("TPS AI Trading Assistant")
        brand.setObjectName("informationBrand")
        brand.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 6, 16, 6)
        layout.setSpacing(10)
        layout.addWidget(developer)
        layout.addWidget(divider)
        layout.addWidget(design)
        layout.addStretch()
        layout.addWidget(brand)
