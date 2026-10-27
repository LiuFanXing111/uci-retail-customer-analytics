# UCI Online Retail II · 在线零售经营分析

一家英国在线零售商的两年交易流水（1,067,371 行 / 25 个月），从数据清洗到经营诊断、客户分层、商品结构、召回成本测算的完整分析。

结论用一句话概括：**这是一门规模稳定、但没有自然增长的生意；收入集中在英国和年末两个月，收缩发生在获客端而不是留存端。**

数据集：[UCI Machine Learning Repository · Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii)（CC BY 4.0）

**在线看**：https://liufanxing111.github.io/uci-retail-customer-analytics/ （图表、结论、报告下载都在这一页）

---

## 关键结论

| 结论 | 数字 |
|---|---|
| 规模稳定但无自然增长 | 两年 GMV £17.07M，有效订单 36,639，客单价 £465.98；2010 年 £8.22M → 2011 年 £8.17M（−0.6%） |
| 波动由季节驱动而非趋势 | 11 月 GMV 比 24 个月均值高 66.1%；剔除末期残缺月后月度区间 £44 万—£116 万 |
| 收入高度集中 | 英国占 83.7%；10—11 月合计占全年 26.0% |
| 取消金额极度集中，均值监控无效 | 取消率 16.64%（单量）／4.22%（金额）；单笔最大占取消总额 23.4%，Top10 占 44.4% |
| 留存没有恶化 | 同期群次月留存 24 批加权 23.1%；只剔除观察窗不完整的两个末月批次后，2010 年 19.9% → 2011 年 23.6%（z=2.81） |
| 收缩在获客端 | 同月新增客户月均从 300 人降到 137 人，2011 年 11 个月无一月同比转正 |
| 商品是长尾而非爆款 | 1,003 个 SKU 贡献 80% 营收；Top10 SKU 仅占营收 8.1% |
| 滞销清退的收益要分层看 | 1,404 个滞销 SKU（占 30.4%）两年只贡献 7.22% GMV；清 C 类伤 1.8%，A 类 69 个要先查断货 |

完整推演过程在 [`reports/`](reports/) 的 31 页报告里。

---

## 图表

**月度 GMV：季节性主导，年度总量持平**

<img src="https://liufanxing111.github.io/uci-retail-customer-analytics/figures/fig1_monthly_gmv.png" width="760">

**取消金额集中度：前 10 张单占四成四**

<img src="https://liufanxing111.github.io/uci-retail-customer-analytics/figures/fig2_cancel.png" width="640">

**24 个同期群的次月留存：置信区间大面积重叠，没有单调下滑**

这张图推翻了「留存一年掉四分之三」的直觉结论，详见下文「一个被推翻的结论」。

<img src="https://liufanxing111.github.io/uci-retail-customer-analytics/figures/fig3_cohort_retention.png" width="760">

**同月新增客户：2011 年每个月都低于 2010 年**

<img src="https://liufanxing111.github.io/uci-retail-customer-analytics/figures/fig4_new_customer.png" width="720">

**商品营收累计曲线：A 类是千级商品池，不是少数爆款**

<img src="https://liufanxing111.github.io/uci-retail-customer-analytics/figures/fig5_pareto.png" width="640">

**召回 ROI 敏感性网格**

<img src="https://liufanxing111.github.io/uci-retail-customer-analytics/figures/fig6_roi_grid.png" width="640">

**RFM 七层：人数与营收的错位**

<img src="https://liufanxing111.github.io/uci-retail-customer-analytics/figures/fig7_rfm.png" width="720">

Tableau 六页仪表盘见 [`dashboard/`](dashboard/)。

---

## 一个被推翻的结论

初版分析写的是「次月留存从 2009-12 批次的 35.3% 降到 2010-12 批次的 9.2%，一年掉四分之三」。复核时按批次人数拆开看，这个说法不成立：

| 批次 | 人数 | 次月留存 | 95% 置信区间 | 留存人数 |
|---|---|---|---|---|
| 2009-12 | 952 | 35.3% | 32.3% — 38.3% | 336 |
| 2010-12 | 76 | 9.2% | 2.7% — 15.7% | 7 |

两端不可比。2010-12 批次只有 76 人，因为数据止于 2011-12-09，这个批次只有 9 天的观察窗口，且多数是回头客而非纯新客；9.2% 只对应 7 个人，置信区间宽达 13 个百分点。而 2009-12 是数据首月，含商家在数据开始前已积累的客户。

把 24 个批次全部算上，2010 年各批在 15.7%—25.9% 之间，2011 年在 14.1%—31.7% 之间，没有下滑趋势。按年加权后，2011 年反而略高于 2010 年。

构成效应（按 2010 年批次结构做直接标准化）只解释了 −2.21 个百分点，缺口全部来自基数不可比。**真正的变化在获客：同月新增客户从月均 300 人降到 137 人。**

这段复核过程留在 [`src/check_retention.py`](src/check_retention.py)，可以复现。

---

## 方法与口径

### 清洗链条

```
原始 1,067,371 行（两个 sheet 合并）
  → 保留 Quantity > 0 且 Price > 0   剔除退货与零负价
  → 剔除 CustomerID 为空            留存/客户结构类指标的分母
  → 按七列去重                       两表在 2010-12-01~09 重叠，1,088 张发票
  → 剔除非商品编码                    POST / BANK CHARGES / AMAZONFEE / Manual / DOT 等
= 有效订单 36,639 ／ 客户 5,861 ／ GMV £17,073,078
```

字段口径全部记录在 [`output/metric_dictionary.csv`](output/metric_dictionary.csv)，19 项指标逐条写明定义、统计范围与数据来源。

### 用到的方法

- **同期群留存**：按首购月份分 24 个队列，二项分布正态近似算 95% 置信区间；用直接标准化做构成分解
- **RFM 七层分层**：R / F / M 三维打分后按业务规则切分，与生命周期阶段交叉验证
- **ABC 分级**：按 SKU 营收累计曲线切 80% / 15% / 5%，叠加动销状态识别滞销
- **FP-Growth 关联规则**：mlxtend，支持度筛选后保留 50 条（实为 25 组正反各一条），补算覆盖订单数
- **召回成本收益测算**：uplift 假设 × 客单价 × 触达人数 − 券成本，做 4×4 的 uplift-成本敏感性网格
- **实验样本量**：按两比例检验反推每组所需人数，用来检验「跑一个月看效果」是否可行

### 两个统计上的坑

**取消金额不能看月度均值。** 2011-12 只有 9 天数据，这 9 天里取消金额有 17.4 万英镑，其中 97% 来自同一笔订单（23843 PAPER CRAFT, LITTLE BIRDIE，单笔 £168,470）。一笔大额取消就能把月均值拉飞，所以监控要按单笔阈值设，而不是偏离均值的百分比。

**「跑一个月按实际分布校准」站不住。** 30 天二次购买率基线实测 22.61%（首单后有完整 30 天观察窗的 5,691 人中有 1,287 人复购）。在 α=0.05、power=0.8 下，要测出 +3pp 每组需要 3,188 人，按月均 137 个新客要跑 46 个月；测 +10pp 每组 310 人，两个月能跑完。定向召回方案只有 430 人，连 5pp 都测不出来。所以这条建议改成先追大颗粒度改造，把「这套触达有没有用」验证掉，再谈小幅优化。

---

## 目录结构

```
.
├── src/                        分析脚本
│   ├── prepare_data.py         合并两个 sheet，生成缓存
│   ├── paths.py                统一路径
│   ├── analysis1.py            清洗 + 探索 + FP-Growth
│   ├── analysis2.py            运营指标体系（主脚本，产出全部 CSV）
│   ├── export_tableau_data.py  导出 Tableau 数据源
│   ├── check_caliber.py        复现报告口径，断言订单数/客户数
│   ├── compute.py              同期群分解、月度指标
│   ├── check_retention.py      留存置信区间与分年加权
│   ├── power_30d.py            实验样本量反推
│   ├── gap_numbers.py          滞销营收、规则覆盖、价值×沉默矩阵
│   ├── draw.py / redraw.py     图表
│   └── dup_probe.py            去重口径诊断
├── output/                     20 个分析结果 CSV + 指标字典
├── figures/                    报告用图
├── reports/                    31 页分析报告（docx）
├── dashboard/                  Tableau 打包工作簿（.twbx）
└── data/README.md              数据获取说明
```

---

## 复现

```bash
pip install -r requirements.txt

# 1) 下载数据放到 data/ 下（见 data/README.md）
# 2) 生成中间缓存（约 40 秒）
python src/prepare_data.py

# 3) 复现报告口径，会断言 36,639 单 / 5,861 客户，对不上直接报错
python src/check_caliber.py

# 4) 跑完整指标体系，输出 CSV 到 output/
python src/analysis2.py

# 5) 重画图表到 figures/
python src/draw.py && python src/redraw.py
```

`src/check_caliber.py` 里有两处硬断言（订单数、客户数），口径对不上会直接失败，不会静默产出错误数字。

顺带说一个已知的口径差：脚本复现出的 GMV 是 £17,072,526，报告正文写的是 £17,073,078，相差 £551.54（0.0032%）。这个差额来自非商品编码清单里几个小额科目（`D`、`DOT`、`BANK CHARGES`）的取舍，两种清单组合都试过，消不掉。订单数和客户数两个主键是精确命中的，所以客户结构与留存类指标不受影响；受影响的只有 GMV 相关的绝对金额，量级在万分之三。这类差异留在明面上比糊过去好，至少下次有人接着做的时候知道从哪里查。

---

## 局限

- **没有成本数据。** 数据里没有进货价，所以毛利、库存资金占用、清仓损失都算不成金额，建议三只能停在「释放展示位」这个层面。
- **没有活动标记。** 无法识别促销期，也无法做真实的 A/B 复盘，所有 uplift 都是假设而非实测。
- **RFM 分层规则不在脚本里。** 报告用的是业务分箱（Champions 1,191 人），而 `analysis1.py` 用 qcut 等频分箱会得到 1,282 人。两套规则并存，报告里已注明，后续应把业务分箱固化到代码。
- **关联规则的置信度不等于增量。** 买 A 的人买 B 的概率高，不代表推荐 B 就能提升转化，真实 uplift 要靠实验测。
- **观察期短。** 25 个月只够看到一个完整的年度周期，季节性结论需要第三年数据验证。

---

## 数据来源

Chen, D. (2015). *Online Retail II* [Dataset]. UCI Machine Learning Repository. DOI: [10.24432/C5CG6D](https://doi.org/10.24432/C5CG6D). CC BY 4.0.
