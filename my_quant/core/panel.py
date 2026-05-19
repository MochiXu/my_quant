"""行情面板：信号核（Strategy.compute_weights）的输入。

Panel 持有 {symbol: OHLCV DataFrame}（DatetimeIndex），并能取「宽表」——
以日期为行、标的为列的某个字段（如收盘价）矩阵，方便策略做截面运算。
"""
from __future__ import annotations

import pandas as pd


class Panel:
    """多标的行情面板。

    各标的的 DataFrame 上市日期可能不同；取宽表时按日期外连接对齐，缺失处为 NaN，
    由策略 / 回测引擎负责处理（暖机期、未上市）。
    """

    def __init__(self, data: dict[str, pd.DataFrame]) -> None:
        if not data:
            raise ValueError("Panel 数据为空")
        self._data = dict(data)

    @property
    def symbols(self) -> list[str]:
        """面板包含的标的代码。"""
        return list(self._data)

    def ohlcv(self, symbol: str) -> pd.DataFrame:
        """取单个标的的完整 OHLCV DataFrame。"""
        return self._data[symbol]

    def field(self, name: str) -> pd.DataFrame:
        """取某字段的宽表：index=日期、columns=标的，按日期外连接对齐。"""
        return pd.DataFrame({s: df[name] for s, df in self._data.items()}).sort_index()

    @property
    def close(self) -> pd.DataFrame:
        """收盘价宽表。"""
        return self.field("close")

    @property
    def index(self) -> pd.DatetimeIndex:
        """全体标的日期的并集（升序）。"""
        return self.close.index

    def slice(self, start=None, end=None) -> "Panel":
        """按日期区间裁剪，返回新 Panel（闭区间）。"""
        out: dict[str, pd.DataFrame] = {}
        for symbol, df in self._data.items():
            sub = df
            if start is not None:
                sub = sub.loc[pd.Timestamp(start):]
            if end is not None:
                sub = sub.loc[: pd.Timestamp(end)]
            out[symbol] = sub
        return Panel(out)

    def subset(self, symbols: list[str]) -> "Panel":
        """取标的子集，返回新 Panel。"""
        return Panel({s: self._data[s] for s in symbols})
