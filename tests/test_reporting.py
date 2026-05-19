"""reporting/ 测试：文本报告与图表。"""
from __future__ import annotations

import pandas as pd

from my_quant.backtest.vector import run_backtest
from my_quant.backtest.walk_forward import walk_forward
from my_quant.reporting.plot import plot_backtest
from my_quant.reporting.report import backtest_report, walk_forward_report
from my_quant.strategies.buy_and_hold import BuyAndHold
from my_quant.strategies.dual_ma import DualMA
from tests.helpers import make_panel


def _trend_panel():
    close = pd.Series([float(v) for v in range(1, 401)],
                      index=pd.date_range("2024-01-01", periods=400))
    return make_panel({"A": close})


def test_backtest_report_contains_metrics():
    panel = _trend_panel()
    result = run_backtest(DualMA(["A"], fast=10, slow=30), panel)
    benchmark = run_backtest(BuyAndHold(["A"]), panel)

    text = backtest_report(result, benchmark, title="测试报告")
    assert "测试报告" in text
    assert "夏普" in text
    assert "基准：buy_and_hold" in text
    assert "超额" in text


def test_walk_forward_report():
    n = 6 * 252
    close = pd.Series([100.0 + i * 0.1 for i in range(n)],
                      index=pd.date_range("2018-01-01", periods=n))
    panel = make_panel({"A": close})
    wf = walk_forward(
        panel,
        lambda p: DualMA(["A"], fast=p["fast"], slow=p["slow"]),
        [{"fast": 5, "slow": 20}, {"fast": 10, "slow": 30}],
        train_years=2, test_years=1,
    )
    text = walk_forward_report(wf, title="WF 报告")
    assert "WF 报告" in text
    assert "OOS" in text


def test_plot_backtest_saves_file(tmp_path):
    panel = _trend_panel()
    result = run_backtest(DualMA(["A"], fast=10, slow=30), panel)
    benchmark = run_backtest(BuyAndHold(["A"]), panel)

    out = plot_backtest(result, benchmark, output_path=tmp_path / "bt.png",
                        title="回测图")
    assert out.exists()
    assert out.stat().st_size > 0
