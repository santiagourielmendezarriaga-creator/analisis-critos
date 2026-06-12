import streamlit as st
import pandas as pd
import numpy as np
import time
import requests
import json
import os
import random
from collections import deque
from datetime import datetime

# ==================== CONFIGURACIÓN ====================
# --- Telegram ---
TELEGRAM_TOKEN = "8532857017:AAHwLhRnM3oC6TbgFFKAEmQnZVoo6JD_esQ"
TELEGRAM_CHAT_ID = "5835990242"

def send_telegram(message, parse_mode="Markdown"):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": parse_mode}
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        st.error(f"Error Telegram: {e}")
        return False

# --- Estrategia ---
BUY_THRESHOLD = 60
SELL_THRESHOLD = 45
STOP_LOSS_PCT = 5.0
TAKE_PROFIT_PCT = 10.0
TRAILING_STOP_PCT = 3.0
MAX_POSITION_SIZE_USDT = 50.0
MAX_DAILY_TRADES = 10
COMMISSION_PCT = 0.1
SLIPPAGE_PCT = 0.05
REFRESH_INTERVAL_SEC = 60
HEARTBEAT_CYCLES = 30
MIN_HISTORY_LEN = 5

# --- Datos de mercado ---
REAL_BASES = {"BTC": 63000, "ETH": 1670}
SIM_PRICES = {"BTC": 63000, "ETH": 1670}
SIM_CHANGES = {"BTC": 0.0, "ETH": 0.0}

# ==================== ESTADO DE SESIÓN ====================
if "balance" not in st.session_state:
    st.session_state.balance = 1000.0
    st.session_state.positions = {"BTC": 0.0, "ETH": 0.0}
    st.session_state.trades = []
    st.session_state.price_history = {"BTC": deque(maxlen=100), "ETH": deque(maxlen=100)}
    st.session_state.last_action = {"BTC": None, "ETH": None}
    st.session_state.last_prices = {"BTC": 0.0, "ETH": 0.0}
    st.session_state.entry_price = {"BTC": 0.0, "ETH": 0.0}
    st.session_state.highest_price = {"BTC": 0.0, "ETH": 0.0}
    st.session_state.cycle_count = 0
    st.session_state.last_cycle_time = time.time()
    st.session_state.daily_trades = 0
    st.session_state.last_trade_day = datetime.now().day
    st.session_state.use_real = True
    st.session_state.last_fail = 0

# Crear carpeta para logs
os.makedirs("data", exist_ok=True)

# Cargar historial de trades
if os.path.exists("data/trades.csv") and not st.session_state.trades:
    try:
        df = pd.read_csv("data/trades.csv")
        for _, row in df.iterrows():
            st.session_state.trades.append((datetime.fromisoformat(row['timestamp']), row['message']))
    except:
        pass

# ==================== FUNCIONES DE MERCADO ====================
def get_binance_price(symbol):
    try:
        pair = f"{symbol}USDT"
        url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={pair}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return float(data['lastPrice']), float(data['priceChangePercent'])
        return None, None
    except:
        return None, None

def get_price(symbol):
    now = time.time()
    if st.session_state.use_real and (now - st.session_state.last_fail > 300):
        price, change = get_binance_price(symbol)
        if price and ((symbol=="BTC" and 30000<price<100000) or (symbol=="ETH" and 500<price<5000)):
            return price, change, "real"
        st.session_state.last_fail = now
        st.session_state.use_real = False
    # Simulación realista
    base = REAL_BASES[symbol]
    last = SIM_PRICES.get(symbol, base)
    new_price = last * (1 + random.uniform(-0.015, 0.015))
    new_price = max(base*0.9, min(base*1.1, new_price))
    change = SIM_CHANGES.get(symbol, 0.0) + random.uniform(-0.3, 0.3)
    change = max(-10, min(10, change))
    SIM_PRICES[symbol] = new_price
    SIM_CHANGES[symbol] = change
    return new_price, change, "sim"

def get_fear_greed():
    try:
        resp = requests.get("https://api.alternative.me/fng/", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return int(data['data'][0]['value']), data['data'][0]['value_classification']
    except:
        pass
    return 50, "Neutral"

# ==================== INDICADORES TÉCNICOS ====================
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

def compute_macd(prices, fast=12, slow=26, signal=9):
    if len(prices) < slow + signal:
        return 0, False, False
    series = pd.Series(prices)
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    if len(hist) >= 2:
        cross_up = hist.iloc[-1] > 0 and hist.iloc[-2] <= 0
        cross_down = hist.iloc[-1] < 0 and hist.iloc[-2] >= 0
        return hist.iloc[-1], cross_up, cross_down
    return 0, False, False

def compute_moving_averages(prices, short=7, long=20):
    if len(prices) < long:
        return None, None
    return np.mean(prices[-short:]), np.mean(prices[-long:])

# ==================== ESTRATEGIA DE PUNTAJE ====================
def calculate_score(price, change_24h, fng, price_history):
    score = 50
    # Fear & Greed (25%)
    score += (50 - fng) * 0.5
    # Cambio 24h (12%)
    score += np.clip(change_24h * 2, -12, 12)
    # RSI (15%)
    if len(price_history) >= 15:
        rsi = compute_rsi(price_history)
        if rsi < 30:
            score += 15
        elif rsi < 40:
            score += 8
        elif rsi > 70:
            score -= 15
        elif rsi > 60:
            score -= 8
    # MACD (12%)
    if len(price_history) >= 35:
        _, cross_up, cross_down = compute_macd(price_history)
        if cross_up:
            score += 12
        elif cross_down:
            score -= 12
    # Medias móviles (10%)
    short_ma, long_ma = compute_moving_averages(price_history)
    if short_ma and long_ma:
        if short_ma > long_ma:
            score += 10
        else:
            score -= 10
    # Tendencia reciente (6%)
    if len(price_history) >= 5:
        trend = np.mean(np.diff(price_history[-5:]))
        score += 6 if trend > 0 else -6
    return np.clip(score, 0, 100)

# ==================== GESTIÓN DE RIESGO ====================
def can_trade():
    now_day = datetime.now().day
    if now_day != st.session_state.last_trade_day:
        st.session_state.daily_trades = 0
        st.session_state.last_trade_day = now_day
    return st.session_state.daily_trades < MAX_DAILY_TRADES

def record_trade():
    st.session_state.daily_trades += 1

def check_stop_loss(symbol, current_price):
    entry = st.session_state.entry_price.get(symbol, 0)
    if entry == 0:
        return False
    loss = (current_price - entry) / entry * 100
    return loss <= -STOP_LOSS_PCT

def check_take_profit(symbol, current_price):
    entry = st.session_state.entry_price.get(symbol, 0)
    if entry == 0:
        return False
    profit = (current_price - entry) / entry * 100
    return profit >= TAKE_PROFIT_PCT

def check_trailing_stop(symbol, current_price):
    entry = st.session_state.entry_price.get(symbol, 0)
    if entry == 0:
        return False
    high = st.session_state.highest_price.get(symbol, current_price)
    if current_price > high:
        st.session_state.highest_price[symbol] = current_price
        high = current_price
    stop_price = high * (1 - TRAILING_STOP_PCT / 100)
    return current_price <= stop_price

# ==================== EJECUCIÓN DE ÓRDENES ====================
def execute_trade(symbol, action, price):
    if action == "BUY":
        if not can_trade():
            return "❌ Límite diario de operaciones alcanzado"
        amount_usdt = min(MAX_POSITION_SIZE_USDT, st.session_state.balance)
        if amount_usdt <= 0:
            return "❌ Saldo insuficiente"
        eff_price = price * (1 + SLIPPAGE_PCT / 100)
        commission = amount_usdt * COMMISSION_PCT / 100
        amount_after = amount_usdt - commission
        qty = amount_after / eff_price
        st.session_state.balance -= amount_usdt
        st.session_state.positions[symbol] += qty
        st.session_state.entry_price[symbol] = eff_price
        st.session_state.highest_price[symbol] = eff_price
        record_trade()
        msg = (f"🟢 *COMPRA* {symbol}\n"
               f"Cantidad: {qty:.6f}\n"
               f"Precio efectivo: ${eff_price:.2f}\n"
               f"Comisión: ${commission:.2f}\n"
               f"Saldo restante: ${st.session_state.balance:.2f}")
        return msg
    else:  # SELL
        qty = st.session_state.positions.get(symbol, 0)
        if qty <= 0:
            return "❌ No hay posición para vender"
        eff_price = price * (1 - SLIPPAGE_PCT / 100)
        gross = qty * eff_price
        commission = gross * COMMISSION_PCT / 100
        net = gross - commission
        st.session_state.balance += net
        st.session_state.positions[symbol] = 0
        record_trade()
        msg = (f"🔴 *VENTA* {symbol}\n"
               f"Cantidad: {qty:.6f}\n"
               f"Precio efectivo: ${eff_price:.2f}\n"
               f"Comisión: ${commission:.2f}\n"
               f"Neto: ${net:.2f}\n"
               f"Saldo nuevo: ${st.session_state.balance:.2f}")
        return msg

# ==================== INTERFAZ STREAMLIT ====================
st.set_page_config(page_title="Crypto Trading Bot Pro", layout="wide")
st.title("🤖 Crypto Trading Bot Pro - Estrategia Avanzada")

st.sidebar.header("⚙️ Configuración")
refresh = st.sidebar.slider("Intervalo (segundos)", 30, 180, REFRESH_INTERVAL_SEC)
auto = st.sidebar.checkbox("Auto-refrescar", value=True)

buy_th = st.sidebar.number_input("Umbral COMPRA", 0, 100, BUY_THRESHOLD, 5)
sell_th = st.sidebar.number_input("Umbral VENTA", 0, 100, SELL_THRESHOLD, 5)
st.sidebar.markdown(f"Stop Loss: {STOP_LOSS_PCT}% | Take Profit: {TAKE_PROFIT_PCT}% | Trailing: {TRAILING_STOP_PCT}%")

st.sidebar.subheader("💰 Cartera")
st.sidebar.metric("Saldo USDT", f"${st.session_state.balance:,.2f}")
total_value = st.session_state.balance
for sym in ["BTC", "ETH"]:
    price = st.session_state.last_prices.get(sym, 0)
    qty = st.session_state.positions.get(sym, 0)
    if qty > 0 and price > 0:
        total_value += qty * price
st.sidebar.metric("Valor total", f"${total_value:,.2f}")
st.sidebar.metric("Operaciones hoy", st.session_state.daily_trades)

if st.sidebar.button("Reiniciar simulación"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

if st.sidebar.button("📢 Enviar alerta de prueba"):
    if send_telegram("🧪 *Alerta de prueba* - Bot profesional activo"):
        st.success("Mensaje enviado")
    else:
        st.error("Error")

# Mostrar modo
if st.session_state.use_real:
    st.success("✅ Datos REALES (Binance)")
else:
    st.warning("⚠️ Datos SIMULADOS (fallback realista)")

# ==================== OBTENER DATOS DEL MERCADO ====================
fng, fng_label = get_fear_greed()
price_data = {}
for sym in ["BTC", "ETH"]:
    price, change, source = get_price(sym)
    st.session_state.last_prices[sym] = price
    price_data[sym] = (price, change, source)
    if price > 0:
        st.session_state.price_history[sym].append(price)
        # Actualizar máximo para trailing stop
        if price > st.session_state.highest_price.get(sym, 0):
            st.session_state.highest_price[sym] = price

# Control de ciclos y latido
st.session_state.cycle_count += 1
now = time.time()
gap = now - st.session_state.last_cycle_time
if gap > 300:
    send_telegram(f"⚠️ Reanudación tras {gap:.0f} segundos de inactividad")
st.session_state.last_cycle_time = now
if st.session_state.cycle_count % HEARTBEAT_CYCLES == 0:
    send_telegram(f"💓 *Heartbeat* - Ciclo {st.session_state.cycle_count} (intervalo {refresh}s)")

# ==================== LÓGICA DE DECISIÓN ====================
for sym in ["BTC", "ETH"]:
    price, change, source = price_data[sym]
    if price == 0:
        continue
    hist = list(st.session_state.price_history[sym])
    if len(hist) < MIN_HISTORY_LEN:
        continue
    score = calculate_score(price, change, fng, hist)
    
    # Señal base
    if score >= buy_th:
        action = "BUY"
    elif score <= sell_th:
        action = "SELL"
    else:
        action = "HOLD"
    
    # Gestión de riesgos: prioridad a salidas
    exit_reason = None
    if st.session_state.positions.get(sym, 0) > 0:
        if check_stop_loss(sym, price):
            action = "SELL"
            exit_reason = "Stop Loss"
        elif check_take_profit(sym, price):
            action = "SELL"
            exit_reason = "Take Profit"
        elif check_trailing_stop(sym, price):
            action = "SELL"
            exit_reason = "Trailing Stop"
    
    # Ejecutar si cambia la acción (o si hay salida forzada)
    last_act = st.session_state.last_action.get(sym)
    if (action != last_act and action in ("BUY", "SELL")):
        msg = execute_trade(sym, action, price)
        if msg:
            if exit_reason:
                msg += f"\n*Motivo:* {exit_reason}"
            send_telegram(msg)
            st.session_state.trades.append((datetime.now(), msg))
            # Guardar en CSV
            with open("data/trades.csv", "a") as f:
                f.write(f"{datetime.now().isoformat()},{msg.replace(chr(10), ' ')}\n")
        st.session_state.last_action[sym] = action

# ==================== MOSTRAR EN PANTALLA ====================
col1, col2 = st.columns(2)
with col1:
    st.subheader("📊 Señales en Vivo")
    rows = []
    for sym in ["BTC", "ETH"]:
        name = "Bitcoin" if sym == "BTC" else "Ethereum"
        price, change, source = price_data.get(sym, (0,0,""))
        if price == 0:
            rows.append({"Moneda": name, "Precio": "Error", "24h": "N/A", "Score": "N/A", "Señal": "ERROR"})
            continue
        hist = list(st.session_state.price_history[sym])
        if len(hist) >= MIN_HISTORY_LEN:
            score = calculate_score(price, change, fng, hist)
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
            "Precio": f"${price:,.2f}",
            "24h %": f"{change:+.2f}%",
            "Score": f"{score:.1f}",
            "Señal": sig
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
    st.metric("Fear & Greed", f"{fng}/100 ({fng_label})")
    st.caption(f"Ciclo: {st.session_state.cycle_count} | Datos: {'Real' if source=='real' else 'Sim'}")

with col2:
    st.subheader("📜 Historial de Operaciones")
    if st.session_state.trades:
        for ts, msg in reversed(st.session_state.trades[-15:]):
            st.text(f"{ts.strftime('%H:%M:%S')} - {msg[:80]}...")
    else:
        st.caption("Aún sin operaciones")
    st.caption("🔔 Las alertas de Telegram incluyen latidos, cambios de puntaje y órdenes.")

# ==================== AUTO REFRESCO ====================
if auto:
    time.sleep(refresh)
    st.rerun()
