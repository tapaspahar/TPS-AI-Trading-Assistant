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
        title = QLabel("Cutie AI Assistant — Talk to TPS"); title.setObjectName("pageTitle"); layout.addWidget(title)
        intro = QLabel(
            "Hindi/English me Cutie ko boliye ki software me kahan jana hai, kya dekhna hai ya PAPER algo ko kaise control karna hai. "
            "Normal software commands turant samjhe jayenge. Real-money action me market, data, risk aur broker safety checks hamesha apply honge."
        ); intro.setWordWrap(True); layout.addWidget(intro)
        box = QGroupBox("Ask Cutie")
        box_layout = QVBoxLayout(box)
        self.prompt = QTextEdit(); self.prompt.setPlaceholderText(
            "Example: jump to expiry after 3 pm page"
        ); self.prompt.setMinimumHeight(110); box_layout.addWidget(self.prompt)
        preview = QPushButton("Ask Cutie"); preview.clicked.connect(self.preview); box_layout.addWidget(preview)
        self.preview_text = QLabel("No command previewed."); self.preview_text.setWordWrap(True); box_layout.addWidget(self.preview_text)
        self.apply_button = QPushButton("Do This"); self.apply_button.setEnabled(False); self.apply_button.clicked.connect(self.apply)
        box_layout.addWidget(self.apply_button); layout.addWidget(box)
        examples = QLabel(
            "Supported examples:\n"
            "• jump to expiry after 3 pm page\n"
            "• open dashboard / show settings / go to strategy trades\n"
            "• NIFTY paper algo start target 1000 max loss 500 max 3 trades 1 lot\n"
            "• algo status\n• emergency stop / kill switch\n\n"
            "General software navigation ko confirmation ki zarurat nahi; Do This press karke action apply hota hai. "
            "REAL prompt abhi direct auto-execute nahi hota: broker fill + protective-exit reconciliation certification pending hai. "
            "REAL request review ke liye block/report hogi; profit guaranteed nahi hai."
        ); examples.setWordWrap(True); layout.addWidget(examples); layout.addStretch()
        self.parsed = None

    def preview(self):
        try:
            self.parsed = parse_cutie_command(self.prompt.toPlainText())
        except ValueError as error:
            self.parsed = None; self.apply_button.setEnabled(False); self.preview_text.setText(f"NOT READY — {error}"); return
        suffix = "" if self.parsed.get("intent") == "NAVIGATE" else "\nTrading safeguards remain mandatory."
        self.preview_text.setText(f"CUTIE SAMJHI — {self.parsed['summary']}{suffix}")
        if self.parsed.get("intent") == "NAVIGATE":
            self.apply_button.setEnabled(False)
            self.command_ready.emit(dict(self.parsed))
        else:
            self.apply_button.setEnabled(True)

    def apply(self):
        if not self.parsed:
            return
        if self.parsed.get("mode") == "REAL":
            QMessageBox.warning(
                self, "Limited REAL pilot review required",
                "Prompt valid hai. REAL command direct auto-submit nahi hogi. Cutie Broker Execution page kholegi jahan Limited Pilot, exact contract, target, stop, quantity aur session activation review karna mandatory hai.",
            )
            self.command_ready.emit({"intent": "REAL_PILOT_REVIEW", "summary": self.parsed["summary"]})
            self.preview_text.setText("REAL PILOT REVIEW — Broker Execution khola gaya; koi order abhi submit nahi hua.")
            return
        self.command_ready.emit(dict(self.parsed))
        self.preview_text.setText(f"APPLIED — {self.parsed['summary']}")
