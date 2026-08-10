import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QScrollArea

from ui.pages.live_market_page import LiveMarketPage
from ui.themes.theme_manager import apply_theme


class LiveMarketLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_market_snapshot_cards_fit_without_overlap_or_scroll(self):
        apply_theme(self.app, "dark", "maximalism")
        page = LiveMarketPage()
        page.resize(1560, 810)
        page.cards["breakout"].set_value("5m close > 24,606.07\nvolume confirmation")
        page.cards["breakdown"].set_value("5m close < 24,581.28\nvolume confirmation")
        for symbol in ("NIFTY", "BANKNIFTY", "SENSEX"):
            page.overview_cards[symbol].set_value("24,588.75\nBearish day bias (-0.70%)")
            page.overview_cards[f"{symbol} FUT"].set_value("24,672.20\nExpires 25 Aug")
        page.overview_cards["INDIA VIX"].set_value(
            "12.56  |  HEALTHY TREND\nUpdated 11:44:53"
        )
        page.show()
        self.app.processEvents()

        self.assertFalse(page.findChildren(QScrollArea))
        for card in list(page.cards.values()) + list(page.overview_cards.values()):
            self.assertLessEqual(card.value_label.geometry().bottom(), card.contentsRect().bottom())

        overview_cards = list(page.overview_cards.values())
        for index, card in enumerate(overview_cards):
            for other in overview_cards[index + 1:]:
                self.assertFalse(card.geometry().intersects(other.geometry()))
        self.assertLess(page.overview_box.geometry().bottom(), page.height())

        visible_text = " ".join(label.text() for label in page.findChildren(QLabel))
        self.assertNotIn("Live feed values will auto-fill", visible_text)
        page.close()


if __name__ == "__main__":
    unittest.main()
