"""core/portfolio.py 测试：目标权重 → 下单清单。"""
from __future__ import annotations

from my_quant.core.portfolio import compute_orders


def test_initial_build_from_all_cash():
    # 全现金 10 万，目标 50% A → 买入。价 10、整手 100 → 5000 股
    orders = compute_orders(
        {"A": 0.5}, positions={}, cash=100_000, prices={"A": 10.0},
        no_trade_band=0.0,
    )
    assert len(orders) == 1
    assert orders[0].symbol == "A"
    assert orders[0].action == "buy"
    assert orders[0].shares == 5000


def test_lot_rounding_floors_to_lot_size():
    # 目标市值 / 价 = 333.3 手 → 向下取整到整手
    orders = compute_orders(
        {"A": 1.0}, positions={}, cash=100_000, prices={"A": 30.0},
        lot_size=100, no_trade_band=0.0,
    )
    # 100000/30 = 3333.3 → 取整到 3300
    assert orders[0].shares == 3300


def test_no_trade_band_skips_small_drift():
    # 当前已持 50%，目标 52%，偏离 2% < 5% 带宽 → 不调仓
    orders = compute_orders(
        {"A": 0.52}, positions={"A": 5000}, cash=50_000, prices={"A": 10.0},
        no_trade_band=0.05,
    )
    assert orders == []


def test_rebalance_generates_sell():
    # 当前满仓 A，目标降到 0 → 全部卖出
    orders = compute_orders(
        {"A": 0.0}, positions={"A": 5000}, cash=0.0, prices={"A": 10.0},
        no_trade_band=0.0,
    )
    assert len(orders) == 1
    assert orders[0].action == "sell"
    assert orders[0].shares == 5000


def test_exit_position_not_in_target():
    # 持有 B，但目标权重里没有 B → 视作目标 0 → 卖出
    orders = compute_orders(
        {"A": 1.0}, positions={"B": 1000}, cash=90_000, prices={"A": 10.0, "B": 10.0},
        no_trade_band=0.0,
    )
    actions = {o.symbol: o.action for o in orders}
    assert actions["B"] == "sell"
    assert actions["A"] == "buy"


def test_orders_sorted_by_symbol():
    orders = compute_orders(
        {"C": 0.3, "A": 0.3, "B": 0.3}, positions={}, cash=300_000,
        prices={"A": 10.0, "B": 10.0, "C": 10.0}, no_trade_band=0.0,
    )
    assert [o.symbol for o in orders] == ["A", "B", "C"]


def test_zero_nav_produces_no_orders():
    assert compute_orders({"A": 1.0}, positions={}, cash=0.0,
                          prices={"A": 10.0}) == []
