import pytest

from engine.pair_forward_test_engine import build_forward_test_plan, summarize_forward_test


def test_plan_sizes_minimum_lots_and_respects_capital():
    plan = build_forward_test_plan(
        ce_price=150, pe_price=149, lot_size=20, capital_limit=100000,
        daily_target_net=2000, estimated_costs=100, target_move_points=50, maximum_loss=2000,
    )
    assert plan["lots"] == 3
    assert plan["quantity"] == 60
    assert plan["capital_required"] == 17940
    assert plan["target_pnl_gross"] == 2100
    assert plan["target_move_points"] == 35


def test_plan_blocks_when_capital_ceiling_is_insufficient():
    with pytest.raises(ValueError, match="capital ceiling"):
        build_forward_test_plan(
            ce_price=500, pe_price=500, lot_size=100, capital_limit=1000,
            daily_target_net=2000, estimated_costs=100, target_move_points=50, maximum_loss=2000,
        )


def test_summary_uses_closed_paper_rows_and_deducts_estimated_costs():
    def row(mode, status, pnl, reason, costs=100):
        return {"mode": mode, "status": status, "last_pnl": pnl, "exit_reason": reason,
                "details_json": '{"estimated_costs": %s}' % costs}
    rows = [
        row("PAPER", "PAPER_CLOSED", 2100, "COMBINED TARGET HIT"),
        row("PAPER", "PAPER_CLOSED", -2000, "COMBINED MAX LOSS HIT"),
        row("PAPER", "PAPER_OPEN", 9999, ""),
        row("REAL", "PAPER_CLOSED", 9999, "COMBINED TARGET HIT"),
    ]
    result = summarize_forward_test(rows, required_sessions=30)
    assert result["closed_sessions"] == 2
    assert result["target_hit_rate"] == 50
    assert result["net_pnl"] == pytest.approx(-100)
    assert not result["real_review_eligible"]
