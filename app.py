import streamlit as st
import random
import time
import json
import os
from datetime import datetime

# ==================== TELEGRAM ====================
TELEGRAM_TOKEN = "8532857017:AAHwLhRnM3oC6TbgFFKAEmQnZVoo6JD_esQ"
TELEGRAM_CHAT_ID = "5835990242"

def send_telegram(msg):
    try:
        import requests
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=5)
    except Exception as e:
        print(f"Error Telegram: {e}")

# ==================== PARÁMETROS ====================
BUY_SCORE = 55
SELL_SCORE = 45
STOP_LOSS = 2.0          # % de pérdida máxima
TAKE_PROFIT = 3.0        # % de ganancia para asegurar
TRAILING_STOP = 1.5      # % de retroceso desde el máximo para vender
MAX_ORDER_MXN = 500      # Máximo por orden
MAX_DAILY = 200          # Operaciones máximas por día
COMMISSION = 0.1         # 0.1%
SLIPPAGE = 0.05          # 0.05%
REFRESH_SEC = 20         # Actualizar cada 20 segundos

# ==================== SIMULACIÓN DE PRECIOS (REALISTA) ====================
BASE_PRICES = {"BTC": 1_070_000, "ETH": 28_000}
prices_sim = {"BTC": 1_070_000, "ETH": 28_000}
changes_sim = {"BTC": 0.0, "ETH": 0.0}

def get_price(symbol):
    global prices_sim, changes_sim
    last = prices_sim.get(symbol, BASE_PRICES[symbol])
    pct = random.uniform(-0.008, 0.008)   # variación entre -0.8% y +0.8%
    new_price = last * (1 + pct)
    # No se aleje más del 10% del precio base
    new_price = max(BASE_PRICES[symbol] * 0.9, min(BASE_PRICES[symbol] * 1.1, new_price))
    # Cambio 24h simulado
    changes_sim[symbol] += random.uniform(-0.2, 0.2)
    changes_sim[symbol] = max(-5, min(5, changes_sim[symbol]))
    prices_sim[symbol] = new_price
    return new_price, changes_sim[symbol]

def get_fear():
    if "fg" not in st.session_state:
        st.session_state.fg = 50
    st.session_state.fg += random.uniform(-2, 2)
    st.session_state.fg = max(10, min(90, st.session_state.fg))
    if st.session_state.fg < 25:
        label = "Extreme Fear"
    elif st.session_state.fg < 40:
        label = "Fear"
    elif st.session_state.fg < 60:
        label = "Neutral"
    elif st.session_state.fg < 75:
        label = "Greed"
    else:
        label = "Extreme Greed"
    return int(st.session_state.fg), label

# ==================== CÁLCULO DE PUNTAJE (SIN ERRORES) ====================
def calculate_score(price, change_24h, fear, price_history):
    """
    price_history: lista de precios recientes (máx 20)
    """
    score = 50
    # Fear & Greed (aporta hasta ±20)
    score += (50 - fear) * 0.4
    # Cambio 24h (aporta hasta ±12)
    score += change_24h * 1.2
    # Tendencia simple (si hay al menos 2 precios)
    if len(price_history) >= 2:
        trend = price_history[-1] - price_history[-2]
        if trend > 0:
            score += 8
        else:
            score -= 8
    return max(0, min(100, score))

# ==================== PERSISTENCIA (GUARDA ESTADO) ====================
STATE_FILE = "bot_state.json"

def save_state():
    state = {
        "balance": st.session_state.balance,
        "positions": st.session_state.positions,
        "trades": [(t.isoformat(), m) for t, m in st.session_state.trades[-100:]],
        "price_history": {k: list(v) for k, v in st.session_state.price_history.items()},
        "last_action": st.session_state.last_action,
        "last_prices": st.session_state.last_prices,
        "entry_price": st.session_state.entry_price,
        "highest_price": st.session_state.highest_price,
        "daily_trades": st.session_state.daily_trades,
        "last_trade_day": st.session_state.last_trade_day,
        "cycle": st.session_state.cycle
    }
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return None

# ==================== INICIALIZAR SESIÓN ====================
saved = load_state()
if saved:
    st.session_state.balance = saved["balance"]
    st.session_state.positions = saved["positions"]
    st.session_state.trades = [(datetime.fromisoformat(t), m) for t, m in saved["trades"]]
    st.session_state.price_history = {k: v for k, v in saved["price_history"].items()}
    st.session_state.last_action = saved["last_action"]
    st.session_state.last_prices = saved["last_prices"]
    st.session_state.entry_price = saved["entry_price"]
    st.session_state.highest_price = saved["highest_price"]
    st.session_state.daily_trades = saved["daily_trades"]
    st.session_state.last_trade_day = saved["last_trade_day"]
    st.session_state.cycle = saved["cycle"]
else:
    st.session_state.balance = 1000.0
    st.session_state.positions = {"BTC": 0.0, "ETH": 0.0}
    st.session_state.trades = []
    st.session_state.price_history = {"BTC": [], "ETH": []}
    st.session_state.last_action = {"BTC": None, "ETH": None}
    st.session_state.last_prices = {"BTC": 0.0, "ETH": 0.0}
    st.session_state.entry_price = {"BTC": 0.0, "ETH": 0.0}
    st.session_state.highest_price = {"BTC": 0.0, "ETH": 0.0}
    st.session_state.daily_trades = 0
    st.session_state.last_trade_day = datetime.now().day
    st.session_state.cycle = 0

# ==================== GESTIÓN DE RIESGO ====================
def can_trade():
    now_day = datetime.now().day
    if now_day != st.session_state.last_trade_day:
        st.session_state.daily_trades = 0
        st.session_state.last_trade_day = now_day
    return st.session_state.daily_trades < MAX_DAILY

def check_stop_loss(symbol, current_price):
    entry = st.session_state.entry_price.get(symbol, 0)
    if entry == 0:
        return False
    loss = (current_price - entry) / entry * 100
    return loss <= -STOP_LOSS

def check_take_profit(symbol, current_price):
    entry = st.session_state.entry_price.get(symbol, 0)
    if entry == 0:
        return False
    profit = (current_price - entry) / entry * 100
    return profit >= TAKE_PROFIT

def check_trailing_stop(symbol, current_price):
    entry = st.session_state.entry_price.get(symbol, 0)
    if entry == 0:
        return False
    high = st.session_state.highest_price.get(symbol, current_price)
    if current_price > high:
        st.session_state.highest_price[symbol] = current_price
        high = current_price
    return current_price <= high * (1 - TRAILING_STOP / 100)

def execute_trade(symbol, action, price):
    if action == "BUY":
        if not can_trade():
            return "❌ Límite diario alcanzado"
        amount = min(MAX_ORDER_MXN, st.session_state.balance)
        if amount <= 0:
            return "❌ Saldo insuficiente"
        eff_price = price * (1 + SLIPPAGE / 100)
        commission = amount * COMMISSION / 100
        qty = (amount - commission) / eff_price
        st.session_state.balance -= amount
        st.session_state.positions[symbol] += qty
        st.session_state.entry_price[symbol] = eff_price
        st.session_state.highest_price[symbol] = eff_price
        st.session_state.daily_trades += 1
        return (f"🟢 *COMPRA* {symbol}\n"
                f"Cantidad: {qty:.6f}\n"
                f"Precio: ${eff_price:,.2f} MXN\n"
                f"Comisión: ${commission:.2f}\n"
                f"Saldo: ${st.session_state.balance:.2f}")
    else:  # SELL
        qty = st.session_state.positions.get(symbol, 0)
        if qty <= 0:
            return "❌ No hay posición"
        eff_price = price * (1 - SLIPPAGE / 100)
        gross = qty * eff_price
        commission = gross * COMMISSION / 100
        net = gross - commission
        st.session_state.balance += net
        st.session_state.positions[symbol] = 0
        st.session_state.daily_trades += 1
        return (f"🔴 *VENTA* {symbol}\n"
                f"Cantidad: {qty:.6f}\n"
                f"Precio: ${eff_price:,.2f}\n"
                f"Neto: ${net:.2f}\n"
                f"Saldo: ${st.session_state.balance:.2f}")

# ==================== INTERFAZ STREAMLIT ====================
st.set_page_config(page_title="Crypto Bot Rápido", layout="wide")
st.title("🤖 Crypto Bot - Trading en MXN (Sin errores)")

st.sidebar.header("⚙️ Configuración")
refresh = st.sidebar.slider("Intervalo (segundos)", 10, 60, REFRESH_SEC)
auto = st.sidebar.checkbox("Auto-refrescar", value=True)
buy_th = st.sidebar.number_input("Compra si score ≥", 0, 100, BUY_SCORE)
sell_th = st.sidebar.number_input("Vende si score ≤", 0, 100, SELL_SCORE)

st.sidebar.subheader("💰 Cartera")
st.sidebar.metric("Saldo MXN", f"${st.session_state.balance:,.2f}")
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
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
    st.rerun()

if st.sidebar.button("📢 Enviar alerta de prueba"):
    send_telegram("🧪 Alerta de prueba - Bot funcionando")
    st.success("Alerta enviada")

st.info("✅ Modo simulación realista sin APIs externas. El bot empieza a operar desde el primer ciclo.")

# ==================== OBTENER DATOS Y PROCESAR ====================
fear, fear_label = get_fear()
st.session_state.cycle += 1

# Actualizar precios y historial
price_data = {}
for sym in ["BTC", "ETH"]:
    price, change = get_price(sym)
    st.session_state.last_prices[sym] = price
    price_data[sym] = (price, change)
    st.session_state.price_history[sym].append(price)
    if len(st.session_state.price_history[sym]) > 20:
        st.session_state.price_history[sym] = st.session_state.price_history[sym][-20:]

# Guardar estado cada 10 ciclos
if st.session_state.cycle % 10 == 0:
    save_state()

# Enviar latido de vida cada 30 ciclos (~10 minutos)
if st.session_state.cycle % 30 == 0 and st.session_state.cycle > 0:
    send_telegram(f"💓 Heartbeat - Ciclo {st.session_state.cycle} | Venta si score ≤ {sell_th}")

# Procesar cada criptomoneda
for sym in ["BTC", "ETH"]:
    price, change = price_data[sym]
    hist = st.session_state.price_history[sym]
    # Calcular puntaje usando el historial (aunque sea de 1 elemento)
    score = calculate_score(price, change, fear, hist)
    
    # Determinar acción base
    if score >= buy_th:
        action = "BUY"
    elif score <= sell_th:
        action = "SELL"
    else:
        action = "HOLD"
    
    # Verificar condiciones de salida si hay posición abierta
    exit_reason = None
    if st.session_state.positions.get(sym, 0) > 0:
        if check_stop_loss(sym, price):
            action = "SELL"
            exit_reason = f"Stop Loss ({STOP_LOSS}%)"
        elif check_take_profit(sym, price):
            action = "SELL"
            exit_reason = f"Take Profit ({TAKE_PROFIT}%)"
        elif check_trailing_stop(sym, price):
            action = "SELL"
            exit_reason = f"Trailing Stop ({TRAILING_STOP}%)"
    
    # Ejecutar solo si la acción cambió respecto al ciclo anterior
    last_act = st.session_state.last_action.get(sym)
    if action != last_act and action in ("BUY", "SELL"):
        msg = execute_trade(sym, action, price)
        if msg:
            if exit_reason:
                msg += f"\n*Motivo:* {exit_reason}"
            send_telegram(msg)
            st.session_state.trades.append((datetime.now(), msg))
            save_state()  # guardar tras cada operación
        st.session_state.last_action[sym] = action

# ==================== MOSTRAR DATOS EN PANTALLA ====================
col1, col2 = st.columns(2)
with col1:
    st.subheader("📊 Señales en Vivo (MXN)")
    rows = []
    for sym in ["BTC", "ETH"]:
        name = "Bitcoin" if sym == "BTC" else "Ethereum"
        price, change = price_data.get(sym, (0, 0))
        if price == 0:
            rows.append({"Moneda": name, "Precio": "Error", "24h%": "N/A", "Score": "N/A", "Señal": "ERROR"})
            continue
        hist = st.session_state.price_history[sym]
        score = calculate_score(price, change, fear, hist)
        if score >= buy_th:
            signal = "🟢 COMPRAR"
        elif score <= sell_th:
            signal = "🔴 VENDER"
        else:
            signal = "⚪ MANTENER"
        rows.append({
            "Moneda": name,
            "Precio (MXN)": f"${price:,.0f}",
            "24h %": f"{change:+.2f}%",
            "Score": f"{score:.1f}",
            "Señal": signal
        })
    st.table(rows)   # más ligero que dataframe
    st.metric("Fear & Greed", f"{fear}/100 ({fear_label})")
    st.caption(f"Ciclo: {st.session_state.cycle} | Venta si score ≤ {sell_th} | Hoy: {st.session_state.daily_trades} ops")

with col2:
    st.subheader("📜 Historial de Operaciones")
    if st.session_state.trades:
        for ts, msg in reversed(st.session_state.trades[-15:]):
            st.text(f"{ts.strftime('%H:%M:%S')} - {msg[:80]}...")
    else:
        st.caption("Esperando operaciones...")
    st.caption("✅ Datos persistentes. El bot puede operar durante horas.")

# ==================== AUTO REFRESCO ====================
if auto:
    time.sleep(refresh)
    st.rerun()
