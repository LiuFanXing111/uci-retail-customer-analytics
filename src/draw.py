
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

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DengXian']
plt.rcParams['axes.unicode_minus'] = False

OUT = CACHE_DIR
FIG = FIG_DIR
os.makedirs(FIG, exist_ok=True)

NAVY = '#1F4E79'
BLUE = '#2E75B6'
RED = '#C0504D'
GRAY = '#7F7F7F'
LGRAY = '#D9D9D9'
LBLUE = '#BDD7EE'

R = json.load(open(os.path.join(OUT, 'metrics.json'), encoding='utf-8'))


def ci(p, n, z=1.96):
    p = p / 100
    if n <= 0:
        return 0, 0
    se = sqrt(p * (1 - p) / n)
    return max(0, (p - z * se)) * 100, min(1, (p + z * se)) * 100


cohorts = [c for c in R['cohorts'] if c['c'] != '2011-12']
xs = np.arange(len(cohorts))
ys = np.array([c['m1'] for c in cohorts])
ns = np.array([c['size'] for c in cohorts])
los = np.array([ci(c['m1'], c['size'])[0] for c in cohorts])
his = np.array([ci(c['m1'], c['size'])[1] for c in cohorts])

fig, ax = plt.subplots(figsize=(7.6, 4.3))
ax.vlines(xs, los, his, color=BLUE, alpha=0.30, linewidth=2.6, zorder=1)
ax.plot(xs, ys, color=NAVY, linewidth=1.4, zorder=2, label='次月留存率')
ax.scatter(xs[1:], ys[1:], s=17 + ns[1:] / 22, color=NAVY, zorder=3, edgecolor='white', linewidth=0.5)
ax.scatter(xs[0], ys[0], s=95, facecolor='white', edgecolor=GRAY, linewidth=1.4, zorder=4)
i12 = [i for i, c in enumerate(cohorts) if c['c'] == '2010-12'][0]
ax.scatter(xs[i12], ys[i12], s=95, facecolor='white', edgecolor=RED, linewidth=1.6, zorder=5)

ax.axhline(19.89, xmax=0.52, color=BLUE, linestyle='--', linewidth=1.0, alpha=0.85)
ax.axhline(22.41, xmin=0.52, color=RED, linestyle='--', linewidth=1.0, alpha=0.85)
ax.text(6.3, 19.89, '2010 年加权 19.9%', fontsize=8, color=BLUE, va='bottom')
ax.text(15.6, 22.41, '2011 年加权 22.4%', fontsize=8, color=RED, va='bottom')

ax.annotate('数据首月批次，含存量客户\n35.3%（952 人）', xy=(0, 35.3), xytext=(1.1, 39.5),
            fontsize=8, color='#404040',
            arrowprops=dict(arrowstyle='-', color=GRAY, linewidth=0.7))
ax.annotate('全年最低点，仅 76 人\n9.2%，CI 2.7–15.7%', xy=(i12, 9.2), xytext=(i12 - 3.6, 4.2),
            fontsize=8, color=RED,
            arrowprops=dict(arrowstyle='-', color=RED, linewidth=0.7, alpha=0.8))

ax.set_xticks(xs)
ax.set_xticklabels([c['c'] for c in cohorts], rotation=90, fontsize=7)
ax.set_ylabel('次月留存率（%）', fontsize=9)
ax.set_xlabel('首购批次', fontsize=9)
ax.set_ylim(0, 46)
ax.tick_params(axis='y', labelsize=8)
ax.grid(axis='y', color=LGRAY, linewidth=0.5, alpha=0.8)
ax.set_axisbelow(True)
for s in ['top', 'right']:
    ax.spines[s].set_visible(False)
ax.set_title('24 个同期群的次月留存：波动区间重叠，无单调下滑', fontsize=10.5, color='#262626', pad=9)
fig.text(0.012, 0.012, '气泡大小表示队列人数；须线为 95% 置信区间（二项分布正态近似）',
         fontsize=7, color=GRAY)
plt.tight_layout(rect=[0, 0.03, 1, 1])
plt.savefig(os.path.join(FIG, 'f1_cohort.png'), dpi=200)
plt.close()
print('f1 ok', flush=True)

mon = R['monthly']
mx = [m['m'] for m in mon]
my = [m['gmv'] / 10000 for m in mon]
cols = [RED if m in ('2010-12', '2011-12') else LBLUE for m in mx]

fig, ax = plt.subplots(figsize=(7.6, 3.9))
ax.bar(range(len(mx)), my, color=cols, edgecolor=[RED if c == RED else BLUE for c in cols],
       linewidth=0.6, width=0.72)
ax.set_xticks(range(len(mx)))
ax.set_xticklabels(mx, rotation=90, fontsize=7)
ax.set_ylabel('月度 GMV（万英镑）', fontsize=9)
ax.grid(axis='y', color=LGRAY, linewidth=0.5, alpha=0.8)
ax.set_axisbelow(True)
for s in ['top', 'right']:
    ax.spines[s].set_visible(False)
ax.tick_params(axis='y', labelsize=8)

ax.axhline(69.0, color=GRAY, linestyle=':', linewidth=1.0)
ax.text(0.2, 69.0, '24 个整月均值 69.0 万', fontsize=8, color=GRAY, va='bottom')

i10 = mx.index('2010-11')
ax.annotate('11 月 115.6 万\n较均值 +67%', xy=(i10, my[i10]), xytext=(i10 - 3.4, 122),
            fontsize=8, color=NAVY, arrowprops=dict(arrowstyle='-', color=NAVY, linewidth=0.7))
i12b = mx.index('2011-12')
ax.annotate('仅 9 天数据\n不可与整月比较', xy=(i12b, my[i12b]), xytext=(i12b - 3.2, 78),
            fontsize=8, color=RED, arrowprops=dict(arrowstyle='-', color=RED, linewidth=0.7, alpha=0.8))
i12a = mx.index('2010-12')
ax.annotate('与上一工作簿\n重叠 9 天', xy=(i12a, my[i12a]), xytext=(i12a - 2.3, 72),
            fontsize=7.5, color=RED, arrowprops=dict(arrowstyle='-', color=RED, linewidth=0.7, alpha=0.8))

ax.set_title('月度 GMV：季节性主导，年度总量持平（2010 年 822 万 → 2011 年 817 万）',
             fontsize=10.5, color='#262626', pad=9)
plt.tight_layout()
plt.savefig(os.path.join(FIG, 'f2_monthly.png'), dpi=200)
plt.close()
print('f2 ok', flush=True)

df = pd.read_pickle(RAW_PKL)
df = df.rename(columns={'Customer ID': 'CustomerID'})[
    ['Invoice', 'StockCode', 'Description', 'Quantity', 'InvoiceDate', 'Price', 'CustomerID', 'Country']]
sales = df[(df.Quantity > 0) & (df.Price > 0)].copy()
sales['Revenue'] = sales.Quantity * sales.Price
sid = sales.dropna(subset=['CustomerID']).drop_duplicates(
    subset=['Invoice', 'StockCode', 'Quantity', 'InvoiceDate', 'Price', 'CustomerID', 'Country'])
NONPROD = ['POST', 'DOT', 'BANK CHARGES', 'FBA', 'S', 'M', 'B', 'C2', 'CRUK', 'PADS', 'D', 'GIFT', 'AMAZONFEE']
clean = sid[~sid.StockCode.astype(str).isin(NONPROD)].copy()

sku = clean.groupby('StockCode')['Revenue'].sum().sort_values(ascending=False)
cum = (sku.cumsum() / sku.sum() * 100).values
idx = np.arange(1, len(sku) + 1)

fig, ax = plt.subplots(figsize=(7.6, 3.9))
ax.plot(idx, cum, color=NAVY, linewidth=1.6)
ax.fill_between(idx, 0, cum, color=LBLUE, alpha=0.45)
a_n = R['sku_a_n']
ax.axvline(a_n, color=RED, linestyle='--', linewidth=1.0)
ax.axhline(80, color=RED, linestyle='--', linewidth=1.0)
ax.scatter([a_n], [80], color=RED, s=30, zorder=5)
ax.annotate('A 类 %d 个 SKU\n占 %.1f%% 数量、贡献 80%% 营收' % (a_n, a_n / len(sku) * 100),
            xy=(a_n, 80), xytext=(a_n + 380, 44), fontsize=8.5, color=RED,
            arrowprops=dict(arrowstyle='-', color=RED, linewidth=0.8))
ax.annotate('Top10：%.1f%%\nTop100：%.1f%%' % (R['sku_top10_share'], R['sku_top100_share']),
            xy=(100, R['sku_top100_share']), xytext=(700, 12), fontsize=8, color=NAVY,
            arrowprops=dict(arrowstyle='-', color=NAVY, linewidth=0.7))
ax.set_xlabel('SKU 按营收降序排名', fontsize=9)
ax.set_ylabel('累计营收占比（%）', fontsize=9)
ax.set_xlim(0, len(sku))
ax.set_ylim(0, 102)
ax.grid(color=LGRAY, linewidth=0.5, alpha=0.8)
ax.set_axisbelow(True)
for s in ['top', 'right']:
    ax.spines[s].set_visible(False)
ax.tick_params(labelsize=8)
ax.set_title('商品营收累计曲线：A 类是千级商品池，不是少数爆款', fontsize=10.5, color='#262626', pad=9)
plt.tight_layout()
plt.savefig(os.path.join(FIG, 'f3_pareto.png'), dpi=200)
plt.close()
print('f3 ok', flush=True)

canc = df[(df.Invoice.astype(str).str.startswith('C')) & df.CustomerID.notna()
          & ~df.StockCode.astype(str).isin(NONPROD)].copy()
amt = (canc.Quantity * canc.Price).abs().sort_values(ascending=False).values
ccum = np.cumsum(amt) / amt.sum() * 100

fig, ax = plt.subplots(figsize=(7.6, 3.7))
n_show = 200
ax.plot(np.arange(1, n_show + 1), ccum[:n_show], color=NAVY, linewidth=1.6)
ax.fill_between(np.arange(1, n_show + 1), 0, ccum[:n_show], color='#F4CCCC', alpha=0.55)
ax.scatter([1], [ccum[0]], color=RED, s=34, zorder=5)
ax.annotate('Top1 单笔占 %.1f%%\n（£168,470，23843 PAPER CRAFT）' % ccum[0],
            xy=(1, ccum[0]), xytext=(16, 12), fontsize=8.5, color=RED,
            arrowprops=dict(arrowstyle='-', color=RED, linewidth=0.8))
ax.annotate('Top10 占 %.1f%%' % ccum[9], xy=(10, ccum[9]), xytext=(40, 30),
            fontsize=8.5, color=NAVY, arrowprops=dict(arrowstyle='-', color=NAVY, linewidth=0.7))
ax.set_xlabel('取消单按金额降序排名', fontsize=9)
ax.set_ylabel('累计占取消总额（%）', fontsize=9)
ax.set_xlim(0, n_show)
ax.set_ylim(0, 100)
ax.grid(color=LGRAY, linewidth=0.5, alpha=0.8)
ax.set_axisbelow(True)
for s in ['top', 'right']:
    ax.spines[s].set_visible(False)
ax.tick_params(labelsize=8)
ax.set_title('取消金额高度集中：前 10 笔占掉四成，均值监控无效', fontsize=10.5, color='#262626', pad=9)
plt.tight_layout()
plt.savefig(os.path.join(FIG, 'f4_cancel.png'), dpi=200)
plt.close()
print('f4 ok', flush=True)

costs = R['sens']['costs']
rows = R['sens']['rows']
mat = np.array([r['roi'] for r in rows])
fig, ax = plt.subplots(figsize=(5.6, 3.4))
im = ax.imshow(mat, cmap='RdYlGn', vmin=0, vmax=2.2, aspect='auto')
ax.set_xticks(range(len(costs)))
ax.set_xticklabels(['£%d' % c for c in costs], fontsize=9)
ax.set_yticks(range(len(rows)))
ax.set_yticklabels(['%d%%' % round(r['uplift'] * 100) for r in rows], fontsize=9)
ax.set_xlabel('人均触达成本', fontsize=9)
ax.set_ylabel('uplift（回流率增量）', fontsize=9)
for i in range(mat.shape[0]):
    for j in range(mat.shape[1]):
        v = mat[i, j]
        ax.text(j, i, '%.2f' % v, ha='center', va='center', fontsize=9,
                color='white' if v < 0.35 or v > 1.7 else '#262626',
                fontweight='bold' if v >= 1 else 'normal')
ax.set_title('定向场景 ROI 敏感性：只有左上四格过线', fontsize=10, color='#262626', pad=8)
cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
cb.set_label('ROI', fontsize=8)
cb.ax.tick_params(labelsize=7)
plt.tight_layout()
plt.savefig(os.path.join(FIG, 'f5_sens.png'), dpi=200)
plt.close()
print('f5 ok', flush=True)

rfm = R['rfm']
rfm = sorted(rfm, key=lambda r: -r['rev_share'])
names = [r['seg'] for r in rfm]
nsh = [r['n_share'] for r in rfm]
rsh = [r['rev_share'] for r in rfm]
yy = np.arange(len(names))
fig, ax = plt.subplots(figsize=(7.2, 3.9))
h = 0.36
ax.barh(yy + h / 2, nsh, height=h, color=LBLUE, edgecolor=BLUE, linewidth=0.6, label='人数占比')
ax.barh(yy - h / 2, rsh, height=h, color=NAVY, label='营收占比')
ax.set_yticks(yy)
ax.set_yticklabels(names, fontsize=8.5)
ax.invert_yaxis()
ax.set_xlabel('占比（%）', fontsize=9)
for i, (a, b) in enumerate(zip(nsh, rsh)):
    ax.text(a + 0.8, i + h / 2, '%.1f' % a, va='center', fontsize=7.5, color=BLUE)
    ax.text(b + 0.8, i - h / 2, '%.1f' % b, va='center', fontsize=7.5, color=NAVY)
ax.grid(axis='x', color=LGRAY, linewidth=0.5, alpha=0.8)
ax.set_axisbelow(True)
for s in ['top', 'right']:
    ax.spines[s].set_visible(False)
ax.tick_params(labelsize=8)
ax.legend(fontsize=8, frameon=False, loc='lower right')
ax.set_xlim(0, max(max(nsh), max(rsh)) * 1.18)
ax.set_title('RFM 七层：人数与营收的错位是客户策略的起点', fontsize=10.5, color='#262626', pad=9)
plt.tight_layout()
plt.savefig(os.path.join(FIG, 'f6_rfm.png'), dpi=200)
plt.close()
print('f6 ok', flush=True)
print('SKU total', len(sku), 'A', a_n)
