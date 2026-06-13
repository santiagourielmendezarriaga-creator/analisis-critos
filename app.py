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

# ==================== PARÁMETROS (configurables en sidebar) ====================
THRESHOLD = 0.01          # 0.01% de cambio desde inicio para comprar
STOP_LOSS_PCT = 2.0       # Stop loss fijo 2% (respaldo)
TRAILING_STOP_PCT = 1.0   # Trailing stop: vende si cae 1% desde máximo
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
        "highest_price": st.session_state.highest_price,   # nuevo para trailing stop
        "cycle": st.session_state.cycle
    }
    with open(STATE_FILE, "w") as f:
        json.dump(to_save, f)

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
            data["trades"] = [(datetime.fromisoformat(ts), msg) for ts, msg in data["trades"]]
            # Asegurar claves nuevas
            if "highest_price" not in data:
                data["highest_price"] = {"BTC": 0.0, "ETH": 0.0}
            if "entry_price" not in data:
                data["entry_price"] = {"BTC": 0.0, "ETH": 0.0}
            return data
        except:
            pass
    return None

# ==================== INTERFAZ ====================
st.set_page_config(page_title="Bot Trailing Stop", layout="wide")
st.title("📈 Bot con Trailing Stop (Bitso real)")

st.sidebar.header("⚙️ Configuración")
umbral = st.sidebar.number_input("Umbral de entrada (%)", 0.005, 1.0, THRESHOLD, 0.005)
stop_loss = st.sidebar.number_input("Stop Loss fijo (%)", 0.5, 10.0, STOP_LOSS_PCT, 0.5)
trailing = st.sidebar.number_input("Trailing Stop (%)", 0.2, 5.0, TRAILING_STOP_PCT, 0.1)

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
    send_telegram("🧪 Bot Trailing Stop - activo")
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
    info_placeholder.caption(f"Ciclo: {st.session_state.cycle} | Umbral: {umbral}% | SL fijo: {stop_loss}% | Trailing: {trailing}%")

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

    # ==================== LÓGICA DE TRADING CON TRAILING STOP ====================
    hoy = datetime.now().day
    if hoy != st.session_state.last_day:
        st.session_state.daily_trades = 0
        st.session_state.last_day = hoy

    for sym, precio, var in [("BTC", btc, var_btc), ("ETH", eth, var_eth)]:
        pos = st.session_state.positions.get(sym, 0)
        entrada = st.session_state.entry_price.get(sym, 0)
        highest = st.session_state.highest_price.get(sym, precio)
        senal = "HOLD"
        razon = ""

        # Actualizar precio máximo si es mayor
        if precio > highest:
            st.session_state.highest_price[sym] = precio
            highest = precio

        # --- Condiciones de venta (prioridad) ---
        if pos > 0 and entrada > 0:
            # 1. Stop Loss fijo (pérdida desde entrada)
            perdida = (precio - entrada) / entrada * 100
            if perdida <= -stop_loss:
                senal = "SELL"
                razon = f"Stop Loss fijo ({stop_loss}%)"
            # 2. Trailing Stop (caída desde el máximo)
            elif highest > entrada:
                caida_desde_max = (precio - highest) / highest * 100
                if caida_desde_max <= -trailing:
                    senal = "SELL"
                    razon = f"Trailing Stop ({trailing}%) desde máximo ${highest:,.2f}"

        # Si no se activó venta, usar señal de entrada
        if senal != "SELL":
            if var >= umbral:
                senal = "BUY"
            elif var <= -umbral:
                senal = "SELL"   # venta por señal bajista
                razon = "Señal de tendencia baja"
            else:
                senal = "HOLD"

        # Ejecutar orden si cambia la acción y es válida
        last_act = st.session_state.last_action.get(sym)
        if senal != last_act and senal in ("BUY", "SELL"):
            if senal == "BUY" and pos == 0 and st.session_state.daily_trades < MAX_DAILY_TRADES:
                # COMPRA
                amount = min(MAX_POSITION_SIZE, st.session_state.balance)
                if amount > 0:
                    eff = precio * (1 + SLIPPAGE/100)
                    com = amount * COMMISSION/100
                    qty = (amount - com) / eff
                    st.session_state.balance -= amount
                    st.session_state.positions[sym] = qty
                    st.session_state.entry_price[sym] = eff
                    st.session_state.highest_price[sym] = eff   # inicializar máximo
                    st.session_state.daily_trades += 1
                    msg = (f"🟢 *COMPRA* {sym}\n"
                           f"Cantidad: {qty:.6f}\n"
                           f"Precio: ${precio:,.2f}\n"
                           f"Efectivo: ${eff:,.2f}\n"
                           f"Comisión: ${com:.2f}\n"
                           f"Saldo: ${st.session_state.balance:.2f}")
                    send_telegram(msg)
                    st.session_state.trades.append((datetime.now(), msg))
                    save_state()
                    st.session_state.last_action[sym] = senal
            elif senal == "SELL" and pos > 0 and st.session_state.daily_trades < MAX_DAILY_TRADES:
                # VENTA (por trailing, stop loss o señal)
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
                       f"Motivo: {razon}")
                send_telegram(msg)
                st.session_state.trades.append((datetime.now(), msg))
                save_state()
                st.session_state.last_action[sym] = senal

    time.sleep(REFRESH_INTERVAL)
