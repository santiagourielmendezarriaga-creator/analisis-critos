import streamlit as st
import requests
import time
import json
import os
from datetime import datetime, timedelta
from collections import deque
import yfinance as yf

# ==================== ARCHIVO LOCAL PARA GUARDAR DATOS ====================
DATA_FILE = "data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return None
    return None

def save_data():
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
        "umbral_caida": st.session_state.umbral_caida,
        "stop_loss": st.session_state.stop_loss,
        "take_profit": st.session_state.take_profit,
        "trailing": st.session_state.trailing,
        "umbral_indicadores": st.session_state.umbral_indicadores,
        "expert_score": st.session_state.expert_score,
        "rsi_os": st.session_state.rsi_os,
        "rsi_ob": st.session_state.rsi_ob,
        "ema_fast": st.session_state.ema_fast,
        "ema_slow": st.session_state.ema_slow,
        "sl_triggered": st.session_state.sl_triggered,
        "sl_low_price": st.session_state.sl_low_price,
        "indicadores_activados": st.session_state.indicadores_activados
    }
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

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
    
    st.session_state.umbral_caida = 0.02
    st.session_state.stop_loss = 5.0
    st.session_state.take_profit = 0.02
    st.session_state.trailing = 1.0
    st.session_state.umbral_indicadores = 50.0
    st.session_state.expert_score = 30
    st.session_state.rsi_os = 30
    st.session_state.rsi_ob = 80
    st.session_state.ema_fast = 5
    st.session_state.ema_slow = 12
    st.session_state.sl_triggered = {"BTC": False, "ETH": False}
    st.session_state.sl_low_price = {"BTC": 0.0, "ETH": 0.0}
    st.session_state.indicadores_activados = {"BTC": False, "ETH": False}

def restore_from_file():
    data = load_data()
    if data is None:
        init_new_user_state()
        return
    
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
    st.session_state.umbral_caida = data.get("umbral_caida", 0.02)
    st.session_state.stop_loss = data.get("stop_loss", 5.0)
    st.session_state.take_profit = data.get("take_profit", 0.02)
    st.session_state.trailing = data.get("trailing", 1.0)
    st.session_state.umbral_indicadores = data.get("umbral_indicadores", 50.0)
    st.session_state.expert_score = data.get("expert_score", 30)
    st.session_state.rsi_os = data.get("rsi_os", 30)
    st.session_state.rsi_ob = data.get("rsi_ob", 80)
    st.session_state.ema_fast = data.get("ema_fast", 5)
    st.session_state.ema_slow = data.get("ema_slow", 12)
    st.session_state.sl_triggered = data.get("sl_triggered", {"BTC": False, "ETH": False})
    st.session_state.sl_low_price = data.get("sl_low_price", {"BTC": 0.0, "ETH": 0.0})
    st.session_state.indicadores_activados = data.get("indicadores_activados", {"BTC": False, "ETH": False})
    
    ph = data.get("price_history", {"BTC": [], "ETH": []})
    st.session_state.price_history = {k: deque(v, maxlen=200) for k, v in ph.items()}

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

# ==================== INDICADORES (no se usan) ====================
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

def get_enhanced_signal(prices, rsi_os, rsi_ob, ema_fast, ema_slow, fng_value, expert_score):
    if len(prices) < max(ema_slow, 15):
        return "HOLD", 50
    ref = prices[0]
    current = prices[-1]
    change_pct = (current - ref) / ref * 100 if ref != 0 else 0
    if change_pct >= 0:
        signal_change = "BUY"
    else:
        signal_change = "SELL"
    
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
    
    buy_votes = 0
    sell_votes = 0
    if signal_change == "BUY": buy_votes += 35
    elif signal_change == "SELL": sell_votes += 35
    if signal_ema == "BUY": buy_votes += 30
    elif signal_ema == "SELL": sell_votes += 30
    if signal_rsi == "BUY": buy_votes += 20
    elif signal_rsi == "SELL": sell_votes += 20
    if fng_value <= 20: buy_votes += 15
    elif fng_value >= 80: sell_votes += 15
    if expert_score >= 60: buy_votes += 20
    elif expert_score <= 40: sell_votes += 20
    
    if buy_votes > sell_votes:
        return "BUY", rsi
    elif sell_votes > buy_votes:
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

# ==================== INICIALIZAR ESTADO ====================
if "data_loaded" not in st.session_state:
    restore_from_file()
    st.session_state.data_loaded = True
    # ==================== INTERFAZ PRINCIPAL ====================
st.set_page_config(page_title="Bot de Trading - Scalping Extremo (Señales Telegram)", layout="wide")

if "umbral_caida" not in st.session_state:
    init_new_user_state()

st.title("📡 Bot de Trading - Scalping Extremo (Señales por Telegram)")

# Sidebar - Parámetros principales
st.sidebar.header("⚙️ Configuración Principal")
valor_umbral = min(50.0, float(st.session_state.umbral_caida))
umbral_caida = st.sidebar.number_input("Caída para comprar (%)", min_value=0.01, max_value=50.0, step=0.01, value=valor_umbral)

valor_tp = min(50.0, float(st.session_state.take_profit))
take_profit = st.sidebar.number_input("Take Profit sin indicadores (%)", min_value=0.01, max_value=50.0, step=0.01, value=valor_tp)

stop_loss = st.sidebar.number_input("Stop Loss (%)", min_value=0.5, max_value=20.0, value=float(st.session_state.stop_loss), step=0.5)
trailing = st.sidebar.number_input("Trailing Stop (%)", min_value=0.2, max_value=5.0, value=float(st.session_state.trailing), step=0.1)

valor_umbral_ind = min(100.0, float(st.session_state.umbral_indicadores))
umbral_indicadores = st.sidebar.number_input("Activar indicadores a partir de (%)", min_value=1.0, max_value=100.0, value=valor_umbral_ind, step=0.5)

# Sidebar - Parámetros de indicadores
st.sidebar.header("🧠 Indicadores (no se activan con TP tan bajo)")
expert_score = st.sidebar.slider("Puntaje de tendencia", 0, 100, st.session_state.expert_score, 5)
rsi_os = st.sidebar.number_input("RSI sobreventa", min_value=20, max_value=40, value=int(st.session_state.rsi_os), step=1)
rsi_ob = st.sidebar.number_input("RSI sobrecompra", min_value=70, max_value=90, value=int(st.session_state.rsi_ob), step=1)
ema_fast = st.sidebar.number_input("EMA rápida (periodos)", min_value=3, max_value=20, value=int(st.session_state.ema_fast), step=1)
ema_slow = st.sidebar.number_input("EMA lenta (periodos)", min_value=10, max_value=50, value=int(st.session_state.ema_slow), step=1)

st.sidebar.subheader("💰 Cartera")
saldo_placeholder = st.sidebar.empty()
total_placeholder = st.sidebar.empty()
ops_placeholder = st.sidebar.empty()

if st.sidebar.button("Reiniciar simulación"):
    init_new_user_state()
    save_data()
    st.rerun()
if st.sidebar.button("📢 Prueba Telegram"):
    send_telegram("📡 Bot de señales activo (modo scalping)")
    st.success("Enviado")

# Actualizar parámetros
st.session_state.umbral_caida = umbral_caida
st.session_state.take_profit = take_profit
st.session_state.stop_loss = stop_loss
st.session_state.trailing = trailing
st.session_state.umbral_indicadores = umbral_indicadores
st.session_state.expert_score = expert_score
st.session_state.rsi_os = rsi_os
st.session_state.rsi_ob = rsi_ob
st.session_state.ema_fast = ema_fast
st.session_state.ema_slow = ema_slow

# Contenedores dinámicos
tabla_placeholder = st.empty()
info_placeholder = st.empty()
historial_placeholder = st.empty()
estado_placeholder = st.empty()

# ==================== FUNCIÓN PARA ENVIAR SEÑALES ====================
def send_signal_telegram(sym, tipo, precio, razon, ejecutado):
    try:
        estado = "✅ EJECUTADA" if ejecutado else "⚠️ NO EJECUTADA"
        msg = (f"📢 SEÑAL {estado} - {tipo} {sym}\n"
               f"Precio: ${precio:,.0f}\n"
               f"Razón: {razon}\n"
               f"Saldo disponible: ${st.session_state.balance:.2f}\n"
               f"Posición {sym}: {st.session_state.positions[sym]:.6f}")
        send_telegram(msg)
    except:
        pass

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

    st.session_state.cycle += 1
    fng_value, fng_label = get_fear_greed()
    
    caida_btc = (st.session_state.ref_price["BTC"] - btc) / st.session_state.ref_price["BTC"] * 100
    caida_eth = (st.session_state.ref_price["ETH"] - eth) / st.session_state.ref_price["ETH"] * 100

    tabla_placeholder.subheader("📊 Señales - Scalping Extremo")
    tabla_placeholder.table({
        "Moneda": ["Bitcoin", "Ethereum"],
        "Precio MXN": [f"${btc:,.0f}", f"${eth:,.0f}"],
        "Caída desde inicio": [f"{caida_btc:+.4f}%", f"{caida_eth:+.4f}%"],
        "¿Comprar?": [
            "✅ COMPRAR $500" if caida_btc >= st.session_state.umbral_caida and st.session_state.positions["BTC"] == 0 else "❌ Esperar",
            "✅ COMPRAR $500" if caida_eth >= st.session_state.umbral_caida and st.session_state.positions["ETH"] == 0 else "❌ Esperar"
        ]
    })
    info_placeholder.caption(f"Ciclo: {st.session_state.cycle} | Caída para comprar: {st.session_state.umbral_caida}% | TP: {st.session_state.take_profit}% | SL: {st.session_state.stop_loss}% | Trailing: {st.session_state.trailing}% | Fear & Greed: {fng_value}/100 ({fng_label})")

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
        pos = st.session_state.positions.get(sym, 0)
        entry = st.session_state.entry_price.get(sym, 0)
        ref = st.session_state.ref_price.get(sym, 0)
        
        caida_actual = (ref - precio) / ref * 100 if ref != 0 else 0
        ganancia = (precio - entry) / entry * 100 if entry != 0 else 0
        
        razon = ""
        accion = None
        
        # Activar indicadores solo si la ganancia supera el umbral
        if pos > 0 and entry > 0:
            if ganancia >= st.session_state.umbral_indicadores:
                st.session_state.indicadores_activados[sym] = True
            else:
                st.session_state.indicadores_activados[sym] = False

        # ===== GESTIÓN DE POSICIÓN ABIERTA =====
        if pos > 0 and entry > 0:
            if ganancia >= st.session_state.take_profit:
                accion = "SELL"
                razon = f"Take Profit ({st.session_state.take_profit}%)"
            elif ganancia <= -st.session_state.stop_loss:
                accion = "SELL"
                razon = f"Stop Loss ({st.session_state.stop_loss}%)"
            else:
                highest = st.session_state.highest_price.get(sym, 0)
                if highest > entry and (highest - precio) / highest * 100 >= st.session_state.trailing:
                    accion = "SELL"
                    razon = f"Trailing Stop ({st.session_state.trailing}%)"

        # ===== COMPRA POR CAÍDA =====
        if accion is None:
            if caida_actual >= st.session_state.umbral_caida and pos == 0:
                accion = "BUY"
                razon = f"Caída del {caida_actual:.4f}%"
                st.session_state.indicadores_activados[sym] = False

        # ===== EJECUCIÓN Y NOTIFICACIÓN =====
        last_act = st.session_state.last_action.get(sym)
        if accion and accion != last_act:
            ejecutado = False
            if accion == "BUY":
                amount = 500.0
                if amount <= st.session_state.balance:
                    com = amount * 0.001
                    qty = (amount - com) / precio
                    st.session_state.balance -= amount
                    st.session_state.positions[sym] = qty
                    st.session_state.entry_price[sym] = precio
                    st.session_state.highest_price[sym] = precio
                    st.session_state.daily_trades += 1
                    st.session_state.indicadores_activados[sym] = False
                    ejecutado = True
                    st.session_state.last_action[sym] = accion
                    save_data()
                else:
                    ejecutado = False
            elif accion == "SELL" and pos > 0:
                qty = pos
                gross = qty * precio
                com = gross * 0.001
                net = gross - com
                st.session_state.balance += net
                st.session_state.positions[sym] = 0
                st.session_state.entry_price[sym] = 0
                st.session_state.daily_trades += 1
                st.session_state.indicadores_activados[sym] = False
                ejecutado = True
                st.session_state.last_action[sym] = accion
                save_data()
            
            # Enviar señal por Telegram (siempre, incluso si no se ejecutó)
            send_signal_telegram(sym, accion, precio, razon, ejecutado)

    if st.session_state.cycle % 10 == 0:
        save_data()

    estado_placeholder.info(f"🔹 Indicadores activos: BTC={st.session_state.indicadores_activados['BTC']} | ETH={st.session_state.indicadores_activados['ETH']}")

    time.sleep(30)
