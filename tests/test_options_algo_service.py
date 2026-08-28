from services.options_algo_service import calculate_algo_day_state, calculate_validation_metrics


def settings(**overrides):
    values = {
        "options_algo_daily_target_net": 1000,
        "options_algo_daily_max_loss": 500,
        "options_algo_max_trades": 10,
        "options_algo_estimated_charges": 50,
    }
    values.update(overrides)
    return values


def test_algo_state_uses_net_after_closed_trade_charges():
    state = calculate_algo_day_state(
        {"trades": 2, "closed_trades": 2, "open_trades": 0, "realized_pnl": 1100},
        settings(), session_active=True,
    )
    assert state.net_pnl == 1000
    assert state.state == "TARGET HIT"
    assert not state.allow_new_entry


def test_algo_state_kills_new_entries_at_loss_or_trade_limit():
    loss = calculate_algo_day_state(
        {"trades": 2, "closed_trades": 2, "open_trades": 0, "realized_pnl": -450},
        settings(), session_active=True,
    )
    assert loss.net_pnl == -550
    assert loss.state == "LOSS LIMIT HIT"
    limit = calculate_algo_day_state(
        {"trades": 10, "closed_trades": 10, "open_trades": 0, "realized_pnl": 0},
        settings(options_algo_estimated_charges=0), session_active=True,
    )
    assert limit.state == "TRADE LIMIT HIT"


def test_algo_state_allows_only_one_open_position_and_requires_session():
    stopped = calculate_algo_day_state({}, settings(), session_active=False)
    assert stopped.state == "STOPPED"
    opened = calculate_algo_day_state(
        {"trades": 1, "closed_trades": 0, "open_trades": 1, "realized_pnl": 0},
        settings(), session_active=True,
    )
    assert opened.state == "MONITORING OPEN TRADE"
    assert not opened.allow_new_entry


def test_algo_state_deducts_estimated_slippage_as_friction():
    state = calculate_algo_day_state(
        {"trades": 2, "closed_trades": 2, "open_trades": 0, "realized_pnl": 1200},
        settings(options_algo_estimated_slippage=25), session_active=True,
    )
    assert state.estimated_slippage == 50
    assert state.net_pnl == 1050


def test_validation_metrics_are_cost_aware_and_require_evidence():
    rows = [
        {"status": "CLOSED", "pnl": 200}, {"status": "CLOSED", "pnl": -50},
        {"status": "OPEN", "pnl": None},
    ]
    result = calculate_validation_metrics(rows, settings(
        options_algo_estimated_slippage=10, options_algo_min_validation_trades=2,
        options_algo_min_validation_win_rate=50, options_algo_max_validation_drawdown=200,
    ))
    assert result.closed_trades == 2
    assert result.wins == 1
    assert result.win_rate == 50.0
    assert result.expectancy == 15.0
    assert result.max_drawdown == 110.0
    assert result.ready_for_review
