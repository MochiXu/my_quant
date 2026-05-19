"""DataProvider 抽象基类。

每个数据类别（ohlcv / valuation / macro_* ...）实现一个 DataProvider。
P0 只有 ohlcv 一个实现；其余类别留作 P1+ 扩展点。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

import pandas as pd

from my_quant.data.results import FetchReport, FreshnessStatus


class DataProvider(ABC):
    """一个数据类别的统一接口：增量下载、读取、新鲜度检查。

    子类须设类属性 `category`（如 "ohlcv"），registry 以它为键登记。
    provider 只做编排（调数据源取数 → 调 store 落盘），不直接碰文件 IO。
    """

    category: str

    @abstractmethod
    def fetch(
        self,
        keys: list[str],
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> FetchReport:
        """增量下载 keys 指定的数据并落盘。单个 key 失败不影响其他。"""

    @abstractmethod
    def load(
        self,
        keys: list[str],
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> dict[str, pd.DataFrame]:
        """从本地 parquet 读取，返回 {key: DataFrame}。"""

    @abstractmethod
    def freshness(
        self,
        keys: list[str],
        *,
        asof: date | None = None,
    ) -> dict[str, FreshnessStatus]:
        """检查 keys 的数据是否已更新到最近交易日。"""
