import yfinance as yf
import pandas as pd
from datetime import datetime

# 下载 QQQM 数据（2021 年上市）
ticker = "QQQM"
start_date = "2021-01-01"
end_date = "2025-12-31"

print("正在下载 QQQM 历史数据...")
data = yf.download(ticker, start=start_date, end=end_date, progress=False)

# 保留收盘价
close = data['Close']

# 按月重采样，取每月最后一个交易日的收盘价
monthly_close = close.resample('M').last()

# 转成 DataFrame 并格式化
monthly_df = monthly_close.reset_index()
monthly_df.columns = ['Date', 'Close_USD']
# 将 Date 转为 YYYY-MM 字符串
monthly_df['YearMonth'] = monthly_df['Date'].dt.to_period('M').astype(str)
# 只保留我们需要的列
monthly_df = monthly_df[['YearMonth', 'Close_USD']]

# 排序
monthly_df = monthly_df.sort_values('YearMonth')

# 打印
print("\nQQQM 月度收盘价（USD）:")
print(monthly_df.to_string(index=False))

# 保存 CSV
csv_path = "qqqm_monthly_prices_2021_2025.csv"
monthly_df.to_csv(csv_path, index=False)
print(f"\n已保存至 {csv_path}")