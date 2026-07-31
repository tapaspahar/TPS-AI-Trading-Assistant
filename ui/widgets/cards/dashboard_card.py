from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout
from PySide6.QtCore import Qt


class DashboardCard(QFrame):

    def __init__(self, title, value):

        super().__init__()

        self.setObjectName("dashboardCard")

        layout = QVBoxLayout(self)

        titleLabel = QLabel(title)
        titleLabel.setObjectName("cardTitle")

        valueLabel = QLabel(value)
        valueLabel.setObjectName("cardValue")

        valueLabel.setAlignment(Qt.AlignCenter)

        layout.addWidget(titleLabel)
        layout.addStretch()
        layout.addWidget(valueLabel)