# ==================== PARTE 1: IMPORTS Y CONFIGURACIÓN GLOBAL ====================
import streamlit as st
import requests
import time
import json
import os
import re
import statistics
from datetime import datetime, timedelta, timezone
from collections import deque

# ==================== FIN PARTE 1 ====================
# ==================== PARTE 2: PERSISTENCIA EN FIREBASE ====================
FIREBASE_URL = "https://bot-cc6c4-default-rtdb.firebaseio.com"

def save_data():
    """Guarda los datos en Firebase. Retorna (éxito, mensaje)."""
    try:
        data = {
            "balance": st.session_state.balance,
            "positions": st.session_state.positions,
            "trades": [(t.isoformat(), msg) for t, msg in st.session_state.trades],
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
            "confianza_umbral": st.session_state.confianza_umbral,
            "intervalo_actualizacion": st.session_state.intervalo_actualizacion,
            "inicio_fase": st.session_state.inicio_fase,
            "fase_actual": st.session_state.fase_actual,
            "analisis_anterior": st.session_state.analisis_anterior
        }
        url = f"{FIREBASE_URL}/bot.json"
        resp = requests.put(url, json=data, timeout=10)
        
        if resp.status_code == 200:
            print(f"💾 Datos guardados. Ciclo: {st.session_state.cycle} | Trades: {len(st.session_state.trades)}")
            return True, "Guardado exitoso"
        else:
            return False, f"Status {resp.status_code}"
    except Exception as e:
        return False, str(e)

def load_data():
    try:
        url = f"{FIREBASE_URL}/bot.json"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data and "balance" in data and "positions" in data and "cycle" in data:
                return data
        return None
    except Exception as e:
        print(f"Error al cargar: {e}")
        return None

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
    st.session_state.confianza_umbral = 20
    st.session_state.intervalo_actualizacion = 5
    st.session_state.inicio_fase = datetime.now().isoformat()
    st.session_state.fase_actual = "operando"
    st.session_state.analisis_anterior = {}

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
        st.session_state.confianza_umbral = data.get("confianza_umbral", 20)
        st.session_state.intervalo_actualizacion = data.get("intervalo_actualizacion", 5)
        st.session_state.inicio_fase = data.get("inicio_fase", datetime.now().isoformat())
        st.session_state.fase_actual = data.get("fase_actual", "operando")
        st.session_state.analisis_anterior = data.get("analisis_anterior", {})
        
        ph = data.get("price_history", {"BTC": [], "ETH": []})
        st.session_state.price_history = {k: deque(v, maxlen=200) for k, v in ph.items()}
        print(f"✅ Datos restaurados. Ciclo: {st.session_state.cycle} | Trades: {len(trades)}")
    except Exception as e:
        print(f"Error al restaurar: {e}")
        init_new_user_state()

# ==================== FIN PARTE 2 ====================
# ==================== PARTE 3: TELEGRAM Y BITSO API ====================
TELEGRAM_TOKEN = "8532857017:AAHwLhRnM3oC6TbgFFKAEmQnZVoo6JD_esQ"
TELEGRAM_CHAT_ID = "5835990242"

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=5)
    except:
        pass

def get_bitso_price(book="btc_mxn"):
    try:
        url = f"https://api.bitso.com/api/v3/ticker/?book={book}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            payload = data.get("payload")
            if payload and payload.get("last"):
                return float(payload["last"])
    except:
        pass
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
# ==================== PARTE 4: ANÁLISIS Y APRENDIZAJE ====================
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

def evaluar_rendimiento(sym):
    rend = st.session_state.rendimiento[sym]
    total = rend["total"]
    if total < 5:
        return {"accion": "MANTENER"}
    ratio = rend["ganadas"] / total
    if ratio > 0.6:
        return {"accion": "AUMENTAR_RIESGO"}
    elif ratio < 0.4:
        return {"accion": "REDUCIR_RIESGO"}
    else:
        return {"accion": "MANTENER"}

def analizar_fase_aprendizaje():
    """
    Analiza las operaciones de los últimos 2 días y saca conclusiones.
    Ajusta parámetros automáticamente.
    """
    trades = st.session_state.trades
    if len(trades) < 3:
        return {
            "suficiente": False,
            "razon": f"Solo {len(trades)} operaciones. Se necesitan mínimo 3."
        }
    
    ventas = []
    for ts, msg in trades:
        if "VENTA" in msg or "SELL" in msg:
            ventas.append({"ts": ts, "msg": msg})
    
    if len(ventas) == 0:
        return {"suficiente": False, "razon": "No hay ventas cerradas para analizar."}
    
    ganancias = 0
    perdidas = 0
    horarios_op = {}
    simbolos = {"BTC": {"wins": 0, "losses": 0}, "ETH": {"wins": 0, "losses": 0}}
    
    for v in ventas:
        msg = v["msg"]
        hora = v["ts"].hour
        horarios_op.setdefault(hora, {"wins": 0, "losses": 0})
        
        es_ganancia = "GANANCIA" in msg.upper() or "PROFIT" in msg.upper() or "Neto" in msg
        
        if es_ganancia:
            ganancias += 1
            horarios_op[hora]["wins"] += 1
            for sym in simbolos:
                if sym in msg:
                    simbolos[sym]["wins"] += 1
        else:
            perdidas += 1
            horarios_op[hora]["losses"] += 1
            for sym in simbolos:
                if sym in msg:
                    simbolos[sym]["losses"] += 1
    
    total_ventas = ganancias + perdidas
    win_rate = (ganancias / total_ventas * 100) if total_ventas > 0 else 0
    
    mejor_hora = None
    peor_hora = None
    mejor_score = -999
    peor_score = 999
    for h, d in horarios_op.items():
        score = d["wins"] - d["losses"]
        if score > mejor_score:
            mejor_score = score
            mejor_hora = h
        if score < peor_score:
            peor_score = score
            peor_hora = h
    
    analisis = {
        "suficiente": True,
        "total_operaciones": total_ventas,
        "ganancias": ganancias,
        "perdidas": perdidas,
        "win_rate": win_rate,
        "mejor_hora": mejor_hora,
        "peor_hora": peor_hora,
        "simbolos": simbolos,
        "ajustes_aplicados": []
    }
    
    # Ajuste 1: Umbral según win rate
    if win_rate < 40:
        st.session_state.confianza_umbral = min(70, st.session_state.confianza_umbral + 5)
        analisis["ajustes_aplicados"].append(f"Umbral subido a {st.session_state.confianza_umbral}% (win rate bajo)")
    elif win_rate > 65:
        st.session_state.confianza_umbral = max(20, st.session_state.confianza_umbral - 5)
        analisis["ajustes_aplicados"].append(f"Umbral bajado a {st.session_state.confianza_umbral}% (win rate alto)")
    
    # Ajuste 2: BTC vs ETH
    for sym, stats in simbolos.items():
        total_sym = stats["wins"] + stats["losses"]
        if total_sym >= 2:
            wr_sym = (stats["wins"] / total_sym * 100)
            if wr_sym < 30:
                analisis["ajustes_aplicados"].append(f"{sym} rinde mal ({wr_sym:.0f}%)")
            elif wr_sym > 70:
                analisis["ajustes_aplicados"].append(f"{sym} rinde bien ({wr_sym:.0f}%)")
    
    # Ajuste 3: TP según win rate
    if win_rate > 60:
        st.session_state.take_profit = min(0.5, st.session_state.take_profit * 1.1)
        analisis["ajustes_aplicados"].append(f"TP aumentado a {st.session_state.take_profit:.3f}%")
    elif win_rate < 40:
        st.session_state.take_profit = max(0.01, st.session_state.take_profit * 0.9)
        analisis["ajustes_aplicados"].append(f"TP reducido a {st.session_state.take_profit:.3f}%")
        st.session_state.stop_loss = max(0.5, st.session_state.stop_loss * 0.9)
        analisis["ajustes_aplicados"].append(f"SL ajustado a {st.session_state.stop_loss:.2f}%")
    
    return analisis

# ==================== FIN PARTE 4 ====================
# ==================== PARTE 5: DATOS EXTERNOS ====================
def get_historical_trend(symbol="BTC", days=30):
    try:
        coin_id = "bitcoin" if symbol == "BTC" else "ethereum"
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
        return {
            "cambio_porcentual": cambio_porcentual,
            "tendencia": tendencia,
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
        coin = "bitcoin" if symbol == "BTC" else "ethereum"
        url = f"https://api.coingecko.com/api/v3/coins/{coin}/market_chart?vs_currency=usd&days=1"
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
# ==================== PARTE 6: INDICADORES Y SEÑAL AVANZADA ====================
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

def calcular_probabilidad(confianza):
    return min(100, max(0, confianza * 2.5))

def obtener_horario_operacion():
    """Determina la calidad del horario actual (hora México)."""
    tz_mexico = timezone(timedelta(hours=-6))
    ahora = datetime.now(tz_mexico)
    hora = ahora.hour
    dia_semana = ahora.weekday()
    
    if dia_semana >= 5:
        return ("FIN DE SEMANA", "🛑", "Mercado con muy poca actividad. Evita operar.", False)
    if 7 <= hora < 11:
        return ("MEJOR HORARIO", "🔥", "Europa + USA activos. Mejores señales y liquidez.", True)
    if (6 <= hora < 7) or (11 <= hora < 14):
        return ("SESIÓN USA", "✅", "Sesión completa de EE.UU. Buen movimiento.", True)
    if 2 <= hora < 6:
        return ("APERTURA EUROPA", "⚠️", "Europa abre: se define la tendencia del día.", True)
    if hora >= 20 or hora < 2:
        return ("SESIÓN ASIA", "🚫", "Solo Asia: poco movimiento. EVITAR operar.", False)
    return ("TARDE / TRANSICIÓN", "🟡", "Entre USA y Asia. Movimiento moderado.", False)

def analisis_avanzado(sym, precio, fng_value):
    trend_data = st.session_state.historical_trend.get(sym, {})
    cambio_30d = trend_data.get("cambio_porcentual", 0)
    tendencia_30d = trend_data.get("tendencia", "NEUTRAL")
    volumen_onchain = get_onchain_volume(sym)
    hist = list(st.session_state.price_history.get(sym, []))
    if len(hist) < 30:
        return "HOLD", 0, "Datos insuficientes", {}
    
    rsi = compute_rsi(hist, 14)
    rsi_pond = 20 if rsi <= 30 else -20 if rsi >= 70 else (50 - rsi) * 0.5
    
    ema_f = compute_ema(hist, st.session_state.ema_fast)
    ema_s = compute_ema(hist, st.session_state.ema_slow)
    ema_pond = 0
    if ema_f and ema_s:
        if ema_f > ema_s: ema_pond = 15
        elif ema_f < ema_s: ema_pond = -15
        if len(hist) > 10:
            ema_prev = compute_ema(hist[:-1], st.session_state.ema_fast)
            if ema_prev and ema_f > ema_prev * 1.001: ema_pond += 5
            elif ema_prev and ema_f < ema_prev * 0.999: ema_pond -= 5
    
    bb_pond = 0
    if len(hist) >= 20:
        sma_20 = sum(hist[-20:]) / 20
        std_20 = statistics.stdev(hist[-20:]) if len(hist[-20:]) > 1 else 0
        if precio > sma_20 + 2*std_20: bb_pond = -15
        elif precio < sma_20 - 2*std_20: bb_pond = 15
    
    macd_pond = 0
    if len(hist) >= 26:
        ema_12 = compute_ema(hist, 12)
        ema_26 = compute_ema(hist, 26)
        if ema_12 and ema_26:
            macd = ema_12 - ema_26
            if len(hist) >= 35:
                macd_hist = []
                for i in range(26, len(hist)):
                    e12 = compute_ema(hist[:i+1], 12)
                    e26 = compute_ema(hist[:i+1], 26)
                    if e12 and e26: macd_hist.append(e12 - e26)
                if len(macd_hist) >= 9:
                    signal = sum(macd_hist[-9:]) / 9
                    if macd > signal: macd_pond = 10
                    elif macd < signal: macd_pond = -10
    
    vol_pond = 10 if volumen_onchain > 2.0 else -5 if volumen_onchain < 0.5 else 0
    tend_pond = 15 if tendencia_30d == "ALCISTA" else -15 if tendencia_30d == "BAJISTA" else 0
    if abs(cambio_30d) > 20: tend_pond *= 1.5
    fng_pond = 10 if fng_value <= 20 else -10 if fng_value >= 80 else (50 - fng_value) * 0.2
    
    atr_pond = 0
    if len(hist) >= 14:
        atr = calcular_atr(hist, 14)
        if atr and precio > 0:
            vol_pct = (atr / precio) * 100
            if vol_pct > 3: atr_pond = -5
            elif vol_pct < 1: atr_pond = 5
    
    puntuacion = rsi_pond + ema_pond + bb_pond + macd_pond + vol_pond + tend_pond + fng_pond + atr_pond
    confianza = abs(puntuacion)
    
    if confianza < 20:
        return "HOLD", confianza, f"Puntuación baja ({confianza:.1f})", {}
    elif puntuacion > 0:
        return "BUY", confianza, f"Señal de compra ({puntuacion:.1f})", {}
    else:
        return "SELL", confianza, f"Señal de venta ({puntuacion:.1f})", {}

# ==================== FIN PARTE 6 ====================
# ==================== PARTE 7: INTERFAZ DE USUARIO ====================
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
    "confianza_umbral": 20,
    "intervalo_actualizacion": 5,
    "inicio_fase": datetime.now().isoformat(),
    "fase_actual": "operando",
    "analisis_anterior": {}
}

for var_name, default_value in required_vars.items():
    if var_name not in st.session_state:
        st.session_state[var_name] = default_value

if "data_loaded" not in st.session_state:
    restore_from_file()
    st.session_state.data_loaded = True

st.title("🧠 Scalping Extremo + Volumen + Tendencia 30d")

# ===== SIDEBAR =====
st.sidebar.header("⚙️ Configuración Principal")
st.session_state.umbral_caida = st.sidebar.number_input("Caída para comprar (%)", min_value=0.001, max_value=50.0, step=0.001, value=float(st.session_state.umbral_caida))
st.session_state.take_profit = st.sidebar.number_input("Take Profit (%)", min_value=0.01, max_value=50.0, step=0.01, value=float(st.session_state.take_profit))
st.session_state.stop_loss = st.sidebar.number_input("Stop Loss (%)", min_value=0.5, max_value=20.0, value=float(st.session_state.stop_loss), step=0.5)
st.session_state.trailing = st.sidebar.number_input("Trailing Stop (%)", min_value=0.2, max_value=5.0, value=float(st.session_state.trailing), step=0.1)
st.session_state.umbral_indicadores_activacion = st.sidebar.number_input("Activar indicadores a partir de ±(%)", min_value=0.1, max_value=20.0, step=0.1, value=float(st.session_state.umbral_indicadores_activacion))

st.sidebar.header("🧠 Modo Aprendizaje")
st.session_state.modo_aprendizaje = st.sidebar.checkbox("✅ Modo aprendizaje activado", value=st.session_state.modo_aprendizaje)

st.sidebar.header("🎯 Probabilidad mínima")
st.session_state.confianza_umbral = st.sidebar.slider(
    "Probabilidad mínima para operar (%)",
    min_value=20, max_value=95, value=st.session_state.confianza_umbral, step=5,
    help="20% = 50% de probabilidad. 40% = 100% de probabilidad."
)

st.sidebar.header("🧠 Indicadores")
st.session_state.rsi_os = st.sidebar.number_input("RSI sobreventa", 20, 40, int(st.session_state.rsi_os), 1)
st.session_state.rsi_ob = st.sidebar.number_input("RSI sobrecompra", 70, 90, int(st.session_state.rsi_ob), 1)
st.session_state.ema_fast = st.sidebar.number_input("EMA rápida", 3, 20, int(st.session_state.ema_fast), 1)
st.session_state.ema_slow = st.sidebar.number_input("EMA lenta", 10, 50, int(st.session_state.ema_slow), 1)

st.sidebar.header("📡 Modo de operación")
st.session_state.modo_solo_senales = st.sidebar.checkbox("🔇 Solo señales (no ejecutar)", value=st.session_state.modo_solo_senales)

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
if st.sidebar.button("💾 Guardar datos ahora"):
    exito, mensaje = save_data()
    if exito:
        st.sidebar.success("✅ Datos guardados")
    else:
        st.sidebar.error(f"❌ Error: {mensaje}")

# ===== CONTROL MANUAL =====
st.sidebar.markdown("---")
st.sidebar.markdown("**🎮 Control Manual**")

if st.sidebar.button("💸 Vender TODO"):
    try:
        btc_price = get_bitso_price("btc_mxn")
        eth_price = get_bitso_price("eth_mxn")
        if btc_price and eth_price:
            vendido = False
            if st.session_state.positions.get("BTC", 0) > 0:
                qty = st.session_state.positions["BTC"]
                net = qty * btc_price * 0.999
                st.session_state.balance += net
                st.session_state.positions["BTC"] = 0
                st.session_state.entry_price["BTC"] = 0
                st.session_state.highest_price["BTC"] = 0
                st.session_state.daily_trades += 1
                msg = f"🔴 VENTA FORZADA BTC | Neto: ${net:.2f}"
                send_telegram(msg)
                st.session_state.trades.append((datetime.now(), msg))
                vendido = True
            if st.session_state.positions.get("ETH", 0) > 0:
                qty = st.session_state.positions["ETH"]
                net = qty * eth_price * 0.999
                st.session_state.balance += net
                st.session_state.positions["ETH"] = 0
                st.session_state.entry_price["ETH"] = 0
                st.session_state.highest_price["ETH"] = 0
                st.session_state.daily_trades += 1
                msg = f"🔴 VENTA FORZADA ETH | Neto: ${net:.2f}"
                send_telegram(msg)
                st.session_state.trades.append((datetime.now(), msg))
                vendido = True
            if vendido:
                save_data()
                st.sidebar.success("✅ Posiciones vendidas")
                st.rerun()
    except Exception as e:
        st.sidebar.error(f"❌ {e}")

def ejecutar_compra_profesional(sym, precio, confianza, razon, tendencia_30d):
    volumen = get_onchain_volume(sym)
    if volumen and volumen < 0.5:
        st.sidebar.warning(f"⚠️ Volumen bajo ({volumen:.2f}B)")
        return
    if confianza >= 40:
        monto, cant = 100.0, 4
    elif confianza >= 30:
        monto, cant = 75.0, 3
    elif confianza >= 20:
        monto, cant = 50.0, 2
    else:
        st.sidebar.warning(f"⚠️ Probabilidad baja")
        return
    
    precio_obj = precio * 0.995
    if st.session_state.positions.get(sym, 0) > 0:
        return
    
    ejecutadas = 0
    if st.session_state.balance >= monto:
        if st.session_state.balance < cant * monto:
            cant = int(st.session_state.balance // monto)
        for i in range(cant):
            if st.session_state.balance >= monto:
                com = monto * 0.001
                qty = (monto - com) / precio_obj
                st.session_state.balance -= monto
                st.session_state.positions[sym] += qty
                if st.session_state.entry_price[sym] == 0:
                    st.session_state.entry_price[sym] = precio_obj
                st.session_state.highest_price[sym] = precio_obj
                st.session_state.daily_trades += 1
                ejecutadas += 1
        if ejecutadas > 0:
            save_data()
            prob = calcular_probabilidad(confianza)
            msg = f"🟢 COMPRA {sym} | {ejecutadas}x${monto:.0f} | ${precio_obj:,.0f} | Prob: {prob:.1f}%"
            send_telegram(msg)
            st.session_state.trades.append((datetime.now(), msg))
            st.sidebar.success(f"✅ {ejecutadas} compras de {sym}")
            st.rerun()

if st.sidebar.button("🟢 Comprar BTC AHORA"):
    precio = get_bitso_price("btc_mxn")
    if precio and st.session_state.positions.get("BTC", 0) == 0:
        ejecutar_compra_profesional("BTC", precio, 50, "Manual", "NEUTRAL")

if st.sidebar.button("🟢 Comprar ETH AHORA"):
    precio = get_bitso_price("eth_mxn")
    if precio and st.session_state.positions.get("ETH", 0) == 0:
        ejecutar_compra_profesional("ETH", precio, 50, "Manual", "NEUTRAL")

# ==================== FIN PARTE 7 ====================
# ==================== PARTE 8: PLACEHOLDERS ====================
tabla_placeholder = st.empty()
info_placeholder = st.empty()
historial_placeholder = st.empty()
estado_placeholder = st.empty()
ultima_senal_placeholder = st.empty()
horario_placeholder = st.empty()
fase_placeholder = st.empty()

def send_signal_telegram_buttons(sym, tipo, precio, razon, confianza, volumen_onchain, cambio_30d, tendencia_30d):
    try:
        prob = calcular_probabilidad(confianza)
        msg = (f"📢 **SEÑAL {tipo} - {sym}**\n"
               f"🎯 Probabilidad: {prob:.1f}%\n"
               f"Precio: ${precio:,.0f}\n"
               f"Razón: {razon}\n"
               f"Volumen: {volumen_onchain:.2f}B USD\n"
               f"Cambio 30d: {cambio_30d:+.2f}%\n"
               f"Tendencia 30d: {tendencia_30d}")
        send_telegram(msg)
        return True
    except:
        return False

# ==================== FIN PARTE 8 ====================
# ==================== PARTE 9: BUCLE INFINITO CON FASE DE APRENDIZAJE ====================
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
    ejecutar_ciclo()

def ejecutar_ciclo():
    """Ciclo completo de análisis y operación."""
    btc = get_bitso_price("btc_mxn")
    eth = get_bitso_price("eth_mxn")
    if btc is None or eth is None:
        tabla_placeholder.error("❌ Error al obtener precios.")
        return

    st.session_state.last_price["BTC"] = btc
    st.session_state.last_price["ETH"] = eth
    st.session_state.price_history["BTC"].append(btc)
    st.session_state.price_history["ETH"].append(eth)

    if st.session_state.ref_price["BTC"] == 0:
        st.session_state.ref_price["BTC"] = btc
        st.session_state.ref_price["ETH"] = eth

    st.session_state.cycle += 1
    
    # Guardar cada 5 ciclos
    if st.session_state.cycle % 5 == 0:
        save_data()

    fng_value, fng_label = get_fear_greed()
    
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

    senal_btc, conf_btc, razon_btc, _ = analisis_avanzado("BTC", btc, fng_value)
    senal_eth, conf_eth, razon_eth, _ = analisis_avanzado("ETH", eth, fng_value)

    prob_btc = calcular_probabilidad(conf_btc)
    prob_eth = calcular_probabilidad(conf_eth)
    prob_umbral = calcular_probabilidad(st.session_state.confianza_umbral)

    # ===== HORARIO ACTUAL =====
    estado_horario, emoji_horario, desc_horario, es_buen_horario = obtener_horario_operacion()

    # ===== CONTROL DE FASE DE APRENDIZAJE (2 DÍAS) =====
    ahora = datetime.now()
    try:
        inicio_fase = datetime.fromisoformat(st.session_state.inicio_fase)
    except:
        inicio_fase = ahora
        st.session_state.inicio_fase = ahora.isoformat()
    
    horas_transcurridas = (ahora - inicio_fase).total_seconds() / 3600
    horas_restantes = max(0, 48 - horas_transcurridas)
    
    # Cambiar a fase "analizando" si pasaron 48h
    if horas_transcurridas >= 48 and st.session_state.fase_actual == "operando":
        st.session_state.fase_actual = "analizando"
        send_telegram("🧠 **FASE DE ANÁLISIS INICIADA**\n\nHan pasado 48h. El bot está analizando sus operaciones para ajustar parámetros.")
    
    # Ejecutar análisis
    if st.session_state.fase_actual == "analizando":
        resultado = analizar_fase_aprendizaje()
        
        if resultado.get("suficiente"):
            st.session_state.analisis_anterior = resultado
            
            mejor_hora_str = f"{resultado['mejor_hora']}:00" if resultado['mejor_hora'] is not None else "N/A"
            peor_hora_str = f"{resultado['peor_hora']}:00" if resultado['peor_hora'] is not None else "N/A"
            
            msg_analisis = (
                f"📊 **ANÁLISIS DE FASE COMPLETADO**\n\n"
                f"📈 Operaciones: {resultado['total_operaciones']}\n"
                f"✅ Ganancias: {resultado['ganancias']}\n"
                f"❌ Pérdidas: {resultado['perdidas']}\n"
                f"🎯 Win Rate: {resultado['win_rate']:.1f}%\n"
                f"⏰ Mejor hora: {mejor_hora_str}\n"
                f"⏰ Peor hora: {peor_hora_str}\n\n"
                f"**Ajustes aplicados:**\n"
                + "\n".join([f"• {a}" for a in resultado['ajustes_aplicados']])
            )
            send_telegram(msg_analisis)
        
        # Reiniciar fase
        st.session_state.inicio_fase = ahora.isoformat()
        st.session_state.fase_actual = "operando"
        st.session_state.trades = []
        st.session_state.rendimiento = {
            "BTC": {"ganadas": 0, "perdidas": 0, "total": 0, "ultimas_10": []},
            "ETH": {"ganadas": 0, "perdidas": 0, "total": 0, "ultimas_10": []}
        }
        save_data()
        send_telegram("🔄 **NUEVA FASE DE 2 DÍAS INICIADA**\nEl bot operará con los parámetros ajustados.")
        st.rerun()

    # ===== TABLA =====
    tabla_placeholder.subheader("📊 Señales + Volumen + Tendencia 30d")
    tabla_placeholder.table({
        "Moneda": ["Bitcoin", "Ethereum"],
        "Precio MXN": [f"${btc:,.0f}", f"${eth:,.0f}"],
        "Cambio": [f"{cambio_btc:+.2f}%", f"{cambio_eth:+.2f}%"],
        "Tendencia": [st.session_state.tendencia["BTC"], st.session_state.tendencia["ETH"]],
        "Señal": [senal_btc, senal_eth],
        "Prob. asertividad": [f"{prob_btc:.1f}%", f"{prob_eth:.1f}%"],
        "Umbral mín.": [f"{prob_umbral:.1f}%", f"{prob_umbral:.1f}%"],
        "Volumen 24h": [
            f"{onchain_vol_btc:.2f}B" if onchain_vol_btc else "N/A",
            f"{onchain_vol_eth:.2f}B" if onchain_vol_eth else "N/A"
        ],
        "Tendencia 30d": [
            trend_btc.get("tendencia", "N/A") if trend_btc else "N/A",
            trend_eth.get("tendencia", "N/A") if trend_eth else "N/A"
        ]
    })

    # ===== HORARIO =====
    horario_texto = f"{emoji_horario} **{estado_horario}** → {desc_horario}"
    if es_buen_horario:
        horario_placeholder.success(horario_texto)
    else:
        horario_placeholder.warning(horario_texto)

    # ===== FASE =====
    if st.session_state.fase_actual == "operando":
        fase_placeholder.info(f"📅 **FASE OPERATIVA** — Próximo análisis en {horas_restantes:.1f} horas")
    else:
        fase_placeholder.warning("🧠 **ANALIZANDO FASE**...")

    # ===== ALERTA TELEGRAM CAMBIO DE SESIÓN =====
    if "ultimo_horario_alerta" not in st.session_state:
        st.session_state.ultimo_horario_alerta = None

    if st.session_state.ultimo_horario_alerta != estado_horario:
        tz_mexico = timezone(timedelta(hours=-6))
        hora_mx = datetime.now(tz_mexico).strftime('%H:%M')
        if es_buen_horario:
            msg_horario = (
                f"✅ **BUEN HORARIO PARA OPERAR**\n\n"
                f"{emoji_horario} **{estado_horario}**\n"
                f"{desc_horario}\n\n"
                f"📍 Hora México: {hora_mx}"
            )
        else:
            msg_horario = (
                f"⚠️ **CAMBIO DE SESIÓN**\n\n"
                f"{emoji_horario} **{estado_horario}**\n"
                f"{desc_horario}\n\n"
                f"📍 Hora México: {hora_mx}"
            )
        send_telegram(msg_horario)
        st.session_state.ultimo_horario_alerta = estado_horario

    # ===== INFO =====
    info_texto = (
        f"Ciclo: {st.session_state.cycle} | "
        f"Caída: {st.session_state.umbral_caida}% | "
        f"TP: {st.session_state.take_profit}% | SL: {st.session_state.stop_loss}% | "
        f"F&G: {fng_value}/100 ({fng_label}) | "
        f"Aprendizaje: {'✅' if st.session_state.modo_aprendizaje else '❌'} | "
        f"Prob. mínima: {prob_umbral:.1f}% | "
        f"Trades fase: {len(st.session_state.trades)}"
    )
    info_placeholder.caption(info_texto)

    # ===== CARTERA =====
    total_val = st.session_state.balance
    for s in ["BTC", "ETH"]:
        p = st.session_state.last_price.get(s, 0)
        q = st.session_state.positions.get(s, 0)
        if q > 0 and p > 0:
            total_val += q * p
    saldo_placeholder.metric("Saldo MXN", f"${st.session_state.balance:,.2f}")
    total_placeholder.metric("Valor total", f"${total_val:,.2f}")
    ops_placeholder.metric("Ops hoy", st.session_state.daily_trades)

    # ===== HISTORIAL =====
    historial_placeholder.subheader(f"📜 Historial (últimas 10 de {len(st.session_state.trades)})")
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

    # ===== APRENDIZAJE PARAMÉTRICO =====
    if st.session_state.cycle % 5 == 0 and st.session_state.modo_aprendizaje:
        for sym in ["BTC", "ETH"]:
            eval_rend = evaluar_rendimiento(sym)
            if eval_rend["accion"] == "AUMENTAR_RIESGO":
                st.session_state.umbral_caida = min(0.05, st.session_state.umbral_caida * 1.2)
                st.session_state.take_profit = min(0.10, st.session_state.take_profit * 1.1)
            elif eval_rend["accion"] == "REDUCIR_RIESGO":
                st.session_state.umbral_caida = max(0.001, st.session_state.umbral_caida * 0.8)
                st.session_state.take_profit = max(0.01, st.session_state.take_profit * 0.9)

    # ===== OPERACIONES =====
    for sym, precio, senal, conf_senal, razon in [
        ("BTC", btc, senal_btc, conf_btc, razon_btc),
        ("ETH", eth, senal_eth, conf_eth, razon_eth)
    ]:
        tendencia_30d = st.session_state.historical_trend.get(sym, {}).get("tendencia", "NEUTRAL")
        umbral_conf = st.session_state.confianza_umbral
        
        st.session_state.ultima_senal = {
            "sym": sym, "accion": senal, "razon": razon,
            "confianza_senal": conf_senal, "precio": precio,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "tendencia_30d": tendencia_30d, "umbral": umbral_conf
        }
        
        # Solo opera si: NO está en modo solo señales Y está en buen horario Y está en fase operativa
        if (not st.session_state.modo_solo_senales 
            and es_buen_horario 
            and st.session_state.fase_actual == "operando"):
            
            if senal == "BUY" and conf_senal > umbral_conf:
                if st.session_state.positions.get(sym, 0) == 0:
                    if tendencia_30d != "BAJISTA":
                        volumen = onchain_vol_btc if sym == "BTC" else onchain_vol_eth
                        if volumen is None or volumen >= 0.5:
                            ejecutar_compra_profesional(sym, precio, conf_senal, razon, tendencia_30d)
            
            elif senal == "SELL" and conf_senal > umbral_conf:
                if st.session_state.positions.get(sym, 0) > 0:
                    if tendencia_30d != "ALCISTA":
                        qty = st.session_state.positions[sym]
                        net = qty * precio * 0.999
                        st.session_state.balance += net
                        st.session_state.positions[sym] = 0
                        st.session_state.entry_price[sym] = 0
                        st.session_state.highest_price[sym] = 0
                        st.session_state.daily_trades += 1
                        prob = calcular_probabilidad(conf_senal)
                        msg = f"🔴 VENTA {sym} | Neto: ${net:.2f} | Prob: {prob:.1f}%"
                        send_telegram(msg)
                        st.session_state.trades.append((datetime.now(), msg))
                        save_data()
                        st.sidebar.success(f"✅ Venta de {sym}")
        
        # Alertas Telegram
        if conf_senal > umbral_conf and senal != "HOLD":
            if not hasattr(st.session_state, f'ultima_senal_{sym}'):
                setattr(st.session_state, f'ultima_senal_{sym}', 0)
            if st.session_state.cycle - getattr(st.session_state, f'ultima_senal_{sym}', 0) > 10:
                volumen_onchain = onchain_vol_btc if sym == "BTC" else onchain_vol_eth
                cambio_30d = st.session_state.historical_trend.get(sym, {}).get("cambio_porcentual", 0)
                send_signal_telegram_buttons(sym, senal, precio, razon, conf_senal, volumen_onchain, cambio_30d, tendencia_30d)
                setattr(st.session_state, f'ultima_senal_{sym}', st.session_state.cycle)

    # ===== ÚLTIMA SEÑAL =====
    if hasattr(st.session_state, 'ultima_senal'):
        s = st.session_state.ultima_senal
        prob = calcular_probabilidad(s.get('confianza_senal', 0))
        ultima_senal_placeholder.info(
            f"📊 {s['sym']} → {s['accion']} | Prob: {prob:.1f}% | "
            f"Razón: {s['razon']} | Tend.30d: {s.get('tendencia_30d', 'N/A')}"
        )

    estado_placeholder.info(
        f"🔹 Indicadores: BTC={st.session_state.indicadores_activados.get('BTC')} | "
        f"ETH={st.session_state.indicadores_activados.get('ETH')} | "
        f"Modo: {'🔇 Solo señales' if st.session_state.modo_solo_senales else '✅ Auto'} | "
        f"Fase: {st.session_state.fase_actual}"
    )

# ===== PRIMER CICLO + BUCLE INFINITO =====
ejecutar_ciclo()

while True:
    time.sleep(st.session_state.intervalo_actualizacion)
    ejecutar_ciclo()

# ==================== FIN PARTE 9 ====================
