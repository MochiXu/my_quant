"""backtest/walk_forward.py 测试。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from my_quant.backtest.walk_forward import walk_forward
from my_quant.strategies.dual_ma import DualMA
from tests.helpers import make_panel

_GRID = [{"fast": 5, "slow": 20}, {"fast": 10, "slow": 30}, {"fast": 20, "slow": 60}]


def _factory(params):
    return DualMA(["A"], fast=params["fast"], slow=params["slow"])


@pytest.fixture
def long_panel():
    """6 年合成日线数据（含波动的上行随机游走）。"""
    n = 6 * 252
    rng = np.random.default_rng(7)
    steps = rng.normal(0.0004, 0.012, n)
    close = pd.Series(100 * np.exp(np.cumsum(steps)),
                      index=pd.date_range("2018-01-01", periods=n))
    return make_panel({"A": close})


def test_walk_forward_produces_segments(long_panel):
    result = walk_forward(long_panel, _factory, _GRID, train_years=2, test_years=1)

    assert len(result.segments) >= 2
    assert len(result.oos_returns) > 0
    assert {"train_start", "test_start", "params", "oos_return"}.issubset(
        result.segments.columns
    )


def test_walk_forward_picks_params_from_grid(long_panel):
    result = walk_forward(long_panel, _factory, _GRID, train_years=2, test_years=1)
    for params in result.segments["params"]:
        assert params in _GRID


def test_walk_forward_oos_returns_continuous_and_sorted(long_panel):
    result = walk_forward(long_panel, _factory, _GRID, train_years=2, test_years=1)
    idx = result.oos_returns.index
    assert idx.is_monotonic_increasing
    assert not idx.has_duplicates


def test_walk_forward_metrics_available(long_panel):
    result = walk_forward(long_panel, _factory, _GRID, train_years=2, test_years=1)
    assert result.metrics.n_periods == len(result.oos_returns)


def test_walk_forward_empty_grid_raises(long_panel):
    with pytest.raises(ValueError, match="param_grid"):
        walk_forward(long_panel, _factory, [], train_years=2, test_years=1)


def test_walk_forward_insufficient_data_raises():
    panel = make_panel({"A": pd.Series(
        [float(i) for i in range(1, 101)],
        index=pd.date_range("2024-01-01", periods=100))})
    with pytest.raises(ValueError, match="数据不足"):
        walk_forward(panel, _factory, _GRID, train_years=4, test_years=1)
