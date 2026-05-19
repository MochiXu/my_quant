"""data/schema.py 测试：akshare 数据规整与 OHLCV 校验。"""
from __future__ import annotations

import pandas as pd
import pytest

from my_quant.data.schema import (
    NUMERIC_COLUMNS,
    OHLCV_COLUMNS,
    normalize_akshare_ohlcv,
    validate_ohlcv,
)


def test_normalize_renames_and_injects(fake_akshare_df):
    df = normalize_akshare_ohlcv(fake_akshare_df, symbol="513100", adjust="hfq")

    assert list(df.columns) == OHLCV_COLUMNS
    assert (df["symbol"] == "513100").all()
    assert (df["adjust"] == "hfq").all()
    assert (df["source"] == "akshare").all()
    assert len(df) == 5
    # 收盘 → close 的值应原样保留
    assert df["close"].iloc[0] == pytest.approx(1.21)


def test_normalize_dtypes(fake_akshare_df):
    df = normalize_akshare_ohlcv(fake_akshare_df, symbol="513100", adjust="raw")

    assert pd.api.types.is_datetime64_any_dtype(df["date"])
    assert pd.api.types.is_datetime64_any_dtype(df["updated_at"])
    for col in NUMERIC_COLUMNS:
        assert df[col].dtype == "float64", col


def test_normalize_sorts_by_date(fake_akshare_df):
    shuffled = fake_akshare_df.iloc[[3, 0, 4, 1, 2]].reset_index(drop=True)
    df = normalize_akshare_ohlcv(shuffled, symbol="513100", adjust="hfq")

    assert df["date"].is_monotonic_increasing


def test_normalize_dedups_within_batch_keep_last(fake_akshare_df):
    # 造一行与首行同日期、但 收盘 不同，验证去重保留后者。
    dup = fake_akshare_df.copy()
    dup.loc[len(dup)] = dup.iloc[0].copy()
    dup.loc[len(dup) - 1, "日期"] = "2024-01-03"  # 与第 2 行（index 1）同日
    dup.loc[len(dup) - 1, "收盘"] = 9.99

    df = normalize_akshare_ohlcv(dup, symbol="513100", adjust="hfq")

    assert len(df) == 5  # 去重后仍 5 个不同日期
    row = df[df["date"] == pd.Timestamp("2024-01-03")]
    assert len(row) == 1
    assert row["close"].iloc[0] == pytest.approx(9.99)  # 保留后追加的那行


def test_normalize_missing_date_column_raises(fake_akshare_df):
    bad = fake_akshare_df.drop(columns=["日期"])
    with pytest.raises(ValueError, match="日期"):
        normalize_akshare_ohlcv(bad, symbol="513100", adjust="hfq")


def test_normalize_missing_numeric_column_raises(fake_akshare_df):
    bad = fake_akshare_df.drop(columns=["成交量"])
    with pytest.raises(ValueError, match="数值列"):
        normalize_akshare_ohlcv(bad, symbol="513100", adjust="hfq")


def test_validate_passes_on_normalized(fake_akshare_df):
    df = normalize_akshare_ohlcv(fake_akshare_df, symbol="513100", adjust="hfq")
    validate_ohlcv(df)  # 不抛错即通过


def test_validate_rejects_wrong_columns(fake_akshare_df):
    df = normalize_akshare_ohlcv(fake_akshare_df, symbol="513100", adjust="hfq")
    with pytest.raises(ValueError, match="列不符"):
        validate_ohlcv(df.drop(columns=["turnover"]))


def test_validate_rejects_duplicate_primary_key(fake_akshare_df):
    df = normalize_akshare_ohlcv(fake_akshare_df, symbol="513100", adjust="hfq")
    dup = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="重复"):
        validate_ohlcv(dup)


def test_validate_rejects_non_monotonic_date(fake_akshare_df):
    df = normalize_akshare_ohlcv(fake_akshare_df, symbol="513100", adjust="hfq")
    reversed_df = df.iloc[::-1].reset_index(drop=True)
    with pytest.raises(ValueError, match="升序"):
        validate_ohlcv(reversed_df)
