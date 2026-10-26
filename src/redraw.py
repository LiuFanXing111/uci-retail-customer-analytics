
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from paths import (PROJ_ROOT, DATA_DIR, CACHE_DIR, OUT_DIR, FIG_DIR,
                   RAW_XLSX, RAW_PKL, ensure_dirs)
ensure_dirs()
import pandas as pd
import numpy as np
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DengXian']
plt.rcParams['axes.unicode_minus'] = False

OUT = CACHE_DIR
FIG = FIG_DIR
NAVY = '#1F4E79'
BLUE = '#2E75B6'
RED = '#C0504D'
GRAY = '#7F7F7F'
LGRAY = '#D9D9D9'
LBLUE = '#BDD7EE'

df = pd.read_pickle(RAW_PKL)
df = df.rename(columns={'Customer ID': 'CustomerID'})[
    ['Invoice', 'StockCode', 'Quantity', 'InvoiceDate', 'Price', 'CustomerID', 'Country']]
df['SC'] = df.StockCode.astype(str)
NONPROD = ['POST', 'DOT', 'BANK CHARGES', 'FBA', 'S', 'M', 'B', 'C2', 'CRUK', 'PADS', 'D', 'GIFT', 'AMAZONFEE']

# ---------- f4: cancel concentration, by invoice ----------
canc = df[(df.Invoice.astype(str).str.startswith('C')) & df.CustomerID.notna()
          & ~df.SC.isin(NONPROD)].copy()
canc['Amt'] = (canc.Quantity * canc.Price).abs()
by_inv = canc.groupby('Invoice')['Amt'].sum().sort_values(ascending=False)
ccum = np.cumsum(by_inv.values) / by_inv.sum() * 100
n_show = 200

fig, ax = plt.subplots(figsize=(7.6, 3.7))
ax.plot(np.arange(1, n_show + 1), ccum[:n_show], color=NAVY, linewidth=1.6)
ax.fill_between(np.arange(1, n_show + 1), 0, ccum[:n_show], color='#F4CCCC', alpha=0.55)
ax.scatter([1], [ccum[0]], color=RED, s=34, zorder=5)
ax.annotate('Top1 单笔占 %.1f%%\n（£168,470，23843 PAPER CRAFT）' % ccum[0],
            xy=(1, ccum[0]), xytext=(18, 10), fontsize=8.5, color=RED,
            arrowprops=dict(arrowstyle='-', color=RED, linewidth=0.8))
ax.annotate('Top10 占 %.1f%%' % ccum[9], xy=(10, ccum[9]), xytext=(46, 27),
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
ax.set_title('取消金额高度集中：前 10 张单占四成四，月度均值监控无效',
             fontsize=10.5, color='#262626', pad=9)
plt.tight_layout()
plt.savefig(os.path.join(FIG, 'f4_cancel.png'), dpi=200)
plt.close()
print('f4 ok top1=%.2f top2=%.2f top10=%.2f n_inv=%d total=%.2f'
      % (ccum[0], ccum[1], ccum[9], len(by_inv), by_inv.sum()), flush=True)

# ---------- f7: new customers, same month 2010 vs 2011 ----------
sales = df[(df.Quantity > 0) & (df.Price > 0)].copy()
sales['Revenue'] = sales.Quantity * sales.Price
clean = sales.dropna(subset=['CustomerID']).drop_duplicates(
    subset=['Invoice', 'StockCode', 'Quantity', 'InvoiceDate', 'Price', 'CustomerID', 'Country'])
clean = clean[~clean.SC.isin(NONPROD)].copy()
fm = clean.groupby('CustomerID')['InvoiceDate'].min().dt.to_period('M')
cnt = fm.value_counts().sort_index()

months = list(range(1, 12))
v2010 = [int(cnt.get(pd.Period('2010-%02d' % m, 'M'), 0)) for m in months]
v2011 = [int(cnt.get(pd.Period('2011-%02d' % m, 'M'), 0)) for m in months]

fig, ax = plt.subplots(figsize=(7.6, 3.7))
x = np.arange(len(months))
w = 0.38
ax.bar(x - w / 2, v2010, w, label='2010 年', color=LBLUE, edgecolor=BLUE, linewidth=0.6)
ax.bar(x + w / 2, v2011, w, label='2011 年', color=NAVY, edgecolor=NAVY, linewidth=0.6)
for i, (a, b) in enumerate(zip(v2010, v2011)):
    ax.text(i + w / 2, b + 8, '%d' % b, ha='center', va='bottom', fontsize=7, color=NAVY)
ax.axhline(np.mean(v2010), color=BLUE, linestyle='--', linewidth=0.9, alpha=0.7)
ax.axhline(np.mean(v2011), color=RED, linestyle='--', linewidth=0.9, alpha=0.7)
ax.text(10.4, np.mean(v2010) + 6, '2010 月均 %d' % round(np.mean(v2010)), fontsize=7.5,
        color=BLUE, ha='right')
ax.text(10.4, np.mean(v2011) + 6, '2011 月均 %d' % round(np.mean(v2011)), fontsize=7.5,
        color=RED, ha='right')
ax.set_xticks(x)
ax.set_xticklabels(['%d月' % m for m in months], fontsize=8)
ax.set_ylabel('当月首次购买的客户数', fontsize=9)
ax.set_ylim(0, max(v2010) * 1.22)
ax.grid(axis='y', color=LGRAY, linewidth=0.5, alpha=0.8)
ax.set_axisbelow(True)
for s in ['top', 'right']:
    ax.spines[s].set_visible(False)
ax.tick_params(labelsize=8)
ax.legend(frameon=False, fontsize=8.5, loc='upper right', ncol=2)
ax.set_title('同月新增客户：2011 年每个月都低于 2010 年，差距在收窄但未回正',
             fontsize=10.5, color='#262626', pad=9)
plt.tight_layout()
plt.savefig(os.path.join(FIG, 'f7_newcust.png'), dpi=200)
plt.close()
print('f7 ok 2010 mean=%.1f 2011 mean=%.1f' % (np.mean(v2010), np.mean(v2011)), flush=True)
for a, b in zip(v2010, v2011):
    print(a, b, '%.1f%%' % ((b / a - 1) * 100))
