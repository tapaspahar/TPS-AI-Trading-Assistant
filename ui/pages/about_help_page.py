from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QScrollArea, QTabWidget, QVBoxLayout, QWidget

from release_info import DISPLAY_VERSION, LAST_UPDATED_AT, RELEASE_NOTES, SOFTWARE_UPDATE_VERSION


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


class AboutPage(QWidget):
    """Product information, attribution and safety scope."""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(10)
        title = QLabel("About TPS")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        subtitle = QLabel("Application purpose, capabilities, credits and safety information.")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        layout.addWidget(_scrolling_text(self._about_html()), 1)

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
          <li>Combine India VIX, ATR regime, opening range, previous-day levels, gap context and verified economic events.</li>
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
          <li>Open <b>Settings</b>, enter your capital and safety limits, choose a broker profile and save its credentials securely,
          and connect live data.</li>
          <li>Use <b>Market Snapshot</b> to select NIFTY, BANKNIFTY or SENSEX and confirm the 5-minute structure,
          support, resistance and breakout/breakdown levels.</li>
          <li>Use <b>Chart Capture</b> or live capture to load EMA 5/20/50, VWAP, SuperTrend, RSI, ATR and volume.</li>
          <li>Review the result in <b>AI Analysis</b>. A bullish candle alone is not a bullish structure; the core
          trend inputs must agree.</li>
          <li>In <b>Options Workspace</b>, keep the recommended Adaptive match rule when you want the required
          checklist count, entry extension and regular-move objective to respond to the live VIX/market regime.</li>
          <li>Open <b>Options Workspace</b>, load the expiry and contract, then analyse OI/PCR. CE is considered
          for confirmed bullish structure and PE for confirmed bearish structure.</li>
          <li>Review <b>Market Environment</b>: India VIX, ATR regime, opening range, previous-day high/low,
          overnight gap, nearby economic events and the directional-versus-hedge research note.</li>
          <li>Check the generated plan in <b>Risk Control Center</b>. Quantity uses predefined index lots:
          NIFTY 65, BANKNIFTY 30 and SENSEX 20.</li>
          <li>Use <b>CAS Analysis</b> after market close to compare an F&amp;O stock's 3:00-3:15 reference VWAP,
          final cash close and front-month futures close. TPS labels this as an estimate when exchange auction
          imbalance data is unavailable through the broker feed.</li>
          <li>Use <b>Stock Options Watch</b> to maintain up to 8 active NSE F&amp;O shares. The completed-candle
          scan shows CE/PE side, score, entry timing and a one-lot paper plan with entry, stop, target and quantity.</li>
          <li>Use <b>Option Strategies</b> to review a VIX/regime-aware limited-risk structure. TPS may suggest a
          Bull Call Debit Spread, Bear Put Debit Spread or Defined-Risk Iron Condor, and shows every leg plus
          one-lot maximum profit/loss. WAIT means the live payoff is not clean enough.</li>
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
        <b>Post-Market Report:</b> inspect the raw saved candle and option-chain timeline.<br>
        <b>Post Market Analysis of TPS:</b> keep a permanent date-wise Roman Hindi journal explaining why
        automatic paper trades were captured or rejected, including coverage gaps and the best near-setups.
        TPS generates it automatically after 3:31 PM and backfills a missed completed date after restart.</p>
        <h3>If no trade appears</h3>
        <p>Open Auto Attempt Report and read the exact failed conditions. Check whether live data was available,
        the candle had closed, trend votes agreed, directional volume was sufficient, support/resistance allowed
        safe room, OI context did not conflict, and daily risk limits were not reached. Lowering a score threshold
        is useful for testing but does not bypass core safety blockers.</p>
        <h3>Automatic paper safety</h3>
        <p>A setup can still be blocked by stale candles, invalid quotes, low option volume, wide bid/ask spread,
        poor risk:reward, cooldown, daily limits, market-close time or a high-impact event window. Configure the
        optional Trading Economics key in Settings for automatic calendar data. Without a valid key TPS reports
        the feed as unavailable; it never creates an event. The event override is for paper testing only and is
        written into the audit. Open paper trades use premium stop/target, optional trailing stop and time exit,
        while underlying 5-minute and 15-minute structure alerts continue independently.</p>
        """

    @staticmethod
    def _hindi_help() -> str:
        return """
        <h2>Jaldi shuru kaise karein</h2>
        <ol>
          <li><b>Settings</b> kholiye, capital aur safety limits bhariye, broker profile select karke credentials securely save
          karke live data connect kijiye.</li>
          <li><b>Market Snapshot</b> me NIFTY, BANKNIFTY ya SENSEX select karke 5-minute market structure,
          support, resistance aur breakout/breakdown level check kijiye.</li>
          <li><b>Chart Capture</b> se EMA 5/20/50, VWAP, SuperTrend, RSI, ATR aur volume values load kijiye.</li>
          <li><b>AI Analysis</b> me result verify kijiye. Sirf ek bullish candle ka matlab bullish market nahi hota;
          main trend conditions ka same direction me hona zaroori hai.</li>
          <li><b>Options Workspace</b> me recommended Adaptive match rule rakhiye. Is mode me required checklist
          count, entry extension aur regular-move objective live VIX/market regime ke hisaab se badlenge.</li>
          <li><b>Options Workspace</b> me expiry aur contract load karke OI/PCR analyse kijiye. Confirmed bullish
          structure me CE aur confirmed bearish structure me PE consider hoga.</li>
          <li><b>Market Environment</b> me India VIX, ATR regime, opening range, previous-day high/low, gap,
          economic event aur directional/hedge research note dekhiye.</li>
          <li><b>Risk Control Center</b> me plan ka risk dekhiye. Quantity predefined lots se niklegi:
          NIFTY 65, BANKNIFTY 30 aur SENSEX 20.</li>
          <li>Market close ke baad <b>CAS Analysis</b> me F&amp;O stock ka 3:00-3:15 reference VWAP, final cash close
          aur front-month future close compare kijiye. Broker feed me exchange auction imbalance na milne par
          TPS result ko estimate ke roop me clearly dikhayega.</li>
          <li><b>Stock Options Watch</b> me maximum 8 active NSE F&amp;O shares rakhiye. Completed 5-minute candle
          scan CE/PE side, score, entry timing aur one-lot paper plan ka entry, stop, target aur quantity dikhayega.</li>
          <li><b>Option Strategies</b> me VIX aur market regime ke hisaab se limited-risk structure review kijiye.
          TPS Bull Call Debit Spread, Bear Put Debit Spread ya Defined-Risk Iron Condor suggest kar sakta hai aur
          har leg ke saath one-lot maximum profit/loss dikhayega. WAIT ka matlab clean payoff abhi nahi bana.</li>
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
        <b>Post-Market Report:</b> saved candle aur option-chain ka raw timeline.<br>
        <b>Post Market Analysis of TPS:</b> date-wise permanent Roman Hindi journal jisme trade capture/reject
        hone ka reason, monitoring gap aur best near-setup baad me kabhi bhi padha ja sakta hai. TPS is report ko
        3:31 PM ke baad khud generate karta hai; app band ho to agle restart par missed date backfill hoti hai.</p>
        <h3>Agar trade na mile</h3>
        <p>Auto Attempt Report kholkar failed conditions padhiye. Check kijiye ki live data mila tha, candle close
        hui thi, trend votes same direction me the, directional volume strong tha, support/resistance ke paas
        sufficient room tha, OI context conflict nahi kar raha tha aur daily risk limit complete nahi hui thi.
        Testing ke liye score kam kiya ja sakta hai, lekin core safety blockers bypass nahi honge.</p>
        <h3>Auto paper safety</h3>
        <p>Score pass hone ke baad bhi stale candle, invalid quote, kam option volume, zyada bid/ask spread,
        kam risk:reward, cooldown, daily limit, market-close time ya high-impact event trade ko rok sakta hai.
        Automatic calendar ke liye Settings me optional Trading Economics key dijiye. Key na hone par TPS feed
        unavailable clearly batata hai; koi event banata nahi hai. Event override sirf paper testing ke liye hai
        aur audit me save hota hai. Open paper trade me premium stop/target, optional trailing stop aur time exit
        ke saath underlying 5-minute aur 15-minute structure alerts bhi independently check hote hain.</p>
        <h3>Zaroori baat</h3>
        <p>TPS analysis aur learning ke liye hai. Profit guarantee nahi karta aur financial advice nahi hai.
        Application broker order place, modify ya cancel nahi karti. Manual trade se pehle har value khud verify kijiye.</p>
        """

    @staticmethod
    def _release_notes_html() -> str:
        notes = "".join(f"<li>{note}</li>" for note in RELEASE_NOTES)
        return f"""
        <h2>Software Update — {SOFTWARE_UPDATE_VERSION}</h2>
        <p><b>Updated:</b> {LAST_UPDATED_AT}<br>
        <b>Release status:</b> Release 1.1 development build; published Release 1.0 remains unchanged.</p>
        <h3>What was built today</h3>
        <ul>{notes}</ul>
        <h3>Roman Hindi summary</h3>
        <p>Aaj ke development update me CAS Analysis, Stock Options Watch, adaptive market rules,
        limited-risk Option Strategies, Market Snapshot layout improvements, reliable scrolling,
        default event status aur visible update history add ki gayi hai.</p>
        <p>Ye notes sirf completed application changes dikhate hain. Kisi diagnostic suggestion ko
        tab tak completed nahi maana jayega jab tak uska code update aur testing finish na ho.</p>
        """


class HelpPage(QWidget):
    """Offline operating guide in English and Roman Hindi."""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(10)
        title = QLabel("Help Center")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        subtitle = QLabel("Step-by-step application guide available offline in two languages.")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        tabs = QTabWidget()
        tabs.addTab(_scrolling_text(AboutPage._english_help()), "English")
        tabs.addTab(_scrolling_text(AboutPage._hindi_help()), "Roman Hindi")
        tabs.addTab(_scrolling_text(AboutPage._release_notes_html()), "Release Notes")
        layout.addWidget(tabs, 1)
