"""live/ledger.py 测试：持仓台账回放。"""
from __future__ import annotations

import pytest

from my_quant.live.ledger import Ledger


def test_record_and_replay_positions(tmp_settings):
    ledger = Ledger(tmp_settings)
    ledger.record_trade(date="2024-01-02", symbol="A", action="buy",
                        shares=1000, price=10.0)
    ledger.record_trade(date="2024-01-05", symbol="A", action="sell",
                        shares=400, price=12.0)

    assert ledger.positions() == {"A": 600}


def test_cash_replay(tmp_settings):
    ledger = Ledger(tmp_settings)
    ledger.record_cash(date="2024-01-01", action="deposit", amount=100_000)
    ledger.record_trade(date="2024-01-02", symbol="A", action="buy",
                        shares=1000, price=10.0, fee=5.0)
    ledger.record_trade(date="2024-01-05", symbol="A", action="sell",
                        shares=500, price=12.0, fee=5.0)
    # 100000 - (10000+5) + (6000-5) = 95990
    assert ledger.cash() == pytest.approx(95_990.0)


def test_dividend_adds_cash(tmp_settings):
    ledger = Ledger(tmp_settings)
    ledger.record_cash(date="2024-01-01", action="deposit", amount=10_000)
    ledger.record_cash(date="2024-06-30", action="dividend", amount=120.0)
    assert ledger.cash() == pytest.approx(10_120.0)


def test_avg_cost_is_weighted(tmp_settings):
    ledger = Ledger(tmp_settings)
    ledger.record_trade(date="2024-01-02", symbol="A", action="buy",
                        shares=100, price=10.0)
    ledger.record_trade(date="2024-01-03", symbol="A", action="buy",
                        shares=100, price=20.0)
    # (100*10 + 100*20) / 200 = 15
    assert ledger.avg_costs()["A"] == pytest.approx(15.0)


def test_avg_cost_unchanged_by_sell(tmp_settings):
    ledger = Ledger(tmp_settings)
    ledger.record_trade(date="2024-01-02", symbol="A", action="buy",
                        shares=200, price=10.0)
    ledger.record_trade(date="2024-01-03", symbol="A", action="sell",
                        shares=100, price=99.0)
    assert ledger.avg_costs()["A"] == pytest.approx(10.0)


def test_snapshot(tmp_settings):
    ledger = Ledger(tmp_settings)
    ledger.record_cash(date="2024-01-01", action="deposit", amount=100_000)
    ledger.record_trade(date="2024-01-02", symbol="A", action="buy",
                        shares=1000, price=10.0)

    snap = ledger.snapshot({"A": 13.0})
    assert snap.cash == pytest.approx(90_000.0)
    assert snap.market_value == pytest.approx(13_000.0)
    assert snap.nav == pytest.approx(103_000.0)
    assert len(snap.positions) == 1
    assert snap.positions[0].weight == pytest.approx(13_000 / 103_000)


def test_empty_ledger_has_no_positions(tmp_settings):
    ledger = Ledger(tmp_settings)
    assert ledger.positions() == {}
    assert ledger.cash() == 0.0


def test_record_trade_rejects_bad_action(tmp_settings):
    with pytest.raises(ValueError, match="action"):
        Ledger(tmp_settings).record_trade(date="2024-01-02", symbol="A",
                                          action="hold", shares=1, price=1.0)


def test_record_cash_rejects_negative_amount(tmp_settings):
    with pytest.raises(ValueError, match="amount"):
        Ledger(tmp_settings).record_cash(date="2024-01-02", action="deposit",
                                         amount=-1.0)
