"""目标权重 → 下单清单。

把策略输出的目标权重，结合当前持仓 / 现金 / 现价，换算成「买卖多少股」的订单。
处理整手取整与无交易带（偏离过小不调仓）。这是实盘出单与回测下单的共用逻辑。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Order:
    """一笔调仓订单。"""

    symbol: str
    action: str          # "buy" 或 "sell"
    shares: int          # 正整数，lot_size 的整数倍
    reason: str = ""     # 生成理由，写进下单计划


def compute_orders(
    target_weights: dict[str, float],
    positions: dict[str, int],
    cash: float,
    prices: dict[str, float],
    *,
    lot_size: int = 100,
    no_trade_band: float = 0.05,
) -> list[Order]:
    """由目标权重算出调仓订单。

    NAV = 现金 + Σ 持仓市值。逐标的：目标市值 = NAV × 目标权重 → 整手取整得目标股数 →
    与当前股数之差即订单。目标权重与当前权重偏离小于 no_trade_band 的标的跳过。

    Args:
        target_weights: {标的: 目标权重}，权重和应 ≤ 1。
        positions: {标的: 当前持股数}。
        cash: 当前现金。
        prices: {标的: 现价}，用于估值与定股数。
        lot_size: 最小交易单位（份/手）。
        no_trade_band: 无交易带阈值。

    Returns:
        Order 列表（按标的代码排序）。
    """
    market_value = sum(
        positions.get(s, 0) * prices[s] for s in positions if s in prices
    )
    nav = cash + market_value

    orders: list[Order] = []
    for symbol in sorted(set(target_weights) | set(positions)):
        price = prices.get(symbol)
        if price is None or price <= 0 or nav <= 0:
            continue

        cur_shares = positions.get(symbol, 0)
        cur_weight = cur_shares * price / nav
        tgt_weight = target_weights.get(symbol, 0.0)

        if abs(tgt_weight - cur_weight) < no_trade_band:
            continue

        tgt_shares = int(nav * tgt_weight / (price * lot_size)) * lot_size
        delta = tgt_shares - cur_shares
        if delta == 0:
            continue

        orders.append(
            Order(
                symbol=symbol,
                action="buy" if delta > 0 else "sell",
                shares=abs(delta),
                reason=f"目标 {tgt_weight:.0%} / 当前 {cur_weight:.0%}",
            )
        )
    return orders
