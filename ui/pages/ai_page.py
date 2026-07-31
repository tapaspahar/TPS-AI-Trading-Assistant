from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout


class AIPage(QWidget):

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("🧠 AI Analysis"))