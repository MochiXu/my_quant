"""ETF 标的池（design.md 附录 A）。

核心池（core）：跨资产轮动 / 择时的主战场，6 只。
行业池（sector）：做行业轮动时再启用，5 只。

注意：代码 / 规模 / 流动性 / t_plus 规则均依公开资料填写，应在使用前用 akshare 或
券商资料逐一核对（design.md 附录 A 明确要求）。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EtfMeta:
    """一只 ETF 的元数据。

    Args:
        symbol: 6 位代码（akshare fund_etf_hist_em 用的格式，不带交易所后缀）。
        name: 中文名。
        role: 在组合里的角色。
        t_plus: 0 = 当日买入当日可卖（跨境 / 黄金 ETF）；1 = 次日才可卖（A 股股票 ETF）。
            P0 数据层不依赖此字段，P3 实盘下单约束才用，先一次定到位。
        category: "core"（核心池）或 "sector"（行业 / 主题池）。
        note: 备注，如基金公司、流动性提示。
    """

    symbol: str
    name: str
    role: str
    t_plus: int
    category: str
    note: str = ""


# 标的池。key == EtfMeta.symbol（test_universe_config.py 会校验一致性）。
UNIVERSE: dict[str, EtfMeta] = {
    # —— 核心池：跨资产轮动主战场 ——
    "510300": EtfMeta("510300", "沪深300ETF", "A股大盘核心", t_plus=1,
                      category="core", note="华泰柏瑞，流动性最好"),
    "510500": EtfMeta("510500", "中证500ETF", "A股中盘弹性", t_plus=1,
                      category="core", note="南方"),
    "159915": EtfMeta("159915", "创业板ETF", "A股成长", t_plus=1,
                      category="core", note="易方达"),
    "513100": EtfMeta("513100", "纳斯达克100ETF", "美股科技成长", t_plus=0,
                      category="core", note="国泰，跨境 T+0"),
    "513500": EtfMeta("513500", "标普500ETF", "美股大盘", t_plus=0,
                      category="core", note="博时，跨境 T+0"),
    "518880": EtfMeta("518880", "黄金ETF", "商品避险腿", t_plus=0,
                      category="core", note="华安"),
    # —— 行业 / 主题池：做行业轮动时再启用 ——
    "588000": EtfMeta("588000", "科创50ETF", "A股硬科技", t_plus=1, category="sector"),
    "512880": EtfMeta("512880", "证券ETF", "券商高 beta", t_plus=1, category="sector"),
    "512760": EtfMeta("512760", "半导体ETF", "半导体芯片", t_plus=1, category="sector"),
    "512170": EtfMeta("512170", "医疗ETF", "医药医疗", t_plus=1, category="sector"),
    "159928": EtfMeta("159928", "消费ETF", "主要消费", t_plus=1, category="sector"),
}


def get(symbol: str) -> EtfMeta:
    """按代码取 ETF 元数据，找不到抛 KeyError。"""
    return UNIVERSE[symbol]


def all_symbols() -> list[str]:
    """全部标的代码。"""
    return list(UNIVERSE.keys())


def core_symbols() -> list[str]:
    """核心池标的代码。"""
    return [s for s, m in UNIVERSE.items() if m.category == "core"]


def sector_symbols() -> list[str]:
    """行业 / 主题池标的代码。"""
    return [s for s, m in UNIVERSE.items() if m.category == "sector"]
