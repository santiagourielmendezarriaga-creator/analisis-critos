import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import time
import numpy as np
from datetime import datetime, timezone, timedelta
from collections import deque

st.set_page_config(page_title="Crypto Live Pro", layout="wide")
st.title("📊 Crypto Analyst - API Cryptocompare (estable y gratis)")

# Telegram (cambia por tus datos)
TELEGRAM_TOKEN = "8532857017:AAHwLhRnM3oC6TbgFFKAEmQnZVoo6JD_esQ"
TELEGRAM_CHAT_ID = "5835990242"

CDMX_TZ = timezone(timedelta(hours=-6))

# Lista de monedas y símbolos para Cryptocompare
CRYPTO_LIST = {
    "BTC": "Bitcoin",
    "ETH": "Ethereum",
    "SOL": "Solana",
    "ADA": "Cardano",
    "DOGE": "Dogecoin",
    "XRP": "XRP"
}

def get_cryptocompare_price(symbol):
    """Obtiene precio actual y cambio 24h desde Cryptocompare"""
    try:
        # Precio actual
        url_price = f"https://min-api.cryptocompare.com/data/price?fsym={symbol}&tsyms=USD"
        resp_price = requests.get(url_price, timeout=10)
        price = float(resp_price.json()["USD"])
        # Cambio 24h
        url_change = f"https://min-api.cryptocompare.com/data/pricemultifull?fsyms={symbol}&tsyms=USD"
        resp_change = requests.get(url_change, timeout=10)
        data = resp_change.json()
        change = data["RAW"][symbol]["USD"]["CHANGEPCT24HOUR"]
        return price, change
    except Exception as e:
        print(f"Error Cryptocompare: {e}")
        return None, None

def get_cryptocompare_histo(symbol, limit=48, aggregate=1):
    """Obtiene datos históricos horarios (últimas 48 horas)"""
    try:
        url = f"https://min-api.cryptocompare.com/data/v2/histohour?fsym={symbol}&tsym=USD&limit={limit}&aggregate={aggregate}"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data["Response"] != "Success":
            return None
        ohlc = []
        for item in data["Data"]["Data"]:
            ohlc.append({
                "timestamp": item["time"],
                "open": item["open"],
                "high": item["high"],
                "low": item["low"],
                "close": item["close"]
            })
        df = pd.DataFrame(ohlc)
        df["datetime"] = pd.to_datetime(df["timestamp"], unit='s')
        df["hour_cdmx"] = df["datetime"].dt.tz_localize('UTC').dt.tz_convert(CDMX_TZ).dt.hour
        return df
    except:
        return None

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
    df = get_cryptocompare_histo(symbol, limit=48)
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
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}, timeout=5)
    except:
        pass

# Estado
if "last_signals" not in st.session_state:
    st.session_state.last_signals = {sym: "" for sym in CRYPTO_LIST}
if "price_history" not in st.session_state:
    st.session_state.price_history = {sym: deque(maxlen=50) for sym in CRYPTO_LIST}
if "last_report_time" not in st.session_state:
    st.session_state.last_report_time = datetime.now().timestamp() - 8*3600
if "fear_greed" not in st.session_state:
    st.session_state.fear_greed = (50, "Neutral")

def main():
    st.sidebar.header("⚙️ Configuración")
    refresh_interval = st.sidebar.slider("Actualizar cada (segundos)", 30, 180, 60)
    auto_refresh = st.sidebar.checkbox("Auto-refrescar", value=True)
    st.sidebar.success("✅ Usando API de Cryptocompare (estable y sin bloqueos)")

    fng_val, fng_label = get_fear_greed()
    st.sidebar.metric("😨 Fear & Greed", f"{fng_val}/100", fng_label)

    tab1, tab2, tab3 = st.tabs(["📊 Precios y Señales", "📈 Gráficas", "⏰ Análisis de Horarios"])

    with tab1:
        col1, col2 = st.columns([2, 1])
        with col1:
            st.subheader("📊 Precios en tiempo real (Cryptocompare)")
            data_rows = []
            for sym, name in CRYPTO_LIST.items():
                price, change = get_cryptocompare_price(sym)
                if price:
                    data_rows.append({
                        "Cripto": name,
                        "Precio (USD)": f"${price:,.2f}",
                        "24h %": f"{change:+.2f}%"
                    })
            if data_rows:
                st.dataframe(pd.DataFrame(data_rows), use_container_width=True)
            else:
                st.warning("No se pudieron obtener precios. Revisa tu conexión a internet.")

        with col2:
            st.subheader("📡 Señales en Tiempo Real")
            for sym, name in CRYPTO_LIST.items():
                price, change = get_cryptocompare_price(sym)
                if price:
                    st.session_state.price_history[sym].append(price)
                    signal, score, desc = generate_signal(price, change, fng_val, st.session_state.price_history[sym])
                    if signal != st.session_state.last_signals[sym] and ("COMPRAR" in signal or "VENDER" in signal):
                        alert = f"🚨 *{name}* 🚨\n{signal}\n💰 ${price:,.2f}\n📈 24h: {change:+.2f}%\n😨 Fear: {fng_val}/100\n🎯 Score: {score}/100"
                        send_telegram(alert)
                        st.session_state.last_signals[sym] = signal
                    st.metric(name, f"${price:,.2f}", f"{change:+.2f}%")
                    st.write(f"**{signal}** (Score: {score}/100)")
                    st.caption(desc)
                else:
                    st.warning(f"{name}: Sin datos (verifica internet)")
                st.markdown("---")

    with tab2:
        selected_sym = st.selectbox("Selecciona criptomoneda", list(CRYPTO_LIST.keys()), format_func=lambda x: CRYPTO_LIST[x])
        df_hist = get_cryptocompare_histo(selected_sym, limit=72)
        if df_hist is not None and not df_hist.empty:
            fig = px.line(df_hist, x="datetime", y="close", title=f"{CRYPTO_LIST[selected_sym]} - Precio horario")
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No se pudieron cargar los datos históricos.")

    with tab3:
        st.subheader("⏰ Mejores y Peores Horas del Día (CDMX)")
        if st.button("🔄 Actualizar horarios ahora"):
            st.cache_data.clear()
            st.rerun()
        for sym, name in CRYPTO_LIST.items():
            best, worst = get_best_worst_hours(sym)
            if best is not None and not best.empty:
                st.markdown(f"### {name}")
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
                st.write(f"⚠️ {name}: Datos insuficientes")

    # Reporte automático cada 8 horas a Telegram
    now_ts = datetime.now().timestamp()
    if now_ts - st.session_state.last_report_time >= 8 * 3600:
        st.session_state.last_report_time = now_ts
        report_lines = ["📊 *REPORTE DE HORARIOS* (Cryptocompare)", ""]
        for sym, name in CRYPTO_LIST.items():
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

if __name__ == "__main__":
    main()
