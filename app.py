import streamlit as st
import requests
import time
import json
import os
from datetime import datetime, timedelta
from collections import deque
from supabase import create_client, Client

# ==================== SUPABASE ====================
SUPABASE_URL = "https://nzoerhdtsnvzshwirjvt.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im56b2VyaGR0c252enNod2lyanZ0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODE0NTkyNzcsImV4cCI6MjA5NzAzNTI3N30.Z2M1zYAMXf-L-Y8lpkWk6lAOD5-ts-F3KP97aPrAYtg"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user_id = None
    st.session_state.user_data = None
    st.session_state.user_email = None
    st.session_state.data_loaded = False

# ==================== AUTENTICACIÓN ====================
def sign_up(email, password):
    try:
        resp = supabase.auth.sign_up({"email": email, "password": password})
        if resp.user:
            trial_end = (datetime.now() + timedelta(hours=24)).isoformat()
            supabase.table("user_data").insert({
                "user_id": resp.user.id,
                "trial_end": trial_end,
                "is_premium": False
            }).execute()
            return True, "Registro exitoso. Prueba gratuita de 24 horas activada."
        return False, "Error en el registro."
    except Exception as e:
        return False, str(e)

def sign_in(email, password):
    try:
        resp = supabase.auth.sign_in_with_password({"email": email, "password": password})
        if resp.user:
            st.session_state.authenticated = True
            st.session_state.user_id = resp.user.id
            st.session_state.user_email = resp.user.email
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
    st.session_state.user_email = None
    st.session_state.data_loaded = False
    st.rerun()

def load_user_data():
    resp = supabase.table("user_data").select("*").eq("user_id", st.session_state.user_id).execute()
    if resp.data:
        st.session_state.user_data = resp.data[0]
    else:
        trial_end = (datetime.now() + timedelta(hours=24)).isoformat()
        supabase.table("user_data").insert({
            "user_id": st.session_state.user_id,
            "trial_end": trial_end,
            "is_premium": False
        }).execute()
        resp = supabase.table("user_data").select("*").eq("user_id", st.session_state.user_id).execute()
        st.session_state.user_data = resp.data[0]

def save_user_data():
    if not st.session_state.user_id:
        return
    # Convertir trades a lista de listas [timestamp, mensaje]
    trades_serializable = []
    for ts, msg in st.session_state.trades[-100:]:
        trades_serializable.append([ts.isoformat(), msg])
    
    data = {
        "balance": st.session_state.balance,
        "positions": st.session_state.positions,
        "trades": trades_serializable,
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
        "trailing_stop": st.session_state.trailing,
        "expert_score": st.session_state.expert_score,
        "expert_comment": st.session_state.expert_comment,
        "custom_balance": st.session_state.get("custom_balance", None),
        "is_premium": st.session_state.is_premium,
        "trial_end": st.session_state.user_data.get("trial_end"),
        "sl_triggered": st.session_state.sl_triggered,
        "sl_low_price": st.session_state.sl_low_price
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
    # Forzar umbral mínimo 0.1
    raw_umbral = data.get("umbral", 0.25)
    st.session_state.umbral = max(0.1, float(raw_umbral))
    st.session_state.rsi_os = data.get("rsi_os", 30)
    st.session_state.rsi_ob = data.get("rsi_ob", 80)
    st.session_state.ema_fast = data.get("ema_fast", 5)
    st.session_state.ema_slow = data.get("ema_slow", 12)
    st.session_state.stop_loss = float(data.get("stop_loss", 2.0))
    st.session_state.take_profit = float(data.get("take_profit", 2.5))
    st.session_state.trailing = float(data.get("trailing_stop", 1.0))
    st.session_state.expert_score = data.get("expert_score", 30)
    st.session_state.expert_comment = data.get("expert_comment", "")
    st.session_state.is_premium = data.get("is_premium", False)
    custom = data.get("custom_balance")
    if custom is not None and st.session_state.is_premium:
        st.session_state.balance = custom
        st.session_state.custom_balance = custom
    else:
        st.session_state.custom_balance = None
    ph = data.get("price_history", {"BTC": [], "ETH": []})
    st.session_state.price_history = {k: deque(v, maxlen=200) for k, v in ph.items()}
    # Cargar flags de SL (ya deben existir en la BD)
    st.session_state.sl_triggered = data.get("sl_triggered", {"BTC": False, "ETH": False})
    st.session_state.sl_low_price = data.get("sl_low_price", {"BTC": 0.0, "ETH": 0.0})

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
    st.session_state.umbral = 0.25
    st.session_state.rsi_os = 30
    st.session_state.rsi_ob = 80
    st.session_state.ema_fast = 5
    st.session_state.ema_slow = 12
    st.session_state.stop_loss = 2.0
    st.session_state.take_profit = 2.5
    st.session_state.trailing = 1.0
    st.session_state.expert_score = 30
    st.session_state.expert_comment = ""
    st.session_state.is_premium = False
    st.session_state.custom_balance = None
    st.session_state.sl_triggered = {"BTC": False, "ETH": False}
    st.session_state.sl_low_price = {"BTC": 0.0, "ETH": 0.0}

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

# ==================== INDICADORES Y ATR ====================
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

def calcular_atr(prices, periodo=14):
    if len(prices) < periodo + 1:
        return None
    atr = 0.0
    for i in range(1, len(prices)):
        rango = abs(prices[i] - prices[i-1])
        if i == 1:
            atr = rango
        else:
            atr = (atr * (periodo - 1) + rango) / periodo
    return atr

def umbral_dinamico(prices, umbral_base=0.25):
    if len(prices) < 15:
        return max(0.1, umbral_base)
    atr = calcular_atr(prices)
    if atr is None or prices[-1] == 0:
        return max(0.1, umbral_base)
    volatilidad_pct = (atr / prices[-1]) * 100
    if volatilidad_pct > 1.5:
        return max(0.1, min(0.6, umbral_base * 1.6))
    elif volatilidad_pct < 0.5:
        return max(0.1, max(0.15, umbral_base * 0.7))
    else:
        return max(0.1, umbral_base)

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
    if signal_change == "BUY": buy_score += 40
    elif signal_change == "SELL": sell_score += 40
    if signal_ema == "BUY": buy_score += 25
    elif signal_ema == "SELL": sell_score += 25
    if signal_rsi == "BUY": buy_score += 20
    elif signal_rsi == "SELL": sell_score += 20
    if signal_fng == "BUY": buy_score += 15
    elif signal_fng == "SELL": sell_score += 15
    if buy_score > sell_score:
        return "BUY", rsi
    elif sell_score > buy_score:
        return "SELL", rsi
    else:
        return "HOLD", rsi

def confirmacion_vela(historial, senal_esperada):
    if len(historial) < 2:
        return True
    prev = historial[-2]
    curr = historial[-1]
    if senal_esperada == "BUY":
        return curr > prev
    elif senal_esperada == "SELL":
        return curr < prev
    return True

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

# ==================== RESTAURAR DATOS ====================
if not st.session_state.data_loaded:
    with st.spinner("Cargando tu cartera y configuración..."):
        if st.session_state.user_data is None:
            init_new_user_state()
        else:
            restore_user_state()
        st.session_state.data_loaded = True
        # ==================== INTERFAZ PRINCIPAL ====================
st.set_page_config(page_title="Bot de Trading Premium", layout="wide")
st.title("📊 Bot de Trading con Estrategia Experta (RSI, EMA, Fear & Greed)")

# Sidebar
st.sidebar.header("⚙️ Configuración General")
valor_umbral = max(0.1, float(st.session_state.umbral))
umbral_base = st.sidebar.number_input("Umbral base (%)", min_value=0.1, max_value=2.0, step=0.05, value=valor_umbral, help="Se ajusta por volatilidad")
rsi_os = st.sidebar.number_input("RSI sobreventa", min_value=20, max_value=40, value=int(st.session_state.rsi_os), step=1)
rsi_ob = st.sidebar.number_input("RSI sobrecompra", min_value=70, max_value=90, value=int(st.session_state.rsi_ob), step=1)
ema_fast = st.sidebar.number_input("EMA rápida (periodos)", min_value=3, max_value=20, value=int(st.session_state.ema_fast), step=1)
ema_slow = st.sidebar.number_input("EMA lenta (periodos)", min_value=10, max_value=50, value=int(st.session_state.ema_slow), step=1)

st.sidebar.header("🛡️ Gestión de Riesgo")
stop_loss = st.sidebar.number_input("Stop Loss fijo (%)", min_value=0.5, max_value=10.0, value=float(st.session_state.stop_loss), step=0.5)
take_profit = st.sidebar.number_input("Take Profit fijo (%)", min_value=0.5, max_value=20.0, value=float(st.session_state.take_profit), step=0.5)
trailing = st.sidebar.number_input("Trailing Stop (%)", min_value=0.2, max_value=5.0, value=float(st.session_state.trailing), step=0.1)

st.sidebar.header("🧠 Análisis de Expertos")
expert_score = st.sidebar.slider("Puntaje de tendencia (0=Muy Bajista, 100=Muy Alcista)", 0, 100, st.session_state.expert_score, 5)
expert_comment = st.sidebar.text_area("Comentario / Estrategia", value=st.session_state.expert_comment, height=100, key="expert_comment_area")
if st.sidebar.button("Actualizar Análisis Experto"):
    st.session_state.expert_score = expert_score
    st.session_state.expert_comment = expert_comment
    save_user_data()
    st.success("Análisis actualizado.")

if st.session_state.user_data.get("is_premium", False):
    st.sidebar.subheader("💰 Personalizar saldo")
    nuevo_saldo = st.sidebar.number_input("Saldo inicial (MXN)", value=float(st.session_state.balance), step=100.0, format="%.2f")
    if nuevo_saldo != st.session_state.balance:
        st.session_state.balance = nuevo_saldo
        supabase.table("user_data").update({"custom_balance": nuevo_saldo}).eq("user_id", st.session_state.user_id).execute()
        st.sidebar.success("Saldo actualizado.")
else:
    st.sidebar.info("🔓 Para personalizar tu saldo, suscríbete al plan premium.")

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
    send_telegram("🧪 Bot mejorado - activo")
    st.success("Enviado")

# Actualizar parámetros
st.session_state.umbral = max(0.1, umbral_base)
st.session_state.rsi_os = rsi_os
st.session_state.rsi_ob = rsi_ob
st.session_state.ema_fast = ema_fast
st.session_state.ema_slow = ema_slow
st.session_state.stop_loss = stop_loss
st.session_state.take_profit = take_profit
st.session_state.trailing = trailing

# Contenedores dinámicos
tabla_placeholder = st.empty()
info_placeholder = st.empty()
historial_placeholder = st.empty()

# ==================== BUCLE PRINCIPAL ====================
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

    # Umbrales dinámicos
    hist_btc = list(st.session_state.price_history["BTC"])
    hist_eth = list(st.session_state.price_history["ETH"])
    umbral_btc = umbral_dinamico(hist_btc, st.session_state.umbral)
    umbral_eth = umbral_dinamico(hist_eth, st.session_state.umbral)

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
            "COMPRAR" if var_btc >= umbral_btc else "VENDER" if var_btc <= -umbral_btc else "MANTENER",
            "COMPRAR" if var_eth >= umbral_eth else "VENDER" if var_eth <= -umbral_eth else "MANTENER"
        ]
    })
    info_placeholder.caption(f"Ciclo: {st.session_state.cycle} | Umbral base: {st.session_state.umbral}% | BTC umbral: {umbral_btc:.2f}% | ETH umbral: {umbral_eth:.2f}% | SL: {st.session_state.stop_loss}% | TP: {st.session_state.take_profit}% | Trailing: {st.session_state.trailing}% | Fear & Greed: {fng_value}/100 ({fng_label})")

    total_val = st.session_state.balance
    for s in ["BTC", "ETH"]:
        p = st.session_state.last_price.get(s, 0)
        q = st.session_state.positions.get(s, 0)
        if q > 0 and p > 0:
            total_val += q * p
    saldo_placeholder.metric("Saldo MXN", f"${st.session_state.balance:,.2f}")
    total_placeholder.metric("Valor total", f"${total_val:,.2f}")
    ops_placeholder.metric("Ops hoy", st.session_state.daily_trades)

    historial_placeholder.subheader("📜 Historial (últimas 10)")
    if st.session_state.trades:
        txt = ""
        for ts, msg in reversed(st.session_state.trades[-10:]):
            short_msg = msg.replace("\n", " | ")[:80]
            txt += f"{ts.strftime('%H:%M:%S')} - {short_msg}\n"
        historial_placeholder.text(txt)
    else:
        historial_placeholder.text("Sin operaciones aún.")

    hoy = datetime.now().day
    if hoy != st.session_state.last_day:
        st.session_state.daily_trades = 0
        st.session_state.last_day = hoy

    for sym, precio in [("BTC", btc), ("ETH", eth)]:
        hist = list(st.session_state.price_history[sym])
        umbral_actual = umbral_btc if sym == "BTC" else umbral_eth
        if len(hist) >= max(st.session_state.ema_slow, 15):
            signal_auto, rsi_val = get_enhanced_signal(
                hist, umbral_actual, st.session_state.rsi_os, st.session_state.rsi_ob,
                st.session_state.ema_fast, st.session_state.ema_slow, fng_value
            )
        else:
            signal_auto = "HOLD"
            rsi_val = 50

        # Votación con veto por experto
        if st.session_state.expert_score >= 80:
            senal = "BUY"
            razon_extra = "Experto Muy Alcista"
        elif st.session_state.expert_score <= 20:
            senal = "SELL"
            razon_extra = "Experto Muy Bajista"
        else:
            buy_votes = 0
            sell_votes = 0
            if signal_auto == "BUY": buy_votes += 40
            elif signal_auto == "SELL": sell_votes += 40
            if st.session_state.expert_score >= 60:
                buy_votes += 35
            elif st.session_state.expert_score <= 40:
                sell_votes += 35
            if fng_value <= 20: buy_votes += 25
            elif fng_value >= 80: sell_votes += 25

            # Veto más agresivo (cambia según tu preferencia)
            if st.session_state.expert_score < 40 and buy_votes > sell_votes:
                senal = "HOLD"
                razon_extra = "Vetado por experto bajista"
            elif st.session_state.expert_score > 60 and sell_votes > buy_votes:
                senal = "HOLD"
                razon_extra = "Vetado por experto alcista"
            else:
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

        # Gestión de posición con rebote al SL
        if pos > 0 and entry > 0:
            ganancia = (precio - entry) / entry * 100

            if ganancia >= st.session_state.take_profit:
                accion = "SELL"
                razon = f"Take Profit ({st.session_state.take_profit}%)"
                st.session_state.sl_triggered[sym] = False
            else:
                if st.session_state.sl_triggered.get(sym, False):
                    low = st.session_state.sl_low_price.get(sym, precio)
                    rebound_pct = 0.5
                    if precio >= low * (1 + rebound_pct/100):
                        accion = "SELL"
                        razon = f"Rebote SL (+{rebound_pct}% desde ${low:,.0f})"
                        st.session_state.sl_triggered[sym] = False
                else:
                    if ganancia <= -st.session_state.stop_loss:
                        st.session_state.sl_triggered[sym] = True
                        st.session_state.sl_low_price[sym] = precio
                        send_telegram(f"⚠️ {sym} tocó SL ({st.session_state.stop_loss}%) - esperando rebote 0.5%")
                    else:
                        if highest > entry:
                            caida = (precio - highest) / highest * 100
                            if caida <= -st.session_state.trailing:
                                accion = "SELL"
                                razon = f"Trailing Stop ({st.session_state.trailing}%)"
                                st.session_state.sl_triggered[sym] = False

        if accion is None:
            if senal == "BUY" and pos == 0:
                if confirmacion_vela(hist, "BUY"):
                    accion = "BUY"
            elif senal == "SELL" and pos > 0:
                if confirmacion_vela(hist, "SELL"):
                    accion = "SELL"
                    razon = razon_extra

        last_act = st.session_state.last_action.get(sym)
        if accion and accion != last_act and st.session_state.daily_trades < 12:
            if accion == "BUY":
                amount = st.session_state.balance * 0.20
                amount = max(200.0, min(1000.0, amount))
                if amount > st.session_state.balance:
                    amount = st.session_state.balance
                if amount >= 200.0:
                    com = amount * 0.001
                    qty = (amount - com) / precio
                    st.session_state.balance -= amount
                    st.session_state.positions[sym] = qty
                    st.session_state.entry_price[sym] = precio
                    st.session_state.highest_price[sym] = precio
                    st.session_state.daily_trades += 1
                    msg = (f"🟢 COMPRA {sym}\n"
                           f"Monto: ${amount:.0f}\n"
                           f"Cantidad: {qty:.6f}\n"
                           f"Precio: ${precio:,.0f}\n"
                           f"Saldo: ${st.session_state.balance:.2f}\n"
                           f"Razón: {razon_extra}")
                    send_telegram(msg)
                    st.session_state.trades.append((datetime.now(), msg))
                    save_user_data()
                    st.session_state.last_action[sym] = accion
            elif accion == "SELL" and pos > 0:
                qty = pos
                gross = qty * precio
                com = gross * 0.001
                net = gross - com
                st.session_state.balance += net
                st.session_state.positions[sym] = 0
                st.session_state.daily_trades += 1
                msg = (f"🔴 VENTA {sym}\n"
                       f"Cantidad: {qty:.6f}\n"
                       f"Precio: ${precio:,.0f}\n"
                       f"Neto: ${net:.2f}\n"
                       f"Motivo: {razon}")
                send_telegram(msg)
                st.session_state.trades.append((datetime.now(), msg))
                save_user_data()
                st.session_state.last_action[sym] = accion
                st.session_state.sl_triggered[sym] = False

    if st.session_state.cycle % 10 == 0:
        save_user_data()

    time.sleep(30)
