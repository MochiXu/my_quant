"""backtest/vector.py 测试：向量化回测引擎。"""
from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from config.settings import SETTINGS, CostModel
from my_quant.backtest.vector import run_backtest
from my_quant.strategies.buy_and_hold import BuyAndHold
from my_quant.strategies.dual_ma import DualMA
from tests.helpers import make_panel

ZERO_COST = replace(SETTINGS, cost=CostModel(commission_rate=0.0, commission_min=0.0,
                                             stamp_tax_rate=0.0, transfer_fee_rate=0.0,
                                             slippage_bps=0.0))


def _series(values, start="2024-01-01"):
    return pd.Series([float(v) for v in values],
                     index=pd.date_range(start, periods=len(values)))


def test_buy_and_hold_tracks_asset_return():
    # 收盘 10 → 12，零成本下买入持有净值应精确 = 12/10
    panel = make_panel({"A": _series([10, 11, 12])})
    result = run_backtest(BuyAndHold(["A"]), panel, settings=ZERO_COST)

    assert result.nav.iloc[-1] == pytest.approx(1.2)
    assert result.metrics.total_return == pytest.approx(0.2)
    assert result.gross_returns.iloc[1] == pytest.approx(0.1)


def test_held_weights_are_decision_weights_shifted():
    # 引擎把决策权重后移一日生效——这是防未来函数的核心
    panel = make_panel({"A": _series(range(1, 101))})
    result = run_backtest(DualMA(["A"], fast=3, slow=10), panel, settings=ZERO_COST)

    expected = result.weights.shift(1).fillna(0.0)
    pd.testing.assert_frame_equal(result.held_weights, expected)


def test_dual_ma_flat_in_downtrend():
    # 下跌趋势 → 信号恒 0 → 策略空仓 → 收益恒 0、净值恒 1、无成本
    panel = make_panel({"A": _series(range(100, 0, -1))})
    result = run_backtest(DualMA(["A"], fast=3, slow=10), panel, settings=SETTINGS)

    assert (result.returns == 0.0).all()
    assert result.nav.iloc[-1] == pytest.approx(1.0)
    assert (result.costs == 0.0).all()


def test_cost_charged_on_position_entry():
    # 买入持有：第 1 天建仓 → 换手率 1.0、计一次成本
    panel = make_panel({"A": _series([10, 11, 12])})
    result = run_backtest(BuyAndHold(["A"]), panel, settings=SETTINGS)

    cost_rate = SETTINGS.cost.commission_rate + SETTINGS.cost.slippage_bps / 1e4
    assert result.turnover.iloc[1] == pytest.approx(1.0)
    assert result.costs.iloc[1] == pytest.approx(cost_rate)
    assert result.returns.iloc[1] == pytest.approx(0.1 - cost_rate)


def test_start_end_slicing():
    panel = make_panel({"A": _series(range(1, 101))})
    result = run_backtest(BuyAndHold(["A"]), panel, settings=ZERO_COST,
                          start="2024-02-01", end="2024-02-10")

    assert result.returns.index.min() >= pd.Timestamp("2024-02-01")
    assert result.returns.index.max() <= pd.Timestamp("2024-02-10")


def test_final_value_scales_with_capital():
    panel = make_panel({"A": _series([10, 12])})
    result = run_backtest(BuyAndHold(["A"]), panel, settings=ZERO_COST)

    assert result.initial_capital == SETTINGS.initial_capital
    assert result.final_value == pytest.approx(SETTINGS.initial_capital * 1.2)


def test_two_asset_buy_and_hold_equal_weight():
    # A 翻倍、B 不变 → 等权组合收益 ≈ +50%
    panel = make_panel({"A": _series([10, 20]), "B": _series([10, 10])})
    result = run_backtest(BuyAndHold(["A", "B"]), panel, settings=ZERO_COST)

    assert result.metrics.total_return == pytest.approx(0.5)
