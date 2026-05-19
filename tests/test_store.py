"""data/store.py 测试：parquet 读写、增量下载、新鲜度检查。"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from my_quant.data import store
from my_quant.data.schema import normalize_akshare_ohlcv, validate_ohlcv
from tests.helpers import akshare_df


# —— 测试辅助 ——

def _make_fetch_fn(calendar, *, close_base=1.0, mode="range"):
    """造一个假的 fetch_fn 并记录调用。

    mode: "range" 返回 [start,end] 交易日；"empty" 返回空；
          "from_start" 忽略 start、从日历首日返回（制造与已有数据的重叠）。
    """
    log: list = []

    def fetch(symbol, adjust, start, end):
        log.append((symbol, adjust, start, end))
        if mode == "empty":
            return pd.DataFrame()
        eff_start = calendar.first_day if mode == "from_start" else start
        days = calendar.trading_days(eff_start, end)
        return akshare_df(days, close_base) if days else pd.DataFrame()

    fetch.log = log  # type: ignore[attr-defined]
    return fetch


# —— 路径与读写 ——

def test_ohlcv_path(tmp_settings):
    p = store.ohlcv_path(tmp_settings, "akshare", "etf", "hfq", "513100")
    assert p == tmp_settings.paths.raw_dir / "akshare" / "etf" / "hfq" / "513100.parquet"


def test_read_parquet_missing_file_returns_none(tmp_settings):
    p = store.ohlcv_path(tmp_settings, "akshare", "etf", "hfq", "513100")
    assert store.read_parquet(p) is None


def test_write_then_read_roundtrip(tmp_settings, fake_akshare_df):
    df = normalize_akshare_ohlcv(fake_akshare_df, symbol="513100", adjust="hfq")
    p = store.ohlcv_path(tmp_settings, "akshare", "etf", "hfq", "513100")

    store.write_parquet(df, p)
    back = store.read_parquet(p)

    assert back is not None
    pd.testing.assert_frame_equal(df, back, check_dtype=False)


def test_write_parquet_leaves_no_tmp_file(tmp_settings, fake_akshare_df):
    df = normalize_akshare_ohlcv(fake_akshare_df, symbol="513100", adjust="hfq")
    p = store.ohlcv_path(tmp_settings, "akshare", "etf", "hfq", "513100")
    store.write_parquet(df, p)

    assert p.exists()
    assert list(p.parent.glob("*.tmp")) == []


def test_last_date(tmp_settings, fake_akshare_df):
    df = normalize_akshare_ohlcv(fake_akshare_df, symbol="513100", adjust="hfq")
    p = store.ohlcv_path(tmp_settings, "akshare", "etf", "hfq", "513100")

    assert store.last_date(p) is None  # 文件不存在
    store.write_parquet(df, p)
    assert store.last_date(p) == date(2024, 1, 8)


# —— 增量下载 ——

def test_append_incremental_first_full(tmp_settings, mock_calendar):
    fetch = _make_fetch_fn(mock_calendar)
    res = store.append_incremental(
        symbol="513100", adjust="hfq", source="akshare", asset="etf",
        fetch_fn=fetch, calendar=mock_calendar, settings=tmp_settings,
        end=date(2024, 1, 5),
    )

    assert res.status == "full"
    assert res.rows_before == 0
    assert res.rows_added == 4  # 01-02,03,04,05
    assert res.last_date_after == date(2024, 1, 5)

    p = store.ohlcv_path(tmp_settings, "akshare", "etf", "hfq", "513100")
    df = store.read_parquet(p)
    assert df is not None and len(df) == 4
    validate_ohlcv(df)


def test_append_incremental_then_increment(tmp_settings, mock_calendar):
    fetch = _make_fetch_fn(mock_calendar)
    store.append_incremental(
        symbol="513100", adjust="hfq", source="akshare", asset="etf",
        fetch_fn=fetch, calendar=mock_calendar, settings=tmp_settings,
        end=date(2024, 1, 5),
    )
    res = store.append_incremental(
        symbol="513100", adjust="hfq", source="akshare", asset="etf",
        fetch_fn=fetch, calendar=mock_calendar, settings=tmp_settings,
        end=date(2024, 1, 10),
    )

    assert res.status == "incremental"
    assert res.rows_before == 4
    assert res.rows_added == 3  # 01-08,09,10
    assert res.last_date_after == date(2024, 1, 10)
    # 第二次取数的 start 应是 01-05 之后的下一个交易日 01-08
    assert fetch.log[1][2] == date(2024, 1, 8)


def test_append_incremental_up_to_date_short_circuits(tmp_settings, mock_calendar):
    fetch = _make_fetch_fn(mock_calendar)
    store.append_incremental(
        symbol="513100", adjust="hfq", source="akshare", asset="etf",
        fetch_fn=fetch, calendar=mock_calendar, settings=tmp_settings,
        end=date(2024, 1, 5),
    )
    res = store.append_incremental(
        symbol="513100", adjust="hfq", source="akshare", asset="etf",
        fetch_fn=fetch, calendar=mock_calendar, settings=tmp_settings,
        end=date(2024, 1, 5),  # 同一终点 → 已最新
    )

    assert res.status == "up_to_date"
    assert res.rows_added == 0
    assert len(fetch.log) == 1  # 第二次未发请求


def test_append_incremental_empty_result(tmp_settings, mock_calendar):
    fetch = _make_fetch_fn(mock_calendar, mode="empty")
    res = store.append_incremental(
        symbol="513100", adjust="hfq", source="akshare", asset="etf",
        fetch_fn=fetch, calendar=mock_calendar, settings=tmp_settings,
        end=date(2024, 1, 5),
    )

    assert res.status == "empty"
    assert res.rows_added == 0
    p = store.ohlcv_path(tmp_settings, "akshare", "etf", "hfq", "513100")
    assert not p.exists()  # 空结果不写盘


def test_append_incremental_dedups_overlapping_fetch(tmp_settings, mock_calendar):
    # 首次：close_base=1.0
    store.append_incremental(
        symbol="513100", adjust="hfq", source="akshare", asset="etf",
        fetch_fn=_make_fetch_fn(mock_calendar, close_base=1.0),
        calendar=mock_calendar, settings=tmp_settings, end=date(2024, 1, 5),
    )
    # 增量：fetch 从日历首日返回（与已有数据重叠），且 close_base 改成 5.0
    res = store.append_incremental(
        symbol="513100", adjust="hfq", source="akshare", asset="etf",
        fetch_fn=_make_fetch_fn(mock_calendar, close_base=5.0, mode="from_start"),
        calendar=mock_calendar, settings=tmp_settings, end=date(2024, 1, 10),
    )

    p = store.ohlcv_path(tmp_settings, "akshare", "etf", "hfq", "513100")
    df = store.read_parquet(p)
    assert df is not None
    validate_ohlcv(df)                 # 无重复主键
    assert len(df) == 7                # 01-02..01-10 共 7 个交易日
    assert res.status == "incremental"
    # 重叠日 01-02 应被新数据（close_base=5.0）覆盖
    row = df[df["date"] == pd.Timestamp("2024-01-02")]
    assert row["close"].iloc[0] == pytest.approx(5.0)


def test_append_incremental_full_refresh_replaces(tmp_settings, mock_calendar):
    store.append_incremental(
        symbol="513100", adjust="hfq", source="akshare", asset="etf",
        fetch_fn=_make_fetch_fn(mock_calendar), calendar=mock_calendar,
        settings=tmp_settings, end=date(2024, 1, 10),
    )
    # full_refresh + 更早的终点 → 应整体替换为更短的数据
    res = store.append_incremental(
        symbol="513100", adjust="hfq", source="akshare", asset="etf",
        fetch_fn=_make_fetch_fn(mock_calendar), calendar=mock_calendar,
        settings=tmp_settings, end=date(2024, 1, 5), full_refresh=True,
    )

    assert res.status == "full"
    p = store.ohlcv_path(tmp_settings, "akshare", "etf", "hfq", "513100")
    df = store.read_parquet(p)
    assert df is not None and len(df) == 4  # 仅 01-02..01-05，旧数据被丢弃


# —— 新鲜度 ——

def test_check_freshness_fresh(tmp_settings, mock_calendar):
    store.append_incremental(
        symbol="513100", adjust="hfq", source="akshare", asset="etf",
        fetch_fn=_make_fetch_fn(mock_calendar), calendar=mock_calendar,
        settings=tmp_settings, end=date(2024, 1, 10),
    )
    fs = store.check_freshness(
        symbol="513100", adjust="hfq", source="akshare", asset="etf",
        calendar=mock_calendar, settings=tmp_settings, asof=date(2024, 1, 10),
    )

    assert fs.is_fresh
    assert fs.lag_trading_days == 0
    assert fs.last_date == date(2024, 1, 10)


def test_check_freshness_stale(tmp_settings, mock_calendar):
    store.append_incremental(
        symbol="513100", adjust="hfq", source="akshare", asset="etf",
        fetch_fn=_make_fetch_fn(mock_calendar), calendar=mock_calendar,
        settings=tmp_settings, end=date(2024, 1, 5),
    )
    fs = store.check_freshness(
        symbol="513100", adjust="hfq", source="akshare", asset="etf",
        calendar=mock_calendar, settings=tmp_settings, asof=date(2024, 1, 10),
    )

    assert not fs.is_fresh
    assert fs.lag_trading_days == 3  # 01-08,09,10
    assert fs.last_date == date(2024, 1, 5)


def test_check_freshness_missing_file(tmp_settings, mock_calendar):
    fs = store.check_freshness(
        symbol="513100", adjust="hfq", source="akshare", asset="etf",
        calendar=mock_calendar, settings=tmp_settings, asof=date(2024, 1, 10),
    )

    assert not fs.is_fresh
    assert fs.last_date is None
    assert fs.lag_trading_days == 0
