# ☁️ S4 策略云端追踪（GitHub Actions 版）

**完全免费、7×24 运行、自动邮件通知的 QQQ S4 定投+补仓策略监控。**

---

## 🎯 功能

- ✅ **每天自动运行** — 香港时间早上 7:00 自动检查
- ✅ **自动邮件通知** — 触发定投/补仓时，GitHub 发邮件到你手机
- ✅ **状态云端持久化** — `state.json` 保存在仓库中，换设备不丢失
- ✅ **历史可追溯** — 所有操作记录保存在 GitHub Issues 里
- ✅ **零成本** — GitHub Actions 免费额度够用

---

## 🚀 部署步骤（5分钟搞定）

### 第 1 步：创建 GitHub 仓库

1. 打开 https://github.com/new
2. 仓库名填写：`s4-tracker`（或任何你喜欢的名字）
3. **选择 Private（私有仓库）** — 你的资产数据不要公开
4. 勾选 **"Add a README file"**
5. 点击 **Create repository**

### 第 2 步：上传代码

在本地终端执行：

```bash
# 克隆你的仓库（把 YOUR_USERNAME 换成你的 GitHub 用户名）
git clone https://github.com/YOUR_USERNAME/s4-tracker.git
cd s4-tracker

# 复制本目录的所有文件到仓库
cp /Users/xulongyu/WorkBuddy/20260522091958/s4-cloud-deploy/s4_cloud.py .
cp /Users/xulongyu/WorkBuddy/20260522091958/s4-cloud-deploy/.github/workflows/tracker.yml .github/workflows/

# 初始化状态文件
echo '{"initialized":false,"last_peak":null,"in_uptrend":false,"last_extra_date":null,"last_regular_date":null,"last_close":null,"total_invested":0.0,"total_shares":0.0,"history":[]}' > state.json

# 提交并推送
git add .
git commit -m "Initial S4 tracker setup"
git push origin main
```

### 第 3 步：配置邮件通知

GitHub 默认会给你的注册邮箱发 Issue 通知，但需要确认设置：

1. 打开 https://github.com/settings/notifications
2. 确保 **"Email notifications"** 已开启
3. 在 **"Subscriptions"** 部分，勾选：
   - ✅ **Comments on Issues and Pull Requests**
   - ✅ **Issue updates**
4. 保存设置

> 💡 **建议**：把 GitHub 邮件地址加入手机通讯录白名单，避免进垃圾邮件。

### 第 4 步：测试运行

1. 打开你的仓库页面
2. 点击顶部 **Actions** 标签
3. 左侧选择 **S4 Strategy Tracker**
4. 点击右侧 **Run workflow** → **Run workflow**
5. 等待 1-2 分钟，刷新页面看执行结果

如果执行成功：
- ✅ **绿色勾** = 正常执行
- 🟡 **黄色点** = 正在运行
- ❌ **红色叉** = 失败，点击查看错误日志

### 第 5 步：验证邮件通知

第一次运行通常**不会触发操作**（除非刚好是月末或大跌日）。

要测试邮件通知，可以临时触发一次定投：

1. 在仓库页面点击 **Actions**
2. 点击 **Run workflow**
3. 展开后填入以下参数（如果配置了 workflow_dispatch inputs）：
   - 或直接修改 `s4_cloud.py` 里的日期做测试

更简单的测试：等下一个月末（或等市场大跌 5%）。

---

## 📅 运行时间表

| 时间 | 说明 |
|------|------|
| UTC 23:00 | GitHub Actions 自动执行 |
| 香港时间次日 7:00 AM | 你早上起床时就能看到邮件 |
| 美股收盘后 3 小时 | 确保 yfinance 数据已更新 |

---

## 📧 邮件通知示例

**定投日邮件：**
```
Subject: 🟢 [S4定投] 2025-06-30 月末定投日

📅 日期: 2025-06-30  |  QQQ 收盘: $500.00

**🔔 今日操作:**
- 【定投】投入 HKD 3,000 | 价格 $500.00 | 买入 0.7692 股

**资产概况:**
- 💰 总投入: HKD 9,000.00
- 📈 持仓市值: HKD 9,164.51
- 💵 累计收益: HKD 164.51 (+1.83%)
```

**补仓邮件：**
```
Subject: 🔴 [S4补仓] 2025-07-05 距高点回撤触发补仓

**🔔 今日操作:**
- 【S4补仓】投入 HKD 3,000 | 价格 $475.00 | 距高点回撤 5.0%
```

---

## ⚙️ 自定义配置

如需调整参数，修改 `s4_cloud.py` 顶部的 `CONFIG`：

```python
CONFIG = {
    "monthly_invest": 3000,      # 每月定投金额（HKD）
    "extra_invest": 3000,        # 补仓金额（HKD）
    "drawdown_threshold": 0.05,  # 回撤阈值（5% = 0.05）
    "cooldown_days": 30,         # 补仓冷却期（天）
    "currency_rate": 7.8,        # USD/HKD 汇率
}
```

修改后提交：
```bash
git add s4_cloud.py
git commit -m "Update config"
git push
```

---

## 🔍 常见问题

### Q: 没有收到邮件？

1. 检查 GitHub 注册邮箱是否正确
2. 查看垃圾邮件文件夹
3. 确认仓库 Settings → Notifications 中已开启邮件
4. 尝试用另一个邮箱地址

### Q: 执行失败了？

1. 进入仓库 → Actions → 点击失败的运行记录
2. 查看日志找出错误原因
3. 常见原因：
   - yfinance 获取数据超时（网络问题，重试即可）
   - GitHub Token 权限不足（检查 workflow 中的 permissions 设置）

### Q: 如何暂停/恢复？

- **暂停**：进入仓库 → Actions → 选择 workflow → 右上角 **Disable workflow**
- **恢复**：点击 **Enable workflow**

### Q: 可以改执行时间吗？

修改 `.github/workflows/tracker.yml` 中的 cron：
```yaml
schedule:
  - cron: '0 23 * * *'   # UTC 23:00 = 香港次日 7:00 AM
```

常用时间参考：
- `0 1 * * *`  = 香港上午 9:00
- `0 12 * * *` = 香港晚上 8:00
- `0 21 * * *` = 香港次日 5:00 AM（美股收盘后）

---

## 🛡️ 隐私说明

- 所有数据保存在你的**私有仓库**中，他人无法查看
- 不依赖任何第三方服务（除了 yfinance 获取公开股价）
- 你的资产信息不会泄露给任何外部平台

---

## 📱 手机端体验

建议在手机上：
1. 安装 GitHub App（iOS/Android）
2. 开启推送通知
3. 这样即使不看邮件，也能收到 Issue 创建提醒

---

**部署完成后，你就拥有了一个 7×24 运行的 S4 策略监控机器人，无论你在哪、电脑开不开机，它都会准时提醒你该定投或补仓了！**
