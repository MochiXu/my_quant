"""backtest/metrics.py 测试。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from my_quant.backtest import metrics


def _returns(values):
    return pd.Series([float(v) for v in values],
                     index=pd.date_range("2024-01-01", periods=len(values)))


def test_total_return():
    # nav: 1 -> 1.1 -> 0.99
    r = _returns([0.1, -0.1])
    assert metrics.total_return(r) == pytest.approx(-0.01)


def test_max_drawdown():
    r = _returns([0.1, -0.1])  # nav 1.1 后跌到 0.99 → 回撤 0.99/1.1-1
    assert metrics.max_drawdown(r) == pytest.approx(0.99 / 1.1 - 1.0)


def test_max_drawdown_monotonic_up_is_zero():
    r = _returns([0.01] * 50)  # 单调上涨，无回撤
    assert metrics.max_drawdown(r) == pytest.approx(0.0)


def test_annual_volatility_constant_returns_is_zero():
    r = _returns([0.01] * 100)  # 恒定收益 → 波动 0
    assert metrics.annual_volatility(r) == pytest.approx(0.0)


def test_sharpe_zero_when_no_volatility():
    r = _returns([0.01] * 100)
    assert metrics.sharpe_ratio(r) == 0.0  # 波动为 0 时安全返回 0


def test_sharpe_positive_for_positive_drift():
    rng = np.random.default_rng(42)
    r = pd.Series(rng.normal(0.001, 0.01, 500),
                  index=pd.date_range("2024-01-01", periods=500))
    assert metrics.sharpe_ratio(r) > 0


def test_cagr_one_year_of_constant_growth():
    # 252 天、每天 +0.1% → 年化 ≈ 1.001**252 - 1
    r = _returns([0.001] * 252)
    expected = 1.001 ** 252 - 1
    assert metrics.cagr(r) == pytest.approx(expected, rel=1e-6)


def test_win_rate_ignores_zero_days():
    r = _returns([0.01, -0.01, 0.0, 0.0, 0.02])  # 3 个非零日，2 胜
    assert metrics.win_rate(r) == pytest.approx(2 / 3)


def test_calmar_zero_without_drawdown():
    r = _returns([0.01] * 50)
    assert metrics.calmar_ratio(r) == 0.0


def test_compute_metrics_assembles_all():
    r = _returns([0.01, -0.02, 0.03, -0.01, 0.02])
    m = metrics.compute_metrics(r)
    assert m.n_periods == 5
    assert m.total_return == pytest.approx(metrics.total_return(r))
    assert set(m.as_dict()) == {
        "total_return", "cagr", "annual_volatility", "sharpe",
        "max_drawdown", "calmar", "win_rate", "n_periods",
    }


def test_empty_returns_safe():
    r = pd.Series([], dtype=float)
    m = metrics.compute_metrics(r)
    assert m.total_return == 0.0
    assert m.sharpe == 0.0
    assert m.max_drawdown == 0.0
