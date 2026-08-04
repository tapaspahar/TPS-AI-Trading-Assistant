from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QScrollArea, QTabWidget, QVBoxLayout, QWidget

from release_info import DISPLAY_VERSION


def _scrolling_text(html: str) -> QScrollArea:
    label = QLabel(html)
    label.setWordWrap(True)
    label.setTextFormat(Qt.RichText)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
    label.setOpenExternalLinks(True)
    label.setContentsMargins(18, 16, 18, 20)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.NoFrame)
    scroll.setWidget(label)
    return scroll


class AboutHelpPage(QWidget):
    """Offline bilingual product information and operating help."""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(10)
        title = QLabel("About & Help")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        subtitle = QLabel("Application information and an offline guide in English and Roman (phonetic) Hindi.")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        tabs = QTabWidget()
        tabs.addTab(_scrolling_text(self._about_html()), "About")
        tabs.addTab(_scrolling_text(self._english_help()), "Help — English")
        tabs.addTab(_scrolling_text(self._hindi_help()), "Help — Roman Hindi")
        layout.addWidget(tabs, 1)

    @staticmethod
    def _about_html() -> str:
        return f"""
        <h2>TPS AI Trading Assistant — {DISPLAY_VERSION}</h2>
        <p>TPS is a decision-support and trading-discipline application for Indian markets. It brings market
        structure, chart confirmation, option-chain context, risk controls, paper-trade validation, journaling,
        backtesting and post-market review into one desktop workspace.</p>
        <h3>What TPS is designed to do</h3>
        <ul>
          <li>Analyse NIFTY, BANKNIFTY and SENSEX market context.</li>
          <li>Evaluate EMA 5/20/50, VWAP, SuperTrend, volume, candle behaviour and support/resistance.</li>
          <li>Use OI, change in OI, volume PCR and OI PCR as confirmation—not as a standalone signal.</li>
          <li>Create reviewable CE/PE plans only when configured rules and risk limits permit.</li>
          <li>Record every automated paper-trade evaluation for later audit.</li>
        </ul>
        <h3>Credits</h3>
        <p><b>Tapas Kumar Pahar</b> — Developer, product direction, trading workflows and strategy rules.<br>
        <b>Pooja Pandey</b> — User-interface design.<br>
        <b>OpenAI Codex</b> — Development collaboration, implementation and testing assistance.</p>
        <h3>Important safety scope</h3>
        <p>TPS is an analytical and educational tool. It does not guarantee returns and must not be treated as
        financial advice. The current workflow is read-only and paper-trading focused: it does not place, modify
        or cancel a broker order. Always verify prices, expiry, strike, lot size, risk and event/news conditions
        before taking any manual action.</p>
        """

    @staticmethod
    def _english_help() -> str:
        return """
        <h2>Quick start</h2>
        <ol>
          <li>Open <b>Settings</b>, enter your capital and safety limits, save Angel One credentials securely,
          and connect live data.</li>
          <li>Use <b>Market Snapshot</b> to select NIFTY, BANKNIFTY or SENSEX and confirm the 5-minute structure,
          support, resistance and breakout/breakdown levels.</li>
          <li>Use <b>Chart Capture</b> or live capture to load EMA 5/20/50, VWAP, SuperTrend, RSI, ATR and volume.</li>
          <li>Review the result in <b>AI Analysis</b>. A bullish candle alone is not a bullish structure; the core
          trend inputs must agree.</li>
          <li>Open <b>Options Workspace</b>, load the expiry and contract, then analyse OI/PCR. CE is considered
          for confirmed bullish structure and PE for confirmed bearish structure.</li>
          <li>Check the generated plan in <b>Risk Control Center</b>. Quantity uses predefined index lots:
          NIFTY 65, BANKNIFTY 30 and SENSEX 20.</li>
          <li>Use <b>Trade Journal</b> for planned entry, stop loss, target, actual exit and review notes.</li>
        </ol>
        <h3>Workspace guide</h3>
        <p><b>Dashboard:</b> daily activity and journal summary.<br>
        <b>Equity Research:</b> search NSE shares, analyse historical candles and maintain a watchlist.<br>
        <b>Auto Attempt Report:</b> permanent 5-minute audit showing captured, rejected and skipped evaluations.<br>
        <b>Checklist:</b> manual discipline and confirmation checks.<br>
        <b>Reports:</b> performance summaries from journal records.<br>
        <b>Backtesting:</b> test rules on historical candles before trusting them live.<br>
        <b>Candle Replay:</b> review decisions candle by candle without future information.<br>
        <b>Post-Market Report:</b> inspect the completed session and missed/blocked setups.</p>
        <h3>If no trade appears</h3>
        <p>Open Auto Attempt Report and read the exact failed conditions. Check whether live data was available,
        the candle had closed, trend votes agreed, directional volume was sufficient, support/resistance allowed
        safe room, OI context did not conflict, and daily risk limits were not reached. Lowering a score threshold
        is useful for testing but does not bypass core safety blockers.</p>
        """

    @staticmethod
    def _hindi_help() -> str:
        return """
        <h2>Jaldi shuru kaise karein</h2>
        <ol>
          <li><b>Settings</b> kholiye, capital aur safety limits bhariye, Angel One credentials securely save
          karke live data connect kijiye.</li>
          <li><b>Market Snapshot</b> me NIFTY, BANKNIFTY ya SENSEX select karke 5-minute market structure,
          support, resistance aur breakout/breakdown level check kijiye.</li>
          <li><b>Chart Capture</b> se EMA 5/20/50, VWAP, SuperTrend, RSI, ATR aur volume values load kijiye.</li>
          <li><b>AI Analysis</b> me result verify kijiye. Sirf ek bullish candle ka matlab bullish market nahi hota;
          main trend conditions ka same direction me hona zaroori hai.</li>
          <li><b>Options Workspace</b> me expiry aur contract load karke OI/PCR analyse kijiye. Confirmed bullish
          structure me CE aur confirmed bearish structure me PE consider hoga.</li>
          <li><b>Risk Control Center</b> me plan ka risk dekhiye. Quantity predefined lots se niklegi:
          NIFTY 65, BANKNIFTY 30 aur SENSEX 20.</li>
          <li><b>Trade Journal</b> me entry, stop loss, target, actual exit aur review notes record kijiye.</li>
        </ol>
        <h3>Har page ka kaam</h3>
        <p><b>Dashboard:</b> aaj ki activity aur journal summary.<br>
        <b>Equity Research:</b> NSE share search, historical analysis aur watchlist.<br>
        <b>Auto Attempt Report:</b> har 5-minute candle par capture, rejection ya skip hone ka permanent record.<br>
        <b>Checklist:</b> manual discipline aur confirmation checks.<br>
        <b>Reports:</b> journal data se performance summary.<br>
        <b>Backtesting:</b> live use se pehle historical candles par rules test karna.<br>
        <b>Candle Replay:</b> future data dekhe bina candle-by-candle practice.<br>
        <b>Post-Market Report:</b> market band hone ke baad poore session aur missed/blocked setups ka review.</p>
        <h3>Agar trade na mile</h3>
        <p>Auto Attempt Report kholkar failed conditions padhiye. Check kijiye ki live data mila tha, candle close
        hui thi, trend votes same direction me the, directional volume strong tha, support/resistance ke paas
        sufficient room tha, OI context conflict nahi kar raha tha aur daily risk limit complete nahi hui thi.
        Testing ke liye score kam kiya ja sakta hai, lekin core safety blockers bypass nahi honge.</p>
        <h3>Zaroori baat</h3>
        <p>TPS analysis aur learning ke liye hai. Profit guarantee nahi karta aur financial advice nahi hai.
        Application broker order place, modify ya cancel nahi karti. Manual trade se pehle har value khud verify kijiye.</p>
        """
