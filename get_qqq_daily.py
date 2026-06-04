import yfinance as yf
import pandas as pd

ticker = "QQQM"
start_date = "2021-01-01"  # QQQM 于 2021 年上市
end_date = "2025-12-31"

print("正在下载 QQQM 日线数据...")
data = yf.download(ticker, start=start_date, end=end_date, progress=False)
data['Close'].to_csv("qqqm_daily_prices_2021_2025.csv")
print("已保存至 qqqm_daily_prices_2021_2025.csv")