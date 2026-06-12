import streamlit as st
import pandas as pd
import numpy as np
import time
import requests
from collections import deque
from datetime import datetime
import random

# ==================== CONFIGURACIÓN TELEGRAM (VERIFICA TUS DATOS) ====================
TELEGRAM_TOKEN = "8532857017:AAHwLhRnM3oC6TbgFFKAEmQnZVoo6JD_esQ"
TELEGRAM_CHAT_ID = "5835990242"

def send_telegram(message):
    """Envía mensaje a Telegram. Retorna True si éxito, False si error."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return True
        else:
            st.error(f"Telegram error {response.status_code}: {response.text}")
            return False
    except Exception as e:
        st.error(f"Excepción al enviar a Telegram: {e}")
        return False

# ==================== PARÁMETROS ====================
DEFAULT_COMMISSION_PCT = 0.1
DEFAULT_SLIPPAGE_PCT = 0.05
REAL_BASES = {"BTC": 63000, "ETH": 1670}
SIM_PRICES = {"BTC": 63000, "ETH": 1670}
SIM_CHANGES = {"BTC": 0.0, "ETH": 0.0}

# Estado de sesión
if "use_real" not in st.session_state:
    st.session_state.use_real = True
if "last_fail" not in st.session_state:
    st.session_state.last_fail = 0
if "cycle_count" not in st.session_state:
    st.session_state.cycle_count = 0
if "last_heartbeat" not in st.session_state:
    st.session_state.last_heartbeat = 0

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
    global SIM_PRICES, SIM_CHANGES
    now = time.time()
    if st.session_state.use_real and (now - st.session_state.last_fail > 300):
        price, change = get_binance_price(symbol)
        if price and ((symbol=="BTC" and 30000<price<100000) or (symbol=="ETH" and 500<price<5000)):
            return price, change, "real"
        st.session_state.last_fail = now
        st.session_state.use_real = False
    # simulación
    base = REAL_BASES[symbol]
    last_price = SIM_PRICES.get(symbol, base)
    new_price = last_price * (1 + random.uniform(-0.015, 0.015))
    new_price = max(base*0.9, min(base*1.1, new_price))
    sim_change = SIM_CHANGES.get(symbol, 0.0) + random.uniform(-0.3, 0.3)
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
    if len(prices) < period+1:
        return 50
    deltas = np.diff(prices[-period-1:])
    gains = np.where(deltas>0, deltas, 0)
    losses = np.where(deltas<0, -deltas, 0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0:
        return 100
    return 100 - (100/(1+avg_gain/avg_loss))

def calculate_score(price, change, fng, hist):
    score = 50
    score += (50 - fng) * 0.5
    score += np.clip(change * 2, -12, 12)
    if len(hist) >= 14:
        rsi = compute_rsi(list(hist))
        if rsi < 30: score += 15
        elif rsi < 40: score += 8
        elif rsi > 70: score -= 15
        elif rsi > 60: score -= 8
    if len(hist) >= 3:
        trend = np.mean(np.diff(list(hist)[-3:]))
        score += 10 if trend > 0 else -10
    return np.clip(score, 0, 100)

# Inicializar estado
if "balance" not in st.session_state:
    st.session_state.balance = 1000.0
    st.session_state.positions = {"BTC": 0.0, "ETH": 0.0}
    st.session_state.trades = []
    st.session_state.price_history = {"BTC": deque(maxlen=50), "ETH": deque(maxlen=50)}
    st.session_state.last_action = {"BTC": None, "ETH": None}
    st.session_state.last_prices = {"BTC": 0.0, "ETH": 0.0}
    st.session_state.last_score = {"BTC": 50, "ETH": 50}
    st.session_state.commission_pct = DEFAULT_COMMISSION_PCT
    st.session_state.slippage_pct = DEFAULT_SLIPPAGE_PCT
    st.session_state.entry_price = {"BTC": 0.0, "ETH": 0.0}

CRYPTOS = {"BTC": "Bitcoin", "ETH": "Ethereum"}

st.set_page_config(page_title="Crypto Auto Trader", layout="wide")
st.title("🤖 Crypto Auto Trader - Alertas Garantizadas")

st.sidebar.header("Configuración")
refresh = st.sidebar.slider("Actualizar cada (segundos)", 30, 180, 60)
auto = st.sidebar.checkbox("Auto-refrescar", True)
buy_base = st.sidebar.slider("Umbral COMPRA", 40, 80, 60)
sell_base = st.sidebar.slider("Umbral VENTA base", 30, 70, 55)
sell_sensitivity = st.sidebar.slider("Sensibilidad a la VENTA", 0, 100, 90)
sell_threshold = max(20, min(70, sell_base + (sell_sensitivity-50)*0.3))
use_stop_loss = st.sidebar.checkbox("Stop Loss", True)
stop_loss_pct = st.sidebar.number_input("Stop Loss %", 1.0, 20.0, 5.0) if use_stop_loss else 0.0
trade_amount = st.sidebar.number_input("Monto por orden USDT", 10.0, 100.0, 20.0)
alert_on_score_change = st.sidebar.checkbox("Alertas por cambio de puntaje", value=True)
st.sidebar.subheader("💰 Estado")
st.sidebar.metric("Saldo", f"${st.session_state.balance:,.2f}")
total_val = st.session_state.balance
for sym in CRYPTOS:
    last_p = st.session_state.last_prices.get(sym, 0)
    qty = st.session_state.positions.get(sym, 0)
    if qty>0 and last_p>0:
        total_val += qty * last_p
st.sidebar.metric("Valor total", f"${total_val:,.2f}")

if st.sidebar.button("Reiniciar simulación"):
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()

if st.sidebar.button("📢 Enviar alerta de prueba"):
    if send_telegram("🧪 Alerta de prueba - Bot funcionando"):
        st.success("Alerta enviada")
    else:
        st.error("Fallo al enviar. Revisa token/chat_id")

# Mostrar modo
if st.session_state.use_real:
    st.success("✅ Modo REAL (Binance)")
else:
    st.warning("⚠️ Modo SIMULACIÓN")
    if st.button("Reintentar API real"):
        st.session_state.use_real = True
        st.session_state.last_fail = 0
        st.rerun()

# Obtener datos
fng, _ = get_fear_greed()
price_data = {}
for sym, name in CRYPTOS.items():
    price, change, source = get_price(sym)
    st.session_state.last_prices[sym] = price
    price_data[sym] = (price, change, source)
    if price>0:
        st.session_state.price_history[sym].append(price)

st.session_state.cycle_count += 1
# Latido cada 10 ciclos (para confirmar que el bot envía algo)
if st.session_state.cycle_count % 10 == 0:
    send_telegram(f"🟢 [Latido] Ciclo {st.session_state.cycle_count} - Bot activo")

# Procesar cada cripto
for sym, name in CRYPTOS.items():
    price, change, source = price_data[sym]
    if price==0: continue
    hist = st.session_state.price_history[sym]
    score = calculate_score(price, change, fng, hist)

    if alert_on_score_change:
        last_sc = st.session_state.last_score.get(sym, 50)
        if abs(score - last_sc) >= 0.5:
            send_telegram(f"📊 *{name}* Puntaje: {score:.1f} (cambio de {last_sc:.1f})")
            st.session_state.last_score[sym] = score

    # Decidir acción (solo si hay al menos 2 lecturas)
    if len(hist) >= 2:
        if score >= buy_base:
            action = "BUY"
        elif score <= sell_threshold:
            action = "SELL"
        else:
            action = "HOLD"
    else:
        action = "HOLD"

    # Stop loss
    stop_loss_trigger = False
    if use_stop_loss and st.session_state.positions.get(sym, 0) > 0:
        entry = st.session_state.entry_price.get(sym, 0)
        if entry > 0:
            loss_pct = (price - entry)/entry * 100
            if loss_pct <= -stop_loss_pct:
                stop_loss_trigger = True
                action = "SELL"

    last_act = st.session_state.last_action.get(sym)
    if (action != last_act and action in ("BUY","SELL")) or stop_loss_trigger:
        if action == "BUY":
            eff_price = price * (1 + st.session_state.slippage_pct/100)
            if st.session_state.balance >= trade_amount:
                amt_after = trade_amount * (1 - st.session_state.commission_pct/100)
                qty = amt_after / eff_price
                st.session_state.balance -= trade_amount
                st.session_state.positions[sym] += qty
                st.session_state.entry_price[sym] = eff_price
                msg = f"🟢 *{name}* COMPRA\nPrecio visto: ${price:.2f}\nEfectivo: ${eff_price:.2f}\nComisión: ${trade_amount*st.session_state.commission_pct/100:.2f}\nCantidad: {qty:.6f}\nScore: {score:.1f}"
            else:
                msg = f"❌ Saldo insuficiente para comprar {name}"
                send_telegram(msg)
                continue
        else: # VENTA
            eff_price = price * (1 - st.session_state.slippage_pct/100)
            qty = st.session_state.positions.get(sym, 0)
            if qty > 0:
                gross = qty * eff_price
                com = gross * st.session_state.commission_pct/100
                net = gross - com
                st.session_state.balance += net
                st.session_state.positions[sym] = 0
                if stop_loss_trigger:
                    msg = f"🛑 *{name}* STOP LOSS ({stop_loss_pct}%)\nPrecio visto: ${price:.2f}\nEfectivo: ${eff_price:.2f}\nComisión: ${com:.2f}\nNeto: ${net:.2f}\nScore: {score:.1f}"
                else:
                    msg = f"🔴 *{name}* VENTA\nPrecio visto: ${price:.2f}\nEfectivo: ${eff_price:.2f}\nComisión: ${com:.2f}\nNeto: ${net:.2f}\nScore: {score:.1f}"
            else:
                msg = f"❌ No hay posición para vender {name}"
                send_telegram(msg)
                continue
        send_telegram(msg)
        st.session_state.trades.append((datetime.now(), msg))
        st.session_state.last_action[sym] = action

# Mostrar en interfaz
col1, col2 = st.columns(2)
with col1:
    st.subheader("Señales en vivo")
    rows = []
    for sym, name in CRYPTOS.items():
        price, change, source = price_data.get(sym, (0,0,""))
        if price:
            hist = st.session_state.price_history[sym]
            score = calculate_score(price, change, fng, hist)
            if score >= buy_base:
                sig = "COMPRAR"
            elif score <= sell_threshold:
                sig = "VENDER"
            else:
                sig = "MANTENER"
            rows.append({"Moneda": name, "Precio": f"${price:,.2f}", "24h %": f"{change:+.2f}%", "Puntaje": f"{score:.1f}/100", "Señal": sig, "Fuente": source})
        else:
            rows.append({"Moneda": name, "Precio": "Error", "24h %": "N/A", "Puntaje": "N/A", "Señal": "ERROR", "Fuente": "N/A"})
    st.dataframe(pd.DataFrame(rows))
    st.metric("Fear & Greed", f"{fng}/100")
    st.caption(f"Umbral VENTA: {sell_threshold:.1f} | Ciclo: {st.session_state.cycle_count}")
with col2:
    st.subheader("Últimas operaciones")
    if st.session_state.trades:
        for ts, msg in reversed(st.session_state.trades[-10:]):
            st.text(f"{ts.strftime('%H:%M:%S')} - {msg.replace('*','')}")
    else:
        st.caption("Esperando órdenes...")
    st.caption("🔔 El bot envía un 'latido' cada 10 ciclos a Telegram para verificar que está vivo.")

if auto:
    time.sleep(refresh)
    st.rerun()
