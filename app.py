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
THRESHOLD = 0.03
STOP_LOSS_PCT = 2.0
TAKE_PROFIT_PCT = 5.0
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

# ==================== PERSISTENCIA (CON VERIFICACIÓN DE CLAVES) ====================
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
        "cycle": st.session_state.cycle
    }
    with open(STATE_FILE, "w") as f:
        json.dump(to_save, f)

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
            # Restaurar trades (datetime)
            data["trades"] = [(datetime.fromisoformat(ts), msg) for ts, msg in data["trades"]]
            # Asegurar claves faltantes (para compatibilidad)
            if "entry_price" not in data:
                data["entry_price"] = {"BTC": 0.0, "ETH": 0.0}
            if "ref_price" not in data:
                data["ref_price"] = {"BTC": 0.0, "ETH": 0.0}
            if "last_price" not in data:
                data["last_price"] = {"BTC": 0.0, "ETH": 0.0}
            if "last_action" not in data:
                data["last_action"] = {"BTC": None, "ETH": None}
            if "cycle" not in data:
                data["cycle"] = 0
            return data
        except:
            pass
    return None

# ==================== INTERFAZ ====================
st.set_page_config(page_title="Bot Bitso SL/TP", layout="wide")
st.title("🤖 Bot con Stop Loss y Take Profit (Bitso real)")

st.sidebar.header("⚙️ Configuración")
umbral = st.sidebar.number_input("Umbral de entrada (%)", 0.01, 1.0, THRESHOLD, 0.01)
stop_loss = st.sidebar.number_input("Stop Loss (%)", 0.5, 10.0, STOP_LOSS_PCT, 0.5)
take_profit = st.sidebar.number_input("Take Profit (%)", 0.5, 20.0, TAKE_PROFIT_PCT, 0.5)

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
    send_telegram("🧪 Bot SL/TP - funcionando")
    st.success("Enviado")

# Contenedores
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
        st.session_state.cycle = saved["cycle"]
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
    btc = get_bitso_price("btc_mxn")
    eth = get_bitso_price("eth_mxn")
    if btc is None or eth is None:
        tabla_placeholder.error("❌ Error al obtener precios de Bitso. Reintentando...")
        time.sleep(REFRESH_INTERVAL)
        continue

    st.session_state.last_price["BTC"] = btc
    st.session_state.last_price["ETH"] = eth

    if st.session_state.ref_price["BTC"] == 0:
        st.session_state.ref_price["BTC"] = btc
        st.session_state.ref_price["ETH"] = eth

    st.session_state.cycle += 1

    var_btc = (btc - st.session_state.ref_price["BTC"]) / st.session_state.ref_price["BTC"] * 100
    var_eth = (eth - st.session_state.ref_price["ETH"]) / st.session_state.ref_price["ETH"] * 100

    tabla_placeholder.subheader("📊 Señales en Vivo")
    tabla_placeholder.table({
        "Moneda": ["Bitcoin", "Ethereum"],
        "Precio MXN": [f"${btc:,.0f}", f"${eth:,.0f}"],
        "Var desde inicio": [f"{var_btc:+.2f}%", f"{var_eth:+.2f}%"],
        "Señal": ["COMPRAR" if var_btc >= umbral else "VENDER" if var_btc <= -umbral else "MANTENER",
                   "COMPRAR" if var_eth >= umbral else "VENDER" if var_eth <= -umbral else "MANTENER"]
    })
    info_placeholder.caption(f"Ciclo: {st.session_state.cycle} | Umbral: {umbral}% | SL: {stop_loss}% | TP: {take_profit}%")

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

    # ==================== LÓGICA DE TRADING ====================
    hoy = datetime.now().day
    if hoy != st.session_state.last_day:
        st.session_state.daily_trades = 0
        st.session_state.last_day = hoy

    for sym, precio, var in [("BTC", btc, var_btc), ("ETH", eth, var_eth)]:
        pos = st.session_state.positions.get(sym, 0)
        entrada = st.session_state.entry_price.get(sym, 0)
        sl_tp_activado = False
        senal = "HOLD"

        if pos > 0 and entrada > 0:
            cambio_precio = (precio - entrada) / entrada * 100
            if cambio_precio <= -stop_loss:
                senal = "SELL"
                sl_tp_activado = True
                motivo = f"Stop Loss ({stop_loss}%)"
            elif cambio_precio >= take_profit:
                senal = "SELL"
                sl_tp_activado = True
                motivo = f"Take Profit ({take_profit}%)"

        if not sl_tp_activado:
            if var >= umbral:
                senal = "BUY"
            elif var <= -umbral:
                senal = "SELL"
            else:
                senal = "HOLD"

        last_act = st.session_state.last_action.get(sym)
        if senal != last_act and senal in ("BUY", "SELL"):
            if senal == "BUY" and pos == 0 and st.session_state.daily_trades < MAX_DAILY_TRADES:
                amount = min(MAX_POSITION_SIZE, st.session_state.balance)
                if amount > 0:
                    eff = precio * (1 + SLIPPAGE/100)
                    com = amount * COMMISSION/100
                    qty = (amount - com) / eff
                    st.session_state.balance -= amount
                    st.session_state.positions[sym] = qty
                    st.session_state.entry_price[sym] = eff
                    st.session_state.daily_trades += 1
                    msg = (f"🟢 *COMPRA* {sym}\nCantidad: {qty:.6f}\nPrecio: ${precio:,.2f}\nEfectivo: ${eff:,.2f}\nComisión: ${com:.2f}\nSaldo: ${st.session_state.balance:.2f}")
                    send_telegram(msg)
                    st.session_state.trades.append((datetime.now(), msg))
                    save_state()
                    st.session_state.last_action[sym] = senal
            elif senal == "SELL" and pos > 0 and st.session_state.daily_trades < MAX_DAILY_TRADES:
                qty = pos
                eff = precio * (1 - SLIPPAGE/100)
                gross = qty * eff
                com = gross * COMMISSION/100
                net = gross - com
                st.session_state.balance += net
                st.session_state.positions[sym] = 0
                st.session_state.daily_trades += 1
                razon = motivo if sl_tp_activado else "Señal de tendencia"
                msg = (f"🔴 *VENTA* {sym}\nCantidad: {qty:.6f}\nPrecio: ${precio:,.2f}\nEfectivo: ${eff:,.2f}\nComisión: ${com:.2f}\nNeto: ${net:.2f}\nSaldo: ${st.session_state.balance:.2f}\nMotivo: {razon}")
                send_telegram(msg)
                st.session_state.trades.append((datetime.now(), msg))
                save_state()
                st.session_state.last_action[sym] = senal

    time.sleep(REFRESH_INTERVAL)
