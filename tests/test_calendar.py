"""data/calendar.py 测试：交易日历日期推算（用 mock_calendar，不联网）。"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from my_quant.data.calendar import TradingCalendar


def test_is_trading_day(mock_calendar):
    assert mock_calendar.is_trading_day("2024-01-05")     # 周五
    assert not mock_calendar.is_trading_day("2024-01-06")  # 周六
    assert not mock_calendar.is_trading_day("2024-01-07")  # 周日


def test_next_trading_day_across_weekend(mock_calendar):
    # 周五 → 下周一
    assert mock_calendar.next_trading_day("2024-01-05") == date(2024, 1, 8)


def test_next_trading_day_from_weekday(mock_calendar):
    # 周三 → 周四
    assert mock_calendar.next_trading_day("2024-01-03") == date(2024, 1, 4)


def test_prev_trading_day_across_weekend(mock_calendar):
    # 周一 → 上周五
    assert mock_calendar.prev_trading_day("2024-01-08") == date(2024, 1, 5)


def test_latest_trading_day_on_weekend(mock_calendar):
    # 周日 → 上一交易日（周五）
    assert mock_calendar.latest_trading_day("2024-01-07") == date(2024, 1, 5)


def test_latest_trading_day_on_trading_day(mock_calendar):
    # asof 本身是交易日 → 返回自己
    assert mock_calendar.latest_trading_day("2024-01-08") == date(2024, 1, 8)


def test_trading_days_inclusive(mock_calendar):
    days = mock_calendar.trading_days("2024-01-02", "2024-01-08")
    assert days == [date(2024, 1, d) for d in (2, 3, 4, 5, 8)]


def test_trading_days_between(mock_calendar):
    # (周五, 下周一] 之间只有周一一个交易日
    assert mock_calendar.trading_days_between("2024-01-05", "2024-01-08") == 1
    # 起止相同 → 0
    assert mock_calendar.trading_days_between("2024-01-08", "2024-01-08") == 0
    # 跨周末多日
    assert mock_calendar.trading_days_between("2024-01-02", "2024-01-08") == 4


def test_next_trading_day_beyond_range_raises(mock_calendar):
    with pytest.raises(ValueError, match="超出日历范围"):
        mock_calendar.next_trading_day("2024-03-29")  # 日历末日


def test_prev_trading_day_beyond_range_raises(mock_calendar):
    with pytest.raises(ValueError, match="超出日历范围"):
        mock_calendar.prev_trading_day("2024-01-02")  # 日历首日


def test_empty_calendar_raises():
    with pytest.raises(ValueError, match="为空"):
        TradingCalendar([])


def test_accepts_mixed_date_types(mock_calendar):
    # date / 字符串 / Timestamp 都应被接受
    assert mock_calendar.is_trading_day(date(2024, 1, 5))
    assert mock_calendar.is_trading_day(pd.Timestamp("2024-01-05"))
    assert mock_calendar.is_trading_day("2024-01-05")
