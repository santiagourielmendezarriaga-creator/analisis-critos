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
    except:
        pass

# ==================== PARÁMETROS ====================
BUY_SCORE = 55          # Compra si puntaje >= 55
SELL_SCORE = 45         # Vende si puntaje <= 45
STOP_LOSS = 2.0         # Stop loss 2%
TAKE_PROFIT = 3.0       # Take profit 3%
TRAILING_STOP = 1.5     # Trailing stop 1.5%
MAX_ORDER_MXN = 500
MAX_DAILY = 200
COMMISSION = 0.1
SLIPPAGE = 0.05
REFRESH_SEC = 20        # Actualiza cada 20 segundos
MIN_HISTORY = 1         # Con 1 dato ya calcula puntaje

# ==================== SIMULACIÓN DE PRECIOS ====================
BASE_PRICES = {"BTC": 1_070_000, "ETH": 28_000}
prices_sim = {"BTC": 1_070_000, "ETH": 28_000}
changes_sim = {"BTC": 0.0, "ETH": 0.0}

def get_price(symbol):
    global prices_sim, changes_sim
    last = prices_sim.get(symbol, BASE_PRICES[symbol])
    # Movimiento aleatorio entre -0.5% y +0.5% (rápido)
    pct = random.uniform(-0.005, 0.005)
    new = last * (1 + pct)
    new = max(BASE_PRICES[symbol]*0.9, min(BASE_PRICES[symbol]*1.1, new))
    changes_sim[symbol] += random.uniform(-0.2, 0.2)
    changes_sim[symbol] = max(-5, min(5, changes_sim[symbol]))
    prices_sim[symbol] = new
    return new, changes_sim[symbol]

def get_fear():
    if "fg" not in st.session_state:
        st.session_state.fg = 50
    st.session_state.fg += random.uniform(-2, 2)
    st.session_state.fg = max(10, min(90, st.session_state.fg))
    label = "Extreme Fear" if st.session_state.fg < 25 else "Fear" if st.session_state.fg < 40 else "Neutral" if st.session_state.fg < 60 else "Greed" if st.session_state.fg < 75 else "Extreme Greed"
    return int(st.session_state.fg), label

# ==================== PUNTAJE SIMPLE ====================
def calc_score(price, change, fear):
    score = 50
    # Fear: miedo suma, avaricia resta
    score += (50 - fear) * 0.4
    # Cambio 24h
    score += change * 1.2
    # Tendencia simple (si tenemos al menos 2 precios)
    if len(price_hist) >= 2:
        trend = price_hist[-1] - price_hist[-2]
        if trend > 0:
            score += 8
        else:
            score -= 8
    return max(0, min(100, score))

# ==================== PERSISTENCIA ====================
STATE_FILE = "state.json"

def save_state():
    with open(STATE_FILE, "w") as f:
        json.dump({
            "balance": st.session_state.balance,
            "positions": st.session_state.positions,
            "trades": [(t.isoformat(), m) for t,m in st.session_state.trades[-50:]],
            "price_history": {k: list(v) for k,v in st.session_state.price_history.items()},
            "last_action": st.session_state.last_action,
            "last_prices": st.session_state.last_prices,
            "entry_price": st.session_state.entry_price,
            "highest_price": st.session_state.highest_price,
            "daily_trades": st.session_state.daily_trades,
            "last_trade_day": st.session_state.last_trade_day,
            "cycle": st.session_state.cycle
        }, f)

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                d = json.load(f)
                return d
        except:
            pass
    return None

# ==================== INICIALIZACIÓN ====================
saved = load_state()
if saved:
    st.session_state.balance = saved["balance"]
    st.session_state.positions = saved["positions"]
    st.session_state.trades = [(datetime.fromisoformat(t), m) for t,m in saved["trades"]]
    st.session_state.price_history = {k: list(v) for k,v in saved["price_history"].items()}
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

# ==================== FUNCIONES DE TRADING ====================
def can_trade():
    day = datetime.now().day
    if day != st.session_state.last_trade_day:
        st.session_state.daily_trades = 0
        st.session_state.last_trade_day = day
    return st.session_state.daily_trades < MAX_DAILY

def check_stop_loss(sym, price):
    entry = st.session_state.entry_price.get(sym, 0)
    return entry > 0 and (price - entry)/entry * 100 <= -STOP_LOSS

def check_take_profit(sym, price):
    entry = st.session_state.entry_price.get(sym, 0)
    return entry > 0 and (price - entry)/entry * 100 >= TAKE_PROFIT

def check_trailing(sym, price):
    entry = st.session_state.entry_price.get(sym, 0)
    if entry == 0:
        return False
    high = st.session_state.highest_price.get(sym, price)
    if price > high:
        st.session_state.highest_price[sym] = price
        high = price
    return price <= high * (1 - TRAILING_STOP/100)

def execute(sym, action, price):
    if action == "BUY":
        if not can_trade():
            return "❌ Límite diario alcanzado"
        amount = min(MAX_ORDER_MXN, st.session_state.balance)
        if amount <= 0:
            return "❌ Saldo insuficiente"
        eff = price * (1 + SLIPPAGE/100)
        com = amount * COMMISSION/100
        qty = (amount - com) / eff
        st.session_state.balance -= amount
        st.session_state.positions[sym] += qty
        st.session_state.entry_price[sym] = eff
        st.session_state.highest_price[sym] = eff
        st.session_state.daily_trades += 1
        return f"🟢 COMPRA {sym}\nCantidad: {qty:.6f}\nPrecio: ${eff:,.2f} MXN\nComisión: ${com:.2f}\nSaldo: ${st.session_state.balance:.2f}"
    else:
        qty = st.session_state.positions.get(sym, 0)
        if qty <= 0:
            return "❌ No hay posición"
        eff = price * (1 - SLIPPAGE/100)
        gross = qty * eff
        com = gross * COMMISSION/100
        net = gross - com
        st.session_state.balance += net
        st.session_state.positions[sym] = 0
        st.session_state.daily_trades += 1
        return f"🔴 VENTA {sym}\nCantidad: {qty:.6f}\nPrecio: ${eff:,.2f}\nNeto: ${net:.2f}\nSaldo: ${st.session_state.balance:.2f}"

# ==================== INTERFAZ ====================
st.set_page_config(page_title="Crypto Bot Rápido", layout="wide")
st.title("🤖 Crypto Bot - Modo Rápido")

st.sidebar.header("Configuración")
refresh = st.sidebar.slider("Intervalo (segundos)", 10, 60, REFRESH_SEC)
auto = st.sidebar.checkbox("Auto-refrescar", value=True)
buy_th = st.sidebar.number_input("Compra si score ≥", 0, 100, BUY_SCORE)
sell_th = st.sidebar.number_input("Vende si score ≤", 0, 100, SELL_SCORE)

st.sidebar.metric("Saldo MXN", f"${st.session_state.balance:,.2f}")
total = st.session_state.balance
for s in ["BTC","ETH"]:
    p = st.session_state.last_prices.get(s,0)
    q = st.session_state.positions.get(s,0)
    if q>0 and p>0:
        total += q*p
st.sidebar.metric("Valor total", f"${total:,.2f}")
st.sidebar.metric("Ops hoy", st.session_state.daily_trades)

if st.sidebar.button("Reiniciar"):
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    if os.path.exists(STATE_FILE): os.remove(STATE_FILE)
    st.rerun()

if st.sidebar.button("Probar alerta"):
    send_telegram("🧪 Alerta de prueba - Bot rápido")

# ==================== LÓGICA PRINCIPAL ====================
fear, fear_label = get_fear()
st.session_state.cycle += 1
data = {}
for sym in ["BTC","ETH"]:
    price, change = get_price(sym)
    st.session_state.last_prices[sym] = price
    data[sym] = (price, change)
    st.session_state.price_history[sym].append(price)
    # Mantener historial corto
    if len(st.session_state.price_history[sym]) > 20:
        st.session_state.price_history[sym] = st.session_state.price_history[sym][-20:]

    # Calcular puntaje incluso con 1 dato (tendencia = 0)
    score = calc_score(price, change, fear)
    # Mostrar en interfaz
    if score >= buy_th:
        signal = "🟢 COMPRAR"
    elif score <= sell_th:
        signal = "🔴 VENDER"
    else:
        signal = "⚪ MANTENER"

    # Ejecutar órdenes
    action = None
    if score >= buy_th:
        action = "BUY"
    elif score <= sell_th:
        action = "SELL"
    else:
        action = "HOLD"

    # Verificar condiciones de salida
    exit_reason = None
    if st.session_state.positions.get(sym,0) > 0:
        if check_stop_loss(sym, price):
            action = "SELL"
            exit_reason = "Stop Loss"
        elif check_take_profit(sym, price):
            action = "SELL"
            exit_reason = "Take Profit"
        elif check_trailing(sym, price):
            action = "SELL"
            exit_reason = "Trailing Stop"

    last = st.session_state.last_action.get(sym)
    if action != last and action in ("BUY","SELL"):
        msg = execute(sym, action, price)
        if exit_reason:
            msg += f"\nMotivo: {exit_reason}"
        send_telegram(msg)
        st.session_state.trades.append((datetime.now(), msg))
        save_state()
        st.session_state.last_action[sym] = action

# ==================== MOSTRAR EN TABLA ====================
col1, col2 = st.columns(2)
with col1:
    st.subheader("Señales")
    rows = []
    for sym in ["BTC","ETH"]:
        name = "Bitcoin" if sym=="BTC" else "Ethereum"
        price, change = data.get(sym, (0,0))
        if price == 0:
            rows.append({"Moneda": name, "Precio": "Error", "24h%": "N/A", "Score": "N/A", "Señal": "ERROR"})
            continue
        # recalcular score para mostrar
        score = calc_score(price, change, fear)
        if score >= buy_th:
            sig = "🟢 COMPRAR"
        elif score <= sell_th:
            sig = "🔴 VENDER"
        else:
            sig = "⚪ MANTENER"
        rows.append({
            "Moneda": name,
            "Precio (MXN)": f"${price:,.0f}",
            "24h%": f"{change:+.2f}%",
            "Score": f"{score:.1f}",
            "Señal": sig
        })
    st.table(rows)  # más ligero que dataframe
    st.metric("Fear & Greed", f"{fear}/100 ({fear_label})")
    st.caption(f"Ciclo: {st.session_state.cycle} | Venta si score ≤ {sell_th}")

with col2:
    st.subheader("Historial")
    if st.session_state.trades:
        for t,m in reversed(st.session_state.trades[-10:]):
            st.text(f"{t.strftime('%H:%M:%S')} - {m[:70]}...")
    else:
        st.caption("Esperando operaciones...")
    st.caption("✅ Bot rápido: sin pandas ni numpy. Arranca inmediatamente.")

# Auto refresco
if auto:
    time.sleep(refresh)
    st.rerun()
