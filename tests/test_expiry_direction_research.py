from datetime import datetime, date
from core.market_session import IST
from core.database_manager import Database
from services.expiry_direction_research import analyze, ExpiryDirectionResearch


def sample(clock, spot):
    return dict(at=f'2026-10-15T{clock}:00+05:30', spot=spot, chain=[])


def session():
    rows = [sample(f'09:{minute:02}', 100 + minute / 100) for minute in range(15, 60)]
    rows += [sample(f'10:{minute:02}', 101) for minute in range(16)]
    rows += [sample('14:59', 102)]
    rows += [sample(f'15:{minute:02}', 103) for minute in range(30)]
    return rows


def test_continuation_and_complete():
    result = analyze(session())
    assert result['morning'] == result['late'] == 'BULLISH'
    assert result['relation'] == 'CONTINUATION'
    assert result['complete']


def test_partial_and_missing_baseline_do_not_learn():
    assert not analyze(session()[:-10])['complete']
    assert analyze(session()[-30:])['morning'] == 'UNKNOWN'
    assert not analyze(session()[::10])['complete']


def test_reversal():
    rows = session()
    for row in rows[-30:]:
        row['spot'] = 100
    assert analyze(rows)['relation'] == 'REVERSAL'


def test_persistence_and_expiry_gate(tmp_path):
    db = Database(tmp_path / 'expiry.db')
    store = ExpiryDirectionResearch(db)
    now = datetime(2026, 10, 15, 15, 5, tzinfo=IST)
    store.record('NIFTY', date(2026, 10, 16), now, 100, [])
    assert not db.cursor.execute('SELECT * FROM expiry_direction_snapshots').fetchall()
    store.record('NIFTY', now.date(), now, 100, [])
    store.record('NIFTY', now.date(), now, 100, [])
    assert len(db.cursor.execute('SELECT * FROM expiry_direction_snapshots').fetchall()) == 1
    assert 'UNKNOWN' in ExpiryDirectionResearch(db).report('NIFTY', now)
    db.connection.close()
