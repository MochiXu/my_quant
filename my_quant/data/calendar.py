"""A 股交易日历。

增量下载（算 delta 区间）与新鲜度检查都依赖它。
`TradingCalendar` 是纯类，持有一个排序的交易日列表；`get_calendar()` 负责从
akshare 拉取或读本地缓存。
"""
from __future__ import annotations

import bisect
import os
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from config.settings import SETTINGS, Settings

_CALENDAR_FILE = "trade_calendar.parquet"


def _to_date(value) -> date:
    """把 date / datetime / Timestamp / 字符串统一成 datetime.date。"""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return pd.Timestamp(value).date()


class TradingCalendar:
    """交易日历：持有排序去重的交易日，提供日期推算。

    所有方法接受 date / datetime / Timestamp / 字符串，内部统一成 date。
    """

    def __init__(self, days: Iterable) -> None:
        self._days: tuple[date, ...] = tuple(sorted({_to_date(d) for d in days}))
        if not self._days:
            raise ValueError("交易日历为空")
        self._day_set: frozenset[date] = frozenset(self._days)

    @property
    def first_day(self) -> date:
        return self._days[0]

    @property
    def last_day(self) -> date:
        return self._days[-1]

    def __len__(self) -> int:
        return len(self._days)

    def is_trading_day(self, d) -> bool:
        """d 是否为交易日。"""
        return _to_date(d) in self._day_set

    def next_trading_day(self, d) -> date:
        """严格晚于 d 的第一个交易日。"""
        d = _to_date(d)
        i = bisect.bisect_right(self._days, d)
        if i >= len(self._days):
            raise ValueError(f"{d} 之后已超出日历范围（末日 {self.last_day}）")
        return self._days[i]

    def prev_trading_day(self, d) -> date:
        """严格早于 d 的最后一个交易日。"""
        d = _to_date(d)
        i = bisect.bisect_left(self._days, d)
        if i == 0:
            raise ValueError(f"{d} 之前已超出日历范围（首日 {self.first_day}）")
        return self._days[i - 1]

    def latest_trading_day(self, asof=None) -> date:
        """<= asof 的最大交易日。asof 为 None 时取今天。

        asof 本身是交易日则返回 asof。
        """
        asof = _to_date(asof) if asof is not None else date.today()
        i = bisect.bisect_right(self._days, asof)
        if i == 0:
            raise ValueError(f"{asof} 早于日历首日 {self.first_day}")
        return self._days[i - 1]

    def trading_days(self, start, end) -> list[date]:
        """[start, end] 闭区间内的全部交易日。"""
        start, end = _to_date(start), _to_date(end)
        lo = bisect.bisect_left(self._days, start)
        hi = bisect.bisect_right(self._days, end)
        return list(self._days[lo:hi])

    def trading_days_between(self, start, end) -> int:
        """(start, end] 内的交易日数——严格晚于 start、且 <= end。

        用于算数据新鲜度的滞后天数：start=实际末日, end=期望末日。
        两者相等返回 0。
        """
        start, end = _to_date(start), _to_date(end)
        lo = bisect.bisect_right(self._days, start)
        hi = bisect.bisect_right(self._days, end)
        return max(0, hi - lo)


def _fetch_from_akshare() -> list[date]:
    """从 akshare 拉全量 A 股交易日历。"""
    import akshare as ak

    df = ak.tool_trade_date_hist_sina()
    return [_to_date(v) for v in df["trade_date"]]


def _write_cache(days: Iterable[date], cache_path: Path) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({"trade_date": pd.to_datetime(sorted(days))})
    tmp = cache_path.with_suffix(cache_path.suffix + ".tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, cache_path)


def _read_cache(cache_path: Path) -> list[date]:
    df = pd.read_parquet(cache_path, columns=["trade_date"])
    return [_to_date(v) for v in df["trade_date"]]


def get_calendar(settings: Settings = SETTINGS, *, refresh: bool = False) -> TradingCalendar:
    """加载交易日历。

    首次或 refresh=True 时从 akshare 拉取并缓存到 meta_dir；否则读本地缓存。
    调用方应取一次实例后复用，不要每次操作都 get。
    """
    cache_path = settings.paths.meta_dir / _CALENDAR_FILE
    if refresh or not cache_path.exists():
        days = _fetch_from_akshare()
        _write_cache(days, cache_path)
    else:
        days = _read_cache(cache_path)
    return TradingCalendar(days)
