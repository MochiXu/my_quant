"""live/runner.py 测试：生成次日下单计划（离线）。"""
from __future__ import annotations

import numpy as np
import pandas as pd

from my_quant.live.ledger import Ledger
from my_quant.live.runner import generate_daily_plan
from my_quant.strategies.buy_and_hold import BuyAndHold
from my_quant.strategies.dual_ma import DualMA
from tests.helpers import make_panel


def _panel(symbols, values):
    """造一个面板：所有标的共用同一条收盘价序列，日期落在 mock_calendar 内。"""
    idx = pd.bdate_range("2024-01-02", periods=len(values))
    return make_panel({s: pd.Series([float(v) for v in values], index=idx)
                       for s in symbols})


def test_generate_plan_buys_from_cash(tmp_settings, mock_calendar):
    Ledger(tmp_settings).record_cash(date="2024-01-02", action="deposit",
                                     amount=100_000)
    panel = _panel(["510300"], np.linspace(5, 7, 60))

    plan = generate_daily_plan(
        BuyAndHold(["510300"]), panel, panel,
        settings=tmp_settings, calendar=mock_calendar,
    )

    assert len(plan.rows) == 1
    assert plan.rows[0].action == "buy"
    assert plan.snapshot.cash == 100_000.0
    assert plan.trade_date == mock_calendar.next_trading_day(panel.index[-1].date())


def test_generate_plan_writes_files(tmp_settings, mock_calendar):
    Ledger(tmp_settings).record_cash(date="2024-01-02", action="deposit",
                                     amount=100_000)
    panel = _panel(["510300"], np.linspace(5, 7, 60))

    plan = generate_daily_plan(
        BuyAndHold(["510300"]), panel, panel,
        settings=tmp_settings, calendar=mock_calendar,
    )

    plans_dir = tmp_settings.paths.live_dir / "plans"
    assert (plans_dir / f"{plan.trade_date}.md").exists()
    assert (plans_dir / f"orders_{plan.trade_date}.csv").exists()


def test_plan_snapshot_reflects_ledger_positions(tmp_settings, mock_calendar):
    ledger = Ledger(tmp_settings)
    ledger.record_cash(date="2024-01-02", action="deposit", amount=100_000)
    ledger.record_trade(date="2024-01-03", symbol="510300", action="buy",
                        shares=5000, price=5.0)
    panel = _panel(["510300"], np.linspace(5, 7, 60))

    plan = generate_daily_plan(
        BuyAndHold(["510300"]), panel, panel,
        settings=tmp_settings, calendar=mock_calendar,
    )

    assert len(plan.snapshot.positions) == 1
    assert plan.snapshot.positions[0].symbol == "510300"
    assert plan.snapshot.positions[0].shares == 5000


def test_dual_ma_downtrend_yields_no_buy(tmp_settings, mock_calendar):
    # 下跌趋势 → 双均线目标权重 0 → 即便有现金也不应产生买单
    Ledger(tmp_settings).record_cash(date="2024-01-02", action="deposit",
                                     amount=100_000)
    panel = _panel(["510300"], np.linspace(7, 5, 60))

    plan = generate_daily_plan(
        DualMA(["510300"], fast=3, slow=10), panel, panel,
        settings=tmp_settings, calendar=mock_calendar,
    )

    assert all(r.action != "buy" for r in plan.rows)
    assert plan.target_weights["510300"] == 0.0
