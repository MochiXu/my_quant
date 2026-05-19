"""OHLCV 落盘 schema 的单一定义来源。

负责把 akshare 返回的中文列 DataFrame 规整成框架统一的英文列格式，并校验。
存盘的 parquet 与从 parquet 读出的 DataFrame 都遵循这里定义的 schema。

主键：(date, symbol, adjust) —— 去重与增量合并的依据。
"""
from __future__ import annotations

import pandas as pd

from my_quant.core.types import AdjustType, SourceName

# akshare fund_etf_hist_em 中文列 → 框架英文列。
# 未列出的列（振幅、涨跌额）是派生量，回测可现算，不落盘以减小体积。
RENAME_MAP: dict[str, str] = {
    "日期": "date",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "成交额": "amount",
    "涨跌幅": "pct_change",
    "换手率": "turnover",
}

# 数值列：统一强制成 float64，保证跨文件、跨增量批次 dtype 稳定。
NUMERIC_COLUMNS: list[str] = [
    "open", "high", "low", "close",
    "volume", "amount", "pct_change", "turnover",
]

# normalize 时注入（非来自数据源）的列。
INJECTED_COLUMNS: list[str] = ["symbol", "adjust", "source", "updated_at"]

# 落盘 parquet 的完整列顺序。
OHLCV_COLUMNS: list[str] = [
    "date", "symbol", "adjust",
    "open", "high", "low", "close",
    "volume", "amount", "pct_change", "turnover",
    "source", "updated_at",
]

# 各列期望 dtype（参考用；validate_ohlcv 对数值列只校验「是数值」不卡精确类型）。
OHLCV_DTYPES: dict[str, str] = {
    "date": "datetime64[ns]",
    "symbol": "string",
    "adjust": "string",
    **{col: "float64" for col in NUMERIC_COLUMNS},
    "source": "string",
    "updated_at": "datetime64[ns]",
}

# 主键。
PRIMARY_KEY: list[str] = ["date", "symbol", "adjust"]


def normalize_akshare_ohlcv(
    raw_df: pd.DataFrame,
    *,
    symbol: str,
    adjust: AdjustType,
    source: SourceName = "akshare",
) -> pd.DataFrame:
    """把 akshare 原始 DataFrame 规整成框架 OHLCV schema。

    流程：重命名 → 注入 symbol/adjust/source/updated_at → 类型转换 → 选列 →
    按 date 排序 → 按主键去重（保留后者）→ 重置索引。

    Args:
        raw_df: ak.fund_etf_hist_em 的返回，中文列。
        symbol: 标的代码。
        adjust: 复权类型。
        source: 数据源名，默认 "akshare"。

    Returns:
        列为 OHLCV_COLUMNS、date 为普通列的 DataFrame。

    Raises:
        ValueError: raw_df 缺少必需的源列（日期或任一数值列）。
    """
    if "日期" not in raw_df.columns:
        raise ValueError(
            f"akshare 返回缺少 '日期' 列，symbol={symbol}：实际列 {list(raw_df.columns)}"
        )

    df = raw_df.rename(columns=RENAME_MAP).copy()

    missing = [c for c in NUMERIC_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"akshare 返回缺少数值列 {missing}，symbol={symbol}："
            f"实际列 {list(raw_df.columns)}"
        )

    df["symbol"] = symbol
    df["adjust"] = adjust
    df["source"] = source
    df["updated_at"] = pd.Timestamp.now()

    df["date"] = pd.to_datetime(df["date"])
    for col in NUMERIC_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")

    df = df[OHLCV_COLUMNS]
    df = (
        df.sort_values("date")
        .drop_duplicates(PRIMARY_KEY, keep="last")
        .reset_index(drop=True)
    )
    return df


def validate_ohlcv(df: pd.DataFrame) -> None:
    """校验 DataFrame 符合 OHLCV schema，不符立即抛错。

    在写盘前调用，杜绝坏数据落地。校验项：列集合与顺序、date 为时间类型、
    数值列为数值、主键唯一、date 升序。

    Raises:
        ValueError: 任一校验项不通过。
    """
    if list(df.columns) != OHLCV_COLUMNS:
        raise ValueError(
            f"OHLCV 列不符：期望 {OHLCV_COLUMNS}，实际 {list(df.columns)}"
        )

    if not pd.api.types.is_datetime64_any_dtype(df["date"]):
        raise ValueError(f"date 列应为 datetime，实际 {df['date'].dtype}")
    if not pd.api.types.is_datetime64_any_dtype(df["updated_at"]):
        raise ValueError(f"updated_at 列应为 datetime，实际 {df['updated_at'].dtype}")

    for col in NUMERIC_COLUMNS:
        if not pd.api.types.is_numeric_dtype(df[col]):
            raise ValueError(f"{col} 列应为数值，实际 {df[col].dtype}")

    dup = df.duplicated(PRIMARY_KEY)
    if dup.any():
        raise ValueError(f"主键 {PRIMARY_KEY} 有 {int(dup.sum())} 行重复")

    if not df["date"].is_monotonic_increasing:
        raise ValueError("date 列未按升序排列")
