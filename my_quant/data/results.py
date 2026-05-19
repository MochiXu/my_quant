"""数据层操作的结果类型。

独立成叶子模块，让 store 与 providers 都能引用而不产生循环依赖。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

# 单个标的的同步结果状态：
#   full        首次全量下载
#   incremental 增量补拉到新数据
#   up_to_date  已是最新，未发请求
#   empty       发了请求但无新数据返回（如新交易日数据尚未发布）
#   failed      过程中抛异常
FetchStatus = Literal["full", "incremental", "up_to_date", "empty", "failed"]


@dataclass
class KeyFetchResult:
    """单个标的（symbol + adjust）的一次同步结果。"""

    key: str
    status: FetchStatus
    rows_before: int = 0
    rows_added: int = 0          # 净增行数 = 同步后行数 − 同步前行数
    last_date_before: date | None = None
    last_date_after: date | None = None
    error: str | None = None


@dataclass
class FetchReport:
    """一次同步任务（多个标的）的汇总。"""

    results: list[KeyFetchResult] = field(default_factory=list)

    @property
    def failed(self) -> list[KeyFetchResult]:
        return [r for r in self.results if r.status == "failed"]

    @property
    def ok(self) -> bool:
        """没有 failed 即为 ok。"""
        return len(self.failed) == 0

    def summary(self) -> str:
        """人读的多行汇总。"""
        lines: list[str] = []
        for r in self.results:
            line = f"  {r.key:18} {r.status:12} +{r.rows_added} 行"
            if r.error:
                line += f"  [错误] {r.error}"
            lines.append(line)

        counts: dict[str, int] = {}
        for r in self.results:
            counts[r.status] = counts.get(r.status, 0) + 1
        tally = "  ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        lines.append(f"合计 {len(self.results)} 项：{tally}")
        return "\n".join(lines)


@dataclass
class FreshnessStatus:
    """单个标的的数据新鲜度。"""

    key: str
    last_date: date | None              # 已有数据的最后日期，None 表示无文件
    expected_last_trading_day: date     # 期望应有的最近交易日
    is_fresh: bool                      # last_date 是否已追上期望
    lag_trading_days: int               # 落后多少个交易日（fresh 或无数据时为 0）
