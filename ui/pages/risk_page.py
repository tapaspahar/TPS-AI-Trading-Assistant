from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout


class RiskPage(QWidget):

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("🛡 Risk Manager"))