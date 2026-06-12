import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import time
import numpy as np
from datetime import datetime, timezone, timedelta
from collections import deque

# ==================== CONFIGURACIÓN ====================
st.set_page_config(page_title="Crypto Binance Pro", layout="wide")
st.title("📊 Crypto Analyst - Binance API + Alertas Telegram + Horarios")

# --- Telegram (cambia por tus datos) ---
TELEGRAM_TOKEN = "8532857017:AAHwLhRnM3oC6TbgFFKAEmQnZVoo6JD_esQ"
TELEGRAM_CHAT_ID = "5835990242"

# --- Zona horaria CDMX ---
CDMX_TZ = timezone(timedelta(hours=-6))

# --- Pares de Binance ---
BINANCE_PAIRS = {
    "bitcoin": {"name": "Bitcoin", "symbol": "BTC", "pair": "BTCUSDT"},
    "ethereum": {"name": "Ethereum", "symbol": "ETH", "pair": "ETHUSDT"},
    "solana": {"name": "Solana", "symbol": "SOL", "pair": "SOLUSDT"},
    "cardano": {"name": "Cardano", "symbol": "ADA", "pair": "ADAUSDT"},
    "dogecoin": {"name": "Dogecoin", "symbol": "DOGE", "pair": "DOGEUSDT"},
    "ripple": {"name": "XRP", "symbol": "XRP", "pair": "XRPUSDT"},
}

# ==================== FUNCIONES BINANCE ====================
def get_binance_price(symbol_pair):
    """Obtiene precio actual y cambio 24h"""
    try:
        url_price = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol_pair}"
        resp_price = requests.get(url_price, timeout=10)
        price = float(resp_price.json()["price"])
        url_24h = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol_pair}"
        resp_24h = requests.get(url_24h, timeout=10)
        change = float(resp_24h.json()["priceChangePercent"])
        return price, change
    except:
        return None, None

def get_binance_klines(symbol_pair, interval="1h", limit=48):
    """Obtiene velas horarias (últimas 48h) para análisis de horarios"""
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol_pair}&interval={interval}&limit={limit}"
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
    except:
        return None

# ==================== FEAR & GREED (cada hora) ====================
def get_fear_greed():
    if "fg_last_update" in st.session_state and datetime.now().timestamp() - st.session_state.fg_last_update < 3600:
        return st.session_state.fear_greed
    try:
        resp = requests.get("https://api.alternative.me/fng/", timeout=10)
        data = resp.json()
        value = int(data['data'][0]['value'])
        classification = data['data'][0]['value_classification']
        st.session_state.fear_greed = (value, classification)
        st.session_state.fg_last_update = datetime.now().timestamp()
        return value, classification
    except:
        return 50, "Neutral"

# ==================== INDICADORES TÉCNICOS ====================
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

# ==================== HORARIOS ÓPTIMOS ====================
def get_best_worst_hours(crypto_id):
    pair = BINANCE_PAIRS[crypto_id]["pair"]
    df = get_binance_klines(pair, limit=48)
    if df is None or df.empty:
        return None, None
    df['change'] = (df['close'] - df['open']) / df['open'] * 100
    hourly = df.groupby('hour_cdmx')['change'].agg(['mean', 'count'])
    hourly = hourly[hourly['count'] >= 2]  # horas con al menos 2 ocurrencias
    if hourly.empty:
        return None, None
    hourly_sorted = hourly.sort_values('mean', ascending=False)
    best = hourly_sorted.head(3)
    worst = hourly_sorted.tail(3)
    return best, worst

# ==================== TELEGRAM ====================
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}, timeout=5)
    except:
        pass

# ==================== ESTADO DE SESIÓN ====================
if "last_signals" not in st.session_state:
    st.session_state.last_signals = {cid: "" for cid in BINANCE_PAIRS}
if "price_history" not in st.session_state:
    st.session_state.price_history = {cid: deque(maxlen=50) for cid in BINANCE_PAIRS}
if "last_report_time" not in st.session_state:
    st.session_state.last_report_time = datetime.now().timestamp() - 8*3600
if "fear_greed" not in st.session_state:
    st.session_state.fear_greed = (50, "Neutral")

# ==================== INTERFAZ ====================
def main():
    st.sidebar.header("⚙️ Configuración")
    refresh_interval = st.sidebar.slider("Actualizar cada (segundos)", 30, 180, 60)
    auto_refresh = st.sidebar.checkbox("Auto-refrescar", value=True)
    st.sidebar.success("✅ Usando API de Binance (sin límites estrictos)")
    st.sidebar.info("🔔 Alertas Telegram: se enviarán cuando la señal cambie a COMPRAR o VENDER")

    fng_val, fng_label = get_fear_greed()
    st.sidebar.metric("😨 Fear & Greed", f"{fng_val}/100", fng_label)

    # Tabs
    tab1, tab2, tab3 = st.tabs(["📊 Precios y Señales", "📈 Gráficas", "⏰ Análisis de Horarios"])

    with tab1:
        col1, col2 = st.columns([2, 1])
        with col1:
            st.subheader("📊 Precios en tiempo real (Binance)")
            data_rows = []
            for cid, info in BINANCE_PAIRS.items():
                price, change = get_binance_price(info["pair"])
                if price:
                    data_rows.append({
                        "Cripto": info["name"],
                        "Precio (USD)": f"${price:,.2f}",
                        "24h %": f"{change:+.2f}%"
                    })
            if data_rows:
                df_prices = pd.DataFrame(data_rows)
                st.dataframe(df_prices, use_container_width=True)
            else:
                st.warning("No se pudieron obtener precios. Verifica tu conexión.")

        with col2:
            st.subheader("📡 Señales en Tiempo Real")
            for cid, info in BINANCE_PAIRS.items():
                price, change = get_binance_price(info["pair"])
                if price:
                    st.session_state.price_history[cid].append(price)
                    signal, score, desc = generate_signal(price, change, fng_val, st.session_state.price_history[cid])
                    # Enviar alerta solo si cambia a COMPRAR o VENDER
                    if signal != st.session_state.last_signals[cid] and ("COMPRAR" in signal or "VENDER" in signal):
                        alert = f"🚨 *{info['name']}* 🚨\n{signal}\n💰 ${price:,.2f}\n📈 24h: {change:+.2f}%\n😨 Fear: {fng_val}/100\n🎯 Score: {score}/100"
                        send_telegram(alert)
                        st.session_state.last_signals[cid] = signal
                    st.metric(info["name"], f"${price:,.2f}", f"{change:+.2f}%")
                    st.write(f"**{signal}** (Score: {score}/100)")
                    st.caption(desc)
                else:
                    st.warning(f"{info['name']}: Sin datos")
                st.markdown("---")

    with tab2:
        selected = st.selectbox("Selecciona criptomoneda", list(BINANCE_PAIRS.keys()), format_func=lambda x: BINANCE_PAIRS[x]["name"])
        pair = BINANCE_PAIRS[selected]["pair"]
        df_klines = get_binance_klines(pair, limit=72)  # 72 horas (3 días)
        if df_klines is not None and not df_klines.empty:
            fig = px.line(df_klines, x="datetime", y="close", title=f"{BINANCE_PAIRS[selected]['name']} - Precio horario (últimas 72h)")
            fig.update_layout(height=400, hovermode='x unified')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No se pudieron cargar las velas horarias.")

    with tab3:
        st.subheader("⏰ Mejores y Peores Horas del Día (CDMX)")
        st.caption("Basado en datos de las últimas 48 horas. Horas con ganancia promedio positiva = buenas para COMPRAR.")
        if st.button("🔄 Actualizar análisis de horarios ahora"):
            st.cache_data.clear()
            st.rerun()
        for cid, info in BINANCE_PAIRS.items():
            best, worst = get_best_worst_hours(cid)
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
                st.write(f"⚠️ {info['name']}: Datos insuficientes para análisis horario")

    # Reporte automático cada 8 horas (telegram)
    now_ts = datetime.now().timestamp()
    if now_ts - st.session_state.last_report_time >= 8 * 3600:
        st.session_state.last_report_time = now_ts
        report_lines = ["📊 *REPORTE DE HORARIOS* (últimas 48h)", ""]
        for cid, info in BINANCE_PAIRS.items():
            best, worst = get_best_worst_hours(cid)
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

if __name__ == "__main__":
    main()
