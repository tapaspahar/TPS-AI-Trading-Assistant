from PySide6.QtWidgets import QFrame, QLabel, QHBoxLayout, QVBoxLayout


class Header(QFrame):

    def __init__(self):
        super().__init__()

        self.setObjectName("header")
        self.setFixedHeight(80)

        title = QLabel("TPS AI Trading Assistant")
        title.setObjectName("title")

        subtitle = QLabel("Version 1.0")
        subtitle.setObjectName("subtitle")

        text_layout = QVBoxLayout()
        text_layout.addWidget(title)
        text_layout.addWidget(subtitle)

        layout = QHBoxLayout(self)
        layout.addLayout(text_layout)
        layout.addStretch()

        user = QLabel("👤 Tapas")
        layout.addWidget(user)