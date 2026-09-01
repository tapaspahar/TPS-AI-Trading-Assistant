"""Automatic completed-candle analysis for all three headline indices."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from core.database_manager import Database
from engine.index_candle_analysis_engine import analyze_index_candle, combine_index_candles
from engine.oi_flow_intelligence import analyze_oi_flow
from services.option_contract_service import UNDERLYING_QUOTES, OptionContractService, contracts_near_spot
from services.market_data_hub import MarketDataHub


INDICES = ("NIFTY", "BANKNIFTY", "SENSEX")


def _time(row):
    value = str(row.get("time") or row.get("timestamp") or "")
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _completed(candles, now):
    rows = list(candles or [])
    if rows and (stamp := _time(rows[-1])) and stamp + timedelta(minutes=5) > now.replace(tzinfo=stamp.tzinfo):
        rows.pop()
    return rows


class IndexMarketAnalysisService:
    def __init__(self, client, db=None):
        self.client = client
        self.db = db or Database()
        self.contracts = OptionContractService()

    def scan_all(self, now=None):
        now = now or datetime.now()
        results, errors = [], []
        for symbol in INDICES:
            try:
                result = self._scan(symbol, now)
                if result:
                    results.append(result)
            except (RuntimeError, ValueError, IndexError, KeyError) as error:
                errors.append(f"{symbol}: {error}")
        combined = combine_index_candles(results)
        self.build_daily_report(now.strftime("%d-%m-%Y"), combined)
        return {"results": results, "combined": combined, "errors": errors}

    def _scan(self, symbol, now):
        future = self.contracts.get_front_month_future(symbol)
        candles = _completed(MarketDataHub.candles(self.client, future["exchange"], future["token"], "FIVE_MINUTE", 5), now)
        if len(candles) < 10:
            raise ValueError("completed 5-minute future candles insufficient")
        candle_time = _time(candles[-1]) or now.replace(second=0, microsecond=0)
        quote_config = UNDERLYING_QUOTES[symbol]
        spot = float(MarketDataHub.quote(self.client, quote_config["exchange"], quote_config["token"]).get("ltp", 0) or 0)
        contracts = contracts_near_spot(self.contracts.get_contracts(symbol), spot, wings=5)
        expiry = min(c["expiry"] for c in contracts)
        contracts = [c for c in contracts if c["expiry"] == expiry]
        quotes = MarketDataHub.option_chain(self.client, contracts[0]["exchange"], [c["token"] for c in contracts])
        from engine.option_chain_engine import analyze_option_chain
        chain = analyze_option_chain(contracts, quotes, spot)
        flow = analyze_oi_flow(chain["quote_rows"], spot, wing_count=5)
        flow["call_oi"], flow["put_oi"] = chain["call_oi"], chain["put_oi"]
        cas_active = symbol == "SENSEX" and now.weekday() < 5 and (now.hour, now.minute) >= (15, 15) and (now.hour, now.minute) <= (15, 40)
        result = analyze_index_candle(symbol, candles, flow, cas_active=cas_active)
        result.update({
            "symbol": symbol, "trade_date": candle_time.strftime("%d-%m-%Y"),
            "candle_time": candle_time.isoformat(timespec="minutes"), "analyzed_at": now.isoformat(timespec="seconds"),
        })
        result["details_json"] = json.dumps({"expiry": str(expiry), "spot": spot, "cas_active": cas_active, "flow_warnings": flow.get("warnings", [])})
        self.db.save_index_candle_analysis(result)
        return result

    def build_daily_report(self, trade_date, combined=None):
        rows = self.db.get_index_candle_analyses(trade_date)
        if not rows:
            return None
        per_symbol = {}
        for symbol in INDICES:
            ordered = sorted((r for r in rows if r["symbol"] == symbol), key=lambda r: r["candle_time"])
            if not ordered:
                continue
            first, last = ordered[0], ordered[-1]
            per_symbol[symbol] = {
                "candles": len(ordered), "move": round(float(last["close"] or 0) - float(first["open"] or 0), 2),
                "buyers": sum("BUYERS" in str(r["aggression"]) for r in ordered),
                "sellers": sum("SELLERS" in str(r["aggression"]) for r in ordered),
                "latest_oi": last["oi_direction"], "coverage": round(sum(int(r["source_completeness"] or 0) for r in ordered) / len(ordered)),
            }
        latest = []
        for symbol in INDICES:
            row = next((dict(r) for r in rows if r["symbol"] == symbol), None)
            if row: latest.append(row)
        combined = combined or combine_index_candles(latest)
        lines = [f"After Market Analysis of Index — {trade_date}", "", combined["explanation"], ""]
        for symbol, data in per_symbol.items():
            dominance = "buyers" if data["buyers"] > data["sellers"] else "sellers" if data["sellers"] > data["buyers"] else "balanced"
            lines.append(f"{symbol}: {data['candles']} completed candles | session observed move {data['move']:+,.2f} pts | {dominance} dominance | latest OI {data['latest_oi']} | source coverage {data['coverage']}%")
        lines += ["", "FII/DII: DATA GAP — reliable intraday participant feed connected nahi hai; daily provisional/public number ko candle cause nahi maana gaya.",
                  "Conclusion evidence-based hai: price + index-future volume + nearby option OI/COI. News causation bina timestamped source ke claim nahi ki gayi."]
        coverage = round(sum(v["coverage"] for v in per_symbol.values()) / max(len(per_symbol), 1))
        report = {"trade_date": trade_date, "generated_at": datetime.now().isoformat(timespec="seconds"), "market_state": combined["state"],
                  "source_completeness": coverage, "summary_text": "\n".join(lines), "details_json": json.dumps({"indices": per_symbol, "combined": combined})}
        self.db.save_index_daily_analysis(report)
        return report
