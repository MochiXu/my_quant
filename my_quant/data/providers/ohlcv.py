"""ohlcv 数据类别的 provider。

二级抽象消除「按数据源取数」与「增量 / 存储编排」的耦合：
  OhlcvProvider —— 编排：遍历 symbol × adjust，调 store 增量落盘 / 读取。
  OhlcvSource   —— 数据源 seam：只管「给定区间返回原始 DataFrame」。

P0 只实现 AkshareEtfSource（ETF 行情）。未来加 tushare 股票源 = 再写一个
OhlcvSource 子类，provider / store / schema 一行不改。
"""
from __future__ import annotations

import time
from datetime import date

import pandas as pd

from config.settings import SETTINGS, Settings
from my_quant.core.types import AdjustType, AssetClass, SourceName
from my_quant.data import store
from my_quant.data.calendar import TradingCalendar, get_calendar
from my_quant.data.providers.base import DataProvider
from my_quant.data.results import FetchReport, FreshnessStatus, KeyFetchResult


class OhlcvSource:
    """OHLCV 数据源抽象。子类封装某个数据源的取数细节（含重试 / 限速）。"""

    name: SourceName
    asset_class: AssetClass

    def fetch_history(
        self, symbol: str, adjust: AdjustType, start: date, end: date
    ) -> pd.DataFrame | None:
        """返回 [start, end] 区间该标的的原始 DataFrame（未规整）。无数据返回空或 None。"""
        raise NotImplementedError


class AkshareEtfSource(OhlcvSource):
    """akshare ETF 行情源（ak.fund_etf_hist_em）。"""

    name: SourceName = "akshare"
    asset_class: AssetClass = "etf"

    # 框架复权类型 → akshare adjust 参数。
    _ADJUST_MAP: dict[AdjustType, str] = {"raw": "", "qfq": "qfq", "hfq": "hfq"}

    def __init__(self, settings: Settings = SETTINGS) -> None:
        self.settings = settings

    def fetch_history(
        self, symbol: str, adjust: AdjustType, start: date, end: date
    ) -> pd.DataFrame | None:
        import akshare as ak

        ak_adjust = self._ADJUST_MAP[adjust]
        start_s = start.strftime("%Y%m%d")
        end_s = end.strftime("%Y%m%d")

        last_err: Exception | None = None
        for attempt in range(1, self.settings.fetch_max_retries + 1):
            try:
                return ak.fund_etf_hist_em(
                    symbol=symbol,
                    period="daily",
                    start_date=start_s,
                    end_date=end_s,
                    adjust=ak_adjust,
                )
            except Exception as e:  # noqa: BLE001 — 取数失败要重试，捕获面要宽
                last_err = e
                if attempt < self.settings.fetch_max_retries:
                    wait = self.settings.fetch_sleep_seconds * attempt
                    print(f"[ohlcv] {symbol}/{adjust} 第 {attempt} 次取数失败：{e}；{wait}s 后重试")
                    time.sleep(wait)

        raise RuntimeError(
            f"akshare 取数失败 {symbol}/{adjust}，已重试 {self.settings.fetch_max_retries} 次"
        ) from last_err


class OhlcvProvider(DataProvider):
    """ohlcv 类别 provider：编排 ETF 行情的增量下载、读取、新鲜度检查。"""

    category = "ohlcv"

    def __init__(
        self,
        settings: Settings = SETTINGS,
        source: OhlcvSource | None = None,
        calendar: TradingCalendar | None = None,
    ) -> None:
        self.settings = settings
        self.source = source if source is not None else AkshareEtfSource(settings)
        # 交易日历懒加载：构造 provider 不应触发网络。
        self._calendar = calendar

    def _get_calendar(self) -> TradingCalendar:
        if self._calendar is None:
            self._calendar = get_calendar(self.settings)
        return self._calendar

    def fetch(
        self,
        keys: list[str],
        *,
        start: date | None = None,
        end: date | None = None,
        adjusts: tuple[AdjustType, ...] | None = None,
        full_refresh: bool = False,
    ) -> FetchReport:
        """对每个 symbol × 每种复权增量下载。单个 (symbol, adjust) 失败记为 failed，不中断其余。"""
        adjusts = adjusts if adjusts is not None else self.settings.adjust_types
        calendar = self._get_calendar()

        results: list[KeyFetchResult] = []
        for symbol in keys:
            for adjust in adjusts:
                try:
                    result = store.append_incremental(
                        symbol=symbol,
                        adjust=adjust,
                        source=self.source.name,
                        asset=self.source.asset_class,
                        fetch_fn=self.source.fetch_history,
                        calendar=calendar,
                        settings=self.settings,
                        start=start,
                        end=end,
                        full_refresh=full_refresh,
                    )
                except Exception as e:  # noqa: BLE001 — 逐 key 容错
                    result = KeyFetchResult(
                        key=f"{symbol}/{adjust}", status="failed", error=str(e)
                    )
                results.append(result)

        return FetchReport(results=results)

    def load(
        self,
        keys: list[str],
        *,
        start: date | None = None,
        end: date | None = None,
        adjust: AdjustType | None = None,
    ) -> dict[str, pd.DataFrame]:
        """读取本地 parquet。返回的 DataFrame 以 date 为 DatetimeIndex。

        缺文件按 settings.on_missing 处理（raise 抛错 / skip 跳过）。
        """
        adjust = adjust if adjust is not None else self.settings.default_adjust
        out: dict[str, pd.DataFrame] = {}

        for symbol in keys:
            path = store.ohlcv_path(
                self.settings, self.source.name, self.source.asset_class, adjust, symbol
            )
            df = store.read_parquet(path)
            if df is None:
                if self.settings.on_missing == "raise":
                    raise FileNotFoundError(f"缺少行情数据：{symbol}/{adjust} -> {path}")
                continue

            df = df.set_index("date").sort_index()
            if start is not None:
                df = df.loc[pd.Timestamp(start):]
            if end is not None:
                df = df.loc[: pd.Timestamp(end)]
            out[symbol] = df

        return out

    def freshness(
        self,
        keys: list[str],
        *,
        asof: date | None = None,
        adjust: AdjustType | None = None,
    ) -> dict[str, FreshnessStatus]:
        """检查 keys 数据是否已更新到最近交易日。"""
        adjust = adjust if adjust is not None else self.settings.default_adjust
        calendar = self._get_calendar()

        return {
            symbol: store.check_freshness(
                symbol=symbol,
                adjust=adjust,
                source=self.source.name,
                asset=self.source.asset_class,
                calendar=calendar,
                settings=self.settings,
                asof=asof,
            )
            for symbol in keys
        }
