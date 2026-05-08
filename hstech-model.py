# -*- coding: utf-8 -*-
import akshare as ak
import pandas as pd
from ta.momentum import RSIIndicator
from datetime import datetime
import time

# ==================== 新增：邮件发送依赖 ====================
import smtplib
from email.mime.text import MIMEText
from email.header import Header
import os
# ============================================================

# =========================
# 参数
# =========================

ETF_CODE = "513130"

BUY_THRESHOLD = -1
SELL_THRESHOLD = 1
EXTREME_THRESHOLD = 5

# ==================== 邮件配置（从环境变量读取，兼容GitHub Secrets和本地调试） ====================
QQ_EMAIL = os.getenv("SENDER_EMAIL", "你的本地调试用QQ邮箱@qq.com")
QQ_AUTH_CODE = os.getenv("SENDER_AUTH_CODE", "你的本地调试用16位授权码")
RECEIVE_EMAIL = os.getenv("RECV_EMAIL", "你的本地调试用接收邮箱@qq.com")
# =================================================================================================

# ==================== 新增：发邮件函数（完全不用改） ====================
def send_email(content):
    try:
        msg = MIMEText(content, "plain", "utf-8")
        msg["Subject"] = Header("513130 ETF 交易信号", "utf-8")
        msg["From"] = QQ_EMAIL
        msg["To"] = RECEIVE_EMAIL

        server = smtplib.SMTP_SSL("smtp.qq.com", 465)
        server.login(QQ_EMAIL, QQ_AUTH_CODE)
        server.sendmail(QQ_EMAIL, RECEIVE_EMAIL, msg.as_string())
        server.quit()
        print("✅ 邮件推送成功")
    except Exception as e:
        print("❌ 邮件发送失败:", e)
# ======================================================================

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
                time.sleep(3)
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
# 置信度计算
# =========================
def calculate_confidence(market_state, rsi, pct_change, volume_state, consecutive):
    score = 50
    if market_state == "上涨趋势":
        score += 25
    elif market_state == "震荡":
        score += 10
    else:
        score -= 20

    if rsi < 30:
        score += 20
    elif rsi < 40:
        score += 10
    elif rsi > 70:
        score -= 15

    if pct_change <= -1:
        score += 15
    elif pct_change >= 1:
        score -= 10

    if volume_state == "放量":
        score += 10
    elif volume_state == "缩量":
        score -= 10

    if consecutive <= -2:
        score += 10
    elif consecutive >= 2:
        score -= 10

    score = max(0, min(100, score))
    return score

# =========================
# 策略逻辑
# =========================
def strategy(df):
    if len(df) < 20:
        raise Exception("数据不足")

    now = datetime.now()
    if now.hour < 15:
        latest = df.iloc[-1]
    else:
        latest = df.iloc[-1]

    current_price = latest["Close"]
    low_price = latest["Low"]

    pct_change = float(latest["PctChange"])
    if abs(pct_change) < 1:
        pct_change *= 100

    ma5 = df["Close"].tail(5).mean()
    ma20 = df["Close"].tail(20).mean()

    ma20_slope = df["Close"].tail(20).diff().mean()

    if current_price > ma20 and ma20_slope > 0:
        market_state = "上涨趋势"
    elif current_price < ma20 and ma20_slope < 0:
        market_state = "下跌趋势"
    else:
        market_state = "震荡"

    current_volume = latest["Volume"]
    avg_volume = df["Volume"].tail(20).mean()

    if current_volume > avg_volume * 1.2:
        volume_state = "放量"
    elif current_volume < avg_volume * 0.8:
        volume_state = "缩量"
    else:
        volume_state = "正常"

    rsi = round(latest["RSI"], 3)
    if pd.isna(rsi):
        rsi = 50

    consecutive = consecutive_days(df)

    if market_state == "上涨趋势":
        if pct_change <= -1 and rsi < 40:
            signal = "强加仓"
            position = "+10%"
        elif pct_change <= -0.5:
            signal = "弱加仓"
            position = "+5%"
        elif pct_change >= 2 and rsi > 70:
            signal = "减仓"
            position = "-5%"
        else:
            signal = "不动"
            position = "保持"

    elif market_state == "震荡":
        if pct_change <= -1 and (rsi < 30 or consecutive <= -2):
            signal = "加仓"
            position = "+5%~10%"
        elif pct_change >= 1 and (rsi > 70 or consecutive >= 2):
            signal = "减仓"
            position = "-5%~10%"
        else:
            signal = "不动"
            position = "保持"

    else:
        if pct_change <= -2 and rsi < 25:
            signal = "轻仓试探"
            position = "+3%"
        elif pct_change >= 1:
            signal = "减仓"
            position = "-5%"
        else:
            signal = "不动"
            position = "观望为主"

    risk = []
    if market_state == "下跌趋势":
        risk.append("处于下跌趋势，建议控制仓位")
    elif market_state == "上涨趋势":
        risk.append("趋势向上，但注意不要追高")

    if rsi > 70:
        risk.append("短期过热，可能回调")
    elif rsi < 30:
        risk.append("短期超卖，可能反弹")

    if volume_state == "缩量":
        risk.append("成交量不足，信号可靠性下降")
    elif volume_state == "放量":
        risk.append("成交量放大，趋势确认度较高")

    confidence = calculate_confidence(market_state, rsi, pct_change, volume_state, consecutive)

    if abs(pct_change) >= EXTREME_THRESHOLD:
        return {
            "signal": "暂停操作",
            "reason": "市场剧烈波动",
            "position": position,
            "market_state": market_state,
            "risk": "；".join(risk),
            "pct_change": pct_change,
            "rsi": rsi,
            "ma5": ma5,
            "ma20": ma20,
            "current_price": current_price,
            "volume_state": volume_state,
            "consecutive": consecutive,
            "confidence": confidence
        }
    return {
        "signal": signal,
        "position": position,
        "market_state": market_state,
        "risk": "；".join(risk),
        "pct_change": pct_change,
        "rsi": rsi,
        "ma5": ma5,
        "ma20": ma20,
        "current_price": current_price,
        "volume_state": volume_state,
        "consecutive": consecutive,
        "confidence": confidence
    }

# =========================
# 输出
# =========================
def print_result(result):
    log = "\n==========================\n"
    log += "恒生科技ETF操作建议\n"
    log += "==========================\n"

    log += f"\n时间：{datetime.now()}\n"
    log += f"\n结论：{result['signal']}\n"
    log += f"置信度：{result['confidence']}\n"
    log += f"市场状态：{result['market_state']}\n"

    if result["signal"] != "暂停操作":
        log += "\n指标情况：\n"
        log += f"今日涨跌幅：{result['pct_change']}%\n"
        log += f"RSI：{round(result['rsi'],3)}\n"
        log += f"当前价格：{round(result['current_price'],3)}\n"
        log += f"5日均线：{round(result['ma5'],3)}\n"
        log += f"20日均线：{round(result['ma20'],3)}\n"
        log += f"成交量状态：{result['volume_state']}\n"
        log += f"连续涨跌天数：{result['consecutive']}\n"
        log += "\n仓位建议：\n"
        log += result["position"] + "\n"
        log += "\n风险提示：\n"
        log += result["risk"] + "\n"
    else:
        log += result["reason"] + "\n"

    log += "==========================\n"
    print(log)
    return log  # 返回日志内容，用于发邮件

# =========================
# 主程序
# =========================
def main():
    try:
        df = get_etf_data(ETF_CODE)
        df = calculate_rsi(df)
        result = strategy(df)
        log_content = print_result(result)
        
        # ==================== 新增：自动发邮件 ====================
        send_email(log_content)
        # ==========================================================

    except Exception as e:
        error_msg = f"运行失败：{str(e)}"
        print(error_msg)
        send_email(error_msg)

if __name__ == "__main__":
    main()
