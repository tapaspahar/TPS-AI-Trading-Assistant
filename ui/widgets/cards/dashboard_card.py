from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QVBoxLayout,
)

from PySide6.QtCore import Qt


class DashboardCard(QFrame):

    def __init__(self, title, value):

        super().__init__()

        self.setFixedSize(260,130)

        self.setStyleSheet("""

        QFrame{

            background:#182338;

            border:1px solid #2B3A55;

            border-radius:15px;

        }

        """)

        layout=QVBoxLayout(self)

        layout.setContentsMargins(20,15,20,15)

        layout.setSpacing(10)

        titleLabel=QLabel(title)

        titleLabel.setStyleSheet("""

            color:#8FA2C5;

            font-size:13px;

        """)

        valueLabel=QLabel(value)

        valueLabel.setAlignment(Qt.AlignLeft)

        valueLabel.setStyleSheet("""

            color:white;

            font-size:28px;

            font-weight:bold;

        """)

        layout.addWidget(titleLabel)

        layout.addWidget(valueLabel)

        layout.addStretch()