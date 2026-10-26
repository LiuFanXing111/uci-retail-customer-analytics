# -*- coding: utf-8 -*-
# ============================================
# 在线零售数据分析
# ============================================
import os
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # 无界面环境也能保存图片
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import timedelta
from mlxtend.frequent_patterns import fpgrowth, association_rules
import warnings
warnings.filterwarnings('ignore')

# 输出目录（项目根下的 output/）
_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(_PROJ_ROOT, 'output')
os.makedirs(OUT_DIR, exist_ok=True)

# ============================================
# 1. 读取数据（合并两个 sheet）
# ============================================
# 数据获取方式见 data/README.md；也可用环境变量 UCI_DATA 指向别处
file_path = os.environ.get(
    'UCI_DATA', os.path.join(_PROJ_ROOT, 'data', 'online_retail_II.xlsx'))
df1 = pd.read_excel(file_path, sheet_name='Year 2009-2010')
df2 = pd.read_excel(file_path, sheet_name='Year 2010-2011')
df = pd.concat([df1, df2], ignore_index=True)

df.columns = ['Invoice', 'StockCode', 'Description', 'Quantity', 'InvoiceDate',
              'Price', 'CustomerID', 'Country']

# 建立编码映射（用于购物篮结果可读化）
code2desc = (df.dropna(subset=['Description'])
             .drop_duplicates('StockCode')
             .set_index('StockCode')['Description']
             .to_dict())

# ============================================
# 2. 初始探索
# ============================================
print("Shape:", df.shape)
print("\n缺失统计:\n", df.isnull().sum())

# ============================================
# 3. 数据清洗
# ============================================
df['InvoiceDate'] = pd.to_datetime(df['InvoiceDate'])
df['CustomerID'] = df['CustomerID'].astype('Int64')

# 3.1 标记取消单（以 C 开头 或 数量/单价为负的都算取消）
df['IsCancel'] = ((df['Invoice'].astype(str).str.startswith('C')) |
                  (df['Quantity'] < 0) | (df['Price'] < 0)).astype(int)

# 3.2 分离销售单（这里直接剔除取消单，保证 GMV/LTV 准确）
sales = df[(df['Quantity'] > 0) & (df['Price'] > 0)].copy()

# 3.3 只保留有 CustomerID 的记录用于 RFM
sales_with_id = sales.dropna(subset=['CustomerID']).copy().drop_duplicates()

# 3.4 过滤非商品编码
non_product_codes = ['POST', 'DOT', 'BANK CHARGES', 'AMAZON', 'FBA', 'S', 'M']
sales_clean = sales_with_id[~sales_with_id['StockCode'].isin(non_product_codes)].copy()

# 3.5 国家标准化（先 lower 再 replace，映射才能命中）
country_mapping = {
    'uk': 'United Kingdom', 'eire': 'Ireland', 'usa': 'United States',
    'r sa': 'South Africa', 'australia': 'Australia',
}
sales_clean['Country'] = (sales_clean['Country'].astype(str)
                          .str.strip().str.lower().replace(country_mapping))

# 3.6 衍生字段
sales_clean['Revenue'] = sales_clean['Quantity'] * sales_clean['Price']
sales_clean['YearMonth'] = sales_clean['InvoiceDate'].dt.to_period('M')
sales_clean['Weekday'] = sales_clean['InvoiceDate'].dt.dayofweek
sales_clean['Hour'] = sales_clean['InvoiceDate'].dt.hour

cancels = df[df['IsCancel'] == 1]
print(f"\n清洗后数据量: {len(sales_clean)}")
print(f"取消单量: {len(cancels)}")

# ============================================
# 4. 总体业务概览
# ============================================
total_gmv = sales_clean['Revenue'].sum()
total_orders = sales_clean['Invoice'].nunique()
total_customers = sales_clean['CustomerID'].nunique()
avg_order_value = total_gmv / total_orders
print(f"总GMV: {total_gmv:.2f}, 总订单数: {total_orders}, "
      f"客户数: {total_customers}, 客单价: {avg_order_value:.2f}")

# ============================================
# 5. RFM 用户分层（完整分群）
# ============================================
snapshot_date = sales_clean['InvoiceDate'].max() + timedelta(days=1)
rfm = sales_clean.groupby('CustomerID').agg(
    Recency=('InvoiceDate', lambda x: (snapshot_date - x.max()).days),
    Frequency=('Invoice', 'nunique'),
    Monetary=('Revenue', 'sum'))


def rfm_score(series, ascending=True):
    labels = range(1, 6) if ascending else range(5, 0, -1)
    try:
        return pd.qcut(series, q=5, labels=labels, duplicates='drop')
    except ValueError:
        return pd.cut(series.rank(method='first'), bins=5, labels=labels)


rfm['R'] = rfm_score(rfm['Recency'], ascending=False).astype(int)
rfm['F'] = rfm_score(rfm['Frequency'], ascending=True).astype(int)
rfm['M'] = rfm_score(rfm['Monetary'], ascending=True).astype(int)
rfm['RFM_Segment'] = rfm['R'].astype(str) + rfm['F'].astype(str) + rfm['M'].astype(str)


def label(r, f, m):
    """完整 RFM 分群逻辑"""
    if r >= 4 and f >= 4 and m >= 4:
        return 'Champions'
    if f >= 4:
        return 'Loyal Customers'
    if r >= 4 and f >= 2:
        return 'Potential Loyalists'
    if r >= 4 and f <= 1:
        return 'New Customers'
    if r <= 2 and f >= 4:
        return 'Cant Lose Them'
    if r <= 2 and f <= 2 and m >= 4:
        return 'Hibernating'
    if r <= 2:
        return 'At Risk'
    return 'Others'


rfm['Segment'] = [label(r, f, m) for r, f, m in zip(rfm['R'], rfm['F'], rfm['M'])]
print("\n=== RFM 分群人数 ===")
print(rfm['Segment'].value_counts())

# ============================================
# 5.1 分层营收结构（按 Segment 聚合营收）
# ============================================
seg_rev = (sales_clean.merge(rfm['Segment'], left_on='CustomerID', right_index=True)
           .groupby('Segment')
           .agg(Customers=('CustomerID', 'nunique'),
                Orders=('Invoice', 'nunique'),
                Revenue=('Revenue', 'sum')))

seg_rev['CustShare%']    = (seg_rev['Customers'] / seg_rev['Customers'].sum() * 100).round(1)
seg_rev['RevShare%']     = (seg_rev['Revenue']   / seg_rev['Revenue'].sum()   * 100).round(1)
seg_rev['ARPU']          = (seg_rev['Revenue']   / seg_rev['Customers']).round(2)
seg_rev['AOV']           = (seg_rev['Revenue']   / seg_rev['Orders']).round(2)
seg_rev = seg_rev.sort_values('Revenue', ascending=False)
seg_rev['CumRevShare%']  = seg_rev['RevShare%'].cumsum().round(1)

print("\n=== 分层营收结构 ===")
print(seg_rev.to_string())

# 头部客群（Champions + Loyal）集中度 —— 简历帕累托句要用的两个数
top2 = seg_rev[seg_rev.index.isin(['Champions', 'Loyal Customers'])]
print(f"\n头部客群(Champions+Loyal) 客户占比: {top2['CustShare%'].sum():.1f}%")
print(f"头部客群(Champions+Loyal) 营收占比: {top2['RevShare%'].sum():.1f}%")
print(f"头部客群 ARPU 为全体的 {top2['Revenue'].sum()/top2['Customers'].sum() / (seg_rev['Revenue'].sum()/seg_rev['Customers'].sum()):.1f} 倍")


# ============================================
# 6. 同期群分析（仅保留前 12 期，避免 NaN 空洞）
# ============================================
first_purchase = (sales_clean.groupby('CustomerID')['YearMonth']
                  .min().reset_index(name='CohortMonth'))
cohort_data = sales_clean.merge(first_purchase, on='CustomerID')
cohort_data['Period'] = (cohort_data['YearMonth'] - cohort_data['CohortMonth']).apply(lambda x: x.n)

cohort_counts = (cohort_data.groupby(['CohortMonth', 'Period'])['CustomerID']
                 .nunique().reset_index(name='n'))
cohort_pivot = cohort_counts.pivot_table(index='CohortMonth', columns='Period', values='n')
cohort_size = cohort_pivot.iloc[:, 0]
retention_matrix = cohort_pivot.divide(cohort_size, axis=0) * 100
retention_matrix = retention_matrix.iloc[:, :12]  # 只取前 12 期

print("\n=== 同期群留存率矩阵（%，前12期）===")
print(retention_matrix.round(1).to_string())

# LTV（累积营收，前6期）
ltv_pivot = (cohort_data.groupby(['CohortMonth', 'Period'])['Revenue']
             .sum().unstack(fill_value=0))
ltv_cumsum = ltv_pivot.cumsum(axis=1).iloc[:, :6]
print("\n=== LTV 累积营收（前6期）===")
print(ltv_cumsum.round(0).to_string())

# ============================================
# 7. 复购率分析
# ============================================
order_counts = sales_clean.groupby('CustomerID')['Invoice'].nunique()
repurchase_rate = (order_counts >= 2).mean() * 100
print(f"\n复购率: {repurchase_rate:.2f}%")

customer_invoices = (sales_clean.groupby(['CustomerID', 'Invoice'])['InvoiceDate']
                     .min().reset_index())
customer_invoices = customer_invoices.sort_values(['CustomerID', 'InvoiceDate'])
customer_invoices['PrevDate'] = (customer_invoices.groupby('CustomerID')['InvoiceDate']
                                 .shift(1))
customer_invoices['DaysBetween'] = ((customer_invoices['InvoiceDate'] -
                                     customer_invoices['PrevDate']).dt.days)
avg_cycle = customer_invoices['DaysBetween'].dropna().median()
print(f"中位复购间隔: {avg_cycle:.0f} 天")

# ============================================
# 8. 产品关联（购物篮分析，剔除取消单 + 可读化）
# ============================================
basket_df = sales_clean[sales_clean['IsCancel'] == 0].copy()
basket = (basket_df.groupby(['Invoice', 'StockCode'])['Quantity']
          .sum().unstack(fill_value=0))
item_freq = (basket > 0).sum(axis=0)
keep_items = item_freq[item_freq >= 20].index
basket = basket[keep_items]
basket_sets = (basket > 0).astype(int)

frequent_itemsets = fpgrowth(basket_sets, min_support=0.02,
                             use_colnames=True, max_len=3)
rules = association_rules(frequent_itemsets, metric='lift', min_threshold=1.2)
rules = rules[rules['confidence'] >= 0.3].sort_values('lift', ascending=False).head(50)

# 把商品编码翻译成描述，提升可读性
rules['antecedent_desc'] = rules['antecedents'].apply(
    lambda s: ' + '.join(code2desc.get(x, str(x)) for x in s))
rules['consequent_desc'] = rules['consequents'].apply(
    lambda s: ' + '.join(code2desc.get(x, str(x)) for x in s))

print("\n=== 频繁项集 Top10 ===")
print(frequent_itemsets.sort_values('support', ascending=False).head(10).to_string())
print("\n=== 关联规则 Top10（含商品描述）===")
print(rules[['antecedent_desc', 'consequent_desc', 'support',
             'confidence', 'lift']].head(10).to_string())

rules.to_csv(os.path.join(OUT_DIR, 'association_rules.csv'),
             index=False, encoding='utf-8-sig')

# ============================================
# 9. 地理 & 时间模式（补充输出）
# ============================================
country_stats = (sales_clean.groupby('Country')
                 .agg(Revenue=('Revenue', 'sum'),
                      Orders=('Invoice', 'nunique'),
                      Customers=('CustomerID', 'nunique'))
                 .sort_values('Revenue', ascending=False))
print("\n=== 国家营收 Top10 ===")
print(country_stats.head(10).round(0).to_string())

hourly_orders = sales_clean.groupby('Hour')['Invoice'].nunique()
weekly_orders = sales_clean.groupby('Weekday')['Invoice'].nunique()

# ============================================
# 10. 可视化（savefig，避免阻塞）
# ============================================
sns.set_style('whitegrid')
fig, axes = plt.subplots(2, 3, figsize=(20, 11))

# RFM 分群人数
rfm['Segment'].value_counts().plot(kind='barh', ax=axes[0, 0], color='steelblue')
axes[0, 0].set_title('RFM Segment Distribution')
axes[0, 0].set_xlabel('Customer Count')

# 同期群留存热力图
sns.heatmap(retention_matrix, annot=True, fmt='.0f', cmap='Blues', ax=axes[0, 1])
axes[0, 1].set_title('Cohort Retention (%) [first 12 periods]')
axes[0, 1].set_ylabel('Cohort Month')

# 月度 GMV 趋势
monthly_gmv = sales_clean.groupby('YearMonth')['Revenue'].sum()
print("\n=== 月度GMV Top5 ===")
print(monthly_gmv.sort_values(ascending=False).head(5).to_string())
axes[0, 2].plot(range(len(monthly_gmv)), monthly_gmv.values, marker='o')
axes[0, 2].set_title('Monthly GMV Trend')
axes[0, 2].set_xticks(range(0, len(monthly_gmv), 3))
axes[0, 2].set_xticklabels([str(x) for x in monthly_gmv.index[::3]], rotation=45)

# 国家营收 Top10
top10 = country_stats.head(10)
axes[1, 0].barh(range(len(top10)), top10['Revenue'].values)
axes[1, 0].set_yticks(range(len(top10)))
axes[1, 0].set_yticklabels(top10.index)
axes[1, 0].set_title('Top 10 Countries by Revenue')

# 小时订单分布
axes[1, 1].bar(hourly_orders.index, hourly_orders.values)
axes[1, 1].set_title('Orders by Hour')

# 复购频次分布
axes[1, 2].hist(order_counts, bins=50, log=True)
axes[1, 2].set_title('Order Frequency Distribution (log)')
axes[1, 2].set_xlabel('Number of Orders')

plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, 'analysis_dashboard.png'), dpi=120)
plt.close()
print(f"\n图表已保存至 {OUT_DIR}/analysis_dashboard.png")

# ============================================
# 11. 补充分析
# ============================================

# 11.1 国家营收补充客单价
country_stats['AvgOrderValue'] = (country_stats['Revenue'] / country_stats['Orders']).round(2)
print("\n=== 国家营收 Top10（含客单价）===")
print(country_stats.head(10).to_string())

# 11.2 月度GMV Top5
print("\n=== 月度GMV Top5 ===")
monthly_gmv = sales_clean.groupby('YearMonth')['Revenue'].sum()
print(monthly_gmv.sort_values(ascending=False).head(5).to_string())

# 11.3 按客户价值分层复购率（高/中/低客单价客户）
high_value = order_counts[order_counts.index.isin(
    rfm[rfm['Monetary'] > rfm['Monetary'].quantile(0.75)].index)]
low_value = order_counts[order_counts.index.isin(
    rfm[rfm['Monetary'] <= rfm['Monetary'].quantile(0.25)].index)]
print(f"\n高价值客户复购率: {(high_value >= 2).mean()*100:.2f}%")
print(f"低价值客户复购率: {(low_value >= 2).mean()*100:.2f}%")

# 11.4 平均留存率曲线
avg_retention = retention_matrix.iloc[:, :12].mean(axis=0)
print("\n=== 平均留存率（按月份差）===")
print(avg_retention.round(1).to_string())

# 11.5 国家营收结构洞察
print(f"\n英国营收占比: {country_stats.iloc[0]['Revenue']/total_gmv*100:.1f}%")
print("注：荷兰/爱尔兰/丹麦客单价为英国4-6倍，属高价值B2B客户，建议差异化运营")

# 11.6, 关联规则分布统计
print(f"\n总规则数: {len(rules)}")
print(f"lift>10: {(rules['lift']>10).sum()},  lift>5: {(rules['lift']>5).sum()}")
print(f"平均lift: {rules['lift'].mean():.2f}, 中位数lift: {rules['lift'].median():.2f}")

# ============================================
# 12. 保存清洗后数据
# ============================================
sales_clean.to_csv(os.path.join(OUT_DIR, 'cleaned_online_retail.csv'), index=False)
print("清洗后数据已保存")

# 供外部复用
globals().update({'sales_clean': sales_clean, 'rfm': rfm,
                  'rules': rules, 'retention_matrix': retention_matrix})
