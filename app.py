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

# ==================== PARÁMETROS DE ESTRATEGIA Y RIESGO ====================
THRESHOLD = 0.03          # 0.03% de cambio para activar señal de entrada
STOP_LOSS_PCT = 2.0       # Stop loss: vende si pérdida >= 2%
TAKE_PROFIT_PCT = 5.0     # Take profit: vende si ganancia >= 5%
MAX_POSITION_SIZE = 500.0
MAX_DAILY_TRADES = 20
COMMISSION = 0.1          # 0.1% de comisión
SLIPPAGE = 0.05           # 0.05% de deslizamiento
REFRESH_INTERVAL = 10     # segundos entre actualizaciones

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

# ==================== PERSISTENCIA ====================
STATE_FILE = "bot_state.json"

def save_state(state):
    # Convertir objetos no serializables a tipos simples
    to_save = {
        "balance": state["balance"],
        "positions": state["positions"],
        "trades": [(ts.isoformat(), msg) for ts, msg in state["trades"]],
        "last_action": state["last_action"],
        "daily_trades": state["daily_trades"],
        "last_day": state["last_day"],
        "last_price": state["last_price"],
        "ref_price": state["ref_price"],
        "entry_price": state["entry_price"],
        "cycle": state.get("cycle", 0)
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

# ==================== INTERFAZ STREAMLIT ====================
st.set_page_config(page_title="Bot Bitso - SL/TP", layout="wide")
st.title("🇲🇽 Bot de Trading con Stop Loss y Take Profit (Precios reales Bitso)")

st.sidebar.header("Configuración")
umbral = st.sidebar.number_input("Umbral de entrada (%)", 0.01, 1.0, THRESHOLD, 0.01)
stop_loss = st.sidebar.number_input("Stop Loss (%)", 0.5, 10.0, STOP_LOSS_PCT, 0.5)
take_profit = st.sidebar.number_input("Take Profit (%)", 0.5, 20.0, TAKE_PROFIT_PCT, 0.5)

st.sidebar.subheader("Cartera")
saldo_placeholder = st.sidebar.empty()
total_placeholder = st.sidebar.empty()
ops_placeholder = st.sidebar.empty()

if st.sidebar.button("Reiniciar simulación"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
    st.rerun()

if st.sidebar.button("Prueba Telegram"):
    send_telegram("🧪 Bot mejorado con SL/TP - funcionando")
    st.success("Enviado")

# Contenedores para datos dinámicos
tabla_placeholder = st.empty()
info_placeholder = st.empty()
historial_placeholder = st.empty()

# ==================== ESTADO INICIAL ====================
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
        st.session_state.entry_price = saved.get("entry_price", {"BTC": 0.0, "ETH": 0.0})
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
        st.session_state.entry_price = {"BTC": 0.0, "ETH": 0.0}
        st.session_state.cycle = 0

# ==================== BUCLE PRINCIPAL ====================
while st.session_state.running:
    # --- Obtener precios reales de Bitso ---
    btc = get_bitso_price("btc_mxn")
    eth = get_bitso_price("eth_mxn")
    if btc is None or eth is None:
        tabla_placeholder.error("❌ Error al obtener precios de Bitso. Reintentando...")
        time.sleep(REFRESH_INTERVAL)
        continue

    # Actualizar últimos precios
    st.session_state.last_price["BTC"] = btc
    st.session_state.last_price["ETH"] = eth

    # Establecer precios de referencia (primera vez)
    if st.session_state.ref_price["BTC"] == 0:
        st.session_state.ref_price["BTC"] = btc
        st.session_state.ref_price["ETH"] = eth

    st.session_state.cycle += 1

    # Calcular variación desde el precio de referencia
    var_btc = (btc - st.session_state.ref_price["BTC"]) / st.session_state.ref_price["BTC"] * 100
    var_eth = (eth - st.session_state.ref_price["ETH"]) / st.session_state.ref_price["ETH"] * 100

    # --- Mostrar tabla de señales (según variación de referencia) ---
    senal_mostrar_btc = "COMPRAR" if var_btc >= umbral else "VENDER" if var_btc <= -umbral else "MANTENER"
    senal_mostrar_eth = "COMPRAR" if var_eth >= umbral else "VENDER" if var_eth <= -umbral else "MANTENER"

    tabla_placeholder.subheader("📊 Señales en Vivo (precios reales Bitso)")
    tabla_placeholder.table({
        "Moneda": ["Bitcoin", "Ethereum"],
        "Precio MXN": [f"${btc:,.0f}", f"${eth:,.0f}"],
        "Var desde inicio": [f"{var_btc:+.2f}%", f"{var_eth:+.2f}%"],
        "Señal": [senal_mostrar_btc, senal_mostrar_eth]
    })
    info_placeholder.caption(f"Ciclo: {st.session_state.cycle} | Umbral: {umbral}% | SL: {stop_loss}% | TP: {take_profit}% | Fuente: Bitso real")

    # Mostrar cartera en sidebar
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

    # --- Lógica de trading con Stop Loss y Take Profit ---
    hoy = datetime.now().day
    if hoy != st.session_state.last_day:
        st.session_state.daily_trades = 0
        st.session_state.last_day = hoy

    for sym, precio, var in [("BTC", btc, var_btc), ("ETH", eth, var_eth)]:
        pos = st.session_state.positions.get(sym, 0)
        entrada = st.session_state.entry_price.get(sym, 0)
        sl_tp_activado = False
        senal = "HOLD"   # por defecto

        # 1. Verificar Stop Loss y Take Profit (solo si hay posición)
        if pos > 0 and entrada > 0:
            cambio_precio = (precio - entrada) / entrada * 100
            if cambio_precio <= -stop_loss:
                senal = "SELL"
                sl_tp_activado = True
                motivo = f"Stop Loss ({stop_loss}%)"
                st.info(f"🛑 Stop Loss {sym}: pérdida {cambio_precio:.2f}%")
            elif cambio_precio >= take_profit:
                senal = "SELL"
                sl_tp_activado = True
                motivo = f"Take Profit ({take_profit}%)"
                st.info(f"💰 Take Profit {sym}: ganancia {cambio_precio:.2f}%")

        # 2. Si no se activó SL/TP, usar señal de tendencia (comparación con precio de referencia)
        if not sl_tp_activado:
            if var >= umbral:
                senal = "BUY"
            elif var <= -umbral:
                senal = "SELL"
            else:
                senal = "HOLD"

        # 3. Ejecutar orden solo si cambió la acción y no es HOLD
        last = st.session_state.last_action.get(sym)
        if senal != last and senal in ("BUY", "SELL"):
            if senal == "BUY" and pos == 0 and st.session_state.daily_trades < MAX_DAILY_TRADES:
                # --- COMPRA ---
                amount = min(MAX_POSITION_SIZE, st.session_state.balance)
                if amount > 0:
                    eff = precio * (1 + SLIPPAGE/100)
                    com = amount * COMMISSION/100
                    qty = (amount - com) / eff
                    st.session_state.balance -= amount
                    st.session_state.positions[sym] = qty
                    st.session_state.entry_price[sym] = eff   # guardar precio de entrada
                    st.session_state.daily_trades += 1
                    msg = (f"🟢 *COMPRA* {sym}\n"
                           f"Cantidad: {qty:.6f}\n"
                           f"Precio real: ${precio:,.2f}\n"
                           f"Efectivo: ${eff:,.2f}\n"
                           f"Comisión: ${com:.2f}\n"
                           f"Saldo: ${st.session_state.balance:.2f}")
                    send_telegram(msg)
                    st.session_state.trades.append((datetime.now(), msg))
                    save_state(st.session_state.__dict__)
                    st.session_state.last_action[sym] = senal
            elif senal == "SELL" and pos > 0 and st.session_state.daily_trades < MAX_DAILY_TRADES:
                # --- VENTA (por SL, TP o señal de tendencia) ---
                qty = pos
                eff = precio * (1 - SLIPPAGE/100)
                gross = qty * eff
                com = gross * COMMISSION/100
                net = gross - com
                st.session_state.balance += net
                st.session_state.positions[sym] = 0
                st.session_state.daily_trades += 1
                # Determinar motivo para el mensaje
                if sl_tp_activado:
                    if cambio_precio <= -stop_loss:
                        razon = f"Stop Loss ({stop_loss}%)"
                    else:
                        razon = f"Take Profit ({take_profit}%)"
                else:
                    razon = "Señal de tendencia"
                msg = (f"🔴 *VENTA* {sym}\n"
                       f"Cantidad: {qty:.6f}\n"
                       f"Precio real: ${precio:,.2f}\n"
                       f"Efectivo: ${eff:,.2f}\n"
                       f"Comisión: ${com:.2f}\n"
                       f"Neto: ${net:.2f}\n"
                       f"Saldo: ${st.session_state.balance:.2f}\n"
                       f"Motivo: {razon}")
                send_telegram(msg)
                st.session_state.trades.append((datetime.now(), msg))
                save_state(st.session_state.__dict__)
                st.session_state.last_action[sym] = senal

    # Esperar antes del próximo ciclo
    time.sleep(REFRESH_INTERVAL)
