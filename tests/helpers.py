"""测试公用辅助（非测试文件，不被 pytest 收集）。"""
from __future__ import annotations

from datetime import date

import pandas as pd

from my_quant.core.panel import Panel


def akshare_df(days: list[date], close_base: float = 1.0) -> pd.DataFrame:
    """造一份 akshare fund_etf_hist_em 风格（中文列）的 DataFrame，覆盖给定交易日。"""
    n = len(days)
    closes = [round(close_base + i * 0.01, 4) for i in range(n)]
    return pd.DataFrame(
        {
            "日期": [d.isoformat() for d in days],
            "开盘": closes,
            "收盘": closes,
            "最高": [round(c + 0.05, 4) for c in closes],
            "最低": [round(c - 0.05, 4) for c in closes],
            "成交量": [1_000_000 + i for i in range(n)],
            "成交额": [1e8] * n,
            "振幅": [0.5] * n,
            "涨跌幅": [0.1] * n,
            "涨跌额": [0.001] * n,
            "换手率": [1.0] * n,
        }
    )


def make_panel(closes: dict[str, pd.Series]) -> Panel:
    """从 {标的: 收盘价序列} 造一个 Panel（OHLC 全取收盘价，volume 取常数）。"""
    data: dict[str, pd.DataFrame] = {}
    for symbol, close in closes.items():
        data[symbol] = pd.DataFrame(
            {"open": close, "high": close, "low": close, "close": close,
             "volume": 1_000_000.0},
        )
    return Panel(data)

