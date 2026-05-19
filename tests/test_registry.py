"""data/registry.py 与 feature_store.py 测试。"""
from __future__ import annotations

from dataclasses import replace

import pytest

from my_quant.core.types import FeatureRef
from my_quant.data.feature_store import FeatureStore
from my_quant.data.providers.ohlcv import OhlcvProvider
from my_quant.data.registry import ProviderRegistry


def test_registry_builds_ohlcv_provider(tmp_settings):
    registry = ProviderRegistry(tmp_settings)
    assert registry.categories() == ["ohlcv"]
    assert isinstance(registry.get("ohlcv"), OhlcvProvider)


def test_registry_get_unregistered_category_raises(tmp_settings):
    registry = ProviderRegistry(tmp_settings)
    with pytest.raises(KeyError, match="macro_us"):
        registry.get("macro_us")


def test_registry_unknown_enabled_category_raises(tmp_settings):
    bad = replace(tmp_settings, enabled_categories=("bogus",))
    with pytest.raises(ValueError, match="未知数据类别"):
        ProviderRegistry(bad)


def test_feature_store_resolve_groups_and_dedups(tmp_settings):
    fs = FeatureStore(ProviderRegistry(tmp_settings))
    refs = [
        FeatureRef("ohlcv", "513100"),
        FeatureRef("ohlcv", "510300"),
        FeatureRef("ohlcv", "513100"),  # 重复
        FeatureRef("macro_us", "vix"),
    ]
    resolved = fs.resolve(refs)

    assert resolved == {"macro_us": ["vix"], "ohlcv": ["510300", "513100"]}


def test_feature_store_resolve_empty(tmp_settings):
    fs = FeatureStore(ProviderRegistry(tmp_settings))
    assert fs.resolve([]) == {}
