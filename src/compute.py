
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from paths import (PROJ_ROOT, DATA_DIR, CACHE_DIR, OUT_DIR, FIG_DIR,
                   RAW_XLSX, RAW_PKL, ensure_dirs)
ensure_dirs()
import pandas as pd
import numpy as np
import json
import os

OUT = CACHE_DIR
df = pd.read_pickle(RAW_PKL)
df = df.rename(columns={'Customer ID': 'CustomerID'})[
    ['Invoice', 'StockCode', 'Description', 'Quantity', 'InvoiceDate',
     'Price', 'CustomerID', 'Country']]

df['IsCancel'] = (df.Invoice.astype(str).str.startswith('C')) | (df.Quantity < 0) | (df.Price < 0)

sales = df[(df.Quantity > 0) & (df.Price > 0)].copy()
sales['Revenue'] = sales.Quantity * sales.Price
sid = sales.dropna(subset=['CustomerID']).drop_duplicates(
    subset=['Invoice', 'StockCode', 'Quantity', 'InvoiceDate', 'Price', 'CustomerID', 'Country'])

NONPROD = ['POST', 'DOT', 'BANK CHARGES', 'FBA', 'S', 'M', 'B', 'C2', 'CRUK', 'PADS', 'D', 'GIFT', 'AMAZONFEE']
clean = sid[~sid.StockCode.astype(str).isin(NONPROD)].copy()
clean['YearMonth'] = clean.InvoiceDate.dt.to_period('M')
clean['Year'] = clean.InvoiceDate.dt.year

R = {}
R['rows_raw'] = int(len(df))
R['orders'] = int(clean.Invoice.nunique())
R['customers'] = int(clean.CustomerID.nunique())
R['gmv'] = float(clean.Revenue.sum())
R['aov'] = float(clean.Revenue.sum() / clean.Invoice.nunique())

print('GMV %.2f 单 %d 客户 %d' % (R['gmv'], R['orders'], R['customers']), flush=True)

mon = clean.groupby('YearMonth')['Revenue'].sum()
R['monthly'] = [{'m': str(k), 'gmv': float(v)} for k, v in mon.items()]

yr = clean.groupby('Year')['Revenue'].sum()
R['yearly'] = {str(k): float(v) for k, v in yr.items()}

inv_month = clean.groupby('Invoice')['YearMonth'].min()
order_n = clean.groupby('YearMonth')['Invoice'].nunique()
R['monthly_orders'] = {str(k): int(v) for k, v in order_n.items()}

cust = clean.groupby('CustomerID').agg(
    first=('InvoiceDate', 'min'),
    last=('InvoiceDate', 'max'),
    freq=('Invoice', 'nunique'),
    monet=('Revenue', 'sum'),
    first_amt=('Revenue', 'sum'))
first_order_amt = (clean.sort_values('InvoiceDate')
                   .groupby(['CustomerID', 'Invoice'])['Revenue'].sum()
                   .reset_index().groupby('CustomerID')['Revenue'].first())
cust['first_order_amt'] = first_order_amt
cust['first_month'] = cust['first'].dt.to_period('M')

orders = (clean.groupby(['CustomerID', 'YearMonth'])['Invoice'].nunique()
          .reset_index().rename(columns={'Invoice': 'n_orders'}))
cohort_set = cust[['first_month']].reset_index()
om = orders.merge(cohort_set, on='CustomerID')
om['period_idx'] = (om.YearMonth - om.first_month).apply(lambda x: x.n)

cohorts = []
for cm, g in om.groupby('first_month'):
    size = int(cust[cust.first_month == cm].shape[0])
    m1 = g[g.period_idx == 1].CustomerID.nunique()
    cohorts.append({'c': str(cm), 'size': size, 'm1': round(m1 / size * 100, 2) if size else None})
R['cohorts'] = cohorts
print('cohorts', len(cohorts), flush=True)

def retail(r, f, m):
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

snap = clean.InvoiceDate.max() + pd.Timedelta(days=1)
c2 = cust.copy()
c2['R'] = snap - c2['last']
c2['R'] = (c2['R'].dt.days)
c2['R_s'] = pd.qcut(c2.R.rank(method='first'), 5, labels=[5, 4, 3, 2, 1]).astype(int)
c2['F_s'] = pd.qcut(c2.freq.rank(method='first'), 5, labels=[1, 2, 3, 4, 5]).astype(int)
c2['M_s'] = pd.qcut(c2.monet.rank(method='first'), 5, labels=[1, 2, 3, 4, 5]).astype(int)
c2['seg'] = [retail(r, f, m) for r, f, m in zip(c2.R_s, c2.F_s, c2.M_s)]
seg = c2.groupby('seg').agg(n=('monet', 'size'), rev=('monet', 'sum')).reset_index()
seg['n_share'] = seg.n / seg.n.sum() * 100
seg['rev_share'] = seg.rev / seg.rev.sum() * 100
R['rfm'] = [{'seg': r.seg, 'n': int(r.n), 'n_share': round(r.n_share, 2),
             'rev': float(r.rev), 'rev_share': round(r.rev_share, 2)} for r in seg.itertuples()]
print(seg.round(2).to_string(), flush=True)

sku = clean.groupby('StockCode')['Revenue'].sum().sort_values(ascending=False)
cum = sku.cumsum() / sku.sum() * 100
R['sku_total'] = int(len(sku))
R['pareto'] = [{'rank': int(i + 1), 'code': str(k), 'rev': float(v), 'cum': round(float(cum.iloc[i]), 3)}
               for i, (k, v) in enumerate(sku.head(300).items())]
R['sku_a_n'] = int((cum <= 80).sum() + 1)
R['sku_top10_share'] = round(float(cum.iloc[9]), 2)
R['sku_top100_share'] = round(float(cum.iloc[99]), 2)

canc = df[df.IsCancel].copy()
canc['Amt'] = (canc.Quantity * canc.Price).abs()
canc_c = canc.dropna(subset=['CustomerID'])
by_inv = canc_c.groupby('Invoice')['Amt'].sum().sort_values(ascending=False)
ccum = by_inv.cumsum() / by_inv.sum() * 100
R['cancel'] = {
    'n_orders': int(len(by_inv)),
    'total': float(by_inv.sum()),
    'top1': round(float(ccum.iloc[0]), 2),
    'top2': round(float(ccum.iloc[1]), 2),
    'top10': round(float(ccum.iloc[9]), 2),
    'curve': [{'rank': int(i + 1), 'cum': round(float(v), 2)} for i, v in enumerate(ccum.head(200).values)],
}
R['cancel_rate_orders'] = round(canc_c.Invoice.nunique() / R['orders'] * 100, 2)
R['cancel_rate_amt'] = round(by_inv.sum() / R['gmv'] * 100, 2)
print('cancel', R['cancel']['top1'], R['cancel']['top10'], R['cancel_rate_orders'], R['cancel_rate_amt'], flush=True)

def decomp(batch_a, batch_b, bins, labels):
    sub = c2[c2.first_month.astype(str).isin([batch_a, batch_b])].copy()
    om2 = om.copy()
    om2['cohort'] = om2.first_month.astype(str)
    m1 = om2[om2.period_idx == 1][['CustomerID', 'cohort']].drop_duplicates()
    m1['retained'] = 1
    sub = sub.merge(m1[['CustomerID', 'retained']], on='CustomerID', how='left')
    sub['retained'] = sub['retained'].fillna(0)
    sub['tier'] = pd.cut(sub.first_order_amt, bins=bins, labels=labels)
    out = {}
    for b in (batch_a, batch_b):
        s = sub[sub.first_month.astype(str) == b]
        out[b] = {
            'n': int(len(s)),
            'raw': round(float(s.retained.mean() * 100), 2),
            'tiers': [{'t': str(t), 'n': int(g.shape[0]),
                       'r': round(float(g.retained.mean() * 100), 2)}
                      for t, g in s.groupby('tier', observed=True)],
            'amt_mean': round(float(s.first_order_amt.mean()), 2),
        }
    allsub = sub.copy()
    w = allsub.groupby('tier', observed=True).size() / len(allsub)
    for b in (batch_a, batch_b):
        s = sub[sub.first_month.astype(str) == b]
        rates = s.groupby('tier', observed=True).retained.mean() * 100
        std = float((rates.reindex(w.index).fillna(0) * w).sum())
        out[b]['std'] = round(std, 2)
    out['raw_gap'] = round(out[batch_b]['raw'] - out[batch_a]['raw'], 2)
    out['std_gap'] = round(out[batch_b]['std'] - out[batch_a]['std'], 2)
    out['composition_effect'] = round(out['raw_gap'] - out['std_gap'], 2)
    return out

R['decomp'] = decomp('2009-12', '2010-12',
                     [0, 100, 300, 1000, np.inf],
                     ['≤£100', '£100–300', '£300–1000', '>£1000'])
print('decomp', json.dumps(R['decomp'], ensure_ascii=False)[:400], flush=True)

sens = []
for up in [0.02, 0.03, 0.05, 0.08]:
    row = []
    for cost in [3, 5, 8, 13]:
        row.append(round(up * 540.22 * 0.30 / cost, 2))
    sens.append({'uplift': up, 'roi': row})
R['sens'] = {'costs': [3, 5, 8, 13], 'rows': sens}

R['repeat_rate'] = round(float((cust.freq >= 2).mean() * 100), 2)
R['freq_le10'] = round(float((cust.freq <= 10).mean() * 100), 2)

uk = clean[clean.Country == 'United Kingdom']['Revenue'].sum()
R['uk_share'] = round(float(uk / R['gmv'] * 100), 2)

json.dump(R, open(os.path.join(OUT, 'metrics.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
print('\nsaved metrics.json', flush=True)
print('yearly', R['yearly'], flush=True)
print('uk', R['uk_share'], 'repeat', R['repeat_rate'], 'freq<=10', R['freq_le10'], flush=True)
