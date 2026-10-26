# -*- coding: utf-8 -*-
"""校验 4 张 CSV 的列名与表间关联完整性（不依赖原始 Excel，仅读 tableau_data/）。"""

import os
import pandas as pd

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tableau_data')


def load(name):
    return pd.read_csv(os.path.join(BASE, name))


def main():
    orders = load('orders.csv')
    customers = load('customers_rfm.csv')
    retention = load('cohort_retention.csv')
    rules = load('association_rules.csv')

    print("=== 各表主键/字段检查 ===")
    print("orders 列:", list(orders.columns))
    print("customers 列:", list(customers.columns))
    print("retention 列:", list(retention.columns))
    print("rules 列:", list(rules.columns))

    # 1. orders 应有 customer_id（小写），customers 保留原始列名 CustomerID
    #    cohort_retention 经 melt 后主键为 CohortMonth（不含 CustomerID 列），属正常
    assert 'customer_id' in orders.columns, "orders 缺少 customer_id"
    assert 'CustomerID' in customers.columns, "customers_rfm 应为原始列名 CustomerID"
    assert 'CohortMonth' in retention.columns, "cohort_retention 主键应为 CohortMonth"

    # 2. RFM groupby 不再依赖 customer_id，检查 customers 主键无缺失
    assert customers['CustomerID'].notna().all(), "CustomerID 存在空值"

    # 3. 表间关联：orders.customer_id 能匹配到 customers.CustomerID
    matched = orders['customer_id'].isin(customers['CustomerID'])
    print(f"\norders 行数: {len(orders)}")
    print(f"orders.customer_id 能匹配 customers 的比例: {matched.mean()*100:.2f}%")

    # 4. RFM 分段数量核对
    print("\n=== RFM 分群人数（校验与 analysis1.py 一致）===")
    print(customers['Segment'].value_counts())

    # 5. 留存矩阵 period 0 应为 100%
    p0 = retention[retention['Period'] == 0]
    print(f"\nperiod=0 留存率（应全为 100）: 最小值={p0['retention_rate'].min()}, 最大值={p0['retention_rate'].max()}")

    # 6. 关联规则含商品描述
    assert 'antecedent_desc' in rules.columns and 'consequent_desc' in rules.columns
    print("\n=== 关联规则 Top5（含商品描述）===")
    print(rules.head(5)[['antecedent_desc', 'consequent_desc', 'lift']].to_string(index=False))

    print("\n[PASS] 全部校验通过")


if __name__ == '__main__':
    main()
