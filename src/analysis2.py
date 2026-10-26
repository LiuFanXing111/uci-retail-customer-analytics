# -*- coding: utf-8 -*-
"""
================================================================================
UCI Online Retail II —— 数据运营视角扩展分析
新建脚本，不改动原 analysis.py；结果输出到脚本同级的 output_ops/ 目录
================================================================================

【相对于原脚本的三处口径修正】
  修正1 非商品编码：原脚本用 isin 精确匹配 7 个且大小写敏感，UCI 里的
        CRUK / PADS / B / gift_0001_* 礼品卡等会漏网。这里改为
        「精确清单 + 前缀/正则」匹配。
  修正2 Frequency 分箱：原脚本用 qcut 等频五分位，但约 28% 的客户 F=1，
        等频分位会退化（duplicates='drop' 后分箱数变少，边界失真）。这里改为
        业务分箱：1 / 2-3 / 4-6 / 7-11 / 12+（实测分布 1625/1604/1122/769/741）。
  修正3 取消单分类：原脚本把 Price<0 也算作取消，而原始数据中 Price<0
        实际是坏账调整（Adjust bad debt）。这里拆成三类：
        IsCancel      = 真实退货/取消（Invoice 以 C 开头 且 数量为负）
        IsStockAdjust = 库存盘点冲销（数量为负但单号非 C，Description 多为
                        check / damages / missing / thrown away，Price 恒为 0，
                        全无 CustomerID）——不是客户退货，不计入取消率
        IsAdjust      = 坏账与费用调整（Price<0，或单号带 C 但数量非负）
        注：3,457 行库存冲销金额全为 0，故对取消金额无影响，但会抬高
            全量口径的取消率（单量），必须剔除。

【新增模块】
  M1 指标体系与指标字典
  M2 月度 / 周度运营指标表（含环比、同比）
  M3 取消单与数据质量分析
  M4 用户标签体系（客户宽表）
  M5 商品 ABC、动销与品类结构
  M6 监控指标与预警规则（历史回溯，非上线）
  M7 流失预警名单（规则型，非模型预测）
  M8 召回策略模拟 ROI（模拟测算，非实际投放）

【用法】
  直接运行：    python uci_ops_analysis.py
  快速试跑：    set UCI_SAMPLE=50000 && python uci_ops_analysis.py
                （或 PowerShell：$env:UCI_SAMPLE=50000; python uci_ops_analysis.py）
================================================================================
"""

import os
import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

# Windows 控制台 GBK 编码兜底：个别字符打不出来时降级为 ?，避免 UnicodeEncodeError 崩溃
_reconfigure = getattr(sys.stdout, 'reconfigure', None)
if _reconfigure is not None:
    _reconfigure(errors='replace')

# ==============================================================================
# 0. 配置
# ==============================================================================

# 项目根目录（src/ 的上一级）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_ROOT = os.path.dirname(BASE_DIR)

# 原始数据：默认读 <项目根>/data/online_retail_II.xlsx
# 数据获取方式见 data/README.md；也可用环境变量 UCI_DATA 指向别处
FILE_PATH = os.environ.get(
    'UCI_DATA', os.path.join(PROJ_ROOT, 'data', 'online_retail_II.xlsx'))

# 输出目录：<项目根>/output/
OUT_DIR = os.path.join(PROJ_ROOT, 'output')
TABLEAU_DIR = os.path.join(OUT_DIR, 'tableau')
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(TABLEAU_DIR, exist_ok=True)

# 调试用：只读取每个 sheet 的前 N 行（环境变量 UCI_SAMPLE）
SAMPLE_ROWS = int(os.environ.get('UCI_SAMPLE', 0)) or None

# 模块开关
RUN = {
    'metrics_dictionary': True,   # M1 指标字典
    'monthly_weekly': True,       # M2 月度/周度指标表
    'cancel_analysis': True,      # M3 取消单分析
    'customer_profile': True,     # M4 用户标签体系
    'product_abc': True,          # M5 商品 ABC 与品类
    'monitoring': True,           # M6 监控与预警规则
    'churn_watchlist': True,      # M7 流失预警名单
    'roi_simulation': True,       # M8 召回模拟 ROI
    'association': False,         # 关联规则：原脚本已产出，默认关闭（打开需 mlxtend）
    'export_tableau': True,       # 导出 Tableau 可用的 csv
    'export_excel': True,         # 导出多 sheet 报表（需 openpyxl）
}

# M8 模拟参数（全部为假设，结果必须标注"模拟"）
SIM = {
    'gross_margin': 0.30,      # 假设毛利率（原始数据无成本价）
    'coupon_value': 5.0,       # 假设每人发放的券面额（英镑）
    'uplift': 0.05,            # 假设触达带来的响应率提升（绝对值，5 个百分点）
    'target_top_pct': 0.20,    # 场景2：只对流失风险中历史价值 Top20% 定向发券
}

# 流失与预警参数
CHURN_BASE_DAYS = 180          # 沉默超过该天数视为流失风险
MONITOR_MOM_THRESHOLD = 30.0   # 环比波动超过 30% 触发预警
MONITOR_Z_THRESHOLD = 3.0      # 偏离滚动均值 3 倍标准差触发预警


def section(title):
    print('\n' + '=' * 78)
    print(title)
    print('=' * 78)


# ==============================================================================
# 1. 读取数据
# ==============================================================================
section('1. 读取数据')

df1 = pd.read_excel(FILE_PATH, sheet_name='Year 2009-2010', nrows=SAMPLE_ROWS)
df2 = pd.read_excel(FILE_PATH, sheet_name='Year 2010-2011', nrows=SAMPLE_ROWS)
df = pd.concat([df1, df2], ignore_index=True)
df.columns = ['Invoice', 'StockCode', 'Description', 'Quantity', 'InvoiceDate',
              'Price', 'CustomerID', 'Country']

print(f'原始行数: {len(df):,}')
df['InvoiceDate'] = pd.to_datetime(df['InvoiceDate'])
df['CustomerID'] = df['CustomerID'].astype('Int64')
print(f'时间范围: {df["InvoiceDate"].min()} ~ {df["InvoiceDate"].max()}')

# ==============================================================================
# 2. 清洗（含三处口径修正）
# ==============================================================================
section('2. 数据清洗（含口径修正）')

# --- 修正3：拆开"真实取消"与"坏账调整" ---
invoice_str = df['Invoice'].astype(str).str.upper()
is_c_prefix = invoice_str.str.startswith('C')
# 真实取消 = 单号 C 开头且数量为负（客户退货）
# 库存盘点冲销 = 数量为负但单号非 C（check / damages / missing 等，Price=0，无客户ID）
# 坏账与费用调整 = 单价为负，或单号带 C 但数量非负
df['IsCancel'] = ((df['Quantity'] < 0) & is_c_prefix).astype(int)
df['IsStockAdjust'] = ((df['Quantity'] < 0) & ~is_c_prefix).astype(int)
df['IsAdjust'] = ((df['Price'] < 0) | (is_c_prefix & (df['Quantity'] >= 0))).astype(int)

# 有效销售：数量为正且单价为正（与原脚本一致，保证可比）
sales = df[(df['Quantity'] > 0) & (df['Price'] > 0)].copy()

# --- 修正1：非商品编码，精确清单 + 前缀/正则 ---
# 注：PADS 是真实商品（PADS TO MATCH ALL CUSHIONS），不要放进非商品清单
EXACT_NON_PRODUCT = {'POST', 'DOT', 'BANK CHARGES', 'CRUK',
                     'S', 'M', 'B', 'C2', 'D', 'AMAZONFEE'}
PREFIX_NON_PRODUCT = ('gift_0001', 'DCGS', 'BANK', 'AMAZON')


def is_non_product(code):
    c = str(code).strip().upper()
    if c in EXACT_NON_PRODUCT:
        return True
    return c.startswith(PREFIX_NON_PRODUCT)


# 只保留有 CustomerID 的记录用于客户级分析（与原脚本一致）
sales_with_id = sales.dropna(subset=['CustomerID']).copy().drop_duplicates()

mask_non = sales_with_id['StockCode'].apply(is_non_product)
print(f'剔除的非商品编码记录数: {int(mask_non.sum()):,}')
sales_clean = sales_with_id[~mask_non].copy()

# --- 修正：国家标准化（lower -> 映射 -> 首字母大写）---
COUNTRY_MAP = {
    'uk': 'United Kingdom', 'eire': 'Ireland', 'usa': 'United States',
    'r sa': 'South Africa', 'australia': 'Australia',
    'united kingdom': 'United Kingdom', 'netherlands': 'Netherlands',
    'france': 'France', 'germany': 'Germany',
}
sales_clean['Country'] = (sales_clean['Country'].astype(str).str.strip()
                          .str.lower().replace(COUNTRY_MAP).str.title())

# --- 衍生字段 ---
sales_clean['Revenue'] = sales_clean['Quantity'] * sales_clean['Price']
sales_clean['YearMonth'] = sales_clean['InvoiceDate'].dt.to_period('M')
sales_clean['Weekday'] = sales_clean['InvoiceDate'].dt.dayofweek
sales_clean['Hour'] = sales_clean['InvoiceDate'].dt.hour

snapshot_date = sales_clean['InvoiceDate'].max() + pd.Timedelta(days=1)
print(f'清洗后行数（有客户ID的有效销售）: {len(sales_clean):,}')
print(f'快照日期: {snapshot_date.date()}')

# 商品编码 -> 名称（后续多个模块共用）
code2desc = (df.dropna(subset=['Description']).drop_duplicates('StockCode')
             .set_index('StockCode')['Description'].to_dict())

# 品类规则（原始数据无品类字段，以下为按商品名关键词自建的近似口径，需在简历/报告中注明）
CATEGORY_RULES = [
    ('CHRISTMAS', '节日装饰'), ('ADVENT', '节日装饰'), ('EASTER', '节日装饰'),
    ('HALLOWEEN', '节日装饰'), ('XMAS', '节日装饰'),
    ('T-LIGHT', '烛台'), ('CANDLE', '烛台'), ('LANTERN', '灯饰'), ('LIGHT', '灯饰'),
    ('MUG', '杯具'), ('TEACUP', '杯具'), ('TEAPOT', '杯具'), ('BOTTLE', '杯具'),
    ('PLATE', '餐具'), ('BOWL', '餐具'), ('CUTLERY', '餐具'), ('CAKE', '餐具'),
    ('BAG', '包袋'), ('PURSE', '包袋'), ('JUTE', '包袋'),
    ('CUSHION', '家居软装'), ('BLANKET', '家居软装'), ('CURTAIN', '家居软装'),
    ('FRAME', '相框与墙面'), ('SIGN', '家居装饰'), ('CLOCK', '家居装饰'),
    ('TOY', '玩具'), ('GAME', '玩具'), ('DOLL', '玩具'),
    ('CARD', '贺卡与文具'), ('PENCIL', '贺卡与文具'), ('NOTEBOOK', '贺卡与文具'),
    ('WRAP', '包装材料'), ('RIBBON', '包装材料'), ('GIFT', '包装材料'),
    ('HEART', '装饰摆件'), ('BIRD', '装饰摆件'), ('FLOWER', '装饰摆件'),
    ('JAM', '食品'), ('CHOCOLATE', '食品'), ('BISCUIT', '食品'), ('TEA', '食品'),
    ('GLASS', '玻璃器皿'), ('JUG', '玻璃器皿'), ('JAR', '储物容器'), ('TIN', '储物容器'),
    ('SOAP', '个护'), ('BATH', '个护'), ('TOWEL', '个护'),
    ('KEY', '配饰小物'), ('MIRROR', '配饰小物'), ('UMBRELLA', '配饰小物'),
]


def guess_category(desc):
    if not isinstance(desc, str):
        return '未识别'
    u = desc.upper()
    for kw, cat in CATEGORY_RULES:
        if kw in u:
            return cat
    return '其他'


sku_desc_all = (df.dropna(subset=['Description']).drop_duplicates('StockCode')
                .set_index('StockCode')['Description'])
sku_cat = sku_desc_all.apply(guess_category)

# 两套口径的 GMV 与订单数（必须成对使用：全量对全量、仅客户ID对仅客户ID）
sales['IsNonProduct'] = sales['StockCode'].apply(is_non_product)
sales_product = sales[~sales['IsNonProduct']].copy()   # 全量有效商品销售（含无客户ID）
sales_product['Revenue'] = sales_product['Quantity'] * sales_product['Price']
gmv_all_valid = sales_product['Revenue'].sum()
orders_all_valid = sales_product['Invoice'].nunique()
gmv_clean = sales_clean['Revenue'].sum()               # 仅含客户ID（主口径）
orders_clean = sales_clean['Invoice'].nunique()
print(f'GMV（全量有效商品销售，含无客户ID）: {gmv_all_valid:,.0f}；订单数 {orders_all_valid:,}')
print(f'GMV（仅含客户ID，主口径）: {gmv_clean:,.0f}；订单数 {orders_clean:,}')
print(f'差异: {(gmv_all_valid - gmv_clean) / gmv_all_valid * 100:.1f}%（无客户ID订单的营收占比）')
print('注：费率类科目（POST / AMAZONFEE / Manual 等）已在同一层剔除，两套管径均不含。')

# 取消单表（含绝对值金额，用于取消率分析）
# 注意：取消行里混有 AMAZON FEE / Manual / Discount / CRUK 等费用与调整科目，
# 不是商品退货，必须拆分，否则取消金额会被严重高估。
cancels = df[df['IsCancel'] == 1].copy()
cancels['CancelAmount'] = (cancels['Quantity'] * cancels['Price']).abs()
cancels['YearMonth'] = cancels['InvoiceDate'].dt.to_period('M')
cancels['IsProduct'] = ~cancels['StockCode'].apply(is_non_product)
cancel_product = cancels[cancels['IsProduct']].copy()        # 商品类取消（主口径）
cancel_fee = cancels[~cancels['IsProduct']].copy()           # 费用/调整类冲销

# 取消行里的"非商品调整项"标记（damaged / thrown away / wrong qnty 等）
# 只标记不自动剔除：部分商品名本身含 CHECK 等词，按关键词一刀切会误删真商品
# 说明：修正3 落地后，这类脏数据多数已归入 IsStockAdjust（非 C 单号）被整体剔除，
#       故本标记通常命中 0 行；保留用于兜底检查，命中不为 0 时需人工复核。
DIRTY_DESC_EXACT = {'damaged', 'damaged?', 'damaged/dirty', 'thrown away',
                    'rusty-thrown away', 'wet', 'dirty', 'torn', 'wrong code',
                    'sold in wrong qnty', 'missing (wrongly coded?)', 'found',
                    'showroom', 'wet rusty', 'broken'}
cancel_product['IsDirtyDesc'] = (
    cancel_product['Description'].astype(str).str.strip().str.lower()
    .isin(DIRTY_DESC_EXACT))

# 与 sales_clean 同范围（仅含客户ID）的取消单，供取消率分子使用，保证分子分母同口径
cancel_product_id = cancel_product.dropna(subset=['CustomerID']).copy()

print(f'真实取消单行数: {len(cancels):,}；坏账/调整行数: {int(df["IsAdjust"].sum()):,}')
print(f'  其中商品类取消: {len(cancel_product):,} 行；费用/调整类冲销: {len(cancel_fee):,} 行')
print(f'  【已剔除】库存盘点冲销: {int(df["IsStockAdjust"].sum()):,} 行'
      f'（非客户退货，金额 0，不计入取消率）')
print(f'  商品类取消中，描述疑似"非商品调整项": {int(cancel_product["IsDirtyDesc"].sum()):,} 行'
      f'（金额 {cancel_product.loc[cancel_product["IsDirtyDesc"], "CancelAmount"].sum():,.0f}，'
      '仅标记供人工复核，不计入剔除）')


# ==============================================================================
# M1 指标体系与指标字典
# ==============================================================================
metric_dictionary = None
if RUN['metrics_dictionary']:
    section('M1 指标体系与指标字典')

    metric_dictionary = pd.DataFrame([
        ['GMV', 'Σ(Quantity × Price)，剔除取消单、坏账调整与非商品编码',
         '有客户ID的有效销售', '月/周/日', '订单明细'],
        ['订单数', 'Invoice 去重计数', '有效销售', '月/周/日', '订单明细'],
        ['客单价 AOV', 'GMV ÷ 订单数', '有效销售', '月/周', '订单明细'],
        ['连带率', '总销售件数 ÷ 订单数', '有效销售', '月/周', '订单明细'],
        ['件均单价', 'GMV ÷ 总销售件数', '有效销售', '月/周', '订单明细'],
        ['活跃客户数', '当期有购买记录的 CustomerID 去重计数', '有客户ID', '月/周', '订单明细'],
        ['新客数', '首购月份等于当期的客户数', '有客户ID', '月', '客户首购表'],
        ['新客占比', '新客数 ÷ 活跃客户数', '有客户ID', '月', '客户首购表'],
        ['老客占比', '1 - 新客占比', '有客户ID', '月', '客户首购表'],
        ['复购率', '统计期内下单次数 ≥ 2 的客户占比', '有客户ID', '全期/滚动', '客户订单表'],
        ['次月留存率', '首购后第 2 个自然月仍有购买的比例', '有客户ID', '同期群', '同期群矩阵'],
        ['月度留存率', '上月活跃客户中本月仍活跃的比例', '有客户ID', '月', '月度活跃集合'],
        ['ARPU', 'GMV ÷ 活跃客户数', '有客户ID', '月/分层', '客户分层表'],
        ['中位复购间隔', '同一客户相邻两次订单日期差的中位数', '有客户ID', '全期', '客户订单表'],
        ['取消率（单量）', '取消单量 ÷ (有效订单量 + 取消单量)；口径须成对，主口径为仅含客户ID',
         '有效销售（主口径：仅含客户ID）', '月', '取消单表'],
        ['取消率（金额）', '取消金额绝对值 ÷ GMV；口径须成对，主口径为仅含客户ID',
         '有效销售（主口径：仅含客户ID）', '月', '取消单表'],
        ['动销 SKU 数', '当期产生销量的 StockCode 去重计数', '有效销售', '月', '订单明细'],
        ['SKU 集中度', '当期 GMV Top10 商品营收 ÷ 当期 GMV', '有效销售', '月', '订单明细'],
        ['客户集中度', '营收占比前 N% 客户的营收累计占比', '有客户ID', '全期', '客户分层表'],
    ], columns=['指标名', '口径定义', '统计范围', '更新频率', '数据来源'])

    path = os.path.join(OUT_DIR, 'metric_dictionary.csv')
    metric_dictionary.to_csv(path, index=False, encoding='utf-8-sig')
    print(f'指标字典共 {len(metric_dictionary)} 项，已保存: {path}')


# ==============================================================================
# M2 月度 / 周度运营指标表
# ==============================================================================
monthly = None
weekly = None
if RUN['monthly_weekly']:
    section('M2 月度 / 周度运营指标表')

    fp = (sales_clean.groupby('CustomerID')['YearMonth'].min()
          .rename('CohortMonth'))
    sc = sales_clean.merge(fp, on='CustomerID')

    m = sc.groupby('YearMonth').agg(
        GMV=('Revenue', 'sum'),
        Orders=('Invoice', 'nunique'),
        Items=('Quantity', 'sum'),
        ActiveCustomers=('CustomerID', 'nunique'),
        ActiveSKUs=('StockCode', 'nunique'),
    )
    new_cust = (sc[sc['YearMonth'] == sc['CohortMonth']]
                .groupby('YearMonth')['CustomerID'].nunique())
    m['NewCustomers'] = new_cust.reindex(m.index).fillna(0).astype(int)
    m['NewCustShare%'] = (m['NewCustomers'] / m['ActiveCustomers'] * 100).round(1)
    m['OldCustShare%'] = (100 - m['NewCustShare%']).round(1)
    m['AOV'] = (m['GMV'] / m['Orders']).round(2)
    m['ItemsPerOrder'] = (m['Items'] / m['Orders']).round(2)
    m['UnitPrice'] = (m['GMV'] / m['Items']).round(2)
    m['ARPU'] = (m['GMV'] / m['ActiveCustomers']).round(2)

    # 月度 Top10 商品集中度
    ms = (sales_clean.groupby(['YearMonth', 'StockCode'])['Revenue'].sum()
          .reset_index())
    ms['rk'] = ms.groupby('YearMonth')['Revenue'].rank(ascending=False, method='first')
    top10 = ms[ms['rk'] <= 10].groupby('YearMonth')['Revenue'].sum()
    m['Top10SKURevShare%'] = (top10.reindex(m.index).fillna(0) / m['GMV'] * 100).round(1)

    # 取消单（按月）——分子分母同口径：均取"仅含客户ID"范围
    if len(cancel_product_id):
        cg = cancel_product_id.groupby('YearMonth').agg(
            CancelOrders=('Invoice', 'nunique'),
            CancelAmount=('CancelAmount', 'sum'))
        m['CancelOrders'] = cg['CancelOrders'].reindex(m.index).fillna(0).astype(int)
        m['CancelAmount'] = cg['CancelAmount'].reindex(m.index).fillna(0).round(0)
        m['CancelOrderRate%'] = (m['CancelOrders'] /
                                 (m['Orders'] + m['CancelOrders']) * 100).round(2)
        m['CancelAmountRate%'] = (m['CancelAmount'] / m['GMV'] * 100).round(2)

    # 首月新客占比恒为 100%（所有人都是首购），属定义起点，标为不可比
    m['IsFirstMonth'] = (m.index == m.index.min())
    m.loc[m['IsFirstMonth'], ['NewCustShare%', 'OldCustShare%']] = np.nan

    # 环比 / 同比 / 数据完整性
    m['MoM_GMV%'] = (m['GMV'].pct_change() * 100).round(1)
    m['YoY_GMV%'] = (m['GMV'].pct_change(12) * 100).round(1)
    last_period = m.index.max()
    m['IsPartialMonth'] = (m.index == last_period)
    monthly = m.copy()

    print('\n=== 月度运营指标（前后各 6 个月）===')
    show_cols = ['GMV', 'Orders', 'ActiveCustomers', 'NewCustShare%', 'AOV',
                 'ItemsPerOrder', 'ActiveSKUs', 'MoM_GMV%']
    print(m[show_cols].head(6).round(0).to_string())
    print('   ...')
    print(m[show_cols].tail(6).round(0).to_string())

    path = os.path.join(OUT_DIR, 'monthly_metrics.csv')
    monthly.to_csv(path, encoding='utf-8-sig')
    print(f'\n月度指标已保存: {path}')
    print('注1：最后一个自然月为数据截断月（IsPartialMonth=True），环比/同比不可直接使用。')
    print('注2：首个自然月所有客户均为首购，新客占比恒为 100%（定义起点，已置空，非业务结论）。')

    # 周度
    w = (sales_clean.groupby(pd.Grouper(key='InvoiceDate', freq='W-MON'))
         .agg(GMV=('Revenue', 'sum'), Orders=('Invoice', 'nunique'),
              Items=('Quantity', 'sum'), ActiveCustomers=('CustomerID', 'nunique'),
              ActiveSKUs=('StockCode', 'nunique')).dropna(how='all'))
    w['AOV'] = (w['GMV'] / w['Orders']).round(2)
    w['WoW_GMV%'] = (w['GMV'].pct_change() * 100).round(1)
    weekly = w
    path = os.path.join(OUT_DIR, 'weekly_metrics.csv')
    weekly.to_csv(path, encoding='utf-8-sig')
    print(f'周度指标已保存: {path}（共 {len(weekly)} 周）')


# ==============================================================================
# M3 取消单与数据质量分析
# ==============================================================================
cancel_summary = None
if RUN['cancel_analysis'] and len(cancels) and monthly is not None:
    section('M3 取消单与数据质量分析')

    # 主口径：商品类取消（费用/调整类冲销单列）
    # 口径修正：分子分母必须同范围。主口径=仅含客户ID；同时给全量口径作对照
    cancel_orders_id = cancel_product_id['Invoice'].nunique()
    cancel_orders_all = cancel_product['Invoice'].nunique()
    cancel_amount_id = cancel_product_id['CancelAmount'].sum()
    cancel_amount_all = cancel_product['CancelAmount'].sum()
    fee_amount = cancel_fee['CancelAmount'].sum()

    rate_orders_id = cancel_orders_id / (cancel_orders_id + orders_clean) * 100
    rate_orders_all = cancel_orders_all / (cancel_orders_all + orders_all_valid) * 100
    rate_amount_id = cancel_amount_id / gmv_clean * 100
    rate_amount_all = cancel_amount_all / gmv_all_valid * 100

    print(f'【主口径｜仅含客户ID】取消单量 {cancel_orders_id:,}；有效订单量 {orders_clean:,}')
    print(f'  取消率（单量）= {rate_orders_id:.2f}%')
    print(f'  取消金额 {cancel_amount_id:,.0f}；GMV {gmv_clean:,.0f}；'
          f'取消率（金额）= {rate_amount_id:.2f}%')
    print(f'【对照口径｜全量】取消单量 {cancel_orders_all:,}；有效订单量 {orders_all_valid:,}')
    print(f'  取消率（单量）= {rate_orders_all:.2f}%；取消率（金额）= {rate_amount_all:.2f}%')
    print(f'【单列】费用/调整类冲销金额: {fee_amount:,.0f}'
          f'（AMAZON FEE / Manual / Discount 等，非商品退货，不计入取消率）')

    # 取消金额集中度：金额被极少数大额批发单主导，不能按均值口径解读
    # 口径与主口径一致：用 cancel_product_id（仅含客户ID），而非全量
    sku_cancel = (cancel_product_id.groupby('StockCode')['CancelAmount'].sum()
                  .sort_values(ascending=False))
    total_sku_cancel = sku_cancel.sum()
    top1_share = sku_cancel.iloc[0] / total_sku_cancel * 100
    top2_share = sku_cancel.iloc[:2].sum() / total_sku_cancel * 100
    top10_share = sku_cancel.iloc[:10].sum() / total_sku_cancel * 100
    print(f'\n取消金额集中度（主口径｜仅客户ID）：Top1 商品（{sku_cancel.index[0]}）'
          f'占 {top1_share:.1f}%，Top2 累计 {top2_share:.1f}%，Top10 累计 {top10_share:.1f}%')
    print('→ 取消金额高度集中于个别大额批发单，应按单笔异常设监控，不宜用月度均值解读。')

    cm = cancel_product_id.groupby('YearMonth').agg(
        CancelOrders=('Invoice', 'nunique'),
        CancelAmount=('CancelAmount', 'sum'))
    cm['CancelOrderRate%'] = (cm['CancelOrders'] /
                              (cm['CancelOrders'] +
                               monthly['Orders'].reindex(cm.index).fillna(0)) * 100).round(2)
    print('\n=== 商品类取消单月度分布（按取消金额 Top5，仅客户ID口径）===')
    print(cm.sort_values('CancelAmount', ascending=False).head(5).round(0).to_string())

    top_cancel_sku = (cancel_product_id.groupby('StockCode')
                      .agg(CancelQty=('Quantity', 'sum'),
                           CancelAmount=('CancelAmount', 'sum'),
                           Times=('Invoice', 'nunique'))
                      .sort_values('CancelAmount', ascending=False).head(10))
    code2desc_used = code2desc  # 已在清洗阶段构建
    top_cancel_sku['Description'] = [code2desc_used.get(i, '') for i in top_cancel_sku.index]
    print('\n=== 取消金额 Top10 商品 ===')
    print(top_cancel_sku.to_string())

    cancel_summary = pd.DataFrame([
        ['【主口径｜仅客户ID】商品类取消单量', cancel_orders_id],
        ['【主口径】有效订单量', orders_clean],
        ['【主口径】取消率（单量，%）', round(rate_orders_id, 2)],
        ['【主口径】取消金额', round(cancel_amount_id, 0)],
        ['【主口径】取消率（金额，%）', round(rate_amount_id, 2)],
        ['【对照｜全量】商品类取消单量', cancel_orders_all],
        ['【对照｜全量】有效订单量', orders_all_valid],
        ['【对照｜全量】取消率（单量，%）', round(rate_orders_all, 2)],
        ['【对照｜全量】取消率（金额，%）', round(rate_amount_all, 2)],
        ['取消金额集中度 Top1（%）', round(top1_share, 1)],
        ['取消金额集中度 Top10（%）', round(top10_share, 1)],
        ['费用/调整类冲销金额（单列，不计入取消率）', round(fee_amount, 0)],
        ['坏账/调整行数（不计入取消率）', int(df['IsAdjust'].sum())],
        ['库存盘点冲销行数（已剔除，不计入取消率）', int(df['IsStockAdjust'].sum())],
        ['疑似非商品调整项行数（仅标记，未剔除）', int(cancel_product['IsDirtyDesc'].sum())],
    ], columns=['指标', '数值'])

    path = os.path.join(OUT_DIR, 'cancel_analysis.csv')
    cm.to_csv(path, encoding='utf-8-sig')
    cancel_summary.to_csv(os.path.join(OUT_DIR, 'cancel_summary.csv'),
                          index=False, encoding='utf-8-sig')
    print(f'\n已保存: {path}')


# ==============================================================================
# M4 用户标签体系
# ==============================================================================
rfm = None
profile = None
seg = None
if RUN['customer_profile']:
    section('M4 用户标签体系（客户宽表）')

    rfm = sales_clean.groupby('CustomerID').agg(
        Recency=('InvoiceDate', lambda x: (snapshot_date - x.max()).days),
        Frequency=('Invoice', 'nunique'),
        Monetary=('Revenue', 'sum'),
        FirstPurchase=('InvoiceDate', 'min'),
        LastPurchase=('InvoiceDate', 'max'),
        Items=('Quantity', 'sum'),
    )

    # --- 修正2：Frequency 改业务分箱 ---
    rfm['F'] = pd.cut(rfm['Frequency'], bins=[0, 1, 3, 6, 11, np.inf],
                      labels=[1, 2, 3, 4, 5]).astype(int)
    rfm['R'] = pd.cut(rfm['Recency'], bins=[-1, 30, 90, 180, 365, np.inf],
                      labels=[5, 4, 3, 2, 1]).astype(int)
    try:
        rfm['M'] = pd.qcut(rfm['Monetary'], q=5, labels=[1, 2, 3, 4, 5],
                           duplicates='drop').astype(int)
    except ValueError:
        rfm['M'] = pd.cut(rfm['Monetary'].rank(method='first'), bins=5,
                          labels=[1, 2, 3, 4, 5]).astype(int)

    def segment_of(r_score, f_score, m_score):
        if r_score >= 4 and f_score >= 4 and m_score >= 4:
            return 'Champions'
        if f_score >= 4:
            return 'Loyal Customers'
        if r_score >= 4 and f_score >= 2:
            return 'Potential Loyalists'
        if r_score >= 4 and f_score <= 1:
            return 'New Customers'
        if r_score <= 2 and f_score >= 4:
            return 'Cant Lose Them'
        if r_score <= 2 and f_score <= 2 and m_score >= 4:
            return 'Hibernating'
        if r_score <= 2:
            return 'At Risk'
        return 'Others'

    rfm['Segment'] = [segment_of(r, f, m) for r, f, m in zip(rfm['R'], rfm['F'], rfm['M'])]
    print('\n=== RFM 分群人数 ===')
    print(rfm['Segment'].value_counts().to_string())
    seg_names = set(rfm['Segment'].unique())
    extra = '；含 Cant Lose Them' if 'Cant Lose Them' in seg_names else '；本次无 Cant Lose Them'
    print(f'（分群共 {rfm["Segment"].nunique()} 类{extra}）')

    # 分层营收结构
    seg = (sales_clean.merge(rfm['Segment'], left_on='CustomerID', right_index=True)
           .groupby('Segment')
           .agg(Customers=('CustomerID', 'nunique'),
                Orders=('Invoice', 'nunique'),
                Revenue=('Revenue', 'sum')))
    seg['CustShare%'] = (seg['Customers'] / seg['Customers'].sum() * 100).round(1)
    seg['RevShare%'] = (seg['Revenue'] / seg['Revenue'].sum() * 100).round(1)
    seg['ARPU'] = (seg['Revenue'] / seg['Customers']).round(2)
    seg['AOV'] = (seg['Revenue'] / seg['Orders']).round(2)
    seg = seg.sort_values('Revenue', ascending=False)
    seg['CumRevShare%'] = seg['RevShare%'].cumsum().round(1)
    print('\n=== 分层营收结构 ===')
    print(seg.round(2).to_string())

    # --- 复购间隔 ---
    ci = (sales_clean.groupby(['CustomerID', 'Invoice'])['InvoiceDate'].min()
          .reset_index().sort_values(['CustomerID', 'InvoiceDate']))
    ci['PrevDate'] = ci.groupby('CustomerID')['InvoiceDate'].shift(1)
    ci['Gap'] = (ci['InvoiceDate'] - ci['PrevDate']).dt.days
    med_gap = ci.groupby('CustomerID')['Gap'].median()
    rfm['MedianGap'] = med_gap.reindex(rfm.index)

    # --- 生命周期阶段 ---
    def lifecycle(cust):
        if cust['Frequency'] == 1 and cust['Recency'] <= 60:
            return '新客'
        if cust['Recency'] <= 90 and cust['Frequency'] >= 4:
            return '成熟期'
        if cust['Recency'] <= 90:
            return '成长期'
        if cust['Recency'] <= 180:
            return '衰退期'
        if cust['Recency'] <= 365:
            return '沉默期'
        return '流失期'

    rfm['LifeStage'] = rfm.apply(lifecycle, axis=1)

    # 品类偏好（sku_cat 已在清洗阶段构建；原始数据无品类字段，属自建近似口径）
    top_sku = (sales_clean.groupby(['CustomerID', 'StockCode'])['Revenue'].sum()
               .reset_index())
    top_sku['Category'] = top_sku['StockCode'].map(sku_cat).fillna('其他')
    cat_pref = (top_sku.groupby(['CustomerID', 'Category'])['Revenue'].sum()
                .reset_index().sort_values('Revenue', ascending=False))
    rfm['TopCategory'] = (cat_pref.groupby('CustomerID')['Category'].first()
                          .reindex(rfm.index).fillna('其他'))

    # --- 价格带偏好（按客户客单价分位）---
    rfm['CustomerAOV'] = (rfm['Monetary'] / rfm['Frequency']).round(2)
    try:
        rfm['PriceBand'] = pd.qcut(rfm['CustomerAOV'], q=3,
                                   labels=['低客单', '中客单', '高客单'],
                                   duplicates='drop').astype(str)
    except ValueError:
        rfm['PriceBand'] = '中客单'

    # --- 批发/大单客 ---
    max_qty = sales_clean.groupby('CustomerID')['Quantity'].max()
    rfm['IsWholesale'] = (max_qty.reindex(rfm.index).fillna(0) >= 100).astype(int)

    # --- 大促敏感（是否在旺季月下单）---
    peak_months = set(sales_clean.groupby('YearMonth')['Revenue'].sum()
                      .sort_values(ascending=False).head(3).index)
    rfm['IsPeakBuyer'] = (sales_clean[sales_clean['YearMonth'].isin(peak_months)]
                          .groupby('CustomerID')['Invoice'].nunique()
                          .reindex(rfm.index).fillna(0).gt(0).astype(int))

    # --- 流失判定（规则型）---
    def churn_threshold(cust):
        base = CHURN_BASE_DAYS
        if pd.notna(cust['MedianGap']) and cust['MedianGap'] > 0:
            base = max(base, 2 * cust['MedianGap'])
        return base

    rfm['ChurnThreshold'] = rfm.apply(churn_threshold, axis=1).round(0)
    rfm['IsChurnRisk'] = np.where(rfm['Recency'] > rfm['ChurnThreshold'], 1, 0)

    profile = rfm.reset_index()
    path = os.path.join(OUT_DIR, 'customer_profile.csv')
    profile.to_csv(path, index=False, encoding='utf-8-sig')
    print(f'\n客户宽表已保存: {path}（{len(profile):,} 位客户，'
          f'{len(profile.columns)} 个字段：客户ID + {len(profile.columns) - 1} 项标签）')
    print('\n=== 生命周期阶段分布 ===')
    print(rfm['LifeStage'].value_counts().to_string())
    print('\n=== 品类偏好分布（Top10，自建近似口径）===')
    print(rfm['TopCategory'].value_counts().head(10).to_string())
    print(f'\n流失风险客户数: {int(rfm["IsChurnRisk"].sum()):,} '
          f'（占 {rfm["IsChurnRisk"].mean() * 100:.1f}%）')

    seg.to_csv(os.path.join(OUT_DIR, 'segment_revenue.csv'), encoding='utf-8-sig')


# ==============================================================================
# M5 商品 ABC、动销与品类结构
# ==============================================================================
product_abc = None
category_structure = None
if RUN['product_abc']:
    section('M5 商品 ABC、动销与品类结构')

    sku = sales_clean.groupby('StockCode').agg(
        Revenue=('Revenue', 'sum'),
        Quantity=('Quantity', 'sum'),
        Orders=('Invoice', 'nunique'),
        FirstSale=('InvoiceDate', 'min'),
        LastSale=('InvoiceDate', 'max'),
    )
    sku['Description'] = [code2desc.get(i, '') for i in sku.index]
    sku = sku.sort_values('Revenue', ascending=False)
    sku['RevShare%'] = (sku['Revenue'] / sku['Revenue'].sum() * 100).round(3)
    sku['CumRevShare%'] = sku['RevShare%'].cumsum().round(2)
    sku['ABC'] = pd.cut(sku['CumRevShare%'], bins=[-0.01, 80, 95, 1000],
                        labels=['A', 'B', 'C']).astype(str)
    sku['InactiveDays'] = (snapshot_date - sku['LastSale']).dt.days
    sku['IsSlowMoving'] = (sku['InactiveDays'] > 180).astype(int)
    sku['IsNewSKU'] = (sku['FirstSale'] >= snapshot_date - pd.Timedelta(days=90)).astype(int)
    product_abc = sku

    n_sku = len(sku)
    n_a = int((sku['ABC'] == 'A').sum())
    print(f'SKU 总数: {n_sku:,}')
    print(f'A 类（累计贡献 80% 营收）: {n_a:,} 个，占 {n_a / n_sku * 100:.1f}%')
    print(f'B 类（80%~95%）: {int((sku["ABC"] == "B").sum()):,} 个')
    print(f'C 类（95%~100%）: {int((sku["ABC"] == "C").sum()):,} 个')
    print(f'滞销 SKU（近 180 天无销量）: {int(sku["IsSlowMoving"].sum()):,} 个，'
          f'占 {sku["IsSlowMoving"].mean() * 100:.1f}%')
    print(f'新品 SKU（近 90 天内首次出现）: {int(sku["IsNewSKU"].sum()):,} 个')
    print(f'Top10 商品营收占比: {sku["RevShare%"].head(10).sum():.1f}%')
    print(f'Top100 商品营收占比: {sku["RevShare%"].head(100).sum():.1f}%')

    # 品类结构（自建近似）
    sales_cat = sales_clean.copy()
    sales_cat['Category'] = sales_cat['StockCode'].map(sku_cat).fillna('其他')
    category_structure = (sales_cat.groupby('Category')
                          .agg(Revenue=('Revenue', 'sum'),
                               Quantity=('Quantity', 'sum'),
                               SKUs=('StockCode', 'nunique'),
                               Orders=('Invoice', 'nunique'))
                          .sort_values('Revenue', ascending=False))
    category_structure['RevShare%'] = (category_structure['Revenue'] /
                                       category_structure['Revenue'].sum() * 100).round(1)
    category_structure['AOV'] = (category_structure['Revenue'] /
                                 category_structure['Orders']).round(2)
    print('\n=== 品类结构（按商品名关键词自建，近似口径）===')
    print(category_structure.head(12).round(0).to_string())

    sku.to_csv(os.path.join(OUT_DIR, 'product_abc.csv'), encoding='utf-8-sig')
    category_structure.to_csv(os.path.join(OUT_DIR, 'category_structure.csv'),
                              encoding='utf-8-sig')
    print('\n已保存: product_abc.csv / category_structure.csv')


# ==============================================================================
# M6 监控指标与预警规则（历史回溯，非上线）
# ==============================================================================
alerts = None
if RUN['monitoring'] and monthly is not None:
    section('M6 监控指标与预警规则（历史回溯）')

    mon = monthly[~monthly['IsPartialMonth']].copy()
    roll_mean = mon['GMV'].rolling(12, min_periods=6).mean()
    roll_std = mon['GMV'].rolling(12, min_periods=6).std()
    mon['RollMean12'] = roll_mean.round(0)
    mon['ZScore'] = ((mon['GMV'] - roll_mean) / roll_std).round(2)

    triggered = []

    def yoy_text(idx):
        v = mon.loc[idx, 'YoY_GMV%'] if 'YoY_GMV%' in mon.columns else np.nan
        return f'{v:.1f}%' if pd.notna(v) else '无同期'

    for idx, row in mon.iterrows():
        if pd.notna(row['ZScore']) and abs(row['ZScore']) > MONITOR_Z_THRESHOLD:
            triggered.append([str(idx), 'GMV', round(row['GMV'], 0),
                              f'偏离12月滚动均值 {row["ZScore"]} 倍标准差',
                              f'超过 {MONITOR_Z_THRESHOLD} 倍标准差', yoy_text(idx)])
        if pd.notna(row['MoM_GMV%']) and abs(row['MoM_GMV%']) > MONITOR_MOM_THRESHOLD:
            triggered.append([str(idx), 'GMV 环比', f'{row["MoM_GMV%"]}%',
                              '环比波动超阈值',
                              f'超过 {MONITOR_MOM_THRESHOLD}%', yoy_text(idx)])

    alerts = pd.DataFrame(triggered,
                          columns=['月份', '监控指标', '实测值', '触发原因', '规则',
                                   '去年同期环比'])
    if len(alerts):
        print(f'回溯共触发 {len(alerts)} 次预警：')
        print(alerts.to_string(index=False))
    else:
        print('回溯未触发预警（可调低阈值）')

    print(f'\n规则说明：|ZScore| > {MONITOR_Z_THRESHOLD} 或 |环比| > {MONITOR_MOM_THRESHOLD}% 触发；')
    print('截断月已排除；本结果为历史数据回溯验证，不代表已上线监控。')
    print('注：旺季前后（如 11-12 月、1 月）的环比波动多为季节性，需结合"去年同期环比"'
          '与季节基线判断，不能直接判定为异常；当前固定阈值存在假阳性，需进一步调优。')
    alerts.to_csv(os.path.join(OUT_DIR, 'monitoring_alerts.csv'),
                  index=False, encoding='utf-8-sig')
    mon.to_csv(os.path.join(OUT_DIR, 'monitoring_series.csv'), encoding='utf-8-sig')


# ==============================================================================
# M7 流失预警名单（规则型）
# ==============================================================================
churn = None
if RUN['churn_watchlist'] and rfm is not None:
    section('M7 流失预警名单（规则型）')

    watch = rfm[rfm['IsChurnRisk'] == 1].copy()
    total_cust = len(rfm)
    churn = pd.DataFrame([
        ['流失风险客户数', len(watch)],
        ['占比(%)', round(len(watch) / total_cust * 100, 1)],
        ['该客群历史营收', round(watch['Monetary'].sum(), 0)],
        ['该客群营收占比(%)', round(watch['Monetary'].sum() / rfm['Monetary'].sum() * 100, 1)],
        ['人均历史营收', round(watch['Monetary'].mean(), 2)],
        ['中位沉默天数', int(watch['Recency'].median())],
    ], columns=['指标', '数值'])
    print(churn.to_string(index=False))
    print('\n=== 流失风险客群的分群构成 ===')
    print(watch['Segment'].value_counts().to_string())
    print('\n=== 流失风险客群的生命周期构成 ===')
    print(watch['LifeStage'].value_counts().to_string())
    print('\n注：判定规则为 Recency > max(180天, 2×该客户历史中位复购间隔)，属规则圈人，非模型预测。')

    watch.reset_index().to_csv(os.path.join(OUT_DIR, 'churn_watchlist.csv'),
                               index=False, encoding='utf-8-sig')
    churn.to_csv(os.path.join(OUT_DIR, 'churn_summary.csv'), index=False,
                 encoding='utf-8-sig')


# ==============================================================================
# M8 召回策略模拟 ROI（模拟测算，非实际投放）
# ==============================================================================
roi = None
if RUN['roi_simulation'] and rfm is not None and monthly is not None:
    section('M8 召回策略模拟 ROI（模拟测算）')

    # 真实可算的基线：月度留存率（上月活跃客户中本月仍活跃的比例）
    active_sets = sales_clean.groupby('YearMonth')['CustomerID'].apply(set)
    periods = list(active_sets.index)
    rates = []
    for i in range(len(periods) - 1):
        cur, nxt = active_sets[periods[i]], active_sets[periods[i + 1]]
        if periods[i + 1] == monthly.index.max():
            continue  # 跳过截断月
        if len(cur) > 0:
            rates.append(len(cur & nxt) / len(cur))
    base_rate = float(np.mean(rates)) if rates else np.nan
    if np.isnan(base_rate):
        print('基线（月度留存率）无法计算：可用月份不足，请检查数据量')
    else:
        print(f'基线（真实计算）：月度留存率均值 = {base_rate * 100:.1f}%'
              f'（基于 {len(rates)} 个月，已排除截断月）')

    target = rfm[rfm['IsChurnRisk'] == 1]
    n_target = len(target)
    # 用目标客群自身的历史客单价更稳妥
    aov_target = (target['Monetary'].sum() / target['Frequency'].sum())

    inc_orders = n_target * SIM['uplift']
    inc_gmv = inc_orders * aov_target
    gross_profit = inc_gmv * SIM['gross_margin']
    cost = n_target * SIM['coupon_value']
    roi_value = (gross_profit - cost) / cost if cost else np.nan

    roi = pd.DataFrame([
        ['目标人群', '流失风险客户（规则圈定）', f'{n_target:,} 人'],
        ['基线：月度留存率', '上月活跃客户本月仍活跃的比例（真实计算）',
         f'{base_rate * 100:.1f}%'],
        ['假设：触达提升响应率', '参数 uplift（假设值，非实测）',
         f'{SIM["uplift"] * 100:.1f} 个百分点'],
        ['假设：毛利率', '原始数据集无成本价（假设值）', f'{SIM["gross_margin"] * 100:.0f}%'],
        ['假设：券面额', '按目标人群全员发放（假设值）', f'{SIM["coupon_value"]:.1f} 英镑/人'],
        ['目标客群历史客单价', '该客群历史营收 ÷ 历史订单数（真实计算）', f'{aov_target:.2f}'],
        ['增量订单（模拟）', '目标人数 × uplift', f'{inc_orders:,.0f} 单'],
        ['增量 GMV（模拟）', '增量订单 × 客单价', f'{inc_gmv:,.0f}'],
        ['增量毛利（模拟）', '增量 GMV × 毛利率', f'{gross_profit:,.0f}'],
        ['券成本（模拟）', '目标人数 × 券面额', f'{cost:,.0f}'],
        ['模拟 ROI', '(增量毛利 - 券成本) ÷ 券成本', f'{roi_value:.2f}'],
    ], columns=['项目', '口径/说明', '取值'])
    print('\n' + roi.to_string(index=False))
    print('\n注1：以上为模拟测算，未实际投放；自然回流部分不计入增量，避免重复计算。')
    print('注2：月度留存率仅作背景参照，未进入 ROI 公式——增量订单只计 uplift 带来的'
          '额外订单（目标人数 × uplift），不叠加自然回流，故不与基线相加。')

    # 场景2：只对流失风险中历史价值 Top20% 定向发券（对比全员发券）
    top_pct = SIM['target_top_pct']
    cut_val = target['Monetary'].quantile(1 - top_pct)
    hi = target[target['Monetary'] >= cut_val]
    n_hi = len(hi)
    aov_hi = (hi['Monetary'].sum() / hi['Frequency'].sum())

    def sim_scenario(n, aov):
        o = n * SIM['uplift']
        g = o * aov
        gp = g * SIM['gross_margin']
        c = n * SIM['coupon_value']
        return o, g, gp, c, ((gp - c) / c if c else np.nan)

    o1, g1, gp1, c1, r1 = sim_scenario(n_target, aov_target)
    o2, g2, gp2, c2, r2 = sim_scenario(n_hi, aov_hi)

    scenarios = pd.DataFrame([
        ['场景1 全员发券', f'{n_target:,} 人', f'{aov_target:.2f}', f'{o1:,.0f}',
         f'{g1:,.0f}', f'{gp1:,.0f}', f'{c1:,.0f}', f'{r1:.2f}',
         '不可行（ROI<1）' if r1 < 1 else '可行'],
        [f'场景2 定向Top{int(top_pct * 100)}%高价值', f'{n_hi:,} 人', f'{aov_hi:.2f}', f'{o2:,.0f}',
         f'{g2:,.0f}', f'{gp2:,.0f}', f'{c2:,.0f}', f'{r2:.2f}',
         '不可行（ROI<1）' if r2 < 1 else '可行'],
    ], columns=['场景', '触达人数', '客群客单价', '增量订单', '增量GMV',
                '增量毛利', '券成本', '模拟ROI', '结论'])
    print('\n=== 两种投放策略对比（均为模拟，假设参数同上）===')
    print(scenarios.to_string(index=False))
    better = '场景2 定向高价值客群' if r2 >= r1 else '场景1 全员发券'
    best = max(r1, r2)
    if best < 1:
        print(f'\n结论：两个场景模拟 ROI 均 < 1（投 1 元回收不足 1 元），当前假设下都不成立；'
              f'{better}更优（ROI {best:.2f}，较另一方案提升 {abs(r2 - r1):.2f}），')
        print('仍需进一步收紧人群、降低券面额或改用非价格类触达方式后复测。')
    else:
        print(f'\n结论：{better}可行（ROI {best:.2f} ≥ 1），建议小流量试投后验证真实效果。')
    print('注：以上均为模拟测算，非实际投放结果，简历与面试中必须标注"模拟"。')

    roi.to_csv(os.path.join(OUT_DIR, 'recall_roi_simulation.csv'), index=False,
               encoding='utf-8-sig')
    scenarios.to_csv(os.path.join(OUT_DIR, 'recall_roi_scenarios.csv'), index=False,
                     encoding='utf-8-sig')


# ==============================================================================
# 关联规则（可选，默认关闭）
# ==============================================================================
if RUN['association']:
    section('关联规则（可选模块）')
    try:
        from mlxtend.frequent_patterns import fpgrowth, association_rules
        basket = (sales_clean.groupby(['Invoice', 'StockCode'])['Quantity'].sum()
                  .unstack(fill_value=0))
        keep = (basket > 0).sum(axis=0)
        basket = basket[keep[keep >= 20].index]
        basket_sets = (basket > 0).astype(int)
        fi = fpgrowth(basket_sets, min_support=0.02, use_colnames=True, max_len=3)
        rules = association_rules(fi, metric='lift', min_threshold=1.2)
        rules = rules[rules['confidence'] >= 0.3].sort_values('lift', ascending=False).head(50)
        rules.to_csv(os.path.join(OUT_DIR, 'association_rules.csv'), index=False,
                     encoding='utf-8-sig')
        print(f'规则数: {len(rules)}，已保存 association_rules.csv')
    except Exception as e:
        print(f'关联规则模块跳过：{e}')


# ==============================================================================
# 导出
# ==============================================================================
section('导出结果')

if RUN['export_tableau']:
    for name, obj in [('monthly_metrics', monthly), ('weekly_metrics', weekly),
                      ('customer_profile', profile), ('product_abc', product_abc),
                      ('category_structure', category_structure),
                      ('segment_revenue', seg if rfm is not None else None),
                      ('metric_dictionary', metric_dictionary)]:
        if obj is not None:
            obj.to_csv(os.path.join(TABLEAU_DIR, f'{name}.csv'), encoding='utf-8-sig')
    print(f'Tableau 数据源已导出至: {TABLEAU_DIR}')

if RUN['export_excel']:
    try:
        xlsx_path = os.path.join(OUT_DIR, 'operations_report.xlsx')

        def excel_ready(table):
            """PeriodIndex / DatetimeIndex 转字符串，避免 openpyxl 写入报错"""
            if table is None:
                return None
            out = table.reset_index()
            for c in out.columns:
                if pd.api.types.is_period_dtype(out[c]):
                    out[c] = out[c].astype(str)
            return out

        with pd.ExcelWriter(xlsx_path, engine='openpyxl') as writer:
            sheets = [('指标字典', metric_dictionary), ('月度指标', monthly),
                      ('周度指标', weekly),
                      ('客户分层', seg if rfm is not None else None),
                      ('客户标签', profile), ('商品ABC', product_abc),
                      ('品类结构', category_structure), ('监控告警', alerts),
                      ('流失汇总', churn), ('ROI模拟', roi)]
            for name, obj in sheets:
                data = excel_ready(obj)
                if data is not None:
                    data.to_excel(writer, sheet_name=name[:31], index=False)
        print(f'多 sheet 报表已保存: {xlsx_path}')
    except Exception as e:
        print(f'Excel 导出失败（不影响 csv 结果）: {e}')

print('\n全部完成。输出目录:', OUT_DIR)
