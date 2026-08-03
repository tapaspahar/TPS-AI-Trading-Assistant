from ui.themes.dark_theme import get_dark_theme


def get_emerald_theme():
    """Deep green terminal theme for a calmer, less blue-heavy workspace."""
    return (get_dark_theme()
            .replace("#0b1220", "#071b19")
            .replace("#101b30", "#0b2824")
            .replace("#101a2d", "#0b2421")
            .replace("#17243b", "#12332e")
            .replace("#1a2942", "#143a33")
            .replace("#1d4ed8", "#047857")
            .replace("#2563eb", "#059669")
            .replace("#4f8cff", "#34d399")
            .replace("#5590ff", "#6ee7b7")
            .replace("#243552", "#1e4a42")
            .replace("#2b3d5b", "#28574e")
            .replace("#2c4161", "#28574e"))
