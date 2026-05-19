# my_quant

个人量化交易框架：对热门 ETF（纳指 100、沪深 300 等）做策略回测与半自动实盘。

- 架构设计见 [docs/design.md](docs/design.md)
- 策略说明见 [docs/strategies.md](docs/strategies.md)

当前进度：**P0 — 项目骨架 + 数据层**。后续阶段见 design.md 第 11 节。

## 安装

```bash
conda activate myTools
cd /Users/mochi/workspace/my_quant
pip install -e ".[dev]"
```

`pip install -e .` 把项目装成可编辑包，统一用 `from my_quant.* import` 绝对导入，
无需 `sys.path` hack。

## 配置

P0 下载 ETF 行情走 akshare，无需密钥。tushare 数据源（P1+）才需要：

```bash
cp .env.example .env   # 编辑 .env 填入 TUSHARE_TOKEN
```

## 同步数据

```bash
python scripts/sync_data.py               # 增量同步 universe 全部 ETF 行情
python scripts/sync_data.py --check       # 只检查数据新鲜度，不下载
python scripts/sync_data.py --symbols 513100 510300
my-quant-sync                             # 装包后等价的 console 命令
```

数据写入 `data/raw/`（已 gitignore）。

## 测试

```bash
pytest            # 默认跳过标记 network 的联网用例
pytest -m network # 单独跑联网冒烟测试
```
