"""晚间脚本：生成次日下单计划。

用法：
    python scripts/run_live.py --symbols 510300 --strategy dual_ma --fast 20 --slow 60
    python scripts/run_live.py --symbols 510300 513100 --asof 2026-05-18

流程：加载最新行情 → 回放台账 → 跑策略取次日目标权重 → 算调仓订单 →
产出下单计划到 data/live/plans/。次日照计划人工下单，成交后用 record_trade.py 回填。
"""
from __future__ import annotations

import argparse
import sys

from config.settings import SETTINGS
from my_quant.live.runner import generate_daily_plan, load_live_panels
from my_quant.strategies.buy_and_hold import BuyAndHold
from my_quant.strategies.dual_ma import DualMA


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="生成次日下单计划")
    p.add_argument("--symbols", nargs="+", default=["510300"], metavar="CODE")
    p.add_argument("--strategy", choices=["dual_ma", "buy_and_hold"], default="dual_ma")
    p.add_argument("--fast", type=int, default=20, help="双均线快线周期")
    p.add_argument("--slow", type=int, default=60, help="双均线慢线周期")
    p.add_argument("--asof", metavar="YYYY-MM-DD",
                   help="据以决策的收盘日，默认取数据最新日")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.strategy == "dual_ma":
        strategy = DualMA(args.symbols, fast=args.fast, slow=args.slow)
    else:
        strategy = BuyAndHold(args.symbols)

    signal_panel, price_panel = load_live_panels(args.symbols, SETTINGS)
    plan = generate_daily_plan(
        strategy, signal_panel, price_panel, settings=SETTINGS, asof=args.asof,
    )

    print(plan.to_markdown())
    print(f"\n计划已保存至 {SETTINGS.paths.live_dir / 'plans'}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
