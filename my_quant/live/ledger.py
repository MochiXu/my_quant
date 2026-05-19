"""持仓台账：成交流水是唯一事实源，持仓 / 现金 / 净值由回放算出。

两个 append-only 的 CSV（易人工编辑回填）：
- trades.csv：证券成交，列 date/symbol/action(buy|sell)/shares/price/fee/note
- cash.csv：现金流水，列 date/action(deposit|withdraw|dividend)/amount/note

接通交易 API 后，成交回报直接 append 进 trades.csv，回放逻辑不变。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from config.settings import SETTINGS, Settings

TRADE_COLUMNS = ["date", "symbol", "action", "shares", "price", "fee", "note"]
CASH_COLUMNS = ["date", "action", "amount", "note"]

TRADE_ACTIONS = {"buy", "sell"}
CASH_ACTIONS = {"deposit", "withdraw", "dividend"}


@dataclass
class PositionDetail:
    """单个持仓的明细。"""

    symbol: str
    shares: int
    avg_cost: float       # 移动加权平均成本
    price: float          # 现价
    market_value: float
    weight: float         # 占 NAV 比例


@dataclass
class AccountSnapshot:
    """某一时点的账户快照。"""

    asof: date
    cash: float
    positions: list[PositionDetail] = field(default_factory=list)
    market_value: float = 0.0
    nav: float = 0.0


def _to_date_str(value) -> str:
    """把 date / datetime / 字符串统一成 'YYYY-MM-DD'。"""
    return pd.Timestamp(value).strftime("%Y-%m-%d")


class Ledger:
    """读写并回放持仓台账。"""

    def __init__(self, settings: Settings = SETTINGS) -> None:
        self.settings = settings
        self.trades_path = settings.paths.live_dir / "trades.csv"
        self.cash_path = settings.paths.live_dir / "cash.csv"

    # —— 读取 ——

    def trades(self) -> pd.DataFrame:
        """全部证券成交流水（按日期升序）。"""
        return self._read(self.trades_path, TRADE_COLUMNS)

    def cash_flows(self) -> pd.DataFrame:
        """全部现金流水（按日期升序）。"""
        return self._read(self.cash_path, CASH_COLUMNS)

    @staticmethod
    def _read(path, columns: list[str]) -> pd.DataFrame:
        if not path.exists():
            return pd.DataFrame(columns=columns)
        # symbol 强制按字符串读，否则全数字代码（如 510300）会被当成整数。
        df = pd.read_csv(path, dtype={"symbol": str})
        df["date"] = pd.to_datetime(df["date"])
        return df.sort_values("date").reset_index(drop=True)

    # —— 写入（append-only）——

    def record_trade(
        self, *, date, symbol: str, action: str, shares: int,
        price: float, fee: float = 0.0, note: str = "",
    ) -> None:
        """追加一条证券成交。"""
        if action not in TRADE_ACTIONS:
            raise ValueError(f"action 须为 {TRADE_ACTIONS}，收到 {action!r}")
        if shares <= 0 or price <= 0:
            raise ValueError("shares 与 price 必须为正")
        self._append(self.trades_path, TRADE_COLUMNS, {
            "date": _to_date_str(date), "symbol": symbol, "action": action,
            "shares": int(shares), "price": float(price), "fee": float(fee),
            "note": note,
        })

    def record_cash(
        self, *, date, action: str, amount: float, note: str = "",
    ) -> None:
        """追加一条现金流水（入金 / 出金 / 分红）。"""
        if action not in CASH_ACTIONS:
            raise ValueError(f"action 须为 {CASH_ACTIONS}，收到 {action!r}")
        if amount <= 0:
            raise ValueError("amount 必须为正（出金也填正数，按 action 解释方向）")
        self._append(self.cash_path, CASH_COLUMNS, {
            "date": _to_date_str(date), "action": action,
            "amount": float(amount), "note": note,
        })

    @staticmethod
    def _append(path, columns: list[str], row: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            existing = pd.read_csv(path, dtype={"symbol": str})
        else:
            existing = pd.DataFrame(columns=columns)
        updated = pd.concat([existing, pd.DataFrame([row])], ignore_index=True)
        updated.to_csv(path, index=False, encoding="utf-8-sig")

    # —— 回放 ——

    def _replay(self) -> tuple[dict[str, tuple[int, float]], float]:
        """回放流水，返回 ({symbol: (shares, avg_cost)}, cash)。"""
        book: dict[str, tuple[int, float]] = {}
        cash = 0.0

        for t in self.trades().itertuples(index=False):
            shares, price, fee = int(t.shares), float(t.price), float(t.fee)
            held, avg = book.get(t.symbol, (0, 0.0))
            if t.action == "buy":
                cash -= shares * price + fee
                new_held = held + shares
                avg = (held * avg + shares * price + fee) / new_held
                book[t.symbol] = (new_held, avg)
            else:  # sell：均价不变，股数减少
                cash += shares * price - fee
                book[t.symbol] = (held - shares, avg)

        for c in self.cash_flows().itertuples(index=False):
            amount = float(c.amount)
            cash += amount if c.action in ("deposit", "dividend") else -amount

        return book, cash

    def positions(self) -> dict[str, int]:
        """当前持仓 {symbol: shares}，只含非零持仓。"""
        book, _ = self._replay()
        return {s: sh for s, (sh, _) in book.items() if sh != 0}

    def avg_costs(self) -> dict[str, float]:
        """当前持仓的移动加权平均成本。"""
        book, _ = self._replay()
        return {s: avg for s, (sh, avg) in book.items() if sh != 0}

    def cash(self) -> float:
        """当前现金。"""
        _, cash = self._replay()
        return cash

    def snapshot(self, prices: dict[str, float], asof: date | None = None) -> AccountSnapshot:
        """给定现价，生成账户快照。"""
        book, cash = self._replay()
        details: list[PositionDetail] = []
        market_value = 0.0
        for symbol, (shares, avg) in sorted(book.items()):
            if shares == 0:
                continue
            price = float(prices.get(symbol, 0.0))
            value = shares * price
            market_value += value
            details.append(PositionDetail(
                symbol=symbol, shares=shares, avg_cost=avg,
                price=price, market_value=value, weight=0.0,
            ))

        nav = cash + market_value
        if nav > 0:
            for d in details:
                d.weight = d.market_value / nav

        return AccountSnapshot(
            asof=asof or date.today(),
            cash=cash, positions=details,
            market_value=market_value, nav=nav,
        )
