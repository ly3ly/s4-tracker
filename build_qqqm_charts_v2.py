#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成 QQQM 回测可视化 PNG 图表
用法: python3 build_qqqm_charts_v2.py
"""

import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np
import os
import pandas as pd

# ============ 中文字体 ============
def get_cn_font():
    candidates = ['PingFang SC', 'Heiti SC', 'STHeiti', 'Arial Unicode MS',
                  'SimHei', 'WenQuanYi Micro Hei', 'sans-serif']
    available = [f.name for f in fm.fontManager.ttflist]
    for c in candidates:
        if c in available:
            return c
    return 'sans-serif'

try:
    CN_FONT = get_cn_font()
    plt.rcParams['font.family'] = CN_FONT
    plt.rcParams['axes.unicode_minus'] = False
    print(f"Using font: {CN_FONT}")
except Exception as e:
    print(f"Font warning: {e}")

# ============ 配置 ============
BASE = '/Users/xulongyu/WorkBuddy/20260522091958'
JSON_FILE = os.path.join(BASE, 'qqqm_full_matrix_report.json')
DAILY_CSV = os.path.join(BASE, 'qqqm_daily_prices_2021_2025.csv')
OUT_DIR = os.path.join(BASE, 'docs')
os.makedirs(OUT_DIR, exist_ok=True)

STRATEGIES = {
    'S1': 'Pure DCA',
    'S2': 'Last Buy Price DD',
    'S3': 'ATH Drawdown',
    'S4': 'Uptrend Peak DD',
    'S5': 'Dual Condition',
}
COLORS = {
    'S1': '#36A2EB',
    'S2': '#FF6384',
    'S3': '#FFCE56',
    'S4': '#4BC0C0',
    'S5': '#9966FF',
}

# ============ 加载数据 ============
with open(JSON_FILE, 'r', encoding='utf-8') as f:
    data = json.load(f)

results = data['results']
config = data['config']
data_range = config.get('data_range', '2021-2025')

print(f"Data loaded: {len(results)} records, range {data_range}")

# ============ 图1: 策略对比（30天冷却期） ============
print("\n[1/4] Generating strategy comparison chart...")

fig, ax = plt.subplots(figsize=(12, 7))

# 按收益率排序
s30 = sorted([r for r in results if r['cooldown'] == 30],
              key=lambda x: -x['return_pct'])

labels = [f"{r['strategy']}\n{STRATEGIES[r['strategy']]}" for r in s30]
returns = [r['return_pct'] for r in s30]

x = np.arange(len(labels))
width = 0.5

bars = ax.bar(x, returns, width, color=[COLORS[r['strategy']] for r in s30], alpha=0.85)
ax.set_ylabel('Return Rate (%)', fontsize=11)
ax.set_title(f'QQQM Strategy Comparison (30d Cooldown, {data_range})',
             fontsize=13, pad=15)
ax.set_xticks(x)
ax.set_xticklabels(labels, fontsize=9)
ax.grid(axis='y', alpha=0.3)
ax.set_ylim(min(returns) - 3, max(returns) + 2)

# 标注数值
for i, (bar, r) in enumerate(zip(bars, s30)):
    h = bar.get_height()
    ax.text(bar.get_x() + bar.get_width()/2., h + 0.2,
            f"{r['return_pct']:.2f}%", ha='center', va='bottom',
            fontsize=9, fontweight='bold' if r['strategy'] == 'S4' else 'normal')

plt.tight_layout()
fig.savefig(os.path.join(OUT_DIR, 'qqqm_strategy_comparison.png'), dpi=150, bbox_inches='tight')
plt.close()
print(f"  -> {OUT_DIR}/qqqm_strategy_comparison.png")

# ============ 图2: S4 冷却期对比 ============
print("\n[2/4] Generating S4 cooldown comparison chart...")

cooldowns = [0, 7, 14, 30]
s4_data = {}
for cd in cooldowns:
    s4_data[cd] = next((r for r in results if r['strategy'] == 'S4' and r['cooldown'] == cd), None)

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

# 左图：收益率
returns_cd = [s4_data[cd]['return_pct'] for cd in cooldowns]
best_cd = 14
cd_colors = [COLORS['S4'] if cd != best_cd else '#22c55e' for cd in cooldowns]

bars1 = ax1.bar([str(cd) for cd in cooldowns], returns_cd,
                  color=cd_colors, alpha=0.8, width=0.6)
ax1.set_ylabel('Return Rate (%)', fontsize=11)
ax1.set_xlabel('Cooldown Period (days)', fontsize=11)
ax1.set_title('S4: Cooldown vs Return', fontsize=12)
ax1.grid(axis='y', alpha=0.3)
ax1.set_ylim(min(returns_cd) - 1, max(returns_cd) + 1)

for bar, cd in zip(bars1, cooldowns):
    h = bar.get_height()
    ax1.text(bar.get_x() + bar.get_width()/2., h + 0.1,
             f"{h:.2f}%", ha='center', va='bottom', fontsize=9,
             fontweight='bold' if cd == best_cd else 'normal')

# 右图：补仓次数
extra_cd = [s4_data[cd]['extra_count'] for cd in cooldowns]
bars2 = ax2.bar([str(cd) for cd in cooldowns], extra_cd,
                  color=cd_colors, alpha=0.8, width=0.6)
ax2.set_ylabel('Extra Buy Count', fontsize=11)
ax2.set_xlabel('Cooldown Period (days)', fontsize=11)
ax2.set_title('S4: Cooldown vs Extra Buys', fontsize=12)
ax2.grid(axis='y', alpha=0.3)

for bar, cd in zip(bars2, cooldowns):
    h = bar.get_height()
    ax2.text(bar.get_x() + bar.get_width()/2., h + 0.3,
             str(int(h)), ha='center', va='bottom', fontsize=9)

fig.suptitle(f'QQQM S4 Cooldown Sensitivity ({data_range})', fontsize=13, y=1.02)
plt.tight_layout()
fig.savefig(os.path.join(OUT_DIR, 'qqqm_cooldown_comparison.png'), dpi=150, bbox_inches='tight')
plt.close()
print(f"  -> {OUT_DIR}/qqqm_cooldown_comparison.png")

# ============ 图3: 全策略冷却期热力图 ============
print("\n[3/4] Generating cooldown heatmap...")

strategy_list = ['S1', 'S2', 'S3', 'S4', 'S5']
cooldown_list = [0, 7, 14, 30]
heat_data = []

for s in strategy_list:
    row = []
    for cd in cooldown_list:
        r = next((r for r in results if r['strategy'] == s and r['cooldown'] == cd), None)
        row.append(r['return_pct'] if r else 0)
    heat_data.append(row)

fig, ax = plt.subplots(figsize=(10, 6))
im = ax.imshow(heat_data, cmap='RdYlGn', aspect='auto', vmin=55, vmax=90)

ax.set_xticks(range(len(cooldown_list)))
ax.set_xticklabels([f'{cd}d' for cd in cooldown_list])
ax.set_yticks(range(len(strategy_list)))
ax.set_yticklabels([f"{s}: {STRATEGIES[s]}" for s in strategy_list])
ax.set_title('QQQM: Strategy x Cooldown Return Heatmap (%)', fontsize=13, pad=15)
ax.set_xlabel('Cooldown Period', fontsize=11)
ax.set_ylabel('Strategy', fontsize=11)

# 标注数值
for i in range(len(strategy_list)):
    for j in range(len(cooldown_list)):
        text_color = 'white' if heat_data[i][j] < 70 else 'black'
        ax.text(j, i, f"{heat_data[i][j]:.2f}%",
                ha='center', va='center', color=text_color, fontsize=9)

plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
plt.tight_layout()
fig.savefig(os.path.join(OUT_DIR, 'qqqm_cooldown_heatmap.png'), dpi=150, bbox_inches='tight')
plt.close()
print(f"  -> {OUT_DIR}/qqqm_cooldown_heatmap.png")

# ============ 图4: 资金曲线（S1 vs S4） ============
print("\n[4/4] Generating value curve chart (S1 vs S4)...")

# 读取日线数据
df_daily = pd.read_csv(DAILY_CSV, index_col=0, parse_dates=True)
prices = df_daily.squeeze()

# 计算每日市值
monthly_invest = 3000
currency_rate = 7.8
drawdown_threshold = 0.05
cooldown_days = 30

def calc_daily_values(strategy):
    shares = 0.0
    total_invested = 0.0
    last_buy_price = None
    last_extra_date = None
    last_peak = None
    in_uptrend = False
    last_regular_price = None
    values = []

    for idx, price in prices.items():
        d = idx.to_pydatetime()
        p = float(price)
        inv = 0.0

        is_regular = ((d + pd.Timedelta(days=1)).month != d.month) or (idx == prices.index[-1])

        if is_regular:
            inv += monthly_invest
            last_buy_price = p
            last_regular_price = p
            if strategy == 'S4':
                in_uptrend = True
                last_peak = p

        if strategy == 'S2':
            if last_buy_price and (last_buy_price - p) / last_buy_price >= drawdown_threshold:
                can = (last_extra_date is None or (d - last_extra_date).days >= cooldown_days)
                if can and not is_regular:
                    inv += monthly_invest
                    last_buy_price = p
                    last_extra_date = d

        elif strategy in ('S3', 'S5'):
            ath = prices.loc[:idx].max()
            dd_ath = (ath - p) / ath if ath > 0 else 0
            cond_ath = dd_ath >= drawdown_threshold
            cond_buy = False
            if last_regular_price:
                cond_buy = (last_regular_price - p) / last_regular_price >= drawdown_threshold
            trig = cond_ath or (strategy == 'S5' and cond_buy)
            if trig:
                can = (last_extra_date is None or (d - last_extra_date).days >= cooldown_days)
                if can and not is_regular:
                    inv += monthly_invest
                    last_buy_price = p
                    last_extra_date = d

        elif strategy == 'S4':
            pi = prices.index.get_loc(idx)
            if is_regular:
                in_uptrend = True
                last_peak = p
            if in_uptrend and pi > 0:
                h_today = p
                if h_today > last_peak:
                    last_peak = h_today
                if p < prices.iloc[pi - 1]:
                    dd = (last_peak - p) / last_peak if last_peak else 0
                    if dd >= drawdown_threshold:
                        can = (last_extra_date is None or (d - last_extra_date).days >= cooldown_days)
                        if can and not is_regular:
                            inv += monthly_invest
                            last_peak = p
                            last_extra_date = d
                            in_uptrend = False

        if inv > 0:
            shares += (inv / currency_rate) / p
            total_invested += inv

        pv = shares * p * currency_rate
        values.append(pv)

    return values

print("  Calculating S1...")
values_s1 = calc_daily_values('S1')
print("  Calculating S4...")
values_s4 = calc_daily_values('S4')

dates = prices.index

fig, ax = plt.subplots(figsize=(14, 7))
ax.plot(dates, values_s1, label='S1: Pure DCA', color=COLORS['S1'], linewidth=2, alpha=0.8)
ax.plot(dates, values_s4, label='S4: Uptrend Peak DD', color=COLORS['S4'], linewidth=2, alpha=0.8)

ax.set_ylabel('Portfolio Value (HKD)', fontsize=11)
ax.set_xlabel('Date', fontsize=11)
ax.set_title(f'QQQM S1 vs S4 Portfolio Value (30d Cooldown)', fontsize=13, pad=15)
ax.legend(fontsize=11)
ax.grid(alpha=0.3)

plt.tight_layout()
fig.savefig(os.path.join(OUT_DIR, 'qqqm_value_curves.png'), dpi=150, bbox_inches='tight')
plt.close()
print(f"  -> {OUT_DIR}/qqqm_value_curves.png")

# ============ 完成 ============
print("\n" + "="*50)
print("ALL CHARTS GENERATED SUCCESSFULLY!")
print("="*50)
print(f"Output directory: {OUT_DIR}/")
print("  - qqqm_strategy_comparison.png  (strategy comparison)")
print("  - qqqm_cooldown_comparison.png (S4 cooldown analysis)")
print("  - qqqm_cooldown_heatmap.png    (strategy x cooldown heatmap)")
print("  - qqqm_value_curves.png        (S1 vs S4 value curves)")
