import streamlit as st
import pandas as pd
import numpy as np
import time
import requests
from datetime import datetime, timedelta, timezone
from collections import deque
import plotly.express as px
import yfinance as yf

# ==================== CONFIGURACIÓN ====================
st.set_page_config(page_title="Crypto Auto Trader", layout="wide")
st.title("🤖 Crypto Auto Trader - Fórmula Matemática + Ejecución Automática")

# Advertencia inicial
st.error("""
**⚠️ ADVERTENCIA DE ALTO RIESGO**  
Este bot puede ejecutar órdenes de compra/venta REALES si se configura con las claves API de Binance.  
**Activar el modo real es bajo tu exclusiva responsabilidad.**  
Primero prueba en modo SIMULACIÓN (paper trading) durante semanas.
""")

# ==================== CONFIGURACIÓN DEL USUARIO ====================
st.sidebar.header("⚙️ Configuración General")
refresh_interval = st.sidebar.slider("Intervalo de actualización (segundos)", 60, 300, 90, step=10)
auto_refresh = st.sidebar.checkbox("Auto-refrescar", value=True)

# ==================== CONFIGURACIÓN DEL TRADING ====================
st.sidebar.subheader("📊 Configuración de Trading")
trading_mode = st.sidebar.radio("Modo de ejecución", ["Simulación (Paper Trading)", "Real (Binance - Riesgo alto)"])
if trading_mode == "Real (Binance - Riesgo alto)":
    st.sidebar.error("⚠️ Modo REAL activado: Se ejecutarán órdenes reales en Binance.")
    binance_api_key = st.sidebar.text_input("API Key de Binance", type="password")
    binance_secret_key = st.sidebar.text_input("Secret Key", type="password")
    st.sidebar.warning("Nunca compartas tus claves. Esta app no las almacena, pero úsalas bajo tu responsabilidad.")
else:
    binance_api_key = None
    binance_secret_key = None
    st.sidebar.success("✅ Modo SIMULACIÓN: No se ejecutará dinero real.")

# Parámetros de la estrategia
st.sidebar.subheader("🎯 Umbrales de la fórmula")
buy_threshold = st.sidebar.slider("Umbral de COMPRA (puntaje mínimo)", 60, 90, 70)
sell_threshold = st.sidebar.slider("Umbral de VENTA (puntaje máximo)", 10, 40, 30)
st.sidebar.caption("La fórmula genera un puntaje 0-100. Si >= buy_threshold → COMPRA, si <= sell_threshold → VENTA.")

trade_amount_usdt = st.sidebar.number_input("Cantidad a operar (en USDT)", min_value=10.0, value=20.0, step=5.0)
st.sidebar.caption("En modo real, se comprará/venderá esta cantidad en USDT. En simulación, es virtual.")

# ==================== FUNCIONES DE MERCADO ====================
CRYPTOS = {
    "BTC-USD": {"name": "Bitcoin", "base": 65000},
    "ETH-USD": {"name": "Ethereum", "base": 3500},
}
# (puedes añadir más, pero menos pares = menos peticiones)

def fetch_yfinance_price(symbol):
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        price = info.get('regularMarketPrice') or info.get('currentPrice')
        change = info.get('regularMarketChangePercent') or info.get('changePercent', 0)
        if price:
            return float(price), float(change)
        # fallback con histórico
        hist = ticker.history(period="1d", interval="1m")
        if not hist.empty:
            price = hist['Close'].iloc[-1]
            yesterday = ticker.history(period="2d", interval="1d")
            if len(yesterday) >= 2:
                change = (price - yesterday['Close'].iloc[-2]) / yesterday['Close'].iloc[-2] * 100
            else:
                change = 0
            return price, change
        return None, None
    except:
        return None, None

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

# ==================== FÓRMULA MATEMÁTICA EXACTA ====================
def calculate_score(price, change_24h, fng_value, price_history):
    """
    Fórmula matemática que devuelve un puntaje de 0 a 100.
    Mayor puntaje = más probable compra, menor = más probable venta.
    """
    score = 50
    # Fear & Greed (0-100) -> influencia lineal: miedo extremo (0) suma 25, avaricia extrema (100) resta 25
    score += (50 - fng_value) * 0.5  # rango -25 a +25
    # Cambio 24h: si >3% suma hasta 12, si < -3% resta hasta 12
    score += np.clip(change_24h * 2, -12, 12)
    # RSI (sobreventa <30 suma, sobrecompra >70 resta)
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
    # Tendencia de precio (últimas 5 lecturas)
    if len(price_history) >= 5:
        trend = np.mean(np.diff(list(price_history)[-5:]))
        if trend > 0:
            score += 10
        else:
            score -= 10
    return np.clip(score, 0, 100)

# ==================== EJECUCIÓN DE ÓRDENES ====================
def execute_order(symbol, side, quantity_usdt, price, mode):
    """
    side: 'BUY' o 'SELL'
    quantity_usdt: monto en USDT a invertir (modo real se convierte a cantidad de moneda)
    """
    if mode == "Simulación (Paper Trading)":
        # Simulación: solo registramos en el estado
        return {"status": "success", "type": "sim", "message": f"SIM: {side} {quantity_usdt:.2f} USDT de {symbol} a ${price:.2f}"}
    else:
        # Modo real Binance
        try:
            from binance.client import Client
            client = Client(binance_api_key, binance_secret_key)
            # Obtener el par en formato Binance (ej: BTCUSDT)
            pair = symbol.replace("-", "")
            # Obtener precio actual para calcular cantidad
            ticker = client.get_symbol_ticker(symbol=pair)
            current_price = float(ticker['price'])
            quantity = quantity_usdt / current_price
            # Redondear cantidad según las reglas del par (se podría mejorar)
            quantity = round(quantity, 6)
            if side == "BUY":
                order = client.order_market_buy(symbol=pair, quantity=quantity)
            else:
                order = client.order_market_sell(symbol=pair, quantity=quantity)
            return {"status": "success", "type": "real", "order": order, "message": f"REAL: {side} {quantity} de {pair} a ~${current_price}"}
        except Exception as e:
            return {"status": "error", "message": f"Error en orden real: {e}"}

# ==================== ESTADO DE LA CUENTA SIMULADA ====================
if "balance_sim" not in st.session_state:
    st.session_state.balance_sim = 1000.0  # USDT inicial
    st.session_state.positions_sim = {sym: 0.0 for sym in CRYPTOS}
    st.session_state.trade_log = []

# ==================== LÓGICA PRINCIPAL ====================
# Variables de control para no repetir órdenes en cada ciclo
if "last_action" not in st.session_state:
    st.session_state.last_action = {sym: None for sym in CRYPTOS}
if "last_price" not in st.session_state:
    st.session_state.last_price = {sym: 0 for sym in CRYPTOS}

# Obtener datos de mercado una vez por ciclo
fng_val, _ = get_fear_greed()
price_data = {}
for sym, info in CRYPTOS.items():
    price, change = fetch_yfinance_price(sym)
    if price is None:
        price = st.session_state.last_price.get(sym, info["base"])
        change = 0
    st.session_state.last_price[sym] = price
    price_data[sym] = {"price": price, "change": change}

# Mostrar resumen de cuenta en sidebar
st.sidebar.subheader("💰 Estado de Cuenta (Simulación)")
st.sidebar.metric("Saldo USDT", f"${st.session_state.balance_sim:,.2f}")
total_value = st.session_state.balance_sim
for sym, qty in st.session_state.positions_sim.items():
    if qty > 0:
        total_value += qty * price_data[sym]["price"]
st.sidebar.metric("Valor total cartera", f"${total_value:,.2f}")
if st.sidebar.button("Reiniciar simulación"):
    st.session_state.balance_sim = 1000.0
    st.session_state.positions_sim = {sym: 0.0 for sym in CRYPTOS}
    st.session_state.trade_log = []
    st.rerun()

# Procesar cada criptomoneda
for sym, info in CRYPTOS.items():
    price = price_data[sym]["price"]
    change = price_data[sym]["change"]
    # Historial de precios (para RSI y tendencia)
    if sym not in st.session_state.price_history:
        st.session_state.price_history[sym] = deque(maxlen=50)
    st.session_state.price_history[sym].append(price)
    # Calcular puntaje según fórmula
    score = calculate_score(price, change, fng_val, st.session_state.price_history[sym])
    # Determinar acción
    action = None
    if score >= buy_threshold:
        action = "BUY"
    elif score <= sell_threshold:
        action = "SELL"
    else:
        action = "HOLD"
    # Ejecutar orden si es diferente a la última acción (evita spam)
    if action != st.session_state.last_action.get(sym) and action in ["BUY", "SELL"]:
        # Ejecutar orden
        if trading_mode == "Simulación (Paper Trading)":
            # Lógica de simulación
            if action == "BUY":
                cost = trade_amount_usdt
                if cost <= st.session_state.balance_sim:
                    st.session_state.balance_sim -= cost
                    quantity = cost / price
                    st.session_state.positions_sim[sym] += quantity
                    msg = f"COMPRA SIMULADA: {quantity:.6f} {info['name']} a ${price:.2f} (Score: {score:.1f})"
                else:
                    msg = f"Fondos insuficientes para comprar {info['name']}"
            else:  # SELL
                quantity = st.session_state.positions_sim[sym]
                if quantity > 0:
                    revenue = quantity * price
                    st.session_state.balance_sim += revenue
                    st.session_state.positions_sim[sym] = 0
                    msg = f"VENTA SIMULADA: {quantity:.6f} {info['name']} a ${price:.2f} (Score: {score:.1f})"
                else:
                    msg = f"No tienes {info['name']} para vender"
            st.session_state.trade_log.append((datetime.now(), msg))
            st.success(msg)
        else:
            # Modo real (Binance)
            if action == "BUY":
                result = execute_order(sym, "BUY", trade_amount_usdt, price, trading_mode)
            else:
                # Para vender, necesitamos la cantidad que tenemos en el exchange. Aquí simplificamos: vender todo lo que tenemos en simulación (no es realista)
                # En modo real deberías consultar el saldo real de la cuenta. Por simplicidad, usamos un placeholder.
                st.error("En modo real, la venta requiere implementar consulta de saldo. No se ejecutará.")
                result = {"status": "error", "message": "Venta real no implementada en este ejemplo por seguridad."}
            if result["status"] == "success":
                st.success(result["message"])
            else:
                st.error(result["message"])
        st.session_state.last_action[sym] = action

# Mostrar señales y precios en la interfaz principal
col1, col2 = st.columns(2)
with col1:
    st.subheader("📊 Precios y Señales en vivo")
    df_signals = []
    for sym, info in CRYPTOS.items():
        price = price_data[sym]["price"]
        change = price_data[sym]["change"]
        score = calculate_score(price, change, fng_val, st.session_state.price_history.get(sym, []))
        action = "COMPRAR" if score >= buy_threshold else "VENDER" if score <= sell_threshold else "MANTENER"
        df_signals.append({
            "Moneda": info["name"],
            "Precio": f"${price:,.2f}",
            "24h %": f"{change:+.2f}%",
            "Puntaje": f"{score:.1f}/100",
            "Señal": action
        })
    st.dataframe(pd.DataFrame(df_signals), use_container_width=True)

with col2:
    st.subheader("📜 Registro de operaciones")
    if st.session_state.trade_log:
        for ts, msg in reversed(st.session_state.trade_log[-10:]):
            st.text(f"{ts.strftime('%H:%M:%S')} - {msg}")
    else:
        st.caption("Aún no hay operaciones.")

# ==================== GRÁFICAS Y ANÁLISIS DE HORARIOS (opcional) ====================
# (Puedes conservar las gráficas del código anterior si lo deseas)

# Auto-refresco
if auto_refresh:
    time.sleep(refresh_interval)
    st.rerun()
