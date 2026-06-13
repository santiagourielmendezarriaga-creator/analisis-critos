import streamlit as st
import requests
import time
import json
import os
import random
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
THRESHOLD = 0.05          # 0.05% (más sensible)
MAX_POSITION_SIZE_MXN = 500.0
MAX_DAILY_TRADES = 200
COMMISSION_PCT = 0.1
SLIPPAGE_PCT = 0.05
REFRESH_INTERVAL_SEC = 5
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
        return last, 0.0
    except:
        return None, None

# ==================== SIMULACIÓN ====================
BACKUP_PRICES = {"BTC": 1_070_000, "ETH": 28_000}
sim_prices = {"BTC": 1_070_000, "ETH": 28_000}

def get_simulated_price(symbol):
    last = sim_prices[symbol]
    new = last * (1 + random.uniform(-0.005, 0.005))
    new = max(BACKUP_PRICES[symbol]*0.95, min(BACKUP_PRICES[symbol]*1.05, new))
    sim_prices[symbol] = new
    return new, 0.0

# ==================== PERSISTENCIA ====================
STATE_FILE = "bot_state.json"

def save_state(state):
    to_save = {
        "balance": state["balance"],
        "positions": state["positions"],
        "trades": [(t.isoformat(), m) for t,m in state["trades"][-100:]],
        "last_action": state.get("last_action", {}),
        "daily_trades": state["daily_trades"],
        "last_trade_day": state["last_trade_day"],
        "cycle": state["cycle"],
        "last_price": state.get("last_price", {})
    }
    with open(STATE_FILE, "w") as f:
        json.dump(to_save, f)

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return None

# ==================== EJECUCIÓN ====================
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
        state["positions"][symbol] = state["positions"].get(symbol, 0) + qty
        state["daily_trades"] += 1
        msg = (f"🟢 *COMPRA* {symbol}\nCantidad: {qty:.6f}\nPrecio: ${eff_price:,.2f}\nComisión: ${commission:.2f}\nSaldo: ${state['balance']:.2f}")
        return qty, msg
    else:
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

# ==================== INICIALIZAR ====================
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
        "last_price": {}
    }

# ==================== INTERFAZ ====================
st.set_page_config(page_title="Bot con Inyección Fuerte", layout="wide")
st.title("⚡ Bot: COMPRA si sube, VENDE si baja (con inyección artificial)")

st.sidebar.header("⚙️ Configuración")
refresh = st.sidebar.slider("Intervalo (segundos)", 3, 20, REFRESH_INTERVAL_SEC)
auto = st.sidebar.checkbox("Auto-refrescar", True)
umbral = st.sidebar.number_input("Umbral de cambio %", 0.01, 1.0, THRESHOLD, 0.01)
inyectar = st.sidebar.checkbox("Forzar movimiento artificial (si mercado plano)", value=True)

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
if st.sidebar.button("Reiniciar"):
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
    st.rerun()
if st.sidebar.button("Prueba Telegram"):
    send_telegram("🧪 Bot con inyección fuerte")
    st.success("Enviado")

st.info(f"⚡ Umbral: {umbral}%. Inyección añade hasta ±0.2% de movimiento si el mercado no varía. Después del ciclo 2 empezarás a ver señales.")

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
if "last_price" not in state:
    state["last_price"] = {"BTC": btc_p, "ETH": eth_p}

state["last_prices"]["BTC"] = btc_p
state["last_prices"]["ETH"] = eth_p

state["cycle"] += 1
if state["cycle"] % 10 == 0:
    save_state(state)
if state["cycle"] % HEARTBEAT_CYCLES == 0 and state["cycle"]>0:
    send_telegram(f"💓 Heartbeat ciclo {state['cycle']} | Fuente: {fuente}")

# ==================== LÓGICA DE SEÑAL ====================
for sym, price in [("BTC", btc_p), ("ETH", eth_p)]:
    prev = state["last_price"].get(sym, price)
    if prev == 0:
        state["last_price"][sym] = price
        continue
    cambio = (price - prev) / prev * 100
    # Inyección más fuerte: hasta ±0.2%
    if inyectar and abs(cambio) < 0.01:
        artificial = random.uniform(-0.2, 0.2)
        cambio += artificial
        st.info(f"⚠️ {sym}: inyección {artificial:+.2f}% → cambio efectivo {cambio:+.2f}%")
    state["last_price"][sym] = price

    # Decisión
    if cambio >= umbral:
        senal = "BUY"
    elif cambio <= -umbral:
        senal = "SELL"
    else:
        senal = "HOLD"

    action = None
    if senal == "BUY" and state["positions"].get(sym, 0) == 0:
        action = "BUY"
    elif senal == "SELL" and state["positions"].get(sym, 0) > 0:
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
        # Mostrar el cambio real (sin inyección) pero la señal es la que se usó
        prev = state["last_price"].get(sym, price)
        cambio_real = (price - prev) / prev * 100 if prev != 0 else 0
        # Recalcular señal con el cambio real para mostrar (opcional)
        if cambio_real >= umbral:
            sig = "🟢 COMPRAR"
        elif cambio_real <= -umbral:
            sig = "🔴 VENDER"
        else:
            sig = "⚪ MANTENER"
        rows.append({"Moneda": name, "Precio": f"${price:,.0f}", "Var real": f"{cambio_real:+.2f}%", "Señal": sig})
    st.table(rows)
    st.metric("Fuente de datos", fuente)
    st.caption(f"Ciclo: {state['cycle']} | Umbral: {umbral}% | Inyección: {'Activada' if inyectar else 'Desactivada'}")
with col2:
    st.subheader("📜 Historial de Operaciones")
    if state["trades"]:
        for ts, msg in reversed(state["trades"][-15:]):
            st.text(f"{ts.strftime('%H:%M:%S')} - {msg[:70]}")
    else:
        st.caption("Aún no hay operaciones. Espera a que pasen al menos 2 ciclos (10 segundos).")

if auto:
    time.sleep(refresh)
    st.rerun()
