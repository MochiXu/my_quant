"""框架通用的轻量类型定义。

P0 只需要数据层用到的类型；策略 / 订单 / 持仓等类型留待 P1+ 再加。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# 复权类型（adjustment type）：raw 原始 / qfq 前复权 / hfq 后复权。
AdjustType = Literal["raw", "qfq", "hfq"]

# 数据源名称。P0 只用 akshare；tushare 留作 P1+ 扩展点。
SourceName = Literal["akshare", "tushare"]

# 资产大类。P0 只覆盖 etf。
AssetClass = Literal["etf", "stock"]


@dataclass(frozen=True)
class FeatureRef:
    """一个特征引用：策略借此声明「我需要哪类数据的哪个 key」。

    frozen=True 让它可哈希，从而能放进 set 做并集去重——feature_store 把多个
    策略的数据需求合并时要用（design.md 第 7.2 节）。

    Args:
        category: 数据类别，对应 DataProvider.category，如 "ohlcv"。
        key: 该类别下的具体标识。对 ohlcv 即标的代码，如 "513100"。
    """

    category: str
    key: str
