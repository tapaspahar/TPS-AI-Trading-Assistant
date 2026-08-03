from ui.themes.light_theme import get_light_theme


def get_sunset_theme():
    """Warm light theme with amber accents for daytime use."""
    return (get_light_theme()
            .replace("#f4f7fb", "#fff8f2")
            .replace("#edf3fa", "#fff0e2")
            .replace("#eaf1fa", "#ffedd5")
            .replace("#e7f0ff", "#ffedd5")
            .replace("#e0ecff", "#ffe4c4")
            .replace("#dbeafe", "#ffedd5")
            .replace("#2563eb", "#ea580c")
            .replace("#377cf6", "#f97316")
            .replace("#4f8cff", "#f97316")
            .replace("#c9d8eb", "#f1c9a5")
            .replace("#d1ddeb", "#efd4bd")
            .replace("#d7e1ef", "#f0d7c1"))
