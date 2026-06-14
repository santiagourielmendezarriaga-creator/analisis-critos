import streamlit as st
import requests
import time
import json
import os
from datetime import datetime
from collections import deque

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
    """Obtiene precio en MXN desde API pública de Bitso"""
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

def get_volume(book="btc_mxn"):
    """Obtiene volumen de las últimas 24h desde API pública de Bitso"""
    try:
        url = f"https://api.bitso.com/api/v3/ticker/?book={book}"
        resp = requests.get(url, timeout=5)
        if resp.status_code != 200:
            return None
        data = resp.json()
        payload = data.get("payload")
        if not payload:
            return None
        volume = payload.get("volume")
        if volume:
            return float(volume)
        return None
    except:
        return None

def get_fear_greed():
    """Obtiene índice de Miedo y Avaricia"""
    try:
        resp = requests.get("https://api.alternative.me/fng/", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return int(data['data'][0]['value']), data['data'][0]['value_classification']
    except:
        pass
    return 50, "Neutral"

def get_macro_event_adjustment():
    """
    Devuelve un factor de ajuste (entre 0 y 1) basado en eventos macroeconómicos.
    Si hay un evento relevante en las próximas 48 horas, reduce el tamaño de la operación.
    """
    # Eventos macro relevantes para junio 2026
    macro_events = {
        "2026-06-18": "Fed Rate Decision",   # Próximo jueves
        "2026-06-19": "BOJ Rate Decision"
    }
    today = datetime.now().date()
    for event_date, event_name in macro_events.items():
        event_dt = datetime.strptime(event_date, "%Y-%m-%d").date()
        days_until = (event_dt - today).days
        if 0 <= days_until <= 2:
            # Si hay evento en los próximos 2 días, reducimos el tamaño de la orden
            return 0.5  # reduce a la mitad
    return 1.0

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
    # 1. Cambio porcentual
    ref = prices[0]
    current = prices[-1]
    change_pct = (current - ref) / ref * 100 if ref != 0 else 0
    if change_pct >= threshold:
        signal_change = "BUY"
    elif change_pct <= -threshold:
        signal_change = "SELL"
    else:
        signal_change = "HOLD"

    # 2. EMA cruce
    ema_f = compute_ema(prices, ema_fast)
    ema_s = compute_ema(prices, ema_slow)
    if ema_f is None or ema_s is None:
        signal_ema = "HOLD"
    else:
        signal_ema = "BUY" if ema_f > ema_s else "SELL" if ema_f < ema_s else "HOLD"

    # 3. RSI
    rsi = compute_rsi(prices)
    if rsi <= rsi_os:
        signal_rsi = "BUY"
    elif rsi >= rsi_ob:
        signal_rsi = "SELL"
    else:
        signal_rsi = "HOLD"

    # 4. Sentimiento (Fear & Greed)
    if fng_value <= 20:
        signal_fng = "BUY"   # Miedo extremo => oportunidad de compra
    elif fng_value >= 80:
        signal_fng = "SELL"  # Avaricia extrema => oportunidad de venta
    else:
        signal_fng = "HOLD"

    # Votación ponderada: las señales técnicas tienen más peso que el sentimiento
    # Asignamos pesos: cambio 25%, EMA 25%, RSI 25%, Sentimiento 25%
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
        "highest_price": st.session_state.highest_price,
        "cycle": st.session_state.cycle,
        "price_history": {k: list(v) for k, v in st.session_state.price_history.items()}
    }
    with open(STATE_FILE, "w") as f:
        json.dump(to_save, f)

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
            data["trades"] = [(datetime.fromisoformat(ts), msg) for ts, msg in data["trades"]]
            data["price_history"] = {k: deque(v, maxlen=200) for k, v in data.get("price_history", {}).items()}
            for key in ["highest_price", "entry_price", "ref_price", "last_price", "last_action"]:
                if key not in data:
                    data[key] = {"BTC": 0.0, "ETH": 0.0} if key != "last_action" else {"BTC": None, "ETH": None}
            if "cycle" not in data:
                data["cycle"] = 0
            return data
        except:
            pass
    return None

# ==================== INTERFAZ ====================
st.set_page_config(page_title="Bot con Estrategia Experta e IA", layout="wide")
st.title("📊 Bot de Trading con Estrategia Experta (RSI, EMA, Fear & Greed)")

# Sidebar: Configuración general
st.sidebar.header("⚙️ Configuración General")
refresh = st.sidebar.slider("Intervalo (segundos)", 5, 30, 10)
umbral = st.sidebar.number_input("Umbral de entrada (%)", 0.005, 1.0, 0.01, 0.005)
rsi_os = st.sidebar.number_input("RSI sobreventa", 20, 40, 30)
rsi_ob = st.sidebar.number_input("RSI sobrecompra", 60, 80, 70)
ema_fast = st.sidebar.number_input("EMA rápida (periodos)", 3, 20, 5)
ema_slow = st.sidebar.number_input("EMA lenta (periodos)", 10, 50, 20)

# Sidebar: Gestión de riesgo
st.sidebar.header("🛡️ Gestión de Riesgo")
stop_loss = st.sidebar.number_input("Stop Loss fijo (%)", 0.5, 10.0, 2.0, 0.5)
take_profit = st.sidebar.number_input("Take Profit fijo (%)", 0.5, 20.0, 5.0, 0.5)
trailing = st.sidebar.number_input("Trailing Stop (%)", 0.2, 5.0, 1.0, 0.1)

# Sidebar: Análisis Experto (NUEVA SECCIÓN)
st.sidebar.header("🧠 Análisis de Expertos (Basado en la 'Guía')")
expert_score = st.sidebar.slider("Puntaje de tendencia (0=Muy Bajista, 100=Muy Alcista)", 0, 100, 50, 5)
expert_comment = st.sidebar.text_area("Comentario / Estrategia", height=100, key="expert_comment")
if st.sidebar.button("Actualizar Análisis Experto"):
    st.success("Análisis de expertos actualizado. El bot lo usará en su próxima decisión.")

# Sidebar: Estado de la cartera (se actualizará dinámicamente)
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
    send_telegram("🧪 Bot con Estrategia Experta e IA - activo")
    st.success("Enviado")

# Contenedores principales
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
        st.session_state.price_history = saved.get("price_history", {})
        for sym in ["BTC", "ETH"]:
            if sym not in st.session_state.price_history:
                st.session_state.price_history[sym] = deque(maxlen=200)
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
        st.session_state.price_history = {"BTC": deque(maxlen=200), "ETH": deque(maxlen=200)}

# ==================== BUCLE PRINCIPAL ====================
while st.session_state.running:
    # 1. Obtener datos del mercado
    btc = get_bitso_price("btc_mxn")
    eth = get_bitso_price("eth_mxn")
    btc_vol = get_volume("btc_mxn")
    eth_vol = get_volume("eth_mxn")
    if btc is None or eth is None:
        tabla_placeholder.error("❌ Error al obtener precios de Bitso. Reintentando...")
        time.sleep(refresh)
        continue

    # 2. Actualizar precios e historial
    st.session_state.last_price["BTC"] = btc
    st.session_state.last_price["ETH"] = eth
    st.session_state.price_history["BTC"].append(btc)
    st.session_state.price_history["ETH"].append(eth)

    if st.session_state.ref_price["BTC"] == 0:
        st.session_state.ref_price["BTC"] = btc
        st.session_state.ref_price["ETH"] = eth

    st.session_state.cycle += 1

    # 3. Obtener datos macro (sentimiento y eventos)
    fng_value, fng_label = get_fear_greed()
    macro_factor = get_macro_event_adjustment()

    # 4. Calcular variación desde referencia (solo para mostrar)
    var_btc = (btc - st.session_state.ref_price["BTC"]) / st.session_state.ref_price["BTC"] * 100
    var_eth = (eth - st.session_state.ref_price["ETH"]) / st.session_state.ref_price["ETH"] * 100

    # 5. Mostrar tabla informativa
    tabla_placeholder.subheader("📊 Señales en Vivo")
    tabla_placeholder.table({
        "Moneda": ["Bitcoin", "Ethereum"],
        "Precio MXN": [f"${btc:,.0f}", f"${eth:,.0f}"],
        "Volumen 24h": [f"{btc_vol:,.0f}" if btc_vol else "N/A", f"{eth_vol:,.0f}" if eth_vol else "N/A"],
        "Var desde inicio": [f"{var_btc:+.2f}%", f"{var_eth:+.2f}%"],
        "Señal (solo info)": ["COMPRAR" if var_btc >= umbral else "VENDER" if var_btc <= -umbral else "MANTENER",
                              "COMPRAR" if var_eth >= umbral else "VENDER" if var_eth <= -umbral else "MANTENER"]
    })
    info_placeholder.caption(f"Ciclo: {st.session_state.cycle} | Umbral: {umbral}% | SL: {stop_loss}% | TP: {take_profit}% | Trailing: {trailing}% | Fear & Greed: {fng_value}/100 ({fng_label}) | Macro Ajuste: {macro_factor:.2f}")

    # 6. Actualizar sidebar
    total_val = st.session_state.balance
    for s in ["BTC", "ETH"]:
        p = st.session_state.last_price.get(s, 0)
        q = st.session_state.positions.get(s, 0)
        if q > 0 and p > 0:
            total_val += q * p
    saldo_placeholder.metric("Saldo MXN", f"${st.session_state.balance:,.2f}")
    total_placeholder.metric("Valor total", f"${total_val:,.2f}")
    ops_placeholder.metric("Ops hoy", st.session_state.daily_trades)

    # 7. Mostrar historial
    historial_placeholder.subheader("📜 Historial")
    if st.session_state.trades:
        txt = ""
        for ts, msg in reversed(st.session_state.trades[-10:]):
            txt += f"{ts.strftime('%H:%M:%S')} - {msg[:60]}\n"
        historial_placeholder.text(txt)
    else:
        historial_placeholder.text("Sin operaciones aún.")

    # ==================== LÓGICA DE TRADING MEJORADA ====================
    # Reset diario
    hoy = datetime.now().day
    if hoy != st.session_state.last_day:
        st.session_state.daily_trades = 0
        st.session_state.last_day = hoy

    for sym, precio in [("BTC", btc), ("ETH", eth)]:
        hist = list(st.session_state.price_history[sym])
        # Señal autónoma del bot
        if len(hist) >= max(ema_slow, 15):
            signal_autonomous, rsi_val = get_enhanced_signal(hist, umbral, rsi_os, rsi_ob, ema_fast, ema_slow, fng_value)
        else:
            signal_autonomous = "HOLD"
            rsi_val = 50

        # Calcular señal final combinando análisis autónomo con análisis experto
        # La señal experto se calcula a partir del expert_score
        if expert_score >= 80:
            signal_expert = "BUY"
        elif expert_score <= 20:
            signal_expert = "SELL"
        else:
            signal_expert = "HOLD"

        # Regla de decisión final por mayoría ponderada
        # Si el análisis experto es muy fuerte (score >= 80 o <= 20), fuerza la señal
        if expert_score >= 80:
            senal = "BUY"
            razon_extra = f"Señal forzada por análisis experto (Puntaje: {expert_score})"
        elif expert_score <= 20:
            senal = "SELL"
            razon_extra = f"Señal forzada por análisis experto (Puntaje: {expert_score})"
        else:
            # Votación ponderada
            buy_votes = 0
            sell_votes = 0
            # Voto del análisis autónomo (peso 40%)
            if signal_autonomous == "BUY": buy_votes += 40
            elif signal_autonomous == "SELL": sell_votes += 40
            # Voto del análisis experto (peso 35%)
            if signal_expert == "BUY": buy_votes += 35
            elif signal_expert == "SELL": sell_votes += 35
            # Voto del Fear & Greed (peso 25%)
            if fng_value <= 20: buy_votes += 25
            elif fng_value >= 80: sell_votes += 25
            if buy_votes > sell_votes:
                senal = "BUY"
                razon_extra = f"Ponderado (Autónomo: {signal_autonomous}, Experto: {signal_expert}, Fear & Greed: {fng_value})"
            elif sell_votes > buy_votes:
                senal = "SELL"
                razon_extra = f"Ponderado (Autónomo: {signal_autonomous}, Experto: {signal_expert}, Fear & Greed: {fng_value})"
            else:
                senal = "HOLD"
                razon_extra = "Votación empatada"

        # Gestión de posición y riesgos
        pos = st.session_state.positions.get(sym, 0)
        entrada = st.session_state.entry_price.get(sym, 0)
        highest = st.session_state.highest_price.get(sym, precio)
        razon = ""
        accion = None

        # Actualizar máximo para trailing stop
        if precio > highest:
            st.session_state.highest_price[sym] = precio
            highest = precio

        # Condiciones de salida (prioridad)
        if pos > 0 and entrada > 0:
            ganancia = (precio - entrada) / entrada * 100
            # Take Profit
            if ganancia >= take_profit:
                accion = "SELL"
                razon = f"Take Profit ({take_profit}%)"
            # Stop Loss
            elif ganancia <= -stop_loss:
                accion = "SELL"
                razon = f"Stop Loss ({stop_loss}%)"
            # Trailing Stop
            elif highest > entrada:
                caida = (precio - highest) / highest * 100
                if caida <= -trailing:
                    accion = "SELL"
                    razon = f"Trailing Stop ({trailing}%) desde máximo ${highest:,.2f}"

        # Si no hay salida, usar la señal combinada
        if accion is None:
            if senal == "BUY" and pos == 0:
                accion = "BUY"
            elif senal == "SELL" and pos > 0:
                accion = "SELL"
                if razon_extra:
                    razon = razon_extra

        # Ejecutar orden
        last_act = st.session_state.last_action.get(sym)
        if accion and accion != last_act and st.session_state.daily_trades < 20:
            # Ajustar tamaño por macro eventos
            position_multiplier = macro_factor
            amount = min(500.0, st.session_state.balance) * position_multiplier
            if accion == "BUY" and amount > 0:
                eff = precio * (1 + 0.05/100)
                com = amount * 0.1/100
                qty = (amount - com) / eff
                st.session_state.balance -= amount
                st.session_state.positions[sym] = qty
                st.session_state.entry_price[sym] = eff
                st.session_state.highest_price[sym] = eff
                st.session_state.daily_trades += 1
                msg = (f"🟢 *COMPRA* {sym}\n"
                       f"Cantidad: {qty:.6f}\n"
                       f"Precio: ${precio:,.2f}\n"
                       f"Efectivo: ${eff:,.2f}\n"
                       f"Comisión: ${com:.2f}\n"
                       f"Saldo: ${st.session_state.balance:.2f}\n"
                       f"RSI: {rsi_val:.1f}\n"
                       f"Fear & Greed: {fng_value}\n"
                       f"Razón: {razon_extra}\n"
                       f"Comentario Experto: {expert_comment[:50] if expert_comment else 'N/A'}")
                send_telegram(msg)
                st.session_state.trades.append((datetime.now(), msg))
                save_state()
                st.session_state.last_action[sym] = accion
            elif accion == "SELL" and pos > 0:
                qty = pos
                eff = precio * (1 - 0.05/100)
                gross = qty * eff
                com = gross * 0.1/100
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
