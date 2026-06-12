import streamlit as st
import requests
import time
import json
import os
import random
from collections import deque
from datetime import datetime

# ==================== CONFIGURACIÓN TELEGRAM ====================
TELEGRAM_TOKEN = "8532857017:AAHwLhRnM3oC6TbgFFKAEmQnZVoo6JD_esQ"
TELEGRAM_CHAT_ID = "5835990242"

def send_telegram(msg, parse_mode="Markdown"):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": parse_mode}
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except:
        return False

# ==================== OBTENER DATOS DE BITSO (REALES) ====================
def get_bitso_ticker(book="btc_mxn"):
    """Devuelve (precio, cambio_porcentaje_24h) o (None, None) si falla."""
    try:
        # Obtener ticker
        url_ticker = f"https://api.bitso.com/api/v3/ticker/?book={book}"
        resp = requests.get(url_ticker, timeout=10)
        if resp.status_code != 200:
            return None, None
        data = resp.json()
        payload = data.get("payload")
        if not payload:
            return None, None
        last = float(payload.get("last", 0))
        if last == 0:
            return None, None

        # Obtener cambio porcentual usando la vela de 24h
        url_ohlc = f"https://api.bitso.com/api/v3/ohlc/?book={book}&time_window=24_hours"
        resp_ohlc = requests.get(url_ohlc, timeout=10)
        if resp_ohlc.status_code == 200:
            ohlc_data = resp_ohlc.json()
            if ohlc_data.get("payload") and len(ohlc_data["payload"]) > 0:
                open_24h = float(ohlc_data["payload"][0]["open"])
                change_pct = (last - open_24h) / open_24h * 100
                return last, change_pct
        return last, 0.0
    except Exception as e:
        print(f"Bitso error: {e}")
        return None, None

def get_fear_greed():
    try:
        resp = requests.get("https://api.alternative.me/fng/", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return int(data["data"][0]["value"]), data["data"][0]["value_classification"]
    except:
        pass
    return 50, "Neutral"

# ==================== SIMULACIÓN DE RESPALDO ====================
BACKUP_PRICES = {"BTC": 1_070_000, "ETH": 28_000}
backup_prices = {"BTC": 1_070_000, "ETH": 28_000}
backup_changes = {"BTC": 0.0, "ETH": 0.0}

def get_simulated_price(symbol):
    base = BACKUP_PRICES[symbol]
    last = backup_prices.get(symbol, base)
    change_pct = random.uniform(-0.008, 0.008)
    new_price = last * (1 + change_pct)
    new_price = max(base * 0.9, min(base * 1.1, new_price))
    sim_change = backup_changes.get(symbol, 0.0) + random.uniform(-0.2, 0.2)
    sim_change = max(-5, min(5, sim_change))
    backup_prices[symbol] = new_price
    backup_changes[symbol] = sim_change
    return new_price, sim_change

# ==================== PARÁMETROS ====================
BUY_THRESHOLD = 55
SELL_THRESHOLD = 45
STOP_LOSS_PCT = 2.0
TAKE_PROFIT_PCT = 3.0
TRAILING_STOP_PCT = 1.5
MAX_POSITION_SIZE_MXN = 500.0
MAX_DAILY_TRADES = 100
COMMISSION_PCT = 0.1
SLIPPAGE_PCT = 0.05
REFRESH_INTERVAL_SEC = 30
HEARTBEAT_CYCLES = 30
MIN_HISTORY_LEN = 2

# ==================== INDICADORES ====================
def calculate_score(price, change_24h, fear, price_history):
    score = 50
    score += (50 - fear) * 0.4
    score += change_24h * 1.2
    if len(price_history) >= 2:
        trend = price_history[-1] - price_history[-2]
        score += 8 if trend > 0 else -8
    return max(0, min(100, score))

# ==================== PERSISTENCIA ====================
STATE_FILE = "bot_state.json"

def save_state(state):
    # Convertir deques y datetime a estructuras JSON
    to_save = {
        "balance": state["balance"],
        "positions": state["positions"],
        "trades": [(t.isoformat(), m) for t, m in state["trades"][-100:]],
        "price_history": {k: list(v) for k, v in state["price_history"].items()},
        "last_action": state["last_action"],
        "last_prices": state["last_prices"],
        "entry_price": state["entry_price"],
        "highest_price": state["highest_price"],
        "daily_trades": state["daily_trades"],
        "last_trade_day": state["last_trade_day"],
        "cycle": state["cycle"],
        "last_score": state["last_score"]
    }
    with open(STATE_FILE, "w") as f:
        json.dump(to_save, f, indent=2)

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                # Asegurar claves faltantes (para compatibilidad)
                if "last_score" not in data:
                    data["last_score"] = {"BTC": 50, "ETH": 50}
                if "price_history" not in data:
                    data["price_history"] = {"BTC": [], "ETH": []}
                if "trades" not in data:
                    data["trades"] = []
                return data
        except:
            pass
    return None

# ==================== GESTIÓN DE RIESGO ====================
def can_trade(state):
    now_day = datetime.now().day
    if now_day != state["last_trade_day"]:
        state["daily_trades"] = 0
        state["last_trade_day"] = now_day
    return state["daily_trades"] < MAX_DAILY_TRADES

def execute_trade(symbol, action, price, state, exit_reason=""):
    if action == "BUY":
        if not can_trade(state):
            return None, "❌ Límite diario alcanzado"
        amount = min(MAX_POSITION_SIZE_MXN, state["balance"])
        if amount <= 0:
            return None, "❌ Saldo insuficiente"
        eff_price = price * (1 + SLIPPAGE_PCT / 100)
        commission = amount * COMMISSION_PCT / 100
        qty = (amount - commission) / eff_price
        state["balance"] -= amount
        state["positions"][symbol] += qty
        state["entry_price"][symbol] = eff_price
        state["highest_price"][symbol] = eff_price
        state["daily_trades"] += 1
        msg = (f"🟢 *COMPRA* {symbol}\nCantidad: {qty:.6f}\nPrecio: ${eff_price:,.2f} MXN\nComisión: ${commission:.2f}\nSaldo: ${state['balance']:.2f}")
        if exit_reason:
            msg += f"\n*Motivo:* {exit_reason}"
        return qty, msg
    else:
        qty = state["positions"].get(symbol, 0)
        if qty <= 0:
            return None, "❌ No hay posición"
        eff_price = price * (1 - SLIPPAGE_PCT / 100)
        gross = qty * eff_price
        commission = gross * COMMISSION_PCT / 100
        net = gross - commission
        state["balance"] += net
        state["positions"][symbol] = 0
        state["daily_trades"] += 1
        msg = (f"🔴 *VENTA* {symbol}\nCantidad: {qty:.6f}\nPrecio: ${eff_price:,.2f}\nComisión: ${commission:.2f}\nNeto: ${net:.2f}\nSaldo: ${state['balance']:.2f}")
        if exit_reason:
            msg += f"\n*Motivo:* {exit_reason}"
        return qty, msg

# ==================== INICIALIZAR ESTADO ====================
saved = load_state()
if saved:
    state = saved
    # Restaurar deques
    state["price_history"] = {k: deque(v, maxlen=100) for k, v in state["price_history"].items()}
    state["trades"] = [(datetime.fromisoformat(ts), msg) for ts, msg in state.get("trades", [])]
else:
    state = {
        "balance": 1000.0,
        "positions": {"BTC": 0.0, "ETH": 0.0},
        "trades": [],
        "price_history": {"BTC": deque(maxlen=100), "ETH": deque(maxlen=100)},
        "last_action": {"BTC": None, "ETH": None},
        "last_prices": {"BTC": 0.0, "ETH": 0.0},
        "entry_price": {"BTC": 0.0, "ETH": 0.0},
        "highest_price": {"BTC": 0.0, "ETH": 0.0},
        "daily_trades": 0,
        "last_trade_day": datetime.now().day,
        "cycle": 0,
        "last_score": {"BTC": 50, "ETH": 50}
    }

# ==================== INTERFAZ STREAMLIT ====================
st.set_page_config(page_title="Crypto Bot - Bitso Real (MXN)", layout="wide")
st.title("🤖 Crypto Bot - Datos Reales de Bitso (MXN)")

st.sidebar.header("⚙️ Configuración")
refresh = st.sidebar.slider("Intervalo (segundos)", 10, 60, REFRESH_INTERVAL_SEC)
auto = st.sidebar.checkbox("Auto-refrescar", value=True)
buy_th = st.sidebar.number_input("Compra si score ≥", 0, 100, BUY_THRESHOLD)
sell_th = st.sidebar.number_input("Vende si score ≤", 0, 100, SELL_THRESHOLD)

st.sidebar.subheader("💰 Cartera (MXN)")
st.sidebar.metric("Saldo MXN", f"${state['balance']:,.2f}")
total_val = state['balance']
for sym in ["BTC", "ETH"]:
    p = state["last_prices"].get(sym, 0)
    q = state["positions"].get(sym, 0)
    if q > 0 and p > 0:
        total_val += q * p
st.sidebar.metric("Valor total", f"${total_val:,.2f}")
st.sidebar.metric("Operaciones hoy", state["daily_trades"])

if st.sidebar.button("Reiniciar simulación (1000 MXN)"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
    st.rerun()

if st.sidebar.button("📢 Enviar alerta de prueba"):
    send_telegram("🧪 Alerta de prueba - Bot con Bitso real")
    st.success("Alerta enviada")

st.info("✅ Obteniendo datos reales de Bitso (BTC/MXN y ETH/MXN). Si falla, usa simulación realista.")

# ==================== OBTENER DATOS REALES ====================
btc_price, btc_change = get_bitso_ticker("btc_mxn")
eth_price, eth_change = get_bitso_ticker("eth_mxn")

if btc_price is None:
    btc_price, btc_change = get_simulated_price("BTC")
    eth_price, eth_change = get_simulated_price("ETH")
    st.warning("⚠️ Usando datos simulados (Bitso no respondió)")
    fuente = "Simulación"
else:
    st.success("✅ Datos reales de Bitso")
    fuente = "Bitso real"

state["last_prices"]["BTC"] = btc_price
state["last_prices"]["ETH"] = eth_price
state["price_history"]["BTC"].append(btc_price)
state["price_history"]["ETH"].append(eth_price)

fear, fear_label = get_fear_greed()
state["cycle"] += 1

# Guardar estado periódicamente
if state["cycle"] % 10 == 0:
    save_state(state)

# Latido
if state["cycle"] % HEARTBEAT_CYCLES == 0 and state["cycle"] > 0:
    send_telegram(f"💓 Heartbeat ciclo {state['cycle']} | Fuente: {fuente}")

# ==================== PROCESAR SEÑALES ====================
for sym, price in [("BTC", btc_price), ("ETH", eth_price)]:
    change = btc_change if sym == "BTC" else eth_change
    hist = list(state["price_history"][sym])
    if len(hist) < MIN_HISTORY_LEN:
        continue
    score = calculate_score(price, change, fear, hist)

    # Alerta cambio puntaje
    last_sc = state["last_score"].get(sym, 50)
    if abs(score - last_sc) >= 3:
        send_telegram(f"📊 *{sym}* Puntaje: {last_sc:.1f} → {score:.1f}")
        state["last_score"][sym] = score

    # Determinar acción
    if score >= buy_th:
        action = "BUY"
    elif score <= sell_th:
        action = "SELL"
    else:
        action = "HOLD"

    # Verificar stop loss / take profit / trailing
    exit_reason = None
    if state["positions"].get(sym, 0) > 0:
        entry = state["entry_price"].get(sym, 0)
        high = state["highest_price"].get(sym, price)
        if entry > 0:
            loss = (price - entry) / entry * 100
            profit = (price - entry) / entry * 100
            if loss <= -STOP_LOSS_PCT:
                action = "SELL"
                exit_reason = f"Stop Loss ({STOP_LOSS_PCT}%)"
            elif profit >= TAKE_PROFIT_PCT:
                action = "SELL"
                exit_reason = f"Take Profit ({TAKE_PROFIT_PCT}%)"
            elif price <= high * (1 - TRAILING_STOP_PCT / 100):
                action = "SELL"
                exit_reason = f"Trailing Stop ({TRAILING_STOP_PCT}%)"
        # Actualizar máximo si es mayor
        if price > state["highest_price"].get(sym, 0):
            state["highest_price"][sym] = price

    # Ejecutar si cambia la acción
    last_act = state["last_action"].get(sym)
    if action != last_act and action in ("BUY", "SELL"):
        qty, msg = execute_trade(sym, action, price, state, exit_reason)
        if msg:
            send_telegram(msg)
            state["trades"].append((datetime.now(), msg))
            save_state(state)
        state["last_action"][sym] = action

# ==================== MOSTRAR EN PANTALLA ====================
col1, col2 = st.columns(2)
with col1:
    st.subheader("📊 Señales en Vivo (MXN)")
    rows = []
    for sym in ["BTC", "ETH"]:
        name = "Bitcoin" if sym == "BTC" else "Ethereum"
        price = state["last_prices"][sym]
        change = btc_change if sym == "BTC" else eth_change
        hist = list(state["price_history"][sym])
        if len(hist) >= MIN_HISTORY_LEN:
            score = calculate_score(price, change, fear, hist)
            if score >= buy_th:
                sig = "🟢 COMPRAR"
            elif score <= sell_th:
                sig = "🔴 VENDER"
            else:
                sig = "⚪ MANTENER"
        else:
            score = 0
            sig = "⏳ Cargando..."
        rows.append({
            "Moneda": name,
            "Precio (MXN)": f"${price:,.0f}",
            "24h %": f"{change:+.2f}%",
            "Score": f"{score:.1f}",
            "Señal": sig
        })
    st.table(rows)
    st.metric("Fear & Greed", f"{fear}/100 ({fear_label})")
    st.caption(f"Ciclo: {state['cycle']} | Venta si score ≤ {sell_th} | Fuente: {fuente}")

with col2:
    st.subheader("📜 Historial de Operaciones")
    if state["trades"]:
        for ts, msg in reversed(state["trades"][-15:]):
            st.text(f"{ts.strftime('%H:%M:%S')} - {msg[:80]}...")
    else:
        st.caption("Esperando operaciones...")
    st.caption("✅ Datos reales de Bitso (sin API key). El bot opera en papel (simulación).")

# ==================== AUTO REFRESCO ====================
if auto:
    time.sleep(refresh)
    st.rerun()
