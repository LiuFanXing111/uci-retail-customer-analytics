
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from paths import (PROJ_ROOT, DATA_DIR, CACHE_DIR, OUT_DIR, FIG_DIR,
                   RAW_XLSX, RAW_PKL, ensure_dirs)
ensure_dirs()
import pandas as pd, numpy as np

raw = pd.read_pickle(RAW_PKL)
df = raw.rename(columns={"Customer ID": "CustomerID"}).copy()
df["Invoice"] = df["Invoice"].astype(str)
df = df[(df.Quantity > 0) & (df.Price > 0)]
df = df.dropna(subset=["CustomerID"])
df = df.drop_duplicates()
df["CustomerID"] = df["CustomerID"].astype(int)
non_product = df["StockCode"].astype(str).str.upper().str.match(
    r"^(POST|D|C2|M|BANK CHARGES|B|PAD|DOT|AMAZONFEE|S|CRUK|SP1002|GIFT|ADJUST|TEST)"
)
df = df[~non_product]
df["Revenue"] = df.Quantity * df.Price

# per-customer first two distinct invoice dates
inv = df.groupby(["CustomerID", "Invoice"])["InvoiceDate"].min().reset_index()
inv = inv.sort_values(["CustomerID", "InvoiceDate"])
g = inv.groupby("CustomerID")["InvoiceDate"]
first = g.min()
second = inv.groupby("CustomerID")["InvoiceDate"].apply(lambda s: s.sort_values().iloc[1] if len(s) > 1 else pd.NaT)

cust = pd.DataFrame({"first": first, "second": second})
cust["gap"] = (cust["second"] - cust["first"]).dt.total_seconds() / 86400
DATA_END = df.InvoiceDate.max()

# only customers whose first order leaves >=30 days of observation window
obs = (DATA_END - cust["first"]).dt.total_seconds() / 86400
eligible = cust[obs >= 30]
conv30 = (eligible["gap"] <= 30).sum()
print("DATA_END", DATA_END)
print("eligible customers (first order +30d window):", len(eligible))
print("reordered within 30d:", int(conv30), "rate:", round(conv30 / len(eligible) * 100, 2))

# monthly new-customer counts (from earlier work): 300 / 137
for p1, label in [(conv30 / len(eligible), "actual 30d")]:
    for delta in [0.03, 0.05, 0.10]:
        p2 = p1 + delta
        z_a, z_b = 1.959964, 0.8416212
        n = (z_a + z_b) ** 2 * (p1 * (1 - p1) + p2 * (1 - p2)) / delta ** 2
        print(f"baseline {p1:.3f} -> +{delta*100:.0f}pp : n per group = {np.ceil(n):.0f}, total = {np.ceil(n)*2:.0f}")
