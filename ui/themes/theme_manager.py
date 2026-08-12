from ui.themes.dark_theme import get_dark_theme
from ui.themes.emerald_theme import get_emerald_theme
from ui.themes.light_theme import get_light_theme
from ui.themes.sunset_theme import get_sunset_theme
from ui.themes.ui_styles import get_ui_style_overlay


THEMES = {
    "dark": get_dark_theme,
    "light": get_light_theme,
    "emerald": get_emerald_theme,
    "sunset": get_sunset_theme,
}


def apply_theme(application, theme_name, ui_style="glassmorphism"):
    """Apply a saved visual preference without changing any trading settings."""
    application.setProperty("tpsThemeName", theme_name)
    application.setProperty("tpsUiStyle", ui_style)
    base = THEMES.get(theme_name, get_dark_theme)()
    application.setStyleSheet(base + "\n" + get_ui_style_overlay(ui_style))
