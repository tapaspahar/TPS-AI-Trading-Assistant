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
            source_image = Image.open(image_path)
            image = ImageOps.grayscale(source_image)
            text = pytesseract.image_to_string(image, config="--psm 11")
        except pytesseract.TesseractNotFoundError as error:
            raise OCRUnavailableError("Tesseract OCR is not installed or not on PATH. Install Tesseract, then restart the app.") from error
        result = self.parse_text(text)
        result.update(self._extract_colored_label_values(source_image, pytesseract))
        self._set_supertrend_state(result)
        return result

    @staticmethod
    def _extract_colored_label_values(image, pytesseract) -> dict:
        """OCR the compact yellow VWAP badge separately from the full chart."""
        data = pytesseract.image_to_data(image, config="--psm 11", output_type=pytesseract.Output.DICT)
        for index, word in enumerate(data["text"]):
            if word.strip().upper().replace(",", "") != "VWAP":
                continue
            left, top = data["left"][index], data["top"][index]
            width, height = data["width"][index], data["height"][index]
            badge = image.crop((max(0, left - 10), max(0, top - 12), min(image.width, left + max(width, 130)), min(image.height, top + height + 14))).resize((810, 180))
            badge_text = pytesseract.image_to_string(badge, config="--psm 7").upper().replace(" ", "")
            value = re.search(r"VWAP([\d.]+)", badge_text)
            if value:
                return {"vwap": value.group(1)}
        # Yellow VWAP badges may be readable by colour even when the word is
        # too small for image-to-data. This fallback searches only the chart's
        # right indicator rail, avoiding yellow candles elsewhere on screen.
        rail_left, rail_right = int(image.width * 0.87), int(image.width * 0.96)
        rail_top, rail_bottom = int(image.height * 0.15), int(image.height * 0.80)
        yellow_pixels = []
        for y in range(rail_top, rail_bottom):
            for x in range(rail_left, rail_right):
                red, green, blue = image.getpixel((x, y))[:3]
                if red > 160 and green > 120 and blue < 100:
                    yellow_pixels.append((x, y))
        if yellow_pixels:
            left, right = min(x for x, _ in yellow_pixels), max(x for x, _ in yellow_pixels)
            top, bottom = min(y for _, y in yellow_pixels), max(y for _, y in yellow_pixels)
            badge = image.crop((max(0, left - 2), max(0, top - 5), min(image.width, right + 8), min(image.height, bottom + 6))).resize((810, 180))
            badge_text = pytesseract.image_to_string(badge, config="--psm 7").upper().replace(" ", "")
            value = re.search(r"VWAP([\d.]+)", badge_text)
            if value:
                return {"vwap": value.group(1)}
        return {}

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
        # Sparse OCR can read a coloured badge's number just before its label.
        if not result["supertrend"]:
            preceding = re.search(r"([\d]{3,}\.[\d]+)(?:\s|[^\d]){0,24}SUPERTREND", normalized)
            if preceding:
                result["supertrend"] = preceding.group(1)
        # On the fixed TPS chart, the right-side labels appear vertically as
        # EMA20 (violet), EMA50 (white), then EMA5 (pink).
        ema_values = re.findall(r"EMA\s*:?\s*PLOT\s*([\d.]+)", normalized)
        if len(ema_values) >= 3:
            result["ema_20"], result["ema_50"], result["ema_5"] = ema_values[:3]
        self._set_supertrend_state(result)
        return result

    @staticmethod
    def _set_supertrend_state(result: dict) -> None:
        try:
            if result["close"] and result["supertrend"]:
                result["supertrend_state"] = "Green / Bullish" if float(result["close"]) > float(result["supertrend"]) else "Red / Bearish"
        except ValueError:
            pass
