import streamlit as st
import requests
import time
import json
import os
import random
from collections import deque
from datetime import datetime

# ==================== TELEGRAM ====================
TELEGRAM_TOKEN = "8532857017:AAHwLhRnM3oC6TbgFFKAEmQnZVoo6JD_esQ"
TELEGRAM_CHAT_ID = "5835990242"

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=3)
    except:
        pass

# ==================== PARÁMETROS ====================
# Umbral de cambio porcentual para decidir compra/venta
# Si el precio sube más de este porcentaje respecto al ciclo anterior -> compra
# Si baja más de este porcentaje -> vende
CHANGE_THRESHOLD = 0.2   # 0.2% (ajústalo según la volatilidad que quieras)

MAX_POSITION_SIZE_MXN = 500.0
MAX_DAILY_TRADES = 200
COMMISSION_PCT = 0.1
SLIPPAGE_PCT = 0.05
REFRESH_INTERVAL_SEC = 10   # actualización cada 10 segundos
HEARTBEAT_CYCLES = 30

# ==================== BITSO (DATOS REALES) ====================
def get_bitso_ticker(book="btc_mxn"):
    try:
        url = f"https://api.bitso.com/api/v3/ticker/?book={book}"
        resp = requests.get(url, timeout=3)
        if resp.status_code != 200:
            return None, None
        data = resp.json()
        payload = data.get("payload")
        if not payload:
            return None, None
        last = float(payload.get("last", 0))
        if last == 0:
            return None, None
        change = float(payload.get("change", 0))
        return last, change
    except:
        return None, None

# ==================== SIMULACIÓN (FALLBACK) ====================
BACKUP_PRICES = {"BTC": 1_070_000, "ETH": 28_000}
sim_prices = {"BTC": 1_070_000, "ETH": 28_000}

def get_simulated_price(symbol):
    last = sim_prices[symbol]
    new = last * (1 + random.uniform(-0.008, 0.008))
    new = max(BACKUP_PRICES[symbol]*0.9, min(BACKUP_PRICES[symbol]*1.1, new))
    sim_prices[symbol] = new
    return new, 0.0

# ==================== PERSISTENCIA ====================
STATE_FILE = "bot_state.json"

def save_state(state):
    to_save = {
        "balance": state["balance"],
        "positions": state["positions"],
        "trades": [(t.isoformat(), m) for t,m in state["trades"][-100:]],
        "price_history": {k: list(v) for k,v in state["price_history"].items()},
        "last_action": state["last_action"],
        "daily_trades": state["daily_trades"],
        "last_trade_day": state["last_trade_day"],
        "cycle": state["cycle"]
    }
    with open(STATE_FILE, "w") as f:
        json.dump(to_save, f)

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                if "price_history" not in data:
                    data["price_history"] = {"BTC": [], "ETH": []}
                return data
        except:
            pass
    return None

# ==================== SEÑAL INSTANTÁNEA (con solo 2 precios) ====================
def get_signal(price_history):
    """
    Retorna 'BUY' si el precio subió más de CHANGE_THRESHOLD% en el último ciclo,
    'SELL' si bajó más de CHANGE_THRESHOLD%,
    'HOLD' en caso contrario o si no hay suficientes datos.
    """
    if len(price_history) < 2:
        return "HOLD"
    last_change = (price_history[-1] - price_history[-2]) / price_history[-2] * 100
    if last_change >= CHANGE_THRESHOLD:
        return "BUY"
    elif last_change <= -CHANGE_THRESHOLD:
        return "SELL"
    else:
        return "HOLD"

# ==================== EJECUCIÓN DE ÓRDENES ====================
def can_trade(state):
    now_day = datetime.now().day
    if now_day != state["last_trade_day"]:
        state["daily_trades"] = 0
        state["last_trade_day"] = now_day
    return state["daily_trades"] < MAX_DAILY_TRADES

def execute_trade(symbol, action, price, state):
    if action == "BUY":
        if not can_trade(state):
            return None, "❌ Límite diario"
        amount = min(MAX_POSITION_SIZE_MXN, state["balance"])
        if amount <= 0:
            return None, "❌ Saldo insuficiente"
        eff_price = price * (1 + SLIPPAGE_PCT/100)
        commission = amount * COMMISSION_PCT/100
        qty = (amount - commission) / eff_price
        state["balance"] -= amount
        state["positions"][symbol] += qty
        state["daily_trades"] += 1
        msg = (f"🟢 *COMPRA* {symbol}\nCantidad: {qty:.6f}\nPrecio: ${eff_price:,.2f}\nComisión: ${commission:.2f}\nSaldo: ${state['balance']:.2f}")
        return qty, msg
    else:  # SELL
        qty = state["positions"].get(symbol, 0)
        if qty <= 0:
            return None, "❌ No hay posición"
        eff_price = price * (1 - SLIPPAGE_PCT/100)
        gross = qty * eff_price
        commission = gross * COMMISSION_PCT/100
        net = gross - commission
        state["balance"] += net
        state["positions"][symbol] = 0
        state["daily_trades"] += 1
        msg = (f"🔴 *VENTA* {symbol}\nCantidad: {qty:.6f}\nPrecio: ${eff_price:,.2f}\nComisión: ${commission:.2f}\nNeto: ${net:.2f}\nSaldo: ${state['balance']:.2f}")
        return qty, msg

# ==================== INICIALIZAR ESTADO ====================
saved = load_state()
if saved:
    state = saved
    state["price_history"] = {k: deque(v, maxlen=100) for k,v in state["price_history"].items()}
    state["trades"] = [(datetime.fromisoformat(ts), msg) for ts,msg in state.get("trades", [])]
else:
    state = {
        "balance": 1000.0,
        "positions": {"BTC": 0.0, "ETH": 0.0},
        "trades": [],
        "price_history": {"BTC": deque(maxlen=100), "ETH": deque(maxlen=100)},
        "last_action": {"BTC": None, "ETH": None},
        "daily_trades": 0,
        "last_trade_day": datetime.now().day,
        "cycle": 0
    }

# ==================== INTERFAZ STREAMLIT ====================
st.set_page_config(page_title="Bot Instantáneo (Solo Compra/Venta)", layout="wide")
st.title("⚡ Bot Instantáneo - Compra/Venta basado en cambio de precio")

st.sidebar.header("⚙️ Configuración")
refresh = st.sidebar.slider("Intervalo (segundos)", 5, 30, REFRESH_INTERVAL_SEC)
auto = st.sidebar.checkbox("Auto-refrescar", True)
change_th = st.sidebar.number_input("Umbral de cambio % (sube/baja para operar)", 0.0, 5.0, CHANGE_THRESHOLD, 0.05)

st.sidebar.subheader("💰 Cartera (MXN)")
st.sidebar.metric("Saldo", f"${state['balance']:,.2f}")
total = state['balance']
for s in ["BTC","ETH"]:
    p = state["last_prices"].get(s,0) if "last_prices" in state else 0
    q = state["positions"].get(s,0)
    if q>0 and p>0:
        total += q*p
st.sidebar.metric("Valor total", f"${total:,.2f}")
st.sidebar.metric("Ops hoy", state["daily_trades"])
if st.sidebar.button("Reiniciar"):
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
    st.rerun()
if st.sidebar.button("Prueba Telegram"):
    send_telegram("🧪 Alerta de prueba - Bot instantáneo")
    st.success("Enviado")

st.info(f"⚡ El bot opera con el cambio porcentual entre el precio actual y el anterior. Umbral actual: {change_th}%. Señal en cada ciclo (desde ciclo 2).")

# ==================== OBTENER DATOS ====================
btc_p, _ = get_bitso_ticker("btc_mxn")
eth_p, _ = get_bitso_ticker("eth_mxn")
if btc_p is None:
    btc_p, _ = get_simulated_price("BTC")
    eth_p, _ = get_simulated_price("ETH")
    fuente = "Simulación"
else:
    fuente = "Bitso real"

if "last_prices" not in state:
    state["last_prices"] = {"BTC": 0.0, "ETH": 0.0}
state["last_prices"]["BTC"] = btc_p
state["last_prices"]["ETH"] = eth_p
state["price_history"]["BTC"].append(btc_p)
state["price_history"]["ETH"].append(eth_p)

state["cycle"] += 1
if state["cycle"] % 10 == 0:
    save_state(state)
if state["cycle"] % HEARTBEAT_CYCLES == 0 and state["cycle"]>0:
    send_telegram(f"💓 Heartbeat ciclo {state['cycle']} | Fuente: {fuente}")

# ==================== LÓGICA DE COMPRA/VENTA ====================
for sym, price in [("BTC", btc_p), ("ETH", eth_p)]:
    hist = list(state["price_history"][sym])
    # Usar el umbral actual (puede cambiarse en la interfaz, pero aquí tomamos el valor del slider)
    # Para que sea dinámico, pasamos el umbral a la función, pero como la función está definida arriba,
    # la redefinimos localmente para usar el valor actual.
    def get_signal_with_threshold(hist, threshold):
        if len(hist) < 2:
            return "HOLD"
        change = (hist[-1] - hist[-2]) / hist[-2] * 100
        if change >= threshold:
            return "BUY"
        elif change <= -threshold:
            return "SELL"
        else:
            return "HOLD"
    
    signal = get_signal_with_threshold(hist, change_th)
    if signal == "HOLD":
        continue

    action = None
    if signal == "BUY" and state["positions"].get(sym, 0) == 0:
        action = "BUY"
    elif signal == "SELL" and state["positions"].get(sym, 0) > 0:
        action = "SELL"

    if action:
        qty, msg = execute_trade(sym, action, price, state)
        if msg:
            send_telegram(msg)
            state["trades"].append((datetime.now(), msg))
            save_state(state)
            if "last_action" not in state:
                state["last_action"] = {}
            state["last_action"][sym] = action

# ==================== DASHBOARD ====================
col1, col2 = st.columns(2)
with col1:
    st.subheader("📊 Señales en Vivo")
    rows = []
    for sym in ["BTC","ETH"]:
        name = "Bitcoin" if sym=="BTC" else "Ethereum"
        price = state["last_prices"].get(sym, 0)
        hist = list(state["price_history"][sym])
        if len(hist) >= 2:
            change = (hist[-1] - hist[-2]) / hist[-2] * 100
            if change >= change_th:
                sig = "🟢 COMPRAR"
            elif change <= -change_th:
                sig = "🔴 VENDER"
            else:
                sig = "⚪ MANTENER"
        else:
            change = 0.0
            sig = "⏳ Cargando..."
        rows.append({"Moneda": name, "Precio": f"${price:,.0f}", "Cambio %": f"{change:+.2f}%", "Señal": sig})
    st.table(rows)
    st.caption(f"Ciclo: {state['cycle']} | Fuente: {fuente} | Umbral: {change_th}%")
with col2:
    st.subheader("📜 Operaciones")
    for ts, msg in reversed(state["trades"][-15:]):
        st.text(f"{ts.strftime('%H:%M:%S')} - {msg[:70]}")
    st.caption("El bot opera con cambio de precio entre ciclos consecutivos (respuesta inmediata).")

if auto:
    time.sleep(refresh)
    st.rerun()
