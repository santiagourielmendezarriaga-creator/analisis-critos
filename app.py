import streamlit as st
import pandas as pd
import numpy as np
import time
import requests
from datetime import datetime, timezone, timedelta
from collections import deque
import plotly.express as px

# ==================== CONFIGURACIÓN ====================
st.set_page_config(page_title="Crypto Live (Solo Lectura)", layout="wide")
st.title("📊 Crypto Live - Datos reales de Binance (Solo Lectura)")

# Advertencia de responsabilidad
st.warning("""
**⚠️ ADVERTENCIA IMPORTANTE**  
Esta app muestra datos en tiempo real de Binance con fines **educativos y de simulación**.  
**NO es una herramienta para tomar decisiones de inversión real.**  
Las criptomonedas son volátiles y pueden generar pérdidas.  
Los datos pueden tener latencia y las señales son orientativas.  
""")

# Telegram (cambia por tus datos si quieres alertas)
TELEGRAM_TOKEN = "8532857017:AAHwLhRnM3oC6TbgFFKAEmQnZVoo6JD_esQ"
TELEGRAM_CHAT_ID = "5835990242"

CDMX_TZ = timezone(timedelta(hours=-6))

# Pares de Binance (símbolos reales)
BINANCE_PAIRS = {
    "BTCUSDT": "Bitcoin",
    "ETHUSDT": "Ethereum",
    "SOLUSDT": "Solana",
    "ADAUSDT": "Cardano",
    "DOGEUSDT": "Dogecoin",
    "XRPUSDT": "XRP"
}

# Control de tasa de peticiones (máximo 20 por minuto)
REQUEST_TIMES = deque(maxlen=20)
RATE_LIMIT_WINDOW = 60  # segundos

def rate_limit():
    now = time.time()
    if len(REQUEST_TIMES) == REQUEST_TIMES.maxlen:
        oldest = REQUEST_TIMES[0]
        if now - oldest < RATE_LIMIT_WINDOW:
            sleep_time = RATE_LIMIT_WINDOW - (now - oldest) + 1
            time.sleep(sleep_time)
    REQUEST_TIMES.append(now)

def fetch_binance_price(symbol):
    """Obtiene precio actual y cambio 24h desde Binance pública"""
    try:
        rate_limit()
        url_price = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
        resp_price = requests.get(url_price, timeout=10)
        price = float(resp_price.json()["price"])
        
        rate_limit()
        url_24h = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}"
        resp_24h = requests.get(url_24h, timeout=10)
        change = float(resp_24h.json()["priceChangePercent"])
        return price, change
    except Exception as e:
        st.error(f"Error obteniendo {symbol}: {e}")
        return None, None

def fetch_binance_klines(symbol, interval="1h", limit=48):
    """Obtiene velas horarias para análisis de horarios"""
    try:
        rate_limit()
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        resp = requests.get(url, timeout=10)
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
    except Exception as e:
        st.error(f"Error obteniendo velas de {symbol}: {e}")
        return None

def get_fear_greed():
    """Índice de miedo y codicia (cacheado 1 hora)"""
    if "fg_last_update" in st.session_state and datetime.now().timestamp() - st.session_state.fg_last_update < 3600:
        return st.session_state.fear_greed
    try:
        rate_limit()
        resp = requests.get("https://api.alternative.me/fng/", timeout=10)
        data = resp.json()
        value = int(data['data'][0]['value'])
        classification = data['data'][0]['value_classification']
        st.session_state.fear_greed = (value, classification)
        st.session_state.fg_last_update = datetime.now().timestamp()
        return value, classification
    except:
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
        return "🟢 COMPRAR", score, "Fuerte señal alcista (solo referencia)"
    elif score >= 60:
        return "🟡 CONSIDERAR COMPRA", score, "Señal moderada alcista (solo referencia)"
    elif score <= 30:
        return "🔴 VENDER", score, "Fuerte señal bajista (solo referencia)"
    elif score <= 40:
        return "🟠 CONSIDERAR VENTA", score, "Señal moderada bajista (solo referencia)"
    else:
        return "⚪ MANTENER", score, "Sin tendencia clara"

def get_best_worst_hours(symbol):
    df = fetch_binance_klines(symbol, limit=48)
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
    st.session_state.last_signals = {sym: "" for sym in BINANCE_PAIRS}
if "price_history" not in st.session_state:
    st.session_state.price_history = {sym: deque(maxlen=50) for sym in BINANCE_PAIRS}
if "last_report_time" not in st.session_state:
    st.session_state.last_report_time = datetime.now().timestamp() - 8*3600
if "current_prices" not in st.session_state:
    st.session_state.current_prices = {sym: 0 for sym in BINANCE_PAIRS}

# --- Interfaz ---
st.sidebar.header("⚙️ Configuración")
refresh_interval = st.sidebar.slider("Actualizar cada (segundos)", 60, 180, 90, step=10)
auto_refresh = st.sidebar.checkbox("Auto-refrescar", value=True)
st.sidebar.info("🔒 Actualización lenta (≥60s) para evitar bloqueos de API.")
st.sidebar.warning("📢 Datos reales de Binance. No usar para trading real.")

fng_val, fng_label = get_fear_greed()
st.sidebar.metric("😨 Fear & Greed", f"{fng_val}/100", fng_label)

tab1, tab2, tab3 = st.tabs(["📊 Precios y Señales", "📈 Gráficas", "⏰ Análisis de Horarios"])

with tab1:
    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("📊 Precios en tiempo real (Binance)")
        data_rows = []
        for sym, name in BINANCE_PAIRS.items():
            price, change = fetch_binance_price(sym)
            if price is not None:
                st.session_state.current_prices[sym] = price
                data_rows.append({
                    "Cripto": name,
                    "Precio (USD)": f"${price:,.2f}",
                    "24h %": f"{change:+.2f}%"
                })
            else:
                data_rows.append({
                    "Cripto": name,
                    "Precio (USD)": "Error",
                    "24h %": "Error"
                })
        df_prices = pd.DataFrame(data_rows)
        st.dataframe(df_prices, use_container_width=True)

    with col2:
        st.subheader("📡 Señales (solo referencia)")
        for sym, name in BINANCE_PAIRS.items():
            price = st.session_state.current_prices[sym]
            if price == 0:
                st.warning(f"{name}: Cargando...")
                continue
            # Obtener cambio 24h real para la señal
            _, change = fetch_binance_price(sym)
            if change is None:
                change = 0
            st.session_state.price_history[sym].append(price)
            signal, score, desc = generate_signal(price, change, fng_val, st.session_state.price_history[sym])
            # Alerta solo si cambia a COMPRAR o VENDER
            if signal != st.session_state.last_signals[sym] and ("COMPRAR" in signal or "VENDER" in signal):
                alert = f"🚨 *{name}* 🚨\n{signal}\n💰 ${price:,.2f}\n📈 24h: {change:+.2f}%\n😨 Fear: {fng_val}/100\n🎯 Score: {score}/100\n_{desc}_"
                send_telegram(alert)
                st.session_state.last_signals[sym] = signal
            st.metric(name, f"${price:,.2f}", f"{change:+.2f}%")
            st.write(f"**{signal}** (Score: {score}/100)")
            st.caption(desc)
            st.markdown("---")

with tab2:
    selected_sym = st.selectbox("Selecciona par", list(BINANCE_PAIRS.keys()), format_func=lambda x: BINANCE_PAIRS[x])
    df_hist = fetch_binance_klines(selected_sym, limit=72)
    if df_hist is not None and not df_hist.empty:
        fig = px.line(df_hist, x="datetime", y="close", title=f"{BINANCE_PAIRS[selected_sym]} - Precio horario (Binance)")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No se pudieron cargar datos históricos. Intenta más tarde.")

with tab3:
    st.subheader("⏰ Mejores y Peores Horas del Día (CDMX) - Basado en velas reales de Binance")
    if st.button("🔄 Actualizar análisis ahora"):
        st.cache_data.clear()
        st.rerun()
    for sym, name in BINANCE_PAIRS.items():
        best, worst = get_best_worst_hours(sym)
        if best is not None and not best.empty:
            st.markdown(f"### {name}")
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
            st.write(f"⚠️ {name}: Datos insuficientes (espera 48h de datos)")

# Reporte automático cada 8 horas (Telegram)
now_ts = datetime.now().timestamp()
if now_ts - st.session_state.last_report_time >= 8 * 3600:
    st.session_state.last_report_time = now_ts
    report_lines = ["📊 *REPORTE DE HORARIOS (Binance)*", ""]
    for sym, name in BINANCE_PAIRS.items():
        best, worst = get_best_worst_hours(sym)
        if best is not None and not best.empty:
            report_lines.append(f"*{name}*")
            report_lines.append("🟢 Mejores: " + ", ".join([f"{int(h):02d}:00 ({row['mean']:+.2f}%)" for h, row in best.iterrows()]))
            report_lines.append("🔴 Peores: " + ", ".join([f"{int(h):02d}:00 ({row['mean']:+.2f}%)" for h, row in worst.iterrows()]))
            report_lines.append("")
    if len(report_lines) > 2:
        send_telegram("\n".join(report_lines))

if auto_refresh:
    time.sleep(refresh_interval)
    st.rerun()
