"""config/universe.py 测试：标的池配置自洽性。"""
from __future__ import annotations

import pytest

from config.universe import (
    UNIVERSE,
    all_symbols,
    core_symbols,
    get,
    sector_symbols,
)


def test_symbol_matches_dict_key():
    for key, meta in UNIVERSE.items():
        assert key == meta.symbol


def test_symbols_unique():
    symbols = all_symbols()
    assert len(symbols) == len(set(symbols))


def test_t_plus_valid():
    for meta in UNIVERSE.values():
        assert meta.t_plus in (0, 1), meta.symbol


def test_category_valid():
    for meta in UNIVERSE.values():
        assert meta.category in ("core", "sector"), meta.symbol


def test_pool_sizes():
    assert len(core_symbols()) == 6
    assert len(sector_symbols()) == 5
    assert len(all_symbols()) == 11


def test_core_and_sector_partition_universe():
    assert set(core_symbols()) | set(sector_symbols()) == set(all_symbols())
    assert set(core_symbols()) & set(sector_symbols()) == set()


def test_get_returns_meta():
    assert get("513100").name == "纳斯达克100ETF"


def test_get_unknown_raises():
    with pytest.raises(KeyError):
        get("000000")
