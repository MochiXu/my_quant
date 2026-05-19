"""回测图表：净值曲线 + 回撤。

matplotlib 用 Agg 后端，便于脚本里无界面保存图片。
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # 非交互后端，保存图片不依赖显示环境

import matplotlib.pyplot as plt  # noqa: E402
import seaborn as sns  # noqa: E402

from my_quant.backtest.vector import BacktestResult  # noqa: E402

# 中文字体候选，按优先级取第一个可用的。
_CJK_FONTS = ["PingFang SC", "Heiti SC", "STHeiti", "Songti SC", "Arial Unicode MS"]


def configure_chinese_font() -> None:
    """让 matplotlib 能正常显示中文与负号。"""
    available = {f.name for f in matplotlib.font_manager.fontManager.ttflist}
    for font in _CJK_FONTS:
        if font in available:
            matplotlib.rcParams["font.sans-serif"] = [font]
            break
    matplotlib.rcParams["axes.unicode_minus"] = False


def plot_backtest(
    result: BacktestResult,
    benchmark: BacktestResult | None = None,
    *,
    output_path: str | Path,
    title: str = "",
) -> Path:
    """画回测图：上图净值曲线（策略 vs 基准），下图回撤。

    Returns:
        实际保存的图片路径。
    """
    sns.set_theme(style="whitegrid")
    configure_chinese_font()  # set_theme 会重置字体，须在其后再配置

    fig, (ax_nav, ax_dd) = plt.subplots(
        2, 1, figsize=(12, 8),
        gridspec_kw={"height_ratios": [3, 1]}, sharex=True,
    )

    nav = result.nav
    ax_nav.plot(nav.index, nav.values, color="green", linewidth=1.6,
                label=f"{result.strategy_name}（{result.metrics.total_return * 100:+.1f}%）")
    if benchmark is not None:
        bnav = benchmark.nav
        ax_nav.plot(bnav.index, bnav.values, color="steelblue", linewidth=1.4,
                    label=f"{benchmark.strategy_name}（{benchmark.metrics.total_return * 100:+.1f}%）")
    ax_nav.axhline(1.0, color="gray", linewidth=0.8, linestyle="--", alpha=0.6)
    ax_nav.set_ylabel("净值（起点 1.0）")
    ax_nav.set_title(title or f"{result.strategy_name} 回测", fontsize=13, fontweight="bold")
    ax_nav.legend(loc="upper left", fontsize=10)

    drawdown = result.nav / result.nav.cummax() - 1.0
    ax_dd.fill_between(drawdown.index, drawdown.values, 0.0,
                       color="indianred", alpha=0.5)
    ax_dd.set_ylabel("回撤")
    ax_dd.set_xlabel("日期")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path
