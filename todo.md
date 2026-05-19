# my_quant 待办

## P0 收尾（待完成）

P0 代码已全部实现，62 个离线单测通过，`pip install -e .` 可装。剩下的是**需要联网**
的实盘验证，因环境代理（`127.0.0.1:7890`）当时不可用而未跑通。

### 1. 联网验证 sync_data（网络恢复后）

环境要求：`conda activate myTools`（Python 3.11，akshare/pandas/pyarrow 已装）。

```bash
cd /Users/mochi/workspace/my_quant

# (1) 首次全量下载一只 ETF
python scripts/sync_data.py --symbols 513100
# 预期：data/raw/akshare/etf/{raw,hfq}/513100.parquet 生成，约 2500+ 行

# (2) 增量幂等：紧接着再跑一次
python scripts/sync_data.py --symbols 513100
# 预期：status 全部 up_to_date，行数不变，不重复打接口

# (3) 新鲜度检查
python scripts/sync_data.py --symbols 513100 --check
# 预期：打印 是否最新 / 滞后交易日数

# (4) 全量同步 universe 11 只 ETF
python scripts/sync_data.py
# 预期：11 只 × 2 复权落盘，打印 FetchReport 汇总

# (5) 抽查数据
python -c "import pandas as pd; df=pd.read_parquet('data/raw/akshare/etf/hfq/513100.parquet'); print(df.tail()); print(df.shape)"
```

排查网络：`HTTP_PROXY/HTTPS_PROXY` 指向 `127.0.0.1:7890`，代理需在运行；
或确认能直连 `push2his.eastmoney.com`。

### 2. 核对 ETF 代码与 t_plus

`config/universe.py` 里 11 只 ETF 的代码、规模、流动性、`t_plus` 是按公开资料填的，
需用 akshare 或券商资料逐一核对（design.md 附录 A 已注明此动作）。
重点确认跨境 ETF（513100/513500/518880）的 T+0 规则。

## 后续阶段（P1+，见 docs/design.md 第 11 节）

- P1：信号核、向量化回测、估值/宏观 provider、overlay 抽象。
- P2 起步时把本次预研的 backtrader 要点（cheat_on_open / order_target_percent /
  自定义佣金类）补进 docs/design.md 第 8 节。
