"""parquet 行情仓库：路径管理、读写、增量下载、新鲜度检查。

本模块是唯一直接碰文件系统的数据层组件。所有路径从 settings 派生。

增量策略：parquet 不支持就地 append，故用「读出 → 拼接 → 去重 → 整文件重写」。
ETF 单文件十年约 2500 行、几十 KB，重写代价可忽略，换来去重 / 排序 / 校验的简单可靠。
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Callable

import pandas as pd

from config.settings import SETTINGS, Settings
from my_quant.core.types import AdjustType, AssetClass, SourceName
from my_quant.data.calendar import TradingCalendar
from my_quant.data.results import FreshnessStatus, KeyFetchResult
from my_quant.data.schema import (
    PRIMARY_KEY,
    normalize_akshare_ohlcv,
    validate_ohlcv,
)

# fetch_fn：provider 传入的取数回调，签名 (symbol, adjust, start, end) -> 原始 DataFrame。
FetchFn = Callable[[str, AdjustType, date, date], "pd.DataFrame | None"]


def ohlcv_path(
    settings: Settings,
    source: SourceName,
    asset: AssetClass,
    adjust: AdjustType,
    symbol: str,
) -> Path:
    """行情 parquet 路径：data/raw/{source}/{asset}/{adjust}/{symbol}.parquet。"""
    return settings.paths.raw_dir / source / asset / adjust / f"{symbol}.parquet"


def read_parquet(path: Path, columns: list[str] | None = None) -> pd.DataFrame | None:
    """读 parquet。文件不存在返回 None。

    若结果含 date 列：转 datetime、按主键去重、按 date 升序——防御手工改动过的脏文件。
    """
    if not path.exists():
        return None
    df = pd.read_parquet(path, columns=columns)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        if all(k in df.columns for k in PRIMARY_KEY):
            df = df.drop_duplicates(PRIMARY_KEY, keep="last")
        df = df.sort_values("date").reset_index(drop=True)
    return df


def write_parquet(df: pd.DataFrame, path: Path) -> None:
    """校验后原子写 parquet：先写 .tmp 再 os.replace，避免中断留下半截文件。"""
    validate_ohlcv(df)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def last_date(path: Path) -> date | None:
    """parquet 中最后一个日期。文件不存在或为空返回 None。

    只读 date 一列，避免为拿末日读整个文件——增量算法的基石。
    """
    if not path.exists():
        return None
    df = pd.read_parquet(path, columns=["date"])
    if df.empty:
        return None
    return pd.to_datetime(df["date"]).max().date()


def export_csv(parquet_path: Path) -> Path | None:
    """把一个行情 parquet 导出成同名 .csv（人工查看用）。

    文件不存在返回 None。CSV 用 utf-8-sig 编码，方便 Excel 打开中文。
    """
    df = read_parquet(parquet_path)
    if df is None:
        return None
    csv_path = parquet_path.with_suffix(".csv")
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    return csv_path


def append_incremental(
    *,
    symbol: str,
    adjust: AdjustType,
    source: SourceName,
    asset: AssetClass,
    fetch_fn: FetchFn,
    calendar: TradingCalendar,
    settings: Settings = SETTINGS,
    start: date | None = None,
    end: date | None = None,
    full_refresh: bool = False,
) -> KeyFetchResult:
    """增量下载单个标的的行情并落盘。

    算法：读已有数据末日 → 算 delta 区间 [next_trading_day, latest] → 已最新则短路 →
    取数 → 规整 → 与已有数据拼接去重 → 校验 → 原子写盘。

    不捕获异常：取数 / 规整 / 写盘抛错时直接向上抛，由 provider 统一记为 failed。

    Args:
        fetch_fn: 取数回调 (symbol, adjust, start, end) -> 原始 DataFrame。
        calendar: 交易日历，用于算 delta 区间。
        start: 首次全量下载的起点，默认取 settings.history_start。
        end: 增量终点，默认取 <= 今天的最近交易日。
        full_refresh: True 时忽略已有数据，从 history_start（或 start）全量重拉并覆盖。

    Returns:
        KeyFetchResult，status ∈ {full, incremental, up_to_date, empty}。
    """
    path = ohlcv_path(settings, source, asset, adjust, symbol)
    existing = read_parquet(path)
    rows_before = 0 if existing is None else len(existing)
    existing_last: date | None = None
    if existing is not None and not existing.empty:
        existing_last = existing["date"].max().date()

    history_start = start if start is not None else pd.Timestamp(settings.history_start).date()
    fresh_start = full_refresh or existing_last is None
    if fresh_start:
        delta_start = history_start
    else:
        delta_start = calendar.next_trading_day(existing_last)

    delta_end = end if end is not None else calendar.latest_trading_day()

    # 已是最新：不发请求直接短路。
    if delta_start > delta_end:
        return KeyFetchResult(
            key=f"{symbol}/{adjust}",
            status="up_to_date",
            rows_before=rows_before,
            rows_added=0,
            last_date_before=existing_last,
            last_date_after=existing_last,
        )

    raw = fetch_fn(symbol, adjust, delta_start, delta_end)
    if raw is None or len(raw) == 0:
        # 发了请求但无新数据（如新交易日数据尚未发布）——非错误。
        return KeyFetchResult(
            key=f"{symbol}/{adjust}",
            status="empty",
            rows_before=rows_before,
            rows_added=0,
            last_date_before=existing_last,
            last_date_after=existing_last,
        )

    delta_df = normalize_akshare_ohlcv(raw, symbol=symbol, adjust=adjust, source=source)

    if fresh_start or existing is None:
        merged = delta_df
    else:
        merged = (
            pd.concat([existing, delta_df], ignore_index=True)
            .drop_duplicates(PRIMARY_KEY, keep="last")  # 重叠日用新数据覆盖
            .sort_values("date")
            .reset_index(drop=True)
        )

    write_parquet(merged, path)

    return KeyFetchResult(
        key=f"{symbol}/{adjust}",
        status="full" if fresh_start else "incremental",
        rows_before=rows_before,
        rows_added=len(merged) - rows_before,
        last_date_before=existing_last,
        last_date_after=merged["date"].max().date(),
    )


def check_freshness(
    *,
    symbol: str,
    adjust: AdjustType,
    source: SourceName,
    asset: AssetClass,
    calendar: TradingCalendar,
    settings: Settings = SETTINGS,
    asof: date | None = None,
) -> FreshnessStatus:
    """检查单个标的数据是否已更新到最近交易日。"""
    path = ohlcv_path(settings, source, asset, adjust, symbol)
    actual = last_date(path)
    expected = calendar.latest_trading_day(asof)

    is_fresh = actual is not None and actual >= expected
    if actual is None or is_fresh:
        lag = 0
    else:
        lag = calendar.trading_days_between(actual, expected)

    return FreshnessStatus(
        key=f"{symbol}/{adjust}",
        last_date=actual,
        expected_last_trading_day=expected,
        is_fresh=is_fresh,
        lag_trading_days=lag,
    )
