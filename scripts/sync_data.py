"""晚间数据同步脚本：增量下载 ETF 行情。

用法：
    python scripts/sync_data.py                  增量同步 universe 全部 ETF
    python scripts/sync_data.py --scope core     只同步核心池
    python scripts/sync_data.py --symbols 513100 510300
    python scripts/sync_data.py --check          只检查新鲜度，不下载
    python scripts/sync_data.py --full-refresh   忽略已有数据全量重拉

注：design.md 7.3 规划「按策略 required_data() 并集同步」，但 P0 还没有策略，
故此处直接同步 universe（按 --scope）。required_data 驱动的过滤留待 P1。
"""
from __future__ import annotations

import argparse
import sys
from datetime import date

import pandas as pd

from config.settings import SETTINGS
from config.universe import all_symbols, core_symbols, sector_symbols
from my_quant.data import store
from my_quant.data.registry import ProviderRegistry
from my_quant.data.results import FetchReport, FreshnessStatus

# P0 只有 akshare ETF 一个数据源。
_SOURCE = "akshare"
_ASSET = "etf"


def _parse_date(s: str) -> date:
    return pd.Timestamp(s).date()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="增量同步 ETF 行情数据")
    p.add_argument("--symbols", nargs="+", metavar="CODE",
                   help="指定标的代码（默认按 --scope 取 universe）")
    p.add_argument("--scope", choices=["core", "sector", "all"], default="all",
                   help="按 universe 类别选标的，默认 all")
    p.add_argument("--adjust", nargs="+", choices=["raw", "qfq", "hfq"],
                   help="复权类型（默认 settings.adjust_types）")
    p.add_argument("--start", type=_parse_date, metavar="YYYY-MM-DD",
                   help="首次全量下载起点")
    p.add_argument("--end", type=_parse_date, metavar="YYYY-MM-DD",
                   help="增量终点")
    p.add_argument("--check", action="store_true",
                   help="只检查数据新鲜度，不下载")
    p.add_argument("--export-csv", action="store_true",
                   help="同步后额外导出 CSV")
    p.add_argument("--full-refresh", action="store_true",
                   help="忽略已有数据，全量重拉并覆盖")
    return p


def _select_symbols(args: argparse.Namespace) -> list[str]:
    if args.symbols:
        return args.symbols
    return {"core": core_symbols, "sector": sector_symbols, "all": all_symbols}[args.scope]()


def _print_freshness(statuses: dict[str, FreshnessStatus]) -> None:
    for key, fs in statuses.items():
        if fs.last_date is None:
            print(f"  {key:10} 缺数据文件")
        elif fs.is_fresh:
            print(f"  {key:10} 最新（{fs.last_date}）")
        else:
            print(f"  {key:10} 滞后 {fs.lag_trading_days} 个交易日"
                  f"（末日 {fs.last_date}，期望 {fs.expected_last_trading_day}）")


def _export_csv(symbols: list[str], adjusts: list[str] | None) -> None:
    adjusts = adjusts if adjusts else list(SETTINGS.adjust_types)
    for symbol in symbols:
        for adjust in adjusts:
            path = store.ohlcv_path(SETTINGS, _SOURCE, _ASSET, adjust, symbol)
            csv_path = store.export_csv(path)
            if csv_path is not None:
                print(f"  导出 {csv_path}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    symbols = _select_symbols(args)
    provider = ProviderRegistry(SETTINGS).get("ohlcv")

    if args.check:
        print(f"检查 {len(symbols)} 只 ETF 数据新鲜度…")
        statuses: dict[str, FreshnessStatus] = provider.freshness(symbols)
        _print_freshness(statuses)
        stale = [s for s in statuses.values() if not s.is_fresh]
        if stale:
            print(f"\n{len(stale)} 只标的数据不是最新。")
            return 1
        print("\n全部最新。")
        return 0

    print(f"同步 {len(symbols)} 只 ETF 行情：{', '.join(symbols)}")
    report: FetchReport = provider.fetch(
        symbols,
        start=args.start,
        end=args.end,
        adjusts=tuple(args.adjust) if args.adjust else None,
        full_refresh=args.full_refresh,
    )
    print(report.summary())

    if args.export_csv:
        print("导出 CSV…")
        _export_csv(symbols, args.adjust)

    if not report.ok:
        print(f"\n{len(report.failed)} 项同步失败。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
