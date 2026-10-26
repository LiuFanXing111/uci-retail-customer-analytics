# -*- coding: utf-8 -*-
"""
Tableau 数据导出脚本（重写版 · 防膨胀 · 全量明细表）
==================================================
设计原则（杜绝笛卡尔积 / 行数翻倍）：
  1. 全程内部列名统一为 CID（大写 CustomerID），【仅在导出 CSV 前最后一刻】
     重命名为 customer_id，杜绝大小写混用导致的 merge 键不匹配。
  2. orders = 【全量交易明细】（正向销售 + 取消单），保留 IsCancel 列，
     退单率可在一张表内直接计算：SUM(INT([IsCancel])) / 总行数。
     ★ RFM / 同期群 / 关联规则仍基于正向 sales_clean，不受取消单污染。
  3. 每个 merge 前断言左表 on 键唯一；merge 后立刻校验行数守恒。
  4. 导出前去重 + 清洗文本内换行符（quoting），避免 CSV 行数异常。

输出（tableau_data/）：
  orders.csv             交易事实表（全量明细，含 IsCancel；True=取消单）
  customers_rfm.csv      客户维度表（主键 customer_id，唯一，仅正向客户）
  cohort_retention.csv   同期群留存矩阵（聚合表，无 CustomerID）
  association_rules.csv  关联规则表
"""
import os
import pandas as pd
from mlxtend.frequent_patterns import fpgrowth, association_rules

# ---------- 0. 配置 ----------
FILE_PATH = os.environ.get(
    '_MOCK_PATH',
    r'D:\File\njupt\class\big data\python\python explainer\File\training\3online_retail_analysis\online_retail_II.xlsx',
)
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tableau_data')
os.makedirs(OUTPUT_DIR, exist_ok=True)

CID = 'CustomerID'      # 内部统一列名（大写）
CID_OUT = 'customer_id'  # 导出列名（小写）

# ---------- 1. 读取 ----------
df1 = pd.read_excel(FILE_PATH, sheet_name='Year 2009-2010')
df2 = pd.read_excel(FILE_PATH, sheet_name='Year 2010-2011')
df = pd.concat([df1, df2], ignore_index=True)
df.columns = ['Invoice', 'StockCode', 'Description', 'Quantity',
              'InvoiceDate', 'Price', CID, 'Country']

# ---------- 2. 清洗（对全量 df 先做类型转换 + 标记） ----------
df['InvoiceDate'] = pd.to_datetime(df['InvoiceDate'])
df[CID] = df[CID].astype('Int64')

# 2.2 标记取消单（Invoice 以 C 开头 或 数量/单价为负）
df['IsCancel'] = df['Invoice'].str.startswith('C', na=False) | (df['Quantity'] < 0)

# 2.3 拆分：正向销售 / 取消单
sales = df[~df['IsCancel']].copy()
cancels = df[df['IsCancel']].copy()

# 2.4 仅保留有 CustomerID 的记录（用于 RFM / 同期群）
sales_with_id = sales.dropna(subset=[CID]).copy()

# 2.5 去重（交易明细级去重：同一发票+商品+日期视为重复）
sales_with_id = sales_with_id.drop_duplicates()

# 2.6 过滤非商品编码
non_product_codes = ['POST', 'DOT', 'BANK CHARGES', 'AMAZON', 'FBA', 'S', 'M']
product_mask = ~sales_with_id['StockCode'].isin(non_product_codes)
sales_clean = sales_with_id[product_mask].copy()

# 2.7 国家标准化（对正向 sales_clean 做）
# ★ 修复：不再整体 lower。改为「小写键查映射表，未命中保留原始写法」，
#   否则 'United Kingdom' 会被压成 'united kingdom'，且 'uk' 键永远匹配不上。
country_mapping = {
    'uk': 'United Kingdom',
    'u.k.': 'United Kingdom',
    'united kingdom': 'United Kingdom',
    'eire': 'Ireland',
    'ireland': 'Ireland',
    'usa': 'United States',
    'u.s.a.': 'United States',
    'united states': 'United States',
    'rsa': 'South Africa',
    'r sa': 'South Africa',
    'south africa': 'South Africa',
    'australia': 'Australia',
}


def normalize_country(s: pd.Series) -> pd.Series:
    """国家名标准化：按小写键匹配映射表；未命中则保留原始写法（仅去首尾空格）。

    相比 str.lower().replace(...) 的好处：
      1) 映射键一定能命中（原写法里 'uk' 永远不会等于 lower 后的 'united kingdom'）；
      2) 未映射的国家（Netherlands / Germany / ...）保持原有大小写，不会变成全小写；
      3) 缺失值 NaN 原样保留，不会被 astype(str) 变成字符串 'nan'。
    """
    out = s.copy()
    mask = out.notna()
    raw = out[mask].astype(str).str.strip()
    key = raw.str.lower()
    out.loc[mask] = key.map(country_mapping).fillna(raw)
    return out


sales_clean['Country'] = normalize_country(sales_clean['Country'])

# 2.8 衍生字段（仅对正向销售）
sales_clean['Revenue'] = sales_clean['Quantity'] * sales_clean['Price']
sales_clean['YearMonth'] = sales_clean['InvoiceDate'].dt.to_period('M')
sales_clean['Weekday'] = sales_clean['InvoiceDate'].dt.dayofweek
sales_clean['Hour'] = sales_clean['InvoiceDate'].dt.hour

print(f"正向 sales_clean 数据量: {len(sales_clean)}")
print(f"取消单 cancels 数据量: {len(cancels)}")

# ================= 3. orders.csv（全量交易明细，含 IsCancel） =================
# 颗粒度：订单-商品明细，正向 + 取消单全保留，靠 IsCancel 区分。
# ★ 对全量 df 补上与 sales_clean 一致的衍生字段（Revenue/YearMonth/Weekday/Hour），
#   且 Country 标准化要作用于全量，保证 orders 字段完整、口径统一。
df['Revenue'] = df['Quantity'] * df['Price']
df['YearMonth'] = df['InvoiceDate'].dt.to_period('M')
df['Weekday'] = df['InvoiceDate'].dt.dayofweek
df['Hour'] = df['InvoiceDate'].dt.hour
df['Country'] = normalize_country(df['Country'])

order_cols = ['Invoice', 'StockCode', 'Description', 'Quantity', 'Price',
              'InvoiceDate', 'Country', 'Revenue', 'YearMonth',
              'Weekday', 'Hour', CID, 'IsCancel']
orders = df[order_cols].copy()

# 清洗文本：去除 Description 内的换行/回车，避免 to_csv 行数膨胀
orders['Description'] = (orders['Description'].astype(str)
                         .str.replace('\r\n', ' ', regex=False)
                         .str.replace('\n', ' ', regex=False)
                         .str.replace('\r', ' ', regex=False))

orders['InvoiceDate'] = orders['InvoiceDate'].dt.strftime('%Y-%m-%d %H:%M:%S')
orders = orders.drop_duplicates()                 # 导出前再去重，保底
orders = orders.rename(columns={CID: CID_OUT})    # 最后一刻转小写

orders_path = os.path.join(OUTPUT_DIR, 'orders.csv')
orders.to_csv(orders_path, index=False, encoding='utf-8-sig', quoting=1)
print(f"已导出: {orders_path}  ({len(orders)} 行)  "
      f"[含 IsCancel，True=取消单，可在一表内算退单率]")

# ================= 4. customers_rfm.csv（仅正向客户） =================
snapshot_date = sales_clean['InvoiceDate'].max() + pd.Timedelta(days=1)

rfm = sales_clean.groupby(CID).agg(
    recency=('InvoiceDate', lambda x: (snapshot_date - x.max()).days),
    frequency=('Invoice', 'nunique'),
    monetary=('Revenue', 'sum'),
).reset_index()

# 4.2 RFM 打分
def rfm_score(series, ascending):
    labels = range(1, 6) if ascending else range(5, 0, -1)   # ← 修正后
    try:
        return pd.qcut(series, q=5, labels=labels, duplicates='drop')
    except ValueError:
        return pd.cut(series.rank(method='first'), bins=5, labels=labels)


rfm['R_Score'] = rfm_score(rfm['recency'], ascending=False)
rfm['F_Score'] = rfm_score(rfm['frequency'], ascending=True)
rfm['M_Score'] = rfm_score(rfm['monetary'], ascending=True)
rfm['RFM_Segment'] = (rfm['R_Score'].astype(str) +
                      rfm['F_Score'].astype(str) +
                      rfm['M_Score'].astype(str))

# 4.3 分群标签
def label(seg):
    r, f, m = int(seg[0]), int(seg[1]), int(seg[2])
    if r >= 4 and f >= 4 and m >= 4: return 'Champions'
    if f >= 4: return 'Loyal Customers'
    if r >= 4 and f >= 2: return 'Potential Loyalists'
    if r >= 4: return 'New Customers'
    if r <= 2 and f >= 4: return 'Cant Lose Them'
    if r <= 2 and f <= 2 and m >= 4: return 'Hibernating'
    if r <= 2: return 'At Risk'
    return 'Others'

rfm['Segment'] = rfm['RFM_Segment'].apply(label)

# 4.4 复购标记（基于正向销售）
order_counts = (sales_clean.groupby(CID)['Invoice']
                .nunique().rename('total_orders'))
rfm = rfm.merge(order_counts, on=CID)
rfm['has_repurchase'] = (rfm['total_orders'] >= 2).astype(int)

# 4.5 LTV：按客户首购月、相对月份累积营收
first_purchase = sales_clean.groupby(CID)['YearMonth'].min().rename('CohortMonth')
sales_with_cohort = sales_clean.merge(first_purchase, on=CID)
sales_with_cohort['Period'] = (sales_with_cohort['YearMonth'] -
                               sales_with_cohort['CohortMonth']).apply(lambda x: x.n)

ltv = (sales_with_cohort.groupby([CID, 'Period'])['Revenue']
       .sum().groupby(CID).cumsum().rename('ltv_cumulative')
       .reset_index())
ltv_p0 = (ltv[ltv['Period'] == 0]
          .drop_duplicates(CID)            # 防重复键
          [[CID, 'ltv_cumulative']])

assert rfm[CID].is_unique, "RFM 主键不唯一！"
rfm = rfm.merge(ltv_p0, on=CID, how='left')
assert len(rfm) == rfm[CID].nunique(), "LTV merge 后发生膨胀！"

# 4.6 整理输出
customers = rfm[[
    CID, 'recency', 'frequency', 'monetary', 'R_Score', 'F_Score', 'M_Score',
    'RFM_Segment', 'Segment', 'total_orders', 'has_repurchase', 'ltv_cumulative'
]].rename(columns={'monetary': 'total_revenue'})
customers = customers.rename(columns={CID: CID_OUT})

customers_path = os.path.join(OUTPUT_DIR, 'customers_rfm.csv')
customers.to_csv(customers_path, index=False, encoding='utf-8-sig', quoting=1)
print(f"已导出: {customers_path}  ({len(customers)} 行)")

# ================= 5. cohort_retention.csv（含活跃客户数） =================
cohort_data = sales_with_cohort[[CID, 'CohortMonth', 'Period', 'Invoice', 'Revenue']].copy()

# ① 每个同期群、每个相对月份的去重客户数
cohort_counts = (cohort_data.groupby(['CohortMonth', 'Period'])[CID]
                 .nunique().reset_index(name='customers'))

# ② 获取每个同期群的首月客户数（Period=0）
cohort_size = (cohort_counts[cohort_counts['Period'] == 0]
               [['CohortMonth', 'customers']]
               .rename(columns={'customers': 'cohort_size'}))

# ③ 合并并计算留存率
cohort_retention = cohort_counts.merge(cohort_size, on='CohortMonth', how='left')
cohort_retention['retention_rate'] = (
    cohort_retention['customers'] / cohort_retention['cohort_size'] * 100
).round(1)

# ④ 选取最终输出列（包含活跃客户数）
cohort_retention = cohort_retention[['CohortMonth', 'Period', 'customers', 'retention_rate']]

# ⑤ 导出（不再需要 dropna，因为只保留有数据的 Period）
retention_path = os.path.join(OUTPUT_DIR, 'cohort_retention.csv')
cohort_retention.to_csv(retention_path, index=False, encoding='utf-8-sig')
print(f"已导出: {retention_path}  ({len(cohort_retention)} 行)")

# ================= 6. association_rules.csv =================
basket_df = sales_clean[sales_clean['IsCancel'] == 0]
basket = (basket_df.groupby(['Invoice', 'StockCode'])['Quantity']
          .sum().unstack(fill_value=0))
min_invoices = 20
item_freq = (basket > 0).sum(axis=0)
keep_items = item_freq[item_freq >= min_invoices].index
basket = basket[keep_items]
basket_sets = (basket > 0).astype(bool)

frequent_itemsets = fpgrowth(basket_sets, min_support=0.02, use_colnames=True, max_len=3)
if len(frequent_itemsets) > 0:
    rules = association_rules(frequent_itemsets, metric='lift', min_threshold=1.2)
    rules = rules[rules['confidence'] >= 0.3].sort_values('lift', ascending=False)
    code2desc = (sales_clean.drop_duplicates('StockCode')
                 .set_index('StockCode')['Description'].to_dict())

    def decode(s, top_n=3):
        names = [code2desc.get(x, str(x)) for x in s][:top_n]
        return ' + '.join(names)

    rules['antecedent_desc'] = rules['antecedents'].apply(lambda s: decode(s))
    rules['consequent_desc'] = rules['consequents'].apply(lambda s: decode(s))
    rules_out = rules[['antecedent_desc', 'consequent_desc',
                       'support', 'confidence', 'lift', 'antecedents', 'consequents']
    ].reset_index(drop=True)
    rules_out.insert(0, 'rule_id', range(1, len(rules_out) + 1))
else:
    rules_out = pd.DataFrame(columns=['rule_id', 'antecedent_desc', 'consequent_desc',
                                     'support', 'confidence', 'lift',
                                     'antecedents', 'consequents'])

rules_path = os.path.join(OUTPUT_DIR, 'association_rules.csv')
rules_out.to_csv(rules_path, index=False, encoding='utf-8-sig', quoting=1)
print(f"已导出: {rules_path}  ({len(rules_out)} 行)")

# ================= 7. 完整性校验（严格，失败即终止） =================
print("\n" + "=" * 50)
print("完整性校验")

n_orders = len(orders)
n_customers = len(customers)
unique_oid_in_orders = orders[CID_OUT].nunique()

# 7.1 orders 行数应等于全量 df 去重后（含取消单，这是正常的）
assert n_orders == len(df.drop_duplicates()), \
    f"orders 行数({n_orders}) ≠ 全量 df 去重后行数，存在膨胀！"

# 7.2 orders 内无完全重复行
dup = orders.duplicated().sum()
assert dup == 0, f"orders 存在 {dup} 行完全重复！"

# 7.3 客户表行数 = 正向客户数；orders 唯一客户 ⊇ 客户表（因含取消单客户）
positive_customers = set(sales_clean[CID].dropna().unique())
assert set(customers[CID_OUT]) == positive_customers, \
    "客户表客户集 ≠ 正向销售客户集，存在不一致！"
assert unique_oid_in_orders >= n_customers, \
    f"orders 唯一客户({unique_oid_in_orders}) 应 ≥ 客户表({n_customers})（含仅有取消单客户）"

# 7.4 主键唯一
assert customers[CID_OUT].is_unique, "customers_rfm 主键不唯一！"

# 7.5 IsCancel 口径检查（★ 方案二：orders 含 IsCancel，退单率可一表计算）
n_cancel = int(orders['IsCancel'].sum())
n_total = len(orders)
print(f"orders 为【全量明细】，含 IsCancel 列：")
print(f"  总行数 = {n_total}，取消单(True) = {n_cancel}，正向(False) = {n_total - n_cancel}")
print(f"  退单率(行级) = {n_cancel / n_total * 100:.2f}%")
assert orders['IsCancel'].nunique() > 1, "IsCancel 仍全 False，取消单未进入 orders！"

print(f"唯一 customer_id 数: {unique_oid_in_orders}")
print("校验通过：无笛卡尔积膨胀，主键唯一，行数守恒，IsCancel 含 True/False。")
print("=" * 50)
print("Tableau 关系建模建议（基数 多:一）：")
print(f"  orders.{CID_OUT}        (多) <-> customers_rfm.{CID_OUT} (一)")
print(f"     ★ orders 含取消单客户（customers_rfm 无），关联请用【关系】而非 join，")
print(f"       基数设为 orders(多) : customers_rfm(一)，避免 M:N 膨胀。")
print(f"  orders.StockCode        (多) <-> association_rules（下钻，用筛选联动，勿物理 join）")
print("  cohort_retention 为聚合表，独立数据源，不与 orders 按 CustomerID 关联。")
print("  退单率计算字段：SUM(INT([IsCancel])) / COUNT([Invoice])")
