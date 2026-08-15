"""Default table order of the dashboard = the LLM column.

Rows with an LLM verdict come first, ranked by verdict tier, then whether the
price is at or below the entry price, then reward/risk weighted by conviction.
Rows without an LLM verdict follow, however large their model margins are.
"""

from invest.dashboard_components.html_generator import HTMLGenerator


def _llm(verdict, ev, entry, conviction="MEDIUM", bear=-25.0, price=100.0):
    return {
        "fair_value": price * (1 + ev / 100),
        "current_price": price,
        "details": {
            "verdict": verdict,
            "expected_value_pct": ev,
            "entry_price": entry,
            "conviction": conviction,
            "quality_score": 18,
            "scenarios": {
                "bull": {"prob": 0.25, "return_pct": ev * 2},
                "base": {"prob": 0.5, "return_pct": ev},
                "bear": {"prob": 0.25, "return_pct": bear},
            },
        },
    }


def _stock(price, valuations, status="completed"):
    return {"status": status, "current_price": price, "valuations": valuations}


def test_default_order_is_llm_column(tmp_path):
    gen = HTMLGenerator(output_dir=str(tmp_path))
    stocks = {
        # BUY, price already above entry: a wait, not a buy
        "RAN_PAST": _stock(150.0, {"llm_deep_analysis": _llm("BUY", 150, entry=90.0, conviction="HIGH", price=150.0)}),
        # BUY, price below entry: actionable now
        "BELOW_ENTRY": _stock(95.0, {"llm_deep_analysis": _llm("BUY", 24, entry=100.0, conviction="MEDIUM-HIGH", price=95.0)}),
        "WATCHER": _stock(50.0, {"llm_deep_analysis": _llm("WATCH", 10, entry=45.0, price=50.0)}),
        "PASSER": _stock(50.0, {"llm_deep_analysis": _llm("PASS", -20, entry=30.0, price=50.0)}),
        # No LLM verdict, absurd model margin: must not float to the top
        "BROKEN_RIM": _stock(2.0, {"rim": {"fair_value": 999.0, "margin_of_safety": 445.0}}),
        "NO_LLM_OK": _stock(30.0, {"dcf": {"fair_value": 40.0, "margin_of_safety": 0.33}}),
    }
    order = [t for t, _ in gen._sort_stocks_for_display(stocks)]
    assert order == ["BELOW_ENTRY", "RAN_PAST", "WATCHER", "PASSER", "BROKEN_RIM", "NO_LLM_OK"]


def test_score_components():
    buy_below = _llm("BUY", 24, entry=100.0, conviction="MEDIUM-HIGH", price=95.0)
    buy_above = _llm("BUY", 24, entry=100.0, conviction="MEDIUM-HIGH", price=105.0)
    assert HTMLGenerator.llm_entry_actionable(buy_below, 95.0) is True
    assert HTMLGenerator.llm_entry_actionable(buy_above, 105.0) is False
    assert HTMLGenerator.llm_entry_actionable(buy_above, None) is None
    below = HTMLGenerator.llm_risk_adjusted_score(buy_below, 95.0)
    above = HTMLGenerator.llm_risk_adjusted_score(buy_above, 105.0)
    assert below - above == 50  # only the actionable bonus differs
    assert HTMLGenerator.llm_risk_adjusted_score({}, 10.0) is None
    # a near-zero bear case cannot blow the ratio up: |bear| clamped to 10, ratio capped at 10
    tiny_bear = _llm("BUY", 30, entry=120.0, conviction="HIGH", bear=-2.0, price=119.0)
    assert HTMLGenerator.llm_risk_adjusted_score(tiny_bear, 119.0) == 100 + 50 + 3.0 * 1.9


def test_llm_cell_marks_entry_state(tmp_path):
    gen = HTMLGenerator(output_dir=str(tmp_path))
    below = gen._format_llm_cell(_llm("BUY", 24, entry=100.0, price=95.0), 95.0, "X")
    above = gen._format_llm_cell(_llm("BUY", 24, entry=100.0, price=105.0), 105.0, "X")
    assert "Price at or below entry" in below
    assert "Price above entry" in above
    assert 'data-sort-value="' in below
