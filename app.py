import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta, timezone
import time
import numpy as np

# ==================== CONFIGURACIÓN ====================
st.set_page_config(page_title="Pro Crypto Analyst", layout="wide", page_icon="📈")
st.title("📊 Pro Crypto Analyst - Señales en Vivo + Horarios Óptimos")

# Telegram config (usa tus datos)
TELEGRAM_TOKEN = "8532857017:AAHwLhRnM3oC6TbgFFKAEmQnZVoo6JD_esQ"
TELEGRAM_CHAT_ID = "5835990242"

# Zona horaria CDMX
ZONA_CDMX = timezone(timedelta(hours=-6))

# Lista de criptomonedas a monitorear (id, nombre, símbolo)
CRYPTOS = {
    "bitcoin": {"name": "Bitcoin", "symbol": "BTC"},
    "ethereum": {"name": "Ethereum", "symbol": "ETH"},
    "solana": {"name": "Solana", "symbol": "SOL"},
    "cardano": {"name": "Cardano", "symbol": "ADA"},
    "dogecoin": {"name": "Dogecoin", "symbol": "DOGE"},
    "ripple": {"name": "XRP", "symbol": "XRP"},
    "polkadot": {"name": "Polkadot", "symbol": "DOT"},
    "avalanche": {"name": "Avalanche", "symbol": "AVAX"}
}

# Inicializar estado de sesión
if "last_signals" not in st.session_state:
    st.session_state.last_signals = {crypto_id: "" for crypto_id in CRYPTOS}
if "price_history" not in st.session_state:
    st.session_state.price_history = {crypto_id: [] for crypto_id in CRYPTOS}
if "last_report" not in st.session_state:
    st.session_state.last_report = datetime.now().timestamp() - 8*3600

# ==================== FUNCIONES DE DATOS ====================
@st.cache_data(ttl=60)
def get_top_crypto():
    """Obtiene top 20 criptomonedas por market cap"""
    url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=20&sparkline=false"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        df = pd.DataFrame(data)
        df = df[['market_cap_rank', 'name', 'symbol', 'current_price', 'price_change_percentage_24h', 'market_cap', 'total_volume']]
        df.columns = ['Rank', 'Nombre', 'Símbolo', 'Precio (USD)', '24h %', 'Cap. Mercado', 'Volumen 24h']
        df['Precio (USD)'] = df['Precio (USD)'].apply(lambda x: f"${x:,.2f}")
        df['24h %'] = df['24h %'].apply(lambda x: f"{x:+.2f}%")
        df['Cap. Mercado'] = df['Cap. Mercado'].apply(lambda x: f"${x:,.0f}")
        df['Volumen 24h'] = df['Volumen 24h'].apply(lambda x: f"${x:,.0f}")
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=120)
def get_ohlc(crypto_id, days=1):
    """Obtiene datos OHLC (horarios) para análisis de horarios"""
    url = f"https://api.coingecko.com/api/v3/coins/{crypto_id}/ohlc?vs_currency=usd&days={days}"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if not data:
            return None
        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close'])
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        df['hour_cdmx'] = df['datetime'].dt.tz_localize('UTC').dt.tz_convert(ZONA_CDMX).dt.hour
        return df
    except:
        return None

@st.cache_data(ttl=60)
def get_historical_prices(crypto_id, days=7):
    """Obtiene precios históricos para gráfica de tendencia"""
    url = f"https://api.coingecko.com/api/v3/coins/{crypto_id}/market_chart?vs_currency=usd&days={days}&interval=daily"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        prices = data['prices']
        df = pd.DataFrame(prices, columns=['timestamp', 'price'])
        df['date'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df[['date', 'price']]
    except:
        return pd.DataFrame()

def get_fear_greed():
    """Obtiene índice de miedo y codicia"""
    try:
        resp = requests.get("https://api.alternative.me/fng/", timeout=10)
        data = resp.json()
        value = int(data['data'][0]['value'])
        classification = data['data'][0]['value_classification']
        return value, classification
    except:
        return 50, "Neutral"

def get_signal(price, change_24h, fng, recent_prices):
    """Calcula señal de compra/venta (0-100)"""
    score = 50
    # Fear & Greed (0-24: miedo extremo -> comprar; 75-100: avaricia -> vender)
    if fng < 25:
        score += 25
    elif fng < 40:
        score += 15
    elif fng > 75:
        score -= 25
    elif fng > 60:
        score -= 15
    # Cambio 24h
    if change_24h > 3:
        score += 10
    elif change_24h > 1:
        score += 5
    elif change_24h < -3:
        score -= 10
    elif change_24h < -1:
        score -= 5
    # Tendencia reciente (últimos 5 precios)
    if len(recent_prices) >= 5:
        avg = sum(recent_prices[-5:]) / 5
        if price > avg:
            score += 10
        else:
            score -= 10
    score = max(0, min(100, score))
    if score >= 65:
        return "🟢 COMPRAR", score
    elif score >= 55:
        return "🟡 CONSIDERAR COMPRA", score
    elif score <= 35:
        return "🔴 VENDER", score
    elif score <= 45:
        return "🟠 CONSIDERAR VENTA", score
    else:
        return "⚪ MANTENER", score

def best_worst_hours(df, crypto_name):
    """Calcula las mejores y peores horas del día"""
    if df is None or df.empty:
        return None, None
    df['change'] = (df['close'] - df['open']) / df['open'] * 100
    hourly = df.groupby('hour_cdmx')['change'].mean().sort_values(ascending=False)
    best = hourly.head(3)
    worst = hourly.tail(3)
    return best, worst

def send_telegram_alert(message):
    """Envía alerta a Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}, timeout=5)
    except:
        pass

# ==================== INTERFAZ PRINCIPAL ====================
# Sidebar
st.sidebar.header("⚙️ Configuración")
interval = st.sidebar.slider("Actualizar cada (segundos)", 15, 120, 30)
auto_refresh = st.sidebar.checkbox("Auto-refrescar", value=True)
st.sidebar.markdown("---")
st.sidebar.subheader("📊 Indicadores en vivo")
fng_value, fng_label = get_fear_greed()
st.sidebar.metric("Fear & Greed", f"{fng_value}/100", fng_label)
st.sidebar.info("🟢 COMPRAR: Fear bajo + cambio positivo + tendencia alcista\n🔴 VENDER: Fear alto + cambio negativo + tendencia bajista")

# Selección de cripto para gráfica detallada
selected_crypto = st.sidebar.selectbox("🔍 Selecciona criptomoneda para gráfico", list(CRYPTOS.keys()), format_func=lambda x: CRYPTOS[x]['name'])

# ==================== COLUMNAS PRINCIPALES ====================
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("🏆 TOP 20 Criptomonedas en Vivo")
    top_df = get_top_crypto()
    if not top_df.empty:
        st.dataframe(top_df, use_container_width=True, height=400)
    else:
        st.warning("No se pudo cargar el top de criptomonedas")

    st.subheader(f"📈 Gráfica de Precio - {CRYPTOS[selected_crypto]['name']} (últimos 7 días)")
    hist_df = get_historical_prices(selected_crypto, days=7)
    if not hist_df.empty:
        fig = px.line(hist_df, x='date', y='price', title=f"Tendencia de {CRYPTOS[selected_crypto]['name']}", 
                      labels={'price': 'Precio USD', 'date': 'Fecha'}, markers=True)
        fig.update_layout(height=400, hovermode='x unified')
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No se pudieron cargar los datos históricos")

with col2:
    st.subheader("📊 Señales en Tiempo Real")
    # Mostrar señales para todas las criptomonedas
    fng, _ = get_fear_greed()
    signals_data = []
    for crypto_id, info in CRYPTOS.items():
        price, change = None, None
        try:
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={crypto_id}&vs_currencies=usd&include_24hr_change=true"
            resp = requests.get(url, timeout=5)
            data = resp.json()
            if crypto_id in data:
                price = data[crypto_id]['usd']
                change = data[crypto_id].get('usd_24h_change', 0)
        except:
            pass
        if price:
            st.session_state.price_history[crypto_id].append(price)
            if len(st.session_state.price_history[crypto_id]) > 30:
                st.session_state.price_history[crypto_id] = st.session_state.price_history[crypto_id][-30:]
            signal, score = get_signal(price, change, fng, st.session_state.price_history[crypto_id])
            st.metric(info['name'], f"${price:,.2f}", f"{change:+.2f}%")
            st.write(f"**{signal}** (Score: {score}/100)")
            signals_data.append((info['name'], signal, score))
            # Alerta Telegram si cambia a COMPRAR o VENDER
            if signal != st.session_state.last_signals[crypto_id] and signal in ["🟢 COMPRAR", "🔴 VENDER"]:
                msg = f"🚨 {info['name']}\n{signal}\nPrecio: ${price:,.2f}\n24h: {change:+.2f}%\nFear: {fng}/100\nScore: {score}/100"
                send_telegram_alert(msg)
                st.session_state.last_signals[crypto_id] = signal
            st.markdown("---")
        else:
            st.write(f"{info['name']}: ⚠️ No disponible")
    # Botón de actualización manual
    if st.button("🔄 Actualizar ahora"):
        st.rerun()

# ==================== ANÁLISIS DE HORARIOS (reporte cada 8h) ====================
st.subheader("⏰ Mejores y Peores Horas del Día (CDMX)")
st.caption("Basado en datos de las últimas 24 horas. Útil para planificar operaciones.")

# Mostrar análisis de horarios para la cripto seleccionada
ohlc_df = get_ohlc(selected_crypto, days=1)
if ohlc_df is not None:
    best, worst = best_worst_hours(ohlc_df, CRYPTOS[selected_crypto]['name'])
    if best is not None:
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("#### 🟢 Mejores horas (ganancia potencial)")
            for hour, chg in best.items():
                st.write(f"**{int(hour):02d}:00** → {chg:+.2f}%")
        with col_b:
            st.markdown("#### 🔴 Peores horas (pérdida potencial)")
            for hour, chg in worst.items():
                st.write(f"**{int(hour):02d}:00** → {chg:+.2f}%")
    else:
        st.info("No hay suficientes datos horarios para esta moneda.")
else:
    st.warning("No se pudieron obtener datos horarios.")

# Reporte automático cada 8 horas (envía por Telegram)
current_time = datetime.now().timestamp()
if current_time - st.session_state.last_report >= 8 * 3600:
    st.session_state.last_report = current_time
    # Enviar resumen por Telegram
    report_msg = "📊 *REPORTE DE HORARIOS* 📊\n\n"
    for crypto_id, info in CRYPTOS.items():
        ohlc = get_ohlc(crypto_id, days=1)
        if ohlc is not None:
            best, worst = best_worst_hours(ohlc, info['name'])
            if best is not None:
                report_msg += f"*{info['name']}*\n"
                report_msg += "🟢 Mejores: " + ", ".join([f"{int(h):02d}:00 ({ch:+.2f}%)" for h, ch in best.items()]) + "\n"
                report_msg += "🔴 Peores: " + ", ".join([f"{int(h):02d}:00 ({ch:+.2f}%)" for h, ch in worst.items()]) + "\n\n"
    send_telegram_alert(report_msg)
    st.toast("Reporte de horarios enviado a Telegram", icon="📨")

# ==================== AUTO REFRESH ====================
if auto_refresh:
    time.sleep(interval)
    st.rerun()
