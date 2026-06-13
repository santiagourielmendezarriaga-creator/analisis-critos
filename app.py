import streamlit as st
import requests
import time
import json
import os
import random
from datetime import datetime
from collections import deque

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
THRESHOLD = 0.1
REFRESH_INTERVAL = 5
MAX_POSITION_SIZE = 500.0
MAX_DAILY_TRADES = 20
COMMISSION = 0.1
SLIPPAGE = 0.05

# ==================== BITSO / SIMULACIÓN ====================
def get_bitso_price(book="btc_mxn"):
    try:
        url = f"https://api.bitso.com/api/v3/ticker/?book={book}"
        r = requests.get(url, timeout=3)
        if r.status_code != 200:
            return None
        data = r.json()
        payload = data.get("payload")
        if not payload:
            return None
        last = float(payload.get("last", 0))
        return last if last > 0 else None
    except:
        return None

BACKUP = {"BTC": 1_070_000, "ETH": 28_000}
sim = {"BTC": 1_070_000, "ETH": 28_000}
def get_simulated_price(symbol):
    sim[symbol] *= (1 + random.uniform(-0.005, 0.005))
    sim[symbol] = max(BACKUP[symbol]*0.95, min(BACKUP[symbol]*1.05, sim[symbol]))
    return sim[symbol]

# ==================== PERSISTENCIA (SIN ERRORES JSON) ====================
STATE_FILE = "bot_state.json"

def save_state(state):
    # Convertir objetos no serializables a JSON
    to_save = {
        "balance": state["balance"],
        "positions": state["positions"],
        "trades": [(ts.isoformat(), msg) for ts, msg in state["trades"]],
        "last_action": state["last_action"],
        "daily_trades": state["daily_trades"],
        "last_day": state["last_day"],
        "cycle": state["cycle"],
        "price_history": {k: list(v) for k, v in state["price_history"].items()},
        "last_price": state["last_price"],
        "ref_price": state["ref_price"]
    }
    with open(STATE_FILE, "w") as f:
        json.dump(to_save, f)

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
            # Restaurar deques y datetime
            data["price_history"] = {k: deque(v, maxlen=10) for k, v in data["price_history"].items()}
            data["trades"] = [(datetime.fromisoformat(ts), msg) for ts, msg in data["trades"]]
            return data
        except:
            pass
    return None

# ==================== INICIALIZAR ESTADO ====================
saved = load_state()
if saved:
    state = saved
else:
    state = {
        "balance": 1000.0,
        "positions": {"BTC": 0.0, "ETH": 0.0},
        "trades": [],
        "last_action": {"BTC": None, "ETH": None},
        "daily_trades": 0,
        "last_day": datetime.now().day,
        "cycle": 0,
        "price_history": {"BTC": deque(maxlen=10), "ETH": deque(maxlen=10)},
        "last_price": {"BTC": 0.0, "ETH": 0.0},
        "ref_price": {"BTC": 0.0, "ETH": 0.0}
    }

# ==================== INTERFAZ ====================
st.set_page_config(page_title="Bot Señal Instantánea", layout="wide")
st.title("⚡ Bot Señal Instantánea (precio inicial)")

st.sidebar.header("Configuración")
interval = st.sidebar.slider("Intervalo (segundos)", 3, 20, REFRESH_INTERVAL)
auto = st.sidebar.checkbox("Auto-refrescar", True)
umbral = st.sidebar.number_input("Umbral de cambio %", 0.01, 1.0, THRESHOLD, 0.01)
inyectar = st.sidebar.checkbox("Forzar movimiento artificial", value=True)

st.sidebar.subheader("Cartera")
st.sidebar.metric("Saldo MXN", f"${state['balance']:,.2f}")
total = state['balance']
for s in ["BTC", "ETH"]:
    p = state["last_price"].get(s, 0)
    q = state["positions"].get(s, 0)
    if q > 0 and p > 0:
        total += q * p
st.sidebar.metric("Valor total", f"${total:,.2f}")
st.sidebar.metric("Ops hoy", state["daily_trades"])

if st.sidebar.button("Reiniciar"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
    st.rerun()
if st.sidebar.button("Prueba Telegram"):
    send_telegram("🧪 Bot instantáneo")
    st.success("Enviado")

st.info(f"⚡ Señal: compara precio actual con precio inicial. Umbral: {umbral}%. Intervalo: {interval}s. Inyección activada: {inyectar}")

# ==================== OBTENER PRECIOS ====================
btc = get_bitso_price("btc_mxn")
eth = get_bitso_price("eth_mxn")
if btc is None:
    btc = get_simulated_price("BTC")
    eth = get_simulated_price("ETH")
    fuente = "Simulación"
else:
    fuente = "Bitso real"

state["last_price"]["BTC"] = btc
state["last_price"]["ETH"] = eth
state["price_history"]["BTC"].append(btc)
state["price_history"]["ETH"].append(eth)

# Referencia inicial
if state["ref_price"]["BTC"] == 0:
    state["ref_price"]["BTC"] = btc
    state["ref_price"]["ETH"] = eth

state["cycle"] += 1

# Calcular cambio (real y con inyección)
cambio_real = {}
cambio_efectivo = {}
for sym in ["BTC", "ETH"]:
    ref = state["ref_price"].get(sym, state["last_price"][sym])
    precio = state["last_price"][sym]
    cambio = (precio - ref) / ref * 100 if ref != 0 else 0
    cambio_real[sym] = cambio
    cambio_efectivo[sym] = cambio
    if inyectar and abs(cambio) < 0.01:
        artificial = random.uniform(-0.2, 0.2)
        cambio_efectivo[sym] = cambio + artificial
        st.info(f"⚠️ {sym}: inyección {artificial:+.2f}% → cambio efectivo {cambio_efectivo[sym]:+.2f}%")

# Guardar estado cada 10 ciclos
if state["cycle"] % 10 == 0:
    save_state(state)

# ==================== LÓGICA DE COMPRA/VENTA ====================
hoy = datetime.now().day
if hoy != state["last_day"]:
    state["daily_trades"] = 0
    state["last_day"] = hoy

for sym, precio in [("BTC", btc), ("ETH", eth)]:
    cambio = cambio_efectivo[sym]
    if cambio >= umbral:
        senal = "BUY"
    elif cambio <= -umbral:
        senal = "SELL"
    else:
        senal = "HOLD"

    action = None
    if senal == "BUY" and state["positions"].get(sym, 0) == 0 and state["daily_trades"] < MAX_DAILY_TRADES:
        action = "BUY"
    elif senal == "SELL" and state["positions"].get(sym, 0) > 0 and state["daily_trades"] < MAX_DAILY_TRADES:
        action = "SELL"

    if action == "BUY":
        amount = min(MAX_POSITION_SIZE, state["balance"])
        if amount > 0:
            eff = precio * (1 + SLIPPAGE/100)
            com = amount * COMMISSION/100
            qty = (amount - com) / eff
            state["balance"] -= amount
            state["positions"][sym] = state["positions"].get(sym, 0) + qty
            state["daily_trades"] += 1
            msg = f"🟢 *COMPRA* {sym}\nCantidad: {qty:.6f}\nPrecio: ${eff:,.2f}\nComisión: ${com:.2f}\nSaldo: ${state['balance']:.2f}"
            send_telegram(msg)
            state["trades"].append((datetime.now(), msg))
            save_state(state)
    elif action == "SELL":
        qty = state["positions"].get(sym, 0)
        if qty > 0:
            eff = precio * (1 - SLIPPAGE/100)
            gross = qty * eff
            com = gross * COMMISSION/100
            net = gross - com
            state["balance"] += net
            state["positions"][sym] = 0
            state["daily_trades"] += 1
            msg = f"🔴 *VENTA* {sym}\nCantidad: {qty:.6f}\nPrecio: ${eff:,.2f}\nComisión: ${com:.2f}\nNeto: ${net:.2f}\nSaldo: ${state['balance']:.2f}"
            send_telegram(msg)
            state["trades"].append((datetime.now(), msg))
            save_state(state)

# ==================== DASHBOARD ====================
col1, col2 = st.columns(2)
with col1:
    st.subheader("📊 Señales en Vivo")
    rows = []
    for sym in ["BTC", "ETH"]:
        name = "Bitcoin" if sym == "BTC" else "Ethereum"
        precio = state["last_price"].get(sym, 0)
        cambio = cambio_real[sym]
        if cambio >= umbral:
            sig = "🟢 COMPRAR"
        elif cambio <= -umbral:
            sig = "🔴 VENDER"
        else:
            sig = "⚪ MANTENER"
        rows.append({"Moneda": name, "Precio": f"${precio:,.0f}", "Var%": f"{cambio:+.2f}%", "Señal": sig})
    st.table(rows)
    st.metric("Fuente", fuente)
    st.caption(f"Ciclo: {state['cycle']} | Umbral: {umbral}% | Inyección: {'ON' if inyectar else 'OFF'}")
with col2:
    st.subheader("📜 Historial")
    for ts, msg in reversed(state["trades"][-10:]):
        st.text(f"{ts.strftime('%H:%M:%S')} - {msg[:60]}")

if auto:
    time.sleep(interval)
    st.rerun()
