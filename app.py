# -*- coding: utf-8 -*-
"""
🧠 Bot Scalping Extremo + Volumen + Tendencia 30d (Streamlit)
VERSIÓN FINAL CORREGIDA, EN ESPAÑOL

Correcciones aplicadas:
  1. El ciclo corre en st.fragment (antes un `while True` congelaba la interfaz).
  2. verificar_orden_pendiente devuelve la orden guardada (antes perdía el registro).
  3. El monto por operación respeta el límite configurado.
  4. Las ventas Maker se registran y se verifican (antes quedaban huérfanas).
  5. Las órdenes pendientes se persisten en Firebase.
  6. MODO_REAL y los montos se parsean explícitamente ("false" ya no es truthy).
  7. El volumen onchain devuelve None si falla la API (antes inventaba 0.5B).
  8. enviar_telegram reintenta sin Markdown si el parseo falla.
  9. El reset diario ocurre antes de mostrar los contadores.
 10. El token de Telegram vive en Secrets, no en el código.
 11. Salidas de riesgo: límite de pérdida, toma de ganancia y detención móvil.
 12. El límite de pérdida y la detención móvil salen A MERCADO.
 13. El límite de pérdida protege incluso en modo "solo señales".
 14. El saldo real de Bitso se lee y se muestra usando el TOTAL (no 'available').
 15. Freno de 15 minutos tras un rechazo de Bitso.
 16. Reconciliación automática: si Bitso ya no tiene el saldo, cierra la posición.
 17. Contador de aciertos vs fallos con punto de equilibrio.
 18. Firebase bajo ruta secreta (no /bot.json).
 19. Señales fuertes de compra/venta a un canal privado de Telegram.
 20. Botón de pánico: cancela TODAS las órdenes abiertas en Bitso.
 21. Limpieza automática de órdenes huérfanas al arrancar (si MODO_REAL=false).

Secrets esperados:
    BITSO_API_KEY, BITSO_API_SECRET, MODO_REAL,
    MONTO_MAXIMO_POR_OPERACION, MONTO_MAXIMO_DIARIO,
    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_CANAL_ID
"""

# ══════════════════ PARTE 1/11: importaciones y configuración global ══════════════════

import streamlit as st
import requests
import time
import json
import os
import re
import hmac
import hashlib
import statistics
from datetime import datetime, timedelta, timezone
from collections import deque

try:
    from streamlit_autorefresh import st_autorefresh as _refresco_automatico
except Exception:
    _refresco_automatico = None

COMISION = 0.006
VOLUMEN_MINIMO_24H = 0.5
GANANCIA_MINIMA_VENTA_PCT = 0.0
TOMA_GANANCIA_FIJA = True
SALIDA_A_MERCADO = True
MARGEN_AGRESIVO_PCT = 0.5
SALIDAS_IGNORAN_SOLO_SENALES = True
ESPERA_TRAS_FALLO_MIN = 15
MENSAJES = deque(maxlen=30)

def avisar(mensaje, nivel="info"):
    try:
        MENSAJES.append((datetime.now().strftime("%H:%M:%S"), nivel, mensaje))
    except Exception:
        pass
    print(f"[{nivel}] {mensaje}")

def _secreto(nombre, predeterminado=None):
    try:
        if nombre in st.secrets:
            return st.secrets[nombre]
    except Exception:
        pass
    valor = os.environ.get(nombre)
    return predeterminado if valor is None else valor

def _a_booleano(valor, predeterminado=False):
    if valor is None:
        return predeterminado
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)):
        return valor != 0
    return str(valor).strip().lower() in {"1", "true", "yes", "y", "si", "sí", "on"}

def _a_decimal(valor, predeterminado):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return predeterminado

def _a_entero(valor, predeterminado):
    try:
        return int(float(valor))
    except (TypeError, ValueError):
        return predeterminado

def _leer(datos, clave_nueva, clave_vieja, predeterminado):
    if clave_nueva in datos:
        return datos[clave_nueva]
    if clave_vieja in datos:
        return datos[clave_vieja]
    return predeterminado
# ══════════════════ PARTE 2/11: persistencia en Firebase ══════════════════
#
# 🔒 SEGURIDAD: los datos se guardan bajo una RUTA SECRETA, no en /bot.json.
#    1. Cambia RUTA_SECRETA por tu propia cadena aleatoria.
#    2. En Firebase Console → Realtime Database → Reglas, publica:
#       {
#         "rules": {
#           ".read": false,
#           ".write": false,
#           "TU_CADENA_SECRETA": { ".read": true, ".write": true }
#         }
#       }

URL_BASE_FIREBASE = "https://bot-cc6c4-default-rtdb.firebaseio.com"
RUTA_SECRETA = "b7k2m9x4q1z8"
URL_FIREBASE = f"{URL_BASE_FIREBASE}/{RUTA_SECRETA}"

def guardar_datos():
    try:
        datos = {
            "saldo": st.session_state.saldo,
            "posiciones": st.session_state.posiciones,
            "operaciones": [(t.isoformat(), msg) for t, msg in st.session_state.operaciones],
            "historial_precios": {k: list(v) for k, v in st.session_state.historial_precios.items()},
            "ultima_accion": st.session_state.ultima_accion,
            "ops_del_dia": st.session_state.ops_del_dia,
            "ultimo_dia": st.session_state.ultimo_dia,
            "monto_del_dia": st.session_state.get("monto_del_dia", 0.0),
            "precio_referencia": st.session_state.precio_referencia,
            "ultimo_precio": st.session_state.ultimo_precio,
            "precio_entrada": st.session_state.precio_entrada,
            "precio_maximo": st.session_state.precio_maximo,
            "ciclo": st.session_state.ciclo,
            "umbral_caida": st.session_state.umbral_caida,
            "limite_perdida": st.session_state.limite_perdida,
            "toma_ganancia": st.session_state.toma_ganancia,
            "seguimiento": st.session_state.seguimiento,
            "umbral_indicadores_activacion": st.session_state.umbral_indicadores_activacion,
            "puntaje_experto": st.session_state.puntaje_experto,
            "rsi_sobreventa": st.session_state.rsi_sobreventa,
            "rsi_sobrecompra": st.session_state.rsi_sobrecompra,
            "ema_rapida": st.session_state.ema_rapida,
            "ema_lenta": st.session_state.ema_lenta,
            "sl_disparado": st.session_state.sl_disparado,
            "sl_precio_minimo": st.session_state.sl_precio_minimo,
            "indicadores_activados": st.session_state.indicadores_activados,
            "modo_solo_senales": st.session_state.modo_solo_senales,
            "rendimiento": st.session_state.rendimiento,
            "confianza": st.session_state.confianza,
            "tendencia": st.session_state.tendencia,
            "historial_operaciones": st.session_state.historial_operaciones,
            "modo_aprendizaje": st.session_state.modo_aprendizaje,
            "cache_onchain": st.session_state.cache_onchain,
            "tendencia_historica": st.session_state.tendencia_historica,
            "confianza_umbral": st.session_state.confianza_umbral,
            "intervalo_actualizacion": st.session_state.intervalo_actualizacion,
            "inicio_fase": st.session_state.inicio_fase,
            "fase_actual": st.session_state.fase_actual,
            "analisis_anterior": st.session_state.analisis_anterior,
            "operar_24_7": st.session_state.get("operar_24_7", False),
            "orden_pendiente_BTC": st.session_state.get("orden_pendiente_BTC"),
            "orden_pendiente_ETH": st.session_state.get("orden_pendiente_ETH"),
            "ultimo_respaldo_auto": st.session_state.get("ultimo_respaldo_auto", time.time()),
            "ultimo_respaldo_operaciones": st.session_state.get("ultimo_respaldo_operaciones", 0),
        }
        url = f"{URL_FIREBASE}/bot.json"
        respuesta = requests.put(url, json=datos, timeout=10)
        if respuesta.status_code == 200:
            print(f"💾 Guardado. Ciclo: {st.session_state.ciclo}")
            return True, "Guardado exitoso"
        return False, f"Status {respuesta.status_code}"
    except Exception as e:
        return False, str(e)

def cargar_datos():
    try:
        url = f"{URL_FIREBASE}/bot.json"
        respuesta = requests.get(url, timeout=10)
        if respuesta.status_code == 200:
            datos = respuesta.json()
            if datos and ("saldo" in datos or "balance" in datos) and ("posiciones" in datos or "positions" in datos):
                return datos
        return None
    except Exception as e:
        print(f"Error al cargar: {e}")
        return None

def iniciar_estado_nuevo():
    st.session_state.saldo = 1000.0
    st.session_state.posiciones = {"BTC": 0.0, "ETH": 0.0}
    st.session_state.operaciones = []
    st.session_state.ultima_accion = {"BTC": None, "ETH": None}
    st.session_state.ops_del_dia = 0
    st.session_state.ultimo_dia = datetime.now().day
    st.session_state.monto_del_dia = 0.0
    st.session_state.precio_referencia = {"BTC": 0.0, "ETH": 0.0}
    st.session_state.ultimo_precio = {"BTC": 0.0, "ETH": 0.0}
    st.session_state.precio_entrada = {"BTC": 0.0, "ETH": 0.0}
    st.session_state.precio_maximo = {"BTC": 0.0, "ETH": 0.0}
    st.session_state.ciclo = 0
    st.session_state.historial_precios = {"BTC": deque(maxlen=200), "ETH": deque(maxlen=200)}
    st.session_state.umbral_caida = 0.005
    st.session_state.limite_perdida = 1.0          # 🔧 ANTES 1.5
    st.session_state.toma_ganancia = 5.0           # 🔧 ANTES 2.5
    st.session_state.seguimiento = 0.5
    st.session_state.umbral_indicadores_activacion = 0.5
    st.session_state.puntaje_experto = 30
    st.session_state.rsi_sobreventa = 30
    st.session_state.rsi_sobrecompra = 80
    st.session_state.ema_rapida = 5
    st.session_state.ema_lenta = 12
    st.session_state.sl_disparado = {"BTC": False, "ETH": False}
    st.session_state.sl_precio_minimo = {"BTC": 0.0, "ETH": 0.0}
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
    st.session_state.cache_onchain = {
        "BTC": {"valor": None, "timestamp": 0},
        "ETH": {"valor": None, "timestamp": 0}
    }
    st.session_state.tendencia_historica = {"BTC": {}, "ETH": {}}
    st.session_state.confianza_umbral = 65
    st.session_state.intervalo_actualizacion = 5
    st.session_state.inicio_fase = datetime.now().isoformat()
    st.session_state.fase_actual = "operando"
    st.session_state.analisis_anterior = {}
    st.session_state.orden_pendiente_BTC = None
    st.session_state.orden_pendiente_ETH = None
    st.session_state.operar_24_7 = False
    st.session_state.ultimo_respaldo_auto = time.time()
    st.session_state.ultimo_respaldo_operaciones = 0

def restaurar_desde_archivo():
    datos = cargar_datos()
    if datos is None:
        iniciar_estado_nuevo()
        return
    try:
        operaciones = []
        for marca, msg in _leer(datos, "operaciones", "trades", []):
            if isinstance(marca, str):
                operaciones.append((datetime.fromisoformat(marca), msg))
            else:
                operaciones.append((marca, msg))

        st.session_state.saldo = _leer(datos, "saldo", "balance", 1000.0)
        st.session_state.posiciones = _leer(datos, "posiciones", "positions", {"BTC": 0.0, "ETH": 0.0})
        st.session_state.operaciones = operaciones
        st.session_state.ultima_accion = _leer(datos, "ultima_accion", "last_action", {"BTC": None, "ETH": None})
        st.session_state.ops_del_dia = _leer(datos, "ops_del_dia", "daily_trades", 0)
        st.session_state.ultimo_dia = _leer(datos, "ultimo_dia", "last_day", datetime.now().day)
        st.session_state.monto_del_dia = _leer(datos, "monto_del_dia", "monto_dia", 0.0)
        st.session_state.precio_referencia = _leer(datos, "precio_referencia", "ref_price", {"BTC": 0.0, "ETH": 0.0})
        st.session_state.ultimo_precio = _leer(datos, "ultimo_precio", "last_price", {"BTC": 0.0, "ETH": 0.0})
        st.session_state.precio_entrada = _leer(datos, "precio_entrada", "entry_price", {"BTC": 0.0, "ETH": 0.0})
        st.session_state.precio_maximo = _leer(datos, "precio_maximo", "highest_price", {"BTC": 0.0, "ETH": 0.0})
        st.session_state.ciclo = _leer(datos, "ciclo", "cycle", 0)
        st.session_state.umbral_caida = datos.get("umbral_caida", 0.005)
        st.session_state.limite_perdida = _leer(datos, "limite_perdida", "stop_loss", 1.0)   # 🔧 ANTES 1.5
        st.session_state.toma_ganancia = max(0.5, _a_decimal(
            _leer(datos, "toma_ganancia", "take_profit", 5.0), 5.0))                        # 🔧 ANTES 2.5
        st.session_state.seguimiento = _leer(datos, "seguimiento", "trailing", 0.5)
        st.session_state.umbral_indicadores_activacion = datos.get("umbral_indicadores_activacion", 0.5)
        st.session_state.puntaje_experto = _leer(datos, "puntaje_experto", "expert_score", 30)
        st.session_state.rsi_sobreventa = _leer(datos, "rsi_sobreventa", "rsi_os", 30)
        st.session_state.rsi_sobrecompra = _leer(datos, "rsi_sobrecompra", "rsi_ob", 80)
        st.session_state.ema_rapida = _leer(datos, "ema_rapida", "ema_fast", 5)
        st.session_state.ema_lenta = _leer(datos, "ema_lenta", "ema_slow", 12)
        st.session_state.sl_disparado = _leer(datos, "sl_disparado", "sl_triggered", {"BTC": False, "ETH": False})
        st.session_state.sl_precio_minimo = _leer(datos, "sl_precio_minimo", "sl_low_price", {"BTC": 0.0, "ETH": 0.0})
        st.session_state.indicadores_activados = datos.get("indicadores_activados", {"BTC": False, "ETH": False})
        st.session_state.modo_solo_senales = datos.get("modo_solo_senales", False)
        st.session_state.modo_aprendizaje = datos.get("modo_aprendizaje", False)
        st.session_state.rendimiento = datos.get("rendimiento", {
            "BTC": {"ganadas": 0, "perdidas": 0, "total": 0, "ultimas_10": []},
            "ETH": {"ganadas": 0, "perdidas": 0, "total": 0, "ultimas_10": []}
        })
        st.session_state.confianza = datos.get("confianza", {"BTC": 50, "ETH": 50})
        st.session_state.tendencia = datos.get("tendencia", {"BTC": "NEUTRAL", "ETH": "NEUTRAL"})
        st.session_state.historial_operaciones = datos.get("historial_operaciones", [])
        st.session_state.cache_onchain = _leer(datos, "cache_onchain", "onchain_cache", {
            "BTC": {"valor": None, "timestamp": 0},
            "ETH": {"valor": None, "timestamp": 0}
        })
        st.session_state.tendencia_historica = _leer(datos, "tendencia_historica", "historical_trend", {"BTC": {}, "ETH": {}})
        st.session_state.confianza_umbral = min(95, max(50, _a_entero(datos.get("confianza_umbral", 65), 65)))
        st.session_state.intervalo_actualizacion = datos.get("intervalo_actualizacion", 5)
        st.session_state.inicio_fase = datos.get("inicio_fase", datetime.now().isoformat())
        st.session_state.fase_actual = datos.get("fase_actual", "operando")
        st.session_state.analisis_anterior = datos.get("analisis_anterior", {})
        st.session_state.operar_24_7 = _a_booleano(datos.get("operar_24_7", False), False)
        historial = _leer(datos, "historial_precios", "price_history", {"BTC": [], "ETH": []})
        st.session_state.historial_precios = {k: deque(v, maxlen=200) for k, v in historial.items()}
        st.session_state.orden_pendiente_BTC = datos.get("orden_pendiente_BTC")
        st.session_state.orden_pendiente_ETH = datos.get("orden_pendiente_ETH")
        st.session_state.ultimo_respaldo_auto = _leer(
            datos, "ultimo_respaldo_auto", "ultimo_backup_auto", None) or time.time()
        st.session_state.ultimo_respaldo_operaciones = _a_entero(
            _leer(datos, "ultimo_respaldo_operaciones", "ultimo_backup_trades", 0), 0)
        print(f"✅ Datos restaurados. Ciclo: {st.session_state.ciclo}")
    except Exception as e:
        print(f"Error al restaurar: {e}")
        iniciar_estado_nuevo()

def crear_respaldo():
    try:
        url = f"{URL_FIREBASE}/bot.json"
        respuesta = requests.get(url, timeout=10)
        if respuesta.status_code != 200:
            return None, "No hay datos para respaldar"
        datos_actuales = respuesta.json()
        if not datos_actuales or ("saldo" not in datos_actuales and "balance" not in datos_actuales):
            return None, "Datos incompletos"
        marca = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        clave_respaldo = f"backup_{marca}"
        url_respaldo = f"{URL_FIREBASE}/backups/{clave_respaldo}.json"
        contenido = {
            "timestamp": marca,
            "cycle": datos_actuales.get("ciclo", datos_actuales.get("cycle", 0)),
            "balance": datos_actuales.get("saldo", datos_actuales.get("balance", 0)),
            "positions": datos_actuales.get("posiciones", datos_actuales.get("positions", {})),
            "trades_count": len(datos_actuales.get("operaciones", datos_actuales.get("trades", []))),
            "data": datos_actuales
        }
        respuesta2 = requests.put(url_respaldo, json=contenido, timeout=15)
        if respuesta2.status_code == 200:
            print(f"💾 Respaldo creado: {clave_respaldo}")
            return clave_respaldo, "Respaldo creado exitosamente"
        return None, "Error al crear el respaldo en Firebase"
    except Exception as e:
        print(f"Error creando respaldo: {e}")
        return None, str(e)

def listar_respaldos():
    try:
        url = f"{URL_FIREBASE}/backups.json"
        respuesta = requests.get(url, timeout=10)
        if respuesta.status_code == 200:
            datos = respuesta.json()
            if datos:
                return sorted(datos.keys(), reverse=True)
        return []
    except Exception as e:
        print(f"Error listando respaldos: {e}")
        return []

def restaurar_respaldo(clave_respaldo):
    try:
        url = f"{URL_FIREBASE}/backups/{clave_respaldo}.json"
        respuesta = requests.get(url, timeout=10)
        if respuesta.status_code == 200:
            datos = respuesta.json()
            if datos and "data" in datos:
                url_bot = f"{URL_FIREBASE}/bot.json"
                respuesta2 = requests.put(url_bot, json=datos["data"], timeout=15)
                if respuesta2.status_code == 200:
                    print(f"✅ Respaldo {clave_respaldo} restaurado")
                    return True
        return False
    except Exception as e:
        print(f"Error restaurando respaldo: {e}")
        return False

def limpiar_respaldos_viejos(maximo_respaldos=10):
    try:
        respaldos = listar_respaldos()
        if len(respaldos) > maximo_respaldos:
            for viejo in respaldos[maximo_respaldos:]:
                url_borrar = f"{URL_FIREBASE}/backups/{viejo}.json"
                requests.delete(url_borrar, timeout=10)
                print(f"🗑️ Respaldo viejo eliminado: {viejo}")
    except Exception as e:
        print(f"Error limpiando respaldos: {e}")
        # ══════════════════ PARTE 3/11: Telegram, Bitso y saldo real ══════════════════

TOKEN_TELEGRAM = str(_secreto("TELEGRAM_TOKEN", "") or os.environ.get("TELEGRAM_TOKEN", "")).strip()
CHAT_ID_TELEGRAM = str(_secreto("TELEGRAM_CHAT_ID", "") or os.environ.get("TELEGRAM_CHAT_ID", "")).strip()
TELEGRAM_CONFIGURADO = bool(TOKEN_TELEGRAM and CHAT_ID_TELEGRAM)

def enviar_telegram(mensaje):
    if not TELEGRAM_CONFIGURADO:
        print("⚠️ Telegram no configurado")
        return False
    try:
        url = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendMessage"
        cuerpo = {"chat_id": CHAT_ID_TELEGRAM, "text": mensaje}
        respuesta = requests.post(url, json={**cuerpo, "parse_mode": "Markdown"}, timeout=5)
        if respuesta.status_code != 200:
            requests.post(url, json=cuerpo, timeout=5)
        return True
    except Exception:
        return False

CANAL_TELEGRAM = str(_secreto("TELEGRAM_CANAL_ID", "") or os.environ.get("TELEGRAM_CANAL_ID", "")).strip()
CANAL_CONFIGURADO = bool(TOKEN_TELEGRAM and CANAL_TELEGRAM)
UMBRAL_SENAL_FUERTE = 80

def enviar_canal_telegram(mensaje):
    if not CANAL_CONFIGURADO:
        return False
    try:
        url = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendMessage"
        cuerpo = {"chat_id": CANAL_TELEGRAM, "text": mensaje, "parse_mode": "Markdown",
                  "disable_web_page_preview": True}
        respuesta = requests.post(url, json=cuerpo, timeout=5)
        if respuesta.status_code != 200:
            cuerpo.pop("parse_mode", None)
            requests.post(url, json=cuerpo, timeout=5)
        return True
    except Exception:
        return False

URL_BASE_BITSO = "https://api.bitso.com"
LLAVE_API_BITSO = str(_secreto("BITSO_API_KEY", "") or "")
SECRETO_API_BITSO = str(_secreto("BITSO_API_SECRET", "") or "")
MODO_REAL = _a_booleano(_secreto("MODO_REAL", False), False)
MONTO_MAXIMO_POR_OPERACION = max(1.0, _a_decimal(_secreto("MONTO_MAXIMO_POR_OPERACION", 50.0), 50.0))
MONTO_MAXIMO_DIARIO = max(1.0, _a_decimal(_secreto("MONTO_MAXIMO_DIARIO", 100.0), 100.0))

def obtener_precio_bitso(libro="btc_mxn"):
    try:
        url = f"{URL_BASE_BITSO}/v3/ticker/?book={libro}"
        respuesta = requests.get(url, timeout=5)
        if respuesta.status_code == 200:
            datos = respuesta.json()
            carga = datos.get("payload")
            if carga and carga.get("last"):
                return float(carga["last"])
    except Exception:
        pass
    return None

def _crear_cabecera_autenticacion(metodo, ruta, cuerpo_json=""):
    if not LLAVE_API_BITSO or not SECRETO_API_BITSO:
        return None, None
    nonce = str(int(time.time() * 1000))
    mensaje = nonce + metodo.upper() + ruta + cuerpo_json
    firma = hmac.new(SECRETO_API_BITSO.encode('utf-8'), mensaje.encode('utf-8'),
                     hashlib.sha256).hexdigest()
    cabecera = f"Bitso {LLAVE_API_BITSO}:{nonce}:{firma}"
    return cabecera, nonce

def obtener_saldo_bitso(usar_cache=True):
    if not LLAVE_API_BITSO or not SECRETO_API_BITSO:
        st.session_state["error_saldo_bitso"] = "Faltan BITSO_API_KEY / BITSO_API_SECRET."
        return None
    ahora = time.time()
    cache = st.session_state.get("cache_saldo_bitso") or {}
    if usar_cache and cache.get("valor") is not None and (ahora - cache.get("timestamp", 0)) < 30:
        return cache["valor"]
    try:
        ruta = "/v3/balance/"
        cabecera, _ = _crear_cabecera_autenticacion("GET", ruta)
        if not cabecera:
            st.session_state["error_saldo_bitso"] = "No se pudo firmar la petición."
            return None
        respuesta = requests.get(URL_BASE_BITSO + ruta, headers={"Authorization": cabecera}, timeout=10)
        if respuesta.status_code != 200:
            st.session_state["error_saldo_bitso"] = f"HTTP {respuesta.status_code}: {respuesta.text[:200]}"
            return None
        datos = respuesta.json()
        if not (isinstance(datos, dict) and datos.get("success")):
            st.session_state["error_saldo_bitso"] = f"Sin success: {str(datos)[:200]}"
            return None
        saldos = {}
        for moneda in datos.get("payload", {}).get("balances", []):
            codigo = str(moneda.get("currency", "")).lower()
            if not codigo:
                continue
            saldos[codigo] = {
                "available": float(moneda.get("available") or 0),
                "total": float(moneda.get("total") or 0),
            }
        st.session_state["error_saldo_bitso"] = None
        st.session_state["cache_saldo_bitso"] = {"valor": saldos, "timestamp": ahora}
        return saldos
    except Exception as e:
        st.session_state["error_saldo_bitso"] = f"Excepción: {e}"
        return None
        # ══════════════════ PARTE 4/11: órdenes de Bitso ══════════════════

def colocar_orden_bitso(libro, lado, cantidad_mayor, precio, tipo="limit"):
    if not MODO_REAL:
        print("⚠️ MODO_REAL desactivado.")
        return None
    try:
        ruta = "/v3/orders/"
        cuerpo = {"book": libro, "side": lado, "type": tipo, "major": str(cantidad_mayor)}
        if tipo != "market":
            cuerpo["price"] = str(precio)
        cuerpo_json = json.dumps(cuerpo, separators=(',', ':'))
        cabecera, _ = _crear_cabecera_autenticacion("POST", ruta, cuerpo_json)
        if not cabecera:
            return None
        cabeceras = {"Authorization": cabecera, "Content-Type": "application/json"}
        respuesta = requests.post(URL_BASE_BITSO + ruta, data=cuerpo_json, headers=cabeceras, timeout=15)
        datos = respuesta.json()
        if respuesta.status_code == 200 and isinstance(datos, dict) and datos.get("success"):
            orden = datos.get("payload", {})
            print(f"✅ Orden {tipo} colocada: {orden.get('oid')}")
            return orden
        error = datos.get("error", {}) if isinstance(datos, dict) else {}
        mensaje_error = error.get("message") or str(datos)[:200] or "Error desconocido"
        print(f"❌ Error al colocar la orden {tipo}: {mensaje_error}")
        return {"error": mensaje_error}
    except Exception as e:
        print(f"❌ Excepción colocando la orden: {e}")
        return {"error": str(e)}

def obtener_estado_orden(oid):
    if not MODO_REAL:
        return None
    try:
        ruta = f"/v3/orders/{oid}/"
        cabecera, _ = _crear_cabecera_autenticacion("GET", ruta)
        if not cabecera:
            return None
        respuesta = requests.get(URL_BASE_BITSO + ruta, headers={"Authorization": cabecera}, timeout=10)
        if respuesta.status_code == 200:
            datos = respuesta.json()
            if isinstance(datos, dict) and datos.get("success"):
                carga = datos.get("payload")
                if isinstance(carga, dict):
                    return carga
        return None
    except Exception as e:
        print(f"Error consultando la orden {oid}: {e}")
        return None

def cancelar_orden_bitso(oid):
    if not MODO_REAL:
        return False
    try:
        ruta = f"/v3/orders/{oid}/"
        cabecera, _ = _crear_cabecera_autenticacion("DELETE", ruta)
        if not cabecera:
            return False
        respuesta = requests.delete(URL_BASE_BITSO + ruta, headers={"Authorization": cabecera}, timeout=10)
        if respuesta.status_code == 200:
            datos = respuesta.json()
            if isinstance(datos, dict) and datos.get("success"):
                print(f"✅ Orden {oid} cancelada")
                return True
        return False
    except Exception as e:
        print(f"Error cancelando la orden {oid}: {e}")
        return False

def verificar_orden_pendiente(simbolo):
    clave_orden = f"orden_pendiente_{simbolo}"
    orden = st.session_state.get(clave_orden)
    if not isinstance(orden, dict):
        st.session_state[clave_orden] = None
        return "sin_orden", None
    oid = orden.get("oid")
    if not oid:
        st.session_state[clave_orden] = None
        return "sin_orden", None
    creada = float(orden.get("timestamp", time.time()) or time.time())
    vencida = (time.time() - creada) > 600
    if not MODO_REAL:
        st.session_state[clave_orden] = None
        return "ejecutada", orden
    estado_orden = None
    try:
        estado_orden = obtener_estado_orden(oid)
    except Exception as e:
        print(f"Error consultando la orden {oid}: {e}")
    if isinstance(estado_orden, dict):
        estado = estado_orden.get("status")
        if estado in ["completed", "filled"]:
            orden = dict(orden)
            orden["ejecucion"] = estado_orden
            st.session_state[clave_orden] = None
            return "ejecutada", orden
        if estado == "cancelled":
            st.session_state[clave_orden] = None
            return "cancelada", None
    if vencida:
        try:
            cancelar_orden_bitso(oid)
        except Exception:
            pass
        st.session_state[clave_orden] = None
        return "cancelada", None
    return "pendiente", orden

def obtener_miedo_codicia():
    try:
        respuesta = requests.get("https://api.alternative.me/fng/", timeout=5)
        if respuesta.status_code == 200:
            datos = respuesta.json()
            return int(datos['data'][0]['value']), datos['data'][0]['value_classification']
    except Exception:
        pass
    return 50, "Neutral"
    # ══════════════════ PARTE 5/11: análisis y aprendizaje ══════════════════

def analizar_tendencia(historial, periodo=20):
    if len(historial) < periodo:
        return "NEUTRAL"
    datos = list(historial)[-periodo:]
    inicio = datos[0]
    final = datos[-1]
    if not inicio:
        return "NEUTRAL"
    cambio = (final - inicio) / inicio * 100
    volatilidad = 0
    for i in range(1, len(datos)):
        if not datos[i-1]:
            continue
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

def evaluar_rendimiento(simbolo):
    rend = st.session_state.rendimiento[simbolo]
    total = rend["total"]
    if total < 5:
        return {"accion": "MANTENER"}
    proporcion = rend["ganadas"] / total
    if proporcion > 0.6:
        return {"accion": "AUMENTAR_RIESGO"}
    elif proporcion < 0.4:
        return {"accion": "REDUCIR_RIESGO"}
    else:
        return {"accion": "MANTENER"}

def analizar_fase_aprendizaje():
    operaciones = st.session_state.operaciones
    if len(operaciones) < 3:
        return {"suficiente": False, "razon": f"Solo {len(operaciones)} operaciones."}
    ventas = []
    for marca, msg in operaciones:
        if "VENTA" in msg or "SELL" in msg:
            ventas.append({"ts": marca, "msg": msg})
    if len(ventas) == 0:
        return {"suficiente": False, "razon": "No hay ventas cerradas."}
    ganancias = 0
    perdidas = 0
    ganancias_totales = 0.0
    horarios = {}
    simbolos = {
        "BTC": {"wins": 0, "losses": 0, "profit": 0.0},
        "ETH": {"wins": 0, "losses": 0, "profit": 0.0}
    }
    for venta in ventas:
        msg = venta["msg"]
        hora = venta["ts"].hour
        horarios.setdefault(hora, {"wins": 0, "losses": 0, "profit": 0.0})
        ganancia = 0.0
        coincidencia = re.search(r"PROFIT:\s*([+-]?\$?[\d,]+\.?\d*)", msg)
        if coincidencia:
            texto_ganancia = coincidencia.group(1).replace("$", "").replace(",", "")
            try:
                ganancia = float(texto_ganancia)
            except (TypeError, ValueError):
                ganancia = 0.0
        ganancias_totales += ganancia
        if ganancia > 0:
            ganancias += 1
            horarios[hora]["wins"] += 1
            horarios[hora]["profit"] += ganancia
            for simbolo in simbolos:
                if simbolo in msg:
                    simbolos[simbolo]["wins"] += 1
                    simbolos[simbolo]["profit"] += ganancia
        else:
            perdidas += 1
            horarios[hora]["losses"] += 1
            horarios[hora]["profit"] += ganancia
            for simbolo in simbolos:
                if simbolo in msg:
                    simbolos[simbolo]["losses"] += 1
                    simbolos[simbolo]["profit"] += ganancia
    total_ventas = ganancias + perdidas
    tasa_acierto = (ganancias / total_ventas * 100) if total_ventas > 0 else 0
    ganancia_promedio = ganancias_totales / total_ventas if total_ventas > 0 else 0
    mejor_hora = None
    peor_hora = None
    mejor_ganancia = -999999
    peor_ganancia = 999999
    for hora, datos_hora in horarios.items():
        if datos_hora["profit"] > mejor_ganancia:
            mejor_ganancia = datos_hora["profit"]
            mejor_hora = hora
        if datos_hora["profit"] < peor_ganancia:
            peor_ganancia = datos_hora["profit"]
            peor_hora = hora
    analisis = {
        "suficiente": True,
        "total_operaciones": total_ventas,
        "ganancias": ganancias,
        "perdidas": perdidas,
        "win_rate": tasa_acierto,
        "profit_total": ganancias_totales,
        "profit_promedio": ganancia_promedio,
        "mejor_hora": mejor_hora,
        "peor_hora": peor_hora,
        "simbolos": simbolos,
        "ajustes_aplicados": []
    }
    if tasa_acierto < 40:
        st.session_state.confianza_umbral = min(95, st.session_state.confianza_umbral + 5)
        analisis["ajustes_aplicados"].append(
            f"Umbral subido a {st.session_state.confianza_umbral}% (tasa de acierto baja)")
    elif tasa_acierto > 65:
        st.session_state.confianza_umbral = max(50, st.session_state.confianza_umbral - 5)
        analisis["ajustes_aplicados"].append(
            f"Umbral bajado a {st.session_state.confianza_umbral}% (tasa de acierto alta)")
    else:
        analisis["ajustes_aplicados"].append(f"Umbral mantenido en {st.session_state.confianza_umbral}%")
    for simbolo, estadisticas in simbolos.items():
        total_simbolo = estadisticas["wins"] + estadisticas["losses"]
        if total_simbolo >= 2:
            tasa_simbolo = (estadisticas["wins"] / total_simbolo * 100)
            if tasa_simbolo < 30:
                analisis["ajustes_aplicados"].append(
                    f"{simbolo} rinde mal ({tasa_simbolo:.0f}% | ${estadisticas['profit']:.2f})")
            elif tasa_simbolo > 70:
                analisis["ajustes_aplicados"].append(
                    f"{simbolo} rinde bien ({tasa_simbolo:.0f}% | ${estadisticas['profit']:.2f})")
    if ganancia_promedio > 0:
        st.session_state.toma_ganancia = min(10.0, st.session_state.toma_ganancia * 1.1)
        analisis["ajustes_aplicados"].append(
            f"Toma de ganancia aumentada a {st.session_state.toma_ganancia:.3f}%")
    elif ganancia_promedio < 0:
        st.session_state.toma_ganancia = max(0.5, st.session_state.toma_ganancia * 0.9)
        st.session_state.limite_perdida = max(0.5, st.session_state.limite_perdida * 0.9)
        analisis["ajustes_aplicados"].append("Toma de ganancia y límite reducidos")
    else:
        analisis["ajustes_aplicados"].append("Sin cambios en TP/SL")
    return analisis
    # ══════════════════ PARTE 6/11: datos externos e indicadores ══════════════════

def obtener_tendencia_historica(simbolo="BTC", dias=30):
    try:
        identificador = "bitcoin" if simbolo == "BTC" else "ethereum"
        url = (f"https://api.coingecko.com/api/v3/coins/{identificador}"
               f"/market_chart?vs_currency=usd&days={dias}")
        respuesta = requests.get(url, timeout=5)
        if respuesta.status_code != 200:
            return None
        datos = respuesta.json()
        precios = [p[1] for p in datos.get("prices", [])]
        if len(precios) < 2:
            return None
        precio_actual = precios[-1]
        precio_inicial = precios[0]
        cambio_porcentual = (precio_actual - precio_inicial) / precio_inicial * 100
        media_30 = sum(precios[-30:]) / 30 if len(precios) >= 30 else sum(precios) / len(precios)
        if precio_actual > media_30 * 1.01:
            tendencia = "ALCISTA"
        elif precio_actual < media_30 * 0.99:
            tendencia = "BAJISTA"
        else:
            tendencia = "LATERAL"
        return {
            "cambio_porcentual": cambio_porcentual,
            "tendencia": tendencia,
            "precio_actual": precio_actual,
            "media_30": media_30
        }
    except Exception:
        return None

def obtener_volumen_onchain(simbolo="BTC"):
    ahora = time.time()
    cache = st.session_state.cache_onchain.get(simbolo, {"valor": None, "timestamp": 0})
    valor_cache = cache.get("valor") if isinstance(cache, dict) else None
    marca_cache = cache.get("timestamp", 0) if isinstance(cache, dict) else 0
    if valor_cache is not None and (ahora - marca_cache) < 60:
        return valor_cache
    try:
        moneda = "bitcoin" if simbolo == "BTC" else "ethereum"
        url = f"https://api.coingecko.com/api/v3/coins/{moneda}/market_chart?vs_currency=usd&days=1"
        respuesta = requests.get(url, timeout=5)
        if respuesta.status_code == 200:
            datos = respuesta.json()
            volumenes = datos.get("total_volumes", [])
            if volumenes:
                volumen_usd = volumenes[-1][1] / 1e9
                st.session_state.cache_onchain[simbolo] = {"valor": volumen_usd, "timestamp": ahora}
                return volumen_usd
    except Exception:
        pass
    return valor_cache

def calcular_ema(precios, periodo):
    if len(precios) < periodo:
        return None
    factor = 2 / (periodo + 1)
    ema = precios[0]
    for precio in precios[1:]:
        ema = precio * factor + ema * (1 - factor)
    return ema

def calcular_rsi(precios, periodo=14):
    if len(precios) < periodo + 1:
        return 50
    diferencias = [precios[i] - precios[i-1] for i in range(1, len(precios))]
    subidas = [d if d > 0 else 0 for d in diferencias]
    bajadas = [-d if d < 0 else 0 for d in diferencias]
    promedio_subidas = sum(subidas[-periodo:]) / periodo
    promedio_bajadas = sum(bajadas[-periodo:]) / periodo
    if promedio_bajadas == 0:
        return 100
    fuerza_relativa = promedio_subidas / promedio_bajadas
    return 100 - (100 / (1 + fuerza_relativa))

def calcular_atr(precios, periodo=14):
    if len(precios) < periodo + 1:
        return None
    atr = 0.0
    for i in range(1, len(precios)):
        rango = abs(precios[i] - precios[i-1])
        if i == 1:
            atr = rango
        else:
            atr = (atr * (periodo - 1) + rango) / periodo
    return atr

def calcular_probabilidad(confianza):
    return min(100, max(0, confianza * 2.5))

def obtener_horario_operacion():
    zona_mexico = timezone(timedelta(hours=-6))
    ahora = datetime.now(zona_mexico)
    hora = ahora.hour
    dia_semana = ahora.weekday()
    if dia_semana >= 5:
        return ("FIN DE SEMANA", "🛑", "Mercado con muy poca actividad.", False)
    if 7 <= hora < 11:
        return ("MEJOR HORARIO", "🔥", "Europa + USA activos.", True)
    if (6 <= hora < 7) or (11 <= hora < 14):
        return ("SESIÓN USA", "✅", "Sesión completa de EE.UU.", True)
    if 2 <= hora < 6:
        return ("APERTURA EUROPA", "⚠️", "Europa abre.", True)
    if hora >= 20 or hora < 2:
        return ("SESIÓN ASIA", "🚫", "Solo Asia. EVITAR operar.", False)
    return ("TARDE / TRANSICIÓN", "🟡", "Entre USA y Asia.", False)

def analisis_avanzado(simbolo, precio, valor_miedo_codicia):
    datos_tendencia = st.session_state.tendencia_historica.get(simbolo, {}) or {}
    cambio_30d = datos_tendencia.get("cambio_porcentual", 0)
    tendencia_30d = datos_tendencia.get("tendencia", "NEUTRAL")
    volumen_onchain = obtener_volumen_onchain(simbolo)
    historial = list(st.session_state.historial_precios.get(simbolo, []))
    if len(historial) < 30:
        return "HOLD", 0, "Datos insuficientes", {}

    rsi = calcular_rsi(historial, 14)
    peso_rsi = 20 if rsi <= 30 else -20 if rsi >= 70 else (50 - rsi) * 0.5

    ema_rapida = calcular_ema(historial, st.session_state.ema_rapida)
    ema_lenta = calcular_ema(historial, st.session_state.ema_lenta)
    peso_ema = 0
    if ema_rapida and ema_lenta:
        if ema_rapida > ema_lenta:
            peso_ema = 15
        elif ema_rapida < ema_lenta:
            peso_ema = -15
        if len(historial) > 10:
            ema_previa = calcular_ema(historial[:-1], st.session_state.ema_rapida)
            if ema_previa and ema_rapida > ema_previa * 1.001:
                peso_ema += 5
            elif ema_previa and ema_rapida < ema_previa * 0.999:
                peso_ema -= 5

    peso_bandas = 0
    if len(historial) >= 20:
        media_20 = sum(historial[-20:]) / 20
        desviacion_20 = statistics.stdev(historial[-20:]) if len(historial[-20:]) > 1 else 0
        if precio > media_20 + 2*desviacion_20:
            peso_bandas = -15
        elif precio < media_20 - 2*desviacion_20:
            peso_bandas = 15

    peso_macd = 0
    if len(historial) >= 26:
        ema_12 = calcular_ema(historial, 12)
        ema_26 = calcular_ema(historial, 26)
        if ema_12 and ema_26:
            macd = ema_12 - ema_26
            if len(historial) >= 35:
                historial_macd = []
                for i in range(26, len(historial)):
                    e12 = calcular_ema(historial[:i+1], 12)
                    e26 = calcular_ema(historial[:i+1], 26)
                    if e12 and e26:
                        historial_macd.append(e12 - e26)
                if len(historial_macd) >= 9:
                    senal_macd = sum(historial_macd[-9:]) / 9
                    if macd > senal_macd:
                        peso_macd = 10
                    elif macd < senal_macd:
                        peso_macd = -10

    peso_volumen = 0
    if volumen_onchain is not None:
        if volumen_onchain > 2.0:
            peso_volumen = 10
        elif volumen_onchain < VOLUMEN_MINIMO_24H:
            peso_volumen = -5

    peso_tendencia = 15 if tendencia_30d == "ALCISTA" else -15 if tendencia_30d == "BAJISTA" else 0
    if abs(cambio_30d) > 20:
        peso_tendencia *= 1.5

    peso_miedo = (10 if valor_miedo_codicia <= 20
                  else -10 if valor_miedo_codicia >= 80
                  else (50 - valor_miedo_codicia) * 0.2)

    peso_atr = 0
    if len(historial) >= 14:
        atr = calcular_atr(historial, 14)
        if atr and precio > 0:
            volatilidad_pct = (atr / precio) * 100
            if volatilidad_pct > 3:
                peso_atr = -5
            elif volatilidad_pct < 1:
                peso_atr = 5

    puntuacion = (peso_rsi + peso_ema + peso_bandas + peso_macd + peso_volumen
                  + peso_tendencia + peso_miedo + peso_atr)
    confianza = abs(puntuacion)
    if confianza < 20:
        return "HOLD", confianza, f"Puntuación baja ({confianza:.1f})", {}
    elif puntuacion > 0:
        return "BUY", confianza, f"Señal de compra ({puntuacion:.1f})", {}
    else:
        return "SELL", confianza, f"Señal de venta ({puntuacion:.1f})", {}
      # ══════════════════ PARTE 7/11: interfaz, cartera, salidas y contador ══════════════════

st.set_page_config(page_title="Bot Scalping Extremo + Tendencia 30d", layout="wide")

variables_requeridas = {
    "ultimo_precio": {"BTC": 0.0, "ETH": 0.0},
    "precio_referencia": {"BTC": 0.0, "ETH": 0.0},
    "precio_entrada": {"BTC": 0.0, "ETH": 0.0},
    "precio_maximo": {"BTC": 0.0, "ETH": 0.0},
    "posiciones": {"BTC": 0.0, "ETH": 0.0},
    "saldo": 1000.0,
    "ops_del_dia": 0,
    "operaciones": [],
    "ultima_accion": {"BTC": None, "ETH": None},
    "ciclo": 0,
    "historial_precios": {"BTC": deque(maxlen=200), "ETH": deque(maxlen=200)},
    "umbral_caida": 0.005,
    "toma_ganancia": 5.0,
    "limite_perdida": 1.0,
    "seguimiento": 0.5,
    "umbral_indicadores_activacion": 0.5,
    "puntaje_experto": 30,
    "rsi_sobreventa": 30,
    "rsi_sobrecompra": 80,
    "ema_rapida": 5,
    "ema_lenta": 12,
    "sl_disparado": {"BTC": False, "ETH": False},
    "sl_precio_minimo": {"BTC": 0.0, "ETH": 0.0},
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
    "cache_onchain": {
        "BTC": {"valor": None, "timestamp": 0},
        "ETH": {"valor": None, "timestamp": 0}
    },
    "tendencia_historica": {"BTC": {}, "ETH": {}},
    "confianza_umbral": 65,
    "intervalo_actualizacion": 5,
    "inicio_fase": datetime.now().isoformat(),
    "fase_actual": "operando",
    "analisis_anterior": {},
    "monto_del_dia": 0.0,
    "orden_pendiente_BTC": None,
    "orden_pendiente_ETH": None,
    "operar_24_7": False,
    "ultimo_respaldo_auto": time.time(),
    "ultimo_respaldo_operaciones": 0,
    "ultimo_dia": datetime.now().day,
    "saldo_sincronizado_bitso": False,       # 🆕 flag de control
    "ultima_sincronizacion": 0.0,            # 🆕 timestamp última sincronización
}

for nombre, valor_predeterminado in variables_requeridas.items():
    if nombre not in st.session_state:
        st.session_state[nombre] = valor_predeterminado

# 🔧 Forzar TP=5% y SL=1% SIEMPRE al arrancar
FORZAR_TP = 5.0
FORZAR_SL = 1.0
if st.session_state.get("toma_ganancia") != FORZAR_TP:
    st.session_state.toma_ganancia = FORZAR_TP
if st.session_state.get("limite_perdida") != FORZAR_SL:
    st.session_state.limite_perdida = FORZAR_SL

st.session_state.toma_ganancia = max(0.5, _a_decimal(st.session_state.get("toma_ganancia", FORZAR_TP), FORZAR_TP))
st.session_state.limite_perdida = max(0.5, _a_decimal(st.session_state.get("limite_perdida", FORZAR_SL), FORZAR_SL))
st.session_state.confianza_umbral = min(95, max(50, _a_entero(st.session_state.get("confianza_umbral", 65), 65)))

if "datos_cargados" not in st.session_state:
    restaurar_desde_archivo()
    st.session_state.datos_cargados = True


# ══════════════════ 🆕 SINCRONIZACIÓN CON BITSO ══════════════════
def sincronizar_estado_con_bitso(forzar=False):
    """
    Lee el saldo real de Bitso y ajusta el registro interno del bot.

    Reglas:
      - Solo sincroniza si NO hay orden pendiente del bot (para no pisar su estado).
      - Usa 'total' (incluye reservado en órdenes) para las posiciones.
      - Para el MXN usa 'available' (lo disponible para comprar).
      - Si detecta cripto que el bot no tenía registrado, lo asigna con
        precio_entrada = precio actual (conservador: asume que ya estaba en el mercado).
      - Si el bot tenía posición pero Bitso ya no tiene nada, la cierra.

    Retorna dict con el resumen de lo que cambió.
    """
    if not LLAVE_API_BITSO or not SECRETO_API_BITSO:
        return {"ok": False, "error": "Sin credenciales de Bitso"}

    # Cooldown: no sincronizar más de 1 vez cada 30s, salvo que sea forzado
    ahora = time.time()
    if not forzar and (ahora - float(st.session_state.get("ultima_sincronizacion", 0))) < 30:
        return {"ok": True, "omitido": "cooldown"}

    saldos = obtener_saldo_bitso(usar_cache=False)
    if not saldos:
        return {"ok": False, "error": st.session_state.get("error_saldo_bitso") or "sin datos"}

    cambios = []

    # MXN: usar 'available' (lo disponible para comprar)
    mxn_disponible = float(saldos.get("mxn", {}).get("available", 0.0))
    saldo_anterior = float(st.session_state.get("saldo", 0.0))
    if abs(mxn_disponible - saldo_anterior) > 0.01:
        st.session_state.saldo = mxn_disponible
        cambios.append(f"MXN: ${saldo_anterior:,.2f} → ${mxn_disponible:,.2f}")

    # BTC y ETH: usar 'total' (incluye lo reservado en órdenes abiertas)
    for simbolo in ("BTC", "ETH"):
        cantidad_bot = float(st.session_state.posiciones.get(simbolo, 0.0))
        cantidad_real = float(saldos.get(simbolo.lower(), {}).get("total", 0.0))
        tiene_orden_pendiente = bool(st.session_state.get(f"orden_pendiente_{simbolo}"))

        # Si el bot tiene una orden pendiente, no tocar esa posición (la está gestionando)
        if tiene_orden_pendiente:
            continue

        # Caso A: el bot cree que no tiene nada, pero Bitso sí tiene cripto
        if cantidad_bot <= 0.00000001 and cantidad_real > 0.00000001:
            st.session_state.posiciones[simbolo] = cantidad_real
            # Precio de entrada: precio actual (conservador: no sabemos a cuánto compró)
            precio_actual = float(st.session_state.ultimo_precio.get(simbolo, 0.0) or 0.0)
            if precio_actual > 0:
                st.session_state.precio_entrada[simbolo] = precio_actual
                st.session_state.precio_maximo[simbolo] = precio_actual
            cambios.append(f"{simbolo}: 0 → {cantidad_real:.8f} (importado de Bitso)")

        # Caso B: el bot cree que tiene, pero Bitso tiene menos (ajuste por comisión o venta externa)
        elif cantidad_bot > 0.00000001 and cantidad_real < cantidad_bot * 0.95:
            st.session_state.posiciones[simbolo] = cantidad_real
            if cantidad_real <= 0.00000001:
                st.session_state.precio_entrada[simbolo] = 0.0
                st.session_state.precio_maximo[simbolo] = 0.0
                cambios.append(f"{simbolo}: {cantidad_bot:.8f} → 0 (ya no hay en Bitso)")
            else:
                cambios.append(f"{simbolo}: {cantidad_bot:.8f} → {cantidad_real:.8f} (ajustado)")

        # Caso C: el bot tiene más que Bitso (raro, pero puede pasar por drift)
        elif cantidad_bot > 0.00000001 and cantidad_real > cantidad_bot * 1.05:
            st.session_state.posiciones[simbolo] = cantidad_real
            cambios.append(f"{simbolo}: {cantidad_bot:.8f} → {cantidad_real:.8f} (Bitso tiene más)")

    st.session_state["ultima_sincronizacion"] = ahora
    st.session_state["saldo_sincronizado_bitso"] = True

    if cambios:
        avisar(f"🔄 Sincronizado con Bitso: {' | '.join(cambios)}", "info")
        guardar_datos()

    return {"ok": True, "cambios": cambios}


# Sincronizar al arrancar (solo una vez por sesión)
if not st.session_state.get("saldo_sincronizado_bitso"):
    try:
        resultado_sync = sincronizar_estado_con_bitso(forzar=True)
        if resultado_sync.get("ok") and resultado_sync.get("cambios"):
            st.toast(f"🔄 Sincronizado con Bitso: {' | '.join(resultado_sync['cambios'])}", icon="🔄")
    except Exception as e:
        print(f"Error sincronizando con Bitso al arrancar: {e}")


# 🧹 Limpieza automática: si NO estamos en modo real, cancelar órdenes huérfanas en Bitso.
if (not MODO_REAL) and LLAVE_API_BITSO and SECRETO_API_BITSO:
    try:
        for libro in ("btc_mxn", "eth_mxn"):
            ruta_oa = f"/v3/open_orders/?book={libro}"
            cab_o, _ = _crear_cabecera_autenticacion("GET", ruta_oa)
            if not cab_o:
                continue
            r_oa = requests.get(URL_BASE_BITSO + ruta_oa,
                                headers={"Authorization": cab_o}, timeout=10)
            if r_oa.status_code == 200:
                abiertas = r_oa.json().get("payload") or []
                for o in abiertas:
                    oid = o.get("oid")
                    if oid:
                        if cancelar_orden_bitso(oid):
                            print(f"🧹 Orden huérfana cancelada: {oid} ({libro})")
    except Exception as e:
        print(f"Error en limpieza de órdenes huérfanas: {e}")

st.title("🧠 Scalping Extremo + Volumen + Tendencia 30d")

if MODO_REAL:
    st.error("🔴 **MODO REAL ACTIVADO** — Órdenes Maker con dinero real")
else:
    st.info("🟢 **MODO SIMULACIÓN** — Sin dinero real")

if not TELEGRAM_CONFIGURADO:
    st.warning(
        "🔑 **Telegram no está configurado.** Define `TELEGRAM_TOKEN` y `TELEGRAM_CHAT_ID` "
        "en los Secrets (App settings → Secrets) para recibir los avisos de ventas y errores."
    )

def _aplicar_compra(simbolo, monto, precio, comision=COMISION):
    cantidad = (monto * (1 - comision)) / precio
    cantidad_previa = float(st.session_state.posiciones.get(simbolo, 0.0))
    entrada_previa = float(st.session_state.precio_entrada.get(simbolo, 0.0))
    cantidad_nueva = cantidad_previa + cantidad
    st.session_state.saldo -= monto
    st.session_state.posiciones[simbolo] = cantidad_nueva
    if cantidad_nueva > 0:
        st.session_state.precio_entrada[simbolo] = (
            ((cantidad_previa * entrada_previa) + (cantidad * precio)) / cantidad_nueva
            if entrada_previa > 0 else precio
        )
    st.session_state.precio_maximo[simbolo] = max(
        float(st.session_state.precio_maximo.get(simbolo, 0.0)), precio)
    st.session_state.ops_del_dia += 1
    st.session_state.monto_del_dia = float(st.session_state.get("monto_del_dia", 0.0)) + monto
    st.session_state[f"venta_fallida_{simbolo}"] = 0.0
    return cantidad

def _aplicar_venta(simbolo, precio, cantidad_forzada=None):
    cantidad = (float(cantidad_forzada) if cantidad_forzada is not None
                else float(st.session_state.posiciones.get(simbolo, 0.0)))
    if cantidad <= 0:
        return 0.0, 0.0
    entrada = float(st.session_state.precio_entrada.get(simbolo, 0.0))
    neto = cantidad * precio * (1 - COMISION)
    ganancia = neto - (cantidad * entrada)
    st.session_state.saldo += neto
    st.session_state.posiciones[simbolo] = 0.0
    st.session_state.precio_entrada[simbolo] = 0.0
    st.session_state.precio_maximo[simbolo] = 0.0
    st.session_state.ops_del_dia += 1
    return neto, ganancia

def _cerrar_posicion(simbolo, precio, motivo, confianza=0, minima_ganancia_pct=0.0,
                     salida_rapida=False, forzar=False):
    if st.session_state.get(f"orden_pendiente_{simbolo}"):
        avisar(f"⏳ Ya hay una orden pendiente para {simbolo}: no se duplica la venta", "info")
        return False
    ultimo_fallo = float(st.session_state.get(f"venta_fallida_{simbolo}", 0.0) or 0.0)
    if ultimo_fallo and (time.time() - ultimo_fallo) < ESPERA_TRAS_FALLO_MIN * 60:
        return False
    cantidad = float(st.session_state.posiciones.get(simbolo, 0.0))
    if cantidad <= 0:
        return False
    entrada = float(st.session_state.precio_entrada.get(simbolo, 0.0))
    if not forzar and entrada > 0 and precio < entrada * (1 + minima_ganancia_pct / 100.0):
        ganancia_potencial = ((precio / entrada) - 1) * 100
        avisar(f"⏸️ {simbolo}: venta por {motivo} frenada; está en {ganancia_potencial:+.2f}% "
               f"(mínimo {minima_ganancia_pct:.2f}%). Esperando al límite de pérdida.", "warning")
        return False
    libro = "btc_mxn" if simbolo == "BTC" else "eth_mxn"
    st.session_state[f"ultima_compra_{simbolo}"] = st.session_state.ciclo
    etiqueta_salida = "mercado" if (salida_rapida and SALIDA_A_MERCADO) else "maker"
    motivo_completo = f"{motivo} [{etiqueta_salida}]"
    if MODO_REAL:
        if salida_rapida and SALIDA_A_MERCADO:
            orden = colocar_orden_bitso(libro, "sell", f"{cantidad:.8f}", "0", tipo="market")
            precio_envio = precio
            if not orden or orden.get("error"):
                avisar(f"⚠️ La orden a mercado de {simbolo} fue rechazada; "
                       f"reintentando con límite agresivo -{MARGEN_AGRESIVO_PCT}%", "warning")
                precio_envio = precio * (1 - MARGEN_AGRESIVO_PCT / 100.0)
                orden = colocar_orden_bitso(libro, "sell", f"{cantidad:.8f}",
                                            f"{precio_envio:.2f}", tipo="limit")
        else:
            precio_envio = precio * 1.002
            orden = colocar_orden_bitso(libro, "sell", f"{cantidad:.8f}",
                                        f"{precio_envio:.2f}", tipo="limit")
        if not orden or orden.get("error"):
            detalle = orden.get("error") if orden else "sin respuesta"
            st.session_state[f"venta_fallida_{simbolo}"] = time.time()
            avisar(f"❌ Venta {simbolo} falló: {detalle}", "error")
            enviar_telegram(f"❌ **VENTA {simbolo} RECHAZADA POR BITSO**\nBitso: {detalle}")
            return False
        st.session_state[f"orden_pendiente_{simbolo}"] = {
            "oid": orden.get("oid"), "side": "sell", "sym": simbolo,
            "price": precio_envio, "qty": cantidad, "monto": 0.0,
            "timestamp": time.time(), "confianza": confianza, "motivo": motivo_completo,
        }
        st.session_state[f"venta_fallida_{simbolo}"] = 0.0
        guardar_datos()
        enviar_telegram(f"⏳ **VENTA {simbolo}** ({motivo_completo})")
        avisar(f"⏳ Venta {simbolo} enviada ({motivo_completo})", "info")
        return True
    precio_sim = precio if etiqueta_salida == "mercado" else precio * 1.002
    neto, ganancia = _aplicar_venta(simbolo, precio_sim)
    porcentaje = ((precio_sim / entrada) - 1) * 100 if entrada else 0.0
    signo = "+" if ganancia > 0 else ""
    resultado = "GANANCIA" if ganancia > 0 else "PÉRDIDA"
    msg = (f"🔴 VENTA [MAKER-SIM] {simbolo} | {motivo_completo} | Neto: ${neto:.2f} | "
           f"PROFIT: {signo}${ganancia:.2f} ({signo}{porcentaje:.2f}%) ({resultado})")
    enviar_telegram(msg)
    st.session_state.operaciones.append((datetime.now(), msg))
    guardar_datos()
    avisar(f"✅ Venta {simbolo} ({motivo_completo}): {signo}${ganancia:.2f}", "success")
    return True

def _revisar_salidas(simbolo, precio):
    cantidad = float(st.session_state.posiciones.get(simbolo, 0.0))
    if cantidad <= 0:
        return False
    entrada = float(st.session_state.precio_entrada.get(simbolo, 0.0))
    if entrada <= 0:
        return False
    maximo = float(st.session_state.precio_maximo.get(simbolo, 0.0) or 0.0)
    if precio > maximo:
        maximo = precio
        st.session_state.precio_maximo[simbolo] = precio
    umbral_perdida = entrada * (1 - st.session_state.limite_perdida / 100.0)
    umbral_ganancia = entrada * (1 + st.session_state.toma_ganancia / 100.0)
    umbral_movil = maximo * (1 - st.session_state.seguimiento / 100.0)
    if st.session_state.modo_solo_senales and not (
            SALIDAS_IGNORAN_SOLO_SENALES and precio <= umbral_perdida):
        hay_aviso = precio <= umbral_perdida or precio >= umbral_ganancia
        clave_aviso = f"aviso_salida_{simbolo}"
        if hay_aviso and not st.session_state.get(clave_aviso):
            st.session_state[clave_aviso] = True
            enviar_telegram(f"🔇 **AVISO DE SALIDA {simbolo}**\nPrecio ${precio:,.0f} vs entrada ${entrada:,.0f}")
            avisar(f"🔇 {simbolo}: salida sugerida, pero 'solo señales' la bloquea", "warning")
        elif not hay_aviso and st.session_state.get(clave_aviso):
            st.session_state[clave_aviso] = False
        return False
    if precio <= umbral_perdida:
        return _cerrar_posicion(simbolo, precio,
                                f"límite de pérdida {st.session_state.limite_perdida}%",
                                salida_rapida=True)
    if TOMA_GANANCIA_FIJA:
        if precio >= umbral_ganancia:
            return _cerrar_posicion(simbolo, precio,
                                    f"toma de ganancia {st.session_state.toma_ganancia}%",
                                    salida_rapida=False)
    elif maximo >= umbral_ganancia and precio <= umbral_movil:
        return _cerrar_posicion(simbolo, precio,
                                f"detención móvil {st.session_state.seguimiento}%",
                                salida_rapida=True)
    return False

def _resumen_aciertos():
    try:
        inicio_fase = datetime.fromisoformat(st.session_state.inicio_fase)
    except Exception:
        inicio_fase = None
    aciertos = 0
    fallos = 0
    ganado = 0.0
    perdido = 0.0
    porcentajes = []
    for marca, msg in st.session_state.operaciones:
        if inicio_fase is not None and isinstance(marca, datetime) and marca < inicio_fase:
            continue
        if "VENTA" not in msg:
            continue
        coincidencia = re.search(r"PROFIT:\s*([+-]?\$?[\d,]+\.?\d*)", msg)
        if not coincidencia:
            continue
        try:
            ganancia = float(coincidencia.group(1).replace("$", "").replace(",", ""))
        except (TypeError, ValueError):
            continue
        if ganancia > 0:
            aciertos += 1
            ganado += ganancia
        else:
            fallos += 1
            perdido += abs(ganancia)
        porcentaje = re.search(r"PROFIT:[^(]*\(([+-]?[\d.]+)%\)", msg)
        if porcentaje:
            try:
                porcentajes.append(float(porcentaje.group(1)))
            except (TypeError, ValueError):
                pass
    cerradas = aciertos + fallos
    tasa = (aciertos / cerradas * 100) if cerradas else 0.0
    comision_ida_vuelta = COMISION * 100 * 2
    acierto_neto = st.session_state.toma_ganancia - comision_ida_vuelta
    fallo_neto = st.session_state.limite_perdida + comision_ida_vuelta
    equilibrio = (fallo_neto / (acierto_neto + fallo_neto) * 100
                  if (acierto_neto + fallo_neto) > 0 else 100.0)
    esperanza = 0.0
    if cerradas:
        esperanza = (tasa / 100) * acierto_neto - (1 - tasa / 100) * fallo_neto
    return {
        "aciertos": aciertos, "fallos": fallos, "cerradas": cerradas, "tasa": tasa,
        "ganado": ganado, "perdido": perdido, "neto": ganado - perdido,
        "ganancia_media_pct": (sum(porcentajes) / len(porcentajes)) if porcentajes else 0.0,
        "equilibrio": equilibrio, "esperanza": esperanza,
        "acierto_neto": acierto_neto, "fallo_neto": fallo_neto,
    }

def ejecutar_compra_profesional(simbolo, precio, confianza, razon, tendencia_30d):
    probabilidad = calcular_probabilidad(confianza)
    volumen = obtener_volumen_onchain(simbolo)
    if volumen is not None and volumen < VOLUMEN_MINIMO_24H:
        avisar(f"⚠️ Volumen 24h bajo ({volumen:.2f}B): compra {simbolo} omitida", "warning")
        return
    clave_orden = f"orden_pendiente_{simbolo}"
    if st.session_state.get(clave_orden):
        avisar(f"⏳ Ya hay una orden pendiente para {simbolo}", "info")
        return
    clave_compra = f"ultima_compra_{simbolo}"
    if st.session_state.get(clave_compra) == st.session_state.ciclo:
        return
    if probabilidad >= 100:
        monto_base, cantidad_ops = 100.0, 4
    elif probabilidad >= 75:
        monto_base, cantidad_ops = 75.0, 3
    elif probabilidad >= 50:
        monto_base, cantidad_ops = 50.0, 2
    else:
        avisar(f"⚠️ Probabilidad baja ({probabilidad:.1f}%): compra {simbolo} omitida", "warning")
        return
    monto = min(monto_base, MONTO_MAXIMO_POR_OPERACION)
    monto_hoy = float(st.session_state.get("monto_del_dia", 0.0))
    restante_dia = MONTO_MAXIMO_DIARIO - monto_hoy
    if monto <= 0 or restante_dia < monto:
        avisar(f"⚠️ Límite diario alcanzado (${monto_hoy:.2f}/${MONTO_MAXIMO_DIARIO:.2f})", "warning")
        return
    cantidad_ops = int(min(cantidad_ops, restante_dia // monto))
    if cantidad_ops < 1:
       # ══════════════════ PARTE 8/11: barra lateral y compra manual ══════════════════

st.sidebar.header("⚙️ Configuración Principal")
st.session_state.umbral_caida = st.sidebar.number_input(
    "Caída para comprar (%)", min_value=0.001, max_value=50.0, step=0.001,
    value=float(st.session_state.umbral_caida))

valor_seguro_toma = max(0.5, float(st.session_state.toma_ganancia))
st.session_state.toma_ganancia = st.sidebar.number_input(
    "Toma de ganancia (%)", min_value=0.5, max_value=50.0, step=0.1, value=valor_seguro_toma)

st.session_state.limite_perdida = st.sidebar.number_input(
    "Límite de pérdida (%)", min_value=0.5, max_value=20.0,
    value=float(st.session_state.limite_perdida), step=0.5)
st.session_state.seguimiento = st.sidebar.number_input(
    "Detención móvil (%)", min_value=0.2, max_value=5.0,
    value=float(st.session_state.seguimiento), step=0.1)
st.session_state.umbral_indicadores_activacion = st.sidebar.number_input(
    "Activar indicadores ±(%)", min_value=0.1, max_value=20.0, step=0.1,
    value=float(st.session_state.umbral_indicadores_activacion))

st.sidebar.header("🧠 Modo de aprendizaje")
st.session_state.modo_aprendizaje = st.sidebar.checkbox(
    "✅ Modo aprendizaje activado", value=st.session_state.modo_aprendizaje)

st.sidebar.header("🎯 Probabilidad mínima")
valor_seguro_umbral = min(95, max(50, int(st.session_state.confianza_umbral)))
st.session_state.confianza_umbral = st.sidebar.slider(
    "Probabilidad mínima para operar (%)",
    min_value=50, max_value=95, value=valor_seguro_umbral, step=5,
    help="50% = señales débiles | 65% = equilibrio | 80%+ = solo señales muy fuertes"
)

st.sidebar.header("🌍 Horario de operación")
st.session_state.operar_24_7 = st.sidebar.checkbox(
    "🔥 Operar 24/7 (sin restricción de horario)",
    value=bool(st.session_state.operar_24_7)
)

st.sidebar.header("🧠 Indicadores")
st.session_state.rsi_sobreventa = st.sidebar.number_input(
    "RSI sobreventa", 20, 40, int(st.session_state.rsi_sobreventa), 1)
st.session_state.rsi_sobrecompra = st.sidebar.number_input(
    "RSI sobrecompra", 70, 90, int(st.session_state.rsi_sobrecompra), 1)
st.session_state.ema_rapida = st.sidebar.number_input(
    "EMA rápida", 3, 20, int(st.session_state.ema_rapida), 1)
st.session_state.ema_lenta = st.sidebar.number_input(
    "EMA lenta", 10, 50, int(st.session_state.ema_lenta), 1)

st.sidebar.header("📡 Modo de operación")
st.session_state.modo_solo_senales = st.sidebar.checkbox(
    "🔇 Solo señales (no ejecutar)", value=st.session_state.modo_solo_senales)

st.sidebar.caption("💰 La cartera se muestra en el panel principal (se refresca en cada ciclo).")
st.sidebar.caption("📌 Las salidas de riesgo se aplican siempre, sin depender del horario ni "
                   "de la fase. El límite de pérdida sale a mercado y protege incluso con "
                   "'solo señales' activado; la toma de ganancia usa orden Maker.")

# 🆕 ===== SECCIÓN DE TELEGRAM =====
st.sidebar.markdown("---")
st.sidebar.markdown("**📡 Telegram**")
if TELEGRAM_CONFIGURADO:
    st.sidebar.success("✅ Chat personal configurado")
else:
    st.sidebar.warning("⚠️ Falta TELEGRAM_TOKEN / TELEGRAM_CHAT_ID")
if CANAL_CONFIGURADO:
    st.sidebar.success(f"✅ Canal configurado (señales ≥{UMBRAL_SENAL_FUERTE}%)")
else:
    st.sidebar.info("ℹ️ Canal no configurado (opcional)")
    st.sidebar.caption("Define `TELEGRAM_CANAL_ID` en Secrets para recibir señales fuertes.")

if st.sidebar.button("📨 Probar Telegram (chat personal)"):
    ok = enviar_telegram("🧪 Prueba: chat personal funcionando desde el bot.")
    st.sidebar.success("✅ Enviado") if ok else st.sidebar.error("❌ Falló el envío")

if st.sidebar.button("📢 Probar Telegram (canal)"):
    if not CANAL_CONFIGURADO:
        st.sidebar.error("Canal no configurado")
    else:
        ok = enviar_canal_telegram("🧪 Prueba: canal funcionando desde el bot.")
        st.sidebar.success("✅ Enviado al canal") if ok else st.sidebar.error("❌ Falló el envío")

# 🆕 ===== BOTÓN DE PÁNICO =====
st.sidebar.markdown("---")
st.sidebar.markdown("**🚨 Emergencia**")
if st.sidebar.button("🚨 CANCELAR TODAS LAS ÓRDENES EN BITSO", type="primary"):
    if not LLAVE_API_BITSO or not SECRETO_API_BITSO:
        st.sidebar.error("Sin credenciales de Bitso")
    else:
        canceladas = 0
        errores = 0
        for libro in ("btc_mxn", "eth_mxn"):
            try:
                ruta_oa = f"/v3/open_orders/?book={libro}"
                cab_o, _ = _crear_cabecera_autenticacion("GET", ruta_oa)
                if not cab_o:
                    continue
                r_oa = requests.get(URL_BASE_BITSO + ruta_oa,
                                    headers={"Authorization": cab_o}, timeout=10)
                if r_oa.status_code == 200:
                    abiertas = r_oa.json().get("payload") or []
                    for o in abiertas:
                        oid = o.get("oid")
                        if oid and cancelar_orden_bitso(oid):
                            canceladas += 1
                        else:
                            errores += 1
            except Exception as e:
                errores += 1
                print(f"Error cancelando en {libro}: {e}")
        st.session_state.orden_pendiente_BTC = None
        st.session_state.orden_pendiente_ETH = None
        if canceladas > 0:
            st.sidebar.success(f"✅ {canceladas} orden(es) cancelada(s)")
        elif errores == 0:
            st.sidebar.info("No había órdenes abiertas")
        else:
            st.sidebar.warning(f"⚠️ {errores} error(es). Revisa Bitso manualmente.")
        time.sleep(1)
        st.rerun()

# ===== COMPRA MANUAL =====
def _compra_manual(simbolo, libro):
    with st.sidebar.expander(f"🔍 Diagnóstico de compra {simbolo}", expanded=True):
        precio = obtener_precio_bitso(libro)
        posicion_actual = st.session_state.posiciones.get(simbolo, 0)
        st.write("**Precio:** " + str(precio))
        st.write("**Posición actual:** " + str(posicion_actual))
        st.write("**MODO_REAL:** " + str(MODO_REAL))
        st.write("**Máximo por operación:** $" + str(MONTO_MAXIMO_POR_OPERACION))
        st.write("**Máximo por día:** $" + str(MONTO_MAXIMO_DIARIO))
        st.write("**Monto usado hoy:** $" + str(st.session_state.get("monto_del_dia", 0)))
        if not precio:
            st.error("❌ No se pudo obtener el precio")
            return
        if posicion_actual > 0:
            st.warning("⚠️ Ya tienes posición: " + str(posicion_actual))
            return
        if not MODO_REAL:
            st.error("❌ MODO_REAL está en FALSE. Actívalo en Secrets.")
            return
        monto = min(50.0, MONTO_MAXIMO_POR_OPERACION)
        precio_objetivo = precio * 0.998
        cantidad = (monto * 0.999) / precio_objetivo
        st.write("**Monto:** $" + str(monto))
        st.write("**Precio objetivo:** $" + str(round(precio_objetivo, 2)))
        st.write("**Cantidad:** " + str(round(cantidad, 8)) + " " + simbolo)
        with st.spinner("Enviando orden a Bitso..."):
            orden = colocar_orden_bitso(libro, "buy", str(round(cantidad, 8)),
                                        str(round(precio_objetivo, 2)))
        if orden and not orden.get("error"):
            st.success("✅ Orden colocada: " + str(orden.get("oid")))
            st.json(orden)
            st.session_state[f"orden_pendiente_{simbolo}"] = {
                "oid": orden.get("oid"), "side": "buy", "sym": simbolo,
                "price": precio_objetivo, "qty": cantidad, "monto": monto,
                "cant": 1, "timestamp": time.time(), "confianza": 0,
                "motivo": "compra manual",
            }
            msg = f"🟢 ORDEN MAKER [REAL] {simbolo} | {cantidad:.8f} a ${precio_objetivo:,.2f}"
            enviar_telegram(msg)
            st.session_state.operaciones.append((datetime.now(), msg))
            guardar_datos()
        else:
            texto_error = orden.get("error", "desconocido") if orden else "sin respuesta"
            st.error("❌ Error: " + str(texto_error))
            st.json(orden)

if st.sidebar.button("🟢 Comprar BTC AHORA"):
    _compra_manual("BTC", "btc_mxn")

if st.sidebar.button("🟢 Comprar ETH AHORA"):
    _compra_manual("ETH", "eth_mxn")

# 🆕 ===== ENVÍO DE SEÑALES AL CANAL =====
def enviar_senal_telegram(simbolo, tipo, precio, razon, confianza, volumen_onchain,
                          cambio_30d, tendencia_30d):
    """
    Envía una señal fuerte al CANAL privado (si está configurado).
    Si no hay canal, la manda al chat personal como respaldo.
    """
    try:
        probabilidad = calcular_probabilidad(confianza)
        texto_volumen = f"{volumen_onchain:.2f}B USD" if volumen_onchain is not None else "N/A"
        emoji_tipo = "🟢" if tipo == "BUY" else "🔴" if tipo == "SELL" else "⚪"
        msg = (f"📢 **SEÑAL {emoji_tipo} {tipo} — {simbolo}**\n"
               f"🎯 Probabilidad: {probabilidad:.1f}%\n"
               f"💰 Precio: ${precio:,.0f} MXN\n"
               f"📝 Razón: {razon}\n"
               f"📊 Volumen 24h: {texto_volumen}\n"
               f"📈 Cambio 30d: {cambio_30d:+.2f}%\n"
               f"🧭 Tendencia 30d: {tendencia_30d}\n"
               f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        if CANAL_CONFIGURADO:
            return enviar_canal_telegram(msg)
        else:
            return enviar_telegram(msg)
    except Exception as e:
        print(f"Error enviando señal al canal: {e}")
        return False
      # ══════════════════ PARTE 9/11: ciclo, panel y refresco ══════════════════

HORAS_FASE_APRENDIZAJE = 48

def _reconciliar_cartera():
    if not MODO_REAL:
        return
    saldos = obtener_saldo_bitso()
    if not saldos:
        return
    for simbolo in ["BTC", "ETH"]:
        cantidad_registro = float(st.session_state.posiciones.get(simbolo, 0.0))
        if cantidad_registro <= 0:
            continue
        if st.session_state.get(f"orden_pendiente_{simbolo}"):
            continue
        cantidad_real = float(saldos.get(simbolo.lower(), {}).get("total", 0.0))
        if cantidad_real > cantidad_registro * 0.05:
            continue
        entrada = float(st.session_state.precio_entrada.get(simbolo, 0.0))
        precio_actual = float(st.session_state.ultimo_precio.get(simbolo, 0.0))
        neto = cantidad_registro * precio_actual * (1 - COMISION)
        ganancia = neto - (cantidad_registro * entrada)
        signo = "+" if ganancia > 0 else ""
        porcentaje_estimado = ((precio_actual / entrada) - 1) * 100 if entrada else 0.0
        st.session_state.posiciones[simbolo] = 0.0
        st.session_state.precio_entrada[simbolo] = 0.0
        st.session_state.precio_maximo[simbolo] = 0.0
        msg = (f"🔴 VENTA [RECONCILIADA] {simbolo} | Bitso ya no tenía el saldo | "
               f"Neto aprox: ${neto:.2f} | PROFIT: {signo}${ganancia:.2f} "
               f"({signo}{porcentaje_estimado:.2f}%) (estimado)")
        st.session_state.operaciones.append((datetime.now(), msg))
        avisar(f"🔁 Reconcilié {simbolo}: ya no hay saldo en Bitso.", "warning")
        enviar_telegram(msg)
        guardar_datos()

def _ejecutar_ordenes_pendientes():
    for simbolo in ["BTC", "ETH"]:
        try:
            estado, datos = verificar_orden_pendiente(simbolo)
            if estado == "ejecutada" and isinstance(datos, dict):
                lado = datos.get("side", "buy")
                precio_ejecucion = _a_decimal(datos.get("price"), 0.0)
                if precio_ejecucion <= 0:
                    continue
                if lado == "buy":
                    monto = _a_decimal(datos.get("monto"), 0.0)
                    if monto > 0 and st.session_state.saldo >= monto:
                        cantidad_real = _aplicar_compra(simbolo, monto, precio_ejecucion)
                        guardar_datos()
                        msg = (f"✅ ORDEN MAKER EJECUTADA {simbolo} | {cantidad_real:.8f} a "
                               f"${precio_ejecucion:,.0f} | Com: {COMISION*100:.2f}%")
                        enviar_telegram(msg)
                        st.session_state.operaciones.append((datetime.now(), msg))
                        avisar(f"✅ Maker {simbolo} ejecutada", "success")
                    else:
                        avisar(f"⚠️ Maker {simbolo} ejecutada sin monto válido", "warning")
                else:
                    cantidad = _a_decimal(datos.get("qty"), 0.0)
                    if cantidad > 0:
                        neto, ganancia = _aplicar_venta(simbolo, precio_ejecucion,
                                                        cantidad_forzada=cantidad)
                        resultado = "GANANCIA" if ganancia > 0 else "PÉRDIDA"
                        signo = "+" if ganancia > 0 else ""
                        motivo = datos.get("motivo", "")
                        msg = (f"🔴 VENTA [MAKER-REAL] {simbolo} | {motivo} | Neto: ${neto:.2f} | "
                               f"PROFIT: {signo}${ganancia:.2f} ({resultado})")
                        enviar_telegram(msg)
                        st.session_state.operaciones.append((datetime.now(), msg))
                        guardar_datos()
                        avisar(f"✅ Venta Maker {simbolo} ejecutada", "success")
            elif estado == "cancelada":
                avisar(f"⚠️ Orden Maker {simbolo} cancelada (tiempo agotado)", "warning")
                enviar_telegram(f"⚠️ Orden Maker {simbolo} cancelada por tiempo agotado.")
        except Exception as e:
            print(f"Error verificando la orden {simbolo}: {e}")
            continue

def _respaldos_automaticos():
    ahora = time.time()
    if "ultimo_respaldo_auto" not in st.session_state or not st.session_state.ultimo_respaldo_auto:
        st.session_state.ultimo_respaldo_auto = ahora
    if (ahora - float(st.session_state.ultimo_respaldo_auto)) / 3600 >= 24:
        try:
            clave_respaldo, _ = crear_respaldo()
            if clave_respaldo:
                st.session_state.ultimo_respaldo_auto = ahora
                limpiar_respaldos_viejos(maximo_respaldos=10)
                enviar_telegram(f"💾 **RESPALDO AUTOMÁTICO (24h)**\n{clave_respaldo}")
        except Exception:
            pass
    if "ultimo_respaldo_operaciones" not in st.session_state:
        st.session_state.ultimo_respaldo_operaciones = 0
    operaciones_actuales = len(st.session_state.operaciones)
    if operaciones_actuales - int(st.session_state.ultimo_respaldo_operaciones) >= 100:
        try:
            clave_respaldo, _ = crear_respaldo()
            if clave_respaldo:
                st.session_state.ultimo_respaldo_operaciones = operaciones_actuales
                limpiar_respaldos_viejos(maximo_respaldos=10)
                enviar_telegram(f"💾 **RESPALDO AUTOMÁTICO (100 operaciones)**\n{clave_respaldo}")
        except Exception:
            pass

def ejecutar_ciclo(interfaz):
    btc = obtener_precio_bitso("btc_mxn")
    eth = obtener_precio_bitso("eth_mxn")
    if btc is None or eth is None:
        interfaz["tabla"].error("❌ Error al obtener los precios.")
        return
    st.session_state.ultimo_precio["BTC"] = btc
    st.session_state.ultimo_precio["ETH"] = eth
    st.session_state.historial_precios["BTC"].append(btc)
    st.session_state.historial_precios["ETH"].append(eth)
    if st.session_state.precio_referencia["BTC"] == 0:
        st.session_state.precio_referencia["BTC"] = btc
        st.session_state.precio_referencia["ETH"] = eth
    hoy = datetime.now().day
    if hoy != st.session_state.ultimo_dia:
        st.session_state.ops_del_dia = 0
        st.session_state.ultimo_dia = hoy
        st.session_state.monto_del_dia = 0.0
    st.session_state.ciclo += 1
    if st.session_state.ciclo % 5 == 0:
        guardar_datos()
    _respaldos_automaticos()
    valor_miedo, etiqueta_miedo = obtener_miedo_codicia()
    cambio_btc = (btc - st.session_state.precio_referencia["BTC"]) / st.session_state.precio_referencia["BTC"] * 100
    cambio_eth = (eth - st.session_state.precio_referencia["ETH"]) / st.session_state.precio_referencia["ETH"] * 100
    st.session_state.tendencia["BTC"] = analizar_tendencia(st.session_state.historial_precios["BTC"])
    st.session_state.tendencia["ETH"] = analizar_tendencia(st.session_state.historial_precios["ETH"])
    for simbolo in ["BTC", "ETH"]:
        if st.session_state.ciclo % 60 == 1 or not st.session_state.tendencia_historica.get(simbolo):
            tendencia = obtener_tendencia_historica(simbolo, 30)
            if tendencia:
                st.session_state.tendencia_historica[simbolo] = tendencia
    st.session_state.indicadores_activados["BTC"] = abs(cambio_btc) >= st.session_state.umbral_indicadores_activacion
    st.session_state.indicadores_activados["ETH"] = abs(cambio_eth) >= st.session_state.umbral_indicadores_activacion
    volumen_onchain_btc = obtener_volumen_onchain("BTC")
    volumen_onchain_eth = obtener_volumen_onchain("ETH")
    tendencia_btc = st.session_state.tendencia_historica.get("BTC", {}) or {}
    tendencia_eth = st.session_state.tendencia_historica.get("ETH", {}) or {}
    senal_btc, confianza_btc, razon_btc, _ = analisis_avanzado("BTC", btc, valor_miedo)
    senal_eth, confianza_eth, razon_eth, _ = analisis_avanzado("ETH", eth, valor_miedo)
    probabilidad_btc = calcular_probabilidad(confianza_btc)
    probabilidad_eth = calcular_probabilidad(confianza_eth)
    umbral_probabilidad = st.session_state.confianza_umbral
    estado_horario, emoji_horario, descripcion_horario, es_buen_horario = obtener_horario_operacion()
    horario_para_operar = es_buen_horario or st.session_state.get("operar_24_7", False)

    # 🆕 ===== ENVIAR SEÑALES FUERTES AL CANAL DE TELEGRAM =====
    for sim_actual, senal_actual, conf_actual, razon_actual, prob_actual, precio_actual in [
        ("BTC", senal_btc, confianza_btc, razon_btc, probabilidad_btc, btc),
        ("ETH", senal_eth, confianza_eth, razon_eth, probabilidad_eth, eth),
    ]:
        if senal_actual != "HOLD" and prob_actual >= UMBRAL_SENAL_FUERTE:
            clave_senal = f"ultima_senal_enviada_{sim_actual}"
            ultima = st.session_state.get(clave_senal, 0)
            if st.session_state.ciclo - ultima > 10:
                datos_t30 = st.session_state.tendencia_historica.get(sim_actual, {}) or {}
                cambio_t30 = datos_t30.get("cambio_porcentual", 0)
                tendencia_t30 = datos_t30.get("tendencia", "N/A")
                vol_onchain = (volumen_onchain_btc if sim_actual == "BTC"
                               else volumen_onchain_eth)
                if enviar_senal_telegram(
                    sim_actual, senal_actual, precio_actual,
                    razon_actual, conf_actual, vol_onchain,
                    cambio_t30, tendencia_t30
                ):
                    st.session_state[clave_senal] = st.session_state.ciclo
                    avisar(f"📢 Señal {senal_actual} de {sim_actual} enviada al canal", "info")

    _ejecutar_ordenes_pendientes()
    if st.session_state.ciclo % 12 == 0:
        _reconciliar_cartera()
    for simbolo_salida, precio_salida in [("BTC", btc), ("ETH", eth)]:
        if st.session_state.posiciones.get(simbolo_salida, 0) > 0:
            st.session_state.precio_maximo[simbolo_salida] = max(
                float(st.session_state.precio_maximo.get(simbolo_salida, 0.0) or 0.0),
                precio_salida)
        _revisar_salidas(simbolo_salida, precio_salida)
    ahora = datetime.now()
    try:
        inicio_fase = datetime.fromisoformat(st.session_state.inicio_fase)
    except Exception:
        inicio_fase = ahora
        st.session_state.inicio_fase = ahora.isoformat()
    horas_transcurridas = (ahora - inicio_fase).total_seconds() / 3600
    horas_restantes = max(0, HORAS_FASE_APRENDIZAJE - horas_transcurridas)
    if horas_transcurridas >= HORAS_FASE_APRENDIZAJE and st.session_state.fase_actual == "operando":
        st.session_state.fase_actual = "analizando"
        enviar_telegram("🧠 **FASE DE ANÁLISIS INICIADA**")
    if st.session_state.fase_actual == "analizando":
        resultado = analizar_fase_aprendizaje()
        if resultado.get("suficiente"):
            st.session_state.analisis_anterior = resultado
            mejor_hora_texto = f"{resultado['mejor_hora']}:00" if resultado['mejor_hora'] is not None else "N/A"
            peor_hora_texto = f"{resultado['peor_hora']}:00" if resultado['peor_hora'] is not None else "N/A"
            signo_total = "+" if resultado.get('profit_total', 0) >= 0 else ""
            msg_analisis = (
                f"📊 **ANÁLISIS DE FASE COMPLETADO**\n\n"
                f"📈 Operaciones: {resultado['total_operaciones']}\n"
                f"✅ Ganancias: {resultado['ganancias']}\n"
                f"❌ Pérdidas: {resultado['perdidas']}\n"
                f"🎯 Tasa de acierto: {resultado['win_rate']:.1f}%\n"
                f"💰 Ganancia total: {signo_total}${resultado.get('profit_total', 0):.2f}\n"
                f"⏰ Mejor hora: {mejor_hora_texto}\n"
                f"⏰ Peor hora: {peor_hora_texto}\n\n"
                f"**Ajustes aplicados:**\n"
                + "\n".join([f"• {a}" for a in resultado['ajustes_aplicados']])
            )
            enviar_telegram(msg_analisis)
        st.session_state.inicio_fase = ahora.isoformat()
        st.session_state.fase_actual = "operando"
        st.session_state.rendimiento = {
            "BTC": {"ganadas": 0, "perdidas": 0, "total": 0, "ultimas_10": []},
            "ETH": {"ganadas": 0, "perdidas": 0, "total": 0, "ultimas_10": []}
        }
        guardar_datos()
        enviar_telegram(f"🔄 **NUEVA FASE DE {HORAS_FASE_APRENDIZAJE}h INICIADA**")
    interfaz["tabla"].subheader("📊 Señales + Volumen + Tendencia 30d")
    interfaz["tabla"].table({
        "Moneda": ["Bitcoin", "Ethereum"],
        "Precio MXN": [f"${btc:,.0f}", f"${eth:,.0f}"],
        "Cambio": [f"{cambio_btc:+.2f}%", f"{cambio_eth:+.2f}%"],
        "Tendencia": [st.session_state.tendencia["BTC"], st.session_state.tendencia["ETH"]],
        "Señal": [senal_btc, senal_eth],
        "Prob. de acierto": [f"{probabilidad_btc:.1f}%", f"{probabilidad_eth:.1f}%"],
        "Umbral mínimo": [f"{umbral_probabilidad:.1f}%", f"{umbral_probabilidad:.1f}%"],
        "Volumen 24h": [
            f"{volumen_onchain_btc:.2f}B" if volumen_onchain_btc is not None else "N/A",
            f"{volumen_onchain_eth:.2f}B" if volumen_onchain_eth is not None else "N/A"
        ],
        "Tendencia 30d": [
            tendencia_btc.get("tendencia", "N/A") if tendencia_btc else "N/A",
            tendencia_eth.get("tendencia", "N/A") if tendencia_eth else "N/A"
        ]
    })
    texto_horario = f"{emoji_horario} **{estado_horario}** → {descripcion_horario}"
    if st.session_state.get("operar_24_7", False):
        interfaz["horario"].info(
            f"🔥 **MODO 24/7 ACTIVADO** — Operando sin restricción de horario | "
            f"Horario actual: {estado_horario}")
    elif es_buen_horario:
        interfaz["horario"].success(texto_horario)
    else:
        interfaz["horario"].warning(texto_horario)
    if st.session_state.fase_actual == "operando":
        interfaz["fase"].info(
            f"📅 **FASE OPERATIVA** — Próxima auto-evaluación en "
            f"{horas_restantes:.1f} horas ({HORAS_FASE_APRENDIZAJE}h por ciclo)")
    else:
        interfaz["fase"].warning("🧠 **ANALIZANDO FASE**...")
    if "ultimo_horario_alerta" not in st.session_state:
        st.session_state.ultimo_horario_alerta = None
    if st.session_state.ultimo_horario_alerta != estado_horario:
        zona_mexico = timezone(timedelta(hours=-6))
        hora_mexico = datetime.now(zona_mexico).strftime('%H:%M')
        if es_buen_horario:
            msg_horario = (f"✅ **BUEN HORARIO**\n\n{emoji_horario} **{estado_horario}**\n"
                           f"{descripcion_horario}\n\n📍 Hora México: {hora_mexico}")
        else:
            msg_horario = (f"⚠️ **CAMBIO DE SESIÓN**\n\n{emoji_horario} **{estado_horario}**\n"
                           f"{descripcion_horario}\n\n📍 Hora México: {hora_mexico}")
        enviar_telegram(msg_horario)
        st.session_state.ultimo_horario_alerta = estado_horario
    texto_info = (
        f"Ciclo: {st.session_state.ciclo} | "
        f"Toma de ganancia: {st.session_state.toma_ganancia}% | "
        f"Límite de pérdida: {st.session_state.limite_perdida}% | "
        f"Detención móvil: {st.session_state.seguimiento}% | "
        f"Miedo/Codicia: {valor_miedo}/100 ({etiqueta_miedo}) | "
        f"Aprendizaje: {'✅' if st.session_state.modo_aprendizaje else '❌'} | "
        f"Prob. mínima: {umbral_probabilidad:.1f}% | "
        f"Modo: {'🔥 24/7' if st.session_state.get('operar_24_7', False) else '⏰ Con horario'} | "
        f"Operaciones de la fase: {len(st.session_state.operaciones)}"
    )
    interfaz["info"].caption(texto_info)
    # ══════════════════ PARTE 10/11: panel (cartera, posiciones, historial) ══════════════════

    saldo_real = obtener_saldo_bitso()
    columnas = interfaz["metricas"].columns(4)
    if saldo_real:
        mxn_data = saldo_real.get("mxn", {})
        mxn_disponible = float(mxn_data.get("available", 0.0))
        mxn_total = float(mxn_data.get("total", 0.0))
        mxn_reservado = max(0.0, mxn_total - mxn_disponible)
        btc_data = saldo_real.get("btc", {})
        btc_disponible = float(btc_data.get("available", 0.0))
        btc_total = float(btc_data.get("total", 0.0))
        btc_reservado = max(0.0, btc_total - btc_disponible)
        eth_data = saldo_real.get("eth", {})
        eth_disponible = float(eth_data.get("available", 0.0))
        eth_total = float(eth_data.get("total", 0.0))
        eth_reservado = max(0.0, eth_total - eth_disponible)
        valor_total_real = (mxn_total + (btc_total * btc) + (eth_total * eth))
        hay_reservado = (mxn_reservado > 0.01 or btc_reservado > 0.00000001
                         or eth_reservado > 0.00000001)
        columnas[0].metric(
            "Saldo MXN (Bitso)",
            f"${mxn_total:,.2f}",
            help=(f"Total: ${mxn_total:,.2f} | Disponible: ${mxn_disponible:,.2f}"
                  + (f" | Reservado: ${mxn_reservado:,.2f}" if mxn_reservado > 0.01 else ""))
        )
        columnas[1].metric("Valor total (Bitso)", f"${valor_total_real:,.2f}")
        columnas[2].metric(
            "BTC / ETH (Bitso)",
            f"{btc_total:.6f} / {eth_total:.6f}",
            help=(f"BTC: disp {btc_disponible:.6f} / total {btc_total:.6f}\n"
                  f"ETH: disp {eth_disponible:.6f} / total {eth_total:.6f}")
        )
        columnas[3].metric("Operaciones hoy", st.session_state.ops_del_dia)
        if hay_reservado:
            detalle = []
            if mxn_reservado > 0.01:
                detalle.append(f"MXN: ${mxn_reservado:,.2f}")
            if btc_reservado > 0.00000001:
                detalle.append(f"BTC: {btc_reservado:.8f}")
            if eth_reservado > 0.00000001:
                detalle.append(f"ETH: {eth_reservado:.8f}")
            interfaz["cartera"].warning(
                f"🔒 Tienes fondos reservados en órdenes abiertas → "
                + " · ".join(detalle)
                + " | Usa el botón de pánico si quieres liberarlos."
            )
        else:
            interfaz["cartera"].caption(
                f"🔗 Datos reales de Bitso — BTC ${btc:,.0f} · ETH ${eth:,.0f} MXN | "
                f"📋 Registro interno del bot: ${st.session_state.saldo:,.2f} "
                f"({st.session_state.posiciones.get('BTC', 0):.6f} BTC / "
                f"{st.session_state.posiciones.get('ETH', 0):.6f} ETH)"
            )
    else:
        valor_total_simulado = st.session_state.saldo
        for simbolo in ["BTC", "ETH"]:
            precio_actual = st.session_state.ultimo_precio.get(simbolo, 0)
            cantidad = st.session_state.posiciones.get(simbolo, 0)
            if cantidad > 0 and precio_actual > 0:
                valor_total_simulado += cantidad * precio_actual
        columnas[0].metric("Saldo MXN (simulado)", f"${st.session_state.saldo:,.2f}")
        columnas[1].metric("Valor total (simulado)", f"${valor_total_simulado:,.2f}")
        columnas[2].metric("BTC / ETH (simulado)",
                           f"{st.session_state.posiciones.get('BTC', 0):.6f} / "
                           f"{st.session_state.posiciones.get('ETH', 0):.6f}")
        columnas[3].metric("Operaciones hoy", st.session_state.ops_del_dia)
        interfaz["cartera"].warning(
            "⚠️ No se pudo leer el saldo real de Bitso: "
            + str(st.session_state.get("error_saldo_bitso") or "sin detalle")
        )
    for simbolo_pos, precio_pos in [("BTC", btc), ("ETH", eth)]:
        cantidad_pos = float(st.session_state.posiciones.get(simbolo_pos, 0.0))
        if cantidad_pos <= 0:
            continue
        entrada_pos = float(st.session_state.precio_entrada.get(simbolo_pos, 0.0))
        if entrada_pos <= 0:
            continue
        objetivo = entrada_pos * (1 + st.session_state.toma_ganancia / 100.0)
        corte = entrada_pos * (1 - st.session_state.limite_perdida / 100.0)
        aviso_pos = (f"🎯 **{simbolo_pos}**: {cantidad_pos:.8f} unidades | "
                     f"entrada ${entrada_pos:,.0f} | "
                     f"vende en ${objetivo:,.0f} (+{st.session_state.toma_ganancia}%) | "
                     f"corta en ${corte:,.0f} (-{st.session_state.limite_perdida}%) | "
                     f"precio ahora ${precio_pos:,.0f} "
                     f"({((precio_pos / entrada_pos) - 1) * 100:+.2f}%)")
        if precio_pos >= objetivo:
            interfaz["posiciones"].success("✅ " + aviso_pos)
        elif precio_pos <= corte:
            interfaz["posiciones"].error("🚨 " + aviso_pos)
        else:
            interfaz["posiciones"].info(aviso_pos)
    interfaz["historial"].subheader(f"📜 Historial (últimas 10 de {len(st.session_state.operaciones)})")
    if st.session_state.operaciones:
        texto = ""
        for marca, msg in reversed(st.session_state.operaciones[-10:]):
            msg_corto = msg.replace("\n", " | ")[:90]
            texto += f"{marca.strftime('%H:%M:%S')} - {msg_corto}\n"
        interfaz["historial"].text(texto)
    else:
        interfaz["historial"].text("Sin operaciones aún.")
    resumen = _resumen_aciertos()
    interfaz["aciertos"].subheader("📈 Aciertos vs fallos de la fase")
    columnas_ac = interfaz["aciertos"].columns(4)
    columnas_ac[0].metric("Aciertos", resumen["aciertos"])
    columnas_ac[1].metric("Fallos", resumen["fallos"])
    columnas_ac[2].metric("Tasa de acierto", f"{resumen['tasa']:.1f}%")
    columnas_ac[3].metric(
        "Punto de equilibrio", f"{resumen['equilibrio']:.1f}%",
        help="Aciertos que necesitas para no perder, según tu TP, tu SL y las comisiones.")
    if resumen["cerradas"] == 0:
        interfaz["aciertos"].caption(
            "Aún no hay ventas en esta fase. Aquí se contarán las que aparezcan en el historial.")
    else:
        texto_ac = (
            f"💰 Ganado ${resumen['ganado']:.2f} · Perdido ${resumen['perdido']:.2f} · "
            f"**Neto ${resumen['neto']:+.2f}** | "
            f"Esperanza por operación: {resumen['esperanza']:+.2f}% "
            f"(acierto +{resumen['acierto_neto']:.2f}% · fallo -{resumen['fallo_neto']:.2f}%)"
        )
        if resumen["esperanza"] < 0:
            interfaz["aciertos"].warning(texto_ac)
        else:
            interfaz["aciertos"].success(texto_ac)
    senal_vista = st.session_state.get("ultima_senal_vista")
    if senal_vista:
        probabilidad = calcular_probabilidad(senal_vista.get('confianza_senal', 0))
        interfaz["ultima_senal"].info(
            f"📊 {senal_vista['sym']} → {senal_vista['accion']} | Prob: {probabilidad:.1f}% | "
            f"Razón: {senal_vista['razon']} | Tend.30d: {senal_vista.get('tendencia_30d', 'N/A')}"
        )
    texto_estado = (
        f"🔹 Indicadores: BTC={st.session_state.indicadores_activados.get('BTC')} | "
        f"ETH={st.session_state.indicadores_activados.get('ETH')} | "
        f"Modo: {'🔇 Solo señales' if st.session_state.modo_solo_senales else '✅ Automático'} | "
        f"Fase: {st.session_state.fase_actual}"
    )
    if st.session_state.get("operar_24_7", False):
        texto_estado += " | 🔥 24/7"
    if st.session_state.get("orden_pendiente_BTC"):
        texto_estado += " | ⏳ Orden BTC pendiente"
    if st.session_state.get("orden_pendiente_ETH"):
        texto_estado += " | ⏳ Orden ETH pendiente"
    interfaz["estado"].info(texto_estado)
    contenedor = interfaz["mensajes"].container()
    with contenedor:
        st.caption("🛠️ Últimos avisos del bot")
        if MENSAJES:
            for hora, nivel, texto in list(MENSAJES)[-8:]:
                icono = {"success": "✅", "warning": "⚠️", "error": "❌"}.get(nivel, "•")
                st.caption(f"{hora} {icono} {texto}")
        else:
            st.caption("Sin avisos.")
            # ══════════════════ PARTE 11/11: refresco y arranque ══════════════════

def _panel():
    interfaz = {
        "tabla": st.container(),
        "horario": st.empty(),
        "fase": st.empty(),
        "info": st.empty(),
        "metricas": st.empty(),
        "cartera": st.empty(),
        "posiciones": st.empty(),
        "historial": st.container(),
        "aciertos": st.container(),
        "ultima_senal": st.empty(),
        "estado": st.empty(),
        "mensajes": st.empty(),
    }
    try:
        ejecutar_ciclo(interfaz)
    except Exception as e:
        print(f"Error en el ciclo: {e}")
        interfaz["estado"].error(f"❌ Error en el ciclo: {e}")

st.sidebar.markdown("---")
st.sidebar.markdown("**⏱️ Intervalo de actualización**")
intervalo = st.sidebar.slider(
    "Actualizar cada (segundos)", min_value=5, max_value=60,
    value=int(st.session_state.intervalo_actualizacion), step=5)
st.session_state.intervalo_actualizacion = intervalo

st.sidebar.markdown("**🔄 Actualización**")
if st.sidebar.button("🔄 Actualizar datos ahora"):
    st.sidebar.success("✅ Datos actualizados")

st.sidebar.caption(f"El panel se refresca automáticamente cada {intervalo} s.")

def _soporta_fragmento_periodico():
    if not hasattr(st, "fragment"):
        return False
    try:
        st.fragment(run_every=timedelta(seconds=1))
        return True
    except Exception:
        return False

if _soporta_fragmento_periodico():
    _fragmento = st.fragment(run_every=timedelta(seconds=int(intervalo)))(_panel)
    _fragmento()
elif _refresco_automatico is not None:
    _refresco_automatico(interval=int(intervalo) * 1000, key="refresco_automatico")
    _panel()
else:
    st.warning(
        "⚠️ Tu versión de Streamlit no soporta `st.fragment(run_every=...)` y no está "
        "instalado `streamlit-autorefresh`: el panel solo se actualizará al interactuar. "
        "Actualiza Streamlit (`pip install -U streamlit`) o instala "
        "`pip install streamlit-autorefresh`."
    )
    _panel()
