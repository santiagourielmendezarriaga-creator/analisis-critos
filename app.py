import streamlit as st
import requests
import time
import json
import os
from datetime import datetime
from collections import deque
from supabase import create_client, Client

# ==================== SUPABASE ====================
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user_id = None
    st.session_state.user_data = None

# ==================== AUTENTICACIÓN ====================
def sign_up(email, password):
    try:
        resp = supabase.auth.sign_up({"email": email, "password": password})
        if resp.user:
            supabase.table("user_data").insert({"user_id": resp.user.id}).execute()
            return True, "Registro exitoso. Revisa tu correo para confirmar."
        return False, "Error en el registro."
    except Exception as e:
        return False, str(e)

def sign_in(email, password):
    try:
        resp = supabase.auth.sign_in_with_password({"email": email, "password": password})
        if resp.user:
            st.session_state.authenticated = True
            st.session_state.user_id = resp.user.id
            load_user_data()
            return True, "Bienvenido"
        return False, "Correo o contraseña incorrectos"
    except Exception as e:
        return False, str(e)

def sign_out():
    supabase.auth.sign_out()
    st.session_state.authenticated = False
    st.session_state.user_id = None
    st.session_state.user_data = None
    st.rerun()

def load_user_data():
    resp = supabase.table("user_data").select("*").eq("user_id", st.session_state.user_id).execute()
    if resp.data:
        st.session_state.user_data = resp.data[0]
    else:
        supabase.table("user_data").insert({"user_id": st.session_state.user_id}).execute()
        resp = supabase.table("user_data").select("*").eq("user_id", st.session_state.user_id).execute()
        st.session_state.user_data = resp.data[0]

def save_user_data():
    if not st.session_state.user_id:
        return
    data = {
        "balance": st.session_state.balance,
        "positions": st.session_state.positions,
        "trades": [(t.isoformat(), msg) for t, msg in st.session_state.trades[-100:]],
        "price_history": {k: list(v) for k, v in st.session_state.price_history.items()},
        "last_action": st.session_state.last_action,
        "daily_trades": st.session_state.daily_trades,
        "last_day": st.session_state.last_day,
        "ref_price": st.session_state.ref_price,
        "last_price": st.session_state.last_price,
        "entry_price": st.session_state.entry_price,
        "highest_price": st.session_state.highest_price,
        "cycle": st.session_state.cycle,
        "umbral": st.session_state.umbral,
        "rsi_os": st.session_state.rsi_os,
        "rsi_ob": st.session_state.rsi_ob,
        "ema_fast": st.session_state.ema_fast,
        "ema_slow": st.session_state.ema_slow,
        "stop_loss": st.session_state.stop_loss,
        "take_profit": st.session_state.take_profit,
        "trailing": st.session_state.trailing,
        "expert_score": st.session_state.expert_score,
        "expert_comment": st.session_state.expert_comment
    }
    supabase.table("user_data").update(data).eq("user_id", st.session_state.user_id).execute()

def restore_user_state():
    data = st.session_state.user_data
    trades = []
    for ts, msg in data.get("trades", []):
        trades.append((datetime.fromisoformat(ts), msg))
    st.session_state.balance = data.get("balance", 1000.0)
    st.session_state.positions = data.get("positions", {"BTC": 0.0, "ETH": 0.0})
    st.session_state.trades = trades
    st.session_state.last_action = data.get("last_action", {"BTC": None, "ETH": None})
    st.session_state.daily_trades = data.get("daily_trades", 0)
    st.session_state.last_day = data.get("last_day", datetime.now().day)
    st.session_state.ref_price = data.get("ref_price", {"BTC": 0.0, "ETH": 0.0})
    st.session_state.last_price = data.get("last_price", {"BTC": 0.0, "ETH": 0.0})
    st.session_state.entry_price = data.get("entry_price", {"BTC": 0.0, "ETH": 0.0})
    st.session_state.highest_price = data.get("highest_price", {"BTC": 0.0, "ETH": 0.0})
    st.session_state.cycle = data.get("cycle", 0)
    st.session_state.umbral = data.get("umbral", 0.01)
    st.session_state.rsi_os = data.get("rsi_os", 30)
    st.session_state.rsi_ob = data.get("rsi_ob", 70)
    st.session_state.ema_fast = data.get("ema_fast", 5)
    st.session_state.ema_slow = data.get("ema_slow", 20)
    st.session_state.stop_loss = data.get("stop_loss", 2.0)
    st.session_state.take_profit = data.get("take_profit", 2.5)
    st.session_state.trailing = data.get("trailing", 1.0)
    st.session_state.expert_score = data.get("expert_score", 30)
    st.session_state.expert_comment = data.get("expert_comment", "")
    ph = data.get("price_history", {"BTC": [], "ETH": []})
    st.session_state.price_history = {k: deque(v, maxlen=200) for k, v in ph.items()}

def init_new_user_state():
    st.session_state.balance = 1000.0
    st.session_state.positions = {"BTC": 0.0, "ETH": 0.0}
    st.session_state.trades = []
    st.session_state.last_action = {"BTC": None, "ETH": None}
    st.session_state.daily_trades = 0
    st.session_state.last_day = datetime.now().day
    st.session_state.ref_price = {"BTC": 0.0, "ETH": 0.0}
    st.session_state.last_price = {"BTC": 0.0, "ETH": 0.0}
    st.session_state.entry_price = {"BTC": 0.0, "ETH": 0.0}
    st.session_state.highest_price = {"BTC": 0.0, "ETH": 0.0}
    st.session_state.cycle = 0
    st.session_state.price_history = {"BTC": deque(maxlen=200), "ETH": deque(maxlen=200)}
    st.session_state.umbral = 0.01
    st.session_state.rsi_os = 30
    st.session_state.rsi_ob = 70
    st.session_state.ema_fast = 5
    st.session_state.ema_slow = 20
    st.session_state.stop_loss = 2.0
    st.session_state.take_profit = 2.5
    st.session_state.trailing = 1.0
    st.session_state.expert_score = 30
    st.session_state.expert_comment = ""

# ==================== TELEGRAM ====================
TELEGRAM_TOKEN = "8532857017:AAHwLhRnM3oC6TbgFFKAEmQnZVoo6JD_esQ"
TELEGRAM_CHAT_ID = "5835990242"

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=3)
    except:
        pass

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

def get_fear_greed():
    try:
        resp = requests.get("https://api.alternative.me/fng/", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return int(data['data'][0]['value']), data['data'][0]['value_classification']
    except:
        pass
    return 50, "Neutral"

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

def get_enhanced_signal(prices, threshold, rsi_os, rsi_ob, ema_fast, ema_slow, fng_value):
    if len(prices) < max(ema_slow, 15):
        return "HOLD", 50
    ref = prices[0]
    current = prices[-1]
    change_pct = (current - ref) / ref * 100 if ref != 0 else 0
    if change_pct >= threshold:
        signal_change = "BUY"
    elif change_pct <= -threshold:
        signal_change = "SELL"
    else:
        signal_change = "HOLD"
    ema_f = compute_ema(prices, ema_fast)
    ema_s = compute_ema(prices, ema_slow)
    if ema_f is None or ema_s is None:
        signal_ema = "HOLD"
    else:
        signal_ema = "BUY" if ema_f > ema_s else "SELL" if ema_f < ema_s else "HOLD"
    rsi = compute_rsi(prices)
    if rsi <= rsi_os:
        signal_rsi = "BUY"
    elif rsi >= rsi_ob:
        signal_rsi = "SELL"
    else:
        signal_rsi = "HOLD"
    if fng_value <= 20:
        signal_fng = "BUY"
    elif fng_value >= 80:
        signal_fng = "SELL"
    else:
        signal_fng = "HOLD"
    buy_score = 0
    sell_score = 0
    if signal_change == "BUY": buy_score += 25
    elif signal_change == "SELL": sell_score += 25
    if signal_ema == "BUY": buy_score += 25
    elif signal_ema == "SELL": sell_score += 25
    if signal_rsi == "BUY": buy_score += 25
    elif signal_rsi == "SELL": sell_score += 25
    if signal_fng == "BUY": buy_score += 25
    elif signal_fng == "SELL": sell_score += 25
    if buy_score > sell_score:
        return "BUY", rsi
    elif sell_score > buy_score:
        return "SELL", rsi
    else:
        return "HOLD", rsi

# ==================== LOGIN ====================
if not st.session_state.authenticated:
    st.title("🤖 Crypto Trading Bot")
    tab1, tab2 = st.tabs(["Iniciar sesión", "Registrarse"])
    with tab1:
        email = st.text_input("Correo electrónico", key="login_email")
        password = st.text_input("Contraseña", type="password", key="login_pass")
        if st.button("Ingresar"):
            ok, msg = sign_in(email, password)
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)
    with tab2:
        email = st.text_input("Correo electrónico", key="reg_email")
        password = st.text_input("Contraseña", type="password", key="reg_pass")
        if st.button("Registrarse"):
            ok, msg = sign_up(email, password)
            if ok:
                st.success(msg)
            else:
                st.error(msg)
    st.stop()

# ==================== INICIALIZAR DATOS ====================
if st.session_state.user_data is None:
    init_new_user_state()
else:
    restore_user_state()

# ==================== INTERFAZ ====================
st.set_page_config(page_title="Bot de Trading con Autenticación", layout="wide")
st.title("📊 Bot de Trading con Estrategia Experta (RSI, EMA, Fear & Greed)")

st.sidebar.header("⚙️ Configuración General")
umbral = st.sidebar.number_input("Umbral de entrada (%)", 0.005, 1.0, st.session_state.umbral, 0.005, key="umbral_input")
rsi_os = st.sidebar.number_input("RSI sobreventa", 20, 40, st.session_state.rsi_os, key="rsi_os_input")
rsi_ob = st.sidebar.number_input("RSI sobrecompra", 60, 80, st.session_state.rsi_ob, key="rsi_ob_input")
ema_fast = st.sidebar.number_input("EMA rápida (periodos)", 3, 20, st.session_state.ema_fast, key="ema_fast_input")
ema_slow = st.sidebar.number_input("EMA lenta (periodos)", 10, 50, st.session_state.ema_slow, key="ema_slow_input")

st.sidebar.header("🛡️ Gestión de Riesgo")
stop_loss = st.sidebar.number_input("Stop Loss fijo (%)", 0.5, 10.0, st.session_state.stop_loss, 0.5, key="stop_loss_input")
take_profit = st.sidebar.number_input("Take Profit fijo (%)", 0.5, 20.0, st.session_state.take_profit, 0.5, key="take_profit_input")
trailing = st.sidebar.number_input("Trailing Stop (%)", 0.2, 5.0, st.session_state.trailing, 0.1, key="trailing_input")

st.sidebar.header("🧠 Análisis de Expertos (Basado en la 'Guía')")
expert_score = st.sidebar.slider("Puntaje de tendencia (0=Muy Bajista, 100=Muy Alcista)", 0, 100, st.session_state.expert_score, 5, key="expert_score_slider")
expert_comment = st.sidebar.text_area("Comentario / Estrategia", value=st.session_state.expert_comment, height=100, key="expert_comment_area")
if st.sidebar.button("Actualizar Análisis Experto"):
    st.session_state.expert_score = expert_score
    st.session_state.expert_comment = expert_comment
    save_user_data()
    st.success("Análisis de expertos actualizado.")

st.sidebar.subheader("💰 Cartera")
saldo_placeholder = st.sidebar.empty()
total_placeholder = st.sidebar.empty()
ops_placeholder = st.sidebar.empty()

if st.sidebar.button("Cerrar sesión"):
    sign_out()

if st.sidebar.button("Reiniciar simulación"):
    init_new_user_state()
    save_user_data()
    st.rerun()

if st.sidebar.button("📢 Prueba Telegram"):
    send_telegram("🧪 Bot con autenticación - activo")
    st.success("Enviado")

st.session_state.umbral = umbral
st.session_state.rsi_os = rsi_os
st.session_state.rsi_ob = rsi_ob
st.session_state.ema_fast = ema_fast
st.session_state.ema_slow = ema_slow
st.session_state.stop_loss = stop_loss
st.session_state.take_profit = take_profit
st.session_state.trailing = trailing

tabla_placeholder = st.empty()
info_placeholder = st.empty()
historial_placeholder = st.empty()

while True:
    btc = get_bitso_price("btc_mxn")
    eth = get_bitso_price("eth_mxn")
    if btc is None or eth is None:
        tabla_placeholder.error("❌ Error al obtener precios. Reintentando...")
        time.sleep(10)
        continue

    st.session_state.last_price["BTC"] = btc
    st.session_state.last_price["ETH"] = eth
    st.session_state.price_history["BTC"].append(btc)
    st.session_state.price_history["ETH"].append(eth)

    if st.session_state.ref_price["BTC"] == 0:
        st.session_state.ref_price["BTC"] = btc
        st.session_state.ref_price["ETH"] = eth

    st.session_state.cycle += 1
    fng_value, fng_label = get_fear_greed()
    var_btc = (btc - st.session_state.ref_price["BTC"]) / st.session_state.ref_price["BTC"] * 100
    var_eth = (eth - st.session_state.ref_price["ETH"]) / st.session_state.ref_price["ETH"] * 100

    tabla_placeholder.subheader("📊 Señales en Vivo")
    tabla_placeholder.table({
        "Moneda": ["Bitcoin", "Ethereum"],
        "Precio MXN": [f"${btc:,.0f}", f"${eth:,.0f}"],
        "Var desde inicio": [f"{var_btc:+.2f}%", f"{var_eth:+.2f}%"],
        "Señal (solo info)": [
            "COMPRAR" if var_btc >= st.session_state.umbral else "VENDER" if var_btc <= -st.session_state.umbral else "MANTENER",
            "COMPRAR" if var_eth >= st.session_state.umbral else "VENDER" if var_eth <= -st.session_state.umbral else "MANTENER"
        ]
    })
    info_placeholder.caption(f"Ciclo: {st.session_state.cycle} | Umbral: {st.session_state.umbral}% | SL: {st.session_state.stop_loss}% | TP: {st.session_state.take_profit}% | Trailing: {st.session_state.trailing}% | Fear & Greed: {fng_value}/100 ({fng_label})")

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

    hoy = datetime.now().day
    if hoy != st.session_state.last_day:
        st.session_state.daily_trades = 0
        st.session_state.last_day = hoy

    for sym, precio in [("BTC", btc), ("ETH", eth)]:
        hist = list(st.session_state.price_history[sym])
        if len(hist) >= max(st.session_state.ema_slow, 15):
            signal_auto, rsi_val = get_enhanced_signal(
                hist, st.session_state.umbral, st.session_state.rsi_os, st.session_state.rsi_ob,
                st.session_state.ema_fast, st.session_state.ema_slow, fng_value
            )
        else:
            signal_auto = "HOLD"
            rsi_val = 50

        if st.session_state.expert_score >= 80:
            signal_expert = "BUY"
        elif st.session_state.expert_score <= 20:
            signal_expert = "SELL"
        else:
            signal_expert = "HOLD"

        if st.session_state.expert_score >= 80:
            senal = "BUY"
            razon_extra = f"Experto ({st.session_state.expert_score})"
        elif st.session_state.expert_score <= 20:
            senal = "SELL"
            razon_extra = f"Experto ({st.session_state.expert_score})"
        else:
            buy_votes = 0
            sell_votes = 0
            if signal_auto == "BUY":
                buy_votes += 40
            elif signal_auto == "SELL":
                sell_votes += 40
            if signal_expert == "BUY":
                buy_votes += 35
            elif signal_expert == "SELL":
                sell_votes += 35
            if fng_value <= 20:
                buy_votes += 25
            elif fng_value >= 80:
                sell_votes += 25
            if buy_votes > sell_votes:
                senal = "BUY"
                razon_extra = "Ponderado"
            elif sell_votes > buy_votes:
                senal = "SELL"
                razon_extra = "Ponderado"
            else:
                senal = "HOLD"
                razon_extra = "Empate"

        pos = st.session_state.positions.get(sym, 0)
        entry = st.session_state.entry_price.get(sym, 0)
        highest = st.session_state.highest_price.get(sym, precio)
        razon = ""
        accion = None

        if precio > highest:
            st.session_state.highest_price[sym] = precio
            highest = precio

        if pos > 0 and entry > 0:
            ganancia = (precio - entry) / entry * 100
            if ganancia >= st.session_state.take_profit:
                accion = "SELL"
                razon = f"Take Profit ({st.session_state.take_profit}%)"
            elif ganancia <= -st.session_state.stop_loss:
                accion = "SELL"
                razon = f"Stop Loss ({st.session_state.stop_loss}%)"
            elif highest > entry:
                caida = (precio - highest) / highest * 100
                if caida <= -st.session_state.trailing:
                    accion = "SELL"
                    razon = f"Trailing Stop ({st.session_state.trailing}%)"

        if accion is None:
            if senal == "BUY" and pos == 0:
                accion = "BUY"
            elif senal == "SELL" and pos > 0:
                accion = "SELL"
                razon = razon_extra

        last_act = st.session_state.last_action.get(sym)
        if accion and accion != last_act and st.session_state.daily_trades < 20:
            amount = min(500.0, st.session_state.balance)
            if accion == "BUY" and amount > 0:
                eff = precio * 1.0005
                com = amount * 0.001
                qty = (amount - com) / eff
                st.session_state.balance -= amount
                st.session_state.positions[sym] = qty
                st.session_state.entry_price[sym] = eff
                st.session_state.highest_price[sym] = eff
                st.session_state.daily_trades += 1
                msg = (f"🟢 COMPRA {sym}\n"
                       f"Cantidad: {qty:.6f}\n"
                       f"Precio: ${precio:,.0f} MXN\n"
                       f"Saldo: ${st.session_state.balance:.2f}\n"
                       f"Razón: {razon_extra}")
                send_telegram(msg)
                st.session_state
