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
        "umbral_indicadores_activacion": st.session_state.umbral_indicadores_activacion,
        "expert_score": st.session_state.expert_score,
        "rsi_os": st.session_state.rsi_os,
        "rsi_ob": st.session_state.rsi_ob,
        "ema_fast": st.session_state.ema_fast,
        "ema_slow": st.session_state.ema_slow,
        "sl_triggered": st.session_state.sl_triggered,
        "sl_low_price": st.session_state.sl_low_price,
        "indicadores_activados": st.session_state.indicadores_activados,
        "modo_solo_senales": st.session_state.modo_solo_senales,
        "rendimiento": st.session_state.rendimiento,
        "confianza": st.session_state.confianza,
        "tendencia": st.session_state.tendencia,
        "historial_operaciones": st.session_state.historial_operaciones,
        "modo_aprendizaje": st.session_state.modo_aprendizaje,
        "onchain_cache": st.session_state.onchain_cache
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
    
    st.session_state.umbral_caida = 0.005
    st.session_state.stop_loss = 1.5
    st.session_state.take_profit = 0.02
    st.session_state.trailing = 0.5
    st.session_state.umbral_indicadores_activacion = 2.0
    
    st.session_state.expert_score = 30
    st.session_state.rsi_os = 30
    st.session_state.rsi_ob = 80
    st.session_state.ema_fast = 5
    st.session_state.ema_slow = 12
    st.session_state.sl_triggered = {"BTC": False, "ETH": False}
    st.session_state.sl_low_price = {"BTC": 0.0, "ETH": 0.0}
    st.session_state.indicadores_activados = {"BTC": False, "ETH": False}
    st.session_state.modo_solo_senales = False
    
    st.session_state.rendimiento = {
        "BTC": {"ganadas": 0, "perdidas": 0, "total": 0, "ultimas_10": []},
        "ETH": {"ganadas": 0, "perdidas": 0, "total": 0, "ultimas_10": []}
    }
    st.session_state.confianza = {"BTC": 50, "ETH": 50}
    st.session_state.tendencia = {"BTC": "NEUTRAL", "ETH": "NEUTRAL"}
    st.session_state.historial_operaciones = []
    st.session_state.modo_aprendizaje = True
    st.session_state.onchain_cache = {
        "BTC": {"valor": None, "timestamp": 0},
        "ETH": {"valor": None, "timestamp": 0}
    }

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
    st.session_state.umbral_caida = data.get("umbral_caida", 0.005)
    st.session_state.stop_loss = data.get("stop_loss", 1.5)
    st.session_state.take_profit = data.get("take_profit", 0.02)
    st.session_state.trailing = data.get("trailing", 0.5)
    st.session_state.umbral_indicadores_activacion = data.get("umbral_indicadores_activacion", 2.0)
    st.session_state.expert_score = data.get("expert_score", 30)
    st.session_state.rsi_os = data.get("rsi_os", 30)
    st.session_state.rsi_ob = data.get("rsi_ob", 80)
    st.session_state.ema_fast = data.get("ema_fast", 5)
    st.session_state.ema_slow = data.get("ema_slow", 12)
    st.session_state.sl_triggered = data.get("sl_triggered", {"BTC": False, "ETH": False})
    st.session_state.sl_low_price = data.get("sl_low_price", {"BTC": 0.0, "ETH": 0.0})
    st.session_state.indicadores_activados = data.get("indicadores_activados", {"BTC": False, "ETH": False})
    st.session_state.modo_solo_senales = data.get("modo_solo_senales", False)
    
    st.session_state.rendimiento = data.get("rendimiento", {
        "BTC": {"ganadas": 0, "perdidas": 0, "total": 0, "ultimas_10": []},
        "ETH": {"ganadas": 0, "perdidas": 0, "total": 0, "ultimas_10": []}
    })
    st.session_state.confianza = data.get("confianza", {"BTC": 50, "ETH": 50})
    st.session_state.tendencia = data.get("tendencia", {"BTC": "NEUTRAL", "ETH": "NEUTRAL"})
    st.session_state.historial_operaciones = data.get("historial_operaciones", [])
    st.session_state.modo_aprendizaje = data.get("modo_aprendizaje", True)
    st.session_state.onchain_cache = data.get("onchain_cache", {
        "BTC": {"valor": None, "timestamp": 0},
        "ETH": {"valor": None, "timestamp": 0}
    })
    
    ph = data.get("price_history", {"BTC": [], "ETH": []})
    st.session_state.price_history = {k: deque(v, maxlen=200) for k, v in ph.items()}

# ==================== API KEY DE ETHERSCAN (desde st.secrets) ====================
try:
    ETHERSCAN_API_KEY = st.secrets["G1WH2NDN3YBMAW8FQ3ICK5E3XKY5A3X8UZ"]
    print("✅ ETHERSCAN_API_KEY cargada correctamente desde st.secrets")
except:
    ETHERSCAN_API_KEY = None
    print("⚠️ No se encontró ETHERSCAN_API_KEY en st.secrets. ETH on-chain usará placeholder.")

# ==================== FUNCIONES DE APRENDIZAJE ====================
def analizar_tendencia(historial, periodo=20):
    if len(historial) < periodo:
        return "NEUTRAL"
    datos = list(historial)[-periodo:]
    inicio = datos[0]
    final = datos[-1]
    cambio = (final - inicio) / inicio * 100
    volatilidad = 0
    for i in range(1, len(datos)):
        volatilidad += abs((datos[i] - datos[i-1]) / datos[i-1] * 100)
    volatilidad = volatilidad / len(datos)
    if cambio > 1.5 and volatilidad < 2:
        return "ALCISTA"
    elif cambio < -1.5 and volatilidad < 2:
        return "BAJISTA"
    elif volatilidad > 2:
        return "VOLATIL"
    else:
        return "LATERAL"

def ajustar_confianza(sym, resultado, monto):
    confianza_actual = st.session_state.confianza[sym]
    if resultado > 0:
        confianza_actual = min(100, confianza_actual + 3)
    else:
        confianza_actual = max(0, confianza_actual - 5)
    st.session_state.confianza[sym] = confianza_actual
    return confianza_actual

def evaluar_rendimiento(sym):
    rend = st.session_state.rendimiento[sym]
    total = rend["total"]
    if total < 5:
        return {"accion": "MANTENER", "mensaje": "Pocas operaciones para evaluar"}
    ganadas = rend["ganadas"]
    ratio = ganadas / total
    if ratio > 0.6:
        return {"accion": "AUMENTAR_RIESGO", "mensaje": f"Rendimiento excelente ({ratio*100:.0f}% ganadas)", "sugerencia": "Subir TP y umbral"}
    elif ratio < 0.4:
        return {"accion": "REDUCIR_RIESGO", "mensaje": f"Rendimiento bajo ({ratio*100:.0f}% ganadas)", "sugerencia": "Bajar TP y umbral"}
    else:
        return {"accion": "MANTENER", "mensaje": f"Rendimiento estable ({ratio*100:.0f}% ganadas)", "sugerencia": "Mantener parámetros"}

def obtener_senal_con_criterio(sym, precio, senal_base, razon_base, confianza):
    if not st.session_state.modo_aprendizaje:
        return senal_base, razon_base
    if confianza < 30:
        if senal_base == "BUY" and "Caída" in razon_base:
            return "HOLD", f"Confianza baja ({confianza}%), esperando confirmación"
        elif senal_base == "SELL" and "Take Profit" in razon_base:
            return "SELL", f"Venta por TP (confianza baja {confianza}%)"
    elif confianza > 70:
        if senal_base == "BUY" and "Caída" in razon_base:
            return "BUY", f"Compra por caída (confianza alta {confianza}%)"
    return senal_base, razon_base

# ==================== DATOS ON-CHAIN CON CACHÉ (VERSIÓN CORREGIDA) ====================
def get_onchain_volume(symbol="BTC"):
    now = time.time()
    cache = st.session_state.onchain_cache.get(symbol, {"valor": None, "timestamp": 0})
    
    if cache["valor"] is not None and (now - cache["timestamp"]) < 60:
        return cache["valor"]
    
    if symbol == "BTC":
        try:
            url = "https://blockchain.info/charts/transaction-volume?timespan=1day&format=json"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                volume = data['values'][-1]['y'] / 1e6
                st.session_state.onchain_cache[symbol] = {"valor": volume, "timestamp": now}
                st.caption(f"🔹 BTC volumen actualizado: {volume:.2f}M")
                return volume
            else:
                st.warning(f"⚠️ Error al obtener BTC: código {response.status_code}")
                return cache["valor"] if cache["valor"] is not None else None
        except Exception as e:
            st.error(f"❌ Error en BTC: {e}")
            return cache["valor"] if cache["valor"] is not None else None

    elif symbol == "ETH":
        # Si no hay API Key, usar placeholder sin llamar a Etherscan
        if not ETHERSCAN_API_KEY:
            st.warning("⚠️ ETHERSCAN_API_KEY no configurada. Usando placeholder para ETH.")
            volume = 1.0
            st.session_state.onchain_cache[symbol] = {"valor": volume, "timestamp": now}
            return volume
        
        try:
            url = f"https://api.etherscan.io/api?module=stats&action=ethdailytx&apikey={ETHERSCAN_API_KEY}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data["status"] == "1":
                    result = data["result"]
                    if result and len(result) > 0:
                        last_day = result[-1]
                        transactions = int(last_day.get("transactionCount", 0))
                        volume = transactions / 1_000_000
                        st.session_state.onchain_cache[symbol] = {"valor": volume, "timestamp": now}
                        st.caption(f"🔹 ETH volumen actualizado: {volume:.2f}M transacciones")
                        return volume
                    else:
                        st.warning("⚠️ Etherscan devolvió resultado vacío")
                        return cache["valor"] if cache["valor"] is not None else None
                else:
                    st.warning(f"⚠️ Etherscan error: {data.get('message', 'desconocido')}")
                    return cache["valor"] if cache["valor"] is not None else None
            else:
                st.warning(f"⚠️ Error al consultar Etherscan: código {response.status_code}")
                return cache["valor"] if cache["valor"] is not None else None
        except Exception as e:
            st.error(f"❌ Error en ETH: {e}")
            return cache["valor"] if cache["valor"] is not None else None
    else:
        return None

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
st.set_page_config(page_title="Bot Inteligente + On-Chain", layout="wide")

if "umbral_caida" not in st.session_state:
    init_new_user_state()

st.title("🧠 Bot Inteligente + Datos On-Chain (BTC y ETH)")

st.sidebar.header("⚙️ Configuración Principal")
valor_umbral = min(50.0, float(st.session_state.umbral_caida))
umbral_caida = st.sidebar.number_input("Caída para comprar (scalping) (%)", min_value=0.001, max_value=50.0, step=0.001, value=valor_umbral)

valor_tp = min(50.0, float(st.session_state.take_profit))
take_profit = st.sidebar.number_input("Take Profit scalping (%)", min_value=0.01, max_value=50.0, step=0.01, value=valor_tp)

stop_loss = st.sidebar.number_input("Stop Loss (%)", min_value=0.5, max_value=20.0, value=float(st.session_state.stop_loss), step=0.5)
trailing = st.sidebar.number_input("Trailing Stop (%)", min_value=0.2, max_value=5.0, value=float(st.session_state.trailing), step=0.1)

valor_umbral_ind_activ = min(20.0, float(st.session_state.umbral_indicadores_activacion))
umbral_indicadores_activacion = st.sidebar.number_input("Activar indicadores a partir de ±(%)", min_value=0.5, max_value=20.0, step=0.1, value=valor_umbral_ind_activ)

st.sidebar.header("🧠 Modo Aprendizaje")
modo_aprendizaje = st.sidebar.checkbox("✅ Modo aprendizaje activado", value=st.session_state.modo_aprendizaje)
st.session_state.modo_aprendizaje = modo_aprendizaje

st.sidebar.header("🧠 Indicadores")
expert_score = st.sidebar.slider("Puntaje de tendencia", 0, 100, st.session_state.expert_score, 5)
rsi_os = st.sidebar.number_input("RSI sobreventa", min_value=20, max_value=40, value=int(st.session_state.rsi_os), step=1)
rsi_ob = st.sidebar.number_input("RSI sobrecompra", min_value=70, max_value=90, value=int(st.session_state.rsi_ob), step=1)
ema_fast = st.sidebar.number_input("EMA rápida (periodos)", min_value=3, max_value=20, value=int(st.session_state.ema_fast), step=1)
ema_slow = st.sidebar.number_input("EMA lenta (periodos)", min_value=10, max_value=50, value=int(st.session_state.ema_slow), step=1)

st.sidebar.header("📡 Modo de operación")
modo_solo_senales = st.sidebar.checkbox("🔇 Modo solo señales (no ejecutar órdenes)", value=st.session_state.modo_solo_senales)
st.session_state.modo_solo_senales = modo_solo_senales

st.sidebar.subheader("💰 Cartera")
saldo_placeholder = st.sidebar.empty()
total_placeholder = st.sidebar.empty()
ops_placeholder = st.sidebar.empty()

if st.sidebar.button("Reiniciar simulación"):
    init_new_user_state()
    save_data()
    st.rerun()
if st.sidebar.button("📢 Prueba Telegram"):
    send_telegram("🧠 Bot con On-Chain activo")
    st.success("Enviado")

st.session_state.umbral_caida = umbral_caida
st.session_state.take_profit = take_profit
st.session_state.stop_loss = stop_loss
st.session_state.trailing = trailing
st.session_state.umbral_indicadores_activacion = umbral_indicadores_activacion
st.session_state.expert_score = expert_score
st.session_state.rsi_os = rsi_os
st.session_state.rsi_ob = rsi_ob
st.session_state.ema_fast = ema_fast
st.session_state.ema_slow = ema_slow

tabla_placeholder = st.empty()
info_placeholder = st.empty()
historial_placeholder = st.empty()
estado_placeholder = st.empty()

def send_signal_telegram(sym, tipo, precio, razon, ejecutado=False, monto=0, cantidad=0, modo="scalping", confianza=50, volumen_onchain=None):
    try:
        estado = "✅ EJECUTADA" if ejecutado else "⚠️ NO EJECUTADA"
        if ejecutado:
            msg = (f"📢 SEÑAL {estado} - {tipo} {sym}\n"
                   f"Modo: {modo}\n"
                   f"Confianza: {confianza}%\n"
                   f"Volumen on-chain: {volumen_onchain:.2f}M {sym}\n"
                   f"Monto: ${monto:.0f}\n"
                   f"Cantidad: {cantidad:.6f}\n"
                   f"Precio: ${precio:,.0f}\n"
                   f"Razón: {razon}\n"
                   f"Saldo: ${st.session_state.balance:.2f}")
        else:
            msg = (f"📢 SEÑAL {estado} - {tipo} {sym}\n"
                   f"Modo: {modo}\n"
                   f"Confianza: {confianza}%\n"
                   f"Volumen on-chain: {volumen_onchain if volumen_onchain else 'N/A'}\n"
                   f"Precio: ${precio:,.0f}\n"
                   f"Razón: {razon}\n"
                   f"Saldo: ${st.session_state.balance:.2f}\n"
                   f"Posición {sym}: {st.session_state.positions[sym]:.6f}")
            if st.session_state.modo_solo_senales:
                msg += "\n🔇 Modo solo señales activado (no ejecutado)"
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

    cambio_btc = (btc - st.session_state.ref_price["BTC"]) / st.session_state.ref_price["BTC"] * 100
    cambio_eth = (eth - st.session_state.ref_price["ETH"]) / st.session_state.ref_price["ETH"] * 100

    st.session_state.tendencia["BTC"] = analizar_tendencia(st.session_state.price_history["BTC"])
    st.session_state.tendencia["ETH"] = analizar_tendencia(st.session_state.price_history["ETH"])

    if abs(cambio_btc) >= st.session_state.umbral_indicadores_activacion:
        st.session_state.indicadores_activados["BTC"] = True
    else:
        st.session_state.indicadores_activados["BTC"] = False

    if abs(cambio_eth) >= st.session_state.umbral_indicadores_activacion:
        st.session_state.indicadores_activados["ETH"] = True
    else:
        st.session_state.indicadores_activados["ETH"] = False

    # Consultar on-chain cada 3 ciclos
    onchain_vol_btc = None
    onchain_vol_eth = None
    if st.session_state.cycle % 3 == 0:
        onchain_vol_btc = get_onchain_volume("BTC")
        onchain_vol_eth = get_onchain_volume("ETH")

    tabla_placeholder.subheader("📊 Señales + Datos On-Chain")
    tabla_placeholder.table({
        "Moneda": ["Bitcoin", "Ethereum"],
        "Precio MXN": [f"${btc:,.0f}", f"${eth:,.0f}"],
        "Cambio desde inicio": [f"{cambio_btc:+.2f}%", f"{cambio_eth:+.2f}%"],
        "Tendencia": [st.session_state.tendencia["BTC"], st.session_state.tendencia["ETH"]],
        "Confianza": [f"{st.session_state.confianza['BTC']}%", f"{st.session_state.confianza['ETH']}%"],
        "Volumen On-Chain (24h)": [
            f"{onchain_vol_btc:.2f}M" if onchain_vol_btc else "N/A",
            f"{onchain_vol_eth:.2f}M" if onchain_vol_eth else "N/A"
        ],
        "Modo": [
            "📉 Scalping" if not st.session_state.indicadores_activados["BTC"] else "🧠 Indicadores",
            "📉 Scalping" if not st.session_state.indicadores_activados["ETH"] else "🧠 Indicadores"
        ]
    })
    info_placeholder.caption(f"Ciclo: {st.session_state.cycle} | Caída scalping: {st.session_state.umbral_caida}% | TP: {st.session_state.take_profit}% | SL: {st.session_state.stop_loss}% | Trailing: {st.session_state.trailing}% | Fear & Greed: {fng_value}/100 ({fng_label}) | Aprendizaje: {'✅' if st.session_state.modo_aprendizaje else '❌'}")

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

    if st.session_state.cycle % 5 == 0 and st.session_state.modo_aprendizaje:
        for sym in ["BTC", "ETH"]:
            eval_rend = evaluar_rendimiento(sym)
            if eval_rend["accion"] == "AUMENTAR_RIESGO":
                st.session_state.umbral_caida = min(0.05, st.session_state.umbral_caida * 1.2)
                st.session_state.take_profit = min(0.10, st.session_state.take_profit * 1.1)
                st.session_state.confianza[sym] = min(100, st.session_state.confianza[sym] + 5)
            elif eval_rend["accion"] == "REDUCIR_RIESGO":
                st.session_state.umbral_caida = max(0.001, st.session_state.umbral_caida * 0.8)
                st.session_state.take_profit = max(0.01, st.session_state.take_profit * 0.9)
                st.session_state.confianza[sym] = max(0, st.session_state.confianza[sym] - 5)

    for sym, precio in [("BTC", btc), ("ETH", eth)]:
        pos = st.session_state.positions.get(sym, 0)
        entry = st.session_state.entry_price.get(sym, 0)
        ref = st.session_state.ref_price.get(sym, 0)
        
        caida_actual = (ref - precio) / ref * 100 if ref != 0 else 0
        ganancia = (precio - entry) / entry * 100 if entry != 0 else 0
        confianza = st.session_state.confianza.get(sym, 50)
        
        razon = ""
        accion = None
        modo_actual = "Indicadores" if st.session_state.indicadores_activados[sym] else "Scalping"

        volumen_onchain = None
        if sym == "BTC":
            volumen_onchain = get_onchain_volume("BTC")
        elif sym == "ETH":
            volumen_onchain = get_onchain_volume("ETH")

        if st.session_state.indicadores_activados[sym]:
            hist = list(st.session_state.price_history[sym])
            if len(hist) >= max(st.session_state.ema_slow, 15):
                senal_indicadores, rsi_val = get_enhanced_signal(
                    hist, st.session_state.rsi_os, st.session_state.rsi_ob,
                    st.session_state.ema_fast, st.session_state.ema_slow,
                    fng_value, st.session_state.expert_score
                )
            else:
                senal_indicadores = "HOLD"
                rsi_val = 50
            
            if pos == 0 and senal_indicadores == "BUY":
                accion = "BUY"
                razon = f"Indicadores COMPRA (RSI:{rsi_val:.0f})"
            elif pos > 0 and senal_indicadores == "SELL":
                accion = "SELL"
                razon = f"Indicadores VENTA (RSI:{rsi_val:.0f})"
            else:
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
        else:
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
            
            if accion is None and pos == 0:
                if caida_actual >= st.session_state.umbral_caida:
                    if confianza >= 30 or not st.session_state.modo_aprendizaje:
                        if volumen_onchain is not None and volumen_onchain > 0.5:
                            accion = "BUY"
                            razon = f"Caída del {caida_actual:.4f}% (Volumen on-chain alto: {volumen_onchain:.2f}M)"
                        else:
                            razon = f"Caída del {caida_actual:.4f}% (Volumen on-chain bajo {volumen_onchain})"
                    else:
                        razon = f"Caída del {caida_actual:.4f}% (ignorada: confianza baja {confianza}%)"

        if accion:
            accion_con_criterio, razon_con_criterio = obtener_senal_con_criterio(
                sym, precio, accion, razon, confianza
            )
            if accion_con_criterio != accion:
                accion = accion_con_criterio
                razon = razon_con_criterio

        last_act = st.session_state.last_action.get(sym)
        if accion and accion != last_act:
            ejecutado = False
            if not st.session_state.modo_solo_senales:
                if accion == "BUY":
                    cantidad_compras = 4
                    monto_por_compra = 100.0
                    compras_ejecutadas = 0
                    
                    if st.session_state.balance >= monto_por_compra:
                        if st.session_state.balance < cantidad_compras * monto_por_compra:
                            cantidad_compras = int(st.session_state.balance // monto_por_compra)
                            if cantidad_compras == 0:
                                st.warning("Saldo insuficiente para $100 MXN")
                        
                        for i in range(cantidad_compras):
                            if st.session_state.balance >= monto_por_compra:
                                com = monto_por_compra * 0.001
                                qty = (monto_por_compra - com) / precio
                                st.session_state.balance -= monto_por_compra
                                st.session_state.positions[sym] += qty
                                if st.session_state.entry_price[sym] == 0:
                                    st.session_state.entry_price[sym] = precio
                                st.session_state.highest_price[sym] = precio
                                st.session_state.daily_trades += 1
                                compras_ejecutadas += 1
                                
                                msg = (f"🟢 COMPRA {sym} #{i+1}\n"
                                       f"Modo: {modo_actual}\n"
                                       f"Confianza: {confianza}%\n"
                                       f"Volumen on-chain: {volumen_onchain:.2f}M {sym}\n"
                                       f"Monto: ${monto_por_compra:.0f}\n"
                                       f"Cantidad: {qty:.6f}\n"
                                       f"Precio: ${precio:,.0f}\n"
                                       f"Saldo restante: ${st.session_state.balance:.2f}")
                                send_telegram(msg)
                                st.session_state.trades.append((datetime.now(), msg))
                                save_data()
                            else:
                                break
                        
                        if compras_ejecutadas > 0:
                            ejecutado = True
                            st.session_state.last_action[sym] = accion
                            st.success(f"✅ {compras_ejecutadas} compras de {sym} por ${monto_por_compra:.0f} c/u")
                        else:
                            st.warning("Saldo insuficiente")
                    else:
                        st.warning(f"⚠️ Saldo insuficiente para la compra mínima de $100 en {sym}")
                        
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
                    
                    resultado_operacion = net - (monto_por_compra * compras_ejecutadas if 'compras_ejecutadas' in locals() and compras_ejecutadas > 0 else 0)
                    if resultado_operacion > 0:
                        st.session_state.rendimiento[sym]["ganadas"] += 1
                    else:
                        st.session_state.rendimiento[sym]["perdidas"] += 1
                    st.session_state.rendimiento[sym]["total"] += 1
                    st.session_state.rendimiento[sym]["ultimas_10"].append(resultado_operacion)
                    if len(st.session_state.rendimiento[sym]["ultimas_10"]) > 10:
                        st.session_state.rendimiento[sym]["ultimas_10"].pop(0)
                    
                    ajustar_confianza(sym, resultado_operacion, monto_por_compra * compras_ejecutadas if 'compras_ejecutadas' in locals() and compras_ejecutadas > 0 else 0)
                    
                    msg = (f"🔴 VENTA {sym}\n"
                           f"Modo: {modo_actual}\n"
                           f"Confianza: {confianza}%\n"
                           f"Volumen on-chain: {volumen_onchain:.2f}M {sym}\n"
                           f"Cantidad: {qty:.6f}\n"
                           f"Precio: ${precio:,.0f}\n"
                           f"Neto: ${net:.2f}\n"
                           f"Motivo: {razon}")
                    send_telegram(msg)
                    st.session_state.trades.append((datetime.now(), msg))
                    save_data()
            else:
                pass
            
            if not ejecutado:
                send_signal_telegram(sym, accion, precio, razon, ejecutado=False, modo=modo_actual, confianza=confianza, volumen_onchain=volumen_onchain)

    if st.session_state.cycle % 10 == 0:
        save_data()

    estado_placeholder.info(f"🔹 Indicadores: BTC={st.session_state.indicadores_activados['BTC']} | ETH={st.session_state.indicadores_activados['ETH']} | Tendencia: BTC={st.session_state.tendencia['BTC']} | ETH={st.session_state.tendencia['ETH']}")
    if st.session_state.modo_solo_senales:
        estado_placeholder.info(f"🔇 Modo solo señales ACTIVADO - No se ejecutan órdenes")

    time.sleep(30)
