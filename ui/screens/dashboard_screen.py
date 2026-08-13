from PySide6.QtCore import QSize, QTimer
from PySide6.QtWidgets import QHBoxLayout, QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget

from ui.widgets.header import Header
from ui.widgets.information_panel import InformationPanel
from ui.widgets.navigation.sidebar import Sidebar
from ui.pages.dashboard_page import DashboardPage
from ui.pages.live_market_page import LiveMarketPage
from ui.pages.options_page import OptionsPage
from ui.pages.chart_capture_page import ChartCapturePage
from ui.pages.journal_page import JournalPage
from ui.pages.checklist_page import ChecklistPage
from ui.pages.ai_page import AIPage
from ui.pages.risk_page import RiskPage
from ui.pages.reports_page import ReportsPage
from ui.pages.backtest_page import BacktestPage
from ui.pages.post_market_page import PostMarketPage
from ui.pages.replay_page import ReplayPage
from ui.pages.settings_page import SettingsPage
from ui.pages.equity_page import EquityPage
from ui.pages.auto_attempt_report_page import AutoAttemptReportPage
from ui.pages.about_help_page import AboutPage, HelpPage
from ui.pages.next_day_bias_page import NextDayBiasPage
from ui.pages.smart_money_page import SmartMoneyPage
from ui.pages.cas_analysis_page import CasAnalysisPage
from ui.pages.stock_options_watch_page import StockOptionsWatchPage
from ui.pages.option_strategies_page import OptionStrategiesPage
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
from ui.widgets.glass_effects import add_glass_shadow
from ui.widgets.accessible_scroll import configure_scroll_area
from services.post_market_tps_analysis import ensure_completed_post_market_reports
from services.self_development_decision import ensure_completed_self_development_reviews
from services.notification_service import NotificationService
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
        self.chartCapturePage = ChartCapturePage()
        self.journalPage = JournalPage()
        self.checklistPage = ChecklistPage()
        self.aiPage = AIPage()
        self.riskPage = RiskPage()
        self.reportsPage = ReportsPage()
        self.backtestPage = BacktestPage()
        self.postMarketPage = PostMarketPage()
        self.replayPage = ReplayPage()
        self.settingsPage = SettingsPage()
        self.equityPage = EquityPage()
        self.autoAttemptReportPage = AutoAttemptReportPage()
        self.aboutPage = AboutPage()
        self.helpPage = HelpPage()
        self.nextDayBiasPage = NextDayBiasPage()
        self.smartMoneyPage = SmartMoneyPage()
        self.casAnalysisPage = CasAnalysisPage()
        self.stockOptionsWatchPage = StockOptionsWatchPage()
        self.optionStrategiesPage = OptionStrategiesPage()
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
        for page in (self.dashboardPage, self.liveMarketPage, self.optionsPage, self.chartCapturePage, self.journalPage,
                     self.checklistPage, self.aiPage, self.riskPage, self.reportsPage, self.settingsPage,
                     self.backtestPage, self.postMarketPage, self.replayPage, self.equityPage,
                     self.autoAttemptReportPage, self.aboutPage, self.helpPage, self.nextDayBiasPage,
                     self.smartMoneyPage, self.casAnalysisPage, self.stockOptionsWatchPage, self.optionStrategiesPage,
                     self.postMarketTpsAnalysisPage, self.preCandlePage, self.powerfulEnginePage, self.putCallRatioPage,
                     self.gapProbabilityPage, self.autoOpportunityPage, self.trendMemoryPage, self.scalperPage,
                     self.notificationCenterPage, self.selfDevelopmentPage, self.recoveryCenterPage):
            self.stack.addWidget(page)
        self.journalPage.trade_saved.connect(self.dashboardPage.refresh)
        self.journalPage.trade_saved.connect(self.reportsPage.refresh)
        self.journalPage.trade_saved.connect(self.optionsPage.update_plan_readiness)
        self.chartCapturePage.symbol_ready.connect(self.journalPage.set_symbol_from_capture)
        self.chartCapturePage.analysis_ready.connect(self.aiPage.load_chart_capture)
        self.aiPage.decision_ready.connect(self.handle_ai_decision)
        self.optionsPage.trade_plan_ready.connect(self.journalPage.load_trade_plan)
        self.optionsPage.trade_plan_ready.connect(self.riskPage.load_trade_plan)
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
        self.liveMarketPage.guard_alert.connect(self.notify_market_guard)
        self.liveMarketPage.structure_received.connect(self.notify_market_structure)
        self.liveMarketPage.level_alert.connect(self.notify_support_resistance)
        self.putCallRatioPage.sentiment_changed.connect(self.notify_pcr_sentiment)
        self.helpPage.page_requested.connect(self.show_page)
        self.optionsPage.auto_attempt_saved.connect(self.autoAttemptReportPage.refresh)
        self.optionsPage.open_chart_capture.connect(lambda: self.show_page(3))
        self.settingsPage.live_connected.connect(self.start_default_nifty)
        self.settingsPage.live_connected.connect(lambda: self.autoOpportunityPage.scan(force=True))
        self.settingsPage.live_connected.connect(self.scalperPage.start_monitoring)
        self.scalperPage.scalp_alert.connect(self.notify_scalp_watch)
        self.notifier.notification_sent.connect(self.notificationCenterPage.refresh)
        self.notificationCenterPage.unread_count_changed.connect(self.sidebar.set_notification_count)
        for button, index in ((self.sidebar.dashboardButton, 0), (self.sidebar.liveMarketButton, 1),
                              (self.sidebar.optionsButton, 2), (self.sidebar.chartCaptureButton, 3),
                              (self.sidebar.journalButton, 4), (self.sidebar.checklistButton, 5),
                              (self.sidebar.aiButton, 6), (self.sidebar.riskButton, 7),
                              (self.sidebar.reportButton, 8), (self.sidebar.settingsButton, 9),
                              (self.sidebar.backtestButton, 10), (self.sidebar.postMarketButton, 11), (self.sidebar.replayButton, 12),
                              (self.sidebar.equityButton, 13), (self.sidebar.autoAttemptReportButton, 14),
                              (self.sidebar.aboutButton, 15), (self.sidebar.helpButton, 16),
                              (self.sidebar.nextDayBiasButton, 17), (self.sidebar.smartMoneyButton, 18)):
            button.clicked.connect(lambda _checked=False, page_index=index: self.show_page(page_index))
        for button, index in ((self.sidebar.casAnalysisButton, 19), (self.sidebar.stockOptionsWatchButton, 20)):
            button.clicked.connect(lambda _checked=False, page_index=index: self.show_page(page_index))
        self.sidebar.optionStrategiesButton.clicked.connect(lambda _checked=False: self.show_page(21))
        self.sidebar.postMarketTpsAnalysisButton.clicked.connect(lambda _checked=False: self.show_page(22))
        self.sidebar.preCandleButton.clicked.connect(lambda _checked=False: self.show_page(23))
        self.sidebar.powerfulEngineButton.clicked.connect(lambda _checked=False: self.show_page(24))
        self.sidebar.putCallRatioButton.clicked.connect(lambda _checked=False: self.show_page(25))
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

    def show_page(self, index: int):
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
        elif index == 11:
            self.postMarketPage.refresh()
        elif index == 14:
            self.autoAttemptReportPage.refresh()
        elif index == 7:
            self.riskPage.refresh()
        elif index == 22:
            self.postMarketTpsAnalysisPage.refresh(auto_generate=True)
        elif index == 25:
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
        self.stack.setCurrentIndex(index)

    def handle_ai_decision(self, context):
        self.optionsPage.set_chart_context(context)
        self.show_page(2)

    def start_default_nifty(self):
        self.liveMarketPage.select_symbol("NIFTY")
