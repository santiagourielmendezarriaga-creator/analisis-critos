import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import time
from datetime import datetime

# ==================== CONFIGURACIÓN TELEGRAM ====================
TELEGRAM_TOKEN = "8532857017:AAHwLhRnM3oC6TbgFFKAEmQnZVoo6JD_esQ"
TELEGRAM_CHAT_ID = "5835990242"  # tu ID personal

def enviar_telegram(mensaje):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": mensaje,
            "parse_mode": "HTML"
        }
        response = requests.post(url, data=data, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"Error al enviar: {e}")
        return False

# ==================== LISTA DE CRIPTOMONEDAS A VIGILAR ====================
CRIPTO_CONFIG = {
    "Bitcoin": {"id": "bitcoin", "ultima_senal": ""},
    "Ethereum": {"id": "ethereum", "ultima_senal": ""},
    "Solana": {"id": "solana", "ultima_senal": ""},
    "Dogecoin": {"id": "dogecoin", "ultima_senal": ""},
    "Cardano": {"id": "cardano", "ultima_senal": ""},
    "XRP": {"id": "ripple", "ultima_senal": ""}
}

# ==================== FUNCIONES ====================
def obtener_precio_individual(coin_id):
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd&include_24hr_change=true"
        response = requests.get(url, timeout=10)
        data = response.json()
        if coin_id in data:
            precio = data[coin_id]["usd"]
            cambio = data[coin_id].get("usd_24h_change", 0)
            return precio, cambio
        return None, None
    except:
        return None, None

def obtener_fear_greed():
    try:
        url = "https://api.alternative.me/fng/"
        response = requests.get(url, timeout=10)
        data = response.json()
        valor = int(data["data"][0]["value"])
        clasificacion = data["data"][0]["value_classification"]
        return valor, clasificacion
    except:
        return None, None

def calcular_senal(precio, cambio, fng_valor, historial):
    puntaje = 50
    if fng_valor:
        if fng_valor < 25:
            puntaje += 25
        elif fng_valor < 40:
            puntaje += 15
        elif fng_valor > 75:
            puntaje -= 25
        elif fng_valor > 60:
            puntaje -= 15
    if cambio:
        if cambio > 3:
            puntaje += 10
        elif cambio > 1:
            puntaje += 5
        elif cambio < -3:
            puntaje -= 10
        elif cambio < -1:
            puntaje -= 5
    if len(historial) >= 5:
        promedio = sum(historial[-5:]) / 5
        if precio > promedio:
            puntaje += 10
        else:
            puntaje -= 10
    puntaje = max(0, min(100, puntaje))
    if puntaje >= 65:
        return "🟢 COMPRAR", puntaje
    elif puntaje >= 55:
        return "🟡 CONSIDERAR COMPRA", puntaje
    elif puntaje <= 35:
        return "🔴 VENDER", puntaje
    elif puntaje <= 45:
        return "🟠 CONSIDERAR VENTA", puntaje
    else:
        return "⚪ MANTENER", puntaje

# ==================== CONFIGURACIÓN STREAMLIT ====================
st.set_page_config(page_title="CriptoAlertas Múltiples", layout="wide")
st.title("🪙 CriptoAnalizador Multi-Monitoreo con Alertas Telegram")

st.sidebar.header("⚙️ Configuración")
intervalo = st.sidebar.slider("Actualizar cada (segundos)", 15, 60, 30)
st.sidebar.success("📱 Alertas activadas para: " + ", ".join(CRIPTO_CONFIG.keys()))

# Inicializar estado
if "historiales" not in st.session_state:
    st.session_state.historiales = {nombre: [] for nombre in CRIPTO_CONFIG.keys()}
if "ultimo_precio" not in st.session_state:
    st.session_state.ultimo_precio = {}

# Mostrar tabla
placeholder_tabla = st.empty()
ultima_actualizacion = st.empty()

# Botón de inicio
if st.sidebar.button("▶️ INICIAR MONITOREO MULTI", type="primary"):
    st.success("Monitoreando todas las criptomonedas...")
    fng_valor, fng_texto = obtener_fear_greed()
    if not fng_valor:
        fng_valor, fng_texto = 50, "Neutral"
    
    while True:
        filas = []
        for nombre, config in CRIPTO_CONFIG.items():
            coin_id = config["id"]
            precio, cambio = obtener_precio_individual(coin_id)
            if precio is None:
                continue
            
            st.session_state.historiales[nombre].append(precio)
            if len(st.session_state.historiales[nombre]) > 30:
                st.session_state.historiales[nombre] = st.session_state.historiales[nombre][-30:]
            
            senal, puntaje = calcular_senal(precio, cambio, fng_valor, st.session_state.historiales[nombre])
            
            # Alerta si cambió a COMPRAR o VENDER
            if senal != config["ultima_senal"] and senal in ["🟢 COMPRAR", "🔴 VENDER"]:
                mensaje = f"""
🚨 <b>ALERTA CRIPTO</b> 🚨

🪙 <b>{nombre}</b>
📊 <b>{senal}</b>
💰 Precio: ${precio:,.2f}
📈 Cambio 24h: {cambio:+.2f}%
😨 Fear & Greed: {fng_valor}/100 ({fng_texto})
📊 Puntaje: {puntaje}/100
                """
                enviar_telegram(mensaje)
                config["ultima_senal"] = senal
            
            # Movimiento brusco
            ultimo = st.session_state.ultimo_precio.get(nombre, precio)
            if ultimo > 0:
                variacion = abs(precio - ultimo) / ultimo * 100
                if variacion > 5:
                    direccion = "⬆️ SUBIÓ" if precio > ultimo else "⬇️ BAJÓ"
                    enviar_telegram(f"⚠️ <b>MOVIMIENTO BRUSCO</b>\n🪙 {nombre}\n{direccion} {variacion:.1f}%\n💰 Ahora: ${precio:,.2f}")
            st.session_state.ultimo_precio[nombre] = precio
            
            filas.append({
                "Cripto": nombre,
                "Precio": f"${precio:,.2f}",
                "24h %": f"{cambio:+.2f}%",
                "Señal": senal,
                "Puntaje": f"{puntaje}/100"
            })
        
        placeholder_tabla.dataframe(pd.DataFrame(filas), use_container_width=True)
        ultima_actualizacion.info(f"🕐 Actualizado: {datetime.now().strftime('%H:%M:%S')} | Fear & Greed: {fng_valor}/100 ({fng_texto})")
        
        time.sleep(intervalo)
        st.rerun()
else:
    st.info("👈 Presiona 'INICIAR MONITOREO MULTI' para empezar a recibir alertas de todas las criptomonedas.")
import requests
import time

TELEGRAM_TOKEN = "8532857017:AAHwLhRnM3oC6TbgFFKAEmQnZVoo6JD_esQ"
URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/"

def obtener_actualizaciones(offset=None):
    url = URL + "getUpdates"
    params = {"timeout": 30, "offset": offset}
    try:
        response = requests.get(url, params=params)
        return response.json().get("result", [])
    except:
        return []

def enviar_mensaje(chat_id, texto):
    url = URL + "sendMessage"
    data = {"chat_id": chat_id, "text": texto, "parse_mode": "HTML"}
    try:
        requests.post(url, data=data)
    except:
        pass

def obtener_precio_cripto(consulta):
    mapa = {
        "bitcoin": "bitcoin", "btc": "bitcoin",
        "ethereum": "ethereum", "eth": "ethereum",
        "solana": "solana", "sol": "solana",
        "dogecoin": "dogecoin", "doge": "dogecoin",
        "cardano": "cardano", "ada": "cardano",
        "ripple": "ripple", "xrp": "ripple"
    }
    coin_id = mapa.get(consulta.lower().strip())
    if not coin_id:
        return None, None
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd&include_24hr_change=true"
        response = requests.get(url, timeout=10)
        data = response.json()
        if coin_id in data:
            precio = data[coin_id]["usd"]
            cambio = data[coin_id].get("usd_24h_change", 0)
            return precio, cambio
        return None, None
    except:
        return None, None

def obtener_fear_greed():
    try:
        url = "https://api.alternative.me/fng/"
        response = requests.get(url, timeout=10)
        data = response.json()
        valor = int(data["data"][0]["value"])
        clasificacion = data["data"][0]["value_classification"]
        return valor, clasificacion
    except:
        return None, None

def manejar_comando(chat_id, texto):
    if texto == "/start":
        ayuda = (
            "🟢 <b>Bot de Alertas Cripto activo</b>\n\n"
            "Comandos disponibles:\n"
            "/precio <cripto> - Ej: /precio Bitcoin, /precio ETH\n"
            "/fear - Muestra el índice de Miedo y Avaricia\n"
            "/ayuda - Muestra esta ayuda"
        )
        enviar_mensaje(chat_id, ayuda)
    elif texto.startswith("/precio"):
        partes = texto.split(maxsplit=1)
        if len(partes) < 2:
            enviar_mensaje(chat_id, "Uso: /precio <nombre o símbolo>\nEj: /precio Bitcoin o /precio BTC")
            return
        consulta = partes[1]
        precio, cambio = obtener_precio_cripto(consulta)
        if precio is None:
            enviar_mensaje(chat_id, f"⚠️ No encontré '{consulta}'. Prueba con: Bitcoin, Ethereum, Solana, Dogecoin, Cardano, XRP o sus símbolos (BTC, ETH, etc.)")
        else:
            respuesta = f"💰 <b>{consulta.upper()}</b>\n💵 Precio: ${precio:,.2f}\n📈 24h: {cambio:+.2f}%"
            enviar_mensaje(chat_id, respuesta)
    elif texto == "/fear":
        valor, texto_fng = obtener_fear_greed()
        if valor is None:
            enviar_mensaje(chat_id, "No se pudo obtener el índice ahora.")
        else:
            emoji = "😨" if valor < 25 else "😟" if valor < 40 else "😐" if valor < 60 else "😊" if valor < 75 else "🤑"
            enviar_mensaje(chat_id, f"{emoji} <b>Fear & Greed Index</b>\nValor: {valor}/100\nEstado: {texto_fng}")
    elif texto == "/ayuda":
        ayuda = (
            "<b>Comandos disponibles:</b>\n"
            "/precio Bitcoin - Precio de Bitcoin\n"
            "/precio ETH - Precio de Ethereum\n"
            "/fear - Índice de Miedo/Avaricia\n"
            "/ayuda - Esta ayuda"
            import requests
import pandas as pd
from datetime import datetime, timezone, timedelta
import time

# --- CONFIGURACIÓN - ¡CAMBIA ESTOS VALORES! ---
TU_CHAT_ID = "5835990242"  # Tu Chat ID de Telegram
TU_TOKEN = "8532857017:AAHwLhRnM3oC6TbgFFKAEmQnZVoo6JD_esQ"  # Token de tu bot de Telegram
# ---------------------------------------------

# Configuración de Zona Horaria
UTC_MINUS_6 = timezone(timedelta(hours=-6))

def enviar_alerta_telegram(mensaje):
    """Envía un mensaje a tu Telegram usando el bot."""
    url = f"https://api.telegram.org/bot{TU_TOKEN}/sendMessage"
    payload = {
        "chat_id": TU_CHAT_ID,
        "text": mensaje,
        "parse_mode": "HTML"
    }
    try:
        respuesta = requests.post(url, json=payload, timeout=10)
        if respuesta.status_code != 200:
            print(f"Error al enviar mensaje: {respuesta.text}")
    except Exception as e:
        print(f"Error de conexión con Telegram: {e}")

def obtener_datos_ohlc(coin_id, vs_currency='usd', days=1):
    """
    Obtiene los datos OHLC (Open, High, Low, Close) de las últimas 'days' horas.
    La granularidad es automática: para 1 día, serán datos horarios.
    """
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
    params = {
        'vs_currency': vs_currency,
        'days': days
    }
    try:
        respuesta = requests.get(url, params=params, timeout=15)
        respuesta.raise_for_status()
        datos = respuesta.json()
        if not datos:
            print(f"No se pudieron obtener datos OHLC para {coin_id}")
            return None

        # Crear el DataFrame con los datos
        df = pd.DataFrame(datos, columns=['timestamp', 'open', 'high', 'low', 'close'])

        # Convertir el timestamp (milisegundos) a datetime en UTC y luego a UTC-6 (CDMX)
        df['timestamp_utc'] = pd.to_datetime(df['timestamp'], unit='ms')
        df['timestamp_cdmx'] = df['timestamp_utc'].dt.tz_localize('UTC').dt.tz_convert(UTC_MINUS_6)

        # Extraer la hora en formato 24h (0-23) en horario de CDMX
        df['hora_cdmx'] = df['timestamp_cdmx'].dt.hour

        return df
    except requests.exceptions.RequestException as e:
        print(f"Error de red al obtener datos de {coin_id}: {e}")
        return None
    except Exception as e:
        print(f"Error inesperado al procesar datos de {coin_id}: {e}")
        return None

def calcular_mejores_peores_horas(df):
    """
    Calcula el cambio porcentual entre el 'close' y el 'open' de cada vela (hora),
    y determina las 3 horas con mayor ganancia promedio y las 3 con mayor pérdida.
    """
    if df is None or df.empty:
        return None, None

    # Calcular el cambio porcentual por hora: (Close - Open) / Open * 100
    df['cambio_porcentual'] = (df['close'] - df['open']) / df['open'] * 100

    # Agrupar por hora y calcular el promedio de cambio
    rendimiento_por_hora = df.groupby('hora_cdmx')['cambio_porcentual'].mean().sort_values(ascending=False)

    # Las 3 horas con MEJOR rendimiento (mayor ganancia)
    mejores_horas = rendimiento_por_hora.head(3)

    # Las 3 horas con PEOR rendimiento (mayor pérdida)
    peores_horas = rendimiento_por_hora.tail(3)

    return mejores_horas, peores_horas

def formatear_mensaje(mejores, peores, moneda):
    """Genera un mensaje de texto legible para enviar a Telegram."""
    if mejores is None:
        return f"⚠️ No se pudieron obtener datos para {moneda}. Puede deberse a un error de conexión."

    mensaje = f"📊 *Análisis de Tendencias Horarias para {moneda}* 📊\n\n"

    # Sección de Mejores Horas
    mensaje += "🟢 *MEJORES HORAS (mayor ganancia potencial)*:\n"
    for hora, cambio in mejores.items():
        # Formatear la hora para mostrarla de 00:00 a 23:00
        hora_formateada = f"{int(hora):02d}:00"
        mensaje += f"  • 🌅 {hora_formateada}: {cambio:+.2f}%\n"

    # Sección de Peores Horas
    mensaje += "\n🔴 *PEORES HORAS (mayor pérdida potencial)*:\n"
    for hora, cambio in peores.items():
        hora_formateada = f"{int(hora):02d}:00"
        mensaje += f"  • 🌙 {hora_formateada}: {cambio:+.2f}%\n"

    mensaje += "\n🧠 _Nota: Estos datos se basan en el análisis de las últimas 24 horas y pueden cambiar diariamente. No es un consejo financiero._"
    return mensaje

def obtener_datos_cripto(coin_id):
    """Obtiene el nombre de la moneda para mostrarlo en el mensaje."""
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
        respuesta = requests.get(url, timeout=10)
        respuesta.raise_for_status()
        data = respuesta.json()
        return data.get('name', coin_id.capitalize())
    except Exception:
        return coin_id.capitalize()

# Lista de monedas a analizar
# Puedes cambiar los IDs. Para ver la lista completa, visita: https://www.coingecko.com/es
criptos_a_analizar = [
    "bitcoin", "ethereum", "solana", "dogecoin", "cardano"
]

if __name__ == "__main__":
    print("Iniciando análisis de horarios de trading...")
    enviar_alerta_telegram("🟢 *Bot de Análisis de Trading Iniciado*\nEstoy analizando los patrones horarios para enviarte un resumen en breve.")

    for cripto_id in criptos_a_analizar:
        # Obtener datos OHLC horarios
        df_ohlc = obtener_datos_ohlc(cripto_id, days=1)  # 'days=1' obtiene los datos de las últimas 24 horas, que para CoinGecko son horarios.

        if df_ohlc is not None and not df_ohlc.empty:
            # Calcular mejores y peores horas
            mejores, peores = calcular_mejores_peores_horas(df_ohlc)

            # Formatear y enviar el mensaje
            nombre_cripto = obtener_datos_cripto(cripto_id)
            mensaje = formatear_mensaje(mejores, peores, nombre_cripto)
            enviar_alerta_telegram(mensaje)

            # Pequeña pausa entre envíos para no saturar la API o Telegram
            time.sleep(5)
        else:
            enviar_alerta_telegram(f"⚠️ No se pudieron obtener datos para '{cripto_id}'. Revisa tu conexión o si el ID es correcto.")
            print(f"No se pudieron obtener datos para {cripto_id}")

    print("Análisis completado. Mensajes enviados a Telegram.")
        )
        enviar_mensaje(chat_id, ayuda)
    else:
        enviar_mensaje(chat_id, "Comando no reconocido. Escribe /ayuda para ver los comandos disponibles.")

def main():
    print("Bot de respuestas iniciado...")
    ultimo_update_id = None
    while True:
        updates = obtener_actualizaciones(offset=ultimo_update_id)
        for update in updates:
            update_id = update["update_id"]
            if "message" in update:
                chat_id = update["message"]["chat"]["id"]
                if "text" in update["message"]:
                    texto = update["message"]["text"]
                    manejar_comando(chat_id, texto)
            ultimo_update_id = update_id + 1
        time.sleep(1)

if __name__ == "__main__":
    main()
