"""scripts/sync_data.py 测试：CLI 编排（离线，mock 掉网络与日历）。"""
from __future__ import annotations

import pandas as pd
import pytest

from my_quant.data.providers import ohlcv
from scripts import sync_data
from tests.helpers import akshare_df


@pytest.fixture
def offline_sync(monkeypatch, tmp_settings, mock_calendar):
    """把 sync_data 接到临时目录 + mock 日历 + 假行情源，使其完全离线可跑。"""
    monkeypatch.setattr(sync_data, "SETTINGS", tmp_settings)
    monkeypatch.setattr(ohlcv, "get_calendar", lambda *a, **k: mock_calendar)

    def fake_fetch(self, symbol, adjust, start, end):
        days = mock_calendar.trading_days(start, end)
        return akshare_df(days) if days else pd.DataFrame()

    monkeypatch.setattr(ohlcv.AkshareEtfSource, "fetch_history", fake_fetch)
    return sync_data


def test_select_symbols_by_scope():
    parser = sync_data.build_parser()
    assert len(sync_data._select_symbols(parser.parse_args(["--scope", "core"]))) == 6
    assert len(sync_data._select_symbols(parser.parse_args(["--scope", "sector"]))) == 5
    assert len(sync_data._select_symbols(parser.parse_args(["--scope", "all"]))) == 11
    assert sync_data._select_symbols(parser.parse_args(["--symbols", "513100"])) == ["513100"]


def test_sync_fetches_and_writes_files(offline_sync, tmp_settings):
    rc = offline_sync.main(["--symbols", "513100", "--end", "2024-01-05"])

    assert rc == 0
    for adjust in ("raw", "hfq"):
        path = tmp_settings.paths.raw_dir / "akshare" / "etf" / adjust / "513100.parquet"
        assert path.exists()


def test_sync_check_reports_fresh(offline_sync):
    # 不指定 --end：同步到 mock 日历末日 → 随后 --check 应判为最新
    assert offline_sync.main(["--symbols", "513100"]) == 0
    assert offline_sync.main(["--symbols", "513100", "--check"]) == 0


def test_sync_check_reports_stale_when_no_data(offline_sync):
    # 从未下载 → --check 判为不新鲜，退出码非 0
    assert offline_sync.main(["--symbols", "513100", "--check"]) == 1


def test_sync_failure_returns_nonzero(offline_sync, monkeypatch):
    def boom(self, symbol, adjust, start, end):
        raise RuntimeError("网络故障")

    monkeypatch.setattr(ohlcv.AkshareEtfSource, "fetch_history", boom)
    assert offline_sync.main(["--symbols", "513100", "--end", "2024-01-05"]) == 1


def test_sync_export_csv(offline_sync, tmp_settings):
    rc = offline_sync.main(["--symbols", "513100", "--end", "2024-01-05",
                            "--adjust", "hfq", "--export-csv"])
    assert rc == 0
    csv_path = tmp_settings.paths.raw_dir / "akshare" / "etf" / "hfq" / "513100.csv"
    assert csv_path.exists()
