# ==================== PARTE 1: IMPORTS Y CONFIGURACIÓN GLOBAL ====================
import streamlit as st
import requests
import time
import json
import os
import statistics
from datetime import datetime, timedelta
from collections import deque
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ==================== FIN PARTE 1 ====================
# ==================== PARTE 2: PERSISTENCIA (DATA.JSON) ====================
DATA_FILE = "data.json"
BACKUP_FILE = "data_backup.json"

def load_data():
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
            "historical_trend": st.session_state.historical_trend,
            "confianza_umbral": st.session_state.confianza_umbral
        }
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        with open(BACKUP_FILE, "w", encoding="utf-8") as bf:
            json.dump(data, bf, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error al guardar datos: {e}")

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
    st.session_state.umbral_indicadores_activacion = 0.5
    
    st.session_state.expert_score = 30
    st.session_state.rsi_os = 30
    st.session_state.rsi_ob = 80
    st.session_state.ema_fast = 5
    st.session_state.ema_slow = 12
    st.session_state.sl_triggered = {"BTC": False, "ETH": False}
    st.session_state.sl_low_price = {"BTC": 0.0, "ETH": 0.0}
    st.session_state.indicadores_activados = {"BTC": False, "ETH": False}
    st.session_state.modo_solo_senales = False
    st.session_state.modo_aprendizaje = False
    
    st.session_state.rendimiento = {
        "BTC": {"ganadas": 0, "perdidas": 0, "total": 0, "ultimas_10": []},
        "ETH": {"ganadas": 0, "perdidas": 0, "total": 0, "ultimas_10": []}
    }
    st.session_state.confianza = {"BTC": 50, "ETH": 50}
    st.session_state.tendencia = {"BTC": "NEUTRAL", "ETH": "NEUTRAL"}
    st.session_state.historial_operaciones = []
    st.session_state.onchain_cache = {
        "BTC": {"valor": None, "timestamp": 0},
        "ETH": {"valor": None, "timestamp": 0}
    }
    st.session_state.historical_trend = {"BTC": {}, "ETH": {}}
    st.session_state.confianza_umbral = 70

def restore_from_file():
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
        st.session_state.modo_aprendizaje = data.get("modo_aprendizaje", False)
        st.session_state.rendimiento = data.get("rendimiento", {
            "BTC": {"ganadas": 0, "perdidas": 0, "total": 0, "ultimas_10": []},
            "ETH": {"ganadas": 0, "perdidas": 0, "total": 0, "ultimas_10": []}
        })
        st.session_state.confianza = data.get("confianza", {"BTC": 50, "ETH": 50})
        st.session_state.tendencia = data.get("tendencia", {"BTC": "NEUTRAL", "ETH": "NEUTRAL"})
        st.session_state.historial_operaciones = data.get("historial_operaciones", [])
        st.session_state.onchain_cache = data.get("onchain_cache", {
            "BTC": {"valor": None, "timestamp": 0},
            "ETH": {"valor": None, "timestamp": 0}
        })
        st.session_state.historical_trend = data.get("historical_trend", {"BTC": {}, "ETH": {}})
        st.session_state.confianza_umbral = data.get("confianza_umbral", 70)
        
        ph = data.get("price_history", {"BTC": [], "ETH": []})
        st.session_state.price_history = {k: deque(v, maxlen=200) for k, v in ph.items()}
    except Exception as e:
        print(f"Error al restaurar datos: {e}")
        init_new_user_state()

# ==================== FIN PARTE 2 ====================
# ==================== PARTE 3: TELEGRAM Y BITSO API ====================
TELEGRAM_TOKEN = "8532857017:AAHwLhRnM3oC6TbgFFKAEmQnZVoo6JD_esQ"
TELEGRAM_CHAT_ID = "5835990242"

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=3)
    except:
        pass

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

# ==================== FIN PARTE 3 ====================
# ==================== PARTE 4: FUNCIONES DE ANÁLISIS Y APRENDIZAJE ====================
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

# ==================== FIN PARTE 4 ====================
# ==================== PARTE 5: DATOS EXTERNOS (COINGECKO, YAHOO FINANCE) ====================
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
    except:
        pass
    volume = 0.5
    st.session_state.onchain_cache[symbol] = {"valor": volume, "timestamp": now}
    return volume

# ==================== FIN PARTE 5 ====================
# ==================== PARTE 6: INDICADORES TÉCNICOS Y SEÑAL AVANZADA ====================
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

def analisis_avanzado(sym, precio, fng_value):
    pos = st.session_state.positions.get(sym, 0)
    entry = st.session_state.entry_price.get(sym, 0)
    ref = st.session_state.ref_price.get(sym, 0)
    
    trend_data = st.session_state.historical_trend.get(sym, {})
    cambio_30d = trend_data.get("cambio_porcentual", 0)
    tendencia_30d = trend_data.get("tendencia", "NEUTRAL")
    
    if sym == "BTC":
        volumen_onchain = get_onchain_volume("BTC")
    else:
        volumen_onchain = get_onchain_volume("ETH")
    
    hist = list(st.session_state.price_history.get(sym, []))
    if len(hist) < 30:
        return "HOLD", 0, "Datos insuficientes", {}
    
    rsi = compute_rsi(hist, 14)
    rsi_ponderado = 0
    if rsi <= 30:
        rsi_ponderado = 20
    elif rsi >= 70:
        rsi_ponderado = -20
    else:
        rsi_ponderado = (50 - rsi) * 0.5
    
    ema_f = compute_ema(hist, st.session_state.ema_fast)
    ema_s = compute_ema(hist, st.session_state.ema_slow)
    ema_ponderado = 0
    if ema_f is not None and ema_s is not None:
        if ema_f > ema_s:
            ema_ponderado = 15
        elif ema_f < ema_s:
            ema_ponderado = -15
        if len(hist) > 10:
            ema_prev = compute_ema(hist[:-1], st.session_state.ema_fast)
            if ema_prev is not None and ema_f > ema_prev * 1.001:
                ema_ponderado += 5
            elif ema_prev is not None and ema_f < ema_prev * 0.999:
                ema_ponderado -= 5
    
    bb_ponderado = 0
    if len(hist) >= 20:
        sma_20 = sum(hist[-20:]) / 20
        std_20 = statistics.stdev(hist[-20:]) if len(hist[-20:]) > 1 else 0
        banda_superior = sma_20 + 2 * std_20
        banda_inferior = sma_20 - 2 * std_20
        if precio > banda_superior:
            bb_ponderado = -15
        elif precio < banda_inferior:
            bb_ponderado = 15
    
    macd_ponderado = 0
    if len(hist) >= 26:
        ema_12 = compute_ema(hist, 12)
        ema_26 = compute_ema(hist, 26)
        if ema_12 is not None and ema_26 is not None:
            macd = ema_12 - ema_26
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
    
    volumen_ponderado = 0
    if volumen_onchain is not None:
        if volumen_onchain > 2.0:
            volumen_ponderado = 10
        elif volumen_onchain < 0.5:
            volumen_ponderado = -5
    
    tendencia_ponderado = 0
    if tendencia_30d == "ALCISTA":
        tendencia_ponderado = 15
    elif tendencia_30d == "BAJISTA":
        tendencia_ponderado = -15
    if abs(cambio_30d) > 20:
        tendencia_ponderado = tendencia_ponderado * 1.5
    
    fng_ponderado = 0
    if fng_value <= 20:
        fng_ponderado = 10
    elif fng_value >= 80:
        fng_ponderado = -10
    else:
        fng_ponderado = (50 - fng_value) * 0.2
    
    atr_ponderado = 0
    if len(hist) >= 14:
        atr = calcular_atr(hist, 14)
        if atr is not None and precio > 0:
            volatilidad_pct = (atr / precio) * 100
            if volatilidad_pct > 3:
                atr_ponderado = -5
            elif volatilidad_pct < 1:
                atr_ponderado = 5
    
    puntuacion = (rsi_ponderado + ema_ponderado + bb_ponderado + 
                  macd_ponderado + volumen_ponderado + tendencia_ponderado + 
                  fng_ponderado + atr_ponderado)
    
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

# ==================== FIN PARTE 6 ====================
# ==================== PARTE 7: INTERFAZ DE USUARIO (CONFIGURACIÓN Y SIDEBAR) ====================
st.set_page_config(page_title="Bot Scalping Extremo + Tendencia 30d", layout="wide")

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
    "historical_trend": {"BTC": {}, "ETH": {}},
    "confianza_umbral": 70
}

for var_name, default_value in required_vars.items():
    if var_name not in st.session_state:
        st.session_state[var_name] = default_value

if "data_loaded" not in st.session_state:
    restore_from_file()
    st.session_state.data_loaded = True

st.title("🧠 Scalping Extremo + Volumen + Tendencia 30d")

st.sidebar.header("⚙️ Configuración Principal")
st.session_state.umbral_caida = st.sidebar.number_input("Caída para comprar (scalping) (%)", min_value=0.001, max_value=50.0, step=0.001, value=float(st.session_state.umbral_caida))
st.session_state.take_profit = st.sidebar.number_input("Take Profit scalping (%)", min_value=0.01, max_value=50.0, step=0.01, value=float(st.session_state.take_profit))
st.session_state.stop_loss = st.sidebar.number_input("Stop Loss (%)", min_value=0.5, max_value=20.0, value=float(st.session_state.stop_loss), step=0.5)
st.session_state.trailing = st.sidebar.number_input("Trailing Stop (%)", min_value=0.2, max_value=5.0, value=float(st.session_state.trailing), step=0.1)
st.session_state.umbral_indicadores_activacion = st.sidebar.number_input("Activar indicadores a partir de ±(%)", min_value=0.1, max_value=20.0, step=0.1, value=float(st.session_state.umbral_indicadores_activacion))

st.sidebar.header("🧠 Modo Aprendizaje")
st.session_state.modo_aprendizaje = st.sidebar.checkbox("✅ Modo aprendizaje activado", value=st.session_state.modo_aprendizaje)

st.sidebar.header("🎯 Umbral de confianza")
st.session_state.confianza_umbral = st.sidebar.slider(
    "Confianza mínima para ejecutar (%)",
    min_value=45, max_value=95, value=st.session_state.confianza_umbral, step=5
)

st.sidebar.header("🧠 Indicadores")
st.session_state.expert_score = st.sidebar.slider("Puntaje de tendencia", 0, 100, st.session_state.expert_score, 5)
st.session_state.rsi_os = st.sidebar.number_input("RSI sobreventa", min_value=20, max_value=40, value=int(st.session_state.rsi_os), step=1)
st.session_state.rsi_ob = st.sidebar.number_input("RSI sobrecompra", min_value=70, max_value=90, value=int(st.session_state.rsi_ob), step=1)
st.session_state.ema_fast = st.sidebar.number_input("EMA rápida (periodos)", min_value=3, max_value=20, value=int(st.session_state.ema_fast), step=1)
st.session_state.ema_slow = st.sidebar.number_input("EMA lenta (periodos)", min_value=10, max_value=50, value=int(st.session_state.ema_slow), step=1)

st.sidebar.header("📡 Modo de operación")
st.session_state.modo_solo_senales = st.sidebar.checkbox("🔇 Modo solo señales (no ejecutar órdenes)", value=st.session_state.modo_solo_senales)

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

st.sidebar.markdown("---")
st.sidebar.markdown("**🎮 Control Manual**")

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
                if st.session_state.balance < monto_por_compra:
                    st.sidebar.warning("⚠️ Saldo insuficiente.")
                else:
                    if st.session_state.balance < cantidad_compras * monto_por_compra:
                        cantidad_compras = int(st.session_state.balance // monto_por_compra)
                    compras_ejecutadas = 0
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
                    if compras_ejecutadas > 0:
                        st.session_state.last_action["BTC"] = "BUY"
                        save_data()
                        msg = f"🟢 COMPRA FORZADA BTC | {compras_ejecutadas} compras de ${monto_por_compra:.0f} | Precio: ${precio:,.0f} | Saldo: ${st.session_state.balance:.2f}"
                        send_telegram(msg)
                        st.session_state.trades.append((datetime.now(), msg))
                        st.sidebar.success(f"✅ {compras_ejecutadas} compras de BTC ejecutadas.")
                        st.rerun()
    except Exception as e:
        st.sidebar.error(f"❌ Error: {e}")

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
                if st.session_state.balance < monto_por_compra:
                    st.sidebar.warning("⚠️ Saldo insuficiente.")
                else:
                    if st.session_state.balance < cantidad_compras * monto_por_compra:
                        cantidad_compras = int(st.session_state.balance // monto_por_compra)
                    compras_ejecutadas = 0
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
                    if compras_ejecutadas > 0:
                        st.session_state.last_action["ETH"] = "BUY"
                        save_data()
                        msg = f"🟢 COMPRA FORZADA ETH | {compras_ejecutadas} compras de ${monto_por_compra:.0f} | Precio: ${precio:,.0f} | Saldo: ${st.session_state.balance:.2f}"
                        send_telegram(msg)
                        st.session_state.trades.append((datetime.now(), msg))
                        st.sidebar.success(f"✅ {compras_ejecutadas} compras de ETH ejecutadas.")
                        st.rerun()
    except Exception as e:
        st.sidebar.error(f"❌ Error: {e}")

st.sidebar.markdown("---")
st.sidebar.markdown("**📡 Ejecutar Señales Manuales**")

def ejecutar_compra_profesional(sym, precio, confianza, razon, tendencia_30d):
    if sym == "BTC":
        volumen = get_onchain_volume("BTC")
    else:
        volumen = get_onchain_volume("ETH")
    if volumen is not None and volumen < 0.5:
        st.sidebar.warning(f"⚠️ Volumen bajo ({volumen:.2f}B), operación no recomendada.")
        return
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
    precio_objetivo = precio * 0.995
    if st.session_state.positions.get(sym, 0) > 0:
        st.sidebar.warning(f"⚠️ Ya tienes posición en {sym}.")
        return
    compras_ejecutadas = 0
    if st.session_state.balance >= monto_por_compra:
        if st.session_state.balance < cantidad_compras * monto_por_compra:
            cantidad_compras = int(st.session_state.balance // monto_por_compra)
        for i in range(cantidad_compras):
            if st.session_state.balance >= monto_por_compra:
                com = monto_por_compra * 0.001
                qty = (monto_por_compra - com) / precio_objetivo
                st.session_state.balance -= monto_por_compra
                st.session_state.positions[sym] += qty
                if st.session_state.entry_price[sym] == 0:
                    st.session_state.entry_price[sym] = precio_objetivo
                st.session_state.highest_price[sym] = precio_objetivo
                st.session_state.daily_trades += 1
                compras_ejecutadas += 1
        if compras_ejecutadas > 0:
            st.session_state.last_action[sym] = "BUY"
            save_data()
            msg = f"🟢 COMPRA PROFESIONAL {sym} | {compras_ejecutadas} compras de ${monto_por_compra:.0f} | Precio: ${precio_objetivo:,.0f} | Confianza: {confianza:.1f}% | Tendencia: {tendencia_30d}"
            send_telegram(msg)
            st.session_state.trades.append((datetime.now(), msg))
            st.sidebar.success(f"✅ {compras_ejecutadas} compras de {sym} ejecutadas.")
            st.rerun()
        else:
            st.sidebar.warning("⚠️ No se pudo ejecutar la compra.")
    else:
        st.sidebar.warning("⚠️ Saldo insuficiente.")

if st.sidebar.button("📡 Ejecutar señal de COMPRA (BTC)"):
    btc_price = get_bitso_price("btc_mxn")
    if btc_price is not None:
        fng_value, _ = get_fear_greed()
        accion, confianza, razon, detalles = analisis_avanzado("BTC", btc_price, fng_value)
        tendencia_30d = st.session_state.historical_trend.get("BTC", {}).get("tendencia", "NEUTRAL")
        if accion == "BUY" and confianza > st.session_state.confianza_umbral:
            if tendencia_30d == "BAJISTA":
                st.sidebar.warning(f"⚠️ Tendencia 30d BAJISTA, no se recomienda comprar (confianza {confianza:.1f}%).")
            else:
                ejecutar_compra_profesional("BTC", btc_price, confianza, razon, tendencia_30d)
        else:
            st.sidebar.info(f"ℹ️ Señal no recomendada: {razon} (confianza {confianza:.1f}%)")

if st.sidebar.button("📡 Ejecutar señal de COMPRA (ETH)"):
    eth_price = get_bitso_price("eth_mxn")
    if eth_price is not None:
        fng_value, _ = get_fear_greed()
        accion, confianza, razon, detalles = analisis_avanzado("ETH", eth_price, fng_value)
        tendencia_30d = st.session_state.historical_trend.get("ETH", {}).get("tendencia", "NEUTRAL")
        if accion == "BUY" and confianza > st.session_state.confianza_umbral:
            if tendencia_30d == "BAJISTA":
                st.sidebar.warning(f"⚠️ Tendencia 30d BAJISTA, no se recomienda comprar (confianza {confianza:.1f}%).")
            else:
                ejecutar_compra_profesional("ETH", eth_price, confianza, razon, tendencia_30d)
        else:
            st.sidebar.info(f"ℹ️ Señal no recomendada: {razon} (confianza {confianza:.1f}%)")

if st.sidebar.button("📡 Ejecutar señal de VENTA (BTC)"):
    btc_price = get_bitso_price("btc_mxn")
    if btc_price is not None:
        fng_value, _ = get_fear_greed()
        accion, confianza, razon, detalles = analisis_avanzado("BTC", btc_price, fng_value)
        tendencia_30d = st.session_state.historical_trend.get("BTC", {}).get("tendencia", "NEUTRAL")
        if accion == "SELL" and confianza > st.session_state.confianza_umbral:
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

if st.sidebar.button("📡 Ejecutar señal de VENTA (ETH)"):
    eth_price = get_bitso_price("eth_mxn")
    if eth_price is not None:
        fng_value, _ = get_fear_greed()
        accion, confianza, razon, detalles = analisis_avanzado("ETH", eth_price, fng_value)
        tendencia_30d = st.session_state.historical_trend.get("ETH", {}).get("tendencia", "NEUTRAL")
        if accion == "SELL" and confianza > st.session_state.confianza_umbral:
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

tabla_placeholder = st.empty()
info_placeholder = st.empty()
historial_placeholder = st.empty()
estado_placeholder = st.empty()
ultima_senal_placeholder = st.empty()

def send_signal_telegram_buttons(sym, tipo, precio, razon, confianza, volumen_onchain, cambio_30d, tendencia_30d):
    try:
        msg = (f"📢 **SEÑAL {tipo} - {sym}**\n"
               f"Confianza: {confianza:.1f}%\n"
               f"Precio: ${precio:,.0f}\n"
               f"Razón: {razon}\n"
               f"Volumen: {volumen_onchain:.2f}B USD\n"
               f"Cambio 30d: {cambio_30d:+.2f}%\n"
               f"Tendencia 30d: {tendencia_30d}\n\n"
               f"⚠️ **Para ejecutar esta orden**, ve a la sección '📡 Ejecutar Señales Manuales' en la app.")
        send_telegram(msg)
        return True
    except Exception as e:
        print(f"Error enviando señal: {e}")
        return False

# ==================== FIN PARTE 7 ====================
# ==================== PARTE 8: FUNCIONES AUXILIARES DE INTERFAZ Y PLACEHOLDERS ====================
# Los placeholders ya están definidos en la Parte 7.
# Esta parte queda como separador para claridad.

# ==================== FIN PARTE 8 ====================
# ==================== PARTE 9: BUCLE INFINITO CON AUTO-REFRESH ====================
# Esta parte se ejecuta en un bucle while True, actualizando los placeholders cada intervalo.

# Inicializar variables de control si no existen
if "intervalo_actualizacion" not in st.session_state:
    st.session_state.intervalo_actualizacion = 5

# ===== CONFIGURACIÓN DEL INTERVALO EN EL SIDEBAR =====
st.sidebar.markdown("---")
st.sidebar.markdown("**⏱️ Intervalo de actualización**")
intervalo = st.sidebar.slider(
    "Actualizar cada (segundos)",
    min_value=5, max_value=60, value=st.session_state.intervalo_actualizacion, step=5
)
st.session_state.intervalo_actualizacion = intervalo

st.sidebar.markdown("---")
st.sidebar.markdown("**🔄 Actualización**")
if st.sidebar.button("🔄 Actualizar datos ahora"):
    ejecutar_ciclo()  # Ejecuta un ciclo inmediato

# ===== FUNCIÓN QUE EJECUTA UN CICLO Y ACTUALIZA LOS PLACEHOLDERS =====
def ejecutar_ciclo():
    """Función que ejecuta un ciclo de actualización y actualiza la interfaz."""
    btc = get_bitso_price("btc_mxn")
    eth = get_bitso_price("eth_mxn")
    if btc is None or eth is None:
        tabla_placeholder.error("❌ Error al obtener precios. Reintentando...")
        return

    st.session_state.last_price["BTC"] = btc
    st.session_state.last_price["ETH"] = eth
    st.session_state.price_history["BTC"].append(btc)
    st.session_state.price_history["ETH"].append(eth)

    if st.session_state.ref_price["BTC"] == 0:
        st.session_state.ref_price["BTC"] = btc
        st.session_state.ref_price["ETH"] = eth

    st.session_state.cycle += 1
    
    if st.session_state.cycle % 3 == 0:
        save_data()

    fng_value, fng_label = get_fear_greed()
    
    caida_btc = (st.session_state.ref_price["BTC"] - btc) / st.session_state.ref_price["BTC"] * 100
    caida_eth = (st.session_state.ref_price["ETH"] - eth) / st.session_state.ref_price["ETH"] * 100
    cambio_btc = (btc - st.session_state.ref_price["BTC"]) / st.session_state.ref_price["BTC"] * 100
    cambio_eth = (eth - st.session_state.ref_price["ETH"]) / st.session_state.ref_price["ETH"] * 100

    st.session_state.tendencia["BTC"] = analizar_tendencia(st.session_state.price_history["BTC"])
    st.session_state.tendencia["ETH"] = analizar_tendencia(st.session_state.price_history["ETH"])

    if st.session_state.cycle % 60 == 0:
        for sym in ["BTC", "ETH"]:
            trend = get_historical_trend(sym, 30)
            if trend:
                st.session_state.historical_trend[sym] = trend

    st.session_state.indicadores_activados["BTC"] = abs(cambio_btc) >= st.session_state.umbral_indicadores_activacion
    st.session_state.indicadores_activados["ETH"] = abs(cambio_eth) >= st.session_state.umbral_indicadores_activacion

    onchain_vol_btc = get_onchain_volume("BTC")
    onchain_vol_eth = get_onchain_volume("ETH")
    trend_btc = st.session_state.historical_trend.get("BTC", {})
    trend_eth = st.session_state.historical_trend.get("ETH", {})

    senal_btc, confianza_btc, razon_btc, detalles_btc = analisis_avanzado("BTC", btc, fng_value)
    senal_eth, confianza_eth, razon_eth, detalles_eth = analisis_avanzado("ETH", eth, fng_value)

    # --- Mostrar tabla ---
    tabla_placeholder.subheader("📊 Señales + Volumen + Tendencia 30d")
    tabla_placeholder.table({
        "Moneda": ["Bitcoin", "Ethereum"],
        "Precio MXN": [f"${btc:,.0f}", f"${eth:,.0f}"],
        "Cambio desde inicio": [f"{cambio_btc:+.2f}%", f"{cambio_eth:+.2f}%"],
        "Tendencia (corta)": [st.session_state.tendencia["BTC"], st.session_state.tendencia["ETH"]],
        "Señal": [senal_btc, senal_eth],
        "Confianza señal": [f"{confianza_btc:.1f}%", f"{confianza_eth:.1f}%"],
        "Umbral": [f"{st.session_state.confianza_umbral}%", f"{st.session_state.confianza_umbral}%"],
        "Volumen 24h": [
            f"{onchain_vol_btc:.2f}B" if onchain_vol_btc else "N/A",
            f"{onchain_vol_eth:.2f}B" if onchain_vol_eth else "N/A"
        ],
        "Tendencia 30d": [
            trend_btc.get("tendencia", "N/A") if trend_btc else "N/A",
            trend_eth.get("tendencia", "N/A") if trend_eth else "N/A"
        ]
    })

    # --- Información de ciclo ---
    info_texto = (
        f"Ciclo: {st.session_state.cycle} | Caída scalping: {st.session_state.umbral_caida}% | "
        f"TP: {st.session_state.take_profit}% | SL: {st.session_state.stop_loss}% | "
        f"Trailing: {st.session_state.trailing}% | Fear & Greed: {fng_value}/100 ({fng_label}) | "
        f"Aprendizaje: {'✅' if st.session_state.modo_aprendizaje else '❌'} | "
        f"Umbral confianza: {st.session_state.confianza_umbral}% | "
        f"Intervalo: {st.session_state.intervalo_actualizacion}s"
    )
    info_placeholder.caption(info_texto)

    # --- Cartera ---
    total_val = st.session_state.balance
    for s in ["BTC", "ETH"]:
        p = st.session_state.last_price.get(s, 0)
        q = st.session_state.positions.get(s, 0)
        if q > 0 and p > 0:
            total_val += q * p
    saldo_placeholder.metric("Saldo MXN", f"${st.session_state.balance:,.2f}")
    total_placeholder.metric("Valor total", f"${total_val:,.2f}")
    ops_placeholder.metric("Ops hoy", st.session_state.daily_trades)

    # --- Historial ---
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

    # --- Aprendizaje ---
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

    # --- Procesar señales y ejecutar órdenes ---
    for sym, precio, senal, confianza_senal, razon in [
        ("BTC", btc, senal_btc, confianza_btc, razon_btc),
        ("ETH", eth, senal_eth, confianza_eth, razon_eth)
    ]:
        tendencia_30d = st.session_state.historical_trend.get(sym, {}).get("tendencia", "NEUTRAL")
        umbral_confianza = st.session_state.confianza_umbral
        
        st.session_state.ultima_senal = {
            "sym": sym,
            "accion": senal,
            "razon": razon,
            "confianza_senal": confianza_senal,
            "precio": precio,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "tendencia_30d": tendencia_30d,
            "umbral": umbral_confianza
        }
        
        if not st.session_state.modo_solo_senales:
            if senal == "BUY" and confianza_senal > umbral_confianza:
                if st.session_state.positions.get(sym, 0) == 0:
                    if tendencia_30d != "BAJISTA":
                        if sym == "BTC":
                            volumen = onchain_vol_btc
                        else:
                            volumen = onchain_vol_eth
                        if volumen is None or volumen >= 0.5:
                            ejecutar_compra_profesional(sym, precio, confianza_senal, razon, tendencia_30d)
                        else:
                            st.sidebar.info(f"ℹ️ Volumen bajo ({volumen:.2f}B), no se ejecuta compra de {sym}")
                    else:
                        st.sidebar.info(f"ℹ️ Tendencia BAJISTA, no se ejecuta compra de {sym}")
                else:
                    st.sidebar.info(f"ℹ️ Ya tienes posición en {sym}, no se compra más.")
            
            elif senal == "SELL" and confianza_senal > umbral_confianza:
                if st.session_state.positions.get(sym, 0) > 0:
                    if tendencia_30d != "ALCISTA":
                        qty = st.session_state.positions[sym]
                        gross = qty * precio
                        com = gross * 0.001
                        net = gross - com
                        st.session_state.balance += net
                        st.session_state.positions[sym] = 0
                        st.session_state.entry_price[sym] = 0
                        st.session_state.highest_price[sym] = 0
                        st.session_state.daily_trades += 1
                        msg = f"🔴 VENTA AUTOMÁTICA {sym} | Cantidad: {qty:.6f} | Precio: ${precio:,.0f} | Neto: ${net:.2f} | Confianza: {confianza_senal:.1f}% | Tendencia: {tendencia_30d}"
                        send_telegram(msg)
                        st.session_state.trades.append((datetime.now(), msg))
                        st.session_state.last_action[sym] = None
                        save_data()
                        st.sidebar.success(f"✅ Venta automática de {sym} ejecutada.")
                    else:
                        st.sidebar.info(f"ℹ️ Tendencia ALCISTA, no se ejecuta venta de {sym}")
                else:
                    st.sidebar.info(f"ℹ️ No hay posición en {sym} para vender.")
        
        if confianza_senal > umbral_confianza and senal != "HOLD":
            if sym == "BTC":
                volumen_onchain = onchain_vol_btc
            else:
                volumen_onchain = onchain_vol_eth
            cambio_30d = st.session_state.historical_trend.get(sym, {}).get("cambio_porcentual", 0)
            
            if not hasattr(st.session_state, f'ultima_senal_{sym}'):
                setattr(st.session_state, f'ultima_senal_{sym}', 0)
            
            if st.session_state.cycle - getattr(st.session_state, f'ultima_senal_{sym}', 0) > 10:
                send_signal_telegram_buttons(
                    sym, senal, precio, razon, confianza_senal,
                    volumen_onchain, cambio_30d, tendencia_30d
                )
                setattr(st.session_state, f'ultima_senal_{sym}', st.session_state.cycle)

    # --- Última señal ---
    if hasattr(st.session_state, 'ultima_senal'):
        senal = st.session_state.ultima_senal
        ultima_texto = (
            f"📊 Última señal: {senal['sym']} → {senal['accion']} | "
            f"Confianza real: {senal.get('confianza_senal', 0):.1f}% | "
            f"Razón: {senal['razon']} | "
            f"Tendencia 30d: {senal.get('tendencia_30d', 'N/A')} | "
            f"Umbral: {senal.get('umbral', 70)}%"
        )
        ultima_senal_placeholder.info(ultima_texto)

    estado_texto = (
        f"🔹 Indicadores: BTC={st.session_state.indicadores_activados.get('BTC', False)} | "
        f"ETH={st.session_state.indicadores_activados.get('ETH', False)} | "
        f"Tendencia 30d: BTC={trend_btc.get('tendencia', 'N/A')} | ETH={trend_eth.get('tendencia', 'N/A')} | "
        f"Modo: {'🔇 Solo señales' if st.session_state.modo_solo_senales else '✅ Ejecución automática'}"
    )
    estado_placeholder.info(estado_texto)

    if st.session_state.cycle % 3 == 0:
        save_data()

# ===== EJECUCIÓN DEL PRIMER CICLO =====
ejecutar_ciclo()

# ===== BUCLE INFINITO =====
while True:
    time.sleep(st.session_state.intervalo_actualizacion)
    ejecutar_ciclo()

# ==================== FIN PARTE 9 ====================
# ==================== PARTE 10: FUNCIONES DE BACKTESTING ====================
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

def obtener_datos_historicos(symbol, start_date, end_date, interval="1h"):
    """Descarga datos históricos de Yahoo Finance."""
    try:
        if symbol == "BTC":
            ticker = "BTC-USD"
        elif symbol == "ETH":
            ticker = "ETH-USD"
        else:
            return None
        
        df = yf.download(ticker, start=start_date, end=end_date, interval=interval)
        if df.empty:
            return None
        
        prices = df['Close'].tolist()
        return prices
    except Exception as e:
        st.error(f"❌ Error descargando datos de {symbol}: {e}")
        return None

def analisis_avanzado_bt(sym, precio, fng_value, price_history, historical_trend, 
                         ema_fast, ema_slow, rsi_os, rsi_ob, umbral_caida, take_profit, stop_loss):
    """Versión para backtest de analisis_avanzado."""
    trend_data = historical_trend.get(sym, {})
    cambio_30d = trend_data.get("cambio_porcentual", 0)
    tendencia_30d = trend_data.get("tendencia", "NEUTRAL")
    
    volumen_onchain = 0.5
    
    hist = list(price_history)
    if len(hist) < 30:
        return "HOLD", 0, "Datos insuficientes", {}
    
    rsi = compute_rsi(hist, 14)
    rsi_ponderado = 0
    if rsi <= rsi_os:
        rsi_ponderado = 20
    elif rsi >= rsi_ob:
        rsi_ponderado = -20
    else:
        rsi_ponderado = (50 - rsi) * 0.5
    
    ema_f = compute_ema(hist, ema_fast)
    ema_s = compute_ema(hist, ema_slow)
    ema_ponderado = 0
    if ema_f is not None and ema_s is not None:
        if ema_f > ema_s:
            ema_ponderado = 15
        elif ema_f < ema_s:
            ema_ponderado = -15
        if len(hist) > 10:
            ema_prev = compute_ema(hist[:-1], ema_fast)
            if ema_prev is not None and ema_f > ema_prev * 1.001:
                ema_ponderado += 5
            elif ema_prev is not None and ema_f < ema_prev * 0.999:
                ema_ponderado -= 5
    
    bb_ponderado = 0
    if len(hist) >= 20:
        sma_20 = sum(hist[-20:]) / 20
        std_20 = statistics.stdev(hist[-20:]) if len(hist[-20:]) > 1 else 0
        banda_superior = sma_20 + 2 * std_20
        banda_inferior = sma_20 - 2 * std_20
        if precio > banda_superior:
            bb_ponderado = -15
        elif precio < banda_inferior:
            bb_ponderado = 15
    
    macd_ponderado = 0
    if len(hist) >= 26:
        ema_12 = compute_ema(hist, 12)
        ema_26 = compute_ema(hist, 26)
        if ema_12 is not None and ema_26 is not None:
            macd = ema_12 - ema_26
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
    
    volumen_ponderado = 0
    if volumen_onchain is not None:
        if volumen_onchain > 2.0:
            volumen_ponderado = 10
        elif volumen_onchain < 0.5:
            volumen_ponderado = -5
    
    tendencia_ponderado = 0
    if tendencia_30d == "ALCISTA":
        tendencia_ponderado = 15
    elif tendencia_30d == "BAJISTA":
        tendencia_ponderado = -15
    if abs(cambio_30d) > 20:
        tendencia_ponderado = tendencia_ponderado * 1.5
    
    fng_ponderado = 0
    if fng_value <= 20:
        fng_ponderado = 10
    elif fng_value >= 80:
        fng_ponderado = -10
    else:
        fng_ponderado = (50 - fng_value) * 0.2
    
    atr_ponderado = 0
    if len(hist) >= 14:
        atr = calcular_atr(hist, 14)
        if atr is not None and precio > 0:
            volatilidad_pct = (atr / precio) * 100
            if volatilidad_pct > 3:
                atr_ponderado = -5
            elif volatilidad_pct < 1:
                atr_ponderado = 5
    
    puntuacion = (rsi_ponderado + ema_ponderado + bb_ponderado + 
                  macd_ponderado + volumen_ponderado + tendencia_ponderado + 
                  fng_ponderado + atr_ponderado)
    
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

def ejecutar_backtest_completo(symbol, prices, config):
    """Ejecuta el backtest completo con la lógica de 8 indicadores."""
    if not prices or len(prices) < 30:
        return None, 0, 0, 0, 0, []
    
    umbral_confianza = config['umbral_confianza']
    umbral_caida = config['umbral_caida']
    take_profit = config['take_profit']
    stop_loss = config['stop_loss']
    rsi_os = config['rsi_os']
    rsi_ob = config['rsi_ob']
    ema_fast = config['ema_fast']
    ema_slow = config['ema_slow']
    
    balance = 1000.0
    positions = 0.0
    entry_price = 0.0
    highest_price = 0.0
    operations = []
    equity_curve = []
    max_balance = balance
    max_drawdown = 0
    ciclo = 0
    
    price_history = deque(maxlen=200)
    historical_trend = {}
    fng_value = 50
    
    for i, price in enumerate(prices):
        price_history.append(price)
        ciclo += 1
        
        if ciclo % 60 == 0:
            if len(prices) > i - 720:
                subset = prices[max(0, i-720):i+1]
                if subset:
                    cambio = (subset[-1] - subset[0]) / subset[0] * 100 if subset[0] != 0 else 0
                    sma_30 = sum(subset[-30:]) / 30 if len(subset) >= 30 else sum(subset) / len(subset)
                    if subset[-1] > sma_30 * 1.01:
                        tendencia = "ALCISTA"
                    elif subset[-1] < sma_30 * 0.99:
                        tendencia = "BAJISTA"
                    else:
                        tendencia = "LATERAL"
                    historical_trend[symbol] = {
                        "cambio_porcentual": cambio,
                        "tendencia": tendencia
                    }
        
        if len(price_history) < 30:
            continue
        
        accion, confianza, razon, detalles = analisis_avanzado_bt(
            symbol, price, fng_value, price_history, historical_trend,
            ema_fast, ema_slow, rsi_os, rsi_ob, umbral_caida, take_profit, stop_loss
        )
        
        if accion == "BUY" and confianza > umbral_confianza and positions == 0:
            tendencia_30d = historical_trend.get(symbol, {}).get("tendencia", "NEUTRAL")
            if tendencia_30d != "BAJISTA":
                monto = 100.0
                com = monto * 0.001
                qty = (monto - com) / price
                balance -= monto
                positions = qty
                entry_price = price
                highest_price = price
                operations.append({
                    "type": "BUY",
                    "price": price,
                    "qty": qty,
                    "balance": balance,
                    "index": i,
                    "confianza": confianza
                })
        
        elif accion == "SELL" and confianza > umbral_confianza and positions > 0:
            tendencia_30d = historical_trend.get(symbol, {}).get("tendencia", "NEUTRAL")
            if tendencia_30d != "ALCISTA":
                gross = positions * price
                com = gross * 0.001
                net = gross - com
                balance += net
                profit = net - (positions * entry_price)
                operations.append({
                    "type": "SELL",
                    "price": price,
                    "qty": positions,
                    "balance": balance,
                    "profit": profit,
                    "index": i,
                    "confianza": confianza
                })
                positions = 0
                entry_price = 0
                highest_price = 0
        
        if positions > 0 and entry_price > 0:
            if price > highest_price:
                highest_price = price
            trailing_stop_price = highest_price * (1 - config['trailing'] / 100)
            stop_loss_price = entry_price * (1 - stop_loss / 100)
            take_profit_price = entry_price * (1 + take_profit / 100)
            
            if price <= stop_loss_price or price <= trailing_stop_price:
                gross = positions * price
                com = gross * 0.001
                net = gross - com
                balance += net
                profit = net - (positions * entry_price)
                operations.append({
                    "type": "SELL (SL)",
                    "price": price,
                    "qty": positions,
                    "balance": balance,
                    "profit": profit,
                    "index": i
                })
                positions = 0
                entry_price = 0
                highest_price = 0
            
            elif price >= take_profit_price:
                gross = positions * price
                com = gross * 0.001
                net = gross - com
                balance += net
                profit = net - (positions * entry_price)
                operations.append({
                    "type": "SELL (TP)",
                    "price": price,
                    "qty": positions,
                    "balance": balance,
                    "profit": profit,
                    "index": i
                })
                positions = 0
                entry_price = 0
                highest_price = 0
        
        total_value = balance + (positions * price) if positions > 0 else balance
        equity_curve.append(total_value)
        if total_value > max_balance:
            max_balance = total_value
        drawdown = (max_balance - total_value) / max_balance * 100 if max_balance > 0 else 0
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    
    if positions > 0 and len(prices) > 0:
        final_price = prices[-1]
        gross = positions * final_price
        com = gross * 0.001
        net = gross - com
        balance += net
        profit = net - (positions * entry_price)
        operations.append({
            "type": "SELL (FINAL)",
            "price": final_price,
            "qty": positions,
            "balance": balance,
            "profit": profit,
            "index": len(prices) - 1
        })
    
    saldo_final = balance
    sell_ops = [op for op in operations if op["type"] in ["SELL", "SELL (SL)", "SELL (TP)", "SELL (FINAL)"]]
    wins = len([op for op in sell_ops if op.get("profit", 0) > 0])
    total_sells = len(sell_ops)
    win_rate = (wins / total_sells * 100) if total_sells > 0 else 0
    
    total_profit = sum([op.get("profit", 0) for op in sell_ops if op.get("profit", 0) > 0])
    total_loss = abs(sum([op.get("profit", 0) for op in sell_ops if op.get("profit", 0) < 0]))
    profit_factor = total_profit / total_loss if total_loss > 0 else 0
    
    return operations, saldo_final, max_drawdown, win_rate, profit_factor, equity_curve

# ==================== FIN PARTE 10 ====================
# ==================== PARTE 11: INTERFAZ DE BACKTESTING ====================
def mostrar_resultados_backtest_completo(symbol, operations, saldo_final, max_drawdown, win_rate, profit_factor, equity_curve, prices):
    """Muestra los resultados del backtest en la interfaz con gráficos avanzados."""
    st.subheader(f"📊 Resultados del Backtest - {symbol}")
    
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("💰 Saldo final", f"${saldo_final:,.2f}")
    with col2:
        rentabilidad = ((saldo_final - 1000) / 1000 * 100)
        st.metric("📈 Rentabilidad", f"{rentabilidad:+.2f}%")
    with col3:
        st.metric("📉 Drawdown máx.", f"{max_drawdown:.2f}%")
    with col4:
        st.metric("🎯 Win Rate", f"{win_rate:.1f}%")
    with col5:
        st.metric("💹 Profit Factor", f"{profit_factor:.2f}")
    
    st.subheader("📋 Resumen de operaciones")
    sell_ops = [op for op in operations if op["type"] in ["SELL", "SELL (SL)", "SELL (TP)", "SELL (FINAL)"]]
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("📊 Total operaciones", len(sell_ops))
    with col2:
        st.metric("🟢 Ganancias", len([op for op in sell_ops if op.get("profit", 0) > 0]))
    with col3:
        st.metric("🔴 Pérdidas", len([op for op in sell_ops if op.get("profit", 0) < 0]))
    
    st.subheader("📋 Detalle de operaciones (últimas 20)")
    if operations:
        df_ops = pd.DataFrame(operations)
        df_ops_display = df_ops[['type', 'price', 'qty', 'balance', 'profit']].copy()
        df_ops_display.columns = ['Tipo', 'Precio', 'Cantidad', 'Saldo', 'Profit']
        st.dataframe(df_ops_display.tail(20))
    
    st.subheader("📈 Evolución del precio y operaciones")
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.08, 
                        row_heights=[0.5, 0.25, 0.25])
    
    fig.add_trace(go.Scatter(x=list(range(len(prices))), y=prices, 
                             name='Precio', line=dict(color='blue', width=1)), row=1, col=1)
    
    buys = [op for op in operations if op['type'] == 'BUY']
    if buys:
        buy_indices = [op['index'] for op in buys]
        buy_prices = [op['price'] for op in buys]
        fig.add_trace(go.Scatter(x=buy_indices, y=buy_prices, 
                                 mode='markers', name='Compra', 
                                 marker=dict(color='green', size=8, symbol='triangle-up')), row=1, col=1)
    
    sells = [op for op in operations if op['type'] in ['SELL', 'SELL (SL)', 'SELL (TP)', 'SELL (FINAL)']]
    if sells:
        sell_indices = [op['index'] for op in sells]
        sell_prices = [op['price'] for op in sells]
        sell_colors = ['red' if op.get('profit', 0) < 0 else 'orange' for op in sells]
        sell_symbols = ['triangle-down' if op.get('profit', 0) < 0 else 'diamond' for op in sells]
        fig.add_trace(go.Scatter(x=sell_indices, y=sell_prices, 
                                 mode='markers', name='Venta', 
                                 marker=dict(color=sell_colors, size=8, symbol=sell_symbols)), row=1, col=1)
    
    if equity_curve:
        fig.add_trace(go.Scatter(x=list(range(len(equity_curve))), y=equity_curve, 
                                 name='Balance', line=dict(color='green', width=2)), row=2, col=1)
        fig.add_hline(y=1000, line_dash="dash", line_color="gray", row=2, col=1)
    
    if equity_curve:
        max_balance_so_far = 1000
        drawdowns = []
        for val in equity_curve:
            if val > max_balance_so_far:
                max_balance_so_far = val
            dd = (max_balance_so_far - val) / max_balance_so_far * 100 if max_balance_so_far > 0 else 0
            drawdowns.append(dd)
        fig.add_trace(go.Scatter(x=list(range(len(drawdowns))), y=drawdowns, 
                                 name='Drawdown %', line=dict(color='red', width=1), fill='tozeroy'), row=3, col=1)
    
    fig.update_layout(height=800, title_text=f"Backtest {symbol} - {len(prices)} datos")
    fig.update_xaxes(title_text="Tiempo (horas)", row=3, col=1)
    fig.update_yaxes(title_text="Precio (USD)", row=1, col=1)
    fig.update_yaxes(title_text="Balance (USD)", row=2, col=1)
    fig.update_yaxes(title_text="Drawdown (%)", row=3, col=1)
    
    st.plotly_chart(fig, use_container_width=True)

# ===== SECCIÓN DE BACKTEST EN EL SIDEBAR =====
st.sidebar.markdown("---")
st.sidebar.markdown("**📊 Backtesting**")

if st.sidebar.checkbox("🔬 Activar modo Backtest", value=False):
    st.sidebar.markdown("### ⚙️ Configuración")
    
    symbol_backtest = st.sidebar.selectbox("Moneda", ["BTC", "ETH"])
    
    col1, col2 = st.sidebar.columns(2)
    with col1:
        start_date = st.date_input("Fecha inicio", value=datetime(2025, 1, 1))
    with col2:
        end_date = st.date_input("Fecha fin", value=datetime.now() - timedelta(days=1))
    
    intervalo = st.sidebar.selectbox("Intervalo", ["1h", "4h", "1d"], index=0)
    
    st.sidebar.markdown("**📈 Parámetros de la estrategia**")
    umbral_bt = st.sidebar.slider("Umbral confianza (%)", 30, 90, st.session_state.confianza_umbral, 5)
    stop_loss_bt = st.sidebar.number_input("Stop Loss (%)", 0.5, 10.0, float(st.session_state.stop_loss), 0.5)
    take_profit_bt = st.sidebar.number_input("Take Profit (%)", 0.1, 5.0, float(st.session_state.take_profit), 0.1)
    trailing_bt = st.sidebar.number_input("Trailing Stop (%)", 0.2, 5.0, float(st.session_state.trailing), 0.1)
    umbral_caida_bt = st.sidebar.number_input("Caída para comprar (%)", 0.001, 5.0, float(st.session_state.umbral_caida), 0.001)
    
    st.sidebar.markdown("**🧠 Indicadores**")
    rsi_os_bt = st.sidebar.number_input("RSI sobreventa", 20, 40, int(st.session_state.rsi_os), 1)
    rsi_ob_bt = st.sidebar.number_input("RSI sobrecompra", 70, 90, int(st.session_state.rsi_ob), 1)
    ema_fast_bt = st.sidebar.number_input("EMA rápida", 3, 20, int(st.session_state.ema_fast), 1)
    ema_slow_bt = st.sidebar.number_input("EMA lenta", 10, 50, int(st.session_state.ema_slow), 1)
    
    if st.sidebar.button("🚀 Ejecutar Backtest"):
        with st.spinner(f"📊 Ejecutando backtest de {symbol_backtest}..."):
            prices = obtener_datos_historicos(symbol_backtest, start_date, end_date, intervalo)
            
            if prices is None or len(prices) < 30:
                st.sidebar.error("❌ No se pudieron obtener datos históricos suficientes.")
            else:
                config = {
                    'umbral_confianza': umbral_bt,
                    'umbral_caida': umbral_caida_bt,
                    'take_profit': take_profit_bt,
                    'stop_loss': stop_loss_bt,
                    'trailing': trailing_bt,
                    'rsi_os': rsi_os_bt,
                    'rsi_ob': rsi_ob_bt,
                    'ema_fast': ema_fast_bt,
                    'ema_slow': ema_slow_bt
                }
                
                operations, saldo_final, max_drawdown, win_rate, profit_factor, equity_curve = ejecutar_backtest_completo(
                    symbol_backtest, prices, config
                )
                
                if operations is None:
                    st.sidebar.error("❌ Error en el backtest. Verifica los datos.")
                else:
                    mostrar_resultados_backtest_completo(
                        symbol_backtest, operations, saldo_final, max_drawdown, 
                        win_rate, profit_factor, equity_curve, prices
                    )
                    
                    st.sidebar.success(f"✅ Backtest completado!")
                    st.sidebar.metric("Saldo final", f"${saldo_final:,.2f}")
                    rentabilidad = ((saldo_final - 1000) / 1000 * 100)
                    st.sidebar.metric("Rentabilidad", f"{rentabilidad:+.2f}%")
                    st.sidebar.metric("Operaciones", len([op for op in operations if op['type'] in ['SELL', 'SELL (SL)', 'SELL (TP)', 'SELL (FINAL)']]))
                    st.sidebar.metric("Win Rate", f"{win_rate:.1f}%")
                    
                    if st.sidebar.button("📥 Aplicar parámetros al bot"):
                        st.session_state.confianza_umbral = umbral_bt
                        st.session_state.stop_loss = stop_loss_bt
                        st.session_state.take_profit = take_profit_bt
                        st.session_state.trailing = trailing_bt
                        st.session_state.umbral_caida = umbral_caida_bt
                        st.session_state.rsi_os = rsi_os_bt
                        st.session_state.rsi_ob = rsi_ob_bt
                        st.session_state.ema_fast = ema_fast_bt
                        st.session_state.ema_slow = ema_slow_bt
                        save_data()
                        st.sidebar.success("✅ Parámetros aplicados al bot en vivo")
                        st.rerun()

# ==================== FIN PARTE 11 ====================
