import streamlit as st
import pandas as pd
import numpy as np
import time
import requests
from collections import deque
from datetime import datetime
import plotly.express as px
import random

# ==================== CONFIGURACIÓN ====================
TELEGRAM_TOKEN = "8532857017:AAHwLhRnM3oC6TbgFFKAEmQnZVoo6JD_esQ"
TELEGRAM_CHAT_ID = "5835990242"

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}, timeout=5)
    except:
        pass

# ==================== DATOS REALES (CRYPTOCOMPARE) CON FALLBACK ====================
# Estado de conectividad
if "use_real" not in st.session_state:
    st.session_state.use_real = True
if "last_fail" not in st.session_state:
    st.session_state.last_fail = 0

def get_real_price(symbol):
    """Intenta obtener precio real de Cryptocompare"""
    try:
        url_price = f"https://min-api.cryptocompare.com/data/price?fsym={symbol}&tsyms=USD"
        resp = requests.get(url_price, timeout=5)
        if resp.status_code != 200:
            return None, None
        price = float(resp.json()["USD"])
        url_change = f"https://min-api.cryptocompare.com/data/pricemultifull?fsyms={symbol}&tsyms=USD"
        resp2 = requests.get(url_change, timeout=5)
        if resp2.status_code == 200:
            data = resp2.json()
            change = data["RAW"][symbol]["USD"]["CHANGEPCT24HOUR"]
            return price, change
        return price, 0.0
    except:
        return None, None

# Precios base realistas para simulación
REAL_BASES = {"BTC": 65000, "ETH": 3500}
SIM_PRICES = {"BTC": 65000, "ETH": 3500}
SIM_CHANGES = {"BTC": 0.0, "ETH": 0.0}

def get_price(symbol):
    global SIM_PRICES, SIM_CHANGES
    now = time.time()
    # Si estamos en modo real y no ha fallado recientemente
    if st.session_state.use_real and (now - st.session_state.last_fail > 300):  # 5 minutos de gracia
        price, change = get_real_price(symbol)
        if price is not None:
            return price, change, "real"
        else:
            st.session_state.last_fail = now
            st.session_state.use_real = False
            # Pasar a modo simulado
    # Modo simulado
    # Simular movimiento de precio realista (random walk con tendencia suave)
    last_price = SIM_PRICES.get(symbol, REAL_BASES[symbol])
    # Cambio porcentual aleatorio entre -1% y +1% (simula volatilidad real)
    change_pct = random.uniform(-0.01, 0.01)
    new_price = last_price * (1 + change_pct)
    # Cambio 24h simulado (varía lentamente)
    sim_change = SIM_CHANGES.get(symbol, 0.0)
    sim_change += random.uniform(-0.5, 0.5)
    sim_change = max(-10, min(10, sim_change))
    SIM_PRICES[symbol] = new_price
    SIM_CHANGES[symbol] = sim_change
    return new_price, sim_change, "sim"

def get_fear_greed():
    try:
        resp = requests.get("https://api.alternative.me/fng/", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return int(data['data'][0]['value']), data['data'][0]['value_classification']
    except:
        pass
    return 50, "Neutral"

# ==================== INDICADORES Y FÓRMULA ====================
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

def calculate_score(price, change, fng, hist):
    score = 50
    # Fear & Greed
    score += (50 - fng) * 0.5
    # Cambio 24h
    score += np.clip(change * 2, -12, 12)
    # RSI
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
    # Tendencia últimas 5 lecturas
    if len(hist) >= 5:
        trend = np.mean(np.diff(list(hist)[-5:]))
        score += 10 if trend > 0 else -10
    return np.clip(score, 0, 100)

# ==================== INICIALIZAR ESTADO ====================
if "balance" not in st.session_state:
    st.session_state.balance = 1000.0
    st.session_state.positions = {"BTC": 0.0, "ETH": 0.0}
    st.session_state.trades = []
    st.session_state.price_history = {"BTC": deque(maxlen=50), "ETH": deque(maxlen=50)}
    st.session_state.last_action = {"BTC": None, "ETH": None}
    st.session_state.last_prices = {"BTC": 0.0, "ETH": 0.0}

CRYPTOS = {"BTC": "Bitcoin", "ETH": "Ethereum"}

# ==================== INTERFAZ ====================
st.set_page_config(page_title="Crypto Auto Trader", layout="wide")
st.title("🤖 Crypto Auto Trader - Fórmula Matemática + Alertas Telegram")

st.sidebar.header("Configuración")
refresh = st.sidebar.slider("Actualizar cada (segundos)", 60, 180, 90)
auto = st.sidebar.checkbox("Auto-refrescar", True)
buy_th = st.sidebar.slider("Umbral COMPRA", 60, 90, 70)
sell_th = st.sidebar.slider("Umbral VENTA", 10, 40, 30)
trade_amount = st.sidebar.number_input("Monto por orden (USDT)", 10.0, 100.0, 20.0)

st.sidebar.subheader("💰 Estado Simulado")
st.sidebar.metric("Saldo USDT", f"${st.session_state.balance:,.2f}")
total = st.session_state.balance
for sym in CRYPTOS:
    last_p = st.session_state.last_prices.get(sym, 0)
    qty = st.session_state.positions.get(sym, 0)
    if qty > 0 and last_p > 0:
        total += qty * last_p
st.sidebar.metric("Valor cartera", f"${total:,.2f}")
if st.sidebar.button("Reiniciar simulación"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

if not st.session_state.use_real:
    st.warning("⚠️ **Modo simulación activado** – No se pudieron obtener datos reales de la API. Los precios son simulados pero realistas.")

# ==================== OBTENER DATOS ====================
fng, fng_label = get_fear_greed()
price_data = {}
for sym, name in CRYPTOS.items():
    price, change, source = get_price(sym)
    st.session_state.last_prices[sym] = price
    price_data[sym] = (price, change, source)
    if price > 0:
        st.session_state.price_history[sym].append(price)

# ==================== LÓGICA DE TRADING ====================
for sym, name in CRYPTOS.items():
    price, change, source = price_data[sym]
    if price == 0:
        continue
    hist = st.session_state.price_history[sym]
    if len(hist) < 5:
        signal_display = "ESPERANDO DATOS"
        score_display = 0
        action = "HOLD"
    else:
        score = calculate_score(price, change, fng, hist)
        score_display = f"{score:.1f}/100"
        if score >= buy_th:
            action = "BUY"
            signal_display = "COMPRAR"
        elif score <= sell_th:
            action = "SELL"
            signal_display = "VENDER"
        else:
            action = "HOLD"
            signal_display = "MANTENER"

        if action != st.session_state.last_action.get(sym) and action in ("BUY", "SELL"):
            if action == "BUY":
                if st.session_state.balance >= trade_amount:
                    st.session_state.balance -= trade_amount
                    qty = trade_amount / price
                    st.session_state.positions[sym] += qty
                    msg = f"🟢 *{name}* COMPRA SIMULADA: {qty:.6f} @ ${price:.2f} (Score: {score:.1f})"
                    send_telegram(msg)
                else:
                    send_telegram(f"❌ Saldo insuficiente para comprar {name}")
            else:
                qty = st.session_state.positions.get(sym, 0)
                if qty > 0:
                    revenue = qty * price
                    st.session_state.balance += revenue
                    st.session_state.positions[sym] = 0
                    msg = f"🔴 *{name}* VENTA SIMULADA: {qty:.6f} @ ${price:.2f} (Score: {score:.1f})"
                    send_telegram(msg)
                else:
                    send_telegram(f"❌ No hay posición para vender {name}")
            st.session_state.trades.append((datetime.now(), msg))
            st.session_state.last_action[sym] = action

# ==================== MOSTRAR EN PANTALLA ====================
col1, col2 = st.columns(2)
with col1:
    st.subheader("📊 Señales en vivo")
    rows = []
    for sym, name in CRYPTOS.items():
        price, change, source = price_data[sym]
        if price == 0:
            rows.append({"Moneda": name, "Precio": "Sin datos", "24h %": "N/A", "Puntaje": "N/A", "Señal": "ERROR", "Fuente": "N/A"})
            continue
        hist = st.session_state.price_history[sym]
        if len(hist) < 5:
            score_display = "Pocos datos"
            signal_display = "ESPERANDO"
        else:
            score = calculate_score(price, change, fng, hist)
            if score >= buy_th:
                signal_display = "COMPRAR"
            elif score <= sell_th:
                signal_display = "VENDER"
            else:
                signal_display = "MANTENER"
            score_display = f"{score:.1f}/100"
        rows.append({
            "Moneda": name,
            "Precio": f"${price:,.2f}",
            "24h %": f"{change:+.2f}%",
            "Puntaje": score_display,
            "Señal": signal_display,
            "Fuente": "Real" if source=="real" else "Sim"
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
    st.metric("😨 Fear & Greed", f"{fng}/100 ({fng_label})")

with col2:
    st.subheader("📜 Últimas operaciones")
    if st.session_state.trades:
        for ts, msg in reversed(st.session_state.trades[-10:]):
            st.text(f"{ts.strftime('%H:%M:%S')} - {msg.replace('*','')}")
    else:
        st.caption("Aún no hay operaciones. Esperando suficientes datos (mínimo 5 lecturas)...")
    # Botón para forzar modo real (si se ha recuperado la conexión)
    if not st.session_state.use_real and st.button("Intentar conectar a API real de nuevo"):
        st.session_state.use_real = True
        st.session_state.last_fail = 0
        st.rerun()

# ==================== AUTO REFRESCO ====================
if auto:
    time.sleep(refresh)
    st.rerun()
