"""strategies/ 测试：buy_and_hold 与 dual_ma。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from my_quant.core.types import FeatureRef
from my_quant.strategies.buy_and_hold import BuyAndHold
from my_quant.strategies.dual_ma import DualMA
from tests.helpers import make_panel


def _series(values, start="2024-01-01"):
    return pd.Series([float(v) for v in values],
                     index=pd.date_range(start, periods=len(values)))


# —— BuyAndHold ——

def test_buy_and_hold_single_symbol_full_weight():
    panel = make_panel({"A": _series([1, 2, 3])})
    weights = BuyAndHold(["A"]).compute_weights(panel)
    assert (weights["A"] == 1.0).all()


def test_buy_and_hold_two_symbols_equal_weight():
    panel = make_panel({"A": _series([1, 2, 3]), "B": _series([1, 2, 3])})
    weights = BuyAndHold(["A", "B"]).compute_weights(panel)
    assert (weights == 0.5).all().all()


def test_buy_and_hold_zero_weight_before_listing():
    a = _series([1, 2, 3], start="2024-01-01")
    b = pd.Series([np.nan, 2.0, 3.0], index=a.index)  # 首日未上市
    panel = make_panel({"A": a, "B": b})
    weights = BuyAndHold(["A", "B"]).compute_weights(panel)
    assert weights["B"].iloc[0] == 0.0
    assert weights["B"].iloc[1] == 0.5


# —— DualMA ——

def test_dual_ma_rejects_fast_ge_slow():
    with pytest.raises(ValueError, match="fast"):
        DualMA(["A"], fast=10, slow=10)


def test_dual_ma_uptrend_holds_after_warmup():
    panel = make_panel({"A": _series(range(1, 101))})  # 严格上涨
    weights = DualMA(["A"], fast=3, slow=10).compute_weights(panel)
    # 前 9 行 slow_ma 为 NaN（暖机）→ 0
    assert (weights["A"].iloc[:9] == 0.0).all()
    # 暖机后上涨趋势中 fast_ma > slow_ma → 满仓 1.0
    assert (weights["A"].iloc[10:] == 1.0).all()


def test_dual_ma_downtrend_stays_flat():
    panel = make_panel({"A": _series(range(100, 0, -1))})  # 严格下跌
    weights = DualMA(["A"], fast=3, slow=10).compute_weights(panel)
    assert (weights["A"] == 0.0).all()


def test_dual_ma_two_symbols_split_weight():
    panel = make_panel({"A": _series(range(1, 101)), "B": _series(range(1, 101))})
    weights = DualMA(["A", "B"], fast=3, slow=10).compute_weights(panel)
    # 两标的同时持有 → 各 0.5
    assert (weights.iloc[20:] == 0.5).all().all()


def test_dual_ma_no_lookahead_warmup_is_zero():
    # 暖机期（不足 slow 根）权重必须为 0，确认没有偷看未来
    panel = make_panel({"A": _series(range(1, 31))})
    weights = DualMA(["A"], fast=5, slow=20).compute_weights(panel)
    assert (weights["A"].iloc[:19] == 0.0).all()


# —— 基类 ——

def test_required_data_declares_ohlcv():
    refs = DualMA(["513100", "510300"]).required_data()
    assert set(refs) == {FeatureRef("ohlcv", "513100"), FeatureRef("ohlcv", "510300")}


def test_strategy_rejects_empty_symbols():
    with pytest.raises(ValueError, match="至少"):
        BuyAndHold([])
