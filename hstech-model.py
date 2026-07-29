# -*- coding: utf-8 -*-
import akshare as ak
import pandas as pd
from ta.momentum import RSIIndicator
from datetime import datetime, date, timedelta
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
HISTORY_DAYS = 30
ROLLING_WINDOW = 10

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
    try:
        df["Date"] = pd.to_datetime(df["Date"]).dt.date
        latest_date = df.iloc[-1]["Date"]
        today = date.today()
        return latest_date == today
    except Exception as e:
        print(f"[日期检查] 失败：{str(e)}")
        return False

# =========================
# 获取实时数据
# =========================
def get_realtime_etf_data(symbol):
    try:
        spot_df = ak.fund_etf_spot_em()
        target_etf = spot_df[spot_df["代码"] == symbol]
        if target_etf.empty:
            print("[实时数据] 未找到目标ETF数据")
            return None
        etf_info = target_etf.iloc[0]
        realtime_data = {
            "Date": datetime.now().strftime("%Y-%m-%d"),
            "Close": float(etf_info["最新价"]),
            "Open": float(etf_info["开盘价"]) if pd.notna(etf_info["开盘价"]) else float(etf_info["最新价"]),
            "High": float(etf_info["最高价"]) if pd.notna(etf_info["最高价"]) else float(etf_info["最新价"]),
            "Low": float(etf_info["最低价"]) if pd.notna(etf_info["最低价"]) else float(etf_info["最新价"]),
            "Volume": float(etf_info["成交量"]) * 100 if pd.notna(etf_info["成交量"]) else 0,
            "PctChange": float(etf_info["涨跌幅"]) if pd.notna(etf_info["涨跌幅"]) else 0
        }
        print(f"✅ 实时数据获取成功 | 最新价：{realtime_data['Close']} | 涨跌幅：{realtime_data['PctChange']}% | 成交量：{realtime_data['Volume']:,}股")
        return realtime_data
    except Exception as e:
        print(f"[实时数据] 获取失败：{str(e)}")
        return None

# =========================
# 获取ETF数据（双接口 + 补全）
# =========================
def get_etf_data(symbol):
    retry = 3

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
                
                if not has_today_data(df.copy()):
                    print("[东财] 数据缺失今日行情，开始补全...")
                    realtime_data = get_realtime_etf_data(symbol)
                    if realtime_data:
                        try:
                            df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
                            new_row = pd.DataFrame([realtime_data])
                            df = pd.concat([df, new_row], ignore_index=True)
                            print(f"✅ 已补全今日({date.today()})实时数据到东财数据源")
                        except Exception as e:
                            print(f"[东财补全] 失败：{str(e)}")
                else:
                    print("[东财] 数据已包含今日最新行情，无需补全")
                    df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
            
                return df
        except Exception as e:
            print("[东财] 失败:", str(e))
        time.sleep((i + 1) * 2)

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
            df.rename(columns={
                "date": "Date",
                "close": "Close",
                "open": "Open",
                "high": "High",
                "low": "Low",
                "volume": "Volume"
            }, inplace=True)

            df["PctChange"] = df["Close"].pct_change() * 100
            df = df.dropna(subset=["Close", "PctChange"])
            df = df[df["Volume"] > 0]
            df = df.reset_index(drop=True)

            if len(df) < 20:
                raise Exception("新浪数据有效长度不足")
            
            df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
            if not has_today_data(df.copy()):
                print("[新浪] 数据缺失今日行情，开始补全...")
                realtime_data = get_realtime_etf_data(symbol)
                if realtime_data:
                    try:
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
    if pd.isna(df.iloc[-1]["RSI"]):
        df["RSI"] = rsi.rsi()
        if pd.isna(df.iloc[-1]["RSI"]):
            df.loc[df.index[-1], "RSI"] = df.iloc[-2]["RSI"] if len(df) > 1 else 50
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
# 核心决策逻辑（抽取出来供历史和当前共用）
# =========================
def decision_logic(market_state, pct_change, rsi, consecutive):
    """根据市场状态、涨跌幅、RSI、连续涨跌天返回 (signal, position)"""
    if market_state == "上涨趋势":
        if pct_change <= -1 and rsi < 40:
            signal, position = "强加仓", "+10%"
        elif pct_change <= -0.5:
            signal, position = "弱加仓", "+5%"
        elif pct_change >= 2 and rsi > 70:
            signal, position = "减仓", "-5%"
        else:
            signal, position = "不动", "保持"
    elif market_state == "震荡":
        if pct_change <= -1 and (rsi < 30 or consecutive <= -2):
            signal, position = "加仓", "+5%~10%"
        elif pct_change >= 1 and (rsi > 70 or consecutive >= 2):
            signal, position = "减仓", "-5%~10%"
        else:
            signal, position = "不动", "保持"
    else:  # 下跌趋势
        if pct_change <= -2 and rsi < 25:
            signal, position = "轻仓试探", "+3%"
        elif pct_change >= 1:
            signal, position = "减仓", "-5%"
        else:
            signal, position = "不动", "观望为主"
    return signal, position

# =========================
# 计算某一日的状态（市场、成交量、连续涨跌等）
# =========================
def compute_states(df, idx):
    """返回第idx行的市场状态、成交量状态、连续涨跌天数、涨跌幅、RSI、当前价、MA5、MA20"""
    row = df.iloc[idx]
    current_price = row["Close"]
    pct_change = row["PctChange"]
    rsi = row["RSI"]
    
    if 'MA5' not in df.columns:
        df['MA5'] = df['Close'].rolling(5).mean()
    if 'MA20' not in df.columns:
        df['MA20'] = df['Close'].rolling(20).mean()
    ma5 = df.iloc[idx]['MA5']
    ma20 = df.iloc[idx]['MA20']
    
    if idx >= 19:
        closes = df.iloc[idx-19:idx+1]['Close']
        ma20_slope = closes.diff().mean()
    else:
        ma20_slope = 0
    
    if current_price > ma20 and ma20_slope > 0:
        market_state = "上涨趋势"
    elif current_price < ma20 and ma20_slope < 0:
        market_state = "下跌趋势"
    else:
        market_state = "震荡"
    
    current_volume = row["Volume"]
    avg_volume = df['Volume'].iloc[max(0, idx-19):idx+1].mean()
    if current_volume > avg_volume * 1.2:
        volume_state = "放量"
    elif current_volume < avg_volume * 0.8:
        volume_state = "缩量"
    else:
        volume_state = "正常"
    
    consecutive = consecutive_days(df.iloc[:idx+1])
    
    return market_state, volume_state, consecutive, pct_change, rsi, current_price, ma5, ma20

# =========================
# 策略逻辑（使用抽取的函数）
# =========================
def strategy(df):
    if len(df) < 20:
        raise Exception("数据量不足")

    idx = len(df) - 1
    market_state, volume_state, consecutive, pct_change, rsi, current_price, ma5, ma20 = compute_states(df, idx)
    
    signal, position = decision_logic(market_state, pct_change, rsi, consecutive)
    
    if abs(pct_change) >= EXTREME_THRESHOLD:
        signal = "暂停操作"
        position = ""
    
    risk = []
    if market_state == "下跌趋势": risk.append("下跌趋势，控仓")
    elif market_state == "上涨趋势": risk.append("趋势向上，不追高")
    if rsi > 70: risk.append("短期过热")
    if rsi < 30: risk.append("短期超卖")
    if volume_state == "缩量": risk.append("量能不足")
    if volume_state == "放量": risk.append("量能确认")
    
    confidence = calculate_confidence(market_state, rsi, pct_change, volume_state, consecutive)
    
    return {
        "data_date": df.iloc[idx]["Date"],
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
        "confidence": confidence,
        "reason": "正常运行",
        "last_10_days": df.tail(10)[["Date", "Open", "High", "Low", "Close", "PctChange", "Volume", "RSI"]].to_dict('records')
    }

# =========================
# 生成历史建议及胜率（全量滚动10个交易日）
# =========================
def build_history_with_signals(df, history_days=HISTORY_DAYS):
    """
    对df中的每一天（从第20天起）计算建议，验证次日涨跌，并计算近10日滚动胜率
    胜率计算使用该日期之前的连续10个交易日（全量历史数据）
    返回一个包含最后history_days天的DataFrame，增加'建议'和'近10日胜率'列
    """
    df['MA5'] = df['Close'].rolling(5).mean()
    df['MA20'] = df['Close'].rolling(20).mean()
    
    records = []  # 元素: {'index': i, 'signal': signal, 'position': position, 'correct': True/False/None}
    
    # 从第20天开始（需要20日均线）到倒数第二天（验证需要次日）
    for i in range(20, len(df) - 1):
        market_state, volume_state, consecutive, pct_change, rsi, _, _, _ = compute_states(df, i)
        signal, position = decision_logic(market_state, pct_change, rsi, consecutive)
        
        if abs(pct_change) >= EXTREME_THRESHOLD:
            signal = "暂停操作"
        
        correct = None
        next_pct = df.iloc[i+1]['PctChange']
        if pd.notna(next_pct) and signal != "暂停操作":
            if '加仓' in signal or signal == '轻仓试探':
                correct = next_pct > 0
            elif '减仓' in signal:
                correct = next_pct < 0
            else:
                correct = next_pct >= 0
        
        records.append({
            'index': i,
            'signal': signal,
            'position': position,
            'correct': correct
        })
    
    # 处理最后一天（无次日数据）
    if len(df) > 20:
        i = len(df) - 1
        market_state, volume_state, consecutive, pct_change, rsi, _, _, _ = compute_states(df, i)
        signal, position = decision_logic(market_state, pct_change, rsi, consecutive)
        if abs(pct_change) >= EXTREME_THRESHOLD:
            signal = "暂停操作"
        records.append({
            'index': i,
            'signal': signal,
            'position': position,
            'correct': None
        })
    
    # 构建correct数组，索引对应df的行索引
    correct_series = [None] * len(df)
    record_dict = {}
    for rec in records:
        correct_series[rec['index']] = rec['correct']
        record_dict[rec['index']] = rec
    
    # 计算每个索引的滚动胜率（该索引之前10个交易日）
    win_rates = [None] * len(df)
    for i in range(len(df)):
        if i >= ROLLING_WINDOW:
            window = correct_series[i-ROLLING_WINDOW:i]
            valid = [c for c in window if c is not None]
            if len(valid) == ROLLING_WINDOW:
                win_rates[i] = sum(valid) / ROLLING_WINDOW
            else:
                win_rates[i] = None
        else:
            win_rates[i] = None
    
    # 取最后 history_days 行作为输出
    last_n = min(history_days, len(df))
    start_idx = len(df) - last_n
    history_indices = list(range(start_idx, len(df)))
    history_df = df.iloc[history_indices].copy()
    
    def get_suggestion(idx):
        rec = record_dict.get(idx)
        if rec and rec['signal']:
            return f"{rec['signal']} {rec['position']}".strip()
        return "-"
    
    history_df['建议'] = [get_suggestion(idx) for idx in history_indices]
    history_df['近10日胜率'] = [
        f"{win_rates[idx]*100:.0f}%" if win_rates[idx] is not None else "-"
        for idx in history_indices
    ]
    
    return history_df

# =========================
# 输出日志（包含历史表格）- 手动拼接，保留涨跌符号
# =========================
def print_result(result, history_df=None):
    utc_now = datetime.utcnow()
    beijing_now = utc_now + timedelta(hours=8)
    
    log = "\n==========================\n"
    log += f"{ETF_CODE} ETF操作建议\n"
    log += "==========================\n"
    log += f"时间：{beijing_now.strftime('%Y-%m-%d %H:%M:%S')}\n"
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
    
    # 定义格式化涨跌幅的函数
    def format_pct(x):
        if pd.isna(x):
            return "-"
        if x > 0:
            return f"+{x:.2f}%"
        elif x == 0:
            return "±0.00%"
        else:
            return f"{x:.2f}%"
    
    if history_df is not None and not history_df.empty:
        log += f"\n近{len(history_df)}日数据参考（含历史建议及近10日胜率）：\n"
        # 设置列宽（字符数，中文字符按2个宽度，但这里仅用于等宽字体）
        header = f"{'日期':<11} {'开盘':<6} {'收盘':<6} {'涨跌':<7} {'成交量':<8} {'RSI':<8} {'10日胜率':<5} {'建议':<10} "
        log += header + "\n"
        log += "-" * len(header) + "\n"
        for _, row in history_df.iterrows():
            date = str(row['Date'])[:10]
            open_ = f"{row['Open']:.3f}" if pd.notna(row['Open']) else "-"
            close_ = f"{row['Close']:.3f}" if pd.notna(row['Close']) else "-"
            pct = format_pct(row['PctChange'])
            vol = f"{int(row['Volume']/10000):,}万" if pd.notna(row['Volume']) and row['Volume'] > 0 else "-"
            rsi = f"{row['RSI']:.3f}" if pd.notna(row['RSI']) else "-"
            sugg = row['建议'] if pd.notna(row['建议']) else "-"
            win = row['近10日胜率'] if pd.notna(row['近10日胜率']) else "-"
            log += f"{date:<11} {open_:<6} {close_:<6} {pct:<7} {vol:<8} {rsi:<8} {win:<5} {sugg:<10} \n"
    else:
        # 兼容旧逻辑（输出原10日数据）
        log += "\n近10日数据参考：\n"
        if 'last_10_days' in result and result['last_10_days']:
            df10 = pd.DataFrame(result['last_10_days'])
            header = f"{'日期':<8} {'开盘':<8} {'收盘':<8} {'涨跌':<8} {'成交量':<12} {'RSI':<8}"
            log += header + "\n"
            log += "-" * len(header) + "\n"
            for _, row in df10.iterrows():
                date = str(row['Date'])[:10]
                open_ = f"{row['Open']:.3f}" if pd.notna(row['Open']) else "-"
                close_ = f"{row['Close']:.3f}" if pd.notna(row['Close']) else "-"
                pct = format_pct(row['PctChange'])
                vol = f"{int(row['Volume']/10000):,}万" if pd.notna(row['Volume']) and row['Volume'] > 0 else "-"
                rsi = f"{row['RSI']:.3f}" if pd.notna(row['RSI']) else "-"
                log += f"{date:<20} {open_:<8} {close_:<8} {pct:<8} {vol:<12} {rsi:<8}\n"
        else:
            log += "无历史数据\n"
    
    print(log)
    return log

# =========================
# 主程序
# =========================
def main():
    try:
        df = get_etf_data(ETF_CODE)
        if df is None or df.empty or len(df) < 20:
            raise Exception("数据获取失败或长度不足")

        df = calculate_rsi(df)
        history_df = build_history_with_signals(df, HISTORY_DAYS)
        result = strategy(df)
        log_content = print_result(result, history_df)
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
