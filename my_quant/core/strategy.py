"""Strategy 信号核基类。

策略是纯粹的「数据 → 目标权重」计算，不碰券商、不碰下单。同一个策略被向量化引擎、
backtrader 引擎、实盘 runner 三处复用（design.md 第 2 节）。

防未来函数契约：`compute_weights` 返回的 weight_df，第 D 行只能用 ≤ D 的数据算出，
代表「D 收盘决策、D+1 起持有」的目标仓位。回测引擎负责把权重后移一日生效。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from my_quant.core.panel import Panel
from my_quant.core.types import FeatureRef


class Strategy(ABC):
    """策略信号核基类。

    子类通常只需实现 `compute_weights`；`__init__` 负责接收标的池，
    `required_data` 默认声明每个标的的 ohlcv（需要估值 / 宏观的策略可覆盖）。
    """

    name: str = "strategy"

    def __init__(self, symbols: list[str]) -> None:
        if not symbols:
            raise ValueError("策略至少需要一个标的")
        self.symbols: list[str] = list(symbols)

    def required_data(self) -> list[FeatureRef]:
        """声明数据需求。默认每个标的的 ohlcv。"""
        return [FeatureRef("ohlcv", s) for s in self.symbols]

    @abstractmethod
    def compute_weights(self, panel: Panel) -> pd.DataFrame:
        """计算目标权重时序。

        Returns:
            DataFrame，index 为日期，columns 为标的，值为目标权重。
            每行权重和 ≤ 1.0，剩余为现金。第 D 行只能用 ≤ D 的数据。
        """
