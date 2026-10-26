# -*- coding: utf-8 -*-
"""补四个数：滞销SKU营收、关联规则覆盖、RFM x 生命周期、数据质量表（口径与报告一致）"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from paths import (PROJ_ROOT, DATA_DIR, CACHE_DIR, OUT_DIR, FIG_DIR,
                   RAW_XLSX, RAW_PKL, ensure_dirs)
ensure_dirs()
import pandas as pd, numpy as np, json

OPS = OUT_DIR
OUT = CACHE_DIR
res = {}

# ================= 清洗（严格复现报告口径） =================
raw = pd.read_pickle(RAW_PKL).rename(columns={"Customer ID": "CustomerID"})
raw["InvoiceStr"] = raw["Invoice"].astype(str)
sales = raw[(raw.Quantity > 0) & (raw.Price > 0)].copy()
sales["Revenue"] = sales.Quantity * sales.Price
sid = sales.dropna(subset=["CustomerID"]).copy()
SUBSET = ["Invoice", "StockCode", "Quantity", "InvoiceDate", "Price", "CustomerID", "Country"]
sid_d = sid.drop_duplicates(subset=SUBSET)
NONPROD = ["POST", "DOT", "BANK CHARGES", "AMAZONFEE", "FBA", "S", "M", "B", "C2", "CRUK", "PADS", "D", "GIFT"]
clean = sid_d[~sid_d.StockCode.astype(str).isin(NONPROD)].copy()

assert clean.Invoice.nunique() == 36639, clean.Invoice.nunique()
assert clean.CustomerID.nunique() == 5861, clean.CustomerID.nunique()
print("clean rows/orders/customers/GMV:", len(clean), clean.Invoice.nunique(),
      clean.CustomerID.nunique(), round(clean.Revenue.sum(), 2))

# ================= 1. 滞销 SKU 营收贡献 =================
abc = pd.read_csv(OPS + r"\product_abc.csv")
abc.columns = [c.replace("\ufeff", "") for c in abc.columns]
tot_rev = abc["Revenue"].sum()
slow = abc[abc["IsSlowMoving"] == 1]
fast = abc[abc["IsSlowMoving"] == 0]
res["abc"] = {
    "sku_total": len(abc), "rev_total": round(tot_rev, 2),
    "slow_n": len(slow), "slow_share_n": round(len(slow) / len(abc) * 100, 2),
    "slow_rev": round(slow["Revenue"].sum(), 2),
    "slow_share_rev": round(slow["Revenue"].sum() / tot_rev * 100, 2),
    "slow_rev_median": round(slow["Revenue"].median(), 2),
    "slow_rev_mean": round(slow["Revenue"].mean(), 2),
    "slow_rev_max": round(slow["Revenue"].max(), 2),
    "slow_top10_share": round(slow["Revenue"].nlargest(10).sum() / slow["Revenue"].sum() * 100, 2),
    "slow_inactive_median": round(slow["InactiveDays"].median(), 1),
    "slow_abc": {k: int(v) for k, v in slow["ABC"].value_counts().items()},
    "fast_n": len(fast),
    "fast_rev_median": round(fast["Revenue"].median(), 2),
    "fast_rev_mean": round(fast["Revenue"].mean(), 2),
    "slow_rev_per_sku_per_year": round(slow["Revenue"].sum() / len(slow) / 2, 2),
}
# 滞销里 A 类那 69 个的营收
slowA = slow[slow["ABC"] == "A"]
res["abc"]["slow_A_n"] = len(slowA)
res["abc"]["slow_A_rev"] = round(slowA["Revenue"].sum(), 2)

# ================= 2. 关联规则覆盖订单数 =================
inv_sets = clean.groupby("Invoice")["StockCode"].apply(lambda s: set(s.astype(str))).values
n_orders = len(inv_sets)
rules = pd.read_csv(OPS + r"\association_rules_tableau.csv")
rules.columns = [c.replace("\ufeff", "") for c in rules.columns]
rows, touched = [], np.zeros(n_orders, dtype=bool)
for _, r in rules.iterrows():
    ant, con = {str(r["antecedent_code"])}, {str(r["consequent_code"])}
    hit = np.array([(ant | con) <= s for s in inv_sets])
    touched |= hit
    rows.append((int(r["rule_id"]), int(hit.sum())))
cov = pd.DataFrame(rows, columns=["rule_id", "orders_both"])
rules = rules.merge(cov, on="rule_id")
rules["coverage_pct"] = (rules["orders_both"] / n_orders * 100).round(2)
res["rules"] = {
    "n_orders": n_orders, "rules_n": len(rules),
    "orders_both_min": int(rules.orders_both.min()),
    "orders_both_median": float(rules.orders_both.median()),
    "orders_both_max": int(rules.orders_both.max()),
    "cov_pct_median": float(rules.coverage_pct.median()),
    "union_orders": int(touched.sum()),
    "union_pct": round(touched.sum() / n_orders * 100, 2),
    "top1_rule": {k: (float(v) if isinstance(v, (np.floating, float)) else v)
                  for k, v in rules.loc[rules["lift"].idxmax()].items() if k != "lift_gt_10"},
}
rules.sort_values("lift", ascending=False).to_csv(OUT + r"\association_rules_coverage.csv",
                                                 index=False, encoding="utf-8-sig")

# ================= 3. RFM x 生命周期 =================
cp = pd.read_csv(OPS + r"\customer_profile.csv")
cp.columns = [c.replace("\ufeff", "") for c in cp.columns]
seg_order = ["Champions", "Loyal Customers", "Potential Loyalists", "New Customers",
             "At Risk", "Hibernating", "Others"]
life_order = [c for c in ["新客", "成长期", "成熟期", "衰退期", "沉默期", "流失期"] if c in cp.LifeStage.unique()]
ct_n = pd.crosstab(cp.Segment, cp.LifeStage).reindex(index=seg_order, columns=life_order).fillna(0).astype(int)
ct_m = cp.pivot_table(index="Segment", columns="LifeStage", values="Monetary", aggfunc="sum") \
        .reindex(index=seg_order, columns=life_order).fillna(0)
ct_n.to_csv(OUT + r"\rfm_life_count.csv", encoding="utf-8-sig")
(ct_m / 1e4).round(1).to_csv(OUT + r"\rfm_life_monetary_wan.csv", encoding="utf-8-sig")

ar = cp[cp.Segment == "At Risk"]
res["cross"] = {
    "total": int(ct_n.values.sum()),
    "seg_order": seg_order, "life_order": life_order,
    "count": ct_n.values.tolist(),
    "monetary_wan": (ct_m / 1e4).round(1).values.tolist(),
    "atrisk_n": len(ar),
    "atrisk_rev": round(ar.Monetary.sum(), 2),
    "atrisk_rev_share": round(ar.Monetary.sum() / cp.Monetary.sum() * 100, 2),
    "atrisk_median_gap": float(ar.MedianGap.median()),
    "champ_all_mature": bool((ct_n.loc["Champions"] > 0).sum() == 1),
    "atrisk_life": {k: int(v) for k, v in ar.LifeStage.value_counts().items()},
    # 二维矩阵替代方案：历史价值分位 x 沉默天数
}
cp["value_q"] = pd.qcut(cp.Monetary, 5, labels=["V1低", "V2", "V3", "V4", "V5高"])
cp["silent_bin"] = pd.cut(cp.Recency, [-1, 60, 180, 365, 10000],
                          labels=["<=60天", "61-180天", "181-365天", ">365天"])
m2 = pd.crosstab(cp.value_q, cp.silent_bin)
res["cross"]["value_x_silent"] = {"rows": m2.index.tolist(), "cols": [str(c) for c in m2.columns],
                                  "count": m2.values.tolist()}
m2.to_csv(OUT + r"\value_silent_matrix.csv", encoding="utf-8-sig")

# ================= 4. 数据质量 =================
q = {}
q["raw_rows"] = len(raw)
q["raw_orders"] = int(raw.InvoiceStr.nunique())
q["raw_skus"] = int(raw.StockCode.nunique())
q["sheets"] = {str(k): int(v) for k, v in raw.source_sheet.value_counts().items()}
q["date_min"], q["date_max"] = str(raw.InvoiceDate.min()), str(raw.InvoiceDate.max())
q["cancel_rows"] = int(raw.InvoiceStr.str.startswith("C").sum())
q["neg_qty_rows"] = int((raw.Quantity < 0).sum())
q["zero_price_rows"] = int((raw.Price <= 0).sum())
q["missing_cust_rows"] = int(raw.CustomerID.isna().sum())
q["missing_cust_pct"] = round(raw.CustomerID.isna().mean() * 100, 2)
q["nonprod_rows_raw"] = int(raw.StockCode.astype(str).isin(NONPROD).sum())
q["nonprod_codes"] = len(NONPROD)
q["dup_rows"] = int(len(sid) - len(sid_d))
q["dup_invoices"] = int(sid.Invoice.nunique() - sid_d.Invoice.nunique())
q["max_qty"] = int(raw.Quantity.max())
q["max_price"] = float(raw.Price.max())
q["clean_rows"] = len(clean)
q["clean_orders"] = int(clean.Invoice.nunique())
q["clean_customers"] = int(clean.CustomerID.nunique())
q["clean_gmv"] = round(clean.Revenue.sum(), 2)
# 两 sheet 重叠窗口
ov = raw[(raw.InvoiceDate >= "2010-12-01") & (raw.InvoiceDate <= "2010-12-09 23:59:59")]
q["overlap_rows_by_sheet"] = {str(k): int(v) for k, v in ov.source_sheet.value_counts().items()}
key = ["Invoice", "StockCode", "Quantity", "InvoiceDate", "Price", "CustomerID", "Country"]
s1 = raw[raw.source_sheet == "Year 2009-2010"][key].drop_duplicates()
s2 = raw[raw.source_sheet == "Year 2010-2011"][key].drop_duplicates()
merged = s2.merge(s1, on=key, how="inner")
q["cross_sheet_dup_rows"] = int(len(merged))
q["cross_sheet_dup_invoices"] = int(merged.Invoice.nunique())
res["quality"] = q

with open(OUT + r"\gap_numbers.json", "w", encoding="utf8") as f:
    json.dump(res, f, ensure_ascii=False, indent=1, default=str)
print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
