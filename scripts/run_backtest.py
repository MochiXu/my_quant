"""回测脚本：对 ETF 跑策略回测，输出文本报告 + 图表。

用法：
    python scripts/run_backtest.py --symbols 510300 --strategy dual_ma --fast 20 --slow 60
    python scripts/run_backtest.py --symbols 513100 --start 2020-01-01
    python scripts/run_backtest.py --symbols 510300 --walk-forward
"""
from __future__ import annotations

import argparse
import sys

from config.settings import SETTINGS
from my_quant.backtest.bt_engine import run_bt_backtest
from my_quant.backtest.vector import run_backtest
from my_quant.backtest.walk_forward import walk_forward
from my_quant.core.panel import Panel
from my_quant.core.strategy import Strategy
from my_quant.data.registry import ProviderRegistry
from my_quant.reporting.plot import plot_backtest
from my_quant.reporting.report import backtest_report, walk_forward_report
from my_quant.strategies.buy_and_hold import BuyAndHold
from my_quant.strategies.dual_ma import DualMA

# walk-forward 的双均线参数网格（fast < slow 的组合）。
_WF_FAST = (10, 20, 40)
_WF_SLOW = (60, 120, 200)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="ETF 策略回测")
    p.add_argument("--symbols", nargs="+", default=["510300"], metavar="CODE",
                   help="标的代码，默认 510300")
    p.add_argument("--strategy", choices=["dual_ma", "buy_and_hold"], default="dual_ma")
    p.add_argument("--engine", choices=["vector", "backtrader"], default="vector",
                   help="回测引擎：vector 向量化（快）/ backtrader 精细撮合")
    p.add_argument("--fast", type=int, default=20, help="双均线快线周期")
    p.add_argument("--slow", type=int, default=60, help="双均线慢线周期")
    p.add_argument("--adjust", choices=["raw", "qfq", "hfq"], default=None,
                   help="复权类型，默认 settings.default_adjust（hfq）")
    p.add_argument("--start", metavar="YYYY-MM-DD", help="回测窗口起点")
    p.add_argument("--end", metavar="YYYY-MM-DD", help="回测窗口终点")
    p.add_argument("--walk-forward", action="store_true",
                   help="跑 walk-forward（双均线参数滚动选优）")
    p.add_argument("--train-years", type=int, default=4)
    p.add_argument("--test-years", type=int, default=1)
    return p


def _load_panel(symbols: list[str], adjust: str | None) -> Panel:
    provider = ProviderRegistry(SETTINGS).get("ohlcv")
    return Panel(provider.load(symbols, adjust=adjust))


def _run(strategy: Strategy, panel: Panel, engine: str, start, end):
    """按引擎名分派回测。"""
    if engine == "backtrader":
        return run_bt_backtest(strategy, panel, start=start, end=end)
    return run_backtest(strategy, panel, start=start, end=end)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    panel = _load_panel(args.symbols, args.adjust)
    label = "/".join(args.symbols)

    if args.walk_forward:
        grid = [{"fast": f, "slow": s} for f in _WF_FAST for s in _WF_SLOW if f < s]
        wf = walk_forward(
            panel,
            lambda p: DualMA(args.symbols, fast=p["fast"], slow=p["slow"]),
            grid,
            train_years=args.train_years,
            test_years=args.test_years,
        )
        print(walk_forward_report(wf, title=f"Walk-Forward 双均线回测 [{label}]"))
        return 0

    if args.strategy == "dual_ma":
        strategy = DualMA(args.symbols, fast=args.fast, slow=args.slow)
    else:
        strategy = BuyAndHold(args.symbols)

    result = _run(strategy, panel, args.engine, args.start, args.end)
    benchmark = None
    if args.strategy != "buy_and_hold":
        benchmark = _run(BuyAndHold(args.symbols), panel, args.engine,
                         args.start, args.end)

    title = f"{strategy.name} 回测 [{label}] · {args.engine} 引擎"
    print(backtest_report(result, benchmark, title=title))

    out_path = (SETTINGS.paths.reports_dir
                / f"backtest_{args.engine}_{strategy.name}_{'_'.join(args.symbols)}.png")
    plot_backtest(result, benchmark, output_path=out_path, title=title)
    print(f"\n图表已保存：{out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
