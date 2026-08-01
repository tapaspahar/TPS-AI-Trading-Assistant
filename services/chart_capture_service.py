"""Local screenshot OCR and parsing for chart review."""

from __future__ import annotations

import re
import shutil
from pathlib import Path


class OCRUnavailableError(RuntimeError):
    pass


class ChartCaptureService:
    # TPS fixed chart profile. The colour/order lets OCR map otherwise identical
    # "EMA:Plot" labels on the broker chart.
    CHART_PROFILE = {
        "ema_5": "Pink",
        "ema_20": "Violet",
        "ema_50": "White",
        "vwap": "Yellow",
        "supertrend": "Green (bullish) / Red (bearish)",
        "volume_ema_period": 20,
    }
    SYMBOLS = ("BANKNIFTY", "FINNIFTY", "SENSEX", "NIFTY")

    def read_image(self, image_path: str | Path) -> dict:
        try:
            import pytesseract
            from PIL import Image, ImageOps
        except ImportError as error:
            raise OCRUnavailableError("OCR package is not installed. Install the project requirements first.") from error
        detected_command = shutil.which("tesseract")
        default_windows_command = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        if not detected_command and default_windows_command.exists():
            # The standard Windows installer sometimes does not update PATH.
            pytesseract.pytesseract.tesseract_cmd = str(default_windows_command)
        try:
            # Sparse mode is a better fit for broker charts with labels scattered
            # around the chart, watchlist and indicator rail.
            text = pytesseract.image_to_string(ImageOps.grayscale(Image.open(image_path)), config="--psm 11")
        except pytesseract.TesseractNotFoundError as error:
            raise OCRUnavailableError("Tesseract OCR is not installed or not on PATH. Install Tesseract, then restart the app.") from error
        return self.parse_text(text)

    def parse_text(self, text: str) -> dict:
        normalized = text.upper().replace(",", "")
        result = {"symbol": "", "timeframe": "", "open": "", "high": "", "low": "", "close": "", "ema_5": "", "ema_20": "", "ema_50": "", "vwap": "", "supertrend": "", "supertrend_state": "", "volume": "", "volume_ema_period": "20", "raw_text": text}
        for symbol in self.SYMBOLS:
            if re.search(rf"\b{symbol}\b", normalized):
                result["symbol"] = symbol
                break
        timeframe = re.search(r"\b(\d+)\s*(?:M|MIN)\b", normalized)
        if timeframe:
            result["timeframe"] = f"{timeframe.group(1)}m"
        ohlc = re.search(r"(?:\bO|[^\w]0)\s*([\d.]+)\s*H\s*([\d.]+)\s*L\s*([\d.]+)\s*C\s*([\d.]+)", normalized)
        if ohlc:
            result.update(dict(zip(("open", "high", "low", "close"), ohlc.groups())))
        for field, label in (("vwap", "VWAP"), ("supertrend", "SUPERTREND"), ("volume", "VOLUME")):
            match = re.search(rf"\b{label}\b\s*[: ]\s*([\d.]+)", normalized)
            if match:
                result[field] = match.group(1)
        # On the fixed TPS chart, the right-side labels appear vertically as
        # EMA20 (violet), EMA50 (white), then EMA5 (pink).
        ema_values = re.findall(r"EMA\s*:?\s*PLOT\s*([\d.]+)", normalized)
        if len(ema_values) >= 3:
            result["ema_20"], result["ema_50"], result["ema_5"] = ema_values[:3]
        try:
            if result["close"] and result["supertrend"]:
                result["supertrend_state"] = "BULLISH" if float(result["close"]) > float(result["supertrend"]) else "BEARISH"
        except ValueError:
            pass
        return result
