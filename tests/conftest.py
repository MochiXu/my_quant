"""pytest 共享 fixtures。

P0 测试全部可离线运行：碰网络的逻辑用假数据 / mock 替代。
"""
from __future__ import annotations

import pandas as pd
import pytest

from config.settings import Paths, Settings
from my_quant.data.calendar import TradingCalendar


@pytest.fixture
def fake_akshare_df() -> pd.DataFrame:
    """模拟 ak.fund_etf_hist_em 的返回：中文列、日期为 str、成交量为 int。

    5 个连续交易日。测试需要变体（空 / 缺列 / 重复）时 .copy() 后自行修改。
    """
    return pd.DataFrame(
        {
            "日期": ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"],
            "开盘": [1.21, 1.19, 1.18, 1.20, 1.22],
            "收盘": [1.21, 1.19, 1.18, 1.21, 1.23],
            "最高": [1.21, 1.19, 1.18, 1.21, 1.23],
            "最低": [1.20, 1.18, 1.18, 1.19, 1.21],
            "成交量": [3300848, 6826748, 4300042, 5000000, 4200000],
            "成交额": [3.99e8, 8.13e8, 5.08e8, 6.00e8, 5.10e8],
            "振幅": [0.25, 0.33, 0.34, 0.50, 0.40],
            "涨跌幅": [-0.25, -1.57, -0.50, 2.00, 1.50],
            "涨跌额": [-0.003, -0.019, -0.006, 0.020, 0.018],
            "换手率": [3.49, 7.21, 4.54, 5.00, 4.20],
        }
    )


@pytest.fixture
def mock_calendar() -> TradingCalendar:
    """固定的交易日历：2024-01-02 ~ 2024-03-29 全部工作日（不含节假日）。

    不联网，用于测试日期推算与增量 / 新鲜度逻辑。覆盖周末跳空。
    """
    days = pd.bdate_range("2024-01-02", "2024-03-29").date
    return TradingCalendar(days)


@pytest.fixture
def tmp_settings(tmp_path) -> Settings:
    """Settings 实例，所有路径指向 pytest 临时目录。

    history_start 设为 2024-01-02，与 mock_calendar 的范围对齐。
    """
    data = tmp_path / "data"
    paths = Paths(
        project_root=tmp_path,
        data_dir=data,
        raw_dir=data / "raw",
        live_dir=data / "live",
        meta_dir=data / "raw" / "_meta",
    )
    return Settings(paths=paths, history_start="2024-01-02")
