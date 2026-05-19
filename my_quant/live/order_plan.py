"""晨间下单计划：把订单整理成可执行清单（CSV）+ 人读日报（markdown）。"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from config.settings import LiveConfig
from my_quant.core.portfolio import Order
from my_quant.live.ledger import AccountSnapshot

_ACTION_CN = {"buy": "买入", "sell": "卖出"}

PLAN_CSV_COLUMNS = [
    "symbol", "name", "action", "shares", "tranches",
    "limit_price", "ref_price", "est_amount", "reason",
]


@dataclass
class PlanRow:
    """下单清单的一行。"""

    symbol: str
    name: str
    action: str
    shares: int
    tranches: int          # 建议拆成几笔
    limit_price: float     # 限价建议
    ref_price: float       # 参考价（最新收盘）
    est_amount: float      # 预估成交金额
    reason: str


@dataclass
class OrderPlan:
    """一份完整的晨间下单计划。"""

    asof: date              # 据以生成的收盘数据日期
    trade_date: date        # 建议执行日（次一交易日）
    snapshot: AccountSnapshot
    target_weights: dict[str, float]
    rows: list[PlanRow] = field(default_factory=list)
    names: dict[str, str] = field(default_factory=dict)  # 标的代码 → 中文名

    def to_dataframe(self) -> pd.DataFrame:
        """下单清单 DataFrame。"""
        return pd.DataFrame(
            [[getattr(r, c) for c in PLAN_CSV_COLUMNS] for r in self.rows],
            columns=PLAN_CSV_COLUMNS,
        )

    def to_markdown(self) -> str:
        """人读的交易计划日报。"""
        snap = self.snapshot
        lines = [
            f"# 交易计划 {self.trade_date}",
            "",
            f"> 基于 {self.asof} 收盘数据生成，建议 {self.trade_date} 开盘执行。",
            "",
            f"## 账户快照（截至 {snap.asof}）",
            "",
            f"- 总资产 NAV：{snap.nav:,.0f}",
            f"- 现金：{snap.cash:,.0f}",
            f"- 持仓市值：{snap.market_value:,.0f}",
            "",
        ]
        if snap.positions:
            lines += ["| 标的 | 名称 | 股数 | 成本 | 现价 | 市值 | 权重 |",
                      "|---|---|---|---|---|---|---|"]
            for p in snap.positions:
                name = self._name(p.symbol)
                lines.append(
                    f"| {p.symbol} | {name} | {p.shares} | {p.avg_cost:.3f} | "
                    f"{p.price:.3f} | {p.market_value:,.0f} | {p.weight:.1%} |"
                )
        else:
            lines.append("当前无持仓。")

        lines += ["", f"## 目标权重（{self.asof} 收盘信号）", ""]
        cash_weight = 1.0 - sum(self.target_weights.values())
        for symbol, weight in sorted(self.target_weights.items()):
            lines.append(f"- {symbol} {self._name(symbol)}：{weight:.1%}")
        lines.append(f"- 现金：{cash_weight:.1%}")

        lines += ["", f"## 下单建议（{self.trade_date} 开盘）", ""]
        if self.rows:
            lines += ["| 标的 | 名称 | 方向 | 股数 | 拆单 | 限价 | 参考价 | 预估金额 | 理由 |",
                      "|---|---|---|---|---|---|---|---|---|"]
            for r in self.rows:
                lines.append(
                    f"| {r.symbol} | {r.name} | {_ACTION_CN[r.action]} | {r.shares} | "
                    f"{r.tranches} | {r.limit_price:.3f} | {r.ref_price:.3f} | "
                    f"{r.est_amount:,.0f} | {r.reason} |"
                )
        else:
            lines.append("今日无需调仓。")
        lines.append("")
        return "\n".join(lines)

    def _name(self, symbol: str) -> str:
        return self.names.get(symbol, symbol)

    def write(self, plans_dir: Path) -> tuple[Path, Path]:
        """把日报与下单清单写入 plans 目录，文件名按执行日命名。"""
        plans_dir.mkdir(parents=True, exist_ok=True)
        md_path = plans_dir / f"{self.trade_date}.md"
        csv_path = plans_dir / f"orders_{self.trade_date}.csv"
        md_path.write_text(self.to_markdown(), encoding="utf-8")
        self.to_dataframe().to_csv(csv_path, index=False, encoding="utf-8-sig")
        return md_path, csv_path


def build_order_plan(
    orders: list[Order],
    *,
    prices: dict[str, float],
    names: dict[str, str],
    snapshot: AccountSnapshot,
    target_weights: dict[str, float],
    asof: date,
    trade_date: date,
    live: LiveConfig,
) -> OrderPlan:
    """把订单加工成下单计划：补名称、限价、拆单、预估金额。"""
    rows: list[PlanRow] = []
    buffer = live.limit_buffer_ticks * live.tick_size
    for order in orders:
        ref = prices[order.symbol]
        raw_limit = ref + buffer if order.action == "buy" else ref - buffer
        # 对齐到最小价位。
        limit = round(round(raw_limit / live.tick_size) * live.tick_size, 4)
        est = order.shares * ref
        tranches = max(1, math.ceil(est / live.tranche_cap))
        rows.append(PlanRow(
            symbol=order.symbol,
            name=names.get(order.symbol, order.symbol),
            action=order.action,
            shares=order.shares,
            tranches=tranches,
            limit_price=limit,
            ref_price=round(ref, 4),
            est_amount=round(est, 2),
            reason=order.reason,
        ))
    return OrderPlan(
        asof=asof, trade_date=trade_date, snapshot=snapshot,
        target_weights=target_weights, rows=rows, names=dict(names),
    )
