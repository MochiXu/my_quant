"""全局配置：路径、成本模型、数据层参数。

纯数据，无逻辑。所有路径从 Paths 派生——其他模块一律通过 SETTINGS 取路径，
不要自己拼 "data/raw/..." 这种字符串，保证路径只有一个事实源。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from my_quant.core.types import AdjustType, SourceName

# 标的数据文件缺失时的处理策略。
OnMissing = Literal["raise", "skip"]


@dataclass(frozen=True)
class CostModel:
    """交易成本模型（design.md 第 9 节）。

    P0 数据层用不到，先一次定到位，供 P1 回测引擎直接取用。
    """

    commission_rate: float = 0.0001   # 佣金费率，双边，万分之一
    commission_min: float = 5.0       # 单笔最低佣金，5 元
    stamp_tax_rate: float = 0.0       # 印花税：ETF 免（个股卖出千一，留作扩展）
    transfer_fee_rate: float = 0.0    # 过户费：ETF 通常免
    slippage_bps: float = 2.0         # 滑点，按 bps（基点）简化


@dataclass(frozen=True)
class Paths:
    """项目内所有目录路径。由 default() 从本文件位置推算，禁止硬编码。"""

    project_root: Path
    data_dir: Path
    raw_dir: Path        # 行情 / 特征库 parquet 根目录
    live_dir: Path       # 实盘台账与下单计划（P3）
    meta_dir: Path       # 元数据缓存，如交易日历

    @classmethod
    def default(cls) -> "Paths":
        # config/settings.py 位于 <project_root>/config/ 下。
        root = Path(__file__).resolve().parent.parent
        data = root / "data"
        return cls(
            project_root=root,
            data_dir=data,
            raw_dir=data / "raw",
            live_dir=data / "live",
            meta_dir=data / "raw" / "_meta",
        )


@dataclass(frozen=True)
class Settings:
    """框架全局配置单例。测试可构造覆盖实例传入各模块。"""

    initial_capital: float = 50_000.0                       # 初始资金（design.md 第 12 节）
    cost: CostModel = field(default_factory=CostModel)
    paths: Paths = field(default_factory=Paths.default)

    # 数据层
    default_adjust: AdjustType = "hfq"                      # 回测 / 信号默认后复权
    adjust_types: tuple[AdjustType, ...] = ("raw", "hfq")   # 落盘的复权种类（不含 qfq）
    history_start: str = "2015-01-01"                       # 首次全量下载起点
    enabled_categories: tuple[str, ...] = ("ohlcv",)        # 启用的数据类别
    ohlcv_default_source: SourceName = "akshare"
    on_missing: OnMissing = "raise"

    # 下载重试
    fetch_max_retries: int = 3
    fetch_sleep_seconds: int = 5


# 模块级单例：常规代码 `from config.settings import SETTINGS` 直接用。
SETTINGS = Settings()
