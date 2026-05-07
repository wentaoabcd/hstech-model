# -*- coding: utf-8 -*-

import akshare as ak
import pandas as pd
from ta.momentum import RSIIndicator
from datetime import datetime
import time
import requests

session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/122.0 Safari/537.36"
    )
})

# =========================
# 参数
# =========================

ETF_CODE = "513130"

BUY_THRESHOLD = -1
SELL_THRESHOLD = 1
EXTREME_THRESHOLD = 5


# =========================
# 获取ETF数据
# =========================

def get_etf_data(symbol):
    
    retry = 5
    for i in range(retry):
        try:
            print(f"正在获取ETF数据... (尝试 {i+1}/{retry})")
            df = ak.fund_etf_hist_em(
                symbol=symbol,
                period="daily",
                adjust="qfq"
            )
            if not df.empty:
                print("成功获取ETF数据")
                df.rename(columns={
                    "日期": "Date",
                    "收盘": "Close",
                    "开盘": "Open",
                    "最高": "High",
                    "最低": "Low",
                    "成交量": "Volume",
                    "涨跌幅": "PctChange"
                    }, inplace=True)
                return df
        except Exception as e:
            print("获取ETF数据失败:", e)
            if i < retry - 1:
                print("3秒后重试...\n")
                time.sleep(3)  # 等待1秒后重试
            else:
                raise Exception("获取ETF数据失败，已达到最大重试次数")




# =========================
# RSI计算
# =========================

def calculate_rsi(df):

    rsi = RSIIndicator(
        close=df["Close"],
        window=14
    )

    df["RSI"] = rsi.rsi()

    return df


# =========================
# 连续涨跌统计
# =========================

def consecutive_days(df):

    closes = df["Close"].tolist()

    count = 0

    for i in range(len(closes)-1, 0, -1):

        if closes[i] > closes[i-1]:

            if count >= 0:
                count += 1
            else:
                break

        elif closes[i] < closes[i-1]:

            if count <= 0:
                count -= 1
            else:
                break

        else:
            break

    return count


# =========================
# 策略逻辑
# =========================

def strategy(df):

    latest = df.iloc[-1]

    current_price = latest["Close"]
    low_price = latest["Low"]
    pct_change = latest["PctChange"]

    # 5日均线
    ma5 = df["Close"].tail(5).mean()

    # 成交量
    current_volume = latest["Volume"]
    avg_volume = df["Volume"].tail(20).mean()

    # RSI
    rsi = latest["RSI"]

    # 连续涨跌
    consecutive = consecutive_days(df)

    # 成交量状态
    if current_volume > avg_volume * 1.2:
        volume_state = "放量"
    elif current_volume < avg_volume * 0.8:
        volume_state = "缩量"
    else:
        volume_state = "正常"

    # 极端波动
    if abs(pct_change) >= EXTREME_THRESHOLD:

        return {
            "signal": "暂停操作",
            "reason": "市场波动过大"
        }

    # 超卖
    oversold = (
        rsi < 30
        or consecutive <= -3
    )

    # 超买
    overbought = (
        rsi > 70
        or consecutive >= 3
    )

    # 加仓条件
    buy_signal = all([
        pct_change <= BUY_THRESHOLD,
        oversold,
        low_price <= ma5,
        volume_state != "缩量"
    ])

    # 减仓条件
    sell_signal = all([
        pct_change >= SELL_THRESHOLD,
        overbought,
        current_price >= ma5,
        volume_state != "缩量"
    ])

    # 输出信号
    if buy_signal:

        signal = "加仓"
        position = "+5% ~ +10%"
        risk = "避免一次性重仓"

    elif sell_signal:

        signal = "减仓"
        position = "-5% ~ -10%"
        risk = "避免过早清仓"

    else:

        signal = "不动"
        position = "保持仓位"
        risk = "避免频繁交易"

    return {
        "signal": signal,
        "position": position,
        "risk": risk,
        "pct_change": pct_change,
        "rsi": rsi,
        "ma5": ma5,
        "current_price": current_price,
        "volume_state": volume_state,
        "consecutive": consecutive
    }


# =========================
# 输出
# =========================

def print_result(result):

    print("\n==========================")
    print("恒生科技ETF交易模型")
    print("==========================")

    print(f"\n时间：{datetime.now()}")

    print(f"\n结论：{result['signal']}")

    if result["signal"] != "暂停操作":

        print("\n指标情况：")

        print(f"今日涨跌幅：{result['pct_change']}%")
        print(f"RSI：{round(result['rsi'],2)}")
        print(f"当前价格：{round(result['current_price'],2)}")
        print(f"5日均线：{round(result['ma5'],2)}")
        print(f"成交量状态：{result['volume_state']}")
        print(f"连续涨跌天数：{result['consecutive']}")

        print("\n仓位建议：")
        print(result["position"])

        print("\n风险提示：")
        print(result["risk"])

    else:

        print(result["reason"])

    print("\n==========================\n")


# =========================
# 主程序
# =========================

def main():

    try:

        df = get_etf_data(ETF_CODE)

        df = calculate_rsi(df)

        result = strategy(df)

        print_result(result)

    except Exception as e:

        print("运行失败：", e)


if __name__ == "__main__":

    main()