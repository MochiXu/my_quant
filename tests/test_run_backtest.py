"""scripts/run_backtest.py 测试：CLI 编排（离线，用合成面板）。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts import run_backtest
from tests.helpers import make_panel


@pytest.fixture
def offline_backtest(monkeypatch, tmp_settings):
    """把 run_backtest 接到临时报告目录 + 合成面板，使其离线可跑。"""
    monkeypatch.setattr(run_backtest, "SETTINGS", tmp_settings)

    n = 6 * 252
    rng = np.random.default_rng(11)
    close = pd.Series(
        100 * np.exp(np.cumsum(rng.normal(0.0004, 0.012, n))),
        index=pd.date_range("2018-01-01", periods=n),
    )
    panel = make_panel({"A": close})
    monkeypatch.setattr(run_backtest, "_load_panel", lambda symbols, adjust: panel)
    return run_backtest


def test_run_backtest_dual_ma(offline_backtest, tmp_settings):
    rc = offline_backtest.main(["--symbols", "A", "--fast", "10", "--slow", "30"])
    assert rc == 0
    chart = tmp_settings.paths.reports_dir / "backtest_dual_ma_A.png"
    assert chart.exists()


def test_run_backtest_buy_and_hold(offline_backtest, tmp_settings):
    rc = offline_backtest.main(["--symbols", "A", "--strategy", "buy_and_hold"])
    assert rc == 0
    assert (tmp_settings.paths.reports_dir / "backtest_buy_and_hold_A.png").exists()


def test_run_backtest_walk_forward(offline_backtest):
    rc = offline_backtest.main(["--symbols", "A", "--walk-forward",
                                "--train-years", "2", "--test-years", "1"])
    assert rc == 0
