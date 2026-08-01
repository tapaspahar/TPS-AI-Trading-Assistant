from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout
from PySide6.QtCore import Qt


class DashboardCard(QFrame):

    def __init__(self, title, value):

        super().__init__()

        self.setObjectName("dashboardCard")

        layout = QVBoxLayout(self)

        titleLabel = QLabel(title)
        titleLabel.setObjectName("cardTitle")

        self.value_label = QLabel(value)
        self.value_label.setObjectName("cardValue")

        self.value_label.setAlignment(Qt.AlignCenter)

        layout.addWidget(titleLabel)
        layout.addStretch()
        layout.addWidget(self.value_label)

    def set_value(self, value):
        self.value_label.setText(str(value))
