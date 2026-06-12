import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta, timezone
import time
import numpy as np
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import json
from collections import deque

# ==================== CONFIGURACIÓN GLOBAL ====================
st.set_page_config(page_title="Crypto Analyst Pro", layout="wide", page_icon="📈")
st.title("📊 Crypto Analyst Pro - Trading Signals & Optimal Hours")

# Telegram (cambia por tus datos)
TELEGRAM_TOKEN = "8532857017:AAHwLhRnM3oC6TbgFFKAEmQnZVoo6JD_esQ"
TELEGRAM_CHAT_ID = "5835990242"

# Zona horaria Ciudad de México (UTC-6, sin horario de verano por ahora)
CDMX_TZ = timezone(timedelta(hours=-6))

# Lista de criptomonedas confiables (IDs de CoinGecko)
CRYPTOS = {
    "bitcoin": {"name": "Bitcoin", "symbol": "BTC", "priority": 1},
    "ethereum": {"name": "Ethereum", "symbol": "ETH", "priority": 2},
    "solana": {"name": "Solana", "symbol": "SOL", "priority": 3},
    "cardano": {"name": "Cardano", "symbol": "ADA", "priority": 4},
    "dogecoin": {"name": "Dogecoin", "symbol": "DOGE", "priority": 5},
    "ripple": {"name": "XRP", "symbol": "XRP", "priority": 6},
}

# Configuración de reintentos
RETRY_ATTEMPTS = 3
RETRY_WAIT = 2  # segundos

# Inicializar estado de sesión
if "last_signals" not in st.session_state:
    st.session_state.last_signals = {cid: "" for cid in CRYPTOS}
if "price_history" not in st.session_state:
    st.session_state.price_history = {cid: deque(maxlen=50) for cid in CRYPTOS}
if "last_report_time" not in st.session_state:
    st.session_state.last_report_time = datetime.now().timestamp() - 8*3600
if "fear_greed" not in st.session_state:
    st.session_state.fear_greed = (50, "Neutral")

# ==================== FUNCIONES DE RED ROBUSTAS ====================
@retry(stop=stop_after_attempt(RETRY_ATTEMPTS), wait=wait_exponential(multiplier=1, min=2, max=10))
def safe_get(url, params=None, timeout=15):
    """Realiza petición GET con reintentos y backoff exponencial"""
    try:
        response = requests.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.warning(f"Error de red: {e}. Reintentando...")
        raise

def get_current_price(crypto_id):
    """Obtiene precio actual y cambio 24h con reintentos"""
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={crypto_id}&vs_currencies=usd&include_24hr_change=true"
    try:
        data = safe_get(url, timeout=10)
        if crypto_id in data:
            price = data[crypto_id]['usd']
            change = data[crypto_id].get('usd_24h_change', 0.0)
            return price, change
    except:
        pass
    return None, None

def get_fear_greed():
    """Obtiene índice de miedo y codicia con caché de 1 hora"""
    if "fg_last_update" in st.session_state and datetime.now().timestamp() - st.session_state.fg_last_update < 3600:
        return st.session_state.fear_greed
    url = "https://api.alternative.me/fng/"
    try:
        data = safe_get(url, timeout=10)
        value = int(data['data'][0]['value'])
        classification = data['data'][0]['value_classification']
        st.session_state.fear_greed = (value, classification)
        st.session_state.fg_last_update = datetime.now().timestamp()
        return value, classification
    except:
        return 50, "Neutral"

@st.cache_data(ttl=300, show_spinner=False)
def get_ohlc(crypto_id, days=2):
    """Obtiene datos OHLC horarios (más robusto con days=2 para tener datos)"""
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

@st.cache_data(ttl=600, show_spinner=False)
def get_historical_prices(crypto_id, days=7):
    """Obtiene precios diarios para gráfica de tendencia"""
    url = f"https://api.coingecko.com/api/v3/coins/{crypto_id}/market_chart?vs_currency=usd&days={days}&interval=daily"
    try:
        data = safe_get(url, timeout=15)
        prices = data['prices']
        df = pd.DataFrame(prices, columns=['timestamp', 'price'])
        df['date'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df[['date', 'price']]
    except:
        return pd.DataFrame()

@st.cache_data(ttl=120, show_spinner=False)
def get_top_crypto():
    """Obtiene top 20 criptomonedas por market cap"""
    url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=20&sparkline=false"
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

# ==================== INDICADORES TÉCNICOS ====================
def compute_rsi(prices, period=14):
    """Calcula RSI a partir de lista de precios"""
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
    rsi = 100 - (100 / (1 + rs))
    return rsi

def compute_macd(prices, fast=12, slow=26, signal=9):
    """Calcula MACD (último valor y cruce)"""
    if len(prices) < slow + signal:
        return 0, False
    ema_fast = pd.Series(prices).ewm(span=fast, adjust=False).mean()
    ema_slow = pd.Series(prices).ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    # Cruce: si el último histograma es positivo y el anterior no
    if len(histogram) >= 2:
        cross_up = histogram.iloc[-1] > 0 and histogram.iloc[-2] <= 0
        cross_down = histogram.iloc[-1] < 0 and histogram.iloc[-2] >= 0
        return histogram.iloc[-1], cross_up, cross_down
    return 0, False, False

def compute_moving_averages(prices, short=7, long=20):
    """Calcula medias móviles simples"""
    if len(prices) < long:
        return None, None
    ma_short = np.mean(prices[-short:])
    ma_long = np.mean(prices[-long:])
    return ma_short, ma_long

# ==================== SEÑAL DE COMPRA/VENTA AVANZADA ====================
def generate_signal(price, change_24h, fng_value, price_history):
    """
    Genera señal combinando:
    - Fear & Greed (25%)
    - Cambio 24h (20%)
    - RSI (15%)
    - MACD (15%)
    - Medias móviles (15%)
    - Tendencia reciente (10%)
    """
    score = 50
    # 1. Fear & Greed (0-24 compra, 75-100 venta)
    if fng_value < 25:
        score += 20
    elif fng_value < 40:
        score += 10
    elif fng_value > 75:
        score -= 20
    elif fng_value > 60:
        score -= 10
    # 2. Cambio 24h
    if change_24h > 3:
        score += 12
    elif change_24h > 1:
        score += 6
    elif change_24h < -3:
        score -= 12
    elif change_24h < -1:
        score -= 6
    # 3. RSI (sobreventa <30 -> compra, sobrecompra >70 -> venta)
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
    # 4. MACD
    if len(price_history) >= 34:
        hist, cross_up, cross_down = compute_macd(list(price_history))
        if cross_up:
            score += 12
        elif cross_down:
            score -= 12
        elif hist > 0:
            score += 5
        elif hist < 0:
            score -= 5
    # 5. Medias móviles
    ma_short, ma_long = compute_moving_averages(list(price_history))
    if ma_short and ma_long:
        if ma_short > ma_long:
            score += 10
        else:
            score -= 10
    # 6. Tendencia últimas 5 lecturas
    if len(price_history) >= 5:
        trend = np.mean(np.diff(list(price_history)[-5:]))
        if trend > 0:
            score += 5
        else:
            score -= 5
    # Limitar entre 0 y 100
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

# ==================== HORARIOS ÓPTIMOS ====================
def get_best_worst_hours(crypto_id):
    """Devuelve las 3 mejores y 3 peores horas del día (CDMX)"""
    df = get_ohlc(crypto_id, days=2)
    if df is None or df.empty:
        return None, None
    # Calcular cambio porcentual por vela
    df['change'] = (df['close'] - df['open']) / df['open'] * 100
    # Agrupar por hora (solo horas con al menos 2 ocurrencias para robustez)
    hourly = df.groupby('hour_cdmx')['change'].agg(['mean', 'count'])
    hourly = hourly[hourly['count'] >= 2]  # filtrar horas con pocos datos
    if hourly.empty:
        return None, None
    hourly_sorted = hourly.sort_values('mean', ascending=False)
    best = hourly_sorted.head(3)
    worst = hourly_sorted.tail(3)
    return best, worst

def format_hour_report(crypto_name, best, worst):
    """Formatea el reporte de horarios para Telegram"""
    if best is None:
        return f"⚠️ No hay suficientes datos horarios para {crypto_name}"
    lines = [f"📊 *{crypto_name}*"]
    lines.append("🟢 Mejores horas para COMPRAR:")
    for hour, row in best.iterrows():
        lines.append(f"   ⏰ {int(hour):02d}:00 → {row['mean']:+.2f}% (promedio)")
    lines.append("🔴 Peores horas para VENDER:")
    for hour, row in worst.iterrows():
        lines.append(f"   ⏰ {int(hour):02d}:00 → {row['mean']:+.2f}% (promedio)")
    return "\n".join(lines)

# ==================== TELEGRAM ====================
def send_telegram(message):
    """Envía mensaje a Telegram de forma asíncrona (no bloquea)"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}, timeout=5)
    except:
        pass

# ==================== INTERFAZ DE STREAMLIT ====================
def main():
    # Sidebar configuración
    st.sidebar.header("⚙️ Configuración")
    refresh_interval = st.sidebar.slider("Intervalo de actualización (segundos)", 15, 120, 60)
    auto_refresh = st.sidebar.checkbox("Auto-refrescar", value=True)
    st.sidebar.markdown("---")
    
    # Mostrar Fear & Greed actual
    fng_val, fng_label = get_fear_greed()
    st.sidebar.metric("😨 Fear & Greed", f"{fng_val}/100", fng_label)
    
    # Información de la estrategia
    with st.sidebar.expander("📈 Estrategia de señales"):
        st.markdown("""
        - **Fear & Greed** (20%): Miedo extremo (<25) suma a COMPRA, avaricia (>75) suma a VENTA
        - **Cambio 24h** (12%): Subidas >3% suman, bajadas >3% restan
        - **RSI** (15%): Sobreventa (<30) suma, sobrecompra (>70) resta
        - **MACD** (12%): Cruce alcista suma, bajista resta
        - **Medias móviles** (10%): MM7 > MM20 suma
        - **Tendencia reciente** (5%): Últimas 5 lecturas ascendentes suman
        """)
    
    # Tabs principales
    tab1, tab2, tab3 = st.tabs(["📊 Top Cripto & Señales", "📈 Gráficos Detallados", "⏰ Análisis de Horarios"])
    
    with tab1:
        col1, col2 = st.columns([2, 1])
        with col1:
            st.subheader("🏆 Top 20 Criptomonedas")
            top_df = get_top_crypto()
            if not top_df.empty:
                st.dataframe(top_df, use_container_width=True, height=450)
            else:
                st.error("No se pudo cargar el top de criptomonedas. Reintentando...")
        with col2:
            st.subheader("📡 Señales en Tiempo Real")
            # Mostrar señales para cada criptomoneda
            for crypto_id, info in CRYPTOS.items():
                price, change = get_current_price(crypto_id)
                if price is not None:
                    # Actualizar historial
                    st.session_state.price_history[crypto_id].append(price)
                    signal, score, desc = generate_signal(price, change, fng_val, st.session_state.price_history[crypto_id])
                    # Alerta si cambia a COMPRAR o VENDER y no se había enviado
                    if signal != st.session_state.last_signals[crypto_id] and "COMPRAR" in signal or "VENDER" in signal:
                        alert_msg = f"🚨 *{info['name']}* 🚨\n{signal}\n💰 Precio: ${price:,.2f}\n📈 24h: {change:+.2f}%\n😨 Fear: {fng_val}/100\n🎯 Score: {score}/100\n_{desc}_"
                        send_telegram(alert_msg)
                        st.session_state.last_signals[crypto_id] = signal
                    # Mostrar en Streamlit
                    st.metric(info['name'], f"${price:,.2f}", f"{change:+.2f}%")
                    st.write(f"**{signal}** (Score: {score}/100)")
                    st.caption(desc)
                else:
                    st.write(f"⚠️ {info['name']}: Sin datos")
                st.markdown("---")
    
    with tab2:
        # Selección de criptomoneda para gráficas
        selected = st.selectbox("Selecciona criptomoneda", list(CRYPTOS.keys()), format_func=lambda x: CRYPTOS[x]['name'])
        info = CRYPTOS[selected]
        # Gráfica de precios históricos
        st.subheader(f"📉 Precio histórico de {info['name']} (últimos 7 días)")
        hist_df = get_historical_prices(selected, days=7)
        if not hist_df.empty:
            fig = px.line(hist_df, x='date', y='price', title=f"Tendencia de {info['name']}", 
                          labels={'price': 'USD', 'date': 'Fecha'}, markers=True)
            fig.update_layout(height=400, hovermode='x unified')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("No se pudo cargar el histórico")
        
        # Gráfica de velas (últimas 48 horas)
        st.subheader(f"🕯️ Velas horarias (últimas 48h)")
        ohlc_df = get_ohlc(selected, days=2)
        if ohlc_df is not None and not ohlc_df.empty:
            fig = go.Figure(data=[go.Candlestick(x=ohlc_df['datetime'],
                                                  open=ohlc_df['open'], high=ohlc_df['high'],
                                                  low=ohlc_df['low'], close=ohlc_df['close'])])
            fig.update_layout(xaxis_title="Fecha/Hora", yaxis_title="Precio USD", height=400)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No hay suficientes datos de velas para esta criptomoneda.")
    
    with tab3:
        st.subheader("⏰ Mejores y Peores Horas del Día (CDMX)")
        st.caption("Basado en datos de las últimas 48 horas. Solo se muestran horas con al menos 2 ocurrencias.")
        # Botón para forzar actualización de horarios
        if st.button("🔄 Actualizar análisis de horarios ahora"):
            st.cache_data.clear()
            st.rerun()
        for crypto_id, info in CRYPTOS.items():
            best, worst = get_best_worst_hours(crypto_id)
            if best is not None and not best.empty:
                st.markdown(f"### {info['name']} ({info['symbol']})")
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown("#### 🟢 Mejores horas para COMPRAR")
                    for hour, row in best.iterrows():
                        st.write(f"⏰ **{int(hour):02d}:00** → +{row['mean']:.2f}% promedio")
                with col_b:
                    st.markdown("#### 🔴 Peores horas para VENDER")
                    for hour, row in worst.iterrows():
                        st.write(f"⏰ **{int(hour):02d}:00** → {row['mean']:.2f}% promedio")
                st.markdown("---")
            else:
                st.write(f"⚠️ {info['name']}: Datos insuficientes para análisis horario")
    
    # Reporte automático cada 8 horas por Telegram
    now_ts = datetime.now().timestamp()
    if now_ts - st.session_state.last_report_time >= 8 * 3600:
        st.session_state.last_report_time = now_ts
        # Enviar reporte de horarios de todas las monedas por Telegram
        report_lines = ["📊 *REPORTE DE HORARIOS (Crypto Analyst Pro)* 📊", ""]
        for crypto_id, info in CRYPTOS.items():
            best, worst = get_best_worst_hours(crypto_id)
            if best is not None and not best.empty:
                report_lines.append(f"*{info['name']}*")
                report_lines.append("🟢 Mejores: " + ", ".join([f"{int(h):02d}:00 ({row['mean']:+.2f}%)" for h, row in best.iterrows()]))
                report_lines.append("🔴 Peores: " + ", ".join([f"{int(h):02d}:00 ({row['mean']:+.2f}%)" for h, row in worst.iterrows()]))
                report_lines.append("")
        if len(report_lines) > 2:
            send_telegram("\n".join(report_lines))
        else:
            send_telegram("⚠️ No se pudo generar el reporte de horarios esta vez. Se reintentará en 8 horas.")
    
    # Auto-refresco
    if auto_refresh:
        time.sleep(refresh_interval)
        st.rerun()

if __name__ == "__main__":
    main()
