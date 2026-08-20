import streamlit as st
import requests
import time
import json
import os
import statistics
from datetime import datetime, timedelta
from collections import deque
import yfinance as yf

# ==================== ARCHIVO LOCAL PARA GUARDAR DATOS ====================
DATA_FILE = "data.json"
BACKUP_FILE = "data_backup.json"

def load_data():
    """Carga datos con manejo de errores y respaldo automático."""
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "balance" in data and "positions" in data and "cycle" in data:
                    return data
                else:
                    if os.path.exists(BACKUP_FILE):
                        with open(BACKUP_FILE, "r", encoding="utf-8") as bf:
                            return json.load(bf)
                    else:
                        return None
        return None
    except (json.JSONDecodeError, KeyError, ValueError):
        if os.path.exists(BACKUP_FILE):
            try:
                with open(BACKUP_FILE, "r", encoding="utf-8") as bf:
                    return json.load(bf)
            except:
                return None
        return None

def save_data():
    """Guarda datos con respaldo automático."""
    try:
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
            "onchain_cache": st.session_state.onchain_cache,
            "historical_trend": st.session_state.historical_trend
        }
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        with open(BACKUP_FILE, "w", encoding="utf-8") as bf:
            json.dump(data, bf, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error al guardar datos: {e}")

def init_new_user_state():
    """Inicializa el estado por defecto CON PARÁMETROS PARA MÁS OPERACIONES."""
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
    
    # ===== PARÁMETROS OPTIMIZADOS PARA MÁS OPERACIONES =====
    st.session_state.umbral_caida = 0.005          # Caída mínima para comprar
    st.session_state.stop_loss = 1.5               # Stop Loss fijo
    st.session_state.take_profit = 0.02            # Take Profit rápido
    st.session_state.trailing = 0.5                # Trailing Stop
    st.session_state.umbral_indicadores_activacion = 0.5  # Activa indicadores al ±0.5%
    
    st.session_state.expert_score = 30
    st.session_state.rsi_os = 30
    st.session_state.rsi_ob = 80
    st.session_state.ema_fast = 5
    st.session_state.ema_slow = 12
    st.session_state.sl_triggered = {"BTC": False, "ETH": False}
    st.session_state.sl_low_price = {"BTC": 0.0, "ETH": 0.0}
    st.session_state.indicadores_activados = {"BTC": False, "ETH": False}
    st.session_state.modo_solo_senales = False      # ¡Ejecuta órdenes!
    
    st.session_state.rendimiento = {
        "BTC": {"ganadas": 0, "perdidas": 0, "total": 0, "ultimas_10": []},
        "ETH": {"ganadas": 0, "perdidas": 0, "total": 0, "ultimas_10": []}
    }
    st.session_state.confianza = {"BTC": 50, "ETH": 50}
    st.session_state.tendencia = {"BTC": "NEUTRAL", "ETH": "NEUTRAL"}
    st.session_state.historial_operaciones = []
    st.session_state.modo_aprendizaje = False      # Desactivado para que no suba los umbrales
    st.session_state.onchain_cache = {
        "BTC": {"valor": None, "timestamp": 0},
        "ETH": {"valor": None, "timestamp": 0}
    }
    st.session_state.historical_trend = {
        "BTC": {},
        "ETH": {}
    }

def restore_from_file():
    """Restaura el estado desde el archivo."""
    data = load_data()
    if data is None:
        init_new_user_state()
        return
    
    try:
        trades = []
        for ts, msg in data.get("trades", []):
            if isinstance(ts, str):
                trades.append((datetime.fromisoformat(ts), msg))
            else:
                trades.append((ts, msg))
        
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
        st.session_state.umbral_indicadores_activacion = data.get("umbral_indicadores_activacion", 0.5)
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
        st.session_state.modo_aprendizaje = data.get("modo_aprendizaje", False)
        st.session_state.onchain_cache = data.get("onchain_cache", {
            "BTC": {"valor": None, "timestamp": 0},
            "ETH": {"valor": None, "timestamp": 0}
        })
        st.session_state.historical_trend = data.get("historical_trend", {
            "BTC": {},
            "ETH": {}
        })
        
        ph = data.get("price_history", {"BTC": [], "ETH": []})
        st.session_state.price_history = {k: deque(v, maxlen=200) for k, v in ph.items()}
    except Exception as e:
        print(f"Error al restaurar datos: {e}")
        init_new_user_state()

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

# ==================== INICIALIZAR ESTADO ====================
if "data_loaded" not in st.session_state:
    restore_from_file()
    st.session_state.data_loaded = True
    # ==================== FUNCIONES DE APRENDIZAJE Y ANÁLISIS ====================
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
    if confianza < 30:
        if senal_base == "BUY" and "Caída" in razon_base:
            return "HOLD", f"Confianza baja ({confianza}%), esperando confirmación"
        elif senal_base == "SELL" and "Take Profit" in razon_base:
            return "SELL", f"Venta por TP (confianza baja {confianza}%)"
    elif confianza > 70:
        if senal_base == "BUY" and "Caída" in razon_base:
            return "BUY", f"Compra por caída (confianza alta {confianza}%)"
    return senal_base, razon_base
    # ==================== DATOS HISTÓRICOS DE 30 DÍAS ====================
def get_historical_trend(symbol="BTC", days=30):
    try:
        if symbol == "BTC":
            coin_id = "bitcoin"
        elif symbol == "ETH":
            coin_id = "ethereum"
        else:
            return None
        
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?vs_currency=usd&days={days}"
        response = requests.get(url, timeout=5)
        if response.status_code != 200:
            return None
        
        data = response.json()
        prices = [p[1] for p in data.get("prices", [])]
        if len(prices) < 2:
            return None
        
        precio_actual = prices[-1]
        precio_hace_30d = prices[0]
        cambio_porcentual = (precio_actual - precio_hace_30d) / precio_hace_30d * 100
        
        sma_30 = sum(prices[-30:]) / 30 if len(prices) >= 30 else sum(prices) / len(prices)
        if precio_actual > sma_30 * 1.01:
            tendencia = "ALCISTA"
        elif precio_actual < sma_30 * 0.99:
            tendencia = "BAJISTA"
        else:
            tendencia = "LATERAL"
        
        retornos = []
        for i in range(1, len(prices)):
            retorno = (prices[i] - prices[i-1]) / prices[i-1]
            retornos.append(retorno)
        volatilidad = statistics.stdev(retornos) if len(retornos) > 1 else 0
        
        return {
            "cambio_porcentual": cambio_porcentual,
            "tendencia": tendencia,
            "volatilidad": volatilidad,
            "maximo": max(prices),
            "minimo": min(prices),
            "precio_actual": precio_actual,
            "sma_30": sma_30
        }
    except:
        return None

# ==================== DATOS ON-CHAIN CON COINGECKO ====================
def get_onchain_volume(symbol="BTC"):
    now = time.time()
    cache = st.session_state.onchain_cache.get(symbol, {"valor": None, "timestamp": 0})
    if cache["valor"] is not None and (now - cache["timestamp"]) < 60:
        return cache["valor"]
    
    try:
        if symbol == "BTC":
            url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=1"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                volumes = data.get("total_volumes", [])
                if volumes:
                    volume_usd = volumes[-1][1] / 1e9
                    st.session_state.onchain_cache[symbol] = {"valor": volume_usd, "timestamp": now}
                    return volume_usd
                else:
                    volume = 0.5
                    st.session_state.onchain_cache[symbol] = {"valor": volume, "timestamp": now}
                    return volume
            else:
                volume = 0.5
                st.session_state.onchain_cache[symbol] = {"valor": volume, "timestamp": now}
                return volume
        elif symbol == "ETH":
            url = "https://api.coingecko.com/api/v3/coins/ethereum/market_chart?vs_currency=usd&days=1"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                volumes = data.get("total_volumes", [])
                if volumes:
                    volume_usd = volumes[-1][1] / 1e9
                    st.session_state.onchain_cache[symbol] = {"valor": volume_usd, "timestamp": now}
                    return volume_usd
                else:
                    volume = 0.5
                    st.session_state.onchain_cache[symbol] = {"valor": volume, "timestamp": now}
                    return volume
            else:
                volume = 0.5
                st.session_state.onchain_cache[symbol] = {"valor": volume, "timestamp": now}
                return volume
        else:
            return None
    except:
        volume = 0.5
        st.session_state.onchain_cache[symbol] = {"valor": volume, "timestamp": now}
        return volume

# ==================== INDICADORES TÉCNICOS ====================
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
    # ==================== INTERFAZ PRINCIPAL ====================
st.set_page_config(page_title="Bot Scalping Extremo + Tendencia 30d", layout="wide")

# ===== INICIALIZACIÓN ROBUSTA DE ESTADO =====
required_vars = {
    "last_price": {"BTC": 0.0, "ETH": 0.0},
    "ref_price": {"BTC": 0.0, "ETH": 0.0},
    "entry_price": {"BTC": 0.0, "ETH": 0.0},
    "highest_price": {"BTC": 0.0, "ETH": 0.0},
    "positions": {"BTC": 0.0, "ETH": 0.0},
    "balance": 1000.0,
    "daily_trades": 0,
    "trades": [],
    "last_action": {"BTC": None, "ETH": None},
    "cycle": 0,
    "price_history": {"BTC": deque(maxlen=200), "ETH": deque(maxlen=200)},
    "umbral_caida": 0.005,
    "take_profit": 0.02,
    "stop_loss": 1.5,
    "trailing": 0.5,
    "umbral_indicadores_activacion": 0.5,
    "expert_score": 30,
    "rsi_os": 30,
    "rsi_ob": 80,
    "ema_fast": 5,
    "ema_slow": 12,
    "sl_triggered": {"BTC": False, "ETH": False},
    "sl_low_price": {"BTC": 0.0, "ETH": 0.0},
    "indicadores_activados": {"BTC": False, "ETH": False},
    "modo_solo_senales": False,
    "modo_aprendizaje": False,
    "rendimiento": {
        "BTC": {"ganadas": 0, "perdidas": 0, "total": 0, "ultimas_10": []},
        "ETH": {"ganadas": 0, "perdidas": 0, "total": 0, "ultimas_10": []}
    },
    "confianza": {"BTC": 50, "ETH": 50},
    "tendencia": {"BTC": "NEUTRAL", "ETH": "NEUTRAL"},
    "historial_operaciones": [],
    "onchain_cache": {
        "BTC": {"valor": None, "timestamp": 0},
        "ETH": {"valor": None, "timestamp": 0}
    },
    "historical_trend": {"BTC": {}, "ETH": {}}
}

for var_name, default_value in required_vars.items():
    if var_name not in st.session_state:
        st.session_state[var_name] = default_value

# Cargar datos guardados (si existen)
if "data_loaded" not in st.session_state:
    restore_from_file()
    st.session_state.data_loaded = True

st.title("🧠 Scalping Extremo + Volumen + Tendencia 30d")

# ===== SIDEBAR =====
st.sidebar.header("⚙️ Configuración Principal")
umbral_caida = st.sidebar.number_input("Caída para comprar (scalping) (%)", min_value=0.001, max_value=50.0, step=0.001, value=float(st.session_state.umbral_caida))
take_profit = st.sidebar.number_input("Take Profit scalping (%)", min_value=0.01, max_value=50.0, step=0.01, value=float(st.session_state.take_profit))
stop_loss = st.sidebar.number_input("Stop Loss (%)", min_value=0.5, max_value=20.0, value=float(st.session_state.stop_loss), step=0.5)
trailing = st.sidebar.number_input("Trailing Stop (%)", min_value=0.2, max_value=5.0, value=float(st.session_state.trailing), step=0.1)
umbral_indicadores_activacion = st.sidebar.number_input("Activar indicadores a partir de ±(%)", min_value=0.1, max_value=20.0, step=0.1, value=float(st.session_state.umbral_indicadores_activacion))

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
    send_telegram("🧠 Bot Scalping Extremo activo")
    st.success("Enviado")

# ===== BOTONES DE CONTROL MANUAL =====
st.sidebar.markdown("---")
st.sidebar.markdown("**🎮 Control Manual**")

# Botón Vender TODO
if st.sidebar.button("💸 Vender TODO (forzar venta)"):
    try:
        btc_price = get_bitso_price("btc_mxn")
        eth_price = get_bitso_price("eth_mxn")
        
        if btc_price is None or eth_price is None:
            st.sidebar.error("❌ Error al obtener precios.")
        else:
            vendido = False
            
            if st.session_state.positions.get("BTC", 0) > 0:
                qty = st.session_state.positions["BTC"]
                gross = qty * btc_price
                com = gross * 0.001
                net = gross - com
                st.session_state.balance += net
                st.session_state.positions["BTC"] = 0
                st.session_state.entry_price["BTC"] = 0
                st.session_state.highest_price["BTC"] = 0
                st.session_state.daily_trades += 1
                msg = f"🔴 VENTA FORZADA BTC | Cantidad: {qty:.6f} | Precio: ${btc_price:,.0f} | Neto: ${net:.2f}"
                send_telegram(msg)
                st.session_state.trades.append((datetime.now(), msg))
                vendido = True
            
            if st.session_state.positions.get("ETH", 0) > 0:
                qty = st.session_state.positions["ETH"]
                gross = qty * eth_price
                com = gross * 0.001
                net = gross - com
                st.session_state.balance += net
                st.session_state.positions["ETH"] = 0
                st.session_state.entry_price["ETH"] = 0
                st.session_state.highest_price["ETH"] = 0
                st.session_state.daily_trades += 1
                msg = f"🔴 VENTA FORZADA ETH | Cantidad: {qty:.6f} | Precio: ${eth_price:,.0f} | Neto: ${net:.2f}"
                send_telegram(msg)
                st.session_state.trades.append((datetime.now(), msg))
                vendido = True
            
            if vendido:
                st.session_state.last_action = {"BTC": None, "ETH": None}
                save_data()
                st.sidebar.success("✅ Posiciones vendidas correctamente.")
                st.rerun()
            else:
                st.sidebar.info("ℹ️ No hay posiciones abiertas para vender.")
    except Exception as e:
        st.sidebar.error(f"❌ Error: {e}")

# Botón Comprar BTC
if st.sidebar.button("🟢 Comprar BTC AHORA"):
    try:
        if st.session_state.positions.get("BTC", 0) > 0:
            st.sidebar.warning("⚠️ Ya tienes posición en BTC.")
        else:
            precio = get_bitso_price("btc_mxn")
            if precio is None:
                st.sidebar.error("❌ Error al obtener precio de BTC.")
            else:
                cantidad_compras = 4
                monto_por_compra = 100.0
                compras_ejecutadas = 0
                monto_total = cantidad_compras * monto_por_compra
                
                if st.session_state.balance < monto_por_compra:
                    st.sidebar.warning("⚠️ Saldo insuficiente.")
                else:
                    if st.session_state.balance < monto_total:
                        cantidad_compras = int(st.session_state.balance // monto_por_compra)
                        if cantidad_compras == 0:
                            st.sidebar.warning("⚠️ Saldo insuficiente.")
                    
                    for i in range(cantidad_compras):
                        if st.session_state.balance >= monto_por_compra:
                            com = monto_por_compra * 0.001
                            qty = (monto_por_compra - com) / precio
                            st.session_state.balance -= monto_por_compra
                            st.session_state.positions["BTC"] += qty
                            if st.session_state.entry_price["BTC"] == 0:
                                st.session_state.entry_price["BTC"] = precio
                            st.session_state.highest_price["BTC"] = precio
                            st.session_state.daily_trades += 1
                            compras_ejecutadas += 1
                        else:
                            break
                    
                    if compras_ejecutadas > 0:
                        st.session_state.last_action["BTC"] = "BUY"
                        save_data()
                        msg = f"🟢 COMPRA FORZADA BTC | {compras_ejecutadas} compras de ${monto_por_compra:.0f} | Precio: ${precio:,.0f} | Saldo: ${st.session_state.balance:.2f}"
                        send_telegram(msg)
                        st.session_state.trades.append((datetime.now(), msg))
                        st.sidebar.success(f"✅ {compras_ejecutadas} compras de BTC ejecutadas.")
                        st.rerun()
                    else:
                        st.sidebar.warning("⚠️ No se pudo comprar.")
    except Exception as e:
        st.sidebar.error(f"❌ Error: {e}")

# Botón Comprar ETH
if st.sidebar.button("🟢 Comprar ETH AHORA"):
    try:
        if st.session_state.positions.get("ETH", 0) > 0:
            st.sidebar.warning("⚠️ Ya tienes posición en ETH.")
        else:
            precio = get_bitso_price("eth_mxn")
            if precio is None:
                st.sidebar.error("❌ Error al obtener precio de ETH.")
            else:
                cantidad_compras = 4
                monto_por_compra = 100.0
                compras_ejecutadas = 0
                monto_total = cantidad_compras * monto_por_compra
                
                if st.session_state.balance < monto_por_compra:
                    st.sidebar.warning("⚠️ Saldo insuficiente.")
                else:
                    if st.session_state.balance < monto_total:
                        cantidad_compras = int(st.session_state.balance // monto_por_compra)
                        if cantidad_compras == 0:
                            st.sidebar.warning("⚠️ Saldo insuficiente.")
                    
                    for i in range(cantidad_compras):
                        if st.session_state.balance >= monto_por_compra:
                            com = monto_por_compra * 0.001
                            qty = (monto_por_compra - com) / precio
                            st.session_state.balance -= monto_por_compra
                            st.session_state.positions["ETH"] += qty
                            if st.session_state.entry_price["ETH"] == 0:
                                st.session_state.entry_price["ETH"] = precio
                            st.session_state.highest_price["ETH"] = precio
                            st.session_state.daily_trades += 1
                            compras_ejecutadas += 1
                        else:
                            break
                    
                    if compras_ejecutadas > 0:
                        st.session_state.last_action["ETH"] = "BUY"
                        save_data()
                        msg = f"🟢 COMPRA FORZADA ETH | {compras_ejecutadas} compras de ${monto_por_compra:.0f} | Precio: ${precio:,.0f} | Saldo: ${st.session_state.balance:.2f}"
                        send_telegram(msg)
                        st.session_state.trades.append((datetime.now(), msg))
                        st.sidebar.success(f"✅ {compras_ejecutadas} compras de ETH ejecutadas.")
                        st.rerun()
                    else:
                        st.sidebar.warning("⚠️ No se pudo comprar.")
    except Exception as e:
        st.sidebar.error(f"❌ Error: {e}")

# ===== ACTUALIZAR PARÁMETROS =====
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

# ===== CONTENEDORES DINÁMICOS =====
tabla_placeholder = st.empty()
info_placeholder = st.empty()
historial_placeholder = st.empty()
estado_placeholder = st.empty()
# ===== FUNCIÓN PARA ENVIAR SEÑALES POR TELEGRAM =====
def send_signal_telegram(sym, tipo, precio, razon, ejecutado=False, monto=0, cantidad=0, modo="scalping", confianza=50, volumen_onchain=None, cambio_30d=None, tendencia_30d=None):
    try:
        estado = "✅ EJECUTADA" if ejecutado else "⚠️ NO EJECUTADA"
        msg = (f"📢 SEÑAL {estado} - {tipo} {sym}\n"
               f"Modo: {modo}\n"
               f"Confianza: {confianza}%\n"
               f"Volumen 24h: {volumen_onchain:.2f}B USD\n"
               f"Cambio 30d: {cambio_30d:+.2f}%\n"
               f"Tendencia 30d: {tendencia_30d}\n"
               f"Precio: ${precio:,.0f}\n")
        if ejecutado:
            msg += f"Monto: ${monto:.0f}\nCantidad: {cantidad:.6f}\nRazón: {razon}\nSaldo: ${st.session_state.balance:.2f}"
        else:
            msg += f"Razón: {razon}\nSaldo: ${st.session_state.balance:.2f}\nPosición {sym}: {st.session_state.positions[sym]:.6f}"
            if st.session_state.modo_solo_senales:
                msg += "\n🔇 Modo solo señales activado (no ejecutado)"
        send_telegram(msg)
    except:
        pass

# ==================== SEÑALES POR TELEGRAM CON BOTONES ====================
def send_signal_telegram_buttons(sym, tipo, precio, razon, confianza, volumen_onchain, cambio_30d, tendencia_30d):
    """Envía una señal con botones de acción por Telegram."""
    try:
        msg_simple = (f"📢 **SEÑAL {tipo} - {sym}**\n"
                      f"Confianza: {confianza:.1f}%\n"
                      f"Precio: ${precio:,.0f}\n"
                      f"Razón: {razon}\n"
                      f"Volumen: {volumen_onchain:.2f}B USD\n"
                      f"Cambio 30d: {cambio_30d:+.2f}%\n"
                      f"Tendencia 30d: {tendencia_30d}\n\n"
                      f"⚠️ **Para ejecutar esta orden**, ve a la sección '📡 Ejecutar Señales Manuales' en la app.")
        
        send_telegram(msg_simple)
        return True
    except Exception as e:
        print(f"Error enviando señal con botones: {e}")
        return False

# ==================== FÓRMULA AVANZADA DE ANÁLISIS ====================
def analisis_avanzado(sym, precio, fng_value):
    """
    Análisis multi-indicador para determinar si es momento de comprar o vender.
    Retorna: (accion, confianza, razon, detalles)
    """
    pos = st.session_state.positions.get(sym, 0)
    entry = st.session_state.entry_price.get(sym, 0)
    ref = st.session_state.ref_price.get(sym, 0)
    
    # Obtener datos de tendencia 30d
    trend_data = st.session_state.historical_trend.get(sym, {})
    cambio_30d = trend_data.get("cambio_porcentual", 0)
    tendencia_30d = trend_data.get("tendencia", "NEUTRAL")
    
    # Obtener volumen on-chain
    if sym == "BTC":
        volumen_onchain = get_onchain_volume("BTC")
    else:
        volumen_onchain = get_onchain_volume("ETH")
    
    # ===== INDICADORES TÉCNICOS =====
    hist = list(st.session_state.price_history.get(sym, []))
    if len(hist) < 30:
        return "HOLD", 0, "Datos insuficientes", {}
    
    # 1. RSI (momento)
    rsi = compute_rsi(hist, 14)
    rsi_ponderado = 0
    if rsi <= 30:
        rsi_ponderado = 20  # Sobreventa → comprar
    elif rsi >= 70:
        rsi_ponderado = -20  # Sobrecompra → vender
    else:
        rsi_ponderado = (50 - rsi) * 0.5  # Neutro
    
    # 2. EMAs (tendencia)
    ema_f = compute_ema(hist, st.session_state.ema_fast)
    ema_s = compute_ema(hist, st.session_state.ema_slow)
    ema_ponderado = 0
    if ema_f is not None and ema_s is not None:
        if ema_f > ema_s:
            ema_ponderado = 15  # Alcista
        elif ema_f < ema_s:
            ema_ponderado = -15  # Bajista
        # Pendiente de EMA rápida
        if len(hist) > 10:
            ema_prev = compute_ema(hist[:-1], st.session_state.ema_fast)
            if ema_prev is not None and ema_f > ema_prev * 1.001:
                ema_ponderado += 5
            elif ema_prev is not None and ema_f < ema_prev * 0.999:
                ema_ponderado -= 5
    
    # 3. Bandas de Bollinger (sobrecompra/sobreventa extrema)
    bb_ponderado = 0
    if len(hist) >= 20:
        sma_20 = sum(hist[-20:]) / 20
        std_20 = statistics.stdev(hist[-20:]) if len(hist[-20:]) > 1 else 0
        banda_superior = sma_20 + 2 * std_20
        banda_inferior = sma_20 - 2 * std_20
        if precio > banda_superior:
            bb_ponderado = -15  # Sobrecompra extrema
        elif precio < banda_inferior:
            bb_ponderado = 15   # Sobrevendido extremo
    
    # 4. MACD (momento)
    macd_ponderado = 0
    if len(hist) >= 26:
        ema_12 = compute_ema(hist, 12)
        ema_26 = compute_ema(hist, 26)
        if ema_12 is not None and ema_26 is not None:
            macd = ema_12 - ema_26
            # Señal (EMA 9 del MACD)
            if len(hist) >= 35:
                macd_hist = []
                for i in range(26, len(hist)):
                    e12 = compute_ema(hist[:i+1], 12)
                    e26 = compute_ema(hist[:i+1], 26)
                    if e12 is not None and e26 is not None:
                        macd_hist.append(e12 - e26)
                if len(macd_hist) >= 9:
                    signal = sum(macd_hist[-9:]) / 9
                    if macd > signal:
                        macd_ponderado = 10
                    elif macd < signal:
                        macd_ponderado = -10
    
    # 5. Volumen on-chain (confirmación)
    volumen_ponderado = 0
    if volumen_onchain is not None:
        if volumen_onchain > 2.0:  # Alto volumen
            volumen_ponderado = 10
        elif volumen_onchain < 0.5:  # Bajo volumen
            volumen_ponderado = -5
    
    # 6. Tendencia de 30 días (contexto macro)
    tendencia_ponderado = 0
    if tendencia_30d == "ALCISTA":
        tendencia_ponderado = 15
    elif tendencia_30d == "BAJISTA":
        tendencia_ponderado = -15
    if abs(cambio_30d) > 20:
        tendencia_ponderado = tendencia_ponderado * 1.5
    
    # 7. Fear & Greed (sentimiento)
    fng_ponderado = 0
    if fng_value <= 20:
        fng_ponderado = 10  # Miedo extremo → comprar
    elif fng_value >= 80:
        fng_ponderado = -10  # Codicia extrema → vender
    else:
        fng_ponderado = (50 - fng_value) * 0.2
    
    # 8. Volatilidad (ATR)
    atr_ponderado = 0
    if len(hist) >= 14:
        atr = calcular_atr(hist, 14)
        if atr is not None and precio > 0:
            volatilidad_pct = (atr / precio) * 100
            if volatilidad_pct > 3:
                atr_ponderado = -5  # Alta volatilidad → cautela
            elif volatilidad_pct < 1:
                atr_ponderado = 5   # Baja volatilidad → oportunidad
    
    # ===== PUNTUACIÓN TOTAL =====
    puntuacion = (rsi_ponderado + ema_ponderado + bb_ponderado + 
                  macd_ponderado + volumen_ponderado + tendencia_ponderado + 
                  fng_ponderado + atr_ponderado)
    
    # ===== DECISIÓN FINAL =====
    confianza = abs(puntuacion)
    if confianza < 20:
        accion = "HOLD"
        razon = f"Puntuación baja ({confianza:.1f}), esperando confirmación"
    elif puntuacion > 0:
        accion = "BUY"
        razon = f"Señal de compra (puntuación {puntuacion:.1f})"
    else:
        accion = "SELL"
        razon = f"Señal de venta (puntuación {puntuacion:.1f})"
    
    # ===== DETALLES PARA DEPURACIÓN =====
    detalles = {
        "rsi": rsi,
        "ema_ponderado": ema_ponderado,
        "bb_ponderado": bb_ponderado,
        "macd_ponderado": macd_ponderado,
        "volumen_ponderado": volumen_ponderado,
        "tendencia_ponderado": tendencia_ponderado,
        "fng_ponderado": fng_ponderado,
        "atr_ponderado": atr_ponderado,
        "puntuacion": puntuacion,
        "confianza": confianza
    }
    
    return accion, confianza, razon, detalles

def calcular_atr(prices, periodo=14):
    """Average True Range (ATR) para medir volatilidad."""
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
    # ===== BOTONES DE EJECUCIÓN DE SEÑALES MANUALES (CON FILTROS PROFESIONALES) =====
st.sidebar.markdown("---")
st.sidebar.markdown("**📡 Ejecutar Señales Manuales**")

def ejecutar_compra_profesional(sym, precio, confianza, razon, tendencia_30d):
    """Ejecuta compra con lógica profesional (tamaño ajustado, orden limitada)."""
    # 1. Filtro de volumen
    if sym == "BTC":
        volumen = get_onchain_volume("BTC")
    else:
        volumen = get_onchain_volume("ETH")
    if volumen is not None and volumen < 0.5:
        st.sidebar.warning(f"⚠️ Volumen bajo ({volumen:.2f}B), operación no recomendada.")
        return
    
    # 2. Ajuste de tamaño según confianza
    if confianza >= 70:
        monto_por_compra = 100.0
        cantidad_compras = 4
    elif confianza >= 60:
        monto_por_compra = 75.0
        cantidad_compras = 3
    elif confianza >= 50:
        monto_por_compra = 50.0
        cantidad_compras = 2
    else:
        st.sidebar.warning(f"⚠️ Confianza baja ({confianza:.1f}%), no se recomienda operar.")
        return
    
    # 3. Precio limitado (0.5% por debajo para compras)
    precio_objetivo = precio * 0.995  # 0.5% descuento
    precio_actual = precio
    
    # Verificar si el precio ya bajó al nivel
    if precio_actual <= precio_objetivo:
        precio_ejecucion = precio_actual
        st.sidebar.info(f"✅ Precio alcanzó objetivo ({precio_objetivo:,.0f}). Ejecutando...")
    else:
        st.sidebar.info(f"⏳ Esperando que el precio baje a {precio_objetivo:,.0f} (actual {precio_actual:,.0f})")
        # En simulación, ejecutamos al precio actual pero mostramos la estrategia
        precio_ejecucion = precio_actual
    
    # Ejecutar compra
    if st.session_state.positions.get(sym, 0) > 0:
        st.sidebar.warning(f"⚠️ Ya tienes posición en {sym}.")
        return
    
    compras_ejecutadas = 0
    if st.session_state.balance >= monto_por_compra:
        if st.session_state.balance < cantidad_compras * monto_por_compra:
            cantidad_compras = int(st.session_state.balance // monto_por_compra)
            if cantidad_compras == 0:
                st.sidebar.warning("⚠️ Saldo insuficiente.")
                return
        
        for i in range(cantidad_compras):
            if st.session_state.balance >= monto_por_compra:
                com = monto_por_compra * 0.001
                qty = (monto_por_compra - com) / precio_ejecucion
                st.session_state.balance -= monto_por_compra
                st.session_state.positions[sym] += qty
                if st.session_state.entry_price[sym] == 0:
                    st.session_state.entry_price[sym] = precio_ejecucion
                st.session_state.highest_price[sym] = precio_ejecucion
                st.session_state.daily_trades += 1
                compras_ejecutadas += 1
            else:
                break
        
        if compras_ejecutadas > 0:
            st.session_state.last_action[sym] = "BUY"
            save_data()
            msg = f"🟢 COMPRA PROFESIONAL {sym} | {compras_ejecutadas} compras de ${monto_por_compra:.0f} | Precio: ${precio_ejecucion:,.0f} | Confianza: {confianza:.1f}% | Tendencia: {tendencia_30d}"
            send_telegram(msg)
            st.session_state.trades.append((datetime.now(), msg))
            st.sidebar.success(f"✅ {compras_ejecutadas} compras de {sym} ejecutadas (precio objetivo {precio_objetivo:,.0f}).")
            st.rerun()
        else:
            st.sidebar.warning("⚠️ No se pudo ejecutar la compra.")
    else:
        st.sidebar.warning("⚠️ Saldo insuficiente.")

# Botón COMPRA BTC (profesional)
if st.sidebar.button("📡 Ejecutar señal de COMPRA (BTC)"):
    btc_price = get_bitso_price("btc_mxn")
    if btc_price is not None:
        fng_value, _ = get_fear_greed()
        accion, confianza, razon, detalles = analisis_avanzado("BTC", btc_price, fng_value)
        tendencia_30d = st.session_state.historical_trend.get("BTC", {}).get("tendencia", "NEUTRAL")
        
        # Filtro profesional: solo comprar si la tendencia es alcista o neutral y confianza > 50
        if accion == "BUY" and confianza > 50:
            if tendencia_30d == "BAJISTA":
                st.sidebar.warning(f"⚠️ Tendencia 30d BAJISTA, no se recomienda comprar (confianza {confianza:.1f}%).")
            else:
                ejecutar_compra_profesional("BTC", btc_price, confianza, razon, tendencia_30d)
        else:
            st.sidebar.info(f"ℹ️ Señal no recomendada: {razon} (confianza {confianza:.1f}%)")

# Botón COMPRA ETH (profesional)
if st.sidebar.button("📡 Ejecutar señal de COMPRA (ETH)"):
    eth_price = get_bitso_price("eth_mxn")
    if eth_price is not None:
        fng_value, _ = get_fear_greed()
        accion, confianza, razon, detalles = analisis_avanzado("ETH", eth_price, fng_value)
        tendencia_30d = st.session_state.historical_trend.get("ETH", {}).get("tendencia", "NEUTRAL")
        
        if accion == "BUY" and confianza > 50:
            if tendencia_30d == "BAJISTA":
                st.sidebar.warning(f"⚠️ Tendencia 30d BAJISTA, no se recomienda comprar (confianza {confianza:.1f}%).")
            else:
                ejecutar_compra_profesional("ETH", eth_price, confianza, razon, tendencia_30d)
        else:
            st.sidebar.info(f"ℹ️ Señal no recomendada: {razon} (confianza {confianza:.1f}%)")

# Botón VENTA BTC (profesional)
if st.sidebar.button("📡 Ejecutar señal de VENTA (BTC)"):
    btc_price = get_bitso_price("btc_mxn")
    if btc_price is not None:
        fng_value, _ = get_fear_greed()
        accion, confianza, razon, detalles = analisis_avanzado("BTC", btc_price, fng_value)
        tendencia_30d = st.session_state.historical_trend.get("BTC", {}).get("tendencia", "NEUTRAL")
        
        if accion == "SELL" and confianza > 50:
            if tendencia_30d == "ALCISTA":
                st.sidebar.warning(f"⚠️ Tendencia 30d ALCISTA, no se recomienda vender (confianza {confianza:.1f}%).")
            else:
                if st.session_state.positions.get("BTC", 0) > 0:
                    qty = st.session_state.positions["BTC"]
                    gross = qty * btc_price
                    com = gross * 0.001
                    net = gross - com
                    st.session_state.balance += net
                    st.session_state.positions["BTC"] = 0
                    st.session_state.entry_price["BTC"] = 0
                    st.session_state.highest_price["BTC"] = 0
                    st.session_state.daily_trades += 1
                    msg = f"🔴 VENTA PROFESIONAL BTC | Cantidad: {qty:.6f} | Precio: ${btc_price:,.0f} | Neto: ${net:.2f} | Confianza: {confianza:.1f}% | Tendencia: {tendencia_30d}"
                    send_telegram(msg)
                    st.session_state.trades.append((datetime.now(), msg))
                    st.session_state.last_action["BTC"] = None
                    save_data()
                    st.sidebar.success(f"✅ Venta de BTC ejecutada.")
                    st.rerun()
                else:
                    st.sidebar.warning("⚠️ No hay posición en BTC para vender.")
        else:
            st.sidebar.info(f"ℹ️ Señal no recomendada: {razon} (confianza {confianza:.1f}%)")

# Botón VENTA ETH (profesional)
if st.sidebar.button("📡 Ejecutar señal de VENTA (ETH)"):
    eth_price = get_bitso_price("eth_mxn")
    if eth_price is not None:
        fng_value, _ = get_fear_greed()
        accion, confianza, razon, detalles = analisis_avanzado("ETH", eth_price, fng_value)
        tendencia_30d = st.session_state.historical_trend.get("ETH", {}).get("tendencia", "NEUTRAL")
        
        if accion == "SELL" and confianza > 50:
            if tendencia_30d == "ALCISTA":
                st.sidebar.warning(f"⚠️ Tendencia 30d ALCISTA, no se recomienda vender (confianza {confianza:.1f}%).")
            else:
                if st.session_state.positions.get("ETH", 0) > 0:
                    qty = st.session_state.positions["ETH"]
                    gross = qty * eth_price
                    com = gross * 0.001
                    net = gross - com
                    st.session_state.balance += net
                    st.session_state.positions["ETH"] = 0
                    st.session_state.entry_price["ETH"] = 0
                    st.session_state.highest_price["ETH"] = 0
                    st.session_state.daily_trades += 1
                    msg = f"🔴 VENTA PROFESIONAL ETH | Cantidad: {qty:.6f} | Precio: ${eth_price:,.0f} | Neto: ${net:.2f} | Confianza: {confianza:.1f}% | Tendencia: {tendencia_30d}"
                    send_telegram(msg)
                    st.session_state.trades.append((datetime.now(), msg))
                    st.session_state.last_action["ETH"] = None
                    save_data()
                    st.sidebar.success(f"✅ Venta de ETH ejecutada.")
                    st.rerun()
                else:
                    st.sidebar.warning("⚠️ No hay posición en ETH para vender.")
        else:
            st.sidebar.info(f"ℹ️ Señal no recomendada: {razon} (confianza {confianza:.1f}%)")
            # ==================== BUCLE PRINCIPAL CON SEÑALES AVANZADAS ====================
while True:
    try:
        # Verificar variables esenciales
        if "last_price" not in st.session_state:
            st.session_state.last_price = {"BTC": 0.0, "ETH": 0.0}
        if "ref_price" not in st.session_state:
            st.session_state.ref_price = {"BTC": 0.0, "ETH": 0.0}
        if "price_history" not in st.session_state:
            st.session_state.price_history = {"BTC": deque(maxlen=200), "ETH": deque(maxlen=200)}
        if "trades" not in st.session_state:
            st.session_state.trades = []
        if "positions" not in st.session_state:
            st.session_state.positions = {"BTC": 0.0, "ETH": 0.0}
        
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
        
        # Guardar cada 3 ciclos
        if st.session_state.cycle % 3 == 0:
            try:
                save_data()
            except Exception as e:
                print(f"Error guardando datos: {e}")

        fng_value, fng_label = get_fear_greed()
        
        caida_btc = (st.session_state.ref_price["BTC"] - btc) / st.session_state.ref_price["BTC"] * 100
        caida_eth = (st.session_state.ref_price["ETH"] - eth) / st.session_state.ref_price["ETH"] * 100

        cambio_btc = (btc - st.session_state.ref_price["BTC"]) / st.session_state.ref_price["BTC"] * 100
        cambio_eth = (eth - st.session_state.ref_price["ETH"]) / st.session_state.ref_price["ETH"] * 100

        st.session_state.tendencia["BTC"] = analizar_tendencia(st.session_state.price_history["BTC"])
        st.session_state.tendencia["ETH"] = analizar_tendencia(st.session_state.price_history["ETH"])

        # Actualizar tendencia 30d cada 60 ciclos
        if st.session_state.cycle % 60 == 0:
            for sym in ["BTC", "ETH"]:
                try:
                    trend = get_historical_trend(sym, 30)
                    if trend:
                        st.session_state.historical_trend[sym] = trend
                except Exception as e:
                    print(f"Error obteniendo tendencia 30d para {sym}: {e}")

        # Activar indicadores
        st.session_state.indicadores_activados["BTC"] = abs(cambio_btc) >= st.session_state.umbral_indicadores_activacion
        st.session_state.indicadores_activados["ETH"] = abs(cambio_eth) >= st.session_state.umbral_indicadores_activacion

        # Obtener volumen
        try:
            onchain_vol_btc = get_onchain_volume("BTC")
            onchain_vol_eth = get_onchain_volume("ETH")
        except:
            onchain_vol_btc = 0.5
            onchain_vol_eth = 0.5

        trend_btc = st.session_state.historical_trend.get("BTC", {})
        trend_eth = st.session_state.historical_trend.get("ETH", {})

        # Mostrar tabla
        tabla_placeholder.subheader("📊 Señales + Volumen + Tendencia 30d")
        tabla_placeholder.table({
            "Moneda": ["Bitcoin", "Ethereum"],
            "Precio MXN": [f"${btc:,.0f}", f"${eth:,.0f}"],
            "Cambio desde inicio": [f"{cambio_btc:+.2f}%", f"{cambio_eth:+.2f}%"],
            "Tendencia (corta)": [st.session_state.tendencia["BTC"], st.session_state.tendencia["ETH"]],
            "Confianza": [f"{st.session_state.confianza['BTC']}%", f"{st.session_state.confianza['ETH']}%"],
            "Volumen 24h (USD)": [
                f"{onchain_vol_btc:.2f}B" if onchain_vol_btc else "N/A",
                f"{onchain_vol_eth:.2f}B" if onchain_vol_eth else "N/A"
            ],
            "Cambio 30d": [
                f"{trend_btc.get('cambio_porcentual', 0):+.2f}%" if trend_btc else "N/A",
                f"{trend_eth.get('cambio_porcentual', 0):+.2f}%" if trend_eth else "N/A"
            ],
            "Tendencia 30d": [
                trend_btc.get("tendencia", "N/A") if trend_btc else "N/A",
                trend_eth.get("tendencia", "N/A") if trend_eth else "N/A"
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

        # Reinicio diario
        hoy = datetime.now().day
        if hoy != st.session_state.last_day:
            st.session_state.daily_trades = 0
            st.session_state.last_day = hoy

        # Evaluar rendimiento solo si aprendizaje activado (desactivado por defecto)
        if st.session_state.cycle % 5 == 0 and st.session_state.modo_aprendizaje:
            for sym in ["BTC", "ETH"]:
                try:
                    eval_rend = evaluar_rendimiento(sym)
                    if eval_rend["accion"] == "AUMENTAR_RIESGO":
                        st.session_state.umbral_caida = min(0.05, st.session_state.umbral_caida * 1.2)
                        st.session_state.take_profit = min(0.10, st.session_state.take_profit * 1.1)
                        st.session_state.confianza[sym] = min(100, st.session_state.confianza[sym] + 5)
                    elif eval_rend["accion"] == "REDUCIR_RIESGO":
                        st.session_state.umbral_caida = max(0.001, st.session_state.umbral_caida * 0.8)
                        st.session_state.take_profit = max(0.01, st.session_state.take_profit * 0.9)
                        st.session_state.confianza[sym] = max(0, st.session_state.confianza[sym] - 5)
                except:
                    pass

        # ===== PROCESAMIENTO DE SEÑALES AVANZADAS =====
        for sym, precio in [("BTC", btc), ("ETH", eth)]:
            try:
                # Análisis avanzado
                accion, confianza, razon, detalles = analisis_avanzado(sym, precio, fng_value)
                
                # Obtener tendencia 30d para el filtro profesional
                tendencia_30d = st.session_state.historical_trend.get(sym, {}).get("tendencia", "NEUTRAL")
                
                # Definir umbral de confianza según tendencia
                if tendencia_30d == "LATERAL":
                    umbral_confianza = 75
                elif tendencia_30d in ["ALCISTA", "BAJISTA"]:
                    umbral_confianza = 60
                else:
                    umbral_confianza = 70
                
                # Si la confianza supera el umbral, enviar señal por Telegram
                if confianza > umbral_confianza and accion != "HOLD":
                    if sym == "BTC":
                        volumen_onchain = onchain_vol_btc
                    else:
                        volumen_onchain = onchain_vol_eth
                    
                    cambio_30d = st.session_state.historical_trend.get(sym, {}).get("cambio_porcentual", 0)
                    
                    # Enviar señal (solo si no se envió en los últimos 10 ciclos)
                    if not hasattr(st.session_state, f'ultima_senal_{sym}'):
                        setattr(st.session_state, f'ultima_senal_{sym}', 0)
                    
                    if st.session_state.cycle - getattr(st.session_state, f'ultima_senal_{sym}', 0) > 10:
                        send_signal_telegram_buttons(
                            sym, accion, precio, razon, confianza,
                            volumen_onchain, cambio_30d, tendencia_30d
                        )
                        setattr(st.session_state, f'ultima_senal_{sym}', st.session_state.cycle)
                
                # Guardar última señal para mostrar en interfaz
                st.session_state.ultima_senal = {
                    "sym": sym,
                    "accion": accion,
                    "razon": razon,
                    "confianza": confianza,
                    "precio": precio,
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "tendencia_30d": tendencia_30d,
                    "umbral": umbral_confianza
                }
                
            except Exception as e:
                print(f"Error en análisis avanzado de {sym}: {e}")

        # Guardar al final del ciclo
        if st.session_state.cycle % 3 == 0:
            try:
                save_data()
            except:
                pass

        estado_placeholder.info(f"🔹 Indicadores: BTC={st.session_state.indicadores_activados.get('BTC', False)} | ETH={st.session_state.indicadores_activados.get('ETH', False)} | Tendencia 30d: BTC={trend_btc.get('tendencia', 'N/A')} | ETH={trend_eth.get('tendencia', 'N/A')}")
        if st.session_state.modo_solo_senales:
            estado_placeholder.info(f"🔇 Modo solo señales ACTIVADO - No se ejecutan órdenes")

    except Exception as e:
        print(f"Error en el bucle principal: {e}")
        time.sleep(10)
        continue

    time.sleep(30)
    # ===== FILTROS PROFESIONALES ADICIONALES =====
# Esta parte se integra en la PARTE 7, pero la separo para claridad

# 1. Filtro de volatilidad extrema (ATR)
def filtro_volatilidad(sym, precio):
    hist = list(st.session_state.price_history.get(sym, []))
    if len(hist) >= 14:
        atr = calcular_atr(hist, 14)
        if atr is not None and precio > 0:
            volatilidad_pct = (atr / precio) * 100
            if volatilidad_pct > 3:
                return False, f"Volatilidad alta ({volatilidad_pct:.1f}%)"
    return True, "OK"

# 2. Filtro de volumen mínimo
def filtro_volumen(sym):
    if sym == "BTC":
        volumen = get_onchain_volume("BTC")
    else:
        volumen = get_onchain_volume("ETH")
    if volumen is not None and volumen < 0.3:
        return False, f"Volumen bajo ({volumen:.2f}B USD)"
    return True, "OK"

# 3. Filtro de tendencia (no operar contra la tendencia macro)
def filtro_tendencia(accion, tendencia_30d):
    if accion == "BUY" and tendencia_30d == "BAJISTA":
        return False, "Tendencia 30d BAJISTA (no comprar)"
    if accion == "SELL" and tendencia_30d == "ALCISTA":
        return False, "Tendencia 30d ALCISTA (no vender)"
    return True, "OK"

# 4. Mostrar resumen de señales en la interfaz
def mostrar_resumen_senales():
    if hasattr(st.session_state, 'ultima_senal'):
        senal = st.session_state.ultima_senal
        st.sidebar.markdown("---")
        st.sidebar.markdown("**📊 Última Señal**")
        st.sidebar.write(f"**{senal['sym']}** - {senal['accion']}")
        st.sidebar.write(f"Confianza: {senal['confianza']:.1f}%")
        st.sidebar.write(f"Razón: {senal['razon']}")
        st.sidebar.write(f"Tendencia 30d: {senal.get('tendencia_30d', 'N/A')}")
        st.sidebar.write(f"Umbral: {senal.get('umbral', 70)}%")
        st.sidebar.write(f"Hora: {senal['timestamp']}")

# Llamar a la función en el bucle principal (PARTE 7)
# Agregar al final del bucle antes de time.sleep(30):
# mostrar_resumen_senales()
