"""Walk-forward 回测：滚动「训练窗选参 → 测试窗验证」。

为什么需要：在全样本上扫参挑最优是「拿答案对答案」，业绩被严重高估。walk-forward
只用训练窗的历史选参，在紧随其后、从未参与选参的测试窗上跑——拼接各测试窗的收益，
才是「真实可执行」的策略业绩。

防未来函数：策略的指标（如均线）是因果的，在完整面板上算权重再切窗口，与只在窗口内
算结果一致；参数仅由训练窗业绩选出，测试窗收益是真正的样本外（OOS）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

from config.settings import SETTINGS, Settings
from my_quant.backtest.metrics import Metrics, compute_metrics
from my_quant.backtest.vector import BacktestResult, run_backtest
from my_quant.core.panel import Panel
from my_quant.core.strategy import Strategy

# 由一组参数构造策略实例。
StrategyFactory = Callable[[dict], Strategy]
# 给一次回测结果打分，分数越高越优。
ScoreFn = Callable[[BacktestResult], float]


@dataclass
class WalkForwardResult:
    """walk-forward 的拼接结果。"""

    segments: pd.DataFrame   # 每个窗口：训练/测试范围、选中参数、训练分、OOS 收益
    oos_returns: pd.Series   # 各测试窗拼接的 OOS 日收益
    oos_nav: pd.Series       # OOS 净值曲线

    @property
    def metrics(self) -> Metrics:
        """OOS 整体绩效。"""
        return compute_metrics(self.oos_returns)


def _default_score(result: BacktestResult) -> float:
    return result.metrics.sharpe


def walk_forward(
    panel: Panel,
    strategy_factory: StrategyFactory,
    param_grid: list[dict],
    *,
    train_years: int = 4,
    test_years: int = 1,
    settings: Settings = SETTINGS,
    score_fn: ScoreFn | None = None,
) -> WalkForwardResult:
    """滚动 walk-forward 回测。

    每个窗口：在 [train_start, train_end] 上对 param_grid 逐一回测打分，选最优参数，
    再在紧随的 [test_start, test_end] 上跑 OOS。窗口按 test_years 步长向前滚动。

    Args:
        strategy_factory: 参数字典 → Strategy 实例。
        param_grid: 待扫描的参数字典列表。
        score_fn: 训练窗打分函数，默认用夏普比率。

    Raises:
        ValueError: param_grid 为空，或数据不足以构成一个窗口。
    """
    if not param_grid:
        raise ValueError("param_grid 为空")
    score_fn = score_fn or _default_score

    index = panel.index
    data_start, data_end = index[0], index[-1]

    segment_rows: list[dict] = []
    oos_parts: list[pd.Series] = []

    train_start = data_start
    while True:
        train_end = train_start + pd.DateOffset(years=train_years)
        test_start = train_end + pd.Timedelta(days=1)
        test_end = min(train_end + pd.DateOffset(years=test_years), data_end)
        if train_end > data_end or test_start > data_end:
            break

        # 1) 训练窗扫参选优
        best_params: dict | None = None
        best_score = float("-inf")
        for params in param_grid:
            train_res = run_backtest(
                strategy_factory(params), panel,
                settings=settings, start=train_start, end=train_end,
            )
            score = score_fn(train_res)
            if score > best_score:
                best_score, best_params = score, params

        # 2) 测试窗跑 OOS
        oos_res = run_backtest(
            strategy_factory(best_params), panel,
            settings=settings, start=test_start, end=test_end,
        )
        if len(oos_res.returns) > 0:
            oos_parts.append(oos_res.returns)
            segment_rows.append({
                "train_start": train_start.date(),
                "train_end": train_end.date(),
                "test_start": oos_res.returns.index[0].date(),
                "test_end": oos_res.returns.index[-1].date(),
                "params": best_params,
                "train_score": round(best_score, 4),
                "oos_return": round(oos_res.metrics.total_return, 4),
            })

        train_start = train_start + pd.DateOffset(years=test_years)

    if not oos_parts:
        raise ValueError("数据不足以构成一个 walk-forward 窗口")

    oos_returns = pd.concat(oos_parts).sort_index()
    oos_nav = (1.0 + oos_returns).cumprod()

    return WalkForwardResult(
        segments=pd.DataFrame(segment_rows),
        oos_returns=oos_returns,
        oos_nav=oos_nav,
    )
