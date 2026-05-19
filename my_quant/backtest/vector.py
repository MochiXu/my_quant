"""向量化回测引擎。

把策略的目标权重时序套到标的收益上，算出组合净值。快，适合参数扫描 / walk-forward。

撮合简化（design.md 第 8 节）：
- 按收盘价成交，收盘到收盘计收益。
- 决策权重后移一日生效（held = weights.shift(1)），杜绝未来函数。
- 成本 = 换手率 × (佣金率 + 滑点)，换手率 = Σ|持有权重日变化|。
  不建模「最低 5 元佣金」（份额取整也不建模）——那是 backtrader 引擎的事。
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from config.settings import SETTINGS, Settings
from my_quant.backtest.metrics import Metrics, compute_metrics
from my_quant.core.panel import Panel
from my_quant.core.strategy import Strategy


@dataclass
class BacktestResult:
    """一次回测的完整结果。"""

    strategy_name: str
    weights: pd.DataFrame        # 策略输出的决策权重
    held_weights: pd.DataFrame   # 实际持有权重（决策权重后移一日）
    asset_returns: pd.DataFrame  # 各标的日收益
    gross_returns: pd.Series     # 扣成本前组合日收益
    costs: pd.Series             # 每日交易成本（占组合比例）
    turnover: pd.Series          # 每日换手率
    returns: pd.Series           # 扣成本后组合日收益（net）
    nav: pd.Series               # 净值曲线（累乘净收益）
    initial_capital: float

    @property
    def equity(self) -> pd.Series:
        """资金曲线 = 净值 × 初始资金。"""
        return self.nav * self.initial_capital

    @property
    def final_value(self) -> float:
        """期末资金。"""
        return float(self.equity.iloc[-1]) if len(self.equity) else self.initial_capital

    @property
    def metrics(self) -> Metrics:
        """绩效指标。"""
        return compute_metrics(self.returns)


def run_backtest(
    strategy: Strategy,
    panel: Panel,
    *,
    settings: Settings = SETTINGS,
    start=None,
    end=None,
) -> BacktestResult:
    """对单个策略跑向量化回测。

    策略在完整面板上算权重（指标暖机用到全部历史），最后再把结果切到评估窗口
    [start, end]，所以窗口起点的指标也是基于真实历史、不丢暖机。

    Args:
        start / end: 评估窗口（闭区间）。None 表示用全程。
    """
    weights = strategy.compute_weights(panel)
    symbols = list(weights.columns)
    close = panel.close[symbols].reindex(weights.index)

    asset_ret = close.pct_change(fill_method=None)
    held = weights.shift(1).fillna(0.0)              # 决策日 → 次日生效

    gross = (held * asset_ret).sum(axis=1)           # 全 NaN 行 → 0
    turnover = held.diff().abs().sum(axis=1)         # 首行 diff 为 NaN → 0
    cost_rate = settings.cost.commission_rate + settings.cost.slippage_bps / 1e4
    costs = turnover * cost_rate
    net = gross - costs

    frame = {
        "weights": weights, "held": held, "asset_ret": asset_ret,
        "gross": gross, "turnover": turnover, "costs": costs, "net": net,
    }
    if start is not None or end is not None:
        idx = net.index
        mask = pd.Series(True, index=idx)
        if start is not None:
            mask &= idx >= pd.Timestamp(start)
        if end is not None:
            mask &= idx <= pd.Timestamp(end)
        frame = {k: v[mask.values] for k, v in frame.items()}

    nav = (1.0 + frame["net"]).cumprod()

    return BacktestResult(
        strategy_name=strategy.name,
        weights=frame["weights"],
        held_weights=frame["held"],
        asset_returns=frame["asset_ret"],
        gross_returns=frame["gross"],
        costs=frame["costs"],
        turnover=frame["turnover"],
        returns=frame["net"],
        nav=nav,
        initial_capital=settings.initial_capital,
    )
