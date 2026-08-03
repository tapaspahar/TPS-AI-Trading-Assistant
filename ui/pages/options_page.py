from threading import Thread

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QFormLayout, QGroupBox, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from core.settings_store import SettingsStore
from services.live_session import LiveSession
from services.option_contract_service import OptionContractService, buying_risk


class OptionsPage(QWidget):
    """Read-only option-buying workspace; broker order placement is intentionally absent."""
    contracts_loaded = Signal(object)
    load_error = Signal(str)
    quote_loaded = Signal(object)
    quote_error = Signal(str)

    def __init__(self):
        super().__init__()
        self.contracts = []
        self.service = OptionContractService()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Options Decision Workspace — verify every condition before placing a manual broker order."))

        selection = QGroupBox("1. Choose a contract")
        form = QFormLayout(selection)
        self.underlying = QComboBox(); self.underlying.addItems(("NIFTY", "BANKNIFTY", "SENSEX"))
        self.expiry = QComboBox(); self.expiry.currentIndexChanged.connect(self.populate_strikes)
        self.option_type = QComboBox(); self.option_type.addItems(("CE", "PE")); self.option_type.currentIndexChanged.connect(self.populate_strikes)
        self.strike = QComboBox()
        load = QPushButton("Load Current Expiries")
        load.clicked.connect(self.load_contracts)
        refresh = QPushButton("Refresh Selected Contract")
        refresh.clicked.connect(self.load_quote)
        form.addRow("Underlying", self.underlying)
        form.addRow(load)
        form.addRow("Expiry", self.expiry)
        form.addRow("Type", self.option_type)
        form.addRow("Strike", self.strike)
        form.addRow(refresh)
        layout.addWidget(selection)

        self.details = QLabel("Load current expiries to choose an option contract.")
        layout.addWidget(self.details)
        self.decision = QLabel("Buying only: CE needs bullish underlying confirmation; PE needs bearish underlying confirmation.\nNaked option selling is intentionally not available in this version.")
        layout.addWidget(self.decision)
        layout.addWidget(QLabel("TPS only analyses data. It does not place, modify, or cancel an Angel One order."))
        layout.addStretch()
        self.contracts_loaded.connect(self.show_contracts)
        self.load_error.connect(self.show_error)
        self.quote_loaded.connect(self.show_quote)
        self.quote_error.connect(self.show_error)

    def load_contracts(self):
        self.details.setText("Downloading today's instrument master…")
        Thread(target=self._load_contracts, args=(self.underlying.currentText(),), daemon=True).start()

    def _load_contracts(self, underlying):
        try:
            self.contracts_loaded.emit(self.service.get_contracts(underlying))
        except (RuntimeError, ValueError) as error:
            self.load_error.emit(str(error))

    def show_contracts(self, contracts):
        self.contracts = contracts
        self.expiry.blockSignals(True)
        self.expiry.clear()
        for expiry in sorted({contract["expiry"] for contract in contracts}):
            self.expiry.addItem(expiry.strftime("%d %b %Y"), expiry)
        self.expiry.blockSignals(False)
        self.populate_strikes()
        self.details.setText(f"{len(contracts)} current contracts loaded. Select expiry, CE/PE and strike.")

    def populate_strikes(self):
        if not self.contracts or self.expiry.currentIndex() < 0:
            return
        expiry = self.expiry.currentData()
        option_type = self.option_type.currentText()
        selected = [contract for contract in self.contracts if contract["expiry"] == expiry and contract["option_type"] == option_type]
        self.strike.clear()
        for contract in selected:
            self.strike.addItem(f"{contract['strike']:,.0f}", contract)

    def selected_contract(self):
        contract = self.strike.currentData()
        if not contract:
            raise ValueError("Load expiries and select a valid option contract first.")
        return contract

    def load_quote(self):
        if not LiveSession.connected():
            QMessageBox.warning(self, "Angel One", "Connect live data from Settings first.")
            return
        try:
            contract = self.selected_contract()
        except ValueError as error:
            QMessageBox.warning(self, "Option contract", str(error))
            return
        self.details.setText("Refreshing live option quote…")
        Thread(target=self._load_quote, args=(contract,), daemon=True).start()

    def _load_quote(self, contract):
        try:
            quote = LiveSession.client.get_option_quote(contract["exchange"], contract["token"])
            self.quote_loaded.emit({"contract": contract, "quote": quote})
        except RuntimeError as error:
            self.quote_error.emit(str(error))

    def show_quote(self, result):
        contract, quote = result["contract"], result["quote"]
        premium = float(quote.get("ltp", 0) or 0)
        settings = SettingsStore().load()
        risk = buying_risk(premium, contract["lot_size"], settings["capital"], settings["risk_percent"])
        oi = quote.get("opnInterest", "—")
        volume = quote.get("tradeVolume", "—")
        self.details.setText(
            f"{contract['symbol']}\nPremium: ₹{premium:,.2f} | OI: {oi} | Volume: {volume}\n"
            f"Lot size: {contract['lot_size']} | One-lot premium risk: ₹{risk['per_lot_risk']:,.2f}\n"
            f"Your configured risk cap: ₹{risk['risk_cap']:,.2f} | Whole lots within cap: {risk['lots']}"
        )
        expected = "bullish" if contract["option_type"] == "CE" else "bearish"
        self.decision.setText(
            f"{contract['option_type']} buying checklist: underlying must show {expected} structure, "
            "a confirmed 5m breakout/breakdown, and adequate option volume.\n"
            "If any condition is missing or lots within your risk cap are 0: avoid the entry."
        )

    def show_error(self, message):
        self.details.setText(f"Options data unavailable: {message}")
