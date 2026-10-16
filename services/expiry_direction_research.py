"""Persistent expiry-only research. One independent learning sample per index/day."""
import json
from datetime import datetime, time
from core.market_session import IST


def direction(change):
    return 'BULLISH' if change > .1 else 'BEARISH' if change < -.1 else 'SIDEWAYS'


def analyze(samples):
    samples = sorted(samples, key=lambda s: s['at'])
    morning = [s for s in samples if '09:15' <= s['at'][11:16] <= '10:15']
    before = [s for s in samples if '14:55' <= s['at'][11:16] < '15:00']
    after = [s for s in samples if '15:00' <= s['at'][11:16] < '15:30']
    trend = 'UNKNOWN'
    if len(morning) >= 10 and morning[0]['at'][11:16] <= '09:20' and morning[-1]['at'][11:16] >= '10:10':
        trend = direction((morning[-1]['spot'] / morning[0]['spot'] - 1) * 100)
    move = (after[-1]['spot'] / before[-1]['spot'] - 1) * 100 if before and after else None
    late = direction(move) if move is not None else 'UNKNOWN'
    relation = ('CONTINUATION' if trend == late else 'REVERSAL') if trend in ('BULLISH', 'BEARISH') and late in ('BULLISH', 'BEARISH') else 'UNRESOLVED'
    # Require a near-close sample and bounded gaps; partial sessions never enter learning.
    window = before[-1:] + after
    complete = bool(trend != 'UNKNOWN' and before and after and after[-1]['at'][11:16] >= '15:29'
                    and max((datetime.fromisoformat(b['at']) - datetime.fromisoformat(a['at'])).total_seconds()
                            for a, b in zip(window, window[1:])) <= 120)
    evidence = []
    if len(after) >= 2:
        previous = {r['contract']: r for r in after[-2]['chain']}
        for row in after[-1]['chain']:
            old = previous.get(row['contract'])
            if not old or row['oi'] is None or old['oi'] is None or old['oi'] <= 0 or old['price'] <= 0:
                continue
            pct = (row['price'] / old['price'] - 1) * 100
            oi_pct = (row['oi'] / old['oi'] - 1) * 100
            if abs(pct) < 2 or abs(oi_pct) < 1:
                continue
            label = ('possible long buildup' if oi_pct > 0 else 'possible short covering') if pct > 0 else ('possible writing' if oi_pct > 0 else 'possible long unwinding')
            evidence.append(f"{row['side']} {row['strike']:g}: premium {pct:+.1f}%, OI {oi_pct:+.1f}% ({label})")
    return dict(morning=trend, late=late, move=move, relation=relation, complete=complete,
                evidence=evidence, reason='; '.join(evidence) or 'OI/price evidence insufficient')


class ExpiryDirectionResearch:
    def __init__(self, db):
        self.db = db
        db.cursor.execute('''CREATE TABLE IF NOT EXISTS expiry_direction_snapshots (
            underlying TEXT, trade_date TEXT, observed_at TEXT, payload TEXT NOT NULL,
            PRIMARY KEY(underlying, observed_at))''')
        db.connection.commit()

    def record(self, symbol, expiry, now, spot, rows):
        if symbol not in ('NIFTY', 'SENSEX') or expiry != now.date() or not time(9, 15) <= now.time() < time(15, 30) or spot <= 0:
            return
        chain = []
        for item in rows:
            c, q = item['contract'], item['quote']
            price = float(q.get('ltp') or 0)
            oi = q.get('opnInterest', q.get('openInterest'))
            if price <= 0:
                continue
            chain.append(dict(contract=c['symbol'], side=c['option_type'], strike=float(c['strike']),
                              price=price, oi=float(oi) if oi is not None else None,
                              volume=q.get('tradeVolume', q.get('volume'))))
        sample = dict(at=now.isoformat(), spot=spot, chain=chain)
        self.db.cursor.execute('INSERT OR IGNORE INTO expiry_direction_snapshots VALUES (?,?,?,?)',
                               (symbol, now.date().isoformat(), now.isoformat(), json.dumps(sample)))
        self.db.connection.commit()

    def report(self, symbol, now):
        rows = self.db.cursor.execute('SELECT trade_date,payload FROM expiry_direction_snapshots WHERE underlying=? AND trade_date<=? ORDER BY observed_at',
                                      (symbol, now.date().isoformat())).fetchall()
        days = {}
        for row in rows:
            days.setdefault(row['trade_date'], []).append(json.loads(row['payload']))
        today = analyze(days.get(now.date().isoformat(), []))
        history = [analyze(s) for d, s in days.items() if d < now.date().isoformat()]
        history = [s for s in history if s['complete'] and s['morning'] == today['morning']]
        n = len(history)
        continuation = sum(s['relation'] == 'CONTINUATION' for s in history)
        reversal = sum(s['relation'] == 'REVERSAL' for s in history)
        move = '-' if today['move'] is None else f"{today['move']:+.2f}%"
        return (f"{symbol} | Morning (09:15–10:15): {today['morning']} | After 3 PM: {today['late']} ({move}) | {today['relation']}\n"
                f"Possible explanation: {today['reason']}\n"
                f"Prior complete expiry days with same morning trend: {n}; continuation {continuation}, reversal {reversal}, sideways {n-continuation-reversal}. "
                + (f"Observed continuation rate {continuation/n:.0%}. " if n >= 20 else 'Insufficient history (minimum 20 days for rate). ')
                + 'Nearby ATM/ITM/OTM sample only; OI does not prove cause. App must run from 09:15 through 15:30 IST. Missing morning data remains UNKNOWN.')
