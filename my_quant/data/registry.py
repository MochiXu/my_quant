"""数据类别 → DataProvider 的注册表。

按 settings.enabled_categories 实例化 provider；其他模块通过 registry 统一取
provider，不直接 import 具体 provider 类——新增数据类别只需在这里登记。
"""
from __future__ import annotations

from config.settings import SETTINGS, Settings
from my_quant.data.providers.base import DataProvider
from my_quant.data.providers.ohlcv import OhlcvProvider


class ProviderRegistry:
    """持有已启用的 provider 实例，按 category 取用。"""

    def __init__(self, settings: Settings = SETTINGS) -> None:
        self.settings = settings
        self._providers: dict[str, DataProvider] = {}
        for category in settings.enabled_categories:
            self._providers[category] = _build_provider(category, settings)

    def get(self, category: str) -> DataProvider:
        """取某类别的 provider；未启用 / 未注册则抛错，杜绝隐式依赖。"""
        if category not in self._providers:
            raise KeyError(
                f"数据类别 '{category}' 未启用或未注册（已启用：{self.categories()}）"
            )
        return self._providers[category]

    def categories(self) -> list[str]:
        """已注册的类别列表。"""
        return list(self._providers)


def _build_provider(category: str, settings: Settings) -> DataProvider:
    """按类别名构造 provider。新增数据类别在此添加分支。"""
    if category == "ohlcv":
        return OhlcvProvider(settings)
    raise ValueError(f"未知数据类别：'{category}'（P0 仅支持 ohlcv）")
