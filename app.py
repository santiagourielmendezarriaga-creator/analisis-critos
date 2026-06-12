import streamlit as st
import pandas as pd
import numpy as np
import time
import random
import requests
from datetime import datetime, timezone, timedelta
from collections import deque
import plotly.express as px

st.set_page_config(page_title="Crypto Live (Híbrido)", layout="wide")
st.title("📊 Crypto Live - Datos reales (si disponibles) + Simulación")

# Advertencia
st.warning("""
**⚠️ Nota:** La app intenta obtener datos reales de Binance. Si falla (por bloqueos de red o límites de API), usará datos simulados realistas.
**No es una herramienta para trading real.** Solo fines educativos.
""")

# Telegram
TELEGRAM_TOKEN = "8532857017:AAHwLhRnM3oC6TbgFFKAEmQnZVoo6JD_esQ"
TELEGRAM_CHAT_ID = "5835990242"

CDMX_TZ = timezone(timedelta(hours=-6))

CRYPTOS = {
    "BTC": {"name": "Bitcoin", "symbol": "BTCUSDT", "base": 65000, "volatility": 0.02},
    "ETH": {"name": "Ethereum", "symbol": "ETHUSDT", "base": 3500, "volatility": 0.025},
    "SOL": {"name": "Solana", "symbol": "SOLUSDT", "base": 150, "volatility": 0.03},
    "ADA": {"name": "Cardano", "symbol": "ADAUSDT", "base": 0.45, "volatility": 0.035},
    "DOGE": {"name": "Dogecoin", "symbol": "DOGEUSDT", "base": 0.12, "volatility": 0.04},
    "XRP": {"name": "XRP", "symbol": "XRPUSDT", "base": 0.55, "volatility": 0.03},
}

# Estado de conectividad
if "use_real_data" not in st.session_state:
    st.session_state.use_real_data = True
if "last_api_fail" not in st.session_state:
    st.session_state.last_api_fail = 0

def fetch_binance_price(symbol):
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if "price" in data:
                price = float(data["price"])
                # Cambio 24h
                url24 = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}"
                resp24 = requests.get(url24, timeout=5)
                if resp24.status_code == 200:
                    change = float(resp24.json()["priceChangePercent"])
                    return price, change
        return None, None
    except:
        return None, None

def simulate_price(base, volatility, last_price=None):
    if last_price is None:
        last_price = base
    change_pct = np.random.normal(0, volatility)
    new_price = last_price * (1 + change_pct)
    change_24h = random.uniform(-8, 8)
    return new_price, change_24h

def get_real_or_simulated(sym, info):
    now = time.time()
    # Si ha habido fallo en los últimos 5 minutos, usamos simulación
    if now - st.session_state.last_api_fail < 300:
        st.session_state.use_real_data = False
    else:
        st.session_state.use_real_data = True

    if st.session_state.use_real_data:
        price, change = fetch_binance_price(info["symbol"])
        if price is not None:
            return price, change, "real"
        else:
            st.session_state.last_api_fail = now
            st.session_state.use_real_data = False
            # Si falla, generamos simulado
            price, change = simulate_price(info["base"], info["volatility"], 
                                          st.session_state.current_prices.get(sym, info["base"]))
            return price, change, "sim"
    else:
        price, change = simulate_price(info["base"], info["volatility"],
                                      st.session_state.current_prices.get(sym, info["base"]))
        return price, change, "sim"

def fetch_binance_klines(symbol, limit=48):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1h&limit={limit}"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            ohlc = []
            for candle in data:
                ohlc.append({
                    "timestamp": candle[0],
                    "open": float(candle[1]),
                    "high": float(candle[2]),
                    "low": float(candle[3]),
                    "close": float(candle[4])
                })
            df = pd.DataFrame(ohlc)
            df["datetime"] = pd.to_datetime(df["timestamp"], unit='ms')
            df["hour_cdmx"] = df["datetime"].dt.tz_localize('UTC').dt.tz_convert(CDMX_TZ).dt.hour
            return df
    except:
        pass
    return None

def get_fear_greed():
    if "fg_last_update" in st.session_state and datetime.now().timestamp() - st.session_state.fg_last_update < 3600:
        return st.session_state.fear_greed
    try:
        resp = requests.get("https://api.alternative.me/fng/", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            value = int(data['data'][0]['value'])
            classification = data['data'][0]['value_classification']
            st.session_state.fear_greed = (value, classification)
            st.session_state.fg_last_update = datetime.now().timestamp()
            return value, classification
    except:
        pass
    return 50, "Neutral"

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
        return "🟢 COMPRAR", score, "Fuerte señal alcista (referencia)"
    elif score >= 60:
        return "🟡 CONSIDERAR COMPRA", score, "Señal moderada alcista"
    elif score <= 30:
        return "🔴 VENDER", score, "Fuerte señal bajista"
    elif score <= 40:
        return "🟠 CONSIDERAR VENTA", score, "Señal moderada bajista"
    else:
        return "⚪ MANTENER", score, "Sin tendencia clara"

def get_best_worst_hours(symbol):
    df = fetch_binance_klines(symbol, limit=48)
    if df is None or df.empty:
        # Si no hay datos reales, generamos datos sintéticos para que la funcionalidad no falle
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
if "fear_greed" not in st.session_state:
    st.session_state.fear_greed = (50, "Neutral")

# --- Interfaz ---
st.sidebar.header("⚙️ Configuración")
refresh_interval = st.sidebar.slider("Actualizar cada (segundos)", 60, 180, 90, step=10)
auto_refresh = st.sidebar.checkbox("Auto-refrescar", value=True)
st.sidebar.info("🔒 Modo híbrido: intenta Binance, si falla usa simulación.")

fng_val, fng_label = get_fear_greed()
st.sidebar.metric("😨 Fear & Greed", f"{fng_val}/100", fng_label)

# Indicador de fuente de datos
if st.session_state.use_real_data:
    st.sidebar.success("📡 Usando datos REALES de Binance")
else:
    st.sidebar.warning("⚠️ Usando datos SIMULADOS (fallo en API)")

tab1, tab2, tab3 = st.tabs(["📊 Precios y Señales", "📈 Gráficas", "⏰ Análisis de Horarios"])

with tab1:
    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("📊 Precios (Reales si posible)")
        data_rows = []
        for sym, info in CRYPTOS.items():
            price, change, source = get_real_or_simulated(sym, info)
            st.session_state.current_prices[sym] = price
            data_rows.append({
                "Cripto": info["name"],
                "Precio (USD)": f"${price:,.2f}",
                "24h %": f"{change:+.2f}%",
                "Fuente": "Real" if source == "real" else "Sim"
            })
        df_prices = pd.DataFrame(data_rows)
        st.dataframe(df_prices, use_container_width=True)
        if not st.session_state.use_real_data:
            st.caption("⚠️ Los precios son simulados porque la API de Binance no respondió.")

    with col2:
        st.subheader("📡 Señales (referencia)")
        for sym, info in CRYPTOS.items():
            price = st.session_state.current_prices[sym]
            _, change, _ = get_real_or_simulated(sym, info)  # solo para obtener cambio
            st.session_state.price_history[sym].append(price)
            signal, score, desc = generate_signal(price, change, fng_val, st.session_state.price_history[sym])
            if signal != st.session_state.last_signals[sym] and ("COMPRAR" in signal or "VENDER" in signal):
                alert = f"🚨 *{info['name']}* 🚨\n{signal}\n💰 ${price:,.2f}\n📈 24h: {change:+.2f}%\n😨 Fear: {fng_val}/100\n🎯 Score: {score}/100"
                send_telegram(alert)
                st.session_state.last_signals[sym] = signal
            st.metric(info["name"], f"${price:,.2f}", f"{change:+.2f}%")
            st.write(f"**{signal}** (Score: {score}/100)")
            st.caption(desc)
            st.markdown("---")

with tab2:
    selected_sym = st.selectbox("Selecciona cripto", list(CRYPTOS.keys()), format_func=lambda x: CRYPTOS[x]["name"])
    # Intentar obtener datos reales para gráfica
    symbol = CRYPTOS[selected_sym]["symbol"]
    df_hist = fetch_binance_klines(symbol, limit=72)
    if df_hist is not None and not df_hist.empty:
        fig = px.line(df_hist, x="datetime", y="close", title=f"{CRYPTOS[selected_sym]['name']} - Precio horario (Binance)")
        st.plotly_chart(fig, use_container_width=True)
    else:
        # Generar datos sintéticos para la gráfica
        hours = 72
        now = datetime.now().replace(minute=0, second=0, microsecond=0)
        times = [now - timedelta(hours=i) for i in range(hours)]
        prices = [CRYPTOS[selected_sym]["base"] * (1 + np.random.normal(0, 0.02)) for _ in range(hours)]
        df_sim = pd.DataFrame({"datetime": times, "close": prices})
        df_sim = df_sim.sort_values("datetime")
        fig = px.line(df_sim, x="datetime", y="close", title=f"{CRYPTOS[selected_sym]['name']} - Precio simulado (sin datos reales)")
        st.plotly_chart(fig, use_container_width=True)
        st.caption("⚠️ Datos simulados: la API de Binance no proporcionó datos históricos.")

with tab3:
    st.subheader("⏰ Mejores y Peores Horas del Día (CDMX)")
    st.caption("Basado en velas reales de Binance (si están disponibles).")
    if st.button("🔄 Actualizar análisis ahora"):
        st.cache_data.clear()
        st.rerun()
    for sym, info in CRYPTOS.items():
        best, worst = get_best_worst_hours(info["symbol"])
        if best is not None and not best.empty:
            st.markdown(f"### {info['name']}")
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("🟢 **Mejores horas para COMPRAR** (histórico)")
                for hour, row in best.iterrows():
                    st.write(f"⏰ {int(hour):02d}:00 → +{row['mean']:.2f}%")
            with col_b:
                st.markdown("🔴 **Peores horas para VENDER** (histórico)")
                for hour, row in worst.iterrows():
                    st.write(f"⏰ {int(hour):02d}:00 → {row['mean']:.2f}%")
            st.markdown("---")
        else:
            st.write(f"⚠️ {info['name']}: No hay suficientes datos reales. Se necesita al menos 48h de velas.")

# Reporte automático cada 8 horas (Telegram)
now_ts = datetime.now().timestamp()
if now_ts - st.session_state.last_report_time >= 8 * 3600:
    st.session_state.last_report_time = now_ts
    report_lines = ["📊 *REPORTE DE HORARIOS*", ""]
    for sym, info in CRYPTOS.items():
        best, worst = get_best_worst_hours(info["symbol"])
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
