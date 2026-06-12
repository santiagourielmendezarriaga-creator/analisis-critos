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
