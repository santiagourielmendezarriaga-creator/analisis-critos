import streamlit as st
import requests
import time
import json
import os
import random
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
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

# ==================== PARÁMETROS POR DEFECTO ====================
DEFAULT_STRATEGY = "change"
DEFAULT_CHANGE_THRESHOLD = 0.2
DEFAULT_RSI_OVERBOUGHT = 70
DEFAULT_RSI_OVERSOLD = 30
DEFAULT_MA_FAST = 5
DEFAULT_MA_SLOW = 20
DEFAULT_STOP_LOSS_PCT = 1.0
DEFAULT_TRAILING_STOP_PCT = 0.8
DEFAULT_TAKE_PROFIT_PCT = 1.5
DEFAULT_DAILY_LOSS_LIMIT = 100.0
DEFAULT_POSITION_SIZE_PCT = 0.5
REFRESH_INTERVAL_SEC = 10
MAX_DAILY_TRADES = 20

# ==================== BITSO (DATOS REALES) ====================
def get_bitso_ticker(book="btc_mxn"):
    try:
        url = f"https://api.bitso.com/api/v3/ticker/?book={book}"
        resp = requests.get(url, timeout=5)
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

# ==================== SIMULACIÓN REALISTA ====================
BACKUP_PRICES = {"BTC": 1_070_000, "ETH": 28_000}
sim_prices = {"BTC": 1_070_000, "ETH": 28_000}

def get_simulated_price(symbol):
    last = sim_prices[symbol]
    change = random.uniform(-0.005, 0.005)
    new_price = last * (1 + change)
    new_price = max(BACKUP_PRICES[symbol]*0.95, min(BACKUP_PRICES[symbol]*1.05, new_price))
    sim_prices[symbol] = new_price
    return new_price, random.uniform(-2, 2)

# ==================== ESTRATEGIAS ====================
def compute_rsi(prices, period=14):
    if len(prices) < period+1:
        return 50
    deltas = np.diff(prices[-period-1:])
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100/(1+rs))

def get_signal_change(prices, threshold):
    if len(prices) < 2:
        return "HOLD", 0.0
    change = (prices[-1] - prices[-2]) / prices[-2] * 100
    if change >= threshold:
        return "BUY", change
    elif change <= -threshold:
        return "SELL", change
    else:
        return "HOLD", change

def get_signal_rsi(prices, oversold, overbought):
    if len(prices) < 15:
        return "HOLD", 0.0
    rsi = compute_rsi(prices)
    if rsi <= oversold:
        return "BUY", rsi
    elif rsi >= overbought:
        return "SELL", rsi
    else:
        return "HOLD", rsi

def get_signal_ma(prices, fast, slow):
    if len(prices) < slow:
        return "HOLD", 0.0
    ma_f = np.mean(prices[-fast:])
    ma_s = np.mean(prices[-slow:])
    if ma_f > ma_s:
        return "BUY", (ma_f - ma_s)/ma_s*100
    else:
        return "SELL", (ma_f - ma_s)/ma_s*100

# ==================== PERSISTENCIA ====================
STATE_FILE = "bot_state.json"

def save_state(state):
    to_save = {
        "balance": state["balance"],
        "positions": state["positions"],
        "trades": [(t.isoformat(), m) for t,m in state["trades"][-200:]],
        "last_action": state.get("last_action", {}),
        "daily_trades": state["daily_trades"],
        "daily_pnl": state["daily_pnl"],
        "last_trade_day": state["last_trade_day"],
        "cycle": state["cycle"],
        "price_history": {k: list(v) for k,v in state["price_history"].items()},
        "last_price": state.get("last_price", {}),
        "last_entry_price": state.get("last_entry_price", {}),
        "highest_price": state.get("highest_price", {})
    }
    with open(STATE_FILE, "w") as f:
        json.dump(to_save, f)

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                for k in ["price_history", "last_price", "last_entry_price", "highest_price"]:
                    if k not in data:
                        data[k] = {}
                if "daily_pnl" not in data:
                    data["daily_pnl"] = 0.0
                return data
        except:
            pass
    return None

# ==================== EJECUCIÓN DE ÓRDENES ====================
def can_trade(state, daily_loss_limit):
    now_day = datetime.now().day
    if now_day != state["last_trade_day"]:
        state["daily_trades"] = 0
        state["daily_pnl"] = 0.0
        state["last_trade_day"] = now_day
    if state["daily_pnl"] <= -daily_loss_limit:
        return False, f"Pérdida diaria máxima alcanzada (${-daily_loss_limit:.2f})"
    return state["daily_trades"] < MAX_DAILY_TRADES, ""

def execute_trade(symbol, action, price, state, commission_pct, slippage_pct, position_size_pct, daily_loss_limit):
    can, reason = can_trade(state, daily_loss_limit)
    if not can:
        return None, f"❌ {reason}"
    if action == "BUY":
        amount = state["balance"] * position_size_pct
        if amount <= 0:
            return None, "❌ Saldo insuficiente"
        eff_price = price * (1 + slippage_pct/100)
        commission = amount * commission_pct / 100
        qty = (amount - commission) / eff_price
        state["balance"] -= amount
        state["positions"][symbol] = state["positions"].get(symbol, 0) + qty
        state["last_entry_price"][symbol] = eff_price
        state["highest_price"][symbol] = eff_price
        state["daily_trades"] += 1
        msg = (f"🟢 *COMPRA* {symbol}\n"
               f"Cantidad: {qty:.6f}\n"
               f"Precio efectivo: ${eff_price:,.2f}\n"
               f"Comisión: ${commission:.2f}\n"
               f"Saldo restante: ${state['balance']:.2f}")
        return qty, msg
    else:
        qty = state["positions"].get(symbol, 0)
        if qty <= 0:
            return None, "❌ No hay posición"
        eff_price = price * (1 - slippage_pct/100)
        gross = qty * eff_price
        commission = gross * commission_pct / 100
        net = gross - commission
        entry = state["last_entry_price"].get(symbol, eff_price)
        pnl = net - (qty * entry)
        state["daily_pnl"] += pnl
        state["balance"] += net
        state["positions"][symbol] = 0
        state["daily_trades"] += 1
        msg = (f"🔴 *VENTA* {symbol}\n"
               f"Cantidad: {qty:.6f}\n"
               f"Precio efectivo: ${eff_price:,.2f}\n"
               f"Comisión: ${commission:.2f}\n"
               f"Neto: ${net:.2f}\n"
               f"P&L: ${pnl:+.2f}\n"
               f"Saldo nuevo: ${state['balance']:.2f}")
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
        "last_action": {"BTC": None, "ETH": None},
        "daily_trades": 0,
        "daily_pnl": 0.0,
        "last_trade_day": datetime.now().day,
        "cycle": 0,
        "price_history": {"BTC": deque(maxlen=100), "ETH": deque(maxlen=100)},
        "last_price": {"BTC": 0.0, "ETH": 0.0},
        "last_entry_price": {"BTC": 0.0, "ETH": 0.0},
        "highest_price": {"BTC": 0.0, "ETH": 0.0}
    }

# ==================== INTERFAZ STREAMLIT ====================
st.set_page_config(page_title="Bot Pro - 6 Mejoras", layout="wide")
st.title("🤖 Bot de Trading Profesional (con todas las mejoras)")

st.sidebar.header("⚙️ Configuración Global")
refresh = st.sidebar.slider("Intervalo (segundos)", 5, 60, REFRESH_INTERVAL_SEC)
auto = st.sidebar.checkbox("Auto-refrescar", True)

# Estrategia
strategy = st.sidebar.selectbox("Estrategia", ["change", "rsi", "ma"], index=0)
if strategy == "change":
    change_th = st.sidebar.number_input("Umbral cambio %", 0.05, 2.0, DEFAULT_CHANGE_THRESHOLD, 0.05)
elif strategy == "rsi":
    oversold = st.sidebar.number_input("RSI sobreventa (compra)", 20, 40, DEFAULT_RSI_OVERSOLD)
    overbought = st.sidebar.number_input("RSI sobrecompra (venta)", 60, 80, DEFAULT_RSI_OVERBOUGHT)
else:
    ma_fast = st.sidebar.number_input("MA rápida (periodos)", 3, 20, DEFAULT_MA_FAST)
    ma_slow = st.sidebar.number_input("MA lenta (periodos)", 10, 50, DEFAULT_MA_SLOW)

# Gestión de riesgo
st.sidebar.subheader("Gestión de Riesgo")
stop_loss = st.sidebar.number_input("Stop Loss (%)", 0.5, 5.0, DEFAULT_STOP_LOSS_PCT, 0.1)
trailing = st.sidebar.number_input("Trailing Stop (%)", 0.2, 3.0, DEFAULT_TRAILING_STOP_PCT, 0.1)
take_profit = st.sidebar.number_input("Take Profit (%)", 0.5, 10.0, DEFAULT_TAKE_PROFIT_PCT, 0.5)
daily_loss_limit = st.sidebar.number_input("Límite pérdida diaria (MXN)", 10.0, 500.0, DEFAULT_DAILY_LOSS_LIMIT, 10.0)
position_size_pct = st.sidebar.slider("Tamaño posición (% saldo)", 0.1, 1.0, DEFAULT_POSITION_SIZE_PCT, 0.05)

# Modo real (desactivado por defecto)
st.sidebar.checkbox("⚠️ Modo REAL (Bitso) - Solo con API key", value=False, disabled=True)
st.sidebar.info("El modo real requiere configuración adicional. Por ahora se mantiene la simulación.")

# Estado cartera
st.sidebar.subheader("💰 Cartera (MXN)")
st.sidebar.metric("Saldo", f"${state['balance']:,.2f}")
total = state['balance']
for s in ["BTC","ETH"]:
    p = state["last_price"].get(s, 0)
    q = state["positions"].get(s, 0)
    if q>0 and p>0:
        total += q * p
st.sidebar.metric("Valor total", f"${total:,.2f}")
st.sidebar.metric("Ops hoy", state["daily_trades"])
st.sidebar.metric("P&L diario", f"${state['daily_pnl']:+.2f}")

if st.sidebar.button("Reiniciar simulación"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
    st.rerun()
if st.sidebar.button("Prueba Telegram"):
    send_telegram("🧪 Alerta - Bot profesional")
    st.success("Enviado")

st.info("✅ 6 mejoras integradas: estrategia configurable, stop-loss, trailing, take-profit, límite pérdida diaria, tamaño posición porcentual. Backtesting disponible abajo.")

# ==================== OBTENER DATOS ====================
btc_p, _ = get_bitso_ticker("btc_mxn")
eth_p, _ = get_bitso_ticker("eth_mxn")
if btc_p is None:
    btc_p, _ = get_simulated_price("BTC")
    eth_p, _ = get_simulated_price("ETH")
    fuente = "Simulación"
else:
    fuente = "Bitso real"

state["last_price"]["BTC"] = btc_p
state["last_price"]["ETH"] = eth_p
state["price_history"]["BTC"].append(btc_p)
state["price_history"]["ETH"].append(eth_p)

state["cycle"] += 1
if state["cycle"] % 20 == 0:
    save_state(state)

if state["cycle"] % 30 == 0 and state["cycle"]>0:
    send_telegram(f"💓 Heartbeat ciclo {state['cycle']} | Fuente: {fuente}")

# ==================== LÓGICA DE SEÑAL ====================
for sym, price in [("BTC", btc_p), ("ETH", eth_p)]:
    hist = list(state["price_history"][sym])
    if strategy == "change":
        signal, value = get_signal_change(hist, change_th)
    elif strategy == "rsi":
        signal, value = get_signal_rsi(hist, oversold, overbought)
    else:
        signal, value = get_signal_ma(hist, ma_fast, ma_slow)

    # Gestión de riesgos si hay posición
    pos = state["positions"].get(sym, 0)
    if pos > 0:
        entry = state["last_entry_price"].get(sym, price)
        high = state["highest_price"].get(sym, price)
        if price > high:
            state["highest_price"][sym] = price
            high = price
        # Stop loss
        if (price - entry)/entry * 100 <= -stop_loss:
            signal = "SELL"
        # Take profit
        elif (price - entry)/entry * 100 >= take_profit:
            signal = "SELL"
        # Trailing stop
        elif high > entry and (price - high)/high * 100 <= -trailing:
            signal = "SELL"

    action = None
    if signal == "BUY" and pos == 0:
        action = "BUY"
    elif signal == "SELL" and pos > 0:
        action = "SELL"

    if action:
        qty, msg = execute_trade(sym, action, price, state,
                                 commission_pct=0.1,
                                 slippage_pct=0.05,
                                 position_size_pct=position_size_pct,
                                 daily_loss_limit=daily_loss_limit)
        if msg:
            send_telegram(msg)
            state["trades"].append((datetime.now(), msg))
            save_state(state)
            state["last_action"][sym] = action

# ==================== BACKTESTING BÁSICO ====================
with st.expander("📊 Backtesting (simulación con datos sintéticos)"):
    st.markdown("Ejecuta una simulación rápida con datos históricos simulados para evaluar la estrategia.")
    days_back = st.number_input("Días hacia atrás", 1, 30, 7)
    if st.button("Ejecutar backtest (no afecta saldo real)"):
        # Generar datos sintéticos
        periods = days_back * 24
        base = BACKUP_PRICES["BTC"]
        prices = [base]
        for _ in range(periods-1):
            prices.append(prices[-1] * (1 + random.uniform(-0.005, 0.005)))
        balance = 1000.0
        position = 0.0
        trades = []
        for i in range(1, len(prices)):
            hist = prices[:i+1]
            if strategy == "change":
                sig, _ = get_signal_change(hist, change_th)
            elif strategy == "rsi":
                sig, _ = get_signal_rsi(hist, oversold, overbought)
            else:
                sig, _ = get_signal_ma(hist, ma_fast, ma_slow)
            # Simular ordenes simplificadas
            if sig == "BUY" and position == 0:
                amount = balance * position_size_pct
                eff_price = prices[i] * 1.0005
                commission = amount * 0.001
                qty = (amount - commission) / eff_price
                balance -= amount
                position = qty
                trades.append(("COMPRA", prices[i]))
            elif sig == "SELL" and position > 0:
                eff_price = prices[i] * 0.9995
                gross = position * eff_price
                commission = gross * 0.001
                net = gross - commission
                balance += net
                position = 0
                trades.append(("VENTA", prices[i]))
        final = balance + (position * prices[-1])
        st.success(f"Capital inicial: 1000 MXN → Capital final: {final:.2f} MXN (Rendimiento: {(final-1000)/10:.2f}%)")
        if trades:
            st.dataframe(pd.DataFrame(trades, columns=["Operación", "Precio"]))

# ==================== DASHBOARD ====================
col1, col2 = st.columns(2)
with col1:
    st.subheader("📊 Señales en Vivo")
    rows = []
    for sym in ["BTC","ETH"]:
        name = "Bitcoin" if sym=="BTC" else "Ethereum"
        price = state["last_price"].get(sym, 0)
        hist = list(state["price_history"].get(sym, []))
        if strategy == "change":
            if len(hist) >= 2:
                cambio = (hist[-1] - hist[-2]) / hist[-2] * 100
                sig = "🟢 COMPRAR" if cambio >= change_th else "🔴 VENDER" if cambio <= -change_th else "⚪ MANTENER"
            else:
                cambio = 0.0
                sig = "⏳ Cargando..."
            valor = cambio
        elif strategy == "rsi":
            if len(hist) >= 15:
                rsi = compute_rsi(hist)
                if rsi <= oversold:
                    sig = "🟢 COMPRAR"
                elif rsi >= overbought:
                    sig = "🔴 VENDER"
                else:
                    sig = "⚪ MANTENER"
                valor = rsi
            else:
                valor = 0.0
                sig = "⏳ Cargando..."
        else:
            if len(hist) >= ma_slow:
                ma_f = np.mean(hist[-ma_fast:])
                ma_s = np.mean(hist[-ma_slow:])
                sig = "🟢 COMPRAR" if ma_f > ma_s else "🔴 VENDER"
                valor = (ma_f - ma_s)/ma_s*100
            else:
                valor = 0.0
                sig = "⏳ Cargando..."
        rows.append({"Moneda": name, "Precio": f"${price:,.0f}", "Indicador": f"{valor:.2f}", "Señal": sig})
    st.table(rows)
    st.metric("Fuente de datos", fuente)
    st.caption(f"Ciclo: {state['cycle']} | Estrategia: {strategy} | Intervalo: {refresh}s")
with col2:
    st.subheader("📜 Historial de Operaciones")
    for ts, msg in reversed(state["trades"][-15:]):
        st.text(f"{ts.strftime('%H:%M:%S')} - {msg[:70]}")
    st.caption("Cada operación incluye gestión de riesgo y tamaño de posición porcentual.")

if auto:
    time.sleep(refresh)
    st.rerun()
