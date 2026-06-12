import streamlit as st
import pandas as pd
import numpy as np
import time
import requests
from collections import deque
from datetime import datetime
import plotly.express as px
import random

# ==================== CONFIGURACIÓN TELEGRAM ====================
TELEGRAM_TOKEN = "8532857017:AAHwLhRnM3oC6TbgFFKAEmQnZVoo6JD_esQ"
TELEGRAM_CHAT_ID = "5835990242"

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}, timeout=5)
    except:
        pass

# ==================== PARÁMETROS DE SIMULACIÓN ====================
DEFAULT_COMMISSION_PCT = 0.1  # 0.1% por operación
DEFAULT_SLIPPAGE_PCT = 0.05   # 0.05% de deslizamiento

# ==================== DATOS REALES CON FALLBACK ====================
if "use_real" not in st.session_state:
    st.session_state.use_real = True
if "last_fail" not in st.session_state:
    st.session_state.last_fail = 0

def get_real_price(symbol):
    try:
        url_price = f"https://min-api.cryptocompare.com/data/price?fsym={symbol}&tsyms=USD"
        resp = requests.get(url_price, timeout=5)
        if resp.status_code != 200:
            return None, None
        price = float(resp.json()["USD"])
        url_change = f"https://min-api.cryptocompare.com/data/pricemultifull?fsyms={symbol}&tsyms=USD"
        resp2 = requests.get(url_change, timeout=5)
        if resp2.status_code == 200:
            data = resp2.json()
            change = data["RAW"][symbol]["USD"]["CHANGEPCT24HOUR"]
            return price, change
        return price, 0.0
    except:
        return None, None

REAL_BASES = {"BTC": 65000, "ETH": 3500}
SIM_PRICES = {"BTC": 65000, "ETH": 3500}
SIM_CHANGES = {"BTC": 0.0, "ETH": 0.0}

def get_price(symbol):
    global SIM_PRICES, SIM_CHANGES
    now = time.time()
    if st.session_state.use_real and (now - st.session_state.last_fail > 300):
        price, change = get_real_price(symbol)
        if price is not None:
            return price, change, "real"
        else:
            st.session_state.last_fail = now
            st.session_state.use_real = False
    last_price = SIM_PRICES.get(symbol, REAL_BASES[symbol])
    change_pct = random.uniform(-0.01, 0.01)
    new_price = last_price * (1 + change_pct)
    sim_change = SIM_CHANGES.get(symbol, 0.0)
    sim_change += random.uniform(-0.5, 0.5)
    sim_change = max(-10, min(10, sim_change))
    SIM_PRICES[symbol] = new_price
    SIM_CHANGES[symbol] = sim_change
    return new_price, sim_change, "sim"

def get_fear_greed():
    try:
        resp = requests.get("https://api.alternative.me/fng/", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return int(data['data'][0]['value']), data['data'][0]['value_classification']
    except:
        pass
    return 50, "Neutral"

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

def calculate_score(price, change, fng, hist):
    score = 50
    score += (50 - fng) * 0.5
    score += np.clip(change * 2, -12, 12)
    if len(hist) >= 14:
        rsi = compute_rsi(list(hist))
        if rsi < 30:
            score += 15
        elif rsi < 40:
            score += 8
        elif rsi > 70:
            score -= 15
        elif rsi > 60:
            score -= 8
    if len(hist) >= 3:   # ANTES ERA 5, AHORA 3 PARA ALERTAS MÁS RÁPIDAS
        trend = np.mean(np.diff(list(hist)[-3:]))
        score += 10 if trend > 0 else -10
    return np.clip(score, 0, 100)

# ==================== INICIALIZAR ESTADO ====================
if "balance" not in st.session_state:
    st.session_state.balance = 1000.0
    st.session_state.positions = {"BTC": 0.0, "ETH": 0.0}
    st.session_state.trades = []
    st.session_state.price_history = {"BTC": deque(maxlen=50), "ETH": deque(maxlen=50)}
    st.session_state.last_action = {"BTC": None, "ETH": None}
    st.session_state.last_prices = {"BTC": 0.0, "ETH": 0.0}
    st.session_state.last_score = {"BTC": 50, "ETH": 50}   # para alertas de cambio
    st.session_state.commission_pct = DEFAULT_COMMISSION_PCT
    st.session_state.slippage_pct = DEFAULT_SLIPPAGE_PCT

CRYPTOS = {"BTC": "Bitcoin", "ETH": "Ethereum"}

st.set_page_config(page_title="Crypto Auto Trader - Alertas Rápidas", layout="wide")
st.title("🤖 Crypto Auto Trader - Modo Alertas Frecuentes")

st.sidebar.header("⚙️ Configuración de Alertas")
refresh = st.sidebar.slider("Actualizar cada (segundos)", 30, 180, 60)   # intervalo más bajo
auto = st.sidebar.checkbox("Auto-refrescar", True)

# Umbrales más sensibles por defecto
buy_th = st.sidebar.slider("Umbral COMPRA (más bajo = más alertas)", 30, 80, 50)
sell_th = st.sidebar.slider("Umbral VENTA (más alto = más alertas)", 20, 70, 50)
trade_amount = st.sidebar.number_input("Monto por orden (USDT)", 10.0, 100.0, 20.0)

# Nueva opción: alerta por cambio de puntaje (no solo cambio de acción)
alert_on_score_change = st.sidebar.checkbox("Enviar alerta cada vez que el puntaje cambie (+info)", value=True)

st.sidebar.subheader("💰 Costos de Simulación")
commission = st.sidebar.number_input("Comisión (%)", 0.0, 1.0, st.session_state.commission_pct, 0.05)
slippage = st.sidebar.number_input("Slippage (%)", 0.0, 1.0, st.session_state.slippage_pct, 0.05)
st.session_state.commission_pct = commission
st.session_state.slippage_pct = slippage

st.sidebar.subheader("💰 Estado de Cartera")
st.sidebar.metric("Saldo USDT", f"${st.session_state.balance:,.2f}")
total = st.session_state.balance
for sym in CRYPTOS:
    last_p = st.session_state.last_prices.get(sym, 0)
    qty = st.session_state.positions.get(sym, 0)
    if qty > 0 and last_p > 0:
        total += qty * last_p
st.sidebar.metric("Valor total", f"${total:,.2f}")
if st.sidebar.button("Reiniciar simulación"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

if not st.session_state.use_real:
    st.warning("⚠️ **Modo simulación** – Datos simulados (alertas seguirán funcionando)")

# Botón manual para probar alerta
if st.sidebar.button("📢 Enviar alerta de prueba a Telegram"):
    send_telegram("🧪 *Alerta de prueba* - Tu bot está funcionando correctamente.")

# ==================== OBTENER DATOS ====================
fng, fng_label = get_fear_greed()
price_data = {}
for sym, name in CRYPTOS.items():
    price, change, source = get_price(sym)
    st.session_state.last_prices[sym] = price
    price_data[sym] = (price, change, source)
    if price > 0:
        st.session_state.price_history[sym].append(price)

# ==================== LÓGICA DE TRADING CON ALERTAS FRECUENTES ====================
for sym, name in CRYPTOS.items():
    price, change, source = price_data[sym]
    if price == 0:
        continue
    hist = st.session_state.price_history[sym]
    # Incluso con pocos datos, calculamos score (para alertas)
    score = calculate_score(price, change, fng, hist)
    # Determinar acción según umbrales (aunque hist <3, la acción podría ser incorrecta, pero alertamos igual)
    if score >= buy_th:
        action = "BUY"
    elif score <= sell_th:
        action = "SELL"
    else:
        action = "HOLD"

    # --- ALERTA POR CAMBIO DE PUNTAJE (opcional) ---
    if alert_on_score_change:
        last_score = st.session_state.last_score.get(sym, 50)
        if abs(score - last_score) >= 1:  # cualquier cambio mínimo
            alert_msg = f"📊 *{name}* Puntaje: {score:.1f} (cambio de {last_score:.1f}) | Señal: {action}"
            send_telegram(alert_msg)
            st.session_state.last_score[sym] = score

    # --- EJECUCIÓN DE ÓRDENES (solo si cambia la acción y hay datos suficientes) ---
    # Para ejecutar órdenes, necesitamos al menos 3 lecturas (para tener una tendencia mínima)
    if len(hist) >= 3:
        if action != st.session_state.last_action.get(sym) and action in ("BUY", "SELL"):
            # Aplicar slippage
            if action == "BUY":
                effective_price = price * (1 + st.session_state.slippage_pct / 100)
                if st.session_state.balance >= trade_amount:
                    amount_after_commission = trade_amount * (1 - st.session_state.commission_pct / 100)
                    qty = amount_after_commission / effective_price
                    st.session_state.balance -= trade_amount
                    st.session_state.positions[sym] += qty
                    msg = (f"🟢 *{name}* COMPRA\n"
                           f"  Precio visto: ${price:.2f}\n"
                           f"  Precio efectivo (slippage {st.session_state.slippage_pct}%): ${effective_price:.2f}\n"
                           f"  Comisión {st.session_state.commission_pct}%: ${trade_amount * st.session_state.commission_pct/100:.2f}\n"
                           f"  Cantidad: {qty:.6f}\n"
                           f"  Score: {score:.1f}")
                else:
                    msg = f"❌ Saldo insuficiente para comprar {name}"
                    send_telegram(msg)
                    continue
            else:  # SELL
                effective_price = price * (1 - st.session_state.slippage_pct / 100)
                qty = st.session_state.positions.get(sym, 0)
                if qty > 0:
                    gross_revenue = qty * effective_price
                    commission_amount = gross_revenue * st.session_state.commission_pct / 100
                    net_revenue = gross_revenue - commission_amount
                    st.session_state.balance += net_revenue
                    st.session_state.positions[sym] = 0
                    msg = (f"🔴 *{name}* VENTA\n"
                           f"  Precio visto: ${price:.2f}\n"
                           f"  Precio efectivo (slippage {st.session_state.slippage_pct}%): ${effective_price:.2f}\n"
                           f"  Comisión {st.session_state.commission_pct}%: ${commission_amount:.2f}\n"
                           f"  Ingreso neto: ${net_revenue:.2f}\n"
                           f"  Score: {score:.1f}")
                else:
                    msg = f"❌ No hay posición para vender {name}"
                    send_telegram(msg)
                    continue
            send_telegram(msg)
            st.session_state.trades.append((datetime.now(), msg))
            st.session_state.last_action[sym] = action
    else:
        # Si aún no hay suficientes datos, mostramos en la interfaz pero no ejecutamos órdenes
        pass

# ==================== INTERFAZ PRINCIPAL ====================
col1, col2 = st.columns(2)
with col1:
    st.subheader("📊 Señales en vivo (alertas frecuentes)")
    rows = []
    for sym, name in CRYPTOS.items():
        price, change, source = price_data[sym]
        if price == 0:
            rows.append({"Moneda": name, "Precio": "Sin datos", "24h %": "N/A", "Puntaje": "N/A", "Señal": "ERROR", "Fuente": "N/A"})
            continue
        hist = st.session_state.price_history[sym]
        score = calculate_score(price, change, fng, hist)
        if score >= buy_th:
            signal_display = "COMPRAR"
        elif score <= sell_th:
            signal_display = "VENDER"
        else:
            signal_display = "MANTENER"
        rows.append({
            "Moneda": name,
            "Precio": f"${price:,.2f}",
            "24h %": f"{change:+.2f}%",
            "Puntaje": f"{score:.1f}/100",
            "Señal": signal_display,
            "Fuente": "Real" if source=="real" else "Sim"
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
    st.metric("😨 Fear & Greed", f"{fng}/100 ({fng_label})")
    st.caption("📢 Las alertas de Telegram se envían cada vez que el puntaje cambia (si activaste la opción) y al ejecutar órdenes.")

with col2:
    st.subheader("📜 Últimas operaciones")
    if st.session_state.trades:
        for ts, msg in reversed(st.session_state.trades[-10:]):
            st.text(f"{ts.strftime('%H:%M:%S')} - {msg.replace('*','')}")
    else:
        st.caption("Aún no hay órdenes ejecutadas. Las alertas de puntaje pueden estar llegando ya.")
    if not st.session_state.use_real and st.button("Intentar conectar a API real de nuevo"):
        st.session_state.use_real = True
        st.session_state.last_fail = 0
        st.rerun()

# ==================== AUTO REFRESCO ====================
if auto:
    time.sleep(refresh)
    st.rerun()
