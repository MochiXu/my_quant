"""core/panel.py 测试。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from my_quant.core.panel import Panel
from tests.helpers import make_panel


def _series(values, start="2024-01-01"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values)))


def test_panel_empty_raises():
    with pytest.raises(ValueError, match="为空"):
        Panel({})


def test_panel_close_wide_table():
    panel = make_panel({"A": _series([1.0, 2.0, 3.0]), "B": _series([10.0, 11.0, 12.0])})
    close = panel.close
    assert list(close.columns) == ["A", "B"]
    assert close["A"].tolist() == [1.0, 2.0, 3.0]
    assert isinstance(close.index, pd.DatetimeIndex)


def test_panel_outer_join_misaligned_dates():
    a = _series([1.0, 2.0, 3.0], start="2024-01-01")
    b = _series([9.0, 9.0], start="2024-01-02")  # 晚一天上市
    panel = make_panel({"A": a, "B": b})
    close = panel.close
    assert len(close) == 3
    assert np.isnan(close["B"].iloc[0])  # B 首日未上市


def test_panel_symbols_and_ohlcv():
    panel = make_panel({"A": _series([1.0, 2.0]), "B": _series([3.0, 4.0])})
    assert panel.symbols == ["A", "B"]
    assert list(panel.ohlcv("A").columns) == ["open", "high", "low", "close", "volume"]


def test_panel_slice():
    panel = make_panel({"A": _series([1.0, 2.0, 3.0, 4.0, 5.0])})
    sliced = panel.slice(start="2024-01-02", end="2024-01-04")
    assert len(sliced.close) == 3
    assert sliced.close.index[0] == pd.Timestamp("2024-01-02")


def test_panel_subset():
    panel = make_panel({"A": _series([1.0]), "B": _series([2.0]), "C": _series([3.0])})
    assert panel.subset(["A", "C"]).symbols == ["A", "C"]
