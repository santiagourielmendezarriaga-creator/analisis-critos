import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timezone, timedelta
import time
import numpy as np
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from collections import deque
import random

# ==================== CONFIGURACIÓN GLOBAL ====================
st.set_page_config(page_title="Crypto Analyst 5min", layout="wide", page_icon="📈")
st.title("📊 Crypto Analyst - Trading Signals (Actualización cada 5 minutos)")

# Telegram (cambia por tus datos)
TELEGRAM_TOKEN = "8532857017:AAHwLhRnM3oC6TbgFFKAEmQnZVoo6JD_esQ"
TELEGRAM_CHAT_ID = "5835990242"

# Zona horaria Ciudad de México
CDMX_TZ = timezone(timedelta(hours=-6))

# Lista de criptomonedas (solo 3 para minimizar peticiones)
CRYPTOS = {
    "bitcoin": {"name": "Bitcoin", "symbol": "BTC"},
    "ethereum": {"name": "Ethereum", "symbol": "ETH"},
    "solana": {"name": "Solana", "symbol": "SOL"},
}

# Configuración de reintentos y límite de tasa
RETRY_ATTEMPTS = 2
BASE_DELAY = 5       # segundos
MAX_DELAY = 30
MAX_REQUESTS_PER_5MIN = 10   # máximo 10 peticiones cada 5 minutos (2 por minuto)
REQUEST_HISTORY = deque(maxlen=MAX_REQUESTS_PER_5MIN)
REQUEST_WINDOW = 300  # 5 minutos en segundos

def rate_limit_wait():
    """Espera si hemos superado el límite de peticiones en la ventana de 5 minutos"""
    now = time.time()
    # Limpiar entradas más antiguas que la ventana
    while REQUEST_HISTORY and (now - REQUEST_HISTORY[0]) > REQUEST_WINDOW:
        REQUEST_HISTORY.popleft()
    if len(REQUEST_HISTORY) >= MAX_REQUESTS_PER_5MIN:
        oldest = REQUEST_HISTORY[0]
        wait_time = REQUEST_WINDOW - (now - oldest) + random.uniform(1, 3)
        time.sleep(wait_time)
    REQUEST_HISTORY.append(now)

@retry(stop=stop_after_attempt(RETRY_ATTEMPTS),
       wait=wait_exponential(multiplier=BASE_DELAY, min=BASE_DELAY, max=MAX_DELAY))
def safe_get(url, params=None, timeout=20):
    """Realiza petición GET con reintentos y respeto de tasa"""
    rate_limit_wait()
    try:
        response = requests.get(url, params=params, timeout=timeout)
        if response.status_code == 429:
            time.sleep(15)
            raise requests.exceptions.RequestException("429 Too Many Requests")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.warning(f"Error: {e}. Reintentando...")
        raise

def get_current_price(crypto_id):
    """Obtiene precio actual y cambio 24h"""
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={crypto_id}&vs_currencies=usd&include_24hr_change=true"
    try:
        data = safe_get(url, timeout=15)
        if crypto_id in data:
            price = data[crypto_id]['usd']
            change = data[crypto_id].get('usd_24h_change', 0.0)
            return price, change
    except:
        pass
    return None, None

def get_fear_greed():
    """Índice de miedo y codicia (cache 1 hora)"""
    if "fg_last_update" in st.session_state and datetime.now().timestamp() - st.session_state.fg_last_update < 3600:
        return st.session_state.fear_greed
    try:
        data = safe_get("https://api.alternative.me/fng/", timeout=10)
        value = int(data['data'][0]['value'])
        classification = data['data'][0]['value_classification']
        st.session_state.fear_greed = (value, classification)
        st.session_state.fg_last_update = datetime.now().timestamp()
        return value, classification
    except:
        return 50, "Neutral"

@st.cache_data(ttl=1800, show_spinner=False)  # 30 minutos de caché
def get_ohlc(crypto_id, days=2):
    url = f"https://api.coingecko.com/api/v3/coins/{crypto_id}/ohlc?vs_currency=usd&days={days}"
    try:
        data = safe_get(url, timeout=15)
        if not data or len(data) < 24:
            return None
        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close'])
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        df['hour_cdmx'] = df['datetime'].dt.tz_localize('UTC').dt.tz_convert(CDMX_TZ).dt.hour
        return df
    except:
        return None

@st.cache_data(ttl=1800, show_spinner=False)
def get_historical_prices(crypto_id, days=7):
    url = f"https://api.coingecko.com/api/v3/coins/{crypto_id}/market_chart?vs_currency=usd&days={days}&interval=daily"
    try:
        data = safe_get(url, timeout=15)
        prices = data['prices']
        df = pd.DataFrame(prices, columns=['timestamp', 'price'])
        df['date'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df[['date', 'price']]
    except:
        return pd.DataFrame()

@st.cache_data(ttl=1800, show_spinner=False)
def get_top_crypto():
    url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=10&sparkline=false"
    try:
        data = safe_get(url, timeout=15)
        df = pd.DataFrame(data)
        df = df[['market_cap_rank', 'name', 'symbol', 'current_price', 'price_change_percentage_24h', 'market_cap', 'total_volume']]
        df.columns = ['Rank', 'Nombre', 'Símbolo', 'Precio (USD)', '24h %', 'Cap. Mercado', 'Volumen 24h']
        df['Precio (USD)'] = df['Precio (USD)'].apply(lambda x: f"${x:,.2f}" if pd.notna(x) else "N/A")
        df['24h %'] = df['24h %'].apply(lambda x: f"{x:+.2f}%" if pd.notna(x) else "N/A")
        df['Cap. Mercado'] = df['Cap. Mercado'].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "N/A")
        df['Volumen 24h'] = df['Volumen 24h'].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "N/A")
        return df
    except:
        return pd.DataFrame()

# ==================== INDICADORES Y SEÑAL ====================
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

def compute_macd(prices, fast=12, slow=26, signal=9):
    if len(prices) < slow + signal:
        return 0, False, False
    ema_fast = pd.Series(prices).ewm(span=fast, adjust=False).mean()
    ema_slow = pd.Series(prices).ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    if len(hist) >= 2:
        cross_up = hist.iloc[-1] > 0 and hist.iloc[-2] <= 0
        cross_down = hist.iloc[-1] < 0 and hist.iloc[-2] >= 0
        return hist.iloc[-1], cross_up, cross_down
    return 0, False, False

def compute_moving_averages(prices, short=7, long=20):
    if len(prices) < long:
        return None, None
    return np.mean(prices[-short:]), np.mean(prices[-long:])

def generate_signal(price, change_24h, fng_value, price_history):
    score = 50
    # Fear & Greed (20 pts)
    if fng_value < 25:
        score += 20
    elif fng_value < 40:
        score += 10
    elif fng_value > 75:
        score -= 20
    elif fng_value > 60:
        score -= 10
    # Cambio 24h (12 pts)
    if change_24h > 3:
        score += 12
    elif change_24h > 1:
        score += 6
    elif change_24h < -3:
        score -= 12
    elif change_24h < -1:
        score -= 6
    # RSI (15 pts)
    if len(price_history) >= 20:
        rsi = compute_rsi(list(price_history))
        if rsi < 30:
            score += 15
        elif rsi < 40:
            score += 8
        elif rsi > 70:
            score -= 15
        elif rsi > 60:
            score -= 8
    # MACD (12 pts)
    if len(price_history) >= 34:
        _, cross_up, cross_down = compute_macd(list(price_history))
        if cross_up:
            score += 12
        elif cross_down:
            score -= 12
    # Medias móviles (10 pts)
    short_ma, long_ma = compute_moving_averages(list(price_history))
    if short_ma and long_ma:
        if short_ma > long_ma:
            score += 10
        else:
            score -= 10
    # Tendencia reciente (5 pts)
    if len(price_history) >= 5:
        trend = np.mean(np.diff(list(price_history)[-5:]))
        if trend > 0:
            score += 5
        else:
            score -= 5
    score = max(0, min(100, int(score)))
    if score >= 70:
        return "🟢 COMPRAR", score, "Fuerte señal alcista"
    elif score >= 60:
        return "🟡 CONSIDERAR COMPRA", score, "Señal moderadamente alcista"
    elif score <= 30:
        return "🔴 VENDER", score, "Fuerte señal bajista"
    elif score <= 40:
        return "🟠 CONSIDERAR VENTA", score, "Señal moderadamente bajista"
    else:
        return "⚪ MANTENER", score, "Sin tendencia clara"

def get_best_worst_hours(crypto_id):
    df = get_ohlc(crypto_id, days=2)
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

# ==================== ESTADO DE SESIÓN ====================
if "last_signals" not in st.session_state:
    st.session_state.last_signals = {cid: "" for cid in CRYPTOS}
if "price_history" not in st.session_state:
    st.session_state.price_history = {cid: deque(maxlen=50) for cid in CRYPTOS}
if "last_report_time" not in st.session_state:
    st.session_state.last_report_time = datetime.now().timestamp() - 8*3600
if "fear_greed" not in st.session_state:
    st.session_state.fear_greed = (50, "Neutral")

# ==================== INTERFAZ ====================
def main():
    st.sidebar.header("⚙️ Configuración")
    # Intervalo mínimo 300 segundos, máximo 600 (10 minutos)
    refresh_interval = st.sidebar.slider("Intervalo de actualización (segundos)", 300, 600, 300, step=30)
    auto_refresh = st.sidebar.checkbox("Auto-refrescar", value=True)
    st.sidebar.info("🔒 Actualización cada 5 minutos para evitar bloqueos de API")
    
    fng_val, fng_label = get_fear_greed()
    st.sidebar.metric("😨 Fear & Greed", f"{fng_val}/100", fng_label)
    
    with st.sidebar.expander("📈 Estrategia"):
        st.markdown("""
        - Fear & Greed (20%)
        - Cambio 24h (12%)
        - RSI (15%)
        - MACD (12%)
        - Medias móviles (10%)
        - Tendencia (5%)
        """)
    
    tab1, tab2, tab3 = st.tabs(["📊 Top & Señales", "📈 Gráficos", "⏰ Horarios"])
    
    with tab1:
        col1, col2 = st.columns([2, 1])
        with col1:
            st.subheader("🏆 Top 10 Criptomonedas")
            top_df = get_top_crypto()
            if not top_df.empty:
                st.dataframe(top_df, use_container_width=True, height=450)
            else:
                st.error("No se pudo cargar el top. Reintentando en 5 minutos...")
        with col2:
            st.subheader("📡 Señales en Tiempo Real")
            for crypto_id, info in CRYPTOS.items():
                price, change = get_current_price(crypto_id)
                if price is not None:
                    st.session_state.price_history[crypto_id].append(price)
                    signal, score, desc = generate_signal(price, change, fng_val, st.session_state.price_history[crypto_id])
                    if signal != st.session_state.last_signals[crypto_id] and ("COMPRAR" in signal or "VENDER" in signal):
                        alert_msg = f"🚨 *{info['name']}* 🚨\n{signal}\n💰 ${price:,.2f}\n📈 24h: {change:+.2f}%\n😨 Fear: {fng_val}/100\n🎯 Score: {score}/100"
                        send_telegram(alert_msg)
                        st.session_state.last_signals[crypto_id] = signal
                    st.metric(info['name'], f"${price:,.2f}", f"{change:+.2f}%")
                    st.write(f"**{signal}** (Score: {score}/100)")
                    st.caption(desc)
                else:
                    st.warning(f"{info['name']}: Sin datos (esperando reintento)")
                st.markdown("---")
    
    with tab2:
        selected = st.selectbox("Selecciona criptomoneda", list(CRYPTOS.keys()), format_func=lambda x: CRYPTOS[x]['name'])
        hist_df = get_historical_prices(selected, days=7)
        if not hist_df.empty:
            fig = px.line(hist_df, x='date', y='price', title=f"{CRYPTOS[selected]['name']} - últimos 7 días", markers=True)
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("No hay datos históricos")
    
    with tab3:
        st.subheader("⏰ Mejores y Peores Horas del Día (CDMX)")
        if st.button("🔄 Actualizar horarios ahora"):
            st.cache_data.clear()
            st.rerun()
        for crypto_id, info in CRYPTOS.items():
            best, worst = get_best_worst_hours(crypto_id)
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
    
    # Reporte automático cada 8 horas
    now_ts = datetime.now().timestamp()
    if now_ts - st.session_state.last_report_time >= 8 * 3600:
        st.session_state.last_report_time = now_ts
        report_lines = ["📊 *REPORTE DE HORARIOS*", ""]
        for crypto_id, info in CRYPTOS.items():
            best, worst = get_best_worst_hours(crypto_id)
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
