from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class DashboardCard(QFrame):

    def __init__(self, title, value):
        super().__init__()

        self.setMinimumSize(220, 120)

        self.setStyleSheet("""
            QFrame{
                background:#1E293B;
                border-radius:15px;
                border:1px solid #334155;
            }

            QLabel{
                color:white;
            }
        """)

        layout = QVBoxLayout(self)

        title_label = QLabel(title)
        title_label.setStyleSheet("""
            font-size:14px;
            color:#94A3B8;
        """)

        value_label = QLabel(value)
        value_label.setStyleSheet("""
            font-size:28px;
            font-weight:bold;
        """)

        layout.addWidget(title_label)
        layout.addWidget(value_label)
        layout.addStretch()