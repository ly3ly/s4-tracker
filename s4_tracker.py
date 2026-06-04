#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
S4 策略实时追踪工具
=========================
自动获取 QQQM 收盘价，判断定投/补仓触发条件，输出醒目提醒。

用法:
    # 自动获取今日价格并检查
    python s4_tracker.py

    # 手动输入价格（自动获取失败时）
    python s4_tracker.py --price 450.50

    # 指定日期 + 强制标记为定投日
    python s4_tracker.py --date 2025-05-30 --regular

    # 初始化状态文件（首次使用）
    python s4_tracker.py --init
"""

import json
import os
import sys
import argparse
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

# ============ 配置 ============
STATE_FILE = "/Users/xulongyu/WorkBuddy/20260522091958/s4_state.json"
LOG_FILE   = "/Users/xulongyu/WorkBuddy/20260522091958/s4_alerts.log"

CONFIG = {
    "monthly_invest": 3000,      # HKD
    "extra_invest": 3000,        # HKD
    "drawdown_threshold": 0.05,  # 5%
    "cooldown_days": 30,
    "currency_rate": 7.8,
    "symbol": "QQQM",
}

# ============ 工具函数 ============

def load_state():
    """加载状态文件"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return init_state()

def init_state():
    """初始化状态"""
    return {
        "initialized": False,
        "last_peak": None,           # 前上涨周期高点 (USD)
        "in_uptrend": False,         # 是否在上涨周期
        "last_extra_date": None,     # 上次补仓日期
        "last_regular_date": None,   # 上次定投日期
        "last_close": None,          # 昨日收盘价（用于判断涨跌）
        "total_invested": 0.0,       # 累计投入 HKD
        "total_shares": 0.0,         # 累计持有股数
        "history": [],               # 操作历史
    }

def save_state(state):
    """保存状态文件"""
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, default=str)

def get_qqq_price():
    """
    自动获取 QQQM 最新收盘价。
    返回: {"date": str, "close": float, "high": float, "prev_close": float|None}
    """
    try:
        import yfinance as yf
        ticker = yf.Ticker(CONFIG["symbol"])
        hist = ticker.history(period="10d")
        if hist.empty:
            return None
        # 去除时区信息
        hist.index = hist.index.tz_localize(None)
        latest = hist.iloc[-1]
        prev = hist.iloc[-2] if len(hist) > 1 else None
        return {
            "date": hist.index[-1].strftime("%Y-%m-%d"),
            "close": round(float(latest["Close"]), 4),
            "high": round(float(latest["High"]), 4),
            "prev_close": round(float(prev["Close"]), 4) if prev is not None else None,
        }
    except Exception as e:
        print(f"[WARN] 自动获取价格失败: {e}")
        return None

def is_last_trading_day_of_month(date_str):
    """
    判断是否为月末最后一个交易日。
    简化逻辑：当天是本月最后一天，或下一天不是本月。
    由于我们是收盘后运行，直接用 calendar 判断。
    """
    d = datetime.strptime(date_str, "%Y-%m-%d")
    # 本月最后一天
    if d.month == 12:
        last_day = datetime(d.year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = datetime(d.year, d.month + 1, 1) - timedelta(days=1)
    return d.day == last_day.day

def send_macos_notification(title, message):
    """
    发送 macOS 桌面通知（仅当触发操作时调用）
    """
    try:
        script = f'display notification "{message}" with title "{title}"'
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
    except Exception:
        pass  # 静默失败，不影响主流程

def print_banner(lines):
    """打印醒目标记"""
    print()
    print("=" * 64)
    for line in lines:
        print(f"  {line}")
    print("=" * 64)
    print()

def log_to_file(lines):
    """写入日志文件"""
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write("=" * 64 + "\n")
        for line in lines:
            f.write(f"  {line}\n")
        f.write("=" * 64 + "\n\n")

# ============ 核心策略逻辑 ============

def run_s4_check(price_data, state, date_str, force_regular=False):
    """
    执行 S4 策略检查。

    参数:
        price_data: {"close": float, "high": float, "prev_close": float|None}
        state:      当前状态字典
        date_str:   日期字符串 YYYY-MM-DD
        force_regular: 是否强制标记为定投日

    返回:
        (action_list, messages, updated_state)
        action_list: ["regular"|"extra", ...]  可能同时触发两个
        messages:    人类可读的操作描述列表
    """
    p = price_data["close"]
    h = price_data["high"]
    prev = price_data.get("prev_close")
    if prev is None and state["last_close"] is not None:
        prev = state["last_close"]

    actions = []
    messages = []

    # ---- 首次初始化 ----
    if not state["initialized"]:
        state["last_peak"] = h
        state["in_uptrend"] = True
        state["initialized"] = True
        print(f"[INIT] 首次运行，last_peak=${h:.2f}, in_uptrend=True")

    # ---- 1. 定期定投（每月最后一个交易日）----
    is_regular_day = force_regular or is_last_trading_day_of_month(date_str)

    if is_regular_day:
        # 检查本月是否已投
        already_invested_this_month = False
        if state["last_regular_date"]:
            last_reg = datetime.strptime(state["last_regular_date"], "%Y-%m-%d")
            current = datetime.strptime(date_str, "%Y-%m-%d")
            if last_reg.year == current.year and last_reg.month == current.month:
                already_invested_this_month = True

        if already_invested_this_month:
            print(f"[SKIP] 本月已定投 ({state['last_regular_date']})")
        else:
            actions.append("regular")
            amt = CONFIG["monthly_invest"]
            shares = amt / (p * CONFIG["currency_rate"])
            state["total_invested"] += amt
            state["total_shares"] += shares
            state["last_regular_date"] = date_str
            # 新月份：重置上涨周期
            state["in_uptrend"] = True
            state["last_peak"] = h
            messages.append(
                f"【定投】投入 HKD {amt:,} | 价格 ${p:.2f} | "
                f"买入 {shares:.4f} 股 | 本月周期重置"
            )

    # ---- 2. S4 上涨周期高点回撤检查 ----
    # 更新高点（如果仍在上涨周期）
    if state["in_uptrend"] and (state["last_peak"] is None or h > state["last_peak"]):
        state["last_peak"] = h
        print(f"[PEAK] 更新周期高点 last_peak = ${h:.2f}")

    # 检查下跌
    if prev is not None and state["in_uptrend"]:
        if p < prev:  # 今日下跌（相比昨日收盘）
            dd = (state["last_peak"] - p) / state["last_peak"] if state["last_peak"] else 0
            print(f"[DROP] 今日下跌 ${prev:.2f}→${p:.2f}, 距高点回撤 {dd*100:.2f}%")

            if dd >= CONFIG["drawdown_threshold"]:
                # 检查冷却期
                can_extra = True
                if state["last_extra_date"]:
                    last_extra = datetime.strptime(state["last_extra_date"], "%Y-%m-%d")
                    current = datetime.strptime(date_str, "%Y-%m-%d")
                    days_since = (current - last_extra).days
                    if days_since < CONFIG["cooldown_days"]:
                        can_extra = False
                        print(f"[COOLDOWN] 冷却期中 ({days_since}/{CONFIG['cooldown_days']} 天)，跳过补仓")

                if can_extra:
                    actions.append("extra")
                    amt = CONFIG["extra_invest"]
                    shares = amt / (p * CONFIG["currency_rate"])
                    state["total_invested"] += amt
                    state["total_shares"] += shares
                    state["last_extra_date"] = date_str
                    state["last_peak"] = p        # 刷新为补仓价
                    state["in_uptrend"] = False   # 退出上涨周期
                    messages.append(
                        f"【S4补仓】投入 HKD {amt:,} | 价格 ${p:.2f} | "
                        f"买入 {shares:.4f} 股 | 距高点回撤 {dd*100:.1f}%"
                    )
        else:
            # 上涨或持平，保持 in_uptrend
            state["in_uptrend"] = True
    else:
        # 没有 prev 价格，无法判断涨跌，保守起见保持原状态
        pass

    # 更新 last_close 为今日收盘价（供明天使用）
    state["last_close"] = p

    # 记录历史
    if actions:
        state["history"].append({
            "date": date_str,
            "price_usd": p,
            "actions": actions,
            "messages": messages,
        })

    save_state(state)
    return actions, messages, state

def build_report(date_str, price, actions, messages, state):
    """构建并输出完整报告"""
    p = price
    hkd_price = p * CONFIG["currency_rate"]
    total_val = state["total_shares"] * p * CONFIG["currency_rate"]
    profit = total_val - state["total_invested"]
    ret_pct = (profit / state["total_invested"] * 100) if state["total_invested"] > 0 else 0

    lines = [
        f"📅 日期: {date_str}  |  QQQM 收盘: ${p:.2f}  (≈ HKD {hkd_price:.2f})",
        "-" * 60,
    ]

    if not actions:
        lines.append("✅ 今日无操作")
    else:
        lines.append("🔔 触发操作！")
        for msg in messages:
            lines.append(f"   → {msg}")

    lines.append("-" * 60)
    lines.append(f"📊 策略状态:")
    lines.append(f"   last_peak:    ${state['last_peak']:.2f}")
    lines.append(f"   in_uptrend:   {state['in_uptrend']}")
    if state["last_regular_date"]:
        lines.append(f"   上次定投:     {state['last_regular_date']}")
    if state["last_extra_date"]:
        lines.append(f"   上次补仓:     {state['last_extra_date']}")
    lines.append("-" * 60)
    lines.append(f"💰 总投入:     HKD {state['total_invested']:,.2f}")
    lines.append(f"📈 持仓市值:   HKD {total_val:,.2f}")
    lines.append(f"💵 累计收益:   HKD {profit:,.2f}  ({ret_pct:+.2f}%)")

    print_banner(lines)
    log_to_file(lines)

    # 触发操作时发送 macOS 通知
    if actions:
        title = "S4策略提醒"
        if "extra" in actions:
            title = "🔴 S4策略：触发补仓！"
        elif "regular" in actions:
            title = "🟢 S4策略：定投日"
        summary = "; ".join(messages)
        send_macos_notification(title, summary)

# ============ 主入口 ============

def main():
    parser = argparse.ArgumentParser(
        description="S4 策略实时追踪工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python s4_tracker.py                          # 自动获取今日价格
  python s4_tracker.py --price 450.5            # 手动输入价格
  python s4_tracker.py --date 2025-05-30        # 指定日期
  python s4_tracker.py --regular                # 强制标记为定投日
  python s4_tracker.py --init                   # 初始化状态文件
        """
    )
    parser.add_argument("--price", type=float, help="手动输入 QQQ 收盘价 (USD)")
    parser.add_argument("--date", type=str, help="日期 (YYYY-MM-DD)，默认今天")
    parser.add_argument("--regular", action="store_true", help="强制标记为定投日（月末）")
    parser.add_argument("--init", action="store_true", help="初始化/重置状态文件")
    parser.add_argument("--status", action="store_true", help="仅查看当前状态，不执行检查")
    args = parser.parse_args()

    # 仅查看状态
    if args.status:
        state = load_state()
        print_banner([
            "S4 策略当前状态",
            f"last_peak:    ${state['last_peak']:.2f}" if state["last_peak"] else "last_peak:    未初始化",
            f"in_uptrend:   {state['in_uptrend']}",
            f"上次定投:     {state['last_regular_date'] or '无'}",
            f"上次补仓:     {state['last_extra_date'] or '无'}",
            f"总投入:       HKD {state['total_invested']:,.2f}",
            f"总股数:       {state['total_shares']:.4f}",
        ])
        return

    # 初始化
    if args.init:
        state = init_state()
        save_state(state)
        print(f"✅ 状态文件已初始化: {STATE_FILE}")
        print("   下次运行时将自动开始追踪。")
        return

    # 确定日期
    date_str = args.date or datetime.now().strftime("%Y-%m-%d")

    # 加载状态
    state = load_state()

    # 获取价格
    if args.price:
        price_data = {
            "date": date_str,
            "close": args.price,
            "high": args.price,
            "prev_close": state.get("last_close"),
        }
        print(f"[INPUT] 使用手动输入价格: ${args.price:.2f}")
    else:
        price_data = get_qqq_price()
        if price_data:
            date_str = price_data["date"]
            print(f"[AUTO] 自动获取 QQQ: ${price_data['close']:.2f} ({date_str})")
        else:
            print("[ERROR] 无法自动获取价格，请使用 --price 手动输入")
            print("        python s4_tracker.py --price 450.50")
            sys.exit(1)

    # 执行策略检查
    actions, messages, state = run_s4_check(
        price_data, state, date_str, force_regular=args.regular
    )

    # 输出报告
    build_report(date_str, price_data["close"], actions, messages, state)

    # 返回码供自动化判断
    if "extra" in actions:
        sys.exit(2)   # 补仓触发
    elif "regular" in actions:
        sys.exit(1)   # 定投触发
    else:
        sys.exit(0)   # 无操作

if __name__ == "__main__":
    main()
