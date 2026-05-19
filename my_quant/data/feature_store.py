"""特征库：按策略声明的数据需求装配特征。

P0 无策略消费者，只落最小骨架——`resolve` 把一组 FeatureRef 按类别归并求并集，
供 P1 的 sync_data 实现「按 required_data() 同步」。

`load_panel`（把多类别特征拼成信号核的输入面板）依赖策略对面板形态的期望，
留待 P1 策略层落地时再实现。
"""
from __future__ import annotations

from my_quant.core.types import FeatureRef
from my_quant.data.registry import ProviderRegistry


class FeatureStore:
    """按 FeatureRef 解析数据需求。"""

    def __init__(self, registry: ProviderRegistry) -> None:
        self.registry = registry

    def resolve(self, refs: list[FeatureRef]) -> dict[str, list[str]]:
        """把 FeatureRef 列表按 category 归并、去重、求并集。

        Returns:
            {category: sorted(keys)}，类别与 key 均已排序，输出稳定。
        """
        grouped: dict[str, set[str]] = {}
        for ref in refs:
            grouped.setdefault(ref.category, set()).add(ref.key)
        return {cat: sorted(keys) for cat, keys in sorted(grouped.items())}
