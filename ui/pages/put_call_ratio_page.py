from datetime import datetime
from threading import Thread

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox, QGridLayout, QGroupBox, QHeaderView, QLabel, QMessageBox,
    QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.database_manager import Database
from engine.option_chain_engine import analyze_option_chain
from engine.pcr_sentiment_engine import analyze_pcr_sentiment
from services.live_session import LiveSession
from services.option_contract_service import OptionContractService, UNDERLYING_QUOTES, contracts_near_spot
from ui.widgets.cards.dashboard_card import DashboardCard
from ui.widgets.excel_export_dialog import open_excel_export


def _compact(value):
    value = float(value or 0)
    if abs(value) >= 10_000_000:
        return f"{value / 10_000_000:.2f} Cr"
    if abs(value) >= 100_000:
        return f"{value / 100_000:.2f} L"
    return f"{value:,.0f}"


class PutCallRatioPage(QWidget):
    result_ready = Signal(dict)
    result_failed = Signal(str)
    sentiment_changed = Signal(dict)

    def __init__(self):
        super().__init__()
        self.service = OptionContractService()
        self.db = Database()
        self.loading = False
        self.last_sentiment = {}
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget(); layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 10, 12, 14)
        layout.setSpacing(9)
        scroll.setWidget(content); outer.addWidget(scroll)
        title = QLabel("Options Market Intelligence")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        note = QLabel(
            "Live Call/Put OI, change in OI, PCR, strike walls, ATM straddle expected range, focused Max Pain, estimated ATM IV/Greeks and execution-quality coverage are combined into transparent derivatives context. No single metric authorizes a trade."
        )
        note.setWordWrap(True); layout.addWidget(note)
        controls = QGridLayout()
        self.symbol = QComboBox(); self.symbol.addItems(("NIFTY", "BANKNIFTY", "SENSEX"))
        self.refresh_button = QPushButton("Refresh Live OI / PCR")
        self.refresh_button.clicked.connect(self.refresh)
        controls.addWidget(QLabel("Underlying"), 0, 0); controls.addWidget(self.symbol, 0, 1)
        controls.addWidget(self.refresh_button, 0, 2)
        excel = QPushButton("Export PCR / OI Excel by Date / Period")
        excel.clicked.connect(lambda: open_excel_export(self, self.db, "pcr_observations"))
        controls.addWidget(excel, 0, 3)
        layout.addLayout(controls)
        grid = QGridLayout(); grid.setHorizontalSpacing(8); grid.setVerticalSpacing(8)
        self.cards = {
            "call_oi": DashboardCard("Total Call OI", "Waiting"),
            "put_oi": DashboardCard("Total Put OI", "Waiting"),
            "change": DashboardCard("Change in OI", "Waiting"),
            "pcr": DashboardCard("OI-PCR / Volume-PCR", "Waiting"),
            "walls": DashboardCard("OI Support / Resistance", "Waiting"),
            "sentiment": DashboardCard("TPS OI Sentiment", "Waiting"),
            "expected": DashboardCard("ATM Expected Move", "Waiting"),
            "max_pain": DashboardCard("Focused Max Pain", "Waiting"),
            "quality": DashboardCard("Chain Data Quality", "Waiting"),
        }
        for index, card in enumerate(self.cards.values()):
            card.set_compact(True); card.setMinimumHeight(92); grid.addWidget(card, index // 3, index % 3)
        layout.addLayout(grid)
        self.explanation = QLabel("Connect broker data and refresh the page.")
        self.explanation.setWordWrap(True); layout.addWidget(self.explanation)
        chain_box = QGroupBox("Focused nearest-expiry strike OI")
        chain_layout = QVBoxLayout(chain_box)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(("Strike", "Call OI", "Call Volume", "Call LTP", "Put OI", "Put Volume", "Put LTP"))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setMinimumHeight(250)
        chain_layout.addWidget(self.table); layout.addWidget(chain_box, 1)
        self.status = QLabel("Options intelligence refreshes every 60 seconds while this page is open.")
        layout.addWidget(self.status)
        self.result_ready.connect(self.show_result)
        self.result_failed.connect(self.show_error)
        self.timer = QTimer(self); self.timer.setInterval(60_000); self.timer.timeout.connect(self.refresh)

    def showEvent(self, event):
        super().showEvent(event)
        self.timer.start()
        QTimer.singleShot(0, self.refresh)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def refresh(self):
        if self.loading:
            return
        if not LiveSession.connected():
            self.status.setText("Broker live data is not connected. Connect it from Settings first.")
            return
        self.loading = True
        symbol = self.symbol.currentText()
        self.status.setText(f"Loading {symbol} nearest-expiry option OI...")
        Thread(target=self._load, args=(symbol,), daemon=True).start()

    def _load(self, symbol):
        database = Database()
        try:
            quote_config = UNDERLYING_QUOTES[symbol]
            spot_quote = LiveSession.client.get_option_quote(quote_config["exchange"], quote_config["token"])
            spot = float(spot_quote.get("ltp", 0) or 0)
            contracts = contracts_near_spot(self.service.get_contracts(symbol), spot, wings=8)
            if not contracts:
                raise RuntimeError(f"No current {symbol} option contracts are available.")
            expiry = min(contract["expiry"] for contract in contracts)
            contracts = [contract for contract in contracts if contract["expiry"] == expiry]
            quotes = LiveSession.client.get_option_chain_quotes(contracts[0]["exchange"], [item["token"] for item in contracts])
            chain = analyze_option_chain(contracts, quotes, spot)
            previous_row = database.get_latest_pcr_observation(symbol, expiry.isoformat())
            previous = dict(previous_row) if previous_row else None
            sentiment = analyze_pcr_sentiment(chain, previous)
            captured_at = datetime.now().astimezone().isoformat(timespec="seconds")
            observation = {
                "captured_at": captured_at, "symbol": symbol, "expiry": expiry.isoformat(),
                **{key: chain.get(key) for key in ("call_oi", "put_oi", "pcr_oi", "call_volume", "put_volume", "pcr_volume")},
                "call_oi_change": sentiment["call_oi_change"], "put_oi_change": sentiment["put_oi_change"],
                "sentiment": sentiment["sentiment"], "confidence": sentiment["confidence"],
            }
            database.save_pcr_observation(observation)
            self.result_ready.emit({
                "symbol": symbol, "spot": spot, "expiry": expiry, "chain": chain,
                "sentiment": sentiment, "captured_at": captured_at,
                "previous_sentiment": previous.get("sentiment") if previous else None,
            })
        except (RuntimeError, ValueError, TypeError, KeyError) as error:
            self.result_failed.emit(str(error))
        finally:
            database.close()

    def show_result(self, result):
        self.loading = False
        chain, sentiment = result["chain"], result["sentiment"]
        self.cards["call_oi"].set_value(f"{_compact(chain['call_oi'])}\nVolume {_compact(chain['call_volume'])}")
        self.cards["put_oi"].set_value(f"{_compact(chain['put_oi'])}\nVolume {_compact(chain['put_volume'])}")
        call_change = sentiment["call_oi_change"]
        put_change = sentiment["put_oi_change"]
        self.cards["change"].set_value(
            "Baseline saved" if call_change is None else f"Call {call_change:+,.0f}\nPut {put_change:+,.0f}"
        )
        oi_pcr = f"{chain['pcr_oi']:.2f}" if chain.get("pcr_oi") is not None else "-"
        volume_pcr = f"{chain['pcr_volume']:.2f}" if chain.get("pcr_volume") is not None else "-"
        self.cards["pcr"].set_value(f"OI {oi_pcr}\nVolume {volume_pcr}")
        self.cards["walls"].set_value(f"Support {chain.get('put_support') or '-'}\nResistance {chain.get('call_resistance') or '-'}")
        self.cards["sentiment"].set_value(f"{sentiment['sentiment']}\nContext confidence {sentiment['confidence']}%")
        expected = chain.get("expected_move")
        self.cards["expected"].set_value(
            f"± {expected:,.2f} ({chain['expected_move_percent']:.2f}%)\n{chain['expected_low']:,.2f} - {chain['expected_high']:,.2f}"
            if expected is not None else "ATM call/put quote unavailable"
        )
        self.cards["max_pain"].set_value(
            f"{chain['focused_max_pain']:,.0f}\nQuoted strike window only"
            if chain.get("focused_max_pain") is not None else "OI unavailable"
        )
        iv_text = f" | ATM IV est. {chain['atm_iv']:.1f}%" if chain.get("atm_iv") is not None else " | ATM IV unavailable"
        self.cards["quality"].set_value(
            f"{chain['data_quality']}/100 {chain['data_quality_label']}\nMedian spread {chain['median_spread_percent']:.2f}%{iv_text}"
            if chain.get("median_spread_percent") is not None else f"{chain['data_quality']}/100 {chain['data_quality_label']}\nSpread depth unavailable{iv_text}"
        )
        self.explanation.setText(
            f"Direction context: {sentiment['direction']}\nEvidence: {'; '.join(sentiment['evidence'])}\n"
            f"Expected move ATM straddle se expiry tak ka market-implied range hai; focused Max Pain sirf loaded strike window ka expiry context hai. "
            f"Dono standalone direction signal nahi hain.\nCaution: {'; '.join(sentiment['warnings'])}"
        )
        by_strike = {}
        for row in chain["quote_rows"]:
            by_strike.setdefault(row["strike"], {})[row["option_type"]] = row
        strikes = sorted(by_strike, key=lambda value: abs(value - result["spot"]))[:12]
        strikes.sort()
        self.table.setRowCount(len(strikes))
        for table_row, strike in enumerate(strikes):
            ce, pe = by_strike[strike].get("CE", {}), by_strike[strike].get("PE", {})
            values = (f"{strike:,.0f}", _compact(ce.get("oi")), _compact(ce.get("volume")), f"{ce.get('ltp', 0):,.2f}",
                      _compact(pe.get("oi")), _compact(pe.get("volume")), f"{pe.get('ltp', 0):,.2f}")
            for column, value in enumerate(values):
                self.table.setItem(table_row, column, QTableWidgetItem(value))
        self.status.setText(
            f"{result['symbol']} spot {result['spot']:,.2f} | Expiry {result['expiry'].strftime('%d %b %Y')} | Updated {datetime.now().strftime('%H:%M:%S')}"
        )
        previous = result.get("previous_sentiment")
        if previous != sentiment["sentiment"] and (
            previous is not None or sentiment["sentiment"] != "BALANCED / RANGE OI"
        ):
            self.sentiment_changed.emit(result)

    def show_error(self, message):
        self.loading = False
        self.status.setText(f"Options intelligence unavailable: {message}")
