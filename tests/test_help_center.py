import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication, QTextBrowser

from ui.pages.about_help_page import HelpPage, help_document_colors
from ui.pages.help_content import PAGES, help_html
from ui.themes.theme_manager import apply_theme


class HelpCenterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_all_routes_exist_in_each_language(self):
        self.assertEqual(len(PAGES), 33)
        self.assertNotIn("AI Analysis", {page[1] for page in PAGES})
        for language in ("en", "roman", "hi"):
            rendered = help_html(language)
            for page_index, title, *_rest in PAGES:
                self.assertIn(title, rendered)
                self.assertIn(f"tps://page/{page_index}", rendered)

    def test_workspace_link_emits_target_page(self):
        page = HelpPage()
        received = []
        page.page_requested.connect(received.append)
        browser = page.findChildren(QTextBrowser)[0]
        page._open_link(browser, QUrl("tps://page/25"))
        self.assertEqual(received, [25])

    def test_help_reader_restyles_for_dark_light_and_brutalist_surfaces(self):
        page = HelpPage()
        browser = page.findChildren(QTextBrowser)[0]

        apply_theme(self.app, "dark", "maximalism")
        self.app.processEvents()
        browser.refresh_theme()
        self.assertIn("#eef2ff", browser.document().defaultStyleSheet())

        apply_theme(self.app, "light", "glassmorphism")
        self.app.processEvents()
        browser.refresh_theme()
        self.assertIn("#172033", browser.document().defaultStyleSheet())

        apply_theme(self.app, "dark", "brutalism")
        self.app.processEvents()
        browser.refresh_theme()
        self.assertIn("#050505", browser.document().defaultStyleSheet())

    def test_every_theme_style_pair_has_explicit_readable_document_colors(self):
        themes = ("dark", "light", "emerald", "sunset")
        styles = (
            "skeuomorphism", "neomorphism", "glassmorphism", "claymorphism", "minimalism",
            "maximalism", "brutalism", "liquid_glass", "bento_grid", "spatial_ui",
        )
        for theme in themes:
            for style in styles:
                colors = help_document_colors(theme, style)
                self.assertRegex(colors["text"], r"^#[0-9a-fA-F]{6}$")
                self.assertNotEqual(colors["text"], colors["link"])


if __name__ == "__main__":
    unittest.main()
