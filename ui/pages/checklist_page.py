from PySide6.QtWidgets import QCheckBox, QLabel, QPushButton, QVBoxLayout, QWidget


class ChecklistPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Pre-Trade Checklist"))
        self.items = []
        for text in ("I know my entry, stop loss and target", "Risk is within my daily limit",
                     "Trend aligns with my trade direction", "Volume supports the setup",
                     "I am calm and not revenge trading"):
            checkbox = QCheckBox(text)
            checkbox.stateChanged.connect(self.update_status)
            self.items.append(checkbox)
            layout.addWidget(checkbox)
        self.status = QLabel()
        layout.addWidget(self.status)
        reset = QPushButton("Reset Checklist")
        reset.clicked.connect(lambda: [item.setChecked(False) for item in self.items])
        layout.addWidget(reset)
        layout.addStretch()
        self.update_status()

    def update_status(self):
        done = sum(item.isChecked() for item in self.items)
        self.status.setText(f"{done}/{len(self.items)} checks complete — {'Ready to review entry' if done == len(self.items) else 'Complete every check before entering'}")
