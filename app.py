import streamlit as st
import pandas as pd
import numpy as np
import time
import random
import requests
from datetime import datetime, timedelta, timezone
from collections import deque
import plotly.express as px

st.set_page_config(page_title="Crypto Simulator Pro", layout="wide")
st.title("📊 Crypto Analyst - Modo Simulado (estable)")

# Telegram (opcional – cambia por tus datos si quieres alertas reales)
TELEGRAM_TOKEN = "8532857017:AAHwLhRnM3oC6TbgFFKAEmQnZVoo6JD_esQ"
TELEGRAM_CHAT_ID = "5835990242"

CDMX_TZ = timezone(timedelta(hours=-6))

CRYPTOS = {
    "BTC": {"name": "Bitcoin", "base": 65000, "volatilidad": 0.02},
    "ETH": {"name": "Ethereum", "base": 3500, "volatilidad": 0.025},
    "SOL": {"name": "Solana", "base": 150, "volatilidad": 0.03},
    "ADA": {"name": "Cardano", "base": 0.45, "volatilidad": 0.035},
    "DOGE": {"name": "Dogecoin", "base": 0.12, "volatilidad": 0.04},
    "XRP": {"name": "XRP", "base": 0.55, "volatilidad": 0.03},
}

def generate_price(base, volatility, last_price=None):
    if last_price is None:
        last_price = base
    change_pct = np.random.normal(0, volatility)
    new_price = last_price * (1 + change_pct)
    return new_price, change_pct * 100

def generate_24h_change():
    return random.uniform(-8, 8)

def generate_fear_greed():
    if "fg_value" not in st.session_state:
        st.session_state.fg_value = 50
    st.session_state.fg_value += random.uniform(-5, 5)
    st.session_state.fg_value = max(0, min(100, st.session_state.fg_value))
    if st.session_state.fg_value < 25:
        label = "Extreme Fear"
    elif st.session_state.fg_value < 40:
        label = "Fear"
    elif st.session_state.fg_value < 60:
        label = "Neutral"
    elif st.session_state.fg_value < 75:
        label = "Greed"
    else:
        label = "Extreme Greed"
    return int(st.session_state.fg_value), label

def generate_ohlc(symbol, days=2):
    info = CRYPTOS[symbol]
    base = info["base"]
    volatility = info["volatilidad"]
    hours = days * 24
    timestamps = []
    opens = []
    highs = []
    lows = []
    closes = []
    price = base
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    for i in range(hours):
        ts = now - timedelta(hours=hours-i)
        timestamps.append(ts)
        open_price = price
        change = np.random.normal(0, volatility/2)
        close_price = open_price * (1 + change)
        high = max(open_price, close_price) * (1 + abs(np.random.normal(0, volatility/4)))
        low = min(open_price, close_price) * (1 - abs(np.random.normal(0, volatility/4)))
        opens.append(open_price)
        closes.append(close_price)
        highs.append(high)
        lows.append(low)
        price = close_price
    df = pd.DataFrame({
        "timestamp": timestamps,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes
    })
    df["datetime"] = df["timestamp"]
    df["hour_cdmx"] = df["timestamp"].dt.tz_localize('UTC').dt.tz_convert(CDMX_TZ).dt.hour
    return df

def compute_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50
    deltas = np.diff(prices[-period-1:])
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def generate_signal(price, change_24h, fng_value, price_history):
    score = 50
    if fng_value < 25:
        score += 20
    elif fng_value < 40:
        score += 10
    elif fng_value > 75:
        score -= 20
    elif fng_value > 60:
        score -= 10
    if change_24h > 3:
        score += 12
    elif change_24h > 1:
        score += 6
    elif change_24h < -3:
        score -= 12
    elif change_24h < -1:
        score -= 6
    if len(price_history) >= 14:
        rsi = compute_rsi(list(price_history))
        if rsi < 30:
            score += 15
        elif rsi < 40:
            score += 8
        elif rsi > 70:
            score -= 15
        elif rsi > 60:
            score -= 8
    if len(price_history) >= 5:
        trend = np.mean(np.diff(list(price_history)[-5:]))
        if trend > 0:
            score += 10
        else:
            score -= 10
    score = max(0, min(100, int(score)))
    if score >= 70:
        return "🟢 COMPRAR", score, "Fuerte señal alcista"
    elif score >= 60:
        return "🟡 CONSIDERAR COMPRA", score, "Señal moderada alcista"
    elif score <= 30:
        return "🔴 VENDER", score, "Fuerte señal bajista"
    elif score <= 40:
        return "🟠 CONSIDERAR VENTA", score, "Señal moderada bajista"
    else:
        return "⚪ MANTENER", score, "Sin tendencia clara"

def get_best_worst_hours(symbol):
    df = generate_ohlc(symbol, days=2)
    if df is None or df.empty:
        return None, None
    df['change'] = (df['close'] - df['open']) / df['open'] * 100
    hourly = df.groupby('hour_cdmx')['change'].agg(['mean', 'count'])
    hourly = hourly[hourly['count'] >= 2]
    if hourly.empty:
        return None, None
    hourly_sorted = hourly.sort_values('mean', ascending=False)
    return hourly_sorted.head(3), hourly_sorted.tail(3)

def send_telegram(message):
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}, timeout=5)
        except:
            pass

# --- Estado de sesión ---
if "last_signals" not in st.session_state:
    st.session_state.last_signals = {sym: "" for sym in CRYPTOS}
if "price_history" not in st.session_state:
    st.session_state.price_history = {sym: deque(maxlen=50) for sym in CRYPTOS}
if "last_report_time" not in st.session_state:
    st.session_state.last_report_time = datetime.now().timestamp() - 8*3600
if "current_prices" not in st.session_state:
    st.session_state.current_prices = {sym: CRYPTOS[sym]["base"] for sym in CRYPTOS}

# --- Interfaz ---
st.sidebar.header("⚙️ Configuración")
refresh_interval = st.sidebar.slider("Actualizar cada (segundos)", 5, 30, 10)
auto_refresh = st.sidebar.checkbox("Auto-refrescar", value=True)
st.sidebar.warning("⚠️ Modo simulado - datos sintéticos. No requiere internet.")

fng_val, fng_label = generate_fear_greed()
st.sidebar.metric("😨 Fear & Greed (sim)", f"{fng_val}/100", fng_label)

tab1, tab2, tab3 = st.tabs(["📊 Precios y Señales", "📈 Gráficas", "⏰ Análisis de Horarios"])

with tab1:
    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("📊 Precios en tiempo real (simulados)")
        data_rows = []
        for sym, info in CRYPTOS.items():
            last_price = st.session_state.current_prices[sym]
            new_price, _ = generate_price(info["base"], info["volatilidad"], last_price)
            st.session_state.current_prices[sym] = new_price
            change_24h = generate_24h_change()
            data_rows.append({
                "Cripto": info["name"],
                "Precio (USD)": f"${new_price:,.2f}",
                "24h %": f"{change_24h:+.2f}%"
            })
        df_prices = pd.DataFrame(data_rows)
        st.dataframe(df_prices, use_container_width=True)

    with col2:
        st.subheader("📡 Señales en Tiempo Real")
        for sym, info in CRYPTOS.items():
            price = st.session_state.current_prices[sym]
            change_24h = generate_24h_change()
            st.session_state.price_history[sym].append(price)
            signal, score, desc = generate_signal(price, change_24h, fng_val, st.session_state.price_history[sym])
            if signal != st.session_state.last_signals[sym] and ("COMPRAR" in signal or "VENDER" in signal):
                alert = f"🚨 *{info['name']}* 🚨\n{signal}\n💰 ${price:,.2f}\n📈 24h: {change_24h:+.2f}%\n😨 Fear: {fng_val}/100\n🎯 Score: {score}/100"
                send_telegram(alert)
                st.session_state.last_signals[sym] = signal
            st.metric(info["name"], f"${price:,.2f}", f"{change_24h:+.2f}%")
            st.write(f"**{signal}** (Score: {score}/100)")
            st.caption(desc)
            st.markdown("---")

with tab2:
    selected_sym = st.selectbox("Selecciona criptomoneda", list(CRYPTOS.keys()), format_func=lambda x: CRYPTOS[x]["name"])
    df_hist = generate_ohlc(selected_sym, days=3)   # <--- Aquí se define df_hist
    if df_hist is not None and not df_hist.empty:
        fig = px.line(df_hist, x="datetime", y="close", title=f"{CRYPTOS[selected_sym]['name']} - Precio horario simulado")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No se pudieron generar datos históricos.")

with tab3:
    st.subheader("⏰ Mejores y Peores Horas del Día (CDMX) - Datos simulados")
    if st.button("🔄 Actualizar horarios ahora"):
        st.cache_data.clear()
        st.rerun()
    for sym, info in CRYPTOS.items():
        best, worst = get_best_worst_hours(sym)
        if best is not None and not best.empty:
            st.markdown(f"### {info['name']}")
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("🟢 **Mejores horas para COMPRAR**")
                for hour, row in best.iterrows():
                    st.write(f"⏰ {int(hour):02d}:00 → +{row['mean']:.2f}%")
            with col_b:
                st.markdown("🔴 **Peores horas para VENDER**")
                for hour, row in worst.iterrows():
                    st.write(f"⏰ {int(hour):02d}:00 → {row['mean']:.2f}%")
            st.markdown("---")
        else:
            st.write(f"⚠️ {info['name']}: Datos insuficientes")

# --- Reporte automático cada 8 horas (Telegram) ---
now_ts = datetime.now().timestamp()
if now_ts - st.session_state.last_report_time >= 8 * 3600:
    st.session_state.last_report_time = now_ts
    report_lines = ["📊 *REPORTE DE HORARIOS* (simulado)", ""]
    for sym, info in CRYPTOS.items():
        best, worst = get_best_worst_hours(sym)
        if best is not None and not best.empty:
            report_lines.append(f"*{info['name']}*")
            report_lines.append("🟢 Mejores: " + ", ".join([f"{int(h):02d}:00 ({row['mean']:+.2f}%)" for h, row in best.iterrows()]))
            report_lines.append("🔴 Peores: " + ", ".join([f"{int(h):02d}:00 ({row['mean']:+.2f}%)" for h, row in worst.iterrows()]))
            report_lines.append("")
    if len(report_lines) > 2:
        send_telegram("\n".join(report_lines))

if auto_refresh:
    time.sleep(refresh_interval)
    st.rerun()
