import streamlit as st
import pandas as pd
import numpy as np
import time
import requests
from collections import deque
from datetime import datetime
import plotly.express as px
import random
import json
import os

# ==================== CONFIGURACIÓN TELEGRAM ====================
TELEGRAM_TOKEN = "8532857017:AAHwLhRnM3oC6TbgFFKAEmQnZVoo6JD_esQ"
TELEGRAM_CHAT_ID = "5835990242"

def send_telegram(message):
    """Envía mensaje a Telegram. Muestra error en st.error si falla (para logs)"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        response = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}, timeout=5)
        if response.status_code != 200:
            st.error(f"Error Telegram: {response.text}")
    except Exception as e:
        st.error(f"Excepción al enviar a Telegram: {e}")

# ==================== PARÁMETROS POR DEFECTO ====================
DEFAULT_COMMISSION_PCT = 0.1      # 0.1% de comisión por operación
DEFAULT_SLIPPAGE_PCT = 0.05       # 0.05% de deslizamiento
REAL_BASES = {"BTC": 63000, "ETH": 1670}   # precios base para simulación realista
SIM_PRICES = {"BTC": 63000, "ETH": 1670}
SIM_CHANGES = {"BTC": 0.0, "ETH": 0.0}

# ==================== FUNCIONES DE DATOS REALES (BINANCE) ====================
if "use_real" not in st.session_state:
    st.session_state.use_real = True
if "last_fail" not in st.session_state:
    st.session_state.last_fail = 0

def get_binance_price(symbol):
    """Obtiene precio real desde Binance (par USDT)"""
    try:
        pair = f"{symbol}USDT"
        url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={pair}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            price = float(data['lastPrice'])
            change = float(data['priceChangePercent'])
            return price, change
        return None, None
    except Exception as e:
        print(f"Error Binance: {e}")
        return None, None

def get_price(symbol):
    """Devuelve (precio, cambio, fuente). Fuente: 'real' o 'sim'"""
    global SIM_PRICES, SIM_CHANGES
    now = time.time()
    # Si modo real activado y no ha fallado recientemente
    if st.session_state.use_real and (now - st.session_state.last_fail > 300):
        price, change = get_binance_price(symbol)
        if price is not None and price > 0:
            # Validar rangos razonables
            if (symbol == "BTC" and 30000 < price < 100000) or (symbol == "ETH" and 500 < price < 5000):
                return price, change, "real"
        # Si falla o precio fuera de rango, pasar a simulación
        st.session_state.last_fail = now
        st.session_state.use_real = False

    # Modo simulado: precios realistas alrededor de REAL_BASES
    last_price = SIM_PRICES.get(symbol, REAL_BASES[symbol])
    change_pct = random.uniform(-0.015, 0.015)  # -1.5% a +1.5%
    new_price = last_price * (1 + change_pct)
    # Limitar desviación excesiva (máx 10% del base)
    base = REAL_BASES[symbol]
    new_price = max(base * 0.9, min(base * 1.1, new_price))
    sim_change = SIM_CHANGES.get(symbol, 0.0)
    sim_change += random.uniform(-0.3, 0.3)
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
    if len(hist) >= 3:
        trend = np.mean(np.diff(list(hist)[-3:]))
        score += 10 if trend > 0 else -10
    return np.clip(score, 0, 100)

# ==================== INICIALIZAR ESTADO DE SESIÓN ====================
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
    st.session_state.cycle_count = 0   # contador de ciclos para depuración

CRYPTOS = {"BTC": "Bitcoin", "ETH": "Ethereum"}

# ==================== INTERFAZ DE USUARIO ====================
st.set_page_config(page_title="Crypto Auto Trader - Alertas Continuas", layout="wide")
st.title("🤖 Crypto Auto Trader - Alertas cada ciclo (corregido)")

st.sidebar.header("⚙️ Configuración General")
refresh = st.sidebar.slider("Actualizar cada (segundos)", 30, 180, 60)
auto = st.sidebar.checkbox("Auto-refrescar", value=True)

# Umbrales de trading
buy_base = st.sidebar.slider("Umbral COMPRA", 40, 80, 60)
sell_base = st.sidebar.slider("Umbral VENTA base", 30, 70, 55)
sell_sensitivity = st.sidebar.slider("Sensibilidad a la VENTA (0=baja, 100=alta)", 0, 100, 90)
sell_offset = (sell_sensitivity - 50) * 0.3
sell_threshold = max(20, min(70, sell_base + sell_offset))
st.sidebar.markdown(f"**Umbral VENTA efectivo:** {sell_threshold:.1f}")

use_stop_loss = st.sidebar.checkbox("Usar Stop Loss", value=True)
stop_loss_pct = st.sidebar.number_input("Stop Loss (%)", 1.0, 20.0, 5.0, 0.5) if use_stop_loss else 0.0

trade_amount = st.sidebar.number_input("Monto por orden (USDT)", 10.0, 100.0, 20.0)
alert_on_score_change = st.sidebar.checkbox("Enviar alerta cada vez que el puntaje cambie (muchas alertas)", value=True)

st.sidebar.subheader("💰 Costos de Simulación")
commission = st.sidebar.number_input("Comisión (%)", 0.0, 1.0, st.session_state.commission_pct, 0.05)
slippage = st.sidebar.number_input("Slippage (%)", 0.0, 1.0, st.session_state.slippage_pct, 0.05)
st.session_state.commission_pct = commission
st.session_state.slippage_pct = slippage

st.sidebar.subheader("💰 Estado de Cartera Simulada")
st.sidebar.metric("Saldo USDT", f"${st.session_state.balance:,.2f}")
total_value = st.session_state.balance
for sym in CRYPTOS:
    last_p = st.session_state.last_prices.get(sym, 0)
    qty = st.session_state.positions.get(sym, 0)
    if qty > 0 and last_p > 0:
        total_value += qty * last_p
st.sidebar.metric("Valor total", f"${total_value:,.2f}")

if st.sidebar.button("Reiniciar simulación"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

if st.sidebar.button("📢 Enviar alerta de prueba"):
    send_telegram("🧪 Alerta de prueba - Bot activo y enviando mensajes correctamente")
    st.success("Alerta de prueba enviada a Telegram")

# Mostrar modo actual
if st.session_state.use_real:
    st.success("✅ Modo REAL activo (datos de Binance)")
else:
    st.warning("⚠️ Modo SIMULACIÓN activo – Precios realistas pero simulados")
    if st.button("Reintentar conectar a API real"):
        st.session_state.use_real = True
        st.session_state.last_fail = 0
        st.rerun()

# ==================== OBTENER DATOS Y PROCESAR CADA CICLO ====================
fng, fng_label = get_fear_greed()
price_data = {}
for sym, name in CRYPTOS.items():
    price, change, source = get_price(sym)
    st.session_state.last_prices[sym] = price
    price_data[sym] = (price, change, source)
    if price > 0:
        st.session_state.price_history[sym].append(price)

# Incrementar contador de ciclos (para depuración)
st.session_state.cycle_count += 1
# (Opcional) enviar un "latido" cada 10 ciclos para verificar que el bucle funciona
if st.session_state.cycle_count % 10 == 0:
    send_telegram(f"🟢 [Latido] Ciclo {st.session_state.cycle_count} - Bot activo")

# ==================== LÓGICA DE TRADING Y ALERTAS ====================
for sym, name in CRYPTOS.items():
    price, change, source = price_data[sym]
    if price == 0:
        continue
    hist = st.session_state.price_history[sym]
    # Siempre calcular puntaje (aunque hist < 2)
    score = calculate_score(price, change, fng, hist)

    # --- ALERTA POR CAMBIO DE PUNTAJE (si está activada) ---
    if alert_on_score_change:
        last_sc = st.session_state.last_score.get(sym, 50)
        if abs(score - last_sc) >= 0.5:   # cualquier cambio >0.5
            alert_msg = f"📊 *{name}* Puntaje: {score:.1f} (cambio de {last_sc:.1f})"
            send_telegram(alert_msg)
            st.session_state.last_score[sym] = score

    # Determinar acción (si hay suficientes datos para decidir)
    if len(hist) >= 2:
        if score >= buy_base:
            action = "BUY"
        elif score <= sell_threshold:
            action = "SELL"
        else:
            action = "HOLD"
    else:
        action = "HOLD"  # aún no hay datos suficientes

    # Verificar stop loss (solo si hay posición)
    stop_loss_trigger = False
    if use_stop_loss and st.session_state.positions.get(sym, 0) > 0:
        entry = st.session_state.entry_price.get(sym, 0)
        if entry > 0:
            loss_pct = (price - entry) / entry * 100
            if loss_pct <= -stop_loss_pct:
                stop_loss_trigger = True
                action = "SELL"

    # --- EJECUTAR ORDEN SI CAMBIA LA ACCIÓN (o stop loss) ---
    last_act = st.session_state.last_action.get(sym)
    if (action != last_act and action in ("BUY", "SELL")) or stop_loss_trigger:
        if action == "BUY":
            effective_price = price * (1 + st.session_state.slippage_pct / 100)
            if st.session_state.balance >= trade_amount:
                amount_after_commission = trade_amount * (1 - st.session_state.commission_pct / 100)
                qty = amount_after_commission / effective_price
                st.session_state.balance -= trade_amount
                st.session_state.positions[sym] += qty
                st.session_state.entry_price[sym] = effective_price
                msg = (f"🟢 *{name}* COMPRA\n"
                       f"  Precio visto: ${price:.2f}\n"
                       f"  Efectivo: ${effective_price:.2f}\n"
                       f"  Comisión: ${trade_amount * st.session_state.commission_pct/100:.2f}\n"
                       f"  Cantidad: {qty:.6f}\n"
                       f"  Score: {score:.1f}")
            else:
                msg = f"❌ Saldo insuficiente para comprar {name}"
                send_telegram(msg)
                continue
        elif action == "SELL":
            effective_price = price * (1 - st.session_state.slippage_pct / 100)
            qty = st.session_state.positions.get(sym, 0)
            if qty > 0:
                gross_revenue = qty * effective_price
                commission_amount = gross_revenue * st.session_state.commission_pct / 100
                net_revenue = gross_revenue - commission_amount
                st.session_state.balance += net_revenue
                st.session_state.positions[sym] = 0
                if stop_loss_trigger:
                    msg = (f"🛑 *{name}* STOP LOSS ({stop_loss_pct}%)\n"
                           f"  Precio visto: ${price:.2f}\n"
                           f"  Efectivo: ${effective_price:.2f}\n"
                           f"  Comisión: ${commission_amount:.2f}\n"
                           f"  Neto: ${net_revenue:.2f}\n"
                           f"  Score: {score:.1f}")
                else:
                    msg = (f"🔴 *{name}* VENTA\n"
                           f"  Precio visto: ${price:.2f}\n"
                           f"  Efectivo: ${effective_price:.2f}\n"
                           f"  Comisión: ${commission_amount:.2f}\n"
                           f"  Neto: ${net_revenue:.2f}\n"
                           f"  Score: {score:.1f}")
            else:
                msg = f"❌ No hay posición para vender {name}"
                send_telegram(msg)
                continue
        # Enviar mensaje a Telegram
        send_telegram(msg)
        # Registrar operación en el historial de la interfaz
        st.session_state.trades.append((datetime.now(), msg))
        st.session_state.last_action[sym] = action

# ==================== MOSTRAR INTERFAZ PRINCIPAL ====================
col1, col2 = st.columns(2)
with col1:
    st.subheader("📊 Señales en vivo")
    rows = []
    for sym, name in CRYPTOS.items():
        price, change, source = price_data.get(sym, (0,0,""))
        if price == 0:
            rows.append({"Moneda": name, "Precio": "Sin datos", "24h %": "N/A", "Puntaje": "N/A", "Señal": "ERROR", "Fuente": "N/A"})
            continue
        hist = st.session_state.price_history[sym]
        score = calculate_score(price, change, fng, hist)
        if score >= buy_base:
            signal = "COMPRAR"
        elif score <= sell_threshold:
            signal = "VENDER"
        else:
            signal = "MANTENER"
        rows.append({
            "Moneda": name,
            "Precio": f"${price:,.2f}",
            "24h %": f"{change:+.2f}%",
            "Puntaje": f"{score:.1f}/100",
            "Señal": signal,
            "Fuente": "Real" if source=="real" else "Sim"
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
    st.metric("😨 Fear & Greed", f"{fng}/100 ({fng_label})")
    st.caption(f"Umbral VENTA efectivo: {sell_threshold:.1f} | Sensibilidad: {sell_sensitivity}% | Ciclo: {st.session_state.cycle_count}")

with col2:
    st.subheader("📜 Últimas operaciones")
    if st.session_state.trades:
        for ts, msg in reversed(st.session_state.trades[-10:]):
            st.text(f"{ts.strftime('%H:%M:%S')} - {msg.replace('*','')}")
    else:
        st.caption("Aún no hay operaciones. Esperando datos...")
    st.caption("🔔 Las alertas de Telegram se envían en cada ciclo (cambio de puntaje u órdenes).")

# ==================== AUTO REFRESCO ====================
if auto:
    time.sleep(refresh)
    st.rerun()
