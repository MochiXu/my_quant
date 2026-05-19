"""backtest/bt_engine.py 测试：backtrader 引擎 + 与向量化引擎交叉校验。

向量化引擎在连续权重空间工作；backtrader 引擎按整手成交、收最低佣金，更贴近真实。
两者用同一信号核，差异来自撮合（开盘成交、整手取整、佣金）——这正是双引擎的价值。
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from config.settings import SETTINGS, CostModel
from my_quant.backtest.bt_engine import run_bt_backtest
from my_quant.backtest.vector import run_backtest
from my_quant.strategies.buy_and_hold import BuyAndHold
from my_quant.strategies.dual_ma import DualMA
from tests.helpers import make_panel

ZERO_COST = replace(SETTINGS, cost=CostModel(commission_rate=0.0, commission_min=0.0,
                                             stamp_tax_rate=0.0, transfer_fee_rate=0.0,
                                             slippage_bps=0.0))


def _panel(values, start="2022-01-01"):
    close = pd.Series([float(v) for v in values],
                      index=pd.date_range(start, periods=len(values)))
    return make_panel({"A": close})


def test_bt_buy_and_hold_makes_money_in_uptrend():
    panel = _panel(np.linspace(5, 9, 250))
    result = run_bt_backtest(BuyAndHold(["A"]), panel, settings=ZERO_COST)

    assert result.final_value > result.initial_capital
    assert result.nav.is_monotonic_increasing


def test_bt_dual_ma_flat_in_downtrend():
    # 下跌趋势 → 信号恒 0 → 不建仓 → 组合市值恒为初始资金
    panel = _panel(np.linspace(9, 5, 250))
    result = run_bt_backtest(DualMA(["A"], fast=5, slow=20), panel, settings=SETTINGS)

    assert result.final_value == pytest.approx(result.initial_capital)


def test_bt_metrics_available():
    panel = _panel(np.linspace(5, 9, 250))
    result = run_bt_backtest(BuyAndHold(["A"]), panel, settings=ZERO_COST)
    assert result.metrics.n_periods == len(result.returns)
    assert result.metrics.total_return > 0


def test_bt_commission_reduces_final_value():
    panel = _panel(np.linspace(5, 9, 250))
    with_cost = run_bt_backtest(BuyAndHold(["A"]), panel, settings=SETTINGS)
    no_cost = run_bt_backtest(BuyAndHold(["A"]), panel, settings=ZERO_COST)

    assert with_cost.final_value < no_cost.final_value


def test_bt_lot_rounding_causes_cash_drag():
    # 高价标的（每手约 1.5 万）在 5 万账户里只能买 3 手，~10% 现金闲置 →
    # backtrader 收益明显低于忽略整手的向量化引擎。这是 P2 要暴露的真实摩擦。
    panel = _panel(np.linspace(150, 300, 250))
    vec = run_backtest(BuyAndHold(["A"]), panel, settings=ZERO_COST)
    bt = run_bt_backtest(BuyAndHold(["A"]), panel, settings=ZERO_COST)

    assert bt.metrics.total_return < vec.metrics.total_return


def test_cross_engine_buy_and_hold_agree():
    # 低价标的、恒定权重：整手残差极小 → 两引擎应高度一致
    panel = _panel(np.linspace(5, 9, 250))
    vec = run_backtest(BuyAndHold(["A"]), panel, settings=ZERO_COST)
    bt = run_bt_backtest(BuyAndHold(["A"]), panel, settings=ZERO_COST)

    assert bt.metrics.total_return == pytest.approx(vec.metrics.total_return, abs=0.03)


def test_cross_engine_dual_ma_same_ballpark():
    # 双均线低换手、低价标的：两引擎量级相近（差异来自开盘 vs 收盘成交）
    rng = np.random.default_rng(3)
    close = pd.Series(5 * np.exp(np.cumsum(rng.normal(0.0005, 0.012, 600))),
                      index=pd.date_range("2022-01-01", periods=600))
    panel = make_panel({"A": close})
    strat = DualMA(["A"], fast=10, slow=30)

    vec = run_backtest(strat, panel, settings=ZERO_COST)
    bt = run_bt_backtest(strat, panel, settings=ZERO_COST)

    assert bt.metrics.total_return == pytest.approx(vec.metrics.total_return, abs=0.15)


def test_bt_start_end_slicing():
    panel = _panel(np.linspace(5, 9, 400))
    result = run_bt_backtest(BuyAndHold(["A"]), panel, settings=ZERO_COST,
                             start="2022-03-01", end="2022-06-30")
    assert result.nav.index.min() >= pd.Timestamp("2022-03-01")
    assert result.nav.index.max() <= pd.Timestamp("2022-06-30")
