"""ManualBroker：当前阶段的人工执行 broker。

持仓来自本地台账；下单不自动执行——只提示，由人按下单计划手动操作，
成交后再把实际成交回填进台账。
"""
from __future__ import annotations

from my_quant.core.portfolio import Order
from my_quant.live.broker.base import Broker
from my_quant.live.ledger import Ledger


class ManualBroker(Broker):
    """半自动 broker：持仓读自台账，下单交给人工。"""

    def __init__(self, ledger: Ledger) -> None:
        self.ledger = ledger

    def get_positions(self) -> dict[str, int]:
        return self.ledger.positions()

    def place_orders(self, orders: list[Order]) -> None:
        if not orders:
            print("[ManualBroker] 今日无需调仓。")
            return
        print(f"[ManualBroker] {len(orders)} 笔订单待人工执行——"
              f"请按下单计划在券商 App 操作，成交后回填台账（trades.csv）。")
