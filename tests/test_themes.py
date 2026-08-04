import unittest

from ui.themes.dark_theme import get_dark_theme
from ui.themes.emerald_theme import get_emerald_theme
from ui.themes.light_theme import get_light_theme
from ui.themes.sunset_theme import get_sunset_theme


class GlassThemeTests(unittest.TestCase):
    def test_every_theme_uses_the_glass_application_shell(self):
        for theme in (get_dark_theme(), get_emerald_theme(), get_light_theme(), get_sunset_theme()):
            self.assertIn("QWidget#dashboardScreen", theme)
            self.assertIn("QStackedWidget#contentStack", theme)
            self.assertIn("rgba(", theme)
            self.assertIn("qlineargradient", theme)
            self.assertIn("QFrame#dashboardCard", theme)

    def test_theme_accents_remain_distinct(self):
        self.assertIn("#3b82f6", get_dark_theme())
        self.assertIn("#10b981", get_emerald_theme())
        self.assertIn("#f97316", get_sunset_theme())
        self.assertIn("#edf4ff", get_light_theme())
