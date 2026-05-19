"""向持仓台账追加一条流水（成交回填 / 入金 / 分红）。

用法：
    python scripts/record_trade.py trade --date 2026-05-20 --symbol 510300 \\
        --action buy --shares 1000 --price 3.85 --fee 5
    python scripts/record_trade.py cash --date 2026-05-19 --action deposit --amount 50000
"""
from __future__ import annotations

import argparse
import sys

from config.settings import SETTINGS
from my_quant.live.ledger import Ledger


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="向持仓台账追加流水")
    sub = p.add_subparsers(dest="kind", required=True)

    t = sub.add_parser("trade", help="证券成交")
    t.add_argument("--date", required=True, metavar="YYYY-MM-DD")
    t.add_argument("--symbol", required=True)
    t.add_argument("--action", choices=["buy", "sell"], required=True)
    t.add_argument("--shares", type=int, required=True)
    t.add_argument("--price", type=float, required=True)
    t.add_argument("--fee", type=float, default=0.0)
    t.add_argument("--note", default="")

    c = sub.add_parser("cash", help="现金流水")
    c.add_argument("--date", required=True, metavar="YYYY-MM-DD")
    c.add_argument("--action", choices=["deposit", "withdraw", "dividend"], required=True)
    c.add_argument("--amount", type=float, required=True)
    c.add_argument("--note", default="")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ledger = Ledger(SETTINGS)

    if args.kind == "trade":
        ledger.record_trade(
            date=args.date, symbol=args.symbol, action=args.action,
            shares=args.shares, price=args.price, fee=args.fee, note=args.note,
        )
        print(f"已记录成交：{args.date} {args.action} {args.symbol} "
              f"{args.shares} @ {args.price}")
    else:
        ledger.record_cash(
            date=args.date, action=args.action, amount=args.amount, note=args.note,
        )
        print(f"已记录现金流水：{args.date} {args.action} {args.amount}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
