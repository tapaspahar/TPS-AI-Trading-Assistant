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
        self.value_label.setWordWrap(True)

        layout.addWidget(titleLabel)
        layout.addStretch()
        layout.addWidget(self.value_label)

    def set_value(self, value):
        text = str(value)
        self.value_label.setText(text)
        density = "compact" if len(text) > 20 or "\n" in text else "normal"
        self.value_label.setProperty("density", density)
        self.value_label.style().unpolish(self.value_label)
        self.value_label.style().polish(self.value_label)
