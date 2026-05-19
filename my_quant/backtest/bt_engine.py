"""backtrader 回测引擎。

事件驱动、逐笔撮合，比向量化引擎更贴近真实成交（开盘成交、最低佣金、整手取整）。
用途：对候选策略做上线前精细验证，并与向量化引擎交叉校验。

与向量化引擎共用同一份信号核（Strategy.compute_weights），只是把权重交给 backtrader
按 cheat-on-open 在次日开盘成交。
"""
from __future__ import annotations

from dataclasses import dataclass

import backtrader as bt
import pandas as pd

from config.settings import SETTINGS, Settings
from my_quant.backtest.bt_strategy import LOT_SIZE, MinFloorCommission, WeightStrategy
from my_quant.backtest.metrics import Metrics, compute_metrics
from my_quant.core.panel import Panel
from my_quant.core.strategy import Strategy


@dataclass
class BtBacktestResult:
    """backtrader 回测结果。

    字段与 vector.BacktestResult 的报告 / 绘图接口鸭子兼容（strategy_name / nav /
    returns / metrics / final_value / initial_capital）。
    """

    strategy_name: str
    equity: pd.Series      # 逐日组合市值
    nav: pd.Series         # 净值（equity / 初始资金）
    returns: pd.Series     # 日收益
    initial_capital: float

    @property
    def final_value(self) -> float:
        return float(self.equity.iloc[-1]) if len(self.equity) else self.initial_capital

    @property
    def metrics(self) -> Metrics:
        return compute_metrics(self.returns)


def run_bt_backtest(
    strategy: Strategy,
    panel: Panel,
    *,
    settings: Settings = SETTINGS,
    start=None,
    end=None,
    lot_size: int = LOT_SIZE,
) -> BtBacktestResult:
    """用 backtrader 跑回测。

    信号核在完整面板上算权重（指标暖机用全历史），再把数据与权重切到 [start, end]
    交给 backtrader 运行——与向量化引擎口径一致。
    """
    weights = strategy.compute_weights(panel)
    symbols = list(weights.columns)
    held = weights.shift(1)                       # 决策权重 → 次日生效

    work_panel = panel.subset(symbols)
    if start is not None or end is not None:
        work_panel = work_panel.slice(start, end)
    held = held.reindex(work_panel.index)

    cerebro = bt.Cerebro(cheat_on_open=True, stdstats=False)
    cerebro.broker.setcash(settings.initial_capital)
    cerebro.broker.addcommissioninfo(
        MinFloorCommission(
            commission=settings.cost.commission_rate,
            min_floor=settings.cost.commission_min,
        )
    )
    for symbol in symbols:
        cerebro.adddata(bt.feeds.PandasData(dataname=work_panel.ohlcv(symbol), name=symbol))
    cerebro.addstrategy(WeightStrategy, held_weights=held, lot_size=lot_size)

    bt_strat = cerebro.run()[0]

    equity = pd.Series(
        {pd.Timestamp(d): v for d, v in bt_strat.equity_curve}
    ).sort_index()
    nav = equity / settings.initial_capital
    returns = nav.pct_change().fillna(0.0)

    return BtBacktestResult(
        strategy_name=strategy.name,
        equity=equity,
        nav=nav,
        returns=returns,
        initial_capital=settings.initial_capital,
    )
