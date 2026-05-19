"""买入持有基准策略。"""
from __future__ import annotations

import pandas as pd

from my_quant.core.panel import Panel
from my_quant.core.strategy import Strategy


class BuyAndHold(Strategy):
    """恒定目标权重基准：每个标的等权，逐日维持。

    单标的时即纯买入持有（始终满仓）；多标的时为「恒定混合」（再平衡回等权）。
    主要用作回测的对照基准。
    """

    name = "buy_and_hold"

    def compute_weights(self, panel: Panel) -> pd.DataFrame:
        close = panel.close[self.symbols]
        weight = 1.0 / len(self.symbols)
        weights = pd.DataFrame(weight, index=close.index, columns=self.symbols)
        # 标的尚未上市（close 为 NaN）的日期权重置 0。
        return weights.where(close.notna(), 0.0)
