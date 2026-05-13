# -*- coding: utf-8 -*-
import akshare as ak
import pandas as pd
from ta.momentum import RSIIndicator
from datetime import datetime, date
import time
import random

# ==================== 邮件发送依赖 ====================
import smtplib
from email.mime.text import MIMEText
from email.header import Header
import os

# =========================
# 参数
# =========================
ETF_CODE = "513130"
BUY_THRESHOLD = -1
SELL_THRESHOLD = 1
EXTREME_THRESHOLD = 5

# ==================== 邮件配置 ====================
QQ_EMAIL = os.getenv("SENDER_EMAIL", "你的本地调试用QQ邮箱@qq.com")
QQ_AUTH_CODE = os.getenv("SENDER_AUTH_CODE", "你的16位授权码")
RECEIVE_EMAIL = os.getenv("RECV_EMAIL", "你的接收邮箱@qq.com")

# ==================== 发邮件函数 ====================
def send_email(content):
    try:
        msg = MIMEText(content, "plain", "utf-8")
        msg["Subject"] = Header(f"{ETF_CODE} ETF 操作建议", "utf-8")
        msg["From"] = QQ_EMAIL
        msg["To"] = RECEIVE_EMAIL
        server = smtplib.SMTP_SSL("smtp.qq.com", 465)
        server.login(QQ_EMAIL, QQ_AUTH_CODE)
        server.sendmail(QQ_EMAIL, RECEIVE_EMAIL, msg.as_string())
        server.quit()
        print("✅ 邮件推送成功")
    except Exception as e:
        print("❌ 邮件发送失败:", e)

# =========================
# 辅助函数：判断数据是否包含当日数据
# =========================
def has_today_data(df):
    """
    检查DataFrame是否包含当日数据
    返回：True（包含）/False（不包含）
    """
    try:
        # 统一日期格式为datetime对象
        df["Date"] = pd.to_datetime(df["Date"]).dt.date
        latest_date = df.iloc[-1]["Date"]
        today = date.today()
        return latest_date == today
    except Exception as e:
        print(f"[日期检查] 失败：{str(e)}")
        return False

# =========================
# 获取实时数据（彻底修复）
# =========================
def get_realtime_etf_data(symbol):
    """获取ETF实时数据，用于补全历史数据"""
    try:
        # 获取ETF实时数据
        spot_df = ak.fund_etf_spot_em()
        
        # 筛选目标ETF
        target_etf = spot_df[spot_df["代码"] == symbol]
        if target_etf.empty:
            print("[实时数据] 未找到目标ETF数据")
            return None
        
        # 提取核心数据
        etf_info = target_etf.iloc[0]
        
        # 精准映射 + 单位统一
        realtime_data = {
            "Date": datetime.now().strftime("%Y-%m-%d"),
            "Close": float(etf_info["最新价"]),
            "Open": float(etf_info["开盘价"]) if pd.notna(etf_info["开盘价"]) else float(etf_info["最新价"]),
            "High": float(etf_info["最高价"]) if pd.notna(etf_info["最高价"]) else float(etf_info["最新价"]),
            "Low": float(etf_info["最低价"]) if pd.notna(etf_info["最低价"]) else float(etf_info["最新价"]),
            # 成交量：手 → 股（1手=100股）
            "Volume": float(etf_info["成交量"]) * 100 if pd.notna(etf_info["成交量"]) else 0,
            # 涨跌幅直接用实时接口的（百分比）
            "PctChange": float(etf_info["涨跌幅"]) if pd.notna(etf_info["涨跌幅"]) else 0
        }
        
        print(f"✅ 实时数据获取成功 | 最新价：{realtime_data['Close']} | 涨跌幅：{realtime_data['PctChange']}% | 成交量：{realtime_data['Volume']:,}股")
        return realtime_data
    except Exception as e:
        print(f"[实时数据] 获取失败：{str(e)}")
        return None

# =========================
# 【最终修复】获取ETF数据（双接口 + 按需补全实时数据）
# =========================
def get_etf_data(symbol):
    retry = 3

    # =========================
    # 数据源1：东方财富
    # =========================
    for i in range(retry):
        try:
            print(f"[东财] 获取数据... ({i+1}/{retry})")
            time.sleep(random.uniform(1, 3) + i)
            df = ak.fund_etf_hist_em(
                symbol=symbol,
                period="daily",
                adjust="qfq"
            )
            if df is not None and not df.empty and len(df) > 20:
                print("✅ 东方财富数据成功")
                df.rename(columns={
                    "日期": "Date",
                    "收盘": "Close",
                    "开盘": "Open",
                    "最高": "High",
                    "最低": "Low",
                    "成交量": "Volume",
                    "涨跌幅": "PctChange"
                }, inplace=True)
                
                # 先判断是否包含当日数据，仅缺失时补全
                if not has_today_data(df.copy()):  # 传副本避免修改原数据
                    print("[东财] 数据缺失今日行情，开始补全...")
                    realtime_data = get_realtime_etf_data(symbol)
                    if realtime_data:
                        try:
                            # 恢复Date为字符串格式，便于拼接
                            df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
                            new_row = pd.DataFrame([realtime_data])
                            df = pd.concat([df, new_row], ignore_index=True)
                            print(f"✅ 已补全今日({date.today()})实时数据到东财数据源")
                        except Exception as e:
                            print(f"[东财补全] 失败：{str(e)}")
                else:
                    print("[东财] 数据已包含今日最新行情，无需补全")
                    # 恢复Date为字符串格式
                    df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
            
                return df
        except Exception as e:
            print("[东财] 失败:", str(e))
        time.sleep((i + 1) * 2)

    # =========================
    # 数据源2：新浪（修复笔误+按需补全）
    # =========================
    print("\n[新浪] 尝试备用数据源...")
    try:
        if symbol.startswith(("51", "50", "56")):
            sina_symbol = "sh" + symbol
        elif symbol.startswith(("15", "16")):
            sina_symbol = "sz" + symbol
        else:
            sina_symbol = "sh" + symbol

        df = ak.fund_etf_hist_sina(symbol=sina_symbol)

        if df is not None and not df.empty and len(df) > 20:
            print("✅ 新浪数据成功")

            # 统一列名
            df.rename(columns={
                "date": "Date",
                "close": "Close",
                "open": "Open",
                "high": "High",
                "low": "Low",
                "volume": "Volume"
            }, inplace=True)

            # 计算新浪数据的涨跌幅（直接转百分比）
            df["PctChange"] = df["Close"].pct_change() * 100

            # 过滤无效行
            df = df.dropna(subset=["Close", "PctChange"])
            df = df[df["Volume"] > 0]
            df = df.reset_index(drop=True)

            if len(df) < 20:
                raise Exception("新浪数据有效长度不足")
            
            # =========================
            # 🔥 按需补全：先判断是否有今日数据
            # =========================
            # 先标准化日期格式
            df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
            # 检查是否包含今日数据
            if not has_today_data(df.copy()):
                print("[新浪] 数据缺失今日行情，开始补全...")
                realtime_data = get_realtime_etf_data(symbol)
                if realtime_data:
                    try:
                        # 添加实时数据行
                        new_row = pd.DataFrame([realtime_data])
                        df = pd.concat([df, new_row], ignore_index=True)
                        print(f"✅ 已补全今日({date.today()})实时数据到新浪数据源 | 涨跌幅：{realtime_data['PctChange']}% | 成交量：{realtime_data['Volume']:,}股")
                    except Exception as e:
                        print(f"[新浪补全] 失败：{str(e)}")
            else:
                print("[新浪] 数据已包含今日最新行情，无需补全")
            
            return df

    except Exception as e:
        print("[新浪] 失败:", str(e))

    print("❌ 所有数据源获取失败")
    return None

# =========================
# RSI计算
# =========================
def calculate_rsi(df):
    rsi = RSIIndicator(close=df["Close"], window=14)
    df["RSI"] = rsi.rsi()
    # 填充最后一行的RSI（实时数据行）
    if pd.isna(df.iloc[-1]["RSI"]):
        # 重新计算RSI确保包含最新数据
        df["RSI"] = rsi.rsi()
        # 如果还是空值，用前一天的RSI或默认值
        if pd.isna(df.iloc[-1]["RSI"]):
            df.loc[df.index[-1], "RSI"] = df.iloc[-2]["RSI"] if len(df) > 1 else 50
    return df

# =========================
# 连续涨跌统计
# =========================
def consecutive_days(df):
    closes = df["Close"].tolist()
    count = 0

    # 从最新一天往前数
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
    if market_state == "上涨趋势": score +=25
    elif market_state == "震荡": score +=10
    else: score -=20

    if rsi <30: score +=20
    elif rsi <40: score +=10
    elif rsi>70: score -=15

    if pct_change <=-1: score +=15
    elif pct_change >=1: score -=10

    if volume_state =="放量": score +=10
    elif volume_state =="缩量": score -=10

    if consecutive <=-2: score +=10
    elif consecutive >=2: score -=10

    return max(0, min(100, score))

# =========================
# 策略逻辑
# =========================
def strategy(df):
    if len(df) <20:
        raise Exception("数据量不足")

    latest = df.iloc[-1]
    current_price = latest["Close"]
    
    # 获取数据日期
    data_date = latest["Date"]

    # 涨跌幅已经是百分比，无需转换
    pct_change = float(latest["PctChange"])

    ma5 = df["Close"].tail(5).mean()
    ma20 = df["Close"].tail(20).mean()
    ma20_slope = df["Close"].tail(20).diff().mean()

    if current_price > ma20 and ma20_slope >0:
        market_state = "上涨趋势"
    elif current_price < ma20 and ma20_slope <0:
        market_state = "下跌趋势"
    else:
        market_state = "震荡"

    current_volume = latest["Volume"]
    avg_volume = df["Volume"].tail(20).mean()
    if current_volume > avg_volume*1.2:
        volume_state = "放量"
    elif current_volume < avg_volume*0.8:
        volume_state = "缩量"
    else:
        volume_state = "正常"

    rsi = round(latest["RSI"],3)
    if pd.isna(rsi): rsi=50

    consecutive = consecutive_days(df)

    # 策略分支
    if market_state == "上涨趋势":
        if pct_change <=-1 and rsi <40:
            signal,position="强加仓","+10%"
        elif pct_change <=-0.5:
            signal,position="弱加仓","+5%"
        elif pct_change >=2 and rsi>70:
            signal,position="减仓","-5%"
        else:
            signal,position="不动","保持"

    elif market_state == "震荡":
        if pct_change <=-1 and (rsi<30 or consecutive <=-2):
            signal,position="加仓","+5%~10%"
        elif pct_change >=1 and (rsi>70 or consecutive >=2):
            signal,position="减仓","-5%~10%"
        else:
            signal,position="不动","保持"

    else:
        if pct_change <=-2 and rsi <25:
            signal,position="轻仓试探","+3%"
        elif pct_change >=1:
            signal,position="减仓","-5%"
        else:
            signal,position="不动","观望为主"

    # 风险
    risk = []
    if market_state=="下跌趋势": risk.append("下跌趋势，控仓")
    elif market_state=="上涨趋势": risk.append("趋势向上，不追高")
    if rsi>70: risk.append("短期过热")
    if rsi<30: risk.append("短期超卖")
    if volume_state=="缩量": risk.append("量能不足")
    if volume_state=="放量": risk.append("量能确认")

    confidence = calculate_confidence(market_state,rsi,pct_change,volume_state,consecutive)

    # 极端行情
    if abs(pct_change) >= EXTREME_THRESHOLD:
        return {
            "data_date": data_date,
            "signal":"暂停操作",
            "reason":"市场剧烈波动",
            "position":position,
            "market_state":market_state,
            "risk":"；".join(risk),
            "pct_change":pct_change,
            "rsi":rsi,
            "ma5":ma5,"ma20":ma20,
            "current_price":current_price,
            "volume_state":volume_state,
            "consecutive":consecutive,
            "confidence":confidence,
            "last_10_days": df.tail(10)[["Date", "Open", "High", "Low", "Close", "PctChange", "Volume", "RSI"]].to_dict('records')
        }

    return {
        "data_date": data_date,
        "signal":signal,
        "position":position,
        "market_state":market_state,
        "risk":"；".join(risk),
        "pct_change":pct_change,
        "rsi":rsi,
        "ma5":ma5,"ma20":ma20,
        "current_price":current_price,
        "volume_state":volume_state,
        "consecutive":consecutive,
        "confidence":confidence,
        "reason":"正常运行",
        "last_10_days": df.tail(10)[["Date", "Open", "High", "Low", "Close", "PctChange", "Volume", "RSI"]].to_dict('records')
    }

# =========================
# 输出日志
# =========================
def print_result(result):
    log = "\n==========================\n"
    log += f"{ETF_CODE} ETF操作建议\n"
    log += "==========================\n"
    log += f"时间：{datetime.now()}\n"
    log += f"结论：{result['signal']}\n"
    log += f"置信度：{result['confidence']}\n"
    log += f"市场状态：{result['market_state']}\n"

    log += "\n指标情况：\n"
    log += f"数据日期：{result['data_date']}\n"
    log += f"今日涨跌幅：{result['pct_change']:.2f}%\n"
    log += f"RSI：{result['rsi']:.3f}\n"
    log += f"当前价格：{result['current_price']:.3f}\n"
    log += f"5日均线：{result['ma5']:.3f}\n"
    log += f"20日均线：{result['ma20']:.3f}\n"
    log += f"成交量状态：{result['volume_state']}\n"
    log += f"连续涨跌天数：{result['consecutive']}\n"

    log += "\n仓位建议：\n"
    log += result["position"] + "\n"

    log += "\n风险提示：\n"
    log += result["risk"] + "\n"

    log += "\n理由：\n"
    log += result["reason"] + "\n"
    
    log += "==========================\n"
    # 近十日数据输出
    log += "\n近十日数据参考：\n"
    log += "------------------------------------------------------\n"
    log += f"{'日期':<10} {'开盘':<4} {'收盘':<4} {'涨跌':<4} {'成交量':<8} {'RSI':<6}\n"
    log += "------------------------------------------------------\n"
    
    for day in result['last_10_days']:
        # 统一格式化数据
        date = str(day['Date'])[:10] if len(str(day['Date'])) > 10 else str(day['Date'])
        open_price = f"{day['Open']:.3f}" if pd.notna(day['Open']) else "-"
        close_price = f"{day['Close']:.3f}" if pd.notna(day['Close']) else "-"
        
        # 涨跌幅直接用（已经是百分比）
        pct_change_str = f"{day['PctChange']:.2f}" if pd.notna(day['PctChange']) else "-"
        
        # 成交量格式化：股 → 万股
        volume = f"{int(day['Volume']/10000):,}万" if pd.notna(day['Volume']) and day['Volume'] > 0 else "-"
        rsi = f"{day['RSI']:.3f}" if pd.notna(day['RSI']) else "-"
        
        # 拼接行数据
        log += f"{date:<12} {open_price:<6} {close_price:<6} {pct_change_str:<6} {volume:<9} {rsi:<8}\n"
    
    log += "------------------------------------------------------\n"
    print(log)
    return log

# =========================
# 主程序
# =========================
def main():
    try:
        df = get_etf_data(ETF_CODE)
        if df is None or df.empty or len(df)<20:
            raise Exception("数据获取失败或长度不足")

        df = calculate_rsi(df)
        result = strategy(df)
        log_content = print_result(result)
        send_email(log_content)

    except Exception as e:
        err = f"""
【ETF脚本运行异常】
时间：{datetime.now()}
错误：{str(e)}
"""
        print(err)
        send_email(err)

if __name__ == "__main__":
    main()
