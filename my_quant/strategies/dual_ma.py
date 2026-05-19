"""双均线择时策略。"""
from __future__ import annotations

import pandas as pd

from my_quant.core.panel import Panel
from my_quant.core.strategy import Strategy


class DualMA(Strategy):
    """双均线择时：短均线在长均线之上 → 持有，否则空仓。

    每个标的独立判断；持有时权重 = 1/N（N 为标的总数），空仓时 0。
    单标的时权重在 {0, 1} 间切换，即经典单 ETF 双均线择时。

    防未来函数：均线用 rolling().mean()，第 D 行只用 ≤ D 的收盘价；引擎负责后移一日生效。
    """

    name = "dual_ma"

    def __init__(self, symbols: list[str], *, fast: int = 20, slow: int = 60) -> None:
        super().__init__(symbols)
        if fast >= slow:
            raise ValueError(f"fast({fast}) 必须小于 slow({slow})")
        self.fast = fast
        self.slow = slow

    def compute_weights(self, panel: Panel) -> pd.DataFrame:
        close = panel.close[self.symbols]
        fast_ma = close.rolling(self.fast).mean()
        slow_ma = close.rolling(self.slow).mean()
        # 暖机期均线为 NaN → 比较得 False → 信号 0。
        signal = (fast_ma > slow_ma).astype(float)
        return signal / len(self.symbols)
