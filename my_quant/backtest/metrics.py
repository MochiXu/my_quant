"""回测绩效指标。

输入统一为日收益序列（net daily returns）；净值、回撤等内部派生。
默认一年 252 个交易日。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def _nav(returns: pd.Series) -> pd.Series:
    """由日收益累乘出净值曲线，起点 1.0。"""
    return (1.0 + returns.fillna(0.0)).cumprod()


def total_return(returns: pd.Series) -> float:
    """区间总收益率。"""
    nav = _nav(returns)
    return float(nav.iloc[-1] - 1.0) if len(nav) else 0.0


def cagr(returns: pd.Series, periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    """年化收益率（复合）。"""
    nav = _nav(returns)
    if len(nav) == 0:
        return 0.0
    years = len(nav) / periods_per_year
    if years <= 0 or nav.iloc[-1] <= 0:
        return 0.0
    return float(nav.iloc[-1] ** (1.0 / years) - 1.0)


def annual_volatility(returns: pd.Series, periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    """年化波动率。"""
    r = returns.dropna()
    if len(r) < 2:
        return 0.0
    return float(r.std(ddof=1) * np.sqrt(periods_per_year))


def sharpe_ratio(
    returns: pd.Series,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
    risk_free: float = 0.0,
) -> float:
    """年化夏普比率。risk_free 为年化无风险利率。波动为 0 时返回 0。"""
    r = returns.dropna()
    if len(r) < 2:
        return 0.0
    excess = r - risk_free / periods_per_year
    sd = excess.std(ddof=1)
    # 阈值判零：恒定收益序列的 std 受浮点误差影响不会恰好为 0。
    if sd < 1e-12:
        return 0.0
    return float(excess.mean() / sd * np.sqrt(periods_per_year))


def max_drawdown(returns: pd.Series) -> float:
    """最大回撤（负值，如 -0.25 表示最深回撤 25%）。"""
    nav = _nav(returns)
    if len(nav) == 0:
        return 0.0
    drawdown = nav / nav.cummax() - 1.0
    return float(drawdown.min())


def calmar_ratio(returns: pd.Series, periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    """卡玛比率 = 年化收益 / |最大回撤|。无回撤时返回 0。"""
    mdd = max_drawdown(returns)
    if mdd == 0:
        return 0.0
    return float(cagr(returns, periods_per_year) / abs(mdd))


def win_rate(returns: pd.Series) -> float:
    """盈利天数占比（只统计非零收益的交易日）。"""
    r = returns.dropna()
    nonzero = r[r != 0]
    if len(nonzero) == 0:
        return 0.0
    return float((nonzero > 0).mean())


@dataclass
class Metrics:
    """一组回测绩效指标。"""

    total_return: float
    cagr: float
    annual_volatility: float
    sharpe: float
    max_drawdown: float
    calmar: float
    win_rate: float
    n_periods: int

    def as_dict(self) -> dict[str, float]:
        return {
            "total_return": self.total_return,
            "cagr": self.cagr,
            "annual_volatility": self.annual_volatility,
            "sharpe": self.sharpe,
            "max_drawdown": self.max_drawdown,
            "calmar": self.calmar,
            "win_rate": self.win_rate,
            "n_periods": self.n_periods,
        }


def compute_metrics(
    returns: pd.Series,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
    risk_free: float = 0.0,
) -> Metrics:
    """从日收益序列汇总所有绩效指标。"""
    return Metrics(
        total_return=total_return(returns),
        cagr=cagr(returns, periods_per_year),
        annual_volatility=annual_volatility(returns, periods_per_year),
        sharpe=sharpe_ratio(returns, periods_per_year, risk_free),
        max_drawdown=max_drawdown(returns),
        calmar=calmar_ratio(returns, periods_per_year),
        win_rate=win_rate(returns),
        n_periods=int(len(returns)),
    )
