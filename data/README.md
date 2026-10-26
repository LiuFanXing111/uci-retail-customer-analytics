# 数据说明

仓库**不包含**原始数据文件（45 MB 的 xlsx，不适合进 git 历史）。请按下述方式自行获取后放到本目录。

## 获取方式

数据集：**Online Retail II**，UCI Machine Learning Repository

- 页面：https://archive.ics.uci.edu/dataset/502/online+retail+ii
- DOI：`10.24432/C5CG6D`
- 许可：CC BY 4.0

下载后把 `online_retail_II.xlsx` 放到 `data/` 下即可：

```
data/
└── online_retail_II.xlsx     # 约 45 MB
```

如果数据在别的位置，用环境变量指向它，不必移动文件：

```bash
# Windows PowerShell
$env:UCI_DATA = "E:\datasets\online_retail_II.xlsx"

# macOS / Linux
export UCI_DATA=/path/to/online_retail_II.xlsx
```

## 数据集概况

一家英国注册的在线零售商在 2009-12-01 至 2011-12-09 之间的全部交易流水，主营礼品与家居装饰，客户以批发商为主。

| 项目 | 内容 |
|---|---|
| 记录数 | 1,067,371 行 |
| 工作表 | `Year 2009-2010`、`Year 2010-2011` 两个 |
| 字段 | Invoice、StockCode、Description、Quantity、InvoiceDate、Price、CustomerID、Country |
| 客户数 | 5,878 个有 ID 的客户（去重清洗后 5,861） |
| 国家 | 41 个，英国占绝大部分 |

## 两处需要注意的数据问题

这两点在分析中都已处理，改脚本时别绕过去：

1. **两个工作表在 2010-12-01 至 2010-12-09 有重叠。** 直接 concat 会把这段时间的流水算两遍。清洗时必须按
   `Invoice + StockCode + Quantity + InvoiceDate + Price + CustomerID + Country` 七列去重，涉及 1,088 张发票。
2. **非商品编码混在 StockCode 里。** `POST`（邮费）、`BANK CHARGES`、`AMAZONFEE`、`Manual`、`Discount`、`DOT`、`M`、`S`、`C2` 等不是商品，做营收与商品结构分析前要剔除，否则客单价和 ABC 分级都会失真。

## 中间缓存

`src/prepare_data.py` 会把两个工作表合并后写一份 pickle 到 `data/cache/raw.pkl`（约 59 MB）。这是本地缓存，已被 `.gitignore` 排除。原始 xlsx 每次解析要 40 秒以上，后续脚本读缓存即可。
