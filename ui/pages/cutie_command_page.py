from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGroupBox, QLabel, QMessageBox, QPushButton, QScrollArea, QTextEdit, QVBoxLayout, QWidget

from engine.cutie_command_engine import parse_cutie_command


class CutieCommandPage(QWidget):
    command_ready = Signal(dict)

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); body = QWidget(); layout = QVBoxLayout(body)
        layout.setContentsMargins(18, 16, 18, 24); layout.setSpacing(12); scroll.setWidget(body); outer.addWidget(scroll)
        title = QLabel("Cutie AI Command Center — Guarded Automation"); title.setObjectName("pageTitle"); layout.addWidget(title)
        intro = QLabel(
            "Hindi/English me ek clear command likhiye. Cutie pehle command ko structured plan me badlegi; unknown ya incomplete prompt execute nahi hoga. "
            "Prompt market-session, data-quality, liquidity, event, expiry, position-size, daily-loss, broker ya kill-switch safeguards ko bypass nahi kar sakta."
        ); intro.setWordWrap(True); layout.addWidget(intro)
        box = QGroupBox("One-command controller")
        box_layout = QVBoxLayout(box)
        self.prompt = QTextEdit(); self.prompt.setPlaceholderText(
            "Example: NIFTY paper algo start target 1000 max loss 500 max 3 trades 1 lot"
        ); self.prompt.setMinimumHeight(110); box_layout.addWidget(self.prompt)
        preview = QPushButton("Understand & Preview Command"); preview.clicked.connect(self.preview); box_layout.addWidget(preview)
        self.preview_text = QLabel("No command previewed."); self.preview_text.setWordWrap(True); box_layout.addWidget(self.preview_text)
        self.apply_button = QPushButton("Apply Guarded Command"); self.apply_button.setEnabled(False); self.apply_button.clicked.connect(self.apply)
        box_layout.addWidget(self.apply_button); layout.addWidget(box)
        examples = QLabel(
            "Supported examples:\n"
            "• NIFTY paper algo start target 1000 max loss 500 max 3 trades 1 lot\n"
            "• algo status\n• emergency stop / kill switch\n\n"
            "REAL prompt abhi direct auto-execute nahi hota: broker fill + protective-exit reconciliation certification pending hai. "
            "REAL request review ke liye block/report hogi; profit guaranteed nahi hai."
        ); examples.setWordWrap(True); layout.addWidget(examples); layout.addStretch()
        self.parsed = None

    def preview(self):
        try:
            self.parsed = parse_cutie_command(self.prompt.toPlainText())
        except ValueError as error:
            self.parsed = None; self.apply_button.setEnabled(False); self.preview_text.setText(f"NOT READY — {error}"); return
        self.preview_text.setText(f"READY TO APPLY — {self.parsed['summary']}\nHard safeguards remain mandatory.")
        self.apply_button.setEnabled(True)

    def apply(self):
        if not self.parsed:
            return
        if self.parsed.get("mode") == "REAL":
            QMessageBox.warning(
                self, "REAL automation blocked",
                "Prompt valid hai, lekin REAL automatic entry/managed-exit reconciliation certified nahi hai. "
                "Cutie is command ko broker ko nahi bhejegi. PAPER validation use karein.",
            )
            self.preview_text.setText("BLOCKED — REAL managed exits and fill reconciliation pending certification.")
            return
        self.command_ready.emit(dict(self.parsed))
        self.preview_text.setText(f"APPLIED — {self.parsed['summary']}")
