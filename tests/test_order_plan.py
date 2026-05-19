"""live/order_plan.py 测试。"""
from __future__ import annotations

from datetime import date

from config.settings import LiveConfig
from my_quant.core.portfolio import Order
from my_quant.live.ledger import AccountSnapshot
from my_quant.live.order_plan import build_order_plan

_SNAP = AccountSnapshot(asof=date(2024, 1, 5), cash=100_000.0,
                        positions=[], market_value=0.0, nav=100_000.0)
_LIVE = LiveConfig()


def _plan(orders):
    return build_order_plan(
        orders,
        prices={"A": 10.0, "B": 20.0},
        names={"A": "标的A", "B": "标的B"},
        snapshot=_SNAP,
        target_weights={"A": 0.5, "B": 0.5},
        asof=date(2024, 1, 5),
        trade_date=date(2024, 1, 8),
        live=_LIVE,
    )


def test_buy_limit_above_ref_sell_below():
    plan = _plan([Order("A", "buy", 1000, "建仓"),
                  Order("B", "sell", 500, "减仓")])
    rows = {r.symbol: r for r in plan.rows}
    buffer = _LIVE.limit_buffer_ticks * _LIVE.tick_size
    assert rows["A"].limit_price == round(10.0 + buffer, 4)   # 买单限价高于参考价
    assert rows["B"].limit_price == round(20.0 - buffer, 4)   # 卖单限价低于参考价


def test_est_amount_and_default_single_tranche():
    plan = _plan([Order("A", "buy", 1000, "建仓")])
    row = plan.rows[0]
    assert row.est_amount == 10_000.0       # 1000 * 10
    assert row.tranches == 1                # 远小于 tranche_cap


def test_large_order_suggests_splitting():
    live = LiveConfig(tranche_cap=5_000.0)
    plan = build_order_plan(
        [Order("A", "buy", 1000, "建仓")],
        prices={"A": 10.0}, names={"A": "标的A"}, snapshot=_SNAP,
        target_weights={"A": 1.0}, asof=date(2024, 1, 5),
        trade_date=date(2024, 1, 8), live=live,
    )
    # 1000*10 = 10000，按 5000 上限 → 拆 2 笔
    assert plan.rows[0].tranches == 2


def test_markdown_has_sections():
    md = _plan([Order("A", "buy", 1000, "建仓")]).to_markdown()
    assert "# 交易计划 2024-01-08" in md
    assert "账户快照" in md
    assert "目标权重" in md
    assert "下单建议" in md
    assert "买入" in md


def test_markdown_no_orders():
    md = _plan([]).to_markdown()
    assert "今日无需调仓" in md


def test_write_produces_files(tmp_path):
    plan = _plan([Order("A", "buy", 1000, "建仓")])
    md_path, csv_path = plan.write(tmp_path)
    assert md_path.name == "2024-01-08.md"
    assert csv_path.name == "orders_2024-01-08.csv"
    assert md_path.exists() and csv_path.exists()
