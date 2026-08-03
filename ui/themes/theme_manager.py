from ui.themes.dark_theme import get_dark_theme
from ui.themes.light_theme import get_light_theme


THEMES = {"dark": get_dark_theme, "light": get_light_theme}


def apply_theme(application, theme_name):
    """Apply a saved visual preference without changing any trading settings."""
    application.setStyleSheet(THEMES.get(theme_name, get_dark_theme)())
