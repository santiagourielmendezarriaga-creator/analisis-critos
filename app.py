import streamlit as st
import requests
import time
import json
import os
import random
from collections import deque
from datetime import datetime
import math

# ==================== TELEGRAM ====================
TELEGRAM_TOKEN = "8532857017:AAHwLhRnM3oC6TbgFFKAEmQnZVoo6JD_esQ"
TELEGRAM_CHAT_ID = "5835990242"

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=5)
    except:
        pass

# ==================== PARÁMETROS RÁPIDOS ====================
TREND_BUY_THRESHOLD = 25
TREND_SELL_THRESHOLD = -25
EMA_FAST = 4
EMA_SLOW = 12
TREND_WINDOW = 8
MIN_PRICES = 3                     # <--- Reducido a 3 para máxima velocidad
STOP_LOSS_PCT = 1.0
TAKE_PROFIT_PCT = 1.5
TRAILING_STOP_PCT = 0.8
MAX_POSITION_SIZE_MXN = 500.0
MAX_DAILY_TRADES = 200
COMMISSION_PCT = 0.1
SLIPPAGE_PCT = 0.05
REFRESH_INTERVAL_SEC = 10
HEARTBEAT_CYCLES = 30

# ==================== FUNCIONES MATEMÁTICAS LIGERAS ====================
def linear_trend_score(prices):
    n = min(TREND_WINDOW, len(prices))
    if n < 2:
        return 0
    y = prices[-n:]
    x = list(range(n))
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    num = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    den = sum((x[i] - mean_x) ** 2 for i in range(n))
    if den == 0:
        return 0
    slope = num / den
    if mean_y == 0:
        return 0
    norm_slope = (slope / mean_y) * 100
    return max(-100, min(100, norm_slope * 8))

def ema_trend_score(prices):
    if len(prices) < EMA_SLOW:
        return 0
    def ema(data, period):
        alpha = 2 / (period + 1)
        ema_val = data[0]
        for val in data[1:]:
            ema_val = val * alpha + ema_val * (1 - alpha)
        return ema_val
    ema_f = ema(prices, EMA_FAST)
    ema_s = ema(prices, EMA_SLOW)
    if ema_s == 0:
        return 0
    diff = (ema_f - ema_s) / ema_s * 100
    return max(-100, min(100, diff))

def recent_change_score(prices):
    if len(prices) < 3:
        return 0
    change = (prices[-1] - prices[-3]) / prices[-3] * 100
    return max(-100, min(100, change * 2.5))

def calculate_trend_score(prices, fear):
    if len(prices) < MIN_PRICES:      # Ahora MIN_PRICES = 3
        return 0
    w1, w2, w3 = 0.5, 0.3, 0.2
    s1 = linear_trend_score(prices)
    s2 = ema_trend_score(prices)
    s3 = recent_change_score(prices)
    trend = w1*s1 + w2*s2 + w3*s3
    fear_adj = (50 - fear) * 0.2
    trend += fear_adj
    return max(-100, min(100, trend))

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

def get_fear_greed():
    try:
        resp = requests.get("https://api.alternative.me/fng/", timeout=3)
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
    new_price = max(base*0.9, min(base*1.1, new_price))
    sim_change = backup_changes.get(symbol, 0.0) + random.uniform(-0.2, 0.2)
    sim_change = max(-5, min(5, sim_change))
    backup_prices[symbol] = new_price
    backup_changes[symbol] = sim_change
    return new_price, sim_change

# ==================== PERSISTENCIA ====================
STATE_FILE = "bot_state.json"

def save_state(state):
    to_save = {
        "balance": state["balance"],
        "positions": state["positions"],
        "trades": [(t.isoformat(), m) for t,m in state["trades"][-100:]],
        "price_history": {k: list(v) for k,v in state["price_history"].items()},
        "last_action": state["last_action"],
        "last_prices": state["last_prices"],
        "entry_price": state["entry_price"],
        "highest_price": state["highest_price"],
        "daily_trades": state["daily_trades"],
        "last_trade_day": state["last_trade_day"],
        "cycle": state["cycle"],
        "last_trend": state["last_trend"]
    }
    with open(STATE_FILE, "w") as f:
        json.dump(to_save, f)

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                if "last_trend" not in data:
                    data["last_trend"] = {"BTC": 0, "ETH": 0}
                if "price_history" not in data:
                    data["price_history"] = {"BTC": [], "ETH": []}
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
            return None, "❌ Límite diario"
        amount = min(MAX_POSITION_SIZE_MXN, state["balance"])
        if amount <= 0:
            return None, "❌ Saldo insuficiente"
        eff_price = price * (1 + SLIPPAGE_PCT/100)
        commission = amount * COMMISSION_PCT/100
        qty = (amount - commission) / eff_price
        state["balance"] -= amount
        state["positions"][symbol] += qty
        state["entry_price"][symbol] = eff_price
        state["highest_price"][symbol] = eff_price
        state["daily_trades"] += 1
        msg = (f"🟢 *COMPRA* {symbol}\nQty: {qty:.6f}\nPrecio: ${eff_price:,.2f}\nComisión: ${commission:.2f}\nSaldo: ${state['balance']:.2f}\nTrend: {state['last_trend'].get(symbol,0):.1f}")
        if exit_reason:
            msg += f"\nMotivo: {exit_reason}"
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
        msg = (f"🔴 *VENTA* {symbol}\nQty: {qty:.6f}\nPrecio: ${eff_price:,.2f}\nComisión: ${commission:.2f}\nNeto: ${net:.2f}\nSaldo: ${state['balance']:.2f}")
        if exit_reason:
            msg += f"\nMotivo: {exit_reason}"
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
        "last_prices": {"BTC": 0.0, "ETH": 0.0},
        "entry_price": {"BTC": 0.0, "ETH": 0.0},
        "highest_price": {"BTC": 0.0, "ETH": 0.0},
        "daily_trades": 0,
        "last_trade_day": datetime.now().day,
        "cycle": 0,
        "last_trend": {"BTC": 0, "ETH": 0}
    }

# ==================== INTERFAZ STREAMLIT ====================
st.set_page_config(page_title="Trend Bot - MIN_PRICES=3", layout="wide")
st.title("⚡ Trend Bot - Análisis con solo 3 precios")

st.sidebar.header("⚙️ Configuración")
refresh = st.sidebar.slider("Intervalo (segundos)", 5, 30, REFRESH_INTERVAL_SEC)
auto = st.sidebar.checkbox("Auto-refrescar", True)
buy_t = st.sidebar.number_input("Compra si tendencia ≥", -100, 100, TREND_BUY_THRESHOLD)
sell_t = st.sidebar.number_input("Vende si tendencia ≤", -100, 100, TREND_SELL_THRESHOLD)

st.sidebar.subheader("💰 Cartera (MXN)")
st.sidebar.metric("Saldo", f"${state['balance']:,.2f}")
total = state['balance']
for s in ["BTC","ETH"]:
    p = state["last_prices"].get(s,0)
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
    send_telegram("🧪 Alerta de prueba - Trend rápido MIN=3")
    st.success("Enviado")

# Obtener datos
btc_p, btc_c = get_bitso_ticker("btc_mxn")
eth_p, eth_c = get_bitso_ticker("eth_mxn")
if btc_p is None:
    btc_p, btc_c = get_simulated_price("BTC")
    eth_p, eth_c = get_simulated_price("ETH")
    fuente = "Simulación"
else:
    fuente = "Bitso real"

state["last_prices"]["BTC"] = btc_p
state["last_prices"]["ETH"] = eth_p
state["price_history"]["BTC"].append(btc_p)
state["price_history"]["ETH"].append(eth_p)

fear, fear_label = get_fear_greed()
state["cycle"] += 1
if state["cycle"] % 10 == 0:
    save_state(state)
if state["cycle"] % HEARTBEAT_CYCLES == 0 and state["cycle"]>0:
    send_telegram(f"💓 Heartbeat ciclo {state['cycle']} | Fuente: {fuente}")

# Procesar cada moneda
for sym, price in [("BTC", btc_p), ("ETH", eth_p)]:
    hist = list(state["price_history"][sym])
    trend = calculate_trend_score(hist, fear)
    state["last_trend"][sym] = trend

    old = state.get("last_trend_alert", {}).get(sym, 0)
    if abs(trend - old) >= 15:
        send_telegram(f"📊 *{sym}* Tendencia: {old:.1f} → {trend:.1f}")
        if "last_trend_alert" not in state:
            state["last_trend_alert"] = {}
        state["last_trend_alert"][sym] = trend

    action = "HOLD"
    if state["positions"].get(sym, 0) == 0:
        if trend >= buy_t:
            action = "BUY"
    else:
        if trend <= sell_t:
            action = "SELL"

    exit_reason = None
    if state["positions"].get(sym, 0) > 0:
        entry = state["entry_price"].get(sym, 0)
        high = state["highest_price"].get(sym, price)
        if entry > 0:
            loss = (price - entry)/entry*100
            profit = (price - entry)/entry*100
            if loss <= -STOP_LOSS_PCT:
                action = "SELL"
                exit_reason = f"Stop Loss ({STOP_LOSS_PCT}%)"
            elif profit >= TAKE_PROFIT_PCT:
                action = "SELL"
                exit_reason = f"Take Profit ({TAKE_PROFIT_PCT}%)"
            elif price <= high * (1 - TRAILING_STOP_PCT/100):
                action = "SELL"
                exit_reason = f"Trailing Stop ({TRAILING_STOP_PCT}%)"
        if price > state["highest_price"].get(sym, 0):
            state["highest_price"][sym] = price

    last_act = state["last_action"].get(sym)
    if action != last_act and action in ("BUY","SELL"):
        qty, msg = execute_trade(sym, action, price, state, exit_reason)
        if msg:
            send_telegram(msg)
            state["trades"].append((datetime.now(), msg))
            save_state(state)
        state["last_action"][sym] = action

# Dashboard
col1, col2 = st.columns(2)
with col1:
    st.subheader("📊 Tendencia en Vivo")
    rows = []
    for sym in ["BTC","ETH"]:
        name = "Bitcoin" if sym=="BTC" else "Ethereum"
        price = state["last_prices"][sym]
        trend = state["last_trend"].get(sym, 0)
        if trend >= buy_t:
            sig = "🟢 COMPRAR"
        elif trend <= sell_t:
            sig = "🔴 VENDER"
        else:
            sig = "⚪ MANTENER"
        rows.append({"Moneda": name, "Precio": f"${price:,.0f}", "Tendencia": f"{trend:.1f}", "Señal": sig})
    st.table(rows)
    st.metric("Fear & Greed", f"{fear}/100 ({fear_label})")
    st.caption(f"Ciclo: {state['cycle']} | Fuente: {fuente} | MIN_PRICES=3")
with col2:
    st.subheader("📜 Operaciones")
    for ts, msg in reversed(state["trades"][-15:]):
        st.text(f"{ts.strftime('%H:%M:%S')} - {msg[:70]}")
    st.caption("Análisis de tendencia con solo 3 precios históricos.")

if auto:
    time.sleep(refresh)
    st.rerun()
