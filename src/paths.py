"""项目统一路径。

所有脚本都从这里取目录，避免出现绝对路径。数据放在 <项目根>/data/ 下，
中间缓存放 <项目根>/data/cache/，产物写到 <项目根>/output/。
"""
import os

PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(PROJ_ROOT, 'data')
CACHE_DIR = os.path.join(DATA_DIR, 'cache')
OUT_DIR = os.path.join(PROJ_ROOT, 'output')
FIG_DIR = os.path.join(PROJ_ROOT, 'figures')

# 原始数据文件；可用环境变量 UCI_DATA 指向别处（比如数据放在外置盘）
RAW_XLSX = os.environ.get('UCI_DATA', os.path.join(DATA_DIR, 'online_retail_II.xlsx'))

# prepare_data.py 生成的缓存，供各复核脚本复用，避免重复解析 45MB Excel
RAW_PKL = os.path.join(CACHE_DIR, 'raw.pkl')


def ensure_dirs():
    for d in (DATA_DIR, CACHE_DIR, OUT_DIR, FIG_DIR):
        os.makedirs(d, exist_ok=True)
