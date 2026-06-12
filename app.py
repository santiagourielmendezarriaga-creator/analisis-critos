import requests
import pandas as pd
import time
from datetime import datetime, timezone, timedelta
from collections import defaultdict

# ==================== CONFIGURACIÓN ====================
TELEGRAM_TOKEN = "8532857017:AAHwLhRnM3oC6TbgFFKAEmQnZVoo6JD_esQ"
TELEGRAM_CHAT_ID = "5835990242"

# Zona horaria de CDMX (UTC-6)
ZONA_CDMX = timezone(timedelta(hours=-6))

# Lista de criptomonedas a analizar (ID de CoinGecko)
CRIPTOS = {
    "bitcoin": "Bitcoin",
    "ethereum": "Ethereum",
    "solana": "Solana",
    "dogecoin": "Dogecoin",
    "cardano": "Cardano",
    "ripple": "XRP"
}

# Configuración de tiempos
INTERVALO_SEÑALES = 60  # segundos (revisar señales cada 1 minuto)
INTERVALO_REPORTE_HORARIOS = 8 * 3600  # 8 horas

# ==================== FUNCIONES TELEGRAM ====================
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
        print(f"Error Telegram: {e}")
        return False

# ==================== FUNCIONES DE MERCADO ====================
def obtener_precio_individual(coin_id):
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd&include_24hr_change=true"
        response = requests.get(url, timeout=10)
        data = response.json()
        if coin_id in data:
            return data[coin_id]["usd"], data[coin_id].get("usd_24h_change", 0)
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

def obtener_datos_ohlc(coin_id):
    """Obtiene datos horarios de las últimas 24 horas"""
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
        params = {"vs_currency": "usd", "days": 1}
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        if not data:
            return None
        
        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df["hora_cdmx"] = df["timestamp"].dt.tz_localize("UTC").dt.tz_convert(ZONA_CDMX).dt.hour
        return df
    except:
        return None

# ==================== SEÑAL DE COMPRA/VENTA ====================
def calcular_senal(precio, cambio_24h, fng_valor, historial):
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
    
    if cambio_24h:
        if cambio_24h > 3:
            puntaje += 10
        elif cambio_24h > 1:
            puntaje += 5
        elif cambio_24h < -3:
            puntaje -= 10
        elif cambio_24h < -1:
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

# ==================== ANÁLISIS DE HORARIOS ====================
def calcular_mejores_peores_horas(df):
    if df is None or df.empty:
        return None, None
    
    df["cambio"] = (df["close"] - df["open"]) / df["open"] * 100
    rendimiento = df.groupby("hora_cdmx")["cambio"].mean().sort_values(ascending=False)
    
    mejores = rendimiento.head(3)
    peores = rendimiento.tail(3)
    return mejores, peores

def formatear_reporte_horarios(cripto_nombre, mejores, peores):
    if mejores is None:
        return f"⚠️ No se pudieron obtener datos para {cripto_nombre}"
    
    mensaje = f"📊 *{cripto_nombre} - MEJORES HORAS PARA OPERAR* 📊\n\n"
    mensaje += "🟢 *Mayor ganancia potencial:*\n"
    for hora, cambio in mejores.items():
        mensaje += f"   ⏰ {int(hora):02d}:00 → {cambio:+.2f}%\n"
    
    mensaje += "\n🔴 *Mayor pérdida potencial:*\n"
    for hora, cambio in peores.items():
        mensaje += f"   ⏰ {int(hora):02d}:00 → {cambio:+.2f}%\n"
    
    mensaje += "\n📌 Basado en últimas 24h. Ideal para comprar en horas verdes y vender en rojas."
    return mensaje

# ==================== BUCLE PRINCIPAL ====================
def main():
    print("🟢 Analizador completo iniciado...")
    enviar_telegram("🟢 *Analizador completo activado*\nMonitoreo de señales + análisis de horarios cada 8 horas.")
    
    # Estado para no repetir alertas
    ultima_senal = {coin: "" for coin in CRIPTOS}
    historial_precios = {coin: [] for coin in CRIPTOS}
    ultimo_reporte = 0
    
    while True:
        ahora = time.time()
        
        # 1. OBTENER FEAR & GREED (para todas las monedas)
        fng_valor, fng_texto = obtener_fear_greed()
        if fng_valor is None:
            fng_valor = 50
            fng_texto = "Neutral"
        
        # 2. ANALIZAR CADA CRIPTOMONEDA
        for coin_id, nombre in CRIPTOS.items():
            precio, cambio = obtener_precio_individual(coin_id)
            if precio is None:
                continue
            
            # Guardar historial
            historial_precios[coin_id].append(precio)
            if len(historial_precios[coin_id]) > 30:
                historial_precios[coin_id] = historial_precios[coin_id][-30:]
            
            # Calcular señal
            senal, puntaje = calcular_senal(precio, cambio, fng_valor, historial_precios[coin_id])
            
            # Enviar alerta si cambió y es relevante
            if senal != ultima_senal[coin_id] and senal in ["🟢 COMPRAR", "🔴 VENDER", "🟡 CONSIDERAR COMPRA"]:
                mensaje = f"""
🚨 <b>ALERTA {nombre}</b> 🚨

📊 {senal}
💰 Precio: ${precio:,.2f}
📈 24h: {cambio:+.2f}%
😨 Fear & Greed: {fng_valor}/100 ({fng_texto})
🎯 Puntaje: {puntaje}/100

⏰ {datetime.now().astimezone(ZONA_CDMX).strftime('%H:%M:%S')}
"""
                enviar_telegram(mensaje)
                ultima_senal[coin_id] = senal
            
            # Mostrar en consola
            print(f"{datetime.now().strftime('%H:%M:%S')} - {nombre}: {senal} (${precio:,.0f})")
        
        # 3. REPORTE DE HORARIOS (cada 8 horas)
        if ahora - ultimo_reporte >= INTERVALO_REPORTE_HORARIOS:
            print("📊 Generando reporte de horarios...")
            enviar_telegram("📊 *REPORTE DE HORARIOS - MEJORES MOMENTOS PARA TRADING* 📊\n")
            
            for coin_id, nombre in CRIPTOS.items():
                df = obtener_datos_ohlc(coin_id)
                if df is not None:
                    mejores, peores = calcular_mejores_peores_horas(df)
                    mensaje = formatear_reporte_horarios(nombre, mejores, peores)
                    enviar_telegram(mensaje)
                    time.sleep(3)  # Pequeña pausa entre envíos
            
            enviar_telegram("✅ *Reporte de horarios completado.*\nPróximo en 8 horas.")
            ultimo_reporte = ahora
        
        # Esperar antes de la siguiente iteración
        time.sleep(INTERVALO_SEÑALES)

if __name__ == "__main__":
    main()
