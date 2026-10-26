
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from paths import (PROJ_ROOT, DATA_DIR, CACHE_DIR, OUT_DIR, FIG_DIR,
                   RAW_XLSX, RAW_PKL, ensure_dirs)
ensure_dirs()
import pandas as pd
import numpy as np
import json
import os
from math import sqrt

OUT = CACHE_DIR
R = json.load(open(os.path.join(OUT, 'metrics.json'), encoding='utf-8'))

def ci(p, n, z=1.96):
    p = p / 100
    se = sqrt(p * (1 - p) / n)
    return round(max(0, (p - z * se)) * 100, 2), round(min(1, (p + z * se)) * 100, 2), round(se * 100, 2)

print('=== 逐批次留存 + 95% 置信区间 ===')
rows = []
for c in R['cohorts']:
    if c['c'] == '2011-12':
        continue
    lo, hi, se = ci(c['m1'], c['size'])
    rows.append((c['c'], c['size'], c['m1'], lo, hi, se))
    print('%-8s n=%-4d m1=%5.2f%%  CI[%5.2f, %5.2f]  SE=%.2f' % (c['c'], c['size'], c['m1'], lo, hi, se))

print('\n=== 分年加权留存（剔除 2009-12 首月）===')
for y in ['2010', '2011']:
    sub = [r for r in rows if r[0].startswith(y)]
    N = sum(r[1] for r in sub)
    K = sum(r[1] * r[2] / 100 for r in sub)
    p = K / N * 100
    lo, hi, se = ci(p, N)
    print('%s: 批次%d  N=%d  retained=%.1f  pooled=%.2f%%  CI[%.2f, %.2f]' % (y, len(sub), N, K, p, lo, hi))

print('\n=== 两比例差异检验（2010 vs 2011）===')
s10 = [r for r in rows if r[0].startswith('2010')]
s11 = [r for r in rows if r[0].startswith('2011')]
n1 = sum(r[1] for r in s10); k1 = sum(r[1] * r[2] / 100 for r in s10)
n2 = sum(r[1] for r in s11); k2 = sum(r[1] * r[2] / 100 for r in s11)
p1, p2 = k1 / n1, k2 / n2
pp = (k1 + k2) / (n1 + n2)
se = sqrt(pp * (1 - pp) * (1 / n1 + 1 / n2))
z = (p2 - p1) / se
print('p2010=%.4f p2011=%.4f diff=%.4f  z=%.3f  (|z|>1.96 显著)' % (p1, p2, p2 - p1, z))

print('\n=== 2009-12 首月批次构成（是否含存量客户）===')
df = pd.read_pickle(RAW_PKL)
df = df.rename(columns={'Customer ID': 'CustomerID'})[
    ['Invoice', 'StockCode', 'Description', 'Quantity', 'InvoiceDate', 'Price', 'CustomerID', 'Country']]
sales = df[(df.Quantity > 0) & (df.Price > 0)].copy()
sales['Revenue'] = sales.Quantity * sales.Price
sid = sales.dropna(subset=['CustomerID']).drop_duplicates(
    subset=['Invoice', 'StockCode', 'Quantity', 'InvoiceDate', 'Price', 'CustomerID', 'Country'])
NONPROD = ['POST', 'DOT', 'BANK CHARGES', 'FBA', 'S', 'M', 'B', 'C2', 'CRUK', 'PADS', 'D', 'GIFT', 'AMAZONFEE']
clean = sid[~sid.StockCode.astype(str).isin(NONPROD)].copy()
first = clean.groupby('CustomerID')['InvoiceDate'].min()
d0 = first[first < '2010-01-01']
print('2009-12 首购客户 %d 人，其首单日期分布：' % len(d0))
print(d0.dt.day.value_counts().sort_index().to_string())
print('其中 12-01 当天首购: %d 人 (%.1f%%)' % ((d0.dt.day == 1).sum(), (d0.dt.day == 1).mean() * 100))

print('\n=== 2010-12 批次 7 人复购明细 ===')
cust_first = first.dt.to_period('M').astype(str)
b = cust_first[cust_first == '2010-12']
print('人数', len(b))

print('\n=== 取消口径重修 ===')
df['IsCancel'] = (df.Invoice.astype(str).str.startswith('C')) | (df.Quantity < 0) | (df.Price < 0)
for name, mask in [
    ('全部IsCancel', df.IsCancel),
    ('C开头', df.Invoice.astype(str).str.startswith('C')),
    ('C开头+客户ID非空', df.Invoice.astype(str).str.startswith('C') & df.CustomerID.notna()),
    ('C开头+客户ID+剔非商品', df.Invoice.astype(str).str.startswith('C') & df.CustomerID.notna() & ~df.StockCode.astype(str).isin(NONPROD)),
    ('IsCancel+客户ID+剔非商品', df.IsCancel & df.CustomerID.notna() & ~df.StockCode.astype(str).isin(NONPROD)),
]:
    sub = df[mask].copy()
    amt = (sub.Quantity * sub.Price).abs()
    byrow = amt.sort_values(ascending=False)
    tot = byrow.sum()
    print('%-26s 行%6d 单%5d 金额%12.2f  top1%%=%5.2f  top10%%=%5.2f' % (
        name, len(sub), sub.Invoice.nunique(), tot,
        byrow.iloc[0] / tot * 100, byrow.head(10).sum() / tot * 100))
