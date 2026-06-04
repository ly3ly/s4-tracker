#!/usr/bin/env python3
"""
QQQM 实盘买入点标注图表
- 策略: S2/S3/S4/S5（30天冷却期）
- 在价格曲线上标注：月末定投点、补仓触发点
"""
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter
import json, os, warnings
warnings.filterwarnings('ignore')

# ============ 配置 ============
BASE = '/Users/xulongyu/WorkBuddy/20260522091958'
CSV = f'{BASE}/qqqm_daily_prices_2021_2025.csv'
OUT_DIR = f'{BASE}/docs'
COOLDOWN = 30
AMT = 3000
RATE = 7.8
THRESHOLD = 0.05

STRATEGIES_TO_PLOT = ['S2', 'S3', 'S4', 'S5']

STRATEGY_LABELS = {
    'S2': 'Last Buy Price Drawdown',
    'S3': 'ATH Drawdown',
    'S4': 'Uptrend Peak Drawdown',
    'S5': 'Dual Condition',
}

COLORS = {
    'S2': '#FF6384',
    'S3': '#FFCE56',
    'S4': '#4BC0C0',
    'S5': '#9966FF',
}

def load_data():
    """从 yfinance 下载 QQQM 日线 OHLCV 数据"""
    import yfinance as yf
    print("  从 yfinance 下载 QQQM 数据...")
    t = yf.Ticker('QQQM')
    df = t.history(start='2021-01-01', end='2025-12-31')
    df = df[['Open','High','Low','Close']].copy()
    df.dropna(inplace=True)
    # 也保存一份 CSV 给后续复用
    df.to_csv(CSV.replace('.csv', '_ohlc.csv'))
    print(f"  获取 {len(df)} 条, {df.index[0].strftime('%Y-%m-%d')} ~ {df.index[-1].strftime('%Y-%m-%d')}")
    return df

def get_month_end(df, date):
    ym = date.strftime('%Y-%m')
    m = df[df.index.strftime('%Y-%m') == ym]
    return m.index[-1] if len(m) > 0 else None

def run_strategy(df, strategy):
    """运行单个策略，返回所有买入点"""
    cd = COOLDOWN
    th = THRESHOLD
    amt = AMT
    rate = RATE

    shares = 0.0
    total_inv = 0.0
    last_buy_price = None
    last_regular_price = None
    last_extra_date = None
    last_peak = None
    in_uptrend = False

    regular_buys = []   # (date, price, amount_hkd)
    extra_buys = []     # (date, price, amount_hkd, reason)
    daily_values = []

    ath = df['High'].cummax()

    for idx, row in df.iterrows():
        d = idx; p = row['Close']; h = row['High']
        inv_today = 0.0; is_regular = False

        # === 月末定投 ===
        if d == get_month_end(df, d):
            inv_today += amt
            is_regular = True
            last_buy_price = p
            last_regular_price = p
            regular_buys.append((d, p, amt))

        # === 各策略补仓 ===
        if strategy == 'S2':
            if last_buy_price is not None:
                dd = (last_buy_price - p) / last_buy_price
                if dd >= th:
                    can = (last_extra_date is None or (d - last_extra_date).days >= cd)
                    if can and not is_regular:
                        inv_today += amt
                        extra_buys.append((d, p, amt, f'S2: 回撤 {dd*100:.1f}%'))
                        last_buy_price = p
                        last_extra_date = d

        elif strategy == 'S3':
            cur_ath = ath.loc[idx]
            dd_ath = (cur_ath - p) / cur_ath
            if dd_ath >= th:
                can = (last_extra_date is None or (d - last_extra_date).days >= cd)
                if can and not is_regular:
                    inv_today += amt
                    extra_buys.append((d, p, amt, f'S3: ATH回撤 {dd_ath*100:.1f}%'))
                    last_extra_date = d
                    last_buy_price = p

        elif strategy == 'S4':
            if is_regular:
                in_uptrend = True
                last_peak = h
            if in_uptrend and h > last_peak:
                last_peak = h
            prev_idx = df.index.get_loc(idx)
            if prev_idx > 0 and in_uptrend:
                if p < df.iloc[prev_idx - 1]['Close']:
                    dd = (last_peak - p) / last_peak if last_peak else 0
                    if dd >= th:
                        can = (last_extra_date is None or (d - last_extra_date).days >= cd)
                        if can and not is_regular:
                            inv_today += amt
                            extra_buys.append((d, p, amt, f'S4: 周期高点回撤 {dd*100:.1f}%'))
                            last_peak = p
                            last_extra_date = d
                            in_uptrend = False

        elif strategy == 'S5':
            cond_ath = False; cond_buy = False
            cur_ath = ath.loc[idx]
            dd_ath = (cur_ath - p) / cur_ath
            if dd_ath >= th:
                cond_ath = True
            if last_regular_price is not None:
                dd_reg = (last_regular_price - p) / last_regular_price
                if dd_reg >= th:
                    cond_buy = True
            if cond_ath or cond_buy:
                can = (last_extra_date is None or (d - last_extra_date).days >= cd)
                if can and not is_regular:
                    inv_today += amt
                    if cond_ath and cond_buy:
                        tag = f'S5: 双条件 (ATH{dd_ath*100:.1f}% + 定投{dd_reg*100:.1f}%)'
                    elif cond_ath:
                        tag = f'S5: ATH回撤 {dd_ath*100:.1f}%'
                    else:
                        tag = f'S5: 定投价回撤 {dd_reg*100:.1f}%'
                    extra_buys.append((d, p, amt, tag))
                    last_extra_date = d
                    last_buy_price = p

        if inv_today > 0:
            usd = inv_today / rate
            shares += usd / p
            total_inv += inv_today

        pv = shares * p * rate
        daily_values.append((d, p, pv, total_inv))

    rdf = pd.DataFrame(daily_values, columns=['Date','Close','PortfolioValue','TotalInvested'])
    rdf.set_index('Date', inplace=True)
    rdf['ReturnPct'] = (rdf['PortfolioValue'] - rdf['TotalInvested']) / rdf['TotalInvested'] * 100
    running_max = rdf['PortfolioValue'].cummax()
    rdf['Drawdown'] = (rdf['PortfolioValue'] - running_max) / running_max * 100

    return {
        'strategy': strategy,
        'cooldown': COOLDOWN,
        'total_invested': round(total_inv, 2),
        'final_value': round(rdf['PortfolioValue'].iloc[-1], 2),
        'return_pct': round(rdf['ReturnPct'].iloc[-1], 2),
        'max_drawdown': round(rdf['Drawdown'].min(), 2),
        'regular_count': len(regular_buys),
        'extra_count': len(extra_buys),
        'regular_buys': [{'date': d.strftime('%Y-%m-%d'), 'price': round(p, 2), 'amount_hkd': a}
                         for d, p, a in regular_buys],
        'extra_buys': [{'date': d.strftime('%Y-%m-%d'), 'price': round(p, 2), 'amount_hkd': a, 'reason': r}
                       for d, p, a, r in extra_buys],
    }

# ============ 图表生成 ============

def plot_strategy_buypoints(df, result, out_path):
    """为单个策略生成买入点标注图"""
    s = result['strategy']
    label = STRATEGY_LABELS[s]
    color = COLORS[s]

    regular_dates = [pd.Timestamp(b['date']) for b in result['regular_buys']]
    regular_prices = [b['price'] for b in result['regular_buys']]
    extra_dates = [pd.Timestamp(b['date']) for b in result['extra_buys']]
    extra_prices = [b['price'] for b in result['extra_buys']]

    fig, ax = plt.subplots(figsize=(20, 8))

    # QQQM 价格线
    ax.plot(df.index, df['Close'], color='#1a1a2e', linewidth=1.0, alpha=0.7, zorder=1)

    # 日线参考（浅灰）
    ax.fill_between(df.index, df['Low'], df['High'], alpha=0.08, color='#1a1a2e')

    # 定投点（月末）
    ax.scatter(regular_dates, regular_prices, c=color, s=50, marker='o',
               edgecolors='white', linewidths=0.5, zorder=3, label=f'Monthly DCA ({len(regular_dates)})')

    # 补仓点
    if extra_dates:
        ax.scatter(extra_dates, extra_prices, c=color, s=90, marker='v',
                   edgecolors='white', linewidths=1.0, zorder=4, label=f'Extra Buy ({len(extra_dates)})')

    # 为补仓点添加竖线标记
    for ed, ep in zip(extra_dates, extra_prices):
        ax.axvline(x=ed, color=color, alpha=0.15, linewidth=0.8, zorder=0)

    # 格式
    ax.set_title(f'QQQM {s}: {label} — Buy Points ({COOLDOWN}d Cooldown)',
                 fontsize=16, fontweight='bold', pad=15)
    ax.set_ylabel('Price (USD)', fontsize=12)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f'${x:.0f}'))

    # 信息框
    info = (f"Return: {result['return_pct']:+.2f}%  |  MaxDD: {result['max_drawdown']:+.2f}%  |  "
            f"Invested: {result['total_invested']:,.0f} HKD  |  "
            f"Final: {result['final_value']:,.0f} HKD  |  "
            f"Extra: {result['extra_count']} times")
    ax.text(0.5, -0.12, info, transform=ax.transAxes, ha='center', fontsize=10,
            bbox=dict(boxstyle='round,pad=0.4', facecolor='#f5f5f5', edgecolor='#ccc', alpha=0.9))

    ax.legend(loc='upper left', fontsize=11, markerscale=1.2)
    ax.grid(True, alpha=0.25)
    ax.set_xlim(df.index[0], df.index[-1])

    plt.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f"  ✅ {out_path}")

def plot_combined_buypoints(df, all_results, out_path):
    """四策略叠加对比图（共用价格线，四色标注）"""
    fig, axes = plt.subplots(4, 1, figsize=(22, 28), sharex=True)

    for i, result in enumerate(all_results):
        ax = axes[i]
        s = result['strategy']
        label = STRATEGY_LABELS[s]
        color = COLORS[s]

        regular_dates = [pd.Timestamp(b['date']) for b in result['regular_buys']]
        regular_prices = [b['price'] for b in result['regular_buys']]
        extra_dates = [pd.Timestamp(b['date']) for b in result['extra_buys']]
        extra_prices = [b['price'] for b in result['extra_buys']]

        # 价格线
        ax.plot(df.index, df['Close'], color='#333', linewidth=1.0, alpha=0.5, zorder=1)
        ax.fill_between(df.index, df['Low'], df['High'], alpha=0.05, color='#333')

        # 定投点
        ax.scatter(regular_dates, regular_prices, c=color, s=35, marker='o',
                   edgecolors='white', linewidths=0.3, zorder=3, label=f'DCA ({len(regular_dates)})')

        # 补仓点
        if extra_dates:
            ax.scatter(extra_dates, extra_prices, c=color, s=70, marker='v',
                       edgecolors='white', linewidths=0.8, zorder=4, label=f'Extra ({len(extra_dates)})')
            for ed in extra_dates:
                ax.axvline(x=ed, color=color, alpha=0.12, linewidth=0.6, zorder=0)

        # 副标题
        info = (f"Return: {result['return_pct']:+.2f}%  |  MaxDD: {result['max_drawdown']:+.2f}%  |  "
                f"Inv: {result['total_invested']:,.0f} HKD  |  Extra: {result['extra_count']}")
        ax.set_title(f'{s}: {label}  —  {info}', fontsize=13, fontweight='bold', color=color, pad=10)
        ax.set_ylabel('Price (USD)', fontsize=10)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f'${x:.0f}'))
        ax.legend(loc='upper left', fontsize=9, markerscale=1.0)
        ax.grid(True, alpha=0.2)

    axes[-1].xaxis.set_major_locator(mdates.YearLocator())
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    axes[-1].set_xlim(df.index[0], df.index[-1])

    fig.suptitle(f'QQQM Buy Points — All Strategies ({COOLDOWN}d Cooldown)', fontsize=18, fontweight='bold', y=0.995)
    plt.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f"  ✅ {out_path}")

def plot_s4_zoomed(df, result, out_path):
    """S4 实盘策略放大图（加注关键补仓点日期和原因）"""
    s = result['strategy']
    color = COLORS[s]

    regular_dates = [pd.Timestamp(b['date']) for b in result['regular_buys']]
    regular_prices = [b['price'] for b in result['regular_buys']]
    extra_dates = [pd.Timestamp(b['date']) for b in result['extra_buys']]
    extra_prices = [b['price'] for b in result['extra_buys']]

    fig, ax = plt.subplots(figsize=(24, 10))

    # 背景价格线
    ax.plot(df.index, df['Close'], color='#1a1a2e', linewidth=1.2, alpha=0.6, zorder=1)
    ax.fill_between(df.index, df['Low'], df['High'], alpha=0.06, color='#1a1a2e')

    # 定投
    ax.scatter(regular_dates, regular_prices, c=color, s=60, marker='o',
               edgecolors='white', linewidths=0.5, zorder=3, label=f'Monthly DCA × {len(regular_dates)}')

    # 补仓 —— 大号 + 日期标注
    if extra_dates:
        ax.scatter(extra_dates, extra_prices, c=color, s=120, marker='v',
                   edgecolors='white', linewidths=1.5, zorder=4,
                   label=f'Extra Buy × {len(extra_dates)}')

        # 日期 + 原因标注（避免重叠，交替偏移）
        for j, (ed, ep, eb) in enumerate(zip(extra_dates, extra_prices, result['extra_buys'])):
            offset_y = 12 if j % 2 == 0 else -15
            ha = 'left' if j % 3 != 2 else 'right'
            ax.annotate(
                f"{ed.strftime('%Y-%m-%d')}\n${ep:.0f}",
                xy=(ed, ep),
                xytext=(0, offset_y),
                textcoords='offset points',
                fontsize=7, color=color, fontweight='bold',
                ha=ha, alpha=0.85,
                arrowprops=dict(arrowstyle='->', color=color, alpha=0.4, lw=0.8)
            )

    # 信息框
    info = (f"S4 30d Cooldown | Return: {result['return_pct']:+.2f}% | MaxDD: {result['max_drawdown']:+.2f}% | "
            f"Invested: {result['total_invested']:,.0f} HKD | Final: {result['final_value']:,.0f} HKD | "
            f"Extra: {result['extra_count']}")
    ax.set_title(f'QQQM S4 (Current Strategy): Monthly DCA + Extra Buy Points', fontsize=16, fontweight='bold', pad=15)
    ax.text(0.5, -0.10, info, transform=ax.transAxes, ha='center', fontsize=10,
            bbox=dict(boxstyle='round,pad=0.4', facecolor='#fefefe', edgecolor='#ccc', alpha=0.9))
    ax.set_ylabel('Price (USD)', fontsize=12)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right', fontsize=8)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f'${x:.0f}'))
    ax.legend(loc='upper left', fontsize=11, markerscale=1.3)
    ax.grid(True, alpha=0.2)
    ax.set_xlim(df.index[0], df.index[-1])

    plt.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f"  ✅ {out_path}")

# ============ 主流程 ============

def main():
    print("=" * 60)
    print("QQQM 买入点标注图表生成")
    print("=" * 60)

    # 1. 加载数据
    print("\n[1/4] 加载价格数据...")
    df = load_data()

    # 2. 运行策略（仅30天冷却期）
    print(f"\n[2/4] 运行策略（冷却期={COOLDOWN}天）...")
    all_results = []
    for s in STRATEGIES_TO_PLOT:
        print(f"  {s}...", end=' ')
        r = run_strategy(df.copy(), s)
        all_results.append(r)
        print(f"收益={r['return_pct']:+.2f}% 定投={r['regular_count']} 补仓={r['extra_count']}")

    # 3. 保存交易详情 JSON
    print("\n[3/4] 保存交易详情...")
    json_path = f'{BASE}/qqqm_trade_details.json'
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"  ✅ {json_path}")

    # 4. 生成图表
    print(f"\n[4/4] 生成图表到 {OUT_DIR}/...")
    os.makedirs(OUT_DIR, exist_ok=True)

    # 单个策略图（各一张）
    for result in all_results:
        s = result['strategy']
        plot_strategy_buypoints(df, result, f'{OUT_DIR}/qqqm_buy_{s.lower()}.png')

    # 四合一对比
    plot_combined_buypoints(df, all_results, f'{OUT_DIR}/qqqm_buy_all.png')

    # S4 实盘放大图
    s4_result = next(r for r in all_results if r['strategy'] == 'S4')
    plot_s4_zoomed(df, s4_result, f'{OUT_DIR}/qqqm_buy_s4_detail.png')

    print(f"\n✅ 全部完成！共生成 {len(STRATEGIES_TO_PLOT) + 2} 张图表")

if __name__ == '__main__':
    main()
