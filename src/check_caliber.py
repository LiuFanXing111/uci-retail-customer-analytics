# -*- coding: utf-8 -*-
"""复现报告口径：从原始流水走到「有效订单 36,639 / 客户 5,861」。

这一步的意义是确保后文所有指标的分母是同一个东西。口径不一致是数据分析
里最常见也最难查的错误——同一份数据能算出好几个 GMV，差别只在几行过滤。

运行：python src/check_caliber.py
需要先跑 src/prepare_data.py 生成缓存。
"""
import os as _os
import sys as _sys

_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from paths import RAW_PKL, ensure_dirs, PROJ_ROOT  # noqa: E402

ensure_dirs()

import pandas as pd  # noqa: E402

# ---------------------------------------------------------------- 口径常量
# 非商品编码：邮费、银行费用、手工调整、赠品、折扣等，不是商品
EXACT_NON_PRODUCT = {'POST', 'DOT', 'BANK CHARGES', 'CRUK',
                     'S', 'M', 'B', 'C2', 'D', 'AMAZONFEE'}
PREFIX_NON_PRODUCT = ('gift_0001', 'DCGS', 'BANK', 'AMAZON')

DEDUP_KEYS = ['Invoice', 'StockCode', 'Quantity', 'InvoiceDate',
              'Price', 'CustomerID', 'Country']

# 报告中的目标值
TARGET_ORDERS = 36639
TARGET_CUSTOMERS = 5861
REPORT_GMV = 17073078.0


def is_non_product(code):
    c = str(code).strip()
    return c in EXACT_NON_PRODUCT or c.startswith(PREFIX_NON_PRODUCT)


def main():
    df = pd.read_pickle(RAW_PKL).rename(columns={'Customer ID': 'CustomerID'})
    df = df[['Invoice', 'StockCode', 'Description', 'Quantity', 'InvoiceDate',
             'Price', 'CustomerID', 'Country', 'source_sheet']].copy()

    print('原始行数 %d' % len(df))
    print('日期范围 %s -> %s' % (df.InvoiceDate.min(), df.InvoiceDate.max()))
    print('C 开头（退货单）%d | 负数量 %d | 负价格 %d'
          % (df.Invoice.astype(str).str.startswith('C').sum(),
             (df.Quantity < 0).sum(), (df.Price < 0).sum()))

    # 第 1 步：只保留正向销售
    sales = df[(df.Quantity > 0) & (df.Price > 0)].copy()
    sales['Revenue'] = sales.Quantity * sales.Price
    print('\n[1] Quantity>0 且 Price>0  行 %d 单 %d GMV %.2f'
          % (len(sales), sales.Invoice.nunique(), sales.Revenue.sum()))

    # 第 2 步：客户结构类指标必须有客户 ID
    sid = sales.dropna(subset=['CustomerID']).copy()
    print('[2] + CustomerID 非空        行 %d 单 %d 客户 %d GMV %.2f'
          % (len(sid), sid.Invoice.nunique(), sid.CustomerID.nunique(),
             sid.Revenue.sum()))

    # 第 3 步：两个工作表在 2010-12-01~09 重叠，必须去重
    sid_d = sid.drop_duplicates(subset=DEDUP_KEYS)
    dup_rows = len(sid) - len(sid_d)
    print('[3] + 七列去重             行 %d 单 %d GMV %.2f （去掉重复 %d 行）'
          % (len(sid_d), sid_d.Invoice.nunique(), sid_d.Revenue.sum(), dup_rows))

    # 第 4 步：剔除非商品编码
    clean = sid_d[~sid_d.StockCode.apply(is_non_product)].copy()
    gmv = clean.Revenue.sum()
    print('[4] + 剔除非商品编码        行 %d 单 %d 客户 %d GMV %.2f'
          % (len(clean), clean.Invoice.nunique(), clean.CustomerID.nunique(), gmv))

    orders = clean.Invoice.nunique()
    customers = clean.CustomerID.nunique()

    print('\n=== 与报告对撞 ===')
    print('有效订单 %d  目标 %d  %s' % (orders, TARGET_ORDERS,
                                      'OK' if orders == TARGET_ORDERS else 'MISMATCH'))
    print('客户数   %d  目标 %d  %s' % (customers, TARGET_CUSTOMERS,
                                      'OK' if customers == TARGET_CUSTOMERS else 'MISMATCH'))
    print('GMV      %.2f  报告 %.2f  差 %.2f' % (gmv, REPORT_GMV, gmv - REPORT_GMV))
    print('客单价   %.2f  报告 465.98' % (gmv / orders))
    print('有效 SKU %d' % clean.StockCode.nunique())

    # 两个主键必须精确命中，否则后文所有分母都不对
    assert orders == TARGET_ORDERS, '订单数对不上：%d' % orders
    assert customers == TARGET_CUSTOMERS, '客户数对不上：%d' % customers

    print('\n订单数与客户数精确命中。GMV 相差 %.2f 英镑（占 %.4f%%），'
          % (gmv - REPORT_GMV, abs(gmv - REPORT_GMV) / REPORT_GMV * 100))
    print('来自非商品编码清单里几个小额科目的取舍；两种清单组合都试过，'
          '这 0.003%% 消不掉，报告正文用的是 %.0f。' % REPORT_GMV)

    # 顺带把影响最大的非商品编码列出来，便于核对
    print('\n非商品编码里营收最大的 12 个：')
    nonprod = sid_d[sid_d.StockCode.apply(is_non_product)]
    top = (nonprod.groupby('StockCode')
           .agg(营收=('Revenue', 'sum'), 行数=('Revenue', 'size'))
           .sort_values('营收', ascending=False).head(12))
    print(top.round(2).to_string())


if __name__ == '__main__':
    main()
