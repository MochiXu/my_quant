"""实盘每日流程：晚间生成次日下单计划。

加载最新行情 → 回放台账得当前持仓/现金 → 跑信号核取次日目标权重 → 算调仓订单 →
产出下单计划（CSV + 日报）。次日由人工照计划下单、回填台账。
"""
from __future__ import annotations

import pandas as pd

from config.settings import SETTINGS, Settings
from config.universe import UNIVERSE
from my_quant.core.panel import Panel
from my_quant.core.portfolio import compute_orders
from my_quant.core.strategy import Strategy
from my_quant.data.calendar import TradingCalendar, get_calendar
from my_quant.data.registry import ProviderRegistry
from my_quant.live.broker.base import Broker
from my_quant.live.broker.manual import ManualBroker
from my_quant.live.ledger import Ledger
from my_quant.live.order_plan import OrderPlan, build_order_plan


def load_live_panels(symbols: list[str], settings: Settings = SETTINGS) -> tuple[Panel, Panel]:
    """加载实盘所需的两个面板：hfq 供策略算信号、raw 供下单定价。"""
    provider = ProviderRegistry(settings).get("ohlcv")
    return (
        Panel(provider.load(symbols, adjust="hfq")),
        Panel(provider.load(symbols, adjust="raw")),
    )


def _latest_price(close: pd.DataFrame, symbol: str, asof: pd.Timestamp) -> float:
    series = close[symbol].loc[:asof].dropna()
    if series.empty:
        raise ValueError(f"{symbol} 在 {asof.date()} 及之前无价格数据")
    return float(series.iloc[-1])


def generate_daily_plan(
    strategy: Strategy,
    signal_panel: Panel,
    price_panel: Panel,
    *,
    settings: Settings = SETTINGS,
    broker: Broker | None = None,
    calendar: TradingCalendar | None = None,
    asof=None,
) -> OrderPlan:
    """生成次日下单计划。

    Args:
        signal_panel: hfq 面板，喂给策略算权重。
        price_panel: raw 面板，提供真实下单参考价。
        broker: 默认 ManualBroker（持仓读自本地台账）。
        calendar: 交易日历，用于推算执行日；默认加载。
        asof: 据以决策的收盘日；默认取信号面板最后一日。
    """
    ledger = Ledger(settings)
    broker = broker if broker is not None else ManualBroker(ledger)
    calendar = calendar if calendar is not None else get_calendar(settings)

    # 信号：hfq 面板算权重，取 asof 当日一行 = 次日目标权重。
    weights = strategy.compute_weights(signal_panel)
    asof_ts = pd.Timestamp(asof) if asof is not None else weights.index[-1]
    target = {s: float(weights.loc[asof_ts, s]) for s in weights.columns}

    # 定价：raw 面板上 asof 当日及以前最近收盘价。
    raw_close = price_panel.close
    prices = {s: _latest_price(raw_close, s, asof_ts) for s in strategy.symbols}

    positions = broker.get_positions()
    cash = ledger.cash()
    snapshot = ledger.snapshot(prices, asof=asof_ts.date())

    orders = compute_orders(
        target, positions, cash, prices,
        lot_size=settings.live.lot_size,
        no_trade_band=settings.live.no_trade_band,
    )

    trade_date = calendar.next_trading_day(asof_ts.date())
    symbols = sorted(set(strategy.symbols) | set(positions))
    names = {s: (UNIVERSE[s].name if s in UNIVERSE else s) for s in symbols}

    plan = build_order_plan(
        orders, prices=prices, names=names, snapshot=snapshot,
        target_weights=target, asof=asof_ts.date(), trade_date=trade_date,
        live=settings.live,
    )

    plan.write(settings.paths.live_dir / "plans")
    broker.place_orders(orders)
    return plan
