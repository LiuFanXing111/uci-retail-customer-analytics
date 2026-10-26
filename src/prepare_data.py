"""把两个年度的 Excel 工作表合并成一个中间缓存。

原始 xlsx 有 45MB，直接反复 pd.read_excel 每次要 40 秒以上，所以先落一份
pickle 缓存，后续所有复核脚本读缓存即可。

用法：
    python src/prepare_data.py
    # 数据不在默认位置时：
    UCI_DATA=/path/to/online_retail_II.xlsx python src/prepare_data.py
"""
import os
import time

import pandas as pd

from paths import RAW_XLSX, RAW_PKL, ensure_dirs


def main():
    ensure_dirs()
    if not os.path.exists(RAW_XLSX):
        raise SystemExit(
            '找不到数据文件：%s\n数据获取方式见 data/README.md' % RAW_XLSX)

    t0 = time.time()
    sheets = pd.read_excel(RAW_XLSX, sheet_name=None, engine='openpyxl')
    print('read done %.1fs' % (time.time() - t0), flush=True)

    frames = []
    for name, part in sheets.items():
        part = part.copy()
        part['source_sheet'] = name
        frames.append(part)
        print('--- %s %s' % (name, part.shape))

    df = pd.concat(frames, ignore_index=True)
    print('total rows %d' % len(df))

    df.to_pickle(RAW_PKL)
    print('saved %s  %.1fs' % (RAW_PKL, time.time() - t0))


if __name__ == '__main__':
    main()
