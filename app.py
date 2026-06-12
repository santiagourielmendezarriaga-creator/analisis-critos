import streamlit as st
import pandas as pd
import numpy as np
import time
import random
import json
import os
from collections import deque
from datetime import datetime

# ==================== CONFIGURACIÓN TELEGRAM ====================
TELEGRAM_TOKEN = "8532857017:AAHwLhRnM3oC6TbgFFKAEmQnZVoo6JD_esQ"
TELEGRAM_CHAT_ID = "5835990242"

def send_telegram(message, parse_mode="Markdown"):
    try:
        import requests
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": parse_mode}
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        st.error(f"Error Telegram: {e}")
        return False

# ==================== PARÁMETROS DE ESTRATEGIA (AJUSTABLES) ====================
BUY_THRESHOLD = 50          # Compra cuando puntaje >= 50
SELL_THRESHOLD = 55         # Vende cuando puntaje <= 55 (más alto que compra, rota rápido)
STOP_LOSS_PCT = 1.5         # Stop loss al 1.5%
TAKE_PROFIT_PCT = 2.5       # Take profit al 2.5%
TRAILING_STOP_PCT = 1.0     # Trailing stop al 1.0%
MAX_POSITION_SIZE_MXN = 500.0   # Máximo 500 MXN por operación
MAX_DAILY_TRADES = 500      # Límite altísimo (para más de 2 horas)
COMMISSION_PCT = 0.1        # 0.1% de comisión
SLIPPAGE_PCT = 0.05         # 0.05% de deslizamiento
REFRESH_INTERVAL_SEC = 30   # Actualizar cada 30 segundos
HEARTBEAT_CYCLES = 30       # Latido cada 30 ciclos (~15 minutos)
MIN_HISTORY_LEN = 2         # Reaccionar con solo 2 datos

# ==================== SIMULACIÓN REALISTA DE MERCADO (MXN) ====================
# Precios base (actualizados a junio 2026)
BASE_PRICES_MXN = {"BTC": 1_070_000, "ETH": 28_000}
SIM_PRICES = {"BTC": 1_070_000, "ETH": 28_000}
SIM_CHANGES = {"BTC": 0.0, "ETH": 0.0}

def get_simulated_price(symbol):
    """Genera precios sintéticos realistas (sin errores de red)."""
    global SIM_PRICES, SIM_CHANGES
    base = BASE_PRICES_MXN[symbol]
    last = SIM_PRICES.get(symbol, base)
    # Movimiento aleatorio entre -0.8% y +0.8% por ciclo (volatilidad moderada)
    change_pct = random.uniform(-0.008, 0.008)
    new_price = last * (1 + change_pct)
    # Limitar desviación máxima del 10% respecto al base
    new_price = max(base * 0.9, min(base * 1.1, new_price))
    # Simular cambio 24h (tendencia suave)
    sim_change = SIM_CHANGES.get(symbol, 0.0)
    sim_change += random.uniform(-0.2, 0.2)
    sim_change = max(-5, min(5, sim_change))
    SIM_PRICES[symbol] = new_price
    SIM_CHANGES[symbol] = sim_change
    return new_price, sim_change

def get_fear_greed():
    """Simula Fear & Greed variable entre 10 y 90."""
    if "fg_value" not in st.session_state:
        st.session_state.fg_value = 50
    st.session_state.fg_value += random.uniform(-2, 2)
    st.session_state.fg_value = max(10, min(90, st.session_state.fg_value))
    if st.session_state.fg_value < 25:
        label = "Extreme Fear"
    elif st.session_state.fg_value < 40:
        label = "Fear"
    elif st.session_state.fg_value < 60:
        label = "Neutral"
    elif st.session_state.fg_value < 75:
        label = "Greed"
    else:
        label = "Extreme Greed"
    return int(st.session_state.fg_value), label

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
    if len(price_history) >= MIN_HISTORY_LEN:
        trend = np.mean(np.diff(price_history[-MIN_HISTORY_LEN:]))
        score += 6 if trend > 0 else -6
    return np.clip(score, 0, 100)

# ==================== PERSISTENCIA DE ESTADO (ARCHIVO JSON) ====================
STATE_FILE = "bot_state.json"

def load_state():
    """Carga el estado desde archivo JSON si existe."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                return data
        except:
            pass
    return None

def save_state():
    """Guarda el estado actual en archivo JSON."""
    state = {
        "balance": st.session_state.balance,
        "positions": st.session_state.positions,
        "trades": [(ts.isoformat(), msg) for ts, msg in st.session_state.trades[-100:]],  # últimas 100
        "price_history": {k: list(v) for k, v in st.session_state.price_history.items()},
        "last_action": st.session_state.last_action,
        "last_prices": st.session_state.last_prices,
        "entry_price": st.session_state.entry_price,
        "highest_price": st.session_state.highest_price,
        "cycle_count": st.session_state.cycle_count,
        "daily_trades": st.session_state.daily_trades,
        "last_trade_day": st.session_state.last_trade_day,
        "fg_value": st.session_state.get("fg_value", 50),
        "last_score": st.session_state.last_score
    }
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

# ==================== INICIALIZAR ESTADO (con persistencia) ====================
saved = load_state()
if saved:
    st.session_state.balance = saved["balance"]
    st.session_state.positions = saved["positions"]
    st.session_state.trades = [(datetime.fromisoformat(ts), msg) for ts, msg in saved["trades"]]
    st.session_state.price_history = {k: deque(v, maxlen=100) for k, v in saved["price_history"].items()}
    st.session_state.last_action = saved["last_action"]
    st.session_state.last_prices = saved["last_prices"]
    st.session_state.entry_price = saved["entry_price"]
    st.session_state.highest_price = saved["highest_price"]
    st.session_state.cycle_count = saved["cycle_count"]
    st.session_state.daily_trades = saved["daily_trades"]
    st.session_state.last_trade_day = saved["last_trade_day"]
    st.session_state.fg_value = saved.get("fg_value", 50)
    st.session_state.last_score = saved.get("last_score", {"BTC": 50, "ETH": 50})
else:
    st.session_state.balance = 1000.0
    st.session_state.positions = {"BTC": 0.0, "ETH": 0.0}
    st.session_state.trades = []
    st.session_state.price_history = {"BTC": deque(maxlen=100), "ETH": deque(maxlen=100)}
    st.session_state.last_action = {"BTC": None, "ETH": None}
    st.session_state.last_prices = {"BTC": 0.0, "ETH": 0.0}
    st.session_state.entry_price = {"BTC": 0.0, "ETH": 0.0}
    st.session_state.highest_price = {"BTC": 0.0, "ETH": 0.0}
    st.session_state.cycle_count = 0
    st.session_state.daily_trades = 0
    st.session_state.last_trade_day = datetime.now().day
    st.session_state.fg_value = 50
    st.session_state.last_score = {"BTC": 50, "ETH": 50}

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
    return (current_price - entry) / entry * 100 <= -STOP_LOSS_PCT

def check_take_profit(symbol, current_price):
    entry = st.session_state.entry_price.get(symbol, 0)
    if entry == 0:
        return False
    return (current_price - entry) / entry * 100 >= TAKE_PROFIT_PCT

def check_trailing_stop(symbol, current_price):
    entry = st.session_state.entry_price.get(symbol, 0)
    if entry == 0:
        return False
    high = st.session_state.highest_price.get(symbol, current_price)
    if current_price > high:
        st.session_state.highest_price[symbol] = current_price
        high = current_price
    return current_price <= high * (1 - TRAILING_STOP_PCT / 100)

def execute_trade(symbol, action, price, exit_reason=""):
    if action == "BUY":
        if not can_trade():
            return None, "❌ Límite diario de operaciones alcanzado"
        amount_mxn = min(MAX_POSITION_SIZE_MXN, st.session_state.balance)
        if amount_mxn <= 0:
            return None, "❌ Saldo insuficiente"
        eff_price = price * (1 + SLIPPAGE_PCT / 100)
        commission = amount_mxn * COMMISSION_PCT / 100
        amount_after = amount_mxn - commission
        qty = amount_after / eff_price
        st.session_state.balance -= amount_mxn
        st.session_state.positions[symbol] += qty
        st.session_state.entry_price[symbol] = eff_price
        st.session_state.highest_price[symbol] = eff_price
        record_trade()
        msg = (f"🟢 *COMPRA* {symbol}\n"
               f"Cantidad: {qty:.6f}\n"
               f"Precio efectivo: ${eff_price:,.2f} MXN\n"
               f"Comisión: ${commission:.2f} MXN\n"
               f"Saldo restante: ${st.session_state.balance:,.2f} MXN")
        if exit_reason:
            msg += f"\n*Motivo:* {exit_reason}"
        return qty, msg
    else:  # SELL
        qty = st.session_state.positions.get(symbol, 0)
        if qty <= 0:
            return None, "❌ No hay posición para vender"
        eff_price = price * (1 - SLIPPAGE_PCT / 100)
        gross = qty * eff_price
        commission = gross * COMMISSION_PCT / 100
        net = gross - commission
        st.session_state.balance += net
        st.session_state.positions[symbol] = 0
        record_trade()
        msg = (f"🔴 *VENTA* {symbol}\n"
               f"Cantidad: {qty:.6f}\n"
               f"Precio efectivo: ${eff_price:,.2f} MXN\n"
               f"Comisión: ${commission:.2f} MXN\n"
               f"Neto: ${net:,.2f} MXN\n"
               f"Saldo nuevo: ${st.session_state.balance:,.2f} MXN")
        if exit_reason:
            msg += f"\n*Motivo:* {exit_reason}"
        return qty, msg

# ==================== INTERFAZ STREAMLIT ====================
st.set_page_config(page_title="Crypto Bot - MXN (Mínimo Error)", layout="wide")
st.title("🤖 Crypto Bot - Trading en MXN (Bitso Simulado)")

st.sidebar.header("⚙️ Configuración en Vivo")
refresh = st.sidebar.slider("Intervalo (segundos)", 15, 60, REFRESH_INTERVAL_SEC)
auto = st.sidebar.checkbox("Auto-refrescar", value=True)
buy_th = st.sidebar.number_input("Umbral COMPRA (0-100)", 0, 100, BUY_THRESHOLD, 5)
sell_th = st.sidebar.number_input("Umbral VENTA (0-100)", 0, 100, SELL_THRESHOLD, 5)

st.sidebar.subheader("💰 Cartera (MXN)")
st.sidebar.metric("Saldo MXN", f"${st.session_state.balance:,.2f}")
total_val = st.session_state.balance
for sym in ["BTC", "ETH"]:
    price = st.session_state.last_prices.get(sym, 0)
    qty = st.session_state.positions.get(sym, 0)
    if qty > 0 and price > 0:
        total_val += qty * price
st.sidebar.metric("Valor total", f"${total_val:,.2f}")
st.sidebar.metric("Operaciones hoy", st.session_state.daily_trades)

if st.sidebar.button("Reiniciar simulación (1000 MXN)"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
    st.rerun()

if st.sidebar.button("📢 Enviar alerta de prueba"):
    send_telegram("🧪 Alerta de prueba - Bot operando sin errores")
    st.success("Alerta enviada")

st.info("✅ Simulación realista (sin APIs externas) - Mínimo error. El bot puede operar días seguidos con persistencia.")

# ==================== OBTENER DATOS SIMULADOS ====================
fng, fng_label = get_fear_greed()
price_data = {}
for sym in ["BTC", "ETH"]:
    price, change = get_simulated_price(sym)
    st.session_state.last_prices[sym] = price
    price_data[sym] = (price, change, "sim")
    if price > 0:
        st.session_state.price_history[sym].append(price)
        if price > st.session_state.highest_price.get(sym, 0):
            st.session_state.highest_price[sym] = price

st.session_state.cycle_count += 1
now = time.time()
if "last_cycle_time" not in st.session_state:
    st.session_state.last_cycle_time = now
gap = now - st.session_state.last_cycle_time
if gap > 300:
    send_telegram(f"⚠️ Reanudación tras {gap:.0f}s")
st.session_state.last_cycle_time = now
if st.session_state.cycle_count % HEARTBEAT_CYCLES == 0:
    send_telegram(f"💓 Heartbeat ciclo {st.session_state.cycle_count} | Venta si score ≤ {sell_th}")

# Guardar estado periódicamente (cada 10 ciclos)
if st.session_state.cycle_count % 10 == 0:
    save_state()

# ==================== DECISIONES Y ALERTAS ====================
for sym in ["BTC", "ETH"]:
    price, change, _ = price_data[sym]
    if price == 0:
        continue
    hist = list(st.session_state.price_history[sym])
    if len(hist) < MIN_HISTORY_LEN:
        continue
    score = calculate_score(price, change, fng, hist)

    # Alerta cambio significativo
    last_score = st.session_state.last_score.get(sym, 50)
    if abs(score - last_score) >= 3:
        send_telegram(f"📊 *{sym}* Puntaje: {last_score:.1f} → {score:.1f}")
        st.session_state.last_score[sym] = score

    # Acción según umbrales ajustables
    if score >= buy_th:
        action = "BUY"
    elif score <= sell_th:
        action = "SELL"
    else:
        action = "HOLD"

    exit_reason = None
    if st.session_state.positions.get(sym, 0) > 0:
        if check_stop_loss(sym, price):
            action = "SELL"
            exit_reason = f"Stop Loss ({STOP_LOSS_PCT}%)"
        elif check_take_profit(sym, price):
            action = "SELL"
            exit_reason = f"Take Profit ({TAKE_PROFIT_PCT}%)"
        elif check_trailing_stop(sym, price):
            action = "SELL"
            exit_reason = f"Trailing Stop ({TRAILING_STOP_PCT}%)"

    last_act = st.session_state.last_action.get(sym)
    if (action != last_act and action in ("BUY", "SELL")):
        qty, msg = execute_trade(sym, action, price, exit_reason)
        if msg:
            send_telegram(msg)
            st.session_state.trades.append((datetime.now(), msg))
            save_state()  # guardar tras cada operación
        st.session_state.last_action[sym] = action

# ==================== MOSTRAR INTERFAZ ====================
col1, col2 = st.columns(2)
with col1:
    st.subheader("📊 Señales en Vivo (MXN)")
    rows = []
    for sym in ["BTC", "ETH"]:
        name = "Bitcoin" if sym == "BTC" else "Ethereum"
        price, change, _ = price_data.get(sym, (0,0,""))
        if price == 0:
            rows.append({"Moneda": name, "Precio": "Error", "24h %": "N/A", "Score": "N/A", "Señal": "ERROR"})
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
            "Precio (MXN)": f"${price:,.2f}",
            "24h %": f"{change:+.2f}%",
            "Score": f"{score:.1f}",
            "Señal": sig
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
    st.metric("Fear & Greed", f"{fng}/100 ({fng_label})")
    st.caption(f"Ciclo: {st.session_state.cycle_count} | Venta si score ≤ {sell_th} | Hoy: {st.session_state.daily_trades} ops")

with col2:
    st.subheader("📜 Historial de Operaciones")
    if st.session_state.trades:
        for ts, msg in reversed(st.session_state.trades[-20:]):
            st.text(f"{ts.strftime('%H:%M:%S')} - {msg[:80]}...")
    else:
        st.caption("Esperando operaciones...")
    st.caption("El bot guarda el estado cada 10 ciclos y tras cada operación. No hay pérdida de datos.")

# ==================== AUTO REFRESCO ====================
if auto:
    time.sleep(refresh)
    st.rerun()
