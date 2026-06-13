import streamlit as st
import requests
import time
import json
import os
from datetime import datetime

# ==================== TELEGRAM ====================
TELEGRAM_TOKEN = "8532857017:AAHwLhRnM3oC6TbgFFKAEmQnZVoo6JD_esQ"
TELEGRAM_CHAT_ID = "5835990242"

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=3)
    except:
        pass

# ==================== PARÁMETROS ====================
THRESHOLD = 0.05          # 0.05% de cambio
REFRESH_INTERVAL = 10     # segundos
MAX_POSITION_SIZE = 500.0
MAX_DAILY_TRADES = 20
COMMISSION = 0.1
SLIPPAGE = 0.05

# ==================== BITSO API (PRECIOS REALES) ====================
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

# ==================== PERSISTENCIA ====================
STATE_FILE = "bot_state.json"

def save_state(state):
    to_save = {
        "balance": state["balance"],
        "positions": state["positions"],
        "trades": [(ts.isoformat(), msg) for ts, msg in state["trades"]],
        "last_action": state["last_action"],
        "daily_trades": state["daily_trades"],
        "last_day": state["last_day"],
        "last_price": state["last_price"],
        "ref_price": state["ref_price"]
    }
    with open(STATE_FILE, "w") as f:
        json.dump(to_save, f)

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
            data["trades"] = [(datetime.fromisoformat(ts), msg) for ts, msg in data["trades"]]
            return data
        except:
            pass
    return None

# ==================== INTERFAZ (se ejecuta una vez) ====================
st.set_page_config(page_title="Bot Bitso Real - Auto Actualización", layout="wide")

# Título y sidebar (se renderizan una sola vez, luego se actualiza el contenido)
st.title("🇲🇽 Bot con Precios Reales de Bitso (MXN) - Actualización automática cada 10s")
st.sidebar.header("Configuración")
umbral = st.sidebar.number_input("Umbral de cambio %", 0.01, 1.0, THRESHOLD, 0.01)

st.sidebar.subheader("Cartera")
saldo_placeholder = st.sidebar.empty()
total_placeholder = st.sidebar.empty()
ops_placeholder = st.sidebar.empty()

if st.sidebar.button("Reiniciar"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
    st.rerun()

if st.sidebar.button("Prueba Telegram"):
    send_telegram("🧪 Bot con precios reales - actualización automática")
    st.success("Enviado")

# Contenedores para datos dinámicos
tabla_placeholder = st.empty()
info_placeholder = st.empty()
historial_placeholder = st.empty()

# ==================== ESTADO DE SESIÓN (persistente entre ciclos) ====================
if "running" not in st.session_state:
    st.session_state.running = True
    # Cargar estado guardado
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
        st.session_state.cycle = saved.get("cycle", 0)
    else:
        st.session_state.balance = 1000.0
        st.session_state.positions = {"BTC": 0.0, "ETH": 0.0}
        st.session_state.trades = []
        st.session_state.last_action = {"BTC": None, "ETH": None}
        st.session_state.daily_trades = 0
        st.session_state.last_day = datetime.now().day
        st.session_state.last_price = {"BTC": 0.0, "ETH": 0.0}
        st.session_state.ref_price = {"BTC": 0.0, "ETH": 0.0}
        st.session_state.cycle = 0

# ==================== BUCLE INFINITO DE ACTUALIZACIÓN ====================
while st.session_state.running:
    # Obtener precios actuales
    btc = get_bitso_price("btc_mxn")
    eth = get_bitso_price("eth_mxn")
    if btc is None or eth is None:
        tabla_placeholder.error("❌ No se pudieron obtener precios de Bitso. Reintentando en 10 segundos...")
        time.sleep(REFRESH_INTERVAL)
        continue

    # Actualizar precios en estado
    st.session_state.last_price["BTC"] = btc
    st.session_state.last_price["ETH"] = eth

    # Establecer precios de referencia si es primera vez
    if st.session_state.ref_price["BTC"] == 0:
        st.session_state.ref_price["BTC"] = btc
        st.session_state.ref_price["ETH"] = eth

    st.session_state.cycle += 1

    # Calcular variación
    var_btc = (btc - st.session_state.ref_price["BTC"]) / st.session_state.ref_price["BTC"] * 100
    var_eth = (eth - st.session_state.ref_price["ETH"]) / st.session_state.ref_price["ETH"] * 100

    # Determinar señales
    senal_btc = "COMPRAR" if var_btc >= umbral else "VENDER" if var_btc <= -umbral else "MANTENER"
    senal_eth = "COMPRAR" if var_eth >= umbral else "VENDER" if var_eth <= -umbral else "MANTENER"

    # Mostrar tabla actualizada
    tabla_placeholder.subheader("📊 Señales en Vivo (precios reales Bitso)")
    tabla_placeholder.table({
        "Moneda": ["Bitcoin", "Ethereum"],
        "Precio MXN": [f"${btc:,.0f}", f"${eth:,.0f}"],
        "Var desde inicio": [f"{var_btc:+.2f}%", f"{var_eth:+.2f}%"],
        "Señal": [senal_btc, senal_eth]
    })
    info_placeholder.caption(f"Ciclo: {st.session_state.cycle} | Umbral: {umbral}% | Fuente: Bitso real | Refresco cada {REFRESH_INTERVAL}s")

    # Actualizar sidebar con saldo y valor total
    total_val = st.session_state.balance
    for s in ["BTC", "ETH"]:
        p = st.session_state.last_price.get(s, 0)
        q = st.session_state.positions.get(s, 0)
        if q > 0 and p > 0:
            total_val += q * p
    saldo_placeholder.metric("Saldo MXN", f"${st.session_state.balance:,.2f}")
    total_placeholder.metric("Valor total", f"${total_val:,.2f}")
    ops_placeholder.metric("Ops hoy", st.session_state.daily_trades)

    # Mostrar historial
    historial_placeholder.subheader("📜 Historial de Operaciones")
    if st.session_state.trades:
        historial_text = ""
        for ts, msg in reversed(st.session_state.trades[-10:]):
            historial_text += f"{ts.strftime('%H:%M:%S')} - {msg[:60]}\n"
        historial_placeholder.text(historial_text)
    else:
        historial_placeholder.text("Aún no hay operaciones.")

    # Lógica de trading (igual que antes)
    hoy = datetime.now().day
    if hoy != st.session_state.last_day:
        st.session_state.daily_trades = 0
        st.session_state.last_day = hoy

    for sym, precio, var in [("BTC", btc, var_btc), ("ETH", eth, var_eth)]:
        if var >= umbral:
            senal = "BUY"
        elif var <= -umbral:
            senal = "SELL"
        else:
            senal = "HOLD"

        action = None
        if senal == "BUY" and st.session_state.positions.get(sym, 0) == 0 and st.session_state.daily_trades < MAX_DAILY_TRADES:
            action = "BUY"
        elif senal == "SELL" and st.session_state.positions.get(sym, 0) > 0 and st.session_state.daily_trades < MAX_DAILY_TRADES:
            action = "SELL"

        if action == "BUY":
            amount = min(MAX_POSITION_SIZE, st.session_state.balance)
            if amount > 0:
                eff = precio * (1 + SLIPPAGE/100)
                com = amount * COMMISSION/100
                qty = (amount - com) / eff
                st.session_state.balance -= amount
                st.session_state.positions[sym] = st.session_state.positions.get(sym, 0) + qty
                st.session_state.daily_trades += 1
                msg = f"🟢 *COMPRA* {sym}\nCantidad: {qty:.6f}\nPrecio real: ${precio:,.2f}\nEfectivo: ${eff:,.2f}\nComisión: ${com:.2f}\nSaldo: ${st.session_state.balance:.2f}"
                send_telegram(msg)
                st.session_state.trades.append((datetime.now(), msg))
                save_state({
                    "balance": st.session_state.balance,
                    "positions": st.session_state.positions,
                    "trades": st.session_state.trades,
                    "last_action": st.session_state.last_action,
                    "daily_trades": st.session_state.daily_trades,
                    "last_day": st.session_state.last_day,
                    "last_price": st.session_state.last_price,
                    "ref_price": st.session_state.ref_price
                })
        elif action == "SELL":
            qty = st.session_state.positions.get(sym, 0)
            if qty > 0:
                eff = precio * (1 - SLIPPAGE/100)
                gross = qty * eff
                com = gross * COMMISSION/100
                net = gross - com
                st.session_state.balance += net
                st.session_state.positions[sym] = 0
                st.session_state.daily_trades += 1
                msg = f"🔴 *VENTA* {sym}\nCantidad: {qty:.6f}\nPrecio real: ${precio:,.2f}\nEfectivo: ${eff:,.2f}\nComisión: ${com:.2f}\nNeto: ${net:.2f}\nSaldo: ${st.session_state.balance:.2f}"
                send_telegram(msg)
                st.session_state.trades.append((datetime.now(), msg))
                save_state({
                    "balance": st.session_state.balance,
                    "positions": st.session_state.positions,
                    "trades": st.session_state.trades,
                    "last_action": st.session_state.last_action,
                    "daily_trades": st.session_state.daily_trades,
                    "last_day": st.session_state.last_day,
                    "last_price": st.session_state.last_price,
                    "ref_price": st.session_state.ref_price
                })

    # Esperar antes de la siguiente iteración
    time.sleep(REFRESH_INTERVAL)
