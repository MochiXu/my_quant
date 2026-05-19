"""data/providers/ohlcv.py 测试：OhlcvProvider 的编排逻辑（用假数据源，不联网）。"""
from __future__ import annotations

from dataclasses import replace
from datetime import date

import pandas as pd
import pytest

from my_quant.data.providers.ohlcv import OhlcvProvider
from tests.helpers import akshare_df


class FakeSource:
    """假的 OhlcvSource：按交易日历返回数据；可指定某些标的取数抛错。"""

    name = "akshare"
    asset_class = "etf"

    def __init__(self, calendar, *, fail_symbols=()):
        self.calendar = calendar
        self.fail_symbols = set(fail_symbols)
        self.calls: list = []

    def fetch_history(self, symbol, adjust, start, end):
        self.calls.append((symbol, adjust, start, end))
        if symbol in self.fail_symbols:
            raise RuntimeError(f"fake source 故障：{symbol}")
        days = self.calendar.trading_days(start, end)
        return akshare_df(days) if days else pd.DataFrame()


def _provider(settings, calendar, **source_kwargs) -> OhlcvProvider:
    return OhlcvProvider(
        settings=settings,
        source=FakeSource(calendar, **source_kwargs),
        calendar=calendar,
    )


def test_fetch_creates_files_for_all_keys_and_adjusts(tmp_settings, mock_calendar):
    provider = _provider(tmp_settings, mock_calendar)
    report = provider.fetch(["513100", "510300"], end=date(2024, 1, 5))

    # 2 标的 × 2 复权（raw, hfq）= 4 项，全部首次全量
    assert len(report.results) == 4
    assert all(r.status == "full" for r in report.results)
    assert report.ok

    for symbol in ("513100", "510300"):
        for adjust in ("raw", "hfq"):
            path = tmp_settings.paths.raw_dir / "akshare" / "etf" / adjust / f"{symbol}.parquet"
            assert path.exists()


def test_fetch_isolates_per_key_failure(tmp_settings, mock_calendar):
    provider = _provider(tmp_settings, mock_calendar, fail_symbols=["510300"])
    report = provider.fetch(["513100", "510300"], end=date(2024, 1, 5))

    assert not report.ok
    assert len(report.failed) == 2  # 510300 的 raw + hfq
    assert {r.key for r in report.failed} == {"510300/raw", "510300/hfq"}
    # 未故障的标的仍成功
    ok = [r for r in report.results if r.status == "full"]
    assert {r.key for r in ok} == {"513100/raw", "513100/hfq"}


def test_load_returns_datetime_indexed_frame(tmp_settings, mock_calendar):
    provider = _provider(tmp_settings, mock_calendar)
    provider.fetch(["513100"], end=date(2024, 1, 10))

    loaded = provider.load(["513100"])
    assert set(loaded) == {"513100"}
    df = loaded["513100"]
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.is_monotonic_increasing
    assert {"open", "high", "low", "close", "volume"}.issubset(df.columns)


def test_load_slices_by_date(tmp_settings, mock_calendar):
    provider = _provider(tmp_settings, mock_calendar)
    provider.fetch(["513100"], end=date(2024, 1, 10))

    sliced = provider.load(["513100"], start=date(2024, 1, 8))["513100"]
    assert sliced.index.min() == pd.Timestamp("2024-01-08")
    assert len(sliced) == 3  # 01-08, 09, 10


def test_load_missing_raises_when_on_missing_raise(tmp_settings, mock_calendar):
    provider = _provider(tmp_settings, mock_calendar)
    with pytest.raises(FileNotFoundError):
        provider.load(["513100"])  # 从未下载


def test_load_missing_skipped_when_on_missing_skip(tmp_settings, mock_calendar):
    skip_settings = replace(tmp_settings, on_missing="skip")
    provider = _provider(skip_settings, mock_calendar)
    provider.fetch(["513100"], end=date(2024, 1, 5))

    loaded = provider.load(["513100", "510300"])  # 510300 未下载
    assert set(loaded) == {"513100"}


def test_freshness_reports_staleness(tmp_settings, mock_calendar):
    provider = _provider(tmp_settings, mock_calendar)
    provider.fetch(["513100"], end=date(2024, 1, 5))

    fs = provider.freshness(["513100"], asof=date(2024, 1, 10))["513100"]
    assert not fs.is_fresh
    assert fs.lag_trading_days == 3
    assert fs.last_date == date(2024, 1, 5)
