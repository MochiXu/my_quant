# my_quant 架构设计

> 状态：**待对齐**。这是项目骨架设计草案，确认后再开始写代码。

## 1. 目标与约束

**做什么**

- 对国内能买到的热门 ETF 做策略回测（纳指 100 ETF、沪深 300 ETF 等）。
- 跑实盘：一天交易 1~2 次，按「日级」粒度决策。
- 晚上人工同步当日行情数据；次日上午人工按计划下单。
- 后续接通券商交易 API 后，把「人工下单」换成「自动下单」，其余流程不变。

**关键约束**

- 现在没有交易 API，实盘是**半自动**：框架出计划 → 人工执行 → 人工回填成交。
- A 股 ETF 交易规则：最小 100 份/手、宽基 ETF T+1（跨境 ETF 如纳指多为 T+0）、
  ETF 免印花税。这些影响下单计划取整与撮合逻辑。
- 决策粒度是「收盘后算、次日成交」，不做日内高频。

## 2. 核心理念：策略只写一遍，三处复用

整个框架围绕一个抽象——**信号核（signal core）**：

> 给定截至某日 T 收盘的历史行情，输出「T+1 起要持有的目标权重」。
> 信号核是纯函数，不碰券商、不碰下单，只做「数据 → 权重」的计算。

同一个信号核被三个消费者复用，保证「回测里跑出来的策略」和「实盘真正执行的策略」
是**同一段代码**，不会行为漂移：

```
                      ┌──────────────────────────┐
                      │   Strategy 信号核         │
                      │   panel ──> 目标权重时序   │
                      └────────────┬─────────────┘
                ┌──────────────────┼──────────────────┐
                ▼                  ▼                  ▼
     ┌──────────────────┐ ┌─────────────────┐ ┌──────────────────┐
     │ 向量化回测引擎     │ │ backtrader 引擎  │ │ 实盘 runner       │
     │ 快速扫参/walk-fwd │ │ 精细撮合验证      │ │ 取最后一行权重    │
     │                  │ │                 │ │ → 次日下单计划    │
     └──────────────────┘ └─────────────────┘ └──────────────────┘
```

**信号核契约（防未来函数的关键）**

- `compute_weights(panel)` 返回一个权重 DataFrame，index 与 panel 对齐，列为各标的。
- 第 D 行的权重**只能用 ≤ D 的数据**算出，代表「D 收盘决策、D+1 成交后要持有的仓位」。
  - 沿用你 `backtest_dual_ma` 里 `signal.shift(1)` 的思路。
- 三个引擎都遵守这条契约：
  - 向量化：`策略收益[D+1] = 权重[D] · 标的收益[D+1]`。
  - backtrader：第 D+1 根 bar 用 `order_target_percent` 调到 `权重[D]`。
  - 实盘：`权重时序.iloc[-1]`（用最新收盘算出）= 明日目标。

## 3. 策略输出抽象：目标权重组合

策略每次再平衡输出 `{标的: 权重}`，权重和 ≤ 1.0，剩余为现金。例如：

```python
{"513100": 0.50, "510300": 0.30, "511880": 0.20}  # 纳指 / 沪深300 / 货币(类现金)
```

- 单标的择时 = 该标的权重在 `{0, 1}` 之间切换的特例。
- 多 ETF 动量轮动 = 每期把权重压到排名靠前的几只上。
- 「目标权重 → 实际下单」的换算（取整到 100 份、现金校验、无交易带）统一由
  `core/portfolio.py` 处理，策略本身不关心股数和钱。

### 策略分层与 overlay

参见 `docs/strategies.md`：真实策略是「分层堆叠」——alpha 信号（方向）/ 环境过滤
（regime）/ 仓位风控 / 组合构建。对应到框架：

- **`Strategy` 信号核**：第 1 层 alpha，输出目标权重。
- **`Overlay`**：第 2、3 层，包在信号核外面、对权重做门控/缩放的可组合装饰器
  （如「波动率目标」「宏观 regime 过滤」「VIX risk-off」）。一个最终策略 =
  信号核 + 0~N 个 overlay。**不需要时就不挂**——简单策略依然简单。
- **`core/portfolio.py`**：第 4 层，把合成后的权重落地成订单。

overlay 与信号核一样遵守「不偷看未来」契约，也各自声明数据需求（见第 7 节）。

## 4. 目录结构

```
my_quant/
├── pyproject.toml
├── requirements.txt
├── README.md
├── .env                       # tushare token 等密钥（gitignored）
├── docs/
│   └── design.md              # 本文档
├── config/
│   ├── universe.py            # ETF/标的池（沿用 quant_learn 的 POOL 风格）
│   └── settings.py            # 路径、成本模型、初始资金、默认复权类型
├── my_quant/                  # 主包
│   ├── data/
│   │   ├── providers/         # 数据源提供方，一类一个，可插拔、可选
│   │   │   ├── base.py        # DataProvider 抽象接口（fetch / load）
│   │   │   ├── ohlcv.py       # 行情（tushare/akshare）—— 默认必备
│   │   │   ├── valuation.py   # 指数估值 PE/PB/股息率 —— 可选
│   │   │   ├── sentiment.py   # 两市成交额、北向资金 —— 可选
│   │   │   ├── macro_cn.py    # 国内宏观 LPR/MLF/社融/PMI —— 可选
│   │   │   └── macro_us.py    # 美债收益率/DXY/VIX/Fed —— 可选
│   │   ├── registry.py        # 类别 → provider 注册表，按 config 启用
│   │   ├── feature_store.py   # 按策略声明的需求装配特征，喂给信号核
│   │   └── store.py           # parquet 读写 + 数据新鲜度检查
│   ├── core/
│   │   ├── types.py           # Order / Fill / TargetWeights / Account / FeatureRef
│   │   ├── strategy.py        # Strategy 基类：信号核 + required_data() 声明
│   │   ├── overlay.py         # Overlay 抽象：环境过滤 / 波动率目标，可叠加在策略外
│   │   └── portfolio.py       # 目标权重 → 目标股数；再平衡 diff；无交易带
│   ├── strategies/
│   │   ├── buy_and_hold.py
│   │   ├── dual_ma.py         # 双均线，移植并改造成目标权重输出
│   │   └── rotation.py        # 多 ETF 动量轮动
│   ├── backtest/
│   │   ├── vector.py          # 向量化引擎（快速扫参/walk-forward）
│   │   ├── bt_engine.py       # backtrader 引擎入口
│   │   ├── bt_strategy.py     # 把信号核包成 bt.Strategy（order_target_percent）
│   │   ├── walk_forward.py    # 移植 quant_learn
│   │   └── metrics.py         # 年化/夏普/回撤/卡玛/换手率/超额
│   ├── live/
│   │   ├── ledger.py          # 持仓台账：trades + cash 流水，回放出持仓/现金/净值
│   │   ├── runner.py          # 实盘每日流程：load → 信号 → 下单计划
│   │   ├── order_plan.py      # 生成晨间下单清单（markdown + csv）
│   │   └── broker/
│   │       ├── base.py        # Broker 抽象接口
│   │       └── manual.py      # ManualBroker：当前阶段——出计划、等人工回填
│   │       # 后续：qmt.py 等真实券商适配，实现同一接口
│   └── reporting/
│       └── report.py          # 回测报告 + 实盘日报
├── data/                      # gitignored
│   ├── raw/                   # parquet 特征库：行情 + 估值/情绪/宏观（按类别分目录）
│   └── live/
│       ├── trades.csv         # 成交流水（append-only，唯一事实源）
│       ├── cash.csv           # 现金流水：入金/出金/分红
│       └── plans/             # 历史晨间下单计划存档
├── scripts/
│   ├── sync_data.py           # 晚上跑：增量下载当日行情
│   ├── run_backtest.py        # 跑单次回测
│   ├── run_sweep.py           # 参数扫描 / walk-forward
│   └── run_live.py            # 晚上跑：生成次日下单计划
└── tests/                     # 信号核无未来函数、台账回放、下单取整等
```

## 5. 关键数据结构

### 5.1 持仓台账（ledger）

**事实源是流水，持仓/现金/净值都由回放流水算出**——可审计、可重算。

`data/live/trades.csv`（证券成交，append-only）：

| date | symbol | action | shares | price | fee | note |
|------|--------|--------|--------|-------|-----|------|
| 2026-05-20 | 513100 | buy | 1000 | 1.523 | 5.0 | 按计划建仓 |

`data/live/cash.csv`（现金流水，append-only）：

| date | action | amount | note |
|------|--------|--------|------|
| 2026-05-19 | deposit | 100000 | 初始入金 |
| 2026-06-30 | dividend | 86.4 | 510300 分红 |

回放规则：

- `现金 = Σcash.amount − Σ(买入 shares·price+fee) + Σ(卖出 shares·price−fee)`
- `持仓[symbol] = Σ买入shares − Σ卖出shares`，均价同步累计
- `净值 = 现金 + Σ 持仓 · 最新收盘价`

接 API 后：成交回报直接 append 进 `trades.csv`，回放逻辑不变。

### 5.2 晨间下单计划

`data/live/plans/2026-05-20.md` —— 人读的日报：账户快照、信号说明、买卖建议。
`data/live/plans/orders_2026-05-20.csv` —— 可执行清单（含拆单与限价建议）：

| symbol | name | action | shares | tranches | limit_price | ref_price | est_amount | reason |
|--------|------|--------|--------|----------|-------------|-----------|------------|--------|
| 513100 | 纳指100ETF | buy | 1000 | 1 | 1.530 | 1.523 | 1530.0 | 目标 0.5 / 当前 0.2 |

- `shares`：股数取整到 100 份；卖出受 T+1 约束（不卖当日买入份额）。
- `limit_price`：限价建议——在参考价上叠加几个最小价位（tick）的缓冲，买单略高、
  卖单略低，避免市价单的坏成交；缓冲幅度可配置。
- `tranches`：拆单建议——把一笔拆成 N 个子单分批挂。5 万账户 + 流动性好的 ETF 通常
  = 1（无需拆）；标的流动性差、或单笔金额相对其日成交额偏大时才 > 1。
- **无交易带**：目标与当前权重偏离小于阈值（如 5%）时不生成订单，避免每天微调。

## 6. 日常工作流

**晚上（收盘后，你手动跑两条命令）**

1. 回填：若当天上午有成交，把实际成交价/数量记进 `trades.csv`。
2. `python scripts/sync_data.py` —— 按激活策略声明的数据需求增量下载当日数据
   （纯趋势策略只拉行情；带宏观/估值的策略才会去拉对应类别）。
3. `python scripts/run_live.py` —— 框架自动：
   - 回放 ledger 得到当前持仓 + 现金；
   - 加载最新面板数据，跑信号核，取最后一行 = 明日目标权重；
   - 与当前持仓 diff，输出 `plans/2026-05-20.md` 和 `orders_2026-05-20.csv`。

**次日上午（开盘后，你手动操作）**

4. 看下单清单，在券商 App 按建议下单。
5. 成交后记下实际成交（晚上回填，回到第 1 步）。

**周期性**：跑回测 / walk-forward 验证、调参。

> 接通交易 API 后：第 4、5 步由 `broker.submit()` 自动完成，前面的流程一字不改。

## 7. 数据层：可插拔的分类特征库

数据层不只存 OHLCV，而是一个**按类别组织、按需启用**的特征库。核心原则：
**策略声明自己要什么数据，框架只取这些**——不用宏观的策略，宏观数据源完全不参与，
晚间同步也不会去拉它。简单策略保持简单，零额外开销。

### 7.1 DataProvider 抽象

每个数据类别是一个 `DataProvider`，统一接口、各自封装数据源与存储：

| Provider | 类别 | 内容 | 数据源 | 默认 |
|---|---|---|---|---|
| `ohlcv` | 行情 | OHLCV、成交量、换手率 | tushare / akshare | **必备** |
| `valuation` | 估值 | 指数 PE / PB / 股息率 | tushare / akshare | 可选 |
| `sentiment` | 情绪 | 两市成交额、北向资金 | akshare | 可选 |
| `macro_cn` | 国内宏观 | LPR / MLF / 社融 / M2 / PMI | akshare | 可选 |
| `macro_us` | 美国宏观 | 美债收益率 / DXY / VIX / Fed | akshare / OpenBB | 可选 |

```python
class DataProvider(ABC):
    category: str
    def fetch(self, keys, start, end): ...   # 增量下载到 parquet
    def load(self, keys, start, end): ...    # 读 parquet → DataFrame
```

新增数据类别 = 加一个 provider 文件并在 `registry.py` 注册，不动其它代码。
行情类沿用 quant_learn：akshare `fund_etf_hist_em` 取的是**场内交易价**，纳指等
跨境 ETF 的 QDII 溢价已包含在内，适合回测。

### 7.2 策略声明数据需求

`Strategy` 和 `Overlay` 都实现 `required_data()`，返回一组 `FeatureRef(category, key)`：

```python
# 纯双均线：只要标的 OHLCV
def required_data(self):
    return [FeatureRef("ohlcv", s) for s in self.universe]

# 带宏观过滤的 overlay：额外声明
def required_data(self):
    return [FeatureRef("macro_us", "ust10y"), FeatureRef("macro_us", "vix")]
```

`feature_store` 把「信号核 + 所挂的所有 overlay」的需求求并集 → 解析到对应 provider
→ 装配成信号核看到的输入。**没声明却被访问的特征直接报错**，杜绝隐式依赖。

### 7.3 按需同步

- `sync_data.py` 读当前激活配置里所有策略的 `required_data()` 取并集 → 只同步用到的
  类别。纯趋势策略晚上同步只拉 OHLCV，秒级完成。
- `registry.py` / `config/settings.py` 控制哪些 provider 启用，可全局开关。

### 7.4 存储与复权

- parquet 存储：行情类 `data/raw/{source}/{asset}/{adjust}/{symbol}.parquet`，
  其它类别 `data/raw/{category}/{key}.parquet`。
- 复权：回测信号用 `hfq`（后复权，价格连续）；实盘下单计划用 `raw`（真实成交价）。
- 增量更新 + 新鲜度检查：`run_live` 前确认数据已更新到最近交易日，否则拦截。
- 宏观/估值数据有**发布滞后**：存储时记录「数据日期」与「可见日期」，回测按可见日期
  对齐，防未来函数。

## 8. 回测引擎

| | 向量化引擎（`backtest/vector.py`） | backtrader 引擎（`backtest/bt_engine.py`） |
|---|---|---|
| 用途 | 快速扫参、walk-forward | 上线前精细撮合验证 |
| 撮合 | 收盘价、连续权重、简化成本 | 次日开盘成交、整手取整、最低佣金 |
| 速度 | 快（适合上千次回测） | 慢（适合验证 1~2 个候选） |
| 共享 | 同一个信号核 `compute_weights` | 同一个信号核（预算权重后喂给 backtrader） |

两引擎共用同一份 `compute_weights` 输出，策略行为不会因引擎漂移。两者的差异是
**有意为之的真实性差距**，不是 bug：

- 向量化引擎在连续权重空间工作，是理想化基准（决策即时按收盘价成交）。
- backtrader 引擎按 `cheat_on_open` 在**次日开盘**成交、**整手取整**（100 份/手）、
  收**最低 5 元佣金**——更贴近 5 万账户的真实摩擦。
- 实测：高价 ETF（每手上万元）在 5 万账户里会因整手取整闲置可观现金，backtrader
  收益明显低于向量化——这正是 design.md 第 12 节标注的颗粒度问题，由 backtrader
  如实暴露。低价标的、恒定权重时两引擎高度一致，可作交叉校验。

实现要点（backtrader）：`Cerebro(cheat_on_open=True)` + 策略逻辑写在 `next_open()`；
用 `order_target_size` 落地整手目标股数；自定义 `CommInfoBase` 子类实现最低佣金下限。

绩效指标（`metrics.py`）：总收益、年化、年化波动、夏普、最大回撤、卡玛、胜率。

## 9. 成本模型（`config/settings.py` 统一配置）

- 佣金：双边，万分之 X，最低 5 元（可配）。
- 印花税：ETF 免（个股卖出千一，留作扩展）。
- 过户费：ETF 通常免。
- 滑点：按 bps 简化。

## 10. 技术选型

- Python 3.10+，沿用 conda 环境 `myTools`。
- 依赖：pandas / numpy / backtrader / akshare / tushare / matplotlib / seaborn / python-dotenv。
- 数据结构沿用 quant_learn 的 `dataclass` 风格，不引入 pydantic，保持轻量。
- 脚本参数解析用 argparse。

## 11. 实施阶段

| 阶段 | 内容 | 产出 |
|---|---|---|
| P0 骨架 & 数据层 | 目录、config、DataProvider 抽象 + ohlcv provider、feature_store、`sync_data` | 能按需增量下载 ETF 数据 |
| P1 信号核 & 向量化回测 | Strategy 基类（含 required_data）、dual_ma 改造、向量化引擎、metrics、walk-forward | 能对纳指/沪深300 ETF 跑回测出报告 |

> 估值/情绪/宏观 provider 与 overlay 不在 P0/P1 一次性铺开——等某个策略真正需要时
> 再逐个落地（provider 抽象已留好扩展点）。保持早期阶段精简。
| P2 backtrader 引擎 | bt_strategy 包装、bt_engine、双引擎交叉验证 | 候选策略精细验证 |
| P3 实盘半自动 | ledger、Broker 抽象、ManualBroker、run_live、order_plan | 晚上出计划、早上手动执行的闭环 |
| P4 接 API | 实现真实券商 Broker 适配，切换 broker | 自动下单，流程不变 |

## 12. 已确认参数（2026-05-19）

1. **初始资金**：5 万元（试水规模）。注意下面两个现实摩擦。
2. **ETF 标的池**：在 quant_learn 基础上扩充，见附录 A。
3. **台账存储**：CSV（`trades.csv` / `cash.csv`，易人工编辑回填）。
4. **下单计划**：给出拆单建议 + 限价建议（不止目标股数 + 参考价）。
5. **回测出图**：matplotlib + seaborn。

**5 万元的两个现实摩擦**（影响策略设计，不影响「能不能做」）：

- **100 份整手取整**：高价 ETF（国债 ETF、货币 ETF 每股约 100 元，1 手 ≈ 1 万元）
  在 5 万账户里仓位颗粒度太粗。→ 标的池优先选低价、流动性好的 ETF；risk-off 的
  「现金腿」直接用真实现金，不强制买货币 ETF。
- **5 元佣金下限**：单笔低于约 1 万元就会触发最低佣金，小额再平衡的成本占比偏高。
  → 低换手策略 + 无交易带来压成本，不要频繁微调仓位。

试水阶段 5 万足够——早期目标是验证「实盘行为 == 回测行为」和整条流程跑顺，不是赚钱。
跑顺、对策略有信心后再加资金即可。

## 附录 A：ETF 标的池草案

放进 `config/universe.py`，每只 ETF 记录 代码 / 名称 / 角色 / `t_plus`（0 或 1）/
类别。**代码、规模、流动性、T+0/T+1 规则在 P0 实现时逐一核对**——同类 ETF 有多只，
要挑规模大、流动性好的。

**核心池**（跨资产轮动 / 择时主战场，约 6 只）

| 代码 | 名称 | 角色 | 备注 |
|---|---|---|---|
| 510300 | 沪深300ETF | A 股大盘核心 | 华泰柏瑞，流动性最好；T+1 |
| 510500 | 中证500ETF | A 股中盘弹性 | 南方；T+1 |
| 159915 | 创业板ETF | A 股成长 | 易方达；T+1 |
| 513100 | 纳斯达克100ETF | 美股科技/成长 | 国泰，跨境多为 T+0 |
| 513500 | 标普500ETF | 美股大盘 | 博时，跨境多为 T+0 |
| 518880 | 黄金ETF | 商品/避险腿 | 华安；T+0 |

**行业/主题池**（做行业轮动时再启用，默认不参与）

| 代码 | 名称 | 角色 |
|---|---|---|
| 588000 | 科创50ETF | A 股硬科技 |
| 512880 | 证券ETF | 券商，高 beta、市场情绪放大器 |
| 512760 | 半导体ETF | 半导体/芯片 |
| 512170 | 医疗ETF | 医药医疗 |
| 159928 | 消费ETF | 主要消费 |

**避险腿**：默认用**真实现金**；如需赚货币收益再考虑国债 ETF（注意每股约 100 元、
整手金额大，5 万账户里颗粒度粗）。
