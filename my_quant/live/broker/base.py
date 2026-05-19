"""Broker 抽象：实盘执行的统一接口。

把「查持仓」「下订单」抽象出来，实盘 runner 不直接耦合具体券商。
当前只有 ManualBroker（人工执行）；接通券商 API 后实现新的 Broker 子类即可，
runner 一行不改。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from my_quant.core.portfolio import Order


class Broker(ABC):
    """券商接口抽象。"""

    @abstractmethod
    def get_positions(self) -> dict[str, int]:
        """返回当前持仓 {symbol: shares}。"""

    @abstractmethod
    def place_orders(self, orders: list[Order]) -> None:
        """提交订单。ManualBroker 仅提示人工执行；真实券商则调用 API 下单。"""
