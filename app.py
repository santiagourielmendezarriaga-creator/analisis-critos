import streamlit as st
import pandas as pd
import numpy as np
import time
import requests
from collections import deque
from datetime import datetime
import plotly.express as px

# ==================== CONFIGURACIÓN TELEGRAM ====================
TELEGRAM_TOKEN = "8532857017:AAHwLhRnM3oC6TbgFFKAEmQnZVoo6JD_esQ"
TELEGRAM_CHAT_ID = "5835990242"

def send_telegram(message):
    """Envía mensaje a Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=data, timeout=5)
    except Exception as e:
        print(f"Error enviando a Telegram: {e}")

# ==================== IMPORTAR YFINANCE ====================
try:
    import yfinance as yf
    YF_OK = True
except ImportError:
    YF_OK = False
    st.error("Falta yfinance. Agrégalo a requirements.txt")

st.set_page_config(page_title="Crypto Auto Trader", layout="wide")
st.title("🤖 Crypto Auto Trader - Fórmula Matemática + Alertas Telegram")

if not YF_OK:
    st.stop()

# ==================== FUNCIONES AUXILIARES ====================
def get_fear_greed():
    try:
        resp = requests.get("https://api.alternative.me/fng/", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return int(data['data'][0]['value']), data['data'][0]['value_classification']
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

def fetch_price(symbol):
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        price = info.get('regularMarketPrice') or info.get('currentPrice')
        change = info.get('regularMarketChangePercent') or info.get('changePercent', 0)
        if price:
            return float(price), float(change)
    except:
        pass
    return None, None

# ==================== FÓRMULA DE PUNTAJE ====================
def calculate_score(price, change, fng, hist):
    score = 50
    score += (50 - fng) * 0.5
    score += np.clip(change * 2, -12, 12)
    if len(hist) >= 14:
        rsi = compute_rsi(list(hist))
        if rsi < 30:
            score += 15
        elif rsi < 40:
            score += 8
        elif rsi > 70:
            score -= 15
        elif rsi > 60:
            score -= 8
    if len(hist) >= 5:
        trend = np.mean(np.diff(list(hist)[-5:]))
        score += 10 if trend > 0 else -10
    return np.clip(score, 0, 100)

# ==================== INICIALIZAR ESTADO ====================
if "balance" not in st.session_state:
    st.session_state.balance = 1000.0
    st.session_state.positions = {}
    st.session_state.trades = []
    st.session_state.price_history = {}
    st.session_state.last_action = {}
    st.session_state.last_prices = {}

CRYPTOS = {"BTC-USD": "Bitcoin", "ETH-USD": "Ethereum"}

for sym in CRYPTOS:
    if sym not in st.session_state.price_history:
        st.session_state.price_history[sym] = deque(maxlen=50)
    if sym not in st.session_state.positions:
        st.session_state.positions[sym] = 0.0
    if sym not in st.session_state.last_action:
        st.session_state.last_action[sym] = None
    if sym not in st.session_state.last_prices:
        st.session_state.last_prices[sym] = 0.0

# ==================== CONFIGURACIÓN SIDEBAR ====================
st.sidebar.header("Configuración")
refresh = st.sidebar.slider("Actualizar cada (segundos)", 60, 180, 90)
auto = st.sidebar.checkbox("Auto-refrescar", True)
buy_th = st.sidebar.slider("Umbral COMPRA", 60, 90, 70)
sell_th = st.sidebar.slider("Umbral VENTA", 10, 40, 30)
trade_amount = st.sidebar.number_input("Monto por orden (USDT)", 10.0, 100.0, 20.0)

st.sidebar.subheader("💰 Estado Simulado")
st.sidebar.metric("Saldo USDT", f"${st.session_state.balance:,.2f}")
total = st.session_state.balance
for sym, qty in st.session_state.positions.items():
    last_p = st.session_state.last_prices.get(sym, 0)
    if qty > 0 and last_p > 0:
        total += qty * last_p
st.sidebar.metric("Valor cartera", f"${total:,.2f}")
if st.sidebar.button("Reiniciar simulación"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# ==================== OBTENER DATOS ====================
fng, fng_label = get_fear_greed()
price_data = {}
for sym, name in CRYPTOS.items():
    price, change = fetch_price(sym)
    if price is None:
        price = st.session_state.last_prices.get(sym, 0)
        change = 0
    st.session_state.last_prices[sym] = price
    price_data[sym] = (price, change)
    st.session_state.price_history[sym].append(price)

# ==================== LÓGICA DE TRADING + ALERTAS TELEGRAM ====================
for sym, name in CRYPTOS.items():
    price, change = price_data[sym]
    if price == 0:
        continue
    hist = st.session_state.price_history[sym]
    score = calculate_score(price, change, fng, hist)
    action = None
    if score >= buy_th:
        action = "BUY"
    elif score <= sell_th:
        action = "SELL"
    else:
        action = "HOLD"

    if action != st.session_state.last_action.get(sym) and action in ("BUY", "SELL"):
        if action == "BUY":
            if st.session_state.balance >= trade_amount:
                st.session_state.balance -= trade_amount
                qty = trade_amount / price
                st.session_state.positions[sym] += qty
                msg = f"🟢 *COMPRA SIMULADA*: {qty:.6f} {name} @ ${price:.2f} (Score: {score:.1f})"
                send_telegram(msg)
            else:
                msg = f"❌ Saldo insuficiente para comprar {name}"
                send_telegram(msg)
        else:  # SELL
            qty = st.session_state.positions.get(sym, 0)
            if qty > 0:
                revenue = qty * price
                st.session_state.balance += revenue
                st.session_state.positions[sym] = 0
                msg = f"🔴 *VENTA SIMULADA*: {qty:.6f} {name} @ ${price:.2f} (Score: {score:.1f})"
                send_telegram(msg)
            else:
                msg = f"❌ No hay posición para vender {name}"
                send_telegram(msg)
        st.session_state.trades.append((datetime.now(), msg))
        st.session_state.last_action[sym] = action

# ==================== MOSTRAR EN INTERFAZ ====================
col1, col2 = st.columns(2)
with col1:
    st.subheader("📊 Señales en vivo")
    rows = []
    for sym, name in CRYPTOS.items():
        price, change = price_data[sym]
        if price == 0:
            continue
        hist = st.session_state.price_history[sym]
        score = calculate_score(price, change, fng, hist)
        signal = "COMPRAR" if score >= buy_th else "VENDER" if score <= sell_th else "MANTENER"
        rows.append({
            "Moneda": name,
            "Precio": f"${price:,.2f}",
            "24h %": f"{change:+.2f}%",
            "Puntaje": f"{score:.1f}/100",
            "Señal": signal
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
    st.metric("😨 Fear & Greed", f"{fng}/100 ({fng_label})")

with col2:
    st.subheader("📜 Últimas operaciones")
    if st.session_state.trades:
        for ts, msg in reversed(st.session_state.trades[-10:]):
            # Mostrar en la interfaz sin formato Markdown
            st.text(f"{ts.strftime('%H:%M:%S')} - {msg.replace('*','')}")
    else:
        st.caption("Esperando primera señal...")

# ==================== AUTO REFRESCO ====================
if auto:
    time.sleep(refresh)
    st.rerun()
