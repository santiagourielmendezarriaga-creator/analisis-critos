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
