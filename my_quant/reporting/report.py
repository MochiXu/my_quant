"""回测文本报告。"""
from __future__ import annotations

from my_quant.backtest.metrics import Metrics
from my_quant.backtest.vector import BacktestResult
from my_quant.backtest.walk_forward import WalkForwardResult


def _pct(x: float) -> str:
    return f"{x * 100:+.2f}%"


def format_metrics(m: Metrics) -> list[str]:
    """把一组指标格式化成对齐的文本行。"""
    return [
        f"  总收益    {_pct(m.total_return)}",
        f"  年化收益  {_pct(m.cagr)}",
        f"  年化波动  {m.annual_volatility * 100:.2f}%",
        f"  夏普      {m.sharpe:.2f}",
        f"  最大回撤  {_pct(m.max_drawdown)}",
        f"  卡玛      {m.calmar:.2f}",
        f"  胜率      {m.win_rate * 100:.1f}%",
        f"  交易日数  {m.n_periods}",
    ]


def backtest_report(
    result: BacktestResult,
    benchmark: BacktestResult | None = None,
    *,
    title: str = "",
) -> str:
    """生成单次回测的文本报告（可选与基准对比）。"""
    lines: list[str] = []
    if title:
        lines += [title, "=" * len(title)]

    lines.append(f"策略：{result.strategy_name}")
    lines += format_metrics(result.metrics)
    lines.append(f"  期末资金  {result.final_value:,.0f}"
                 f"（初始 {result.initial_capital:,.0f}）")

    if benchmark is not None:
        lines += ["", f"基准：{benchmark.strategy_name}"]
        lines += format_metrics(benchmark.metrics)
        edge = result.metrics.total_return - benchmark.metrics.total_return
        lines += ["", f"超额（策略 − 基准 总收益）：{_pct(edge)}"]

    return "\n".join(lines)


def walk_forward_report(wf: WalkForwardResult, *, title: str = "") -> str:
    """生成 walk-forward 的文本报告。"""
    lines: list[str] = []
    if title:
        lines += [title, "=" * len(title)]

    lines.append("OOS（样本外）整体绩效：")
    lines += format_metrics(wf.metrics)
    lines += ["", f"各窗口（共 {len(wf.segments)} 段）："]
    for _, row in wf.segments.iterrows():
        lines.append(
            f"  {row['test_start']} ~ {row['test_end']}  "
            f"参数={row['params']}  训练分={row['train_score']}  "
            f"OOS={row['oos_return'] * 100:+.1f}%"
        )
    return "\n".join(lines)
