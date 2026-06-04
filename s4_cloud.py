#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
S4 策略云端追踪脚本
====================
运行在 GitHub Actions 上，每天自动检查 QQQM 价格，触发操作时创建 GitHub Issue 发邮件通知。

环境变量:
    GITHUB_TOKEN    - GitHub 自动提供
    GITHUB_REPO     - 仓库名，格式: owner/repo
"""

import json
import os
import sys
from datetime import datetime, timedelta

import requests
import yfinance as yf

# ============ 配置 ============
STATE_FILE = "state.json"
CONFIG = {
    "monthly_invest": 3000,      # HKD
    "extra_invest": 3000,        # HKD
    "drawdown_threshold": 0.05,  # 5%
    "cooldown_days": 14,         # 补仓冷却期（天）— 经回测验证，14天为最佳平衡点
    "currency_rate": 7.8,
    "symbol": "QQQM",
}

# ============ 市场时间检查 ============

def is_market_hours():
    """判断当前是否在美股交易时段（近似）
    覆盖 EDT(9:30-16:00 ET = 13:30-20:00 UTC) +
        EST(9:30-16:00 ET = 14:30-21:00 UTC)
    只在周一~周五返回 True（周末永远 False）
    """
    now = datetime.utcnow()
    if now.weekday() >= 5:  # 周六/周日
        return False

    minute_of_day = now.hour * 60 + now.minute
    # EDT 夏令时: 13:30-20:00 UTC
    edt_open = 13 * 60 + 30   # 810
    edt_close = 20 * 60        # 1200
    # EST 冬令时: 14:30-21:00 UTC
    est_open = 14 * 60 + 30   # 870
    est_close = 21 * 60        # 1260

    in_edt = edt_open <= minute_of_day <= edt_close
    in_est = est_open <= minute_of_day <= est_close
    return in_edt or in_est


# ============ GitHub API 工具 ============

def get_repo():
    """从环境变量获取仓库名"""
    repo = os.environ.get("GITHUB_REPO")
    if not repo:
        # 尝试从 GITHUB_REPOSITORY 环境变量获取（Actions 自动提供）
        repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        raise RuntimeError("请设置 GITHUB_REPO 环境变量，格式: owner/repo")
    return repo

def get_token():
    """获取 GitHub Token"""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN 未设置")
    return token

def create_issue(title, body, labels=None):
    """创建 GitHub Issue，GitHub 会自动发邮件通知"""
    repo = get_repo()
    token = get_token()
    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    data = {"title": title, "body": body}
    if labels:
        data["labels"] = labels
    
    resp = requests.post(url, headers=headers, json=data, timeout=30)
    if resp.status_code == 201:
        issue = resp.json()
        print(f"[ISSUE] 已创建通知: {issue['html_url']}")
        return issue
    else:
        print(f"[ERROR] 创建 Issue 失败: {resp.status_code} - {resp.text}")
        return None

# ============ 状态管理 ============

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
        "last_peak": None,
        "in_uptrend": False,
        "last_extra_date": None,
        "last_regular_date": None,
        "last_close": None,
        "total_invested": 0.0,
        "total_shares": 0.0,
        "history": [],
    }

def save_state(state):
    """保存状态文件"""
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, default=str)
    print(f"[STATE] 状态已保存到 {STATE_FILE}")

# ============ 价格获取 ============

def get_qqq_price():
    """获取 QQQM 最新收盘价"""
    try:
        ticker = yf.Ticker("QQQM")
        hist = ticker.history(period="5d")
        if hist.empty:
            return None
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
        print(f"[ERROR] 获取价格失败: {e}")
        return None

# ============ S4 策略核心 ============

def is_last_trading_day_of_month(date_str):
    """判断是否为月末最后一个交易日（交易日感知版）

    规则：如果 yfinance 返回的日期是本月最后一个交易日。
    逻辑：从当月最后一天往前找，第一个周一~周五就是最后一个交易日。
    如果 date_str 等于那个日期，就是月末定投日。
    """
    d = datetime.strptime(date_str, "%Y-%m-%d")
    # 当月最后一天
    if d.month == 12:
        last_calendar = datetime(d.year + 1, 1, 1) - timedelta(days=1)
    else:
        last_calendar = datetime(d.year, d.month + 1, 1) - timedelta(days=1)
    # 从最后一天往前找第一个工作日
    last_trading = last_calendar
    while last_trading.weekday() >= 5:  # 5=Saturday, 6=Sunday
        last_trading -= timedelta(days=1)
    return d.date() == last_trading.date()

def run_s4_strategy(price_data, state, date_str, force_regular=False):
    """
    执行 S4 策略检查。
    返回: (actions, messages, updated_state)
    """
    p = price_data["close"]
    h = price_data["high"]
    prev = price_data.get("prev_close")
    if prev is None and state.get("last_close"):
        prev = state["last_close"]

    actions = []
    messages = []

    # 首次初始化
    if not state.get("initialized"):
        state["last_peak"] = h
        state["in_uptrend"] = True
        state["initialized"] = True
        print(f"[INIT] 首次运行，last_peak=${h:.2f}, in_uptrend=True")

    # 1. 定期定投（每月最后一天）
    is_regular_day = force_regular or is_last_trading_day_of_month(date_str)

    if is_regular_day:
        already_invested = False
        if state.get("last_regular_date"):
            last_reg = datetime.strptime(state["last_regular_date"], "%Y-%m-%d")
            current = datetime.strptime(date_str, "%Y-%m-%d")
            if last_reg.year == current.year and last_reg.month == current.month:
                already_invested = True

        if already_invested:
            print(f"[SKIP] 本月已定投 ({state['last_regular_date']})")
        else:
            actions.append("regular")
            amt = CONFIG["monthly_invest"]
            shares = amt / (p * CONFIG["currency_rate"])
            state["total_invested"] += amt
            state["total_shares"] += shares
            state["last_regular_date"] = date_str
            state["in_uptrend"] = True
            state["last_peak"] = h
            messages.append(
                f"【定投】投入 HKD {amt:,} | 价格 ${p:.2f} | "
                f"买入 {shares:.4f} 股 | 本月周期重置"
            )

    # 2. S4 上涨周期高点回撤检查
    if state.get("in_uptrend") and h > state.get("last_peak", 0):
        state["last_peak"] = h
        print(f"[PEAK] 更新周期高点 last_peak = ${h:.2f}")

    if prev is not None and state.get("in_uptrend"):
        if p < prev:
            dd = (state["last_peak"] - p) / state["last_peak"] if state["last_peak"] else 0
            print(f"[DROP] 今日下跌 ${prev:.2f}→${p:.2f}, 距高点回撤 {dd*100:.2f}%")

            if dd >= CONFIG["drawdown_threshold"]:
                can_extra = True
                if state.get("last_extra_date"):
                    last_extra = datetime.strptime(state["last_extra_date"], "%Y-%m-%d")
                    current = datetime.strptime(date_str, "%Y-%m-%d")
                    days_since = (current - last_extra).days
                    if days_since < CONFIG["cooldown_days"]:
                        can_extra = False
                        print(f"[COOLDOWN] 冷却期中 ({days_since}/{CONFIG['cooldown_days']} 天)")

                if can_extra:
                    actions.append("extra")
                    amt = CONFIG["extra_invest"]
                    shares = amt / (p * CONFIG["currency_rate"])
                    state["total_invested"] += amt
                    state["total_shares"] += shares
                    state["last_extra_date"] = date_str
                    state["last_peak"] = p
                    state["in_uptrend"] = False
                    messages.append(
                        f"【S4补仓】投入 HKD {amt:,} | 价格 ${p:.2f} | "
                        f"买入 {shares:.4f} 股 | 距高点回撤 {dd*100:.1f}%"
                    )
        else:
            state["in_uptrend"] = True

    state["last_close"] = p

    if actions:
        state["history"].append({
            "date": date_str,
            "price_usd": p,
            "actions": actions,
            "messages": messages,
        })

    return actions, messages, state

def build_report(date_str, price, actions, messages, state):
    """构建报告"""
    p = price
    total_val = state["total_shares"] * p * CONFIG["currency_rate"]
    profit = total_val - state["total_invested"]
    ret_pct = (profit / state["total_invested"] * 100) if state["total_invested"] > 0 else 0

    lines = [
        f"📅 日期: {date_str}  |  QQQM 收盘: ${p:.2f}",
        "",
        "**策略状态:**",
        f"- last_peak: ${state['last_peak']:.2f}" if state.get("last_peak") else "- last_peak: 未初始化",
        f"- in_uptrend: {state['in_uptrend']}",
        f"- 上次定投: {state.get('last_regular_date', '无')}",
        f"- 上次补仓: {state.get('last_extra_date', '无')}",
        "",
        "**资产概况:**",
        f"- 💰 总投入: HKD {state['total_invested']:,.2f}",
        f"- 📈 持仓市值: HKD {total_val:,.2f}",
        f"- 💵 累计收益: HKD {profit:,.2f} ({ret_pct:+.2f}%)",
    ]

    if actions:
        lines.insert(2, "")
        lines.insert(3, "**🔔 今日操作:**")
        for msg in messages:
            lines.insert(4, f"- {msg}")
    else:
        lines.insert(2, "")
        lines.insert(3, "✅ 今日无操作")

    return "\n".join(lines)

# ============ 主入口 ============

def main():
    print("=" * 60)
    print("S4 策略云端追踪")
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 60)

    # 非交易时段快速退出（防节假日等边缘情况）
    if not is_market_hours():
        print("[SKIP] 非美股交易时段，退出")
        sys.exit(0)

    # 加载状态
    state = load_state()

    # 获取价格
    price_data = get_qqq_price()
    if not price_data:
        print("[ERROR] 无法获取 QQQM 价格，今日跳过")
        sys.exit(1)

    date_str = price_data["date"]
    print(f"[DATA] QQQM {date_str} 收盘: ${price_data['close']:.2f}")

    # 执行策略
    actions, messages, state = run_s4_strategy(price_data, state, date_str)

    # 保存状态
    save_state(state)

    # 构建报告
    report = build_report(date_str, price_data["close"], actions, messages, state)
    print("\n" + report)

    # 触发操作时创建 GitHub Issue（邮件通知）
    if actions:
        if "extra" in actions:
            title = f"🔴 [S4补仓] {date_str} 距高点回撤触发补仓"
        elif "regular" in actions:
            title = f"🟢 [S4定投] {date_str} 月末定投日"
        else:
            title = f"📊 [S4操作] {date_str}"

        issue = create_issue(title, report, labels=["s4-alert"])
        if issue:
            print(f"\n[NOTIFY] 邮件通知已发送至你的 GitHub 注册邮箱")

    # 返回码
    if "extra" in actions:
        sys.exit(2)
    elif "regular" in actions:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
