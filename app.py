import streamlit as st
import requests
import time
import json
import os
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
THRESHOLD = 0.1          # 0.1% de cambio para activar compra/venta
REFRESH_INTERVAL = 10    # segundos (no menos de 10 para no saturar API)
MAX_POSITION_SIZE = 500.0
MAX_DAILY_TRADES = 20
COMMISSION = 0.1
SLIPPAGE = 0.05

# ==================== PRECIOS REALES DESDE CRYPTOCOMPARE ====================
def get_cryptocompare_price(symbol):
    """
    symbol: 'BTC' o 'ETH'
    Retorna precio en MXN (float) o None si falla.
    """
    try:
        url = f"https://min-api.cryptocompare.com/data/price?fsym={symbol}&tsyms=MXN"
        resp = requests.get(url, timeout=5)
        if resp.status_code != 200:
            return None
        data = resp.json()
        price = data.get("MXN")
        if price and price > 0:
            return float(price)
        return None
    except Exception as e:
        print(f"Error obteniendo precio de {symbol}: {e}")
        return None

# ==================== PERSISTENCIA ====================
STATE_FILE = "bot_state.json"

def save_state(state):
    to_save = {
        "balance": state["balance"],
        "positions": state["positions"],
        "trades": [(ts.isoformat(), msg) for ts, msg in state["trades"]],
        "last_action": state["last_action"],
        "daily_trades": state["daily_trades"],
        "last_day": state["last_day"],
        "cycle": state["cycle"],
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
        "last_price": {"BTC": 0.0, "ETH": 0.0},
        "ref_price": {"BTC": 0.0, "ETH": 0.0}
    }

# ==================== INTERFAZ STREAMLIT ====================
st.set_page_config(page_title="Bot con Precios Reales (Cryptocompare)", layout="wide")
st.title("📈 Bot con Precios Reales de Cryptocompare (MXN)")

st.sidebar.header("Configuración")
interval = st.sidebar.slider("Intervalo (segundos)", 10, 60, REFRESH_INTERVAL)
auto = st.sidebar.checkbox("Auto-refrescar", True)
umbral = st.sidebar.number_input("Umbral de cambio %", 0.05, 2.0, THRESHOLD, 0.05)

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
    send_telegram("🧪 Bot con precios reales - funcionando")
    st.success("Enviado")

st.info(f"⚠️ Los precios son REALES obtenidos de Cryptocompare (BTC/MXN y ETH/MXN). Umbral: {umbral}%. Intervalo: {interval}s. No hay simulación ni inyección artificial.")

# ==================== OBTENER PRECIOS REALES ====================
btc = get_cryptocompare_price("BTC")
eth = get_cryptocompare_price("ETH")

if btc is None or eth is None:
    st.error("❌ No se pudieron obtener precios reales. Verifica tu conexión a Internet o la API de Cryptocompare.")
    st.stop()

# Mostrar precios obtenidos
st.success(f"✅ Precios reales: BTC = ${btc:,.2f} MXN, ETH = ${eth:,.2f} MXN")

# Actualizar estado
state["last_price"]["BTC"] = btc
state["last_price"]["ETH"] = eth

# Establecer precio de referencia (solo la primera vez)
if state["ref_price"]["BTC"] == 0:
    state["ref_price"]["BTC"] = btc
    state["ref_price"]["ETH"] = eth

state["cycle"] += 1

# Calcular cambio porcentual desde el precio de referencia
cambio = {}
for sym in ["BTC", "ETH"]:
    ref = state["ref_price"].get(sym, state["last_price"][sym])
    precio = state["last_price"][sym]
    cambio[sym] = (precio - ref) / ref * 100 if ref != 0 else 0

# Guardar estado cada 10 ciclos
if state["cycle"] % 10 == 0:
    save_state(state)

# ==================== LÓGICA DE COMPRA/VENTA ====================
hoy = datetime.now().day
if hoy != state["last_day"]:
    state["daily_trades"] = 0
    state["last_day"] = hoy

for sym, precio in [("BTC", btc), ("ETH", eth)]:
    var = cambio[sym]
    if var >= umbral:
        senal = "BUY"
    elif var <= -umbral:
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
            msg = f"🟢 *COMPRA* {sym}\nCantidad: {qty:.6f}\nPrecio real: ${precio:,.2f}\nEfectivo: ${eff:,.2f}\nComisión: ${com:.2f}\nSaldo: ${state['balance']:.2f}"
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
            msg = f"🔴 *VENTA* {sym}\nCantidad: {qty:.6f}\nPrecio real: ${precio:,.2f}\nEfectivo: ${eff:,.2f}\nComisión: ${com:.2f}\nNeto: ${net:.2f}\nSaldo: ${state['balance']:.2f}"
            send_telegram(msg)
            state["trades"].append((datetime.now(), msg))
            save_state(state)

# ==================== DASHBOARD ====================
col1, col2 = st.columns(2)
with col1:
    st.subheader("📊 Señales en Vivo (precios reales)")
    rows = []
    for sym in ["BTC", "ETH"]:
        name = "Bitcoin" if sym == "BTC" else "Ethereum"
        precio = state["last_price"].get(sym, 0)
        var = cambio[sym]
        if var >= umbral:
            sig = "🟢 COMPRAR"
        elif var <= -umbral:
            sig = "🔴 VENDER"
        else:
            sig = "⚪ MANTENER"
        rows.append({"Moneda": name, "Precio MXN": f"${precio:,.0f}", "Var desde inicio": f"{var:+.2f}%", "Señal": sig})
    st.table(rows)
    st.caption(f"Ciclo: {state['cycle']} | Umbral: {umbral}% | Fuente: Cryptocompare")
with col2:
    st.subheader("📜 Historial de Operaciones")
    for ts, msg in reversed(state["trades"][-10:]):
        st.text(f"{ts.strftime('%H:%M:%S')} - {msg[:60]}")

if auto:
    time.sleep(interval)
    st.rerun()
