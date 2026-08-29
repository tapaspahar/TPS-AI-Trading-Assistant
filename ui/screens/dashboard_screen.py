from PySide6.QtCore import QSize, QTimer
from PySide6.QtWidgets import QHBoxLayout, QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget

from ui.widgets.header import Header
from ui.widgets.information_panel import InformationPanel
from ui.widgets.navigation.sidebar import Sidebar
from ui.pages.dashboard_page import DashboardPage
from ui.pages.live_market_page import LiveMarketPage
from ui.pages.options_page import OptionsPage
from ui.pages.journal_page import JournalPage
from ui.pages.reports_page import ReportsPage
from ui.pages.backtest_page import BacktestPage
from ui.pages.post_market_page import PostMarketPage
from ui.pages.replay_page import ReplayPage
from ui.pages.settings_page import SettingsPage
from ui.pages.equity_page import EquityPage
from ui.pages.auto_attempt_report_page import AutoAttemptReportPage
from ui.pages.about_help_page import AboutPage, HelpPage
from ui.pages.smart_money_page import SmartMoneyPage
from ui.pages.cas_analysis_page import CasAnalysisPage
from ui.pages.stock_options_watch_page import StockOptionsWatchPage
from ui.pages.option_strategies_page import OptionStrategiesPage
from ui.pages.strategy_trades_page import StrategyTradesPage
from ui.pages.post_market_tps_analysis_page import PostMarketTpsAnalysisPage
from ui.pages.pre_candle_page import PreCandlePage
from ui.pages.powerful_engine_page import PowerfulEnginePage
from ui.pages.put_call_ratio_page import PutCallRatioPage
from ui.pages.gap_probability_page import GapProbabilityPage
from ui.pages.auto_opportunity_page import AutoOpportunityPage
from ui.pages.trend_memory_page import TrendMemoryPage
from ui.pages.scalper_page import ScalperPage
from ui.pages.notification_center_page import NotificationCenterPage
from ui.pages.self_development_page import SelfDevelopmentPage
from ui.pages.recovery_center_page import RecoveryCenterPage
from ui.pages.volatility_intelligence_page import VolatilityIntelligencePage
from ui.pages.expiry_observation_page import ExpiryObservationPage
from ui.pages.execution_control_page import ExecutionControlPage
from ui.pages.options_algo_page import OptionsAlgoPage
from ui.pages.cutie_command_page import CutieCommandPage
from ui.widgets.glass_effects import add_glass_shadow
from ui.widgets.accessible_scroll import configure_scroll_area
from ui.widgets.consolidated_workspace import ConsolidatedWorkspace
from services.post_market_tps_analysis import ensure_completed_post_market_reports
from services.self_development_decision import ensure_completed_self_development_reviews
from services.notification_service import NotificationService
from services.live_session import LiveSession
from services.trend_memory_service import ensure_completed_trend_memories, get_live_trend_analogs


class ResponsiveStackedWidget(QStackedWidget):
    """Keep hidden workspace size hints from forcing the shell off-screen."""

    def minimumSizeHint(self):
        # QStackedWidget normally returns the largest minimum hint from every
        # page, including hidden report/help tables. With display scaling this
        # can make the top-level window larger than the monitor work area and
        # push its native title bar above the screen. Individual long pages
        # already own scroll areas, so the shell itself may safely shrink.
        return QSize(0, 0)


class DashboardScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("dashboardScreen")
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 12, 14, 10)
        main_layout.setSpacing(10)
        self.header = Header()
        self.header.settings_requested.connect(lambda: self.show_page(9))
        self.notifier = NotificationService.instance(self)
        self._market_states = {}
        self._trend_memory_alerts = set()
        add_glass_shadow(self.header)
        main_layout.addWidget(self.header)
        body_layout = QHBoxLayout()
        body_layout.setSpacing(10)
        self.sidebar = Sidebar()
        add_glass_shadow(self.sidebar, blur=20, y_offset=3, opacity=75)
        body_layout.addWidget(self.sidebar)
        self.stack = ResponsiveStackedWidget()
        self.stack.setObjectName("contentStack")
        self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        add_glass_shadow(self.stack, blur=25, y_offset=5, opacity=75)
        self.dashboardPage = DashboardPage()
        self.liveMarketPage = LiveMarketPage()
        self.optionsPage = OptionsPage()
        # Routes 3 and 7 remain reserved for backward-compatible Help links;
        # their former manual workspaces are replaced by automatic flows.
        self.retiredChartCaptureSlot = QWidget()
        self.journalPage = JournalPage()
        # Index 6 is intentionally reserved so every established workspace
        # keeps its public route after the retired manual AI form is removed.
        self.retiredAiPageSlot = QWidget()
        self.retiredRiskPageSlot = QWidget()
        self.reportsPage = ReportsPage()
        self.backtestPage = BacktestPage()
        self.postMarketPage = PostMarketPage()
        self.replayPage = ReplayPage()
        self.settingsPage = SettingsPage()
        self.equityPage = EquityPage()
        self.autoAttemptReportPage = AutoAttemptReportPage()
        self.aboutPage = AboutPage()
        self.helpPage = HelpPage()
        self.smartMoneyPage = SmartMoneyPage()
        self.casAnalysisPage = CasAnalysisPage()
        self.stockOptionsWatchPage = StockOptionsWatchPage()
        self.optionStrategiesPage = OptionStrategiesPage()
        self.strategyTradesPage = StrategyTradesPage()
        self.postMarketTpsAnalysisPage = PostMarketTpsAnalysisPage()
        self.preCandlePage = PreCandlePage()
        self.powerfulEnginePage = PowerfulEnginePage()
        self.putCallRatioPage = PutCallRatioPage()
        self.gapProbabilityPage = GapProbabilityPage()
        self.autoOpportunityPage = AutoOpportunityPage()
        self.trendMemoryPage = TrendMemoryPage()
        self.scalperPage = ScalperPage()
        self.notificationCenterPage = NotificationCenterPage()
        self.selfDevelopmentPage = SelfDevelopmentPage()
        self.recoveryCenterPage = RecoveryCenterPage()
        self.volatilityIntelligencePage = VolatilityIntelligencePage()
        self.expiryObservationPage = ExpiryObservationPage()
        self.executionControlPage = ExecutionControlPage()
        self.optionsAlgoPage = OptionsAlgoPage()
        self.cutieCommandPage = CutieCommandPage()
        self.optionsHub = ConsolidatedWorkspace((
            (self.optionsPage, "Trade Plan & Auto Paper"),
            (self.putCallRatioPage, "OI / PCR Intelligence"),
        ))
        self.strategyHub = ConsolidatedWorkspace((
            (self.optionStrategiesPage, "Defined-Risk Strategies"),
            (self.volatilityIntelligencePage, "VIX / ATR Intelligence"),
        ))
        self.postMarketHub = ConsolidatedWorkspace((
            (self.postMarketTpsAnalysisPage, "Daily TPS Analysis"),
            (self.postMarketPage, "Raw Market Timeline"),
        ))
        self.gapHub = ConsolidatedWorkspace((
            (self.gapProbabilityPage, "Automatic 3:20 + 3:40 Probability"),
        ))
        self.powerfulHub = ConsolidatedWorkspace((
            (self.powerfulEnginePage, "Combined Signal"),
            (self.smartMoneyPage, "Smart Money Evidence"),
            (self.preCandlePage, "Candle DNA"),
        ))
        self.autoOpportunityHub = ConsolidatedWorkspace((
            (self.autoOpportunityPage, "Automatic Opportunities"),
            (self.stockOptionsWatchPage, "Pinned F&O Watchlist"),
        ))
        retired = lambda: QWidget()
        pages = (
            self.dashboardPage, self.liveMarketPage, self.optionsHub, self.retiredChartCaptureSlot, self.journalPage,
            retired(), self.retiredAiPageSlot, self.retiredRiskPageSlot, self.reportsPage, self.settingsPage,
            self.backtestPage, retired(), self.replayPage, self.equityPage,
            self.autoAttemptReportPage, self.aboutPage, self.helpPage, retired(), retired(),
            self.casAnalysisPage, retired(), self.strategyHub, self.postMarketHub, retired(),
            self.powerfulHub, retired(), self.gapHub, self.autoOpportunityHub, self.trendMemoryPage,
            self.scalperPage, self.notificationCenterPage, self.selfDevelopmentPage, self.recoveryCenterPage, retired(),
            self.strategyTradesPage, self.expiryObservationPage, self.executionControlPage, self.optionsAlgoPage,
            self.cutieCommandPage,
        )
        for page in pages:
            self.stack.addWidget(page)
        self.journalPage.trade_saved.connect(self.dashboardPage.refresh)
        self.journalPage.trade_saved.connect(self.reportsPage.refresh)
        self.journalPage.trade_saved.connect(self.optionsPage.update_plan_readiness)
        self.optionsPage.trade_plan_ready.connect(lambda _plan: self.show_page(4))
        self.journalPage.open_backtesting.connect(lambda: self.show_page(10))
        self.optionsPage.paper_trade_captured.connect(lambda _plan: self.journalPage.load_trades())
        self.optionsPage.paper_trade_captured.connect(lambda _plan: self.dashboardPage.refresh())
        self.optionsPage.paper_trade_closed.connect(lambda _closed: self.journalPage.load_trades())
        self.optionsPage.paper_trade_closed.connect(lambda _closed: self.dashboardPage.refresh())
        self.optionsPage.paper_trade_closed.connect(lambda _closed: self.reportsPage.refresh())
        self.optionsPage.paper_trade_captured.connect(self.notify_trade_capture)
        self.optionsPage.paper_trade_closed.connect(self.notify_trade_closed)
        self.optionsPage.auto_paper_status.connect(self.notify_auto_attempt)
        self.optionStrategiesPage.loaded.connect(self.strategyTradesPage.ingest_analysis)
        self.strategyTradesPage.strategy_event.connect(self.notify_strategy_trade)
        self.strategyTradesPage.execution_requested.connect(self.prepare_execution_candidate)
        self.autoOpportunityPage.execution_requested.connect(self.prepare_execution_candidate)
        self.liveMarketPage.guard_alert.connect(self.notify_market_guard)
        self.liveMarketPage.structure_received.connect(self.notify_market_structure)
        self.liveMarketPage.level_alert.connect(self.notify_support_resistance)
        self.putCallRatioPage.sentiment_changed.connect(self.notify_pcr_sentiment)
        self.helpPage.page_requested.connect(self.show_page)
        self.optionsPage.auto_attempt_saved.connect(self.autoAttemptReportPage.refresh)
        self.settingsPage.live_connected.connect(self.start_default_nifty)
        self.settingsPage.live_connected.connect(self.optionsPage.prepare_live_workspace)
        self.settingsPage.live_connected.connect(lambda: self.autoOpportunityPage.scan(force=True))
        self.settingsPage.live_connected.connect(self.scalperPage.start_monitoring)
        self.settingsPage.live_connected.connect(self.dashboardPage.refresh_funds)
        self.cutieCommandPage.command_ready.connect(self.apply_cutie_command)
        self.scalperPage.scalp_alert.connect(self.notify_scalp_watch)
        self.notifier.notification_sent.connect(self.notificationCenterPage.refresh)
        self.notificationCenterPage.unread_count_changed.connect(self.sidebar.set_notification_count)
        for button, index in ((self.sidebar.dashboardButton, 0), (self.sidebar.liveMarketButton, 1),
                              (self.sidebar.optionsButton, 2),
                              (self.sidebar.journalButton, 4),
                              (self.sidebar.reportButton, 8), (self.sidebar.settingsButton, 9),
                              (self.sidebar.backtestButton, 10), (self.sidebar.replayButton, 12),
                              (self.sidebar.equityButton, 13), (self.sidebar.autoAttemptReportButton, 14),
                              (self.sidebar.aboutButton, 15), (self.sidebar.helpButton, 16)):
            button.clicked.connect(lambda _checked=False, page_index=index: self.show_page(page_index))
        self.sidebar.expiryObservationButton.clicked.connect(lambda: self.show_page(35))
        self.sidebar.executionControlButton.clicked.connect(lambda: self.show_page(36))
        self.sidebar.optionsAlgoButton.clicked.connect(lambda: self.show_page(37))
        self.sidebar.cutieCommandButton.clicked.connect(lambda: self.show_page(38))
        for button, index in ((self.sidebar.casAnalysisButton, 19),):
            button.clicked.connect(lambda _checked=False, page_index=index: self.show_page(page_index))
        self.sidebar.optionStrategiesButton.clicked.connect(lambda _checked=False: self.show_page(21))
        self.sidebar.strategyTradesButton.clicked.connect(lambda _checked=False: self.show_page(34))
        self.sidebar.postMarketTpsAnalysisButton.clicked.connect(lambda _checked=False: self.show_page(22))
        self.sidebar.powerfulEngineButton.clicked.connect(lambda _checked=False: self.show_page(24))
        self.sidebar.gapProbabilityButton.clicked.connect(lambda _checked=False: self.show_page(26))
        self.sidebar.autoOpportunityButton.clicked.connect(lambda _checked=False: self.show_page(27))
        self.sidebar.trendMemoryButton.clicked.connect(lambda _checked=False: self.show_page(28))
        self.sidebar.scalperButton.clicked.connect(lambda _checked=False: self.show_page(29))
        self.sidebar.notificationCenterButton.clicked.connect(lambda _checked=False: self.show_page(30))
        self.sidebar.selfDevelopmentButton.clicked.connect(lambda _checked=False: self.show_page(31))
        self.sidebar.recoveryCenterButton.clicked.connect(lambda _checked=False: self.show_page(32))
        body_layout.addWidget(self.stack)
        main_layout.addLayout(body_layout, 1)
        self.informationPanel = InformationPanel()
        add_glass_shadow(self.informationPanel, blur=16, y_offset=2, opacity=60)
        main_layout.addWidget(self.informationPanel)
        # Apply one predictable scrolling experience after every page has
        # joined the dashboard widget tree.
        for scroll_area in self.findChildren(QScrollArea):
            configure_scroll_area(scroll_area)
        self.post_market_report_timer = QTimer(self)
        self.post_market_report_timer.setInterval(60_000)
        self.post_market_report_timer.timeout.connect(self.update_completed_post_market_reports)
        self.post_market_report_timer.start()
        self.trend_memory_timer = QTimer(self)
        self.trend_memory_timer.setInterval(60_000)
        self.trend_memory_timer.timeout.connect(self.update_trend_memory_monitor)
        self.trend_memory_timer.start()
        QTimer.singleShot(0, self.update_completed_post_market_reports)
        QTimer.singleShot(0, self.update_trend_memory_monitor)
        QTimer.singleShot(0, self.notificationCenterPage.refresh)
        QTimer.singleShot(0, self.settingsPage.auto_connect_saved_credentials)

    def apply_cutie_command(self, command):
        """Route a validated command to the existing guarded controller."""
        try:
            message = self.optionsAlgoPage.apply_cutie_command(command)
        except Exception as error:
            self.cutieCommandPage.preview_text.setText(f"BLOCKED — {error}")
            return
        self.cutieCommandPage.preview_text.setText(f"APPLIED — {message}")
        if command.get("intent") in {"START_ALGO", "ALGO_STATUS"}:
            self.show_page(37)

    def update_completed_post_market_reports(self):
        """Finalize daily TPS audit after close and backfill missed app days."""
        try:
            updated = ensure_completed_post_market_reports(self.postMarketTpsAnalysisPage.db)
        except Exception:
            # A temporary database lock must not interrupt the trading UI;
            # the one-minute scheduler will retry automatically.
            return
        if updated and self.stack.currentIndex() == 22:
            self.postMarketTpsAnalysisPage.refresh(auto_generate=False)
        if updated:
            count = len(updated) if hasattr(updated, "__len__") else updated
            self.notifier.notify(
                "post_market_analysis", "TPS post-market report ready",
                f"{count} completed market-day report(s) were generated.",
            )
        try:
            development_updates = ensure_completed_self_development_reviews(self.selfDevelopmentPage.db)
        except Exception:
            return
        if development_updates and self.stack.currentIndex() == 31:
            self.selfDevelopmentPage.refresh(auto_generate=False)
        if development_updates:
            self.notifier.notify(
                "self_development", "TPS AI development review ready",
                f"{len(development_updates)} evidence-led software rectification review(s) were generated. Human review is required.",
            )
    def update_trend_memory_monitor(self):
        """Finalize completed days and alert once when a strong analog appears."""
        try:
            updated = ensure_completed_trend_memories(self.trendMemoryPage.db)
            live = get_live_trend_analogs(self.trendMemoryPage.db)
        except Exception:
            return
        if updated and self.stack.currentIndex() == 28:
            self.trendMemoryPage.refresh()
        for item in live:
            if not item.get("matches"):
                continue
            current, best = item["current"], item["matches"][0]
            if float(best.get("similarity", 0)) < 80.0:
                continue
            key = (current["trade_date"], current["symbol"], best["trade_date"])
            if key in self._trend_memory_alerts:
                continue
            self._trend_memory_alerts.add(key)
            self.notifier.notify(
                "trend_memory", f"TPS similar market pattern — {current['symbol']}",
                f"{best['similarity']:.1f}% match with {best['trade_date']}. Us din: {best['outcome_text']}",
                dedupe_key=f"{current['trade_date']}:{current['symbol']}:{best['trade_date']}",
                once_per_day=True,
            )

    def notify_trade_capture(self, plan):
        contract = plan.get("contract") or {}
        symbol = contract.get("symbol") or plan.get("symbol") or "Option trade"
        self.notifier.notify(
            "trade_capture", "TPS paper trade captured",
            f"{symbol} | Entry {float(plan.get('entry', 0)):.2f} | Stop {float(plan.get('stoploss', 0)):.2f} | Target {float(plan.get('target', 0)):.2f}",
        )

    def notify_trade_closed(self, closed):
        for item in closed or []:
            outcome = str(item.get("outcome", "TRADE EXIT")).upper()
            category = "target_achieved" if outcome == "TARGET HIT" else "stop_loss" if "STOP" in outcome else "trade_exit"
            self.notifier.notify(
                category, f"TPS paper trade: {outcome}",
                f"{item.get('symbol', 'Option trade')} exited at {float(item.get('ltp', 0)):.2f}.",
            )

    def notify_auto_attempt(self, result):
        if not isinstance(result, dict) or result.get("plan"):
            return
        attempt = result.get("attempt") or {}
        timing = attempt.get("timing") or {}
        if timing.get("stage") == "EARLY WATCH":
            candidate = attempt.get("candidate") or "SETUP"
            symbol = attempt.get("symbol") or "INDEX"
            self.notifier.notify(
                "early_watch", f"TPS Early Watch - {symbol} {candidate}",
                f"{attempt.get('candle_time') or 'Completed candle'} is near-qualified for study only; "
                "this is NOT an entry approval. Wait for FIRST VALID and every safety guard.",
                dedupe_key=f"{symbol}:{candidate}:{attempt.get('candle_time') or attempt.get('checked_at')}",
                once_per_day=True,
            )
            return
        self.notifier.notify(
            "auto_attempt_report", "TPS auto-trade evaluation completed",
            f"{attempt.get('candle_time') or 'Latest candle'} | {result.get('status', 'No trade captured')}",
        )

    def notify_market_guard(self, alert):
        self.notifier.notify(
            "risk_manager", alert.get("title", "TPS Open Trade Guard"),
            alert.get("message", "An open-trade risk condition needs review."),
        )

    def notify_market_structure(self, result):
        key = (result.get("symbol"), result.get("timeframe", "5m"))
        state = result.get("state")
        previous = self._market_states.get(key)
        self._market_states[key] = state
        if previous is None or previous == state:
            return
        self.notifier.notify(
            "market_structure", "TPS market structure changed",
            f"{key[0]} {key[1]} changed from {previous} to {state}. Support {result.get('support', 0):,.2f}; resistance {result.get('resistance', 0):,.2f}.",
        )

    def notify_support_resistance(self, alert):
        self.notifier.notify(
            "support_resistance", alert.get("title", "TPS support/resistance alert"),
            alert.get("message", "Price is near a marked chart level."),
            dedupe_key=alert.get("dedupe_key") or alert.get("title"), once_per_day=True,
        )

    def notify_pcr_sentiment(self, result):
        sentiment = result.get("sentiment") or {}
        pcr = result.get("chain", {}).get("pcr_oi")
        pcr_text = f"{pcr:.2f}" if pcr is not None else "unavailable"
        self.notifier.notify(
            "put_call_ratio", f"TPS OI sentiment changed — {result.get('symbol', 'Index')}",
            f"{sentiment.get('sentiment', 'OI context updated')} | OI-PCR {pcr_text}. Chart confirmation remains mandatory.",
        )

    def notify_scalp_watch(self, result):
        self.notifier.notify(
            "scalper", f"TPS {result.get('action')} — {result.get('symbol')}",
            f"{(result.get('option_liquidity') or {}).get('symbol', 'Near-expiry option')} | Premium entry ₹{result.get('entry_reference', 0):,.2f} | "
            f"SL {result.get('stop', 0):,.2f} | T1 {result.get('target1', 0):,.2f} | Score {result.get('score')}/100. Paper/research alert only.",
        )

    def notify_strategy_trade(self, event):
        kind = event.get("kind", "UPDATED")
        strategy = event.get("strategy", "Defined-risk strategy")
        message = (f"{event.get('symbol', 'Index')} {strategy} paper strategy captured for validation. "
                   "Maximum benefit/loss is predefined; no broker order was placed.")
        if kind == "CLOSED":
            message = f"{strategy} paper monitor closed: {event.get('outcome')} | Model P&L ₹{float(event.get('pnl') or 0):,.2f}."
        elif kind == "SESSION_REVIEW":
            message = (f"{event.get('symbol', 'Index')} ka market-close strategy review save ho gaya. "
                       f"Aaj ka best paper result: {strategy}. Strategy Trades page par full comparison dekhiye.")
        self.notifier.notify("strategy_trades", f"Cutie strategy {kind.lower()} — {strategy}", message)

    def show_page(self, index: int):
        requested_index = index
        aliases = {
            3: (2, self.optionsHub, 0),
            5: (2, self.optionsHub, 0),
            11: (22, self.postMarketHub, 1),
            7: (9, None, 0),
            17: (26, self.gapHub, 0),
            18: (24, self.powerfulHub, 1),
            20: (27, self.autoOpportunityHub, 1),
            23: (24, self.powerfulHub, 2),
            25: (2, self.optionsHub, 1),
            33: (21, self.strategyHub, 1),
        }
        if requested_index in aliases:
            index, hub, tab = aliases[requested_index]
            if hub is not None:
                hub.select_tab(tab)
        else:
            primary_tabs = {
                2: self.optionsHub,
                21: self.strategyHub,
                22: self.postMarketHub,
                24: self.powerfulHub,
                26: self.gapHub,
                27: self.autoOpportunityHub,
            }
            hub = primary_tabs.get(requested_index)
            if hub is not None:
                hub.select_tab(0)
        self.sidebar.set_active(index)
        if index == 0:
            self.dashboardPage.refresh()
        elif index == 8:
            self.reportsPage.refresh()
        elif index == 1:
            self.liveMarketPage.refresh_status()
            self.liveMarketPage.start_market_overview()
        elif index == 2:
            self.optionsPage.prepare_live_workspace()
        elif requested_index == 11:
            self.postMarketPage.refresh()
        elif index == 14:
            self.autoAttemptReportPage.refresh()
        elif index == 22:
            self.postMarketTpsAnalysisPage.refresh(auto_generate=True)
        elif requested_index == 25:
            self.putCallRatioPage.refresh()
        elif index == 26:
            self.gapProbabilityPage.refresh_history()
        elif index == 27:
            self.autoOpportunityPage.refresh_history()
        elif index == 28:
            self.trendMemoryPage.refresh()
        elif index == 29:
            self.scalperPage.analyze(force=True)
        elif index == 30:
            self.notificationCenterPage.refresh()
        elif index == 31:
            self.selfDevelopmentPage.refresh(auto_generate=True)
        elif requested_index == 33 and LiveSession.connected():
            self.volatilityIntelligencePage.analyze()
        elif requested_index == 34:
            self.strategyTradesPage.refresh()
        elif requested_index == 35:
            self.expiryObservationPage.refresh_history()
            self.expiryObservationPage.scan()
        elif requested_index == 36:
            self.executionControlPage.refresh_mode()
        elif requested_index == 37:
            self.optionsAlgoPage.refresh()
        self.stack.setCurrentIndex(index)

    def prepare_execution_candidate(self, payload):
        self.executionControlPage.load_candidate(payload)
        self.show_page(36)

    def start_default_nifty(self):
        self.liveMarketPage.select_symbol("NIFTY")
