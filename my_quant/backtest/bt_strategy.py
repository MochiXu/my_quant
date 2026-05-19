"""把信号核包装成 backtrader 策略。

WeightStrategy 不自己算信号——它拿到预先算好的「持有权重时序」（held_weights，
已是决策权重后移一日的结果），在每个交易日开盘把仓位调到目标权重对应的整手股数。

这样 backtrader 引擎与向量化引擎用的是同一份 compute_weights 输出，策略行为不会
因引擎而漂移；两者差异只来自撮合（开盘成交、佣金、整手取整）。
"""
from __future__ import annotations

import backtrader as bt
import pandas as pd

# A 股 ETF 最小交易单位：100 份/手。
LOT_SIZE = 100


class MinFloorCommission(bt.CommInfoBase):
    """带「单笔最低佣金」的佣金方案。

    backtrader 原生 setcommission 只支持纯比例，不支持最低 5 元下限，故自定义。
    """

    params = dict(
        commission=0.0001,            # 佣金比例
        min_floor=5.0,                # 单笔最低佣金
        stocklike=True,
        commtype=bt.CommInfoBase.COMM_PERC,
        percabs=True,                 # commission 为绝对比例（非百分数）
    )

    def _getcommission(self, size, price, pseudoexec):
        if size == 0:
            return 0.0
        return max(abs(size) * price * self.p.commission, self.p.min_floor)


class WeightStrategy(bt.Strategy):
    """按预算好的目标权重时序，每日开盘再平衡到整手股数。

    params:
        held_weights: DataFrame，index=日期、columns=标的，已后移一日的持有权重。
        lot_size: 最小交易单位（份/手）。
    """

    params = dict(held_weights=None, lot_size=LOT_SIZE)

    def __init__(self) -> None:
        self._held: pd.DataFrame = self.p.held_weights
        self._data_by_name: dict[str, bt.AbstractDataBase] = {
            d._name: d for d in self.datas
        }
        # 逐日记录组合市值，回测后用来还原净值曲线。
        self.equity_curve: list[tuple] = []

    def next_open(self) -> None:
        """开盘前用「上一收盘的决策」把仓位调到目标整手股数（cheat-on-open）。"""
        ts = pd.Timestamp(self.datas[0].datetime.date(0))
        if ts not in self._held.index:
            return
        row = self._held.loc[ts]
        portfolio_value = self.broker.getvalue()

        for name, data in self._data_by_name.items():
            weight = row.get(name, 0.0)
            if weight is None or pd.isna(weight):
                weight = 0.0
            price = data.open[0]
            if price <= 0:
                continue
            # 目标市值 → 整手股数（向下取整到 lot_size 的整数倍）。
            lots = int((portfolio_value * weight) / (price * self.p.lot_size))
            self.order_target_size(data, target=lots * self.p.lot_size)

    def next(self) -> None:
        """收盘记录组合市值。"""
        self.equity_curve.append(
            (self.datas[0].datetime.date(0), self.broker.getvalue())
        )
