#!/usr/bin/env python3
"""
QQQM 全策略 × 全冷却期 综合回测
- 标的: QQQM (2021-01 至今)
- 策略: S1 ~ S5
- 冷却期: 0, 7, 14, 30 天
- 修复: S5 使用 last_regular_price（上次定投价），非 last_buy_price
"""

import yfinance as yf
import pandas as pd
import numpy as np
import json, warnings
warnings.filterwarnings('ignore')

COOLDOWNS = [0, 7, 14, 30]
STRATEGIES = ['S1', 'S2', 'S3', 'S4', 'S5']
CONFIG = {
    'symbol': 'QQQM',
    'start_date': '2021-01-01',
    'end_date': '2025-12-31',
    'monthly_invest': 3000,
    'currency_rate': 7.8,
    'drawdown_threshold': 5.0,
}

STRATEGY_LABELS = {
    'S1': '纯月度定投',
    'S2': '上次买入价回撤',
    'S3': 'ATH回撤',
    'S4': '上涨周期高点回撤',
    'S5': '双条件（ATH或定投价回撤）',
}

def fetch_data():
    print(f"下载 {CONFIG['symbol']} {CONFIG['start_date']}~{CONFIG['end_date']}...")
    t = yf.Ticker(CONFIG['symbol'])
    df = t.history(start=CONFIG['start_date'], end=CONFIG['end_date'])
    df = df[['Open','High','Low','Close','Volume']].copy()
    df.dropna(inplace=True)
    print(f"  {len(df)} 条, {df.index[0].strftime('%Y-%m-%d')} ~ {df.index[-1].strftime('%Y-%m-%d')}")
    return df

def get_month_end(df, date):
    ym = date.strftime('%Y-%m')
    m = df[df.index.strftime('%Y-%m') == ym]
    return m.index[-1] if len(m) > 0 else None

def run_strategy(df, strategy, cooldown):
    """返回 dict: {strategy, cooldown, total_inv, final_val, ret_pct, max_dd, 
                    regular_count, extra_count, extra_buys}"""
    cd = cooldown
    th = CONFIG['drawdown_threshold'] / 100
    amt = CONFIG['monthly_invest']
    rate = CONFIG['currency_rate']

    shares = 0.0
    total_inv = 0.0
    last_buy_price = None       # S2 用
    last_regular_price = None   # S5 用: 仅月末定投价
    last_extra_date = None
    last_peak = None            # S4
    in_uptrend = False          # S4

    regular_buys = []
    extra_buys = []
    daily_values = []

    ath = df['High'].cummax()

    for idx, row in df.iterrows():
        d = idx; p = row['Close']; h = row['High']
        inv_today = 0.0; is_regular = False

        # === 月末定投（所有策略共用）===
        if d == get_month_end(df, d):
            inv_today += amt
            is_regular = True
            last_buy_price = p
            last_regular_price = p      # ⭐ S5 独立追踪
            regular_buys.append((d, p, amt))

        # ===== 各策略补仓 =====
        if strategy == 'S2':
            if last_buy_price is not None:
                dd = (last_buy_price - p) / last_buy_price
                if dd >= th:
                    can = (last_extra_date is None or (d - last_extra_date).days >= cd)
                    if can and not is_regular:
                        inv_today += amt
                        extra_buys.append((d, p, amt, f'S2_回撤{dd*100:.1f}%'))
                        last_buy_price = p
                        last_extra_date = d

        elif strategy == 'S3':
            cur_ath = ath.loc[idx]
            dd_ath = (cur_ath - p) / cur_ath
            if dd_ath >= th:
                can = (last_extra_date is None or (d - last_extra_date).days >= cd)
                if can and not is_regular:
                    inv_today += amt
                    extra_buys.append((d, p, amt, f'S3_ATH回撤{dd_ath*100:.1f}%'))
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
                            extra_buys.append((d, p, amt, f'S4_周期高点回撤{dd*100:.1f}%'))
                            last_peak = p
                            last_extra_date = d
                            in_uptrend = False

        elif strategy == 'S5':
            # ⭐ 修复: cond_buy 用 last_regular_price（上次月末定投价）
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
                        tag = f'S5_双条件(ATH{dd_ath*100:.1f}%_定投{dd_reg*100:.1f}%)'
                    elif cond_ath:
                        tag = f'S5_ATH回撤{dd_ath*100:.1f}%'
                    else:
                        tag = f'S5_定投价回撤{dd_reg*100:.1f}%'
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
    max_dd = rdf['Drawdown'].min()

    return {
        'strategy': strategy,
        'cooldown': cooldown,
        'total_invested': round(total_inv, 2),
        'final_value': round(rdf['PortfolioValue'].iloc[-1], 2),
        'return_pct': round(rdf['ReturnPct'].iloc[-1], 2),
        'max_drawdown': round(max_dd, 2),
        'regular_count': len(regular_buys),
        'extra_count': len(extra_buys),
        'extra_buys': extra_buys,
    }

def main():
    base = '/Users/xulongyu/WorkBuddy/20260522091958'
    df = fetch_data()
    data_range = f"{df.index[0].strftime('%Y-%m-%d')} ~ {df.index[-1].strftime('%Y-%m-%d')}"
    n_days = len(df)
    n_months = len(set(df.index.strftime('%Y-%m')))

    # ======== 运行全部组合 ========
    all_results = []
    total = len(STRATEGIES) * len(COOLDOWNS)
    i = 0
    for s in STRATEGIES:
        for cd in COOLDOWNS:
            i += 1
            r = run_strategy(df.copy(), s, cd)
            all_results.append(r)
            print(f"  [{i}/{total}] {s}-{cd}d: 收益={r['return_pct']:.2f}% "
                  f"maxDD={r['max_drawdown']:.2f}% "
                  f"定投{r['regular_count']}/补仓{r['extra_count']} "
                  f"投入={r['total_invested']:,.0f} 终值={r['final_value']:,.0f}")

    # ======== 生成 Markdown 报告 ========
    lines = [
        '# QQQM 全策略 × 全冷却期 综合回测报告\n',
        f'**标的**: QQQM (Invesco NASDAQ 100 ETF)',
        f'**回测区间**: {data_range}（{n_months} 个月，{n_days} 个交易日）',
        f'**每月定投**: {CONFIG["monthly_invest"]:,} HKD | **补仓金额**: {CONFIG["monthly_invest"]:,} HKD',
        f'**回撤阈值**: {CONFIG["drawdown_threshold"]}% | **汇率**: USD/HKD = {CONFIG["currency_rate"]}\n',
        '',
        '---\n',
        '## 策略说明\n',
        '| 策略 | 补仓触发条件 |',
        '|------|-------------|',
    ]
    for s in STRATEGIES:
        lines.append(f'| **{s}** | {STRATEGY_LABELS[s]} |')
    
    lines.extend(['', '---\n', '## 全矩阵对比（收益率 %）\n'])
    lines.append('| 策略 | 0天冷却 | 7天冷却 | 14天冷却 | 30天冷却 |')
    lines.append('|------|---------|---------|----------|----------|')
    for s in STRATEGIES:
        vals = []
        for cd in COOLDOWNS:
            r = next(x for x in all_results if x['strategy']==s and x['cooldown']==cd)
            vals.append(f"{r['return_pct']:.2f}")
        lines.append(f"| **{s}** {STRATEGY_LABELS[s]} | {vals[0]} | {vals[1]} | {vals[2]} | {vals[3]} |")

    lines.extend(['', '## 全矩阵对比（最大回撤 %）\n'])
    lines.append('| 策略 | 0天冷却 | 7天冷却 | 14天冷却 | 30天冷却 |')
    lines.append('|------|---------|---------|----------|----------|')
    for s in STRATEGIES:
        vals = []
        for cd in COOLDOWNS:
            r = next(x for x in all_results if x['strategy']==s and x['cooldown']==cd)
            vals.append(f"{r['max_drawdown']:.2f}")
        lines.append(f"| **{s}** {STRATEGY_LABELS[s]} | {vals[0]} | {vals[1]} | {vals[2]} | {vals[3]} |")

    lines.extend(['', '## 全矩阵对比（总投入 HKD）\n'])
    lines.append('| 策略 | 0天冷却 | 7天冷却 | 14天冷却 | 30天冷却 |')
    lines.append('|------|---------|---------|----------|----------|')
    for s in STRATEGIES:
        vals = []
        for cd in COOLDOWNS:
            r = next(x for x in all_results if x['strategy']==s and x['cooldown']==cd)
            vals.append(f"{r['total_invested']:,.0f}")
        lines.append(f"| **{s}** {STRATEGY_LABELS[s]} | {vals[0]} | {vals[1]} | {vals[2]} | {vals[3]} |")

    lines.extend(['', '## 全矩阵对比（补仓次数）\n'])
    lines.append('| 策略 | 0天冷却 | 7天冷却 | 14天冷却 | 30天冷却 |')
    lines.append('|------|---------|---------|----------|----------|')
    for s in STRATEGIES:
        vals = []
        for cd in COOLDOWNS:
            r = next(x for x in all_results if x['strategy']==s and x['cooldown']==cd)
            vals.append(str(r['extra_count']))
        # S1 always 0
        lines.append(f"| **{s}** {STRATEGY_LABELS[s]} | {vals[0]} | {vals[1]} | {vals[2]} | {vals[3]} |")

    # ======== 关键结论 ========
    lines.extend(['', '---\n', '## 关键发现\n'])

    # 30天最佳策略（实盘配置）
    r30 = [x for x in all_results if x['cooldown']==30]
    best30 = max(r30, key=lambda x: x['return_pct'])
    best30_dd = max(r30, key=lambda x: x['max_drawdown'])  # 负数中越大越好（-18 > -20）
    lines.append(f'### 30天冷却期（当前实盘）')
    lines.append(f'- **收益率最高**: {best30["strategy"]} ({best30["return_pct"]:.2f}%)')
    lines.append(f'- **回撤最低**: {best30_dd["strategy"]} ({best30_dd["max_drawdown"]:.2f}%)')

    # 全局最优
    best_all = max(all_results, key=lambda x: x['return_pct'])
    lines.append(f'\n### 全局最优')
    lines.append(f'- **收益率最高**: {best_all["strategy"]}-{best_all["cooldown"]}天 ({best_all["return_pct"]:.2f}%)')
    lines.append(f'- 配置: 投入 {best_all["total_invested"]:,.0f} HKD, 终值 {best_all["final_value"]:,.0f} HKD')

    # S3 vs S5 差异检查
    s3_30 = next(x for x in all_results if x['strategy']=='S3' and x['cooldown']==30)
    s5_30 = next(x for x in all_results if x['strategy']=='S5' and x['cooldown']==30)
    if abs(s3_30['return_pct'] - s5_30['return_pct']) < 0.01:
        lines.append(f'\n⚠️ **S3 与 S5 数据仍然接近**: 收益率差 {abs(s3_30["return_pct"]-s5_30["return_pct"]):.2f}%，补仓差 {abs(s3_30["extra_count"]-s5_30["extra_count"])} 次。原因：ATH回撤是主导条件，定投价回撤单独触发的情况极少。')
    else:
        lines.append(f'\n✅ **S3 vs S5 已分化**: S3={s3_30["return_pct"]:.2f}% vs S5={s5_30["return_pct"]:.2f}%')

    # ======== 补仓明细（30天） ========
    lines.extend(['', '---\n', '## 补仓明细（30天冷却期）\n'])
    for s in ['S2','S3','S4','S5']:
        r = next(x for x in all_results if x['strategy']==s and x['cooldown']==30)
        if r['extra_count'] > 0:
            lines.append(f'\n### {s} {STRATEGY_LABELS[s]} — {r["extra_count"]} 次补仓\n')
            lines.append('| 日期 | 价格(USD) | 金额(HKD) | 触发原因 |')
            lines.append('|------|-----------|-----------|----------|')
            for eb in r['extra_buys']:
                d, p, a, reason = eb
                lines.append(f'| {d.strftime("%Y-%m-%d")} | ${p:.2f} | {a:,.0f} | {reason} |')
        else:
            lines.append(f'\n### {s} {STRATEGY_LABELS[s]} — 无补仓\n')

    md_path = f'{base}/qqqm_full_matrix_report.md'
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    # ======== JSON ========
    json_out = {
        'config': {**CONFIG, 'data_range': data_range, 'n_days': n_days, 'n_months': n_months},
        'results': [{k:v for k,v in r.items() if k != 'extra_buys'} for r in all_results],
    }
    jpath = f'{base}/qqqm_full_matrix_report.json'
    with open(jpath, 'w', encoding='utf-8') as f:
        json.dump(json_out, f, indent=2, ensure_ascii=False)

    print(f"\n✅ 报告已保存: {md_path} / {jpath}")

if __name__ == '__main__':
    main()
