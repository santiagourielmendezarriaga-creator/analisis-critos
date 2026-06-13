import streamlit as st
import requests
import time
import json
import os
from datetime import datetime
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

# ==================== PARÁMETROS (configurables en sidebar) ====================
DEFAULT_THRESHOLD = 0.01        # 0.01% de cambio desde inicio
DEFAULT_STOP_LOSS = 2.0         # Stop loss fijo 2%
DEFAULT_TRAILING = 1.0          # Trailing stop 1%
DEFAULT_RSI_OVERSOLD = 30
DEFAULT_RSI_OVERBOUGHT = 70
DEFAULT_EMA_FAST = 5
DEFAULT_EMA_SLOW = 20
MAX_POSITION_SIZE = 500.0
MAX_DAILY_TRADES = 20
COMMISSION = 0.1
SLIPPAGE = 0.05
REFRESH_INTERVAL = 10

# ==================== BITSO API ====================
def get_bitso_price(book="btc_mxn"):
    try:
        url = f"https://api.bitso.com/api/v3/ticker/?book={book}"
        resp = requests.get(url, timeout=5)
        if resp.status_code != 200:
            return None
        data = resp.json()
        payload = data.get("payload")
        if not payload:
            return None
        last = payload.get("last")
        if last:
            return float(last)
        return None
    except:
        return None

# ==================== INDICADORES ====================
def compute_ema(prices, period):
    if len(prices) < period:
        return None
    k = 2 / (period + 1)
    ema = prices[0]
    for p in prices[1:]:
        ema = p * k + ema * (1 - k)
    return ema

def compute_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def get_enhanced_signal(prices, threshold, rsi_os, rsi_ob, ema_fast, ema_slow):
    """
    Retorna ("BUY"/"SELL"/"HOLD", rsi_value)
    Basado en votación de tres indicadores:
    - Cambio porcentual desde el primer precio de la lista (umbral)
    - Cruce de EMAs (rápida > lenta → BUY, inverso → SELL)
    - RSI (sobreventa → BUY, sobrecompra → SELL)
    """
    if len(prices) < max(ema_slow, 15):
        return "HOLD", 50
    # 1. Cambio porcentual
    ref = prices[0]
    current = prices[-1]
    change_pct = (current - ref) / ref * 100 if ref != 0 else 0
    if change_pct >= threshold:
        signal_change = "BUY"
    elif change_pct <= -threshold:
        signal_change = "SELL"
    else:
        signal_change = "HOLD"

    # 2. EMA cruce
    ema_f = compute_ema(prices, ema_fast)
    ema_s = compute_ema(prices, ema_slow)
    if ema_f is None or ema_s is None:
        signal_ema = "HOLD"
    else:
        signal_ema = "BUY" if ema_f > ema_s else "SELL" if ema_f < ema_s else "HOLD"

    # 3. RSI
    rsi = compute_rsi(prices)
    if rsi <= rsi_os:
        signal_rsi = "BUY"
    elif rsi >= rsi_ob:
        signal_rsi = "SELL"
    else:
        signal_rsi = "HOLD"

    # Votación
    votes = [signal_change, signal_ema, signal_rsi]
    buy_votes = votes.count("BUY")
    sell_votes = votes.count("SELL")
    if buy_votes > sell_votes:
        return "BUY", rsi
    elif sell_votes > buy_votes:
        return "SELL", rsi
    else:
        return "HOLD", rsi

# ==================== PERSISTENCIA ====================
STATE_FILE = "bot_state.json"

def save_state():
    to_save = {
        "balance": st.session_state.balance,
        "positions": st.session_state.positions,
        "trades": [(ts.isoformat(), msg) for ts, msg in st.session_state.trades],
        "last_action": st.session_state.last_action,
        "daily_trades": st.session_state.daily_trades,
        "last_day": st.session_state.last_day,
        "last_price": st.session_state.last_price,
        "ref_price": st.session_state.ref_price,
        "entry_price": st.session_state.entry_price,
        "highest_price": st.session_state.highest_price,
        "cycle": st.session_state.cycle,
        "price_history": {k: list(v) for k, v in st.session_state.price_history.items()}
    }
    with open(STATE_FILE, "w") as f:
        json.dump(to_save, f)

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
            data["trades"] = [(datetime.fromisoformat(ts), msg) for ts, msg in data["trades"]]
            data["price_history"] = {k: deque(v, maxlen=200) for k, v in data.get("price_history", {}).items()}
            # Asegurar claves nuevas
            for key in ["highest_price", "entry_price", "ref_price", "last_price", "last_action"]:
                if key not in data:
                    data[key] = {"BTC": 0.0, "ETH": 0.0} if key != "last_action" else {"BTC": None, "ETH": None}
            if "cycle" not in data:
                data["cycle"] = 0
            return data
        except:
            pass
    return None

# ==================== INTERFAZ ====================
st.set_page_config(page_title="Bot con Señal Mejorada + Trailing Stop", layout="wide")
st.title("📊 Bot de Trading con RSI, EMA y Trailing Stop (Bitso real)")

st.sidebar.header("⚙️ Configuración de Estrategia")
umbral = st.sidebar.number_input("Umbral cambio % (desde inicio)", 0.005, 1.0, DEFAULT_THRESHOLD, 0.005)
rsi_os = st.sidebar.number_input("RSI sobreventa (compra)", 20, 40, DEFAULT_RSI_OVERSOLD)
rsi_ob = st.sidebar.number_input("RSI sobrecompra (venta)", 60, 80, DEFAULT_RSI_OVERBOUGHT)
ema_fast = st.sidebar.number_input("EMA rápida (periodos)", 3, 20, DEFAULT_EMA_FAST)
ema_slow = st.sidebar.number_input("EMA lenta (periodos)", 10, 50, DEFAULT_EMA_SLOW)

st.sidebar.header("🛡️ Gestión de Riesgo")
stop_loss = st.sidebar.number_input("Stop Loss fijo (%)", 0.5, 10.0, DEFAULT_STOP_LOSS, 0.5)
trailing = st.sidebar.number_input("Trailing Stop (%)", 0.2, 5.0, DEFAULT_TRAILING, 0.1)

st.sidebar.subheader("💰 Cartera")
saldo_placeholder = st.sidebar.empty()
total_placeholder = st.sidebar.empty()
ops_placeholder = st.sidebar.empty()

if st.sidebar.button("Reiniciar simulación"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
    st.rerun()

if st.sidebar.button("📢 Prueba Telegram"):
    send_telegram("🧪 Bot mejorado RSI+EMA+Trailing - activo")
    st.success("Enviado")

tabla_placeholder = st.empty()
info_placeholder = st.empty()
historial_placeholder = st.empty()

# ==================== INICIALIZAR ESTADO ====================
if "running" not in st.session_state:
    st.session_state.running = True
    saved = load_state()
    if saved:
        st.session_state.balance = saved["balance"]
        st.session_state.positions = saved["positions"]
        st.session_state.trades = saved["trades"]
        st.session_state.last_action = saved["last_action"]
        st.session_state.daily_trades = saved["daily_trades"]
        st.session_state.last_day = saved["last_day"]
        st.session_state.last_price = saved["last_price"]
        st.session_state.ref_price = saved["ref_price"]
        st.session_state.entry_price = saved["entry_price"]
        st.session_state.highest_price = saved["highest_price"]
        st.session_state.cycle = saved["cycle"]
        st.session_state.price_history = saved.get("price_history", {})
        for sym in ["BTC", "ETH"]:
            if sym not in st.session_state.price_history:
                st.session_state.price_history[sym] = deque(maxlen=200)
    else:
        st.session_state.balance = 1000.0
        st.session_state.positions = {"BTC": 0.0, "ETH": 0.0}
        st.session_state.trades = []
        st.session_state.last_action = {"BTC": None, "ETH": None}
        st.session_state.daily_trades = 0
        st.session_state.last_day = datetime.now().day
        st.session_state.last_price = {"BTC": 0.0, "ETH": 0.0}
        st.session_state.ref_price = {"BTC": 0.0, "ETH": 0.0}
        st.session_state.entry_price = {"BTC": 0.0, "ETH": 0.0}
        st.session_state.highest_price = {"BTC": 0.0, "ETH": 0.0}
        st.session_state.cycle = 0
        st.session_state.price_history = {"BTC": deque(maxlen=200), "ETH": deque(maxlen=200)}

# ==================== BUCLE PRINCIPAL ====================
while st.session_state.running:
    btc = get_bitso_price("btc_mxn")
    eth = get_bitso_price("eth_mxn")
    if btc is None or eth is None:
        tabla_placeholder.error("❌ Error al obtener precios de Bitso. Reintentando...")
        time.sleep(REFRESH_INTERVAL)
        continue

    st.session_state.last_price["BTC"] = btc
    st.session_state.last_price["ETH"] = eth

    # Actualizar historial de precios
    st.session_state.price_history["BTC"].append(btc)
    st.session_state.price_history["ETH"].append(eth)

    # Precios de referencia (para la señal de cambio)
    if st.session_state.ref_price["BTC"] == 0:
        st.session_state.ref_price["BTC"] = btc
        st.session_state.ref_price["ETH"] = eth

    st.session_state.cycle += 1

    # Mostrar tabla con señales (solo informativa, basada en cambio)
    var_btc = (btc - st.session_state.ref_price["BTC"]) / st.session_state.ref_price["BTC"] * 100
    var_eth = (eth - st.session_state.ref_price["ETH"]) / st.session_state.ref_price["ETH"] * 100
    tabla_placeholder.subheader("📊 Señales en Vivo (Bitso real)")
    tabla_placeholder.table({
        "Moneda": ["Bitcoin", "Ethereum"],
        "Precio MXN": [f"${btc:,.0f}", f"${eth:,.0f}"],
        "Var desde inicio": [f"{var_btc:+.2f}%", f"{var_eth:+.2f}%"],
        "Señal (solo info)": ["COMPRAR" if var_btc >= umbral else "VENDER" if var_btc <= -umbral else "MANTENER",
                              "COMPRAR" if var_eth >= umbral else "VENDER" if var_eth <= -umbral else "MANTENER"]
    })
    info_placeholder.caption(f"Ciclo: {st.session_state.cycle} | Umbral: {umbral}% | SL: {stop_loss}% | Trailing: {trailing}% | RSI: {rsi_os}/{rsi_ob} | EMA({ema_fast},{ema_slow})")

    # Actualizar sidebar
    total_val = st.session_state.balance
    for s in ["BTC", "ETH"]:
        p = st.session_state.last_price.get(s, 0)
        q = st.session_state.positions.get(s, 0)
        if q > 0 and p > 0:
            total_val += q * p
    saldo_placeholder.metric("Saldo MXN", f"${st.session_state.balance:,.2f}")
    total_placeholder.metric("Valor total", f"${total_val:,.2f}")
    ops_placeholder.metric("Ops hoy", st.session_state.daily_trades)

    historial_placeholder.subheader("📜 Historial")
    if st.session_state.trades:
        txt = ""
        for ts, msg in reversed(st.session_state.trades[-10:]):
            txt += f"{ts.strftime('%H:%M:%S')} - {msg[:60]}\n"
        historial_placeholder.text(txt)
    else:
        historial_placeholder.text("Sin operaciones aún.")

    # ==================== LÓGICA DE TRADING CON SEÑAL MEJORADA ====================
    hoy = datetime.now().day
    if hoy != st.session_state.last_day:
        st.session_state.daily_trades = 0
        st.session_state.last_day = hoy

    for sym, precio in [("BTC", btc), ("ETH", eth)]:
        hist = list(st.session_state.price_history[sym])
        # Señal mejorada (votación)
        if len(hist) >= max(ema_slow, 15):
            senal, rsi_val = get_enhanced_signal(hist, umbral, rsi_os, rsi_ob, ema_fast, ema_slow)
        else:
            senal = "HOLD"
            rsi_val = 50

        pos = st.session_state.positions.get(sym, 0)
        entrada = st.session_state.entry_price.get(sym, 0)
        highest = st.session_state.highest_price.get(sym, precio)
        razon = ""
        accion = None

        # Actualizar máximo para trailing stop
        if precio > highest:
            st.session_state.highest_price[sym] = precio
            highest = precio

        # --- Condiciones de salida (prioritarias sobre la señal) ---
        if pos > 0 and entrada > 0:
            # Stop loss fijo
            perdida = (precio - entrada) / entrada * 100
            if perdida <= -stop_loss:
                accion = "SELL"
                razon = f"Stop Loss fijo ({stop_loss}%)"
            # Trailing stop
            elif highest > entrada:
                caida = (precio - highest) / highest * 100
                if caida <= -trailing:
                    accion = "SELL"
                    razon = f"Trailing Stop ({trailing}%) desde máximo ${highest:,.2f}"

        # Si no se activó salida, usar la señal mejorada
        if accion is None:
            if senal == "BUY" and pos == 0:
                accion = "BUY"
            elif senal == "SELL" and pos > 0:
                accion = "SELL"
                razon = "Señal de venta (RSI/EMA/cambio)"

        # Ejecutar orden si cambia la acción y hay límites
        last_act = st.session_state.last_action.get(sym)
        if accion and accion != last_act and st.session_state.daily_trades < MAX_DAILY_TRADES:
            if accion == "BUY":
                amount = min(MAX_POSITION_SIZE, st.session_state.balance)
                if amount > 0:
                    eff = precio * (1 + SLIPPAGE/100)
                    com = amount * COMMISSION/100
                    qty = (amount - com) / eff
                    st.session_state.balance -= amount
                    st.session_state.positions[sym] = qty
                    st.session_state.entry_price[sym] = eff
                    st.session_state.highest_price[sym] = eff
                    st.session_state.daily_trades += 1
                    msg = (f"🟢 *COMPRA* {sym}\n"
                           f"Cantidad: {qty:.6f}\n"
                           f"Precio: ${precio:,.2f}\n"
                           f"Efectivo: ${eff:,.2f}\n"
                           f"Comisión: ${com:.2f}\n"
                           f"Saldo: ${st.session_state.balance:.2f}\n"
                           f"RSI: {rsi_val:.1f}")
                    send_telegram(msg)
                    st.session_state.trades.append((datetime.now(), msg))
                    save_state()
                    st.session_state.last_action[sym] = accion
            elif accion == "SELL" and pos > 0:
                qty = pos
                eff = precio * (1 - SLIPPAGE/100)
                gross = qty * eff
                com = gross * COMMISSION/100
                net = gross - com
                st.session_state.balance += net
                st.session_state.positions[sym] = 0
                st.session_state.daily_trades += 1
                msg = (f"🔴 *VENTA* {sym}\n"
                       f"Cantidad: {qty:.6f}\n"
                       f"Precio: ${precio:,.2f}\n"
                       f"Efectivo: ${eff:,.2f}\n"
                       f"Comisión: ${com:.2f}\n"
                       f"Neto: ${net:.2f}\n"
                       f"Saldo: ${st.session_state.balance:.2f}\n"
                       f"Motivo: {razon}\n"
                       f"RSI: {rsi_val:.1f}")
                send_telegram(msg)
                st.session_state.trades.append((datetime.now(), msg))
                save_state()
                st.session_state.last_action[sym] = accion

    time.sleep(REFRESH_INTERVAL)
