import streamlit as st
import random
import time
import json
import os
from collections import deque
from datetime import datetime

# ==================== TELEGRAM ====================
TELEGRAM_TOKEN = "8532857017:AAHwLhRnM3oC6TbgFFKAEmQnZVoo6JD_esQ"
TELEGRAM_CHAT_ID = "5835990242"

def send_telegram(msg):
    try:
        import requests
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=3)
    except:
        pass

# ==================== PARÁMETROS ====================
MAX_POSITION_SIZE_MXN = 500.0
MAX_DAILY_TRADES = 200
COMMISSION_PCT = 0.1
SLIPPAGE_PCT = 0.05
REFRESH_INTERVAL_SEC = 5

# ==================== SIMULACIÓN CON SEÑAL FORZADA ====================
# Alterna entre subida y bajada para generar señales continuas
phase = 0
prices = {"BTC": 1_070_000, "ETH": 28_000}

def get_forced_price(symbol):
    global phase
    phase += 1
    # Alterna entre +0.2% y -0.2% cada ciclo
    change = 0.2 if phase % 2 == 0 else -0.2
    new_price = prices[symbol] * (1 + change / 100)
    prices[symbol] = new_price
    return new_price, change

# ==================== PERSISTENCIA ====================
STATE_FILE = "bot_state.json"

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return None

# ==================== EJECUCIÓN DE ÓRDENES ====================
def can_trade(state):
    now_day = datetime.now().day
    if now_day != state.get("last_trade_day", now_day):
        state["daily_trades"] = 0
        state["last_trade_day"] = now_day
    return state.get("daily_trades", 0) < MAX_DAILY_TRADES

def execute_trade(symbol, action, price, state):
    if action == "BUY":
        if not can_trade(state):
            return None, "❌ Límite diario"
        amount = min(MAX_POSITION_SIZE_MXN, state.get("balance", 1000.0))
        if amount <= 0:
            return None, "❌ Saldo insuficiente"
        eff_price = price * (1 + SLIPPAGE_PCT/100)
        commission = amount * COMMISSION_PCT/100
        qty = (amount - commission) / eff_price
        state["balance"] = state.get("balance", 1000.0) - amount
        state["positions"][symbol] = state["positions"].get(symbol, 0) + qty
        state["daily_trades"] = state.get("daily_trades", 0) + 1
        msg = (f"🟢 *COMPRA* {symbol}\nQty: {qty:.6f}\nPrecio: ${eff_price:,.2f}\nComisión: ${commission:.2f}\nSaldo: ${state['balance']:.2f}")
        return qty, msg
    else:
        qty = state["positions"].get(symbol, 0)
        if qty <= 0:
            return None, "❌ No hay posición"
        eff_price = price * (1 - SLIPPAGE_PCT/100)
        gross = qty * eff_price
        commission = gross * COMMISSION_PCT/100
        net = gross - commission
        state["balance"] = state.get("balance", 1000.0) + net
        state["positions"][symbol] = 0
        state["daily_trades"] = state.get("daily_trades", 0) + 1
        msg = (f"🔴 *VENTA* {symbol}\nQty: {qty:.6f}\nPrecio: ${eff_price:,.2f}\nComisión: ${commission:.2f}\nNeto: ${net:.2f}\nSaldo: ${state['balance']:.2f}")
        return qty, msg

# ==================== INICIALIZAR ESTADO ====================
saved = load_state()
if saved:
    state = saved
    state["trades"] = [(datetime.fromisoformat(ts), msg) for ts,msg in state.get("trades", [])]
else:
    state = {
        "balance": 1000.0,
        "positions": {"BTC": 0.0, "ETH": 0.0},
        "trades": [],
        "last_action": {"BTC": None, "ETH": None},
        "daily_trades": 0,
        "last_trade_day": datetime.now().day,
        "cycle": 0,
        "ref_price": {}
    }

# ==================== INTERFAZ ====================
st.set_page_config(page_title="Bot Demostración (Señal Forzada)", layout="wide")
st.title("⚡ Bot Demostración - Señal Garantizada en cada ciclo")

st.sidebar.header("⚙️ Configuración")
refresh = st.sidebar.slider("Intervalo (segundos)", 3, 20, REFRESH_INTERVAL_SEC)
auto = st.sidebar.checkbox("Auto-refrescar", True)

st.sidebar.subheader("💰 Cartera (MXN)")
st.sidebar.metric("Saldo", f"${state['balance']:,.2f}")
total = state['balance']
for s in ["BTC","ETH"]:
    p = state.get("last_prices", {}).get(s, 0)
    q = state["positions"].get(s, 0)
    if q>0 and p>0:
        total += q*p
st.sidebar.metric("Valor total", f"${total:,.2f}")
st.sidebar.metric("Ops hoy", state["daily_trades"])
if st.sidebar.button("Reiniciar simulación"):
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
    st.rerun()
if st.sidebar.button("Prueba Telegram"):
    send_telegram("🧪 Alerta - Modo demostración")
    st.success("Enviado")

st.info("⚡ Modo DEMOSTRACIÓN: los precios suben y bajan artificialmente cada ciclo para generar señales de compra/venta inmediatas.")

# ==================== OBTENER DATOS FORZADOS ====================
btc_p, btc_c = get_forced_price("BTC")
eth_p, eth_c = get_forced_price("ETH")

if "last_prices" not in state:
    state["last_prices"] = {"BTC": 0.0, "ETH": 0.0}
state["last_prices"]["BTC"] = btc_p
state["last_prices"]["ETH"] = eth_p

if "ref_price" not in state:
    state["ref_price"] = {"BTC": btc_p, "ETH": eth_p}

state["cycle"] = state.get("cycle", 0) + 1
if state["cycle"] % 10 == 0:
    save_state(state)

# ==================== SEÑAL ====================
for sym, price in [("BTC", btc_p), ("ETH", eth_p)]:
    ref = state["ref_price"].get(sym, price)
    cambio = (price - ref) / ref * 100
    # Forzar señal si el cambio es positivo o negativo (siempre lo será con la alternancia)
    if cambio > 0:
        signal = "BUY"
    elif cambio < 0:
        signal = "SELL"
    else:
        signal = "HOLD"

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
    st.subheader("📊 Señales en Vivo (demostración)")
    rows = []
    for sym in ["BTC","ETH"]:
        name = "Bitcoin" if sym=="BTC" else "Ethereum"
        price = state["last_prices"].get(sym, 0)
        ref = state["ref_price"].get(sym, price)
        cambio = (price - ref) / ref * 100 if ref != 0 else 0
        signal = "🟢 COMPRAR" if cambio > 0 else "🔴 VENDER" if cambio < 0 else "⚪ MANTENER"
        rows.append({"Moneda": name, "Precio": f"${price:,.0f}", "Variación": f"{cambio:+.2f}%", "Señal": signal})
    st.table(rows)
    st.caption(f"Ciclo: {state['cycle']} | Modo demostración - Señal cambia cada ciclo")
with col2:
    st.subheader("📜 Operaciones")
    for ts, msg in reversed(state["trades"][-15:]):
        st.text(f"{ts.strftime('%H:%M:%S')} - {msg[:70]}")
    st.caption("En cada ciclo, el bot compra o vende alternativamente.")

if auto:
    time.sleep(refresh)
    st.rerun()
