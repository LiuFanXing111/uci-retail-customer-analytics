# -*- coding: utf-8 -*-
"""定位 34,337 这个重复行数是怎么算出来的"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from paths import (PROJ_ROOT, DATA_DIR, CACHE_DIR, OUT_DIR, FIG_DIR,
                   RAW_XLSX, RAW_PKL, ensure_dirs)
ensure_dirs()
import pandas as pd, numpy as np
OUT = CACHE_DIR
raw = pd.read_pickle(RAW_PKL).rename(columns={"Customer ID": "CustomerID"})
raw["InvoiceStr"] = raw["Invoice"].astype(str)

print("sheets:", raw.source_sheet.value_counts().to_dict())
s1 = raw[raw.source_sheet == "Year 2009-2010"]
s2 = raw[raw.source_sheet == "Year 2010-2011"]

# 重叠窗口
w1 = s1[(s1.InvoiceDate >= "2010-12-01") & (s1.InvoiceDate <= "2010-12-09 23:59:59")]
w2 = s2[(s2.InvoiceDate >= "2010-12-01") & (s2.InvoiceDate <= "2010-12-09 23:59:59")]
print("window rows s1/s2:", len(w1), len(w2))

both_inv = set(w1.Invoice) & set(w2.Invoice)
print("invoices in both:", len(both_inv))
print("rows of those invoices in s1:", int(w1.Invoice.isin(both_inv).sum()),
      "| in s2:", int(w2.Invoice.isin(both_inv).sum()))
print("sum both:", int(w1.Invoice.isin(both_inv).sum() + w2.Invoice.isin(both_inv).sum()))

# 全表（不只窗口）按发票看重复
inv1, inv2 = set(s1.Invoice), set(s2.Invoice)
both_all = inv1 & inv2
print("all-sheet invoices in both:", len(both_all))
print("rows s1:", int(s1.Invoice.isin(both_all).sum()), "rows s2:", int(s2.Invoice.isin(both_all).sum()),
      "sum:", int(s1.Invoice.isin(both_all).sum() + s2.Invoice.isin(both_all).sum()))

# 整行（全列）重复
k = ["Invoice", "StockCode", "Description", "Quantity", "InvoiceDate", "Price", "CustomerID", "Country"]
m = s2[k].merge(s1[k], on=k, how="inner")
print("full-column cross-sheet dup rows:", len(m), "invoices:", m.Invoice.nunique())

# 只按 Invoice+StockCode+Quantity+Price
k2 = ["Invoice", "StockCode", "Quantity", "Price"]
m2 = s2[k2].drop_duplicates().merge(s1[k2].drop_duplicates(), on=k2, how="inner")
print("key4 cross-sheet dup rows:", len(m2))

# raw 整体 drop_duplicates 后的重复行数
print("raw duplicated rows (all cols):", int(raw.duplicated().sum()))
k3 = ["Invoice", "StockCode", "Quantity", "InvoiceDate", "Price", "CustomerID", "Country"]
print("raw duplicated rows (subset7):", int(raw.duplicated(subset=k3).sum()))
print("raw duplicated rows (subset7, keep=False):", int(raw.duplicated(subset=k3, keep=False).sum()))
