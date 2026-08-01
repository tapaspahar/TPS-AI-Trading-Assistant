"""Local screenshot OCR and parsing for chart review."""

from __future__ import annotations

import re
from pathlib import Path


class OCRUnavailableError(RuntimeError):
    pass


class ChartCaptureService:
    SYMBOLS = ("BANKNIFTY", "FINNIFTY", "SENSEX", "NIFTY")

    def read_image(self, image_path: str | Path) -> dict:
        try:
            import pytesseract
            from PIL import Image, ImageOps
        except ImportError as error:
            raise OCRUnavailableError("OCR package is not installed. Install the project requirements first.") from error
        try:
            text = pytesseract.image_to_string(ImageOps.grayscale(Image.open(image_path)), config="--psm 6")
        except pytesseract.TesseractNotFoundError as error:
            raise OCRUnavailableError("Tesseract OCR is not installed or not on PATH. Install Tesseract, then restart the app.") from error
        return self.parse_text(text)

    def parse_text(self, text: str) -> dict:
        normalized = text.upper().replace(",", "")
        result = {"symbol": "", "timeframe": "", "open": "", "high": "", "low": "", "close": "", "vwap": "", "supertrend": "", "volume": "", "raw_text": text}
        for symbol in self.SYMBOLS:
            if re.search(rf"\b{symbol}\b", normalized):
                result["symbol"] = symbol
                break
        timeframe = re.search(r"\b(\d+)\s*(?:M|MIN)\b", normalized)
        if timeframe:
            result["timeframe"] = f"{timeframe.group(1)}m"
        ohlc = re.search(r"\bO\s*([\d.]+).*?\bH\s*([\d.]+).*?\bL\s*([\d.]+).*?\bC\s*([\d.]+)", normalized)
        if ohlc:
            result.update(dict(zip(("open", "high", "low", "close"), ohlc.groups())))
        for field, label in (("vwap", "VWAP"), ("supertrend", "SUPERTREND"), ("volume", "VOLUME")):
            match = re.search(rf"\b{label}\b\s*[: ]\s*([\d.]+)", normalized)
            if match:
                result[field] = match.group(1)
        return result
