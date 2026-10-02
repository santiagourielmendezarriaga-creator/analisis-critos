# -*- coding: utf-8 -*-
"""
🧠 Bot Scalping Extremo + Volumen + Tendencia 30d (Streamlit)
VERSIÓN CORREGIDA, EN ESPAÑOL, CON SALDO REAL DE BITSO Y VENTAS POR REGLAS

Cambios respecto al original (marcados con "# ⭐ FIX:"):

  1. Se eliminó el `while True: time.sleep(...)` final que bloqueaba Streamlit: la
     interfaz nunca se repintaba. El ciclo corre en un `st.fragment(run_every=...)`.
  2. `verificar_orden_pendiente()` devolvía el payload de Bitso en vez de la orden
     guardada, así que una compra Maker real nunca se contabilizaba.
  3. El tramo de probabilidad >= 100% pedía $100 con límite de $50 y nunca compraba.
  4. `st.stop()` dentro de "Vender TODO" abortaba el script y dejaba la orden real
     sin seguimiento.
  5. Las órdenes pendientes no se guardaban en Firebase.
  6. MODO_REAL y los montos leídos de secrets podían venir como texto ("false" es
     truthy).
  7. `obtener_volumen_onchain()` inventaba 0.5B si fallaba la API.
  8. `enviar_telegram()` fallaba en silencio con Markdown inválido.
  9. El reset diario de contadores ocurría DESPUÉS de mostrarlos.
 10. El token de Telegram estaba hardcodeado (expuesto). RÓTALO.
 11. Todo el código en español, con migración automática desde las claves viejas.
 12. El saldo REAL de Bitso se lee y se muestra. Leer el saldo ya NO exige MODO_REAL.
 13. El bot VENDE POR REGLAS: límite de pérdida, toma de ganancia y detención móvil
     opcional, con prioridad sobre la señal. La señal SELL ya no exige +2.5%.
 14. El límite de pérdida y la detención móvil salen A MERCADO (llenado inmediato),
     con respaldo automático en límite agresivo si Bitso rechaza el mercado.
 15. El límite de pérdida protege incluso con "solo señales" activado.
 16. ⭐ NUEVO: si Bitso RECHAZA una venta, esa venta entra en pausa (por defecto 15
     minutos) para no reintentar cada ciclo, y el aviso dice la cantidad exacta que
     se intentó vender, para diagnosticar el rechazo.

Configuración esperada (Streamlit secrets o variables de entorno):
    BITSO_API_KEY, BITSO_API_SECRET, MODO_REAL,
    MONTO_MAXIMO_POR_OPERACION, MONTO_MAXIMO_DIARIO,
    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
"""

# ══════════════════ BLOQUE 1/10: importaciones y configuración global ══════════════════

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

try:  # ⭐ FIX: refresco por temporizador opcional si no hay st.fragment(run_every)
    from streamlit_autorefresh import st_autorefresh as _refresco_automatico
except Exception:
    _refresco_automatico = None

COMISION = 0.006                       # 0.60% por operación
VOLUMEN_MINIMO_24H = 0.5               # miles de millones de USD
# ⭐ FIX: la señal SELL ya no exige +2.5%. 0.0 = puede cerrar en cuanto esté a la par
# o en ganancia. Las pérdidas las corta el límite de pérdida, no la señal.
GANANCIA_MINIMA_VENTA_PCT = 0.0
# ⭐ NUEVO: True  = vende justo al alcanzar la toma de ganancia (simple y predecible)
#            False = deja correr la ganancia y sale con la detención móvil
TOMA_GANANCIA_FIJA = True
# ⭐ NUEVO: cómo se ejecutan las salidas
SALIDA_A_MERCADO = True      # el límite de pérdida y la detención móvil salen a mercado
MARGEN_AGRESIVO_PCT = 0.5    # si el mercado es rechazado: límite 0.5% por DEBAJO del mercado
# ⭐ NUEVO: el límite de pérdida protege incluso con "solo señales" activado.
# Si no, al desactivar la ejecución te quedas sin red de seguridad.
SALIDAS_IGNORAN_SOLO_SENALES = True
# ⭐ NUEVO: minutos de pausa tras un rechazo de Bitso, para no reintentar cada ciclo
ESPERA_TRAS_FALLO_MIN = 15
MENSAJES = deque(maxlen=30)            # avisos del ciclo (antes iban a la barra lateral)

def avisar(mensaje, nivel="info"):
    """Registra un aviso del ciclo. Se muestra en el panel principal."""
    try:
        MENSAJES.append((datetime.now().strftime("%H:%M:%S"), nivel, mensaje))
    except Exception:
        pass
    print(f"[{nivel}] {mensaje}")

def _secreto(nombre, predeterminado=None):
    """Lee un secreto de st.secrets y, si no existe, del entorno."""
    try:
        if nombre in st.secrets:
            return st.secrets[nombre]
    except Exception:
        pass
    valor = os.environ.get(nombre)
    return predeterminado if valor is None else valor

def _a_booleano(valor, predeterminado=False):
    """⭐ FIX: 'false' (texto) era truthy y podía activar MODO_REAL sin querer."""
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
    """⭐ FIX: migración; acepta las claves nuevas (español) y las viejas (inglés)."""
    if clave_nueva in datos:
        return datos[clave_nueva]
    if clave_vieja in datos:
        return datos[clave_vieja]
    return predeterminado
    # ══════════════════ BLOQUE 2/10: persistencia en Firebase ══════════════════

URL_FIREBASE = "https://bot-cc6c4-default-rtdb.firebaseio.com"

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
            # ⭐ FIX: las órdenes pendientes deben sobrevivir a un reinicio
            "orden_pendiente_BTC": st.session_state.get("orden_pendiente_BTC"),
            "orden_pendiente_ETH": st.session_state.get("orden_pendiente_ETH"),
            # ⭐ FIX: contadores de respaldos automáticos (antes vivían solo en memoria)
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
    st.session_state.limite_perdida = 1.5
    st.session_state.toma_ganancia = 2.5
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
    st.session_state.ultimo_respaldo_auto = time.time()          # ⭐ FIX: faltaba
    st.session_state.ultimo_respaldo_operaciones = 0             # ⭐ FIX: faltaba
# ══════════════════ BLOQUE 3/10: restaurar estado y respaldos ══════════════════

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
        st.session_state.limite_perdida = _leer(datos, "limite_perdida", "stop_loss", 1.5)
        st.session_state.toma_ganancia = max(0.5, _a_decimal(
            _leer(datos, "toma_ganancia", "take_profit", 2.5), 2.5))
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
        # ⭐ FIX: restaurar órdenes pendientes (antes se forzaban a None)
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
        # ══════════════════ BLOQUE 4/10: Telegram, Bitso y saldo real ══════════════════

# ⚠️ SEGURIDAD: el token original quedó expuesto en el código fuente. RÓTALO en
# BotFather y colócalo en Secrets. Este respaldo solo evita romper la app mientras
# no esté configurado.
_TOKEN_SEGURO = _secreto("TELEGRAM_TOKEN", "") or os.environ.get("TELEGRAM_TOKEN", "")
_CHAT_SEGURO = _secreto("TELEGRAM_CHAT_ID", "")
_TOKEN_RESPALDO = "8532857017:AAHwLhRnM3oC6TbgFFKAEmQnZVoo6JD_esQ"
_CHAT_RESPALDO = "5835990242"

TOKEN_TELEGRAM = _TOKEN_SEGURO or _TOKEN_RESPALDO
CHAT_ID_TELEGRAM = str(_CHAT_SEGURO or _CHAT_RESPALDO)
USANDO_TOKEN_RESPALDO = not _TOKEN_SEGURO

def enviar_telegram(mensaje):
    """Envía a Telegram. ⭐ FIX: reintenta sin Markdown si el parseo falla."""
    try:
        url = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendMessage"
        cuerpo = {"chat_id": CHAT_ID_TELEGRAM, "text": mensaje}
        respuesta = requests.post(url, json={**cuerpo, "parse_mode": "Markdown"}, timeout=5)
        if respuesta.status_code != 200:
            requests.post(url, json=cuerpo, timeout=5)
        return True
    except Exception:
        return False

# ===== CONFIGURACIÓN DE BITSO =====
URL_BASE_BITSO = "https://api.bitso.com"

# ⭐ FIX: parseo explícito; antes `bool("false")` activaba el modo real
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
    firma = hmac.new(
        SECRETO_API_BITSO.encode('utf-8'),
        mensaje.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    cabecera = f"Bitso {LLAVE_API_BITSO}:{nonce}:{firma}"
    return cabecera, nonce

def obtener_saldo_bitso(usar_cache=True):
    """
    Lee el saldo REAL de la cuenta de Bitso.
    ⭐ FIX: ya NO exige MODO_REAL. Solo necesita las llaves cargadas, así puedes ver tu
    saldo sin activar el trading real. MODO_REAL solo controla el envío de órdenes.
    """
    if not LLAVE_API_BITSO or not SECRETO_API_BITSO:
        st.session_state["error_saldo_bitso"] = "Faltan BITSO_API_KEY / BITSO_API_SECRET en Secrets."
        return None

    ahora = time.time()
    cache = st.session_state.get("cache_saldo_bitso") or {}
    if usar_cache and cache.get("valor") is not None and (ahora - cache.get("timestamp", 0)) < 30:
        return cache["valor"]

    try:
        ruta = "/v3/balance/"
        cabecera, _ = _crear_cabecera_autenticacion("GET", ruta)
        if not cabecera:
            st.session_state["error_saldo_bitso"] = "No se pudo firmar la petición (llaves vacías)."
            return None

        cabeceras = {"Authorization": cabecera}
        respuesta = requests.get(URL_BASE_BITSO + ruta, headers=cabeceras, timeout=10)

        if respuesta.status_code != 200:
            st.session_state["error_saldo_bitso"] = (
                f"Bitso respondió HTTP {respuesta.status_code}: {respuesta.text[:200]}")
            return None

        datos = respuesta.json()
        if not (isinstance(datos, dict) and datos.get("success")):
            st.session_state["error_saldo_bitso"] = f"Bitso respondió sin success: {str(datos)[:200]}"
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
        st.session_state["error_saldo_bitso"] = f"Excepción consultando el saldo: {e}"
        print(f"Error consultando saldo: {e}")
        return None
    # ══════════════════ BLOQUE 5/10: órdenes de Bitso ══════════════════

def colocar_orden_bitso(libro, lado, cantidad_mayor, precio, tipo="limit"):
    """
    Coloca una orden en Bitso.
      tipo="limit"  → orden Maker con precio (la de siempre, mejor precio)
      tipo="market" → orden a mercado, sin precio (llenado inmediato)
    Las salidas de pánico (límite de pérdida y detención móvil) usan mercado.
    """
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
        cabeceras = {
            "Authorization": cabecera,
            "Content-Type": "application/json"
        }
        url = URL_BASE_BITSO + ruta
        respuesta = requests.post(url, data=cuerpo_json, headers=cabeceras, timeout=15)
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
    """Consulta el estado de una orden por su ID. VERSIÓN ROBUSTA."""
    if not MODO_REAL:
        return None
    try:
        ruta = f"/v3/orders/{oid}/"
        cabecera, _ = _crear_cabecera_autenticacion("GET", ruta)
        if not cabecera:
            return None
        cabeceras = {"Authorization": cabecera}
        url = URL_BASE_BITSO + ruta
        respuesta = requests.get(url, headers=cabeceras, timeout=10)
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
        cabeceras = {"Authorization": cabecera}
        url = URL_BASE_BITSO + ruta
        respuesta = requests.delete(url, headers=cabeceras, timeout=10)
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
    """
    Verifica si hay una orden pendiente para `simbolo`.

    ⭐ FIX: devuelve SIEMPRE la orden almacenada (con monto/precio/cantidad/lado) y no
    el payload de Bitso. Antes ponía la clave en None y devolvía el payload, así que el
    código de ejecución leía monto=0 y descartaba la operación en silencio.

    ⭐ FIX 2: el vencimiento de 10 minutos se evalúa SIN depender del estado que
    devuelva Bitso. Antes, si la API no daba un estado legible (orden ya cancelada allá,
    404 o error), la clave quedaba bloqueada para siempre y el bot no volvía a vender
    ese símbolo nunca más.
    """
    clave_orden = f"orden_pendiente_{simbolo}"
    orden = st.session_state.get(clave_orden)

    if not isinstance(orden, dict):
        st.session_state[clave_orden] = None
        return "sin_orden", None

    oid = orden.get("oid")
    if not oid:
        st.session_state[clave_orden] = None
        return "sin_orden", None

    # ⭐ FIX 2: el vencimiento se calcula ANTES de consultar el estado
    creada = float(orden.get("timestamp", time.time()) or time.time())
    vencida = (time.time() - creada) > 600

    if not MODO_REAL:
        # Sin API real no hay órdenes en el exchange: se resuelve de inmediato.
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
        # ⭐ FIX 2: vencida o sin estado legible → se intenta cancelar y SIEMPRE se libera
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
    # ══════════════════ BLOQUE 6/10: análisis y aprendizaje ══════════════════

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
            f"Toma de ganancia aumentada a {st.session_state.toma_ganancia:.3f}% (ganancia ${ganancia_promedio:.2f})")
    elif ganancia_promedio < 0:
        st.session_state.toma_ganancia = max(0.5, st.session_state.toma_ganancia * 0.9)
        st.session_state.limite_perdida = max(0.5, st.session_state.limite_perdida * 0.9)
        analisis["ajustes_aplicados"].append(
            f"Toma de ganancia y límite de pérdida reducidos (ganancia ${ganancia_promedio:.2f})")
    else:
        analisis["ajustes_aplicados"].append("Toma de ganancia y límite de pérdida sin cambios")
    return analisis
    # ══════════════════ BLOQUE 7/10: datos externos e indicadores ══════════════════

def obtener_tendencia_historica(simbolo="BTC", dias=30):
    try:
        identificador = "bitcoin" if simbolo == "BTC" else "ethereum"
        url = f"https://api.coingecko.com/api/v3/coins/{identificador}/market_chart?vs_currency=usd&days={dias}"
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
    """
    ⭐ FIX: antes devolvía un valor inventado de 0.5B si la API fallaba, y ese 0.5
    pasaba justo el filtro de volumen mínimo. Ahora devuelve None (= sin dato).
    """
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
    return valor_cache  # dato viejo (o None) en lugar de un número inventado

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
    # ⭐ FIX: con volumen None la comparación `None > 2.0` lanzaba TypeError
    peso_volumen = 0
    if volumen_onchain is not None:
        if volumen_onchain > 2.0:
            peso_volumen = 10
        elif volumen_onchain < VOLUMEN_MINIMO_24H:
            peso_volumen = -5
    peso_tendencia = 15 if tendencia_30d == "ALCISTA" else -15 if tendencia_30d == "BAJISTA" else 0
    if abs(cambio_30d) > 20:
        peso_tendencia *= 1.5
    peso_miedo = 10 if valor_miedo_codicia <= 20 else -10 if valor_miedo_codicia >= 80 else (50 - valor_miedo_codicia) * 0.2
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
   # ══════════════════ BLOQUE 8/10: interfaz, cartera, compra automática, salidas y contador ══════════════════

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
    "toma_ganancia": 2.0,
    "limite_perdida": 1.5,
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
}

for nombre, valor_predeterminado in variables_requeridas.items():
    if nombre not in st.session_state:
        st.session_state[nombre] = valor_predeterminado

st.session_state.toma_ganancia = max(0.5, _a_decimal(st.session_state.get("toma_ganancia", 2.0), 2.0))
st.session_state.confianza_umbral = min(95, max(50, _a_entero(st.session_state.get("confianza_umbral", 65), 65)))

if "datos_cargados" not in st.session_state:
    restaurar_desde_archivo()
    st.session_state.datos_cargados = True

st.title("🧠 Scalping Extremo + Volumen + Tendencia 30d")

if MODO_REAL:
    st.error("🔴 **MODO REAL ACTIVADO** — Órdenes Maker con dinero real")
else:
    st.info("🟢 **MODO SIMULACIÓN** — Sin dinero real")

if USANDO_TOKEN_RESPALDO:
    st.warning(
        "🔑 **Telegram usa el token hardcodeado del código original (expuesto).** "
        "Rótalo en BotFather y define `TELEGRAM_TOKEN` / `TELEGRAM_CHAT_ID` en Secrets."
    )

# ===== FUNCIONES DE REGISTRO CONTABLE (SIMULACIÓN) =====
def _aplicar_compra(simbolo, monto, precio, comision=COMISION):
    """Suma una compra al registro simulado. ⭐ precio de entrada = media ponderada."""
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
    # ⭐ NUEVO: una compra nueva limpia el freno de ventas rechazadas
    st.session_state[f"venta_fallida_{simbolo}"] = 0.0
    return cantidad

def _aplicar_venta(simbolo, precio, cantidad_forzada=None):
    """Cierra la posición en el registro simulado y devuelve (neto, ganancia)."""
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
    """
    Cierra la posición (real o simulada) dejando consistentes el registro, Telegram y
    el respaldo. Devuelve True si la venta se envió.

    salida_rapida=True  → límite de pérdida y detención móvil: sale a MERCADO para
                          garantizar el llenado (si Bitso lo rechaza, usa un límite
                          agresivo por debajo del mercado).
    salida_rapida=False → toma de ganancia y señal: orden Maker por encima del mercado.
    forzar=True         → vende aunque esté en pérdida (venta manual).
    """
    # Nunca duplicar una venta que ya está en camino al exchange
    if st.session_state.get(f"orden_pendiente_{simbolo}"):
        avisar(f"⏳ Ya hay una orden pendiente para {simbolo}: no se duplica la venta", "info")
        return False

    # ⭐ NUEVO: freno tras un rechazo de Bitso, para no martillar cada 5 segundos
    ultimo_fallo = float(st.session_state.get(f"venta_fallida_{simbolo}", 0.0) or 0.0)
    if ultimo_fallo and (time.time() - ultimo_fallo) < ESPERA_TRAS_FALLO_MIN * 60:
        return False

    cantidad = float(st.session_state.posiciones.get(simbolo, 0.0))
    if cantidad <= 0:
        return False

    entrada = float(st.session_state.precio_entrada.get(simbolo, 0.0))

    # La señal de venta solo cierra si no se está en pérdida. Quien corta las pérdidas
    # es el límite de pérdida de _revisar_salidas().
    if not forzar and entrada > 0 and precio < entrada * (1 + minima_ganancia_pct / 100.0):
        ganancia_potencial = ((precio / entrada) - 1) * 100
        avisar(f"⏸️ {simbolo}: venta por {motivo} frenada; está en {ganancia_potencial:+.2f}% "
               f"(mínimo {minima_ganancia_pct:.2f}%). Esperando al límite de pérdida.", "warning")
        return False

    libro = "btc_mxn" if simbolo == "BTC" else "eth_mxn"
    # Evita recomprar el mismo símbolo en el mismo ciclo tras una salida
    st.session_state[f"ultima_compra_{simbolo}"] = st.session_state.ciclo

    etiqueta_salida = "mercado" if (salida_rapida and SALIDA_A_MERCADO) else "maker"
    motivo_completo = f"{motivo} [{etiqueta_salida}]"

    if MODO_REAL:
        if salida_rapida and SALIDA_A_MERCADO:
            # 1) intento a mercado: llenado inmediato
            orden = colocar_orden_bitso(libro, "sell", f"{cantidad:.8f}", "0", tipo="market")
            precio_envio = precio
            if not orden or orden.get("error"):
                # 2) respaldo: límite AGRESIVO por debajo del mercado (cruza el libro)
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
            # ⭐ NUEVO: el aviso dice EXACTAMENTE qué se intentó vender
            avisar(f"❌ Venta {simbolo} falló: intenté vender {cantidad:.8f} {simbolo} "
                   f"a ${precio_envio:,.2f} | Bitso: {detalle} | "
                   f"En pausa {ESPERA_TRAS_FALLO_MIN} min.", "error")
            enviar_telegram(f"❌ **VENTA {simbolo} RECHAZADA POR BITSO**\n"
                            f"Intenté vender {cantidad:.8f} {simbolo} a ${precio_envio:,.2f}\n"
                            f"Bitso: {detalle}\n"
                            f"Motivo del bot: {motivo_completo}")
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

    # --- simulación ---
    # a mercado se asume el precio actual (sin la bonificación del Maker)
    precio_sim = precio if etiqueta_salida == "mercado" else precio * 1.002
    neto, ganancia = _aplicar_venta(simbolo, precio_sim)
    porcentaje = ((precio_sim / entrada) - 1) * 100 if entrada else 0.0
    signo = "+" if ganancia > 0 else ""
    resultado = "GANANCIA" if ganancia > 0 else "PÉRDIDA"
    # el texto "PROFIT:" se mantiene porque el aprendizaje y el contador lo leen
    msg = (f"🔴 VENTA [MAKER-SIM] {simbolo} | {motivo_completo} | Neto: ${neto:.2f} | "
           f"PROFIT: {signo}${ganancia:.2f} ({signo}{porcentaje:.2f}%) ({resultado})")
    enviar_telegram(msg)
    st.session_state.operaciones.append((datetime.now(), msg))
    guardar_datos()
    avisar(f"✅ Venta {simbolo} ({motivo_completo}): {signo}${ganancia:.2f}", "success")
    return True

def _revisar_salidas(simbolo, precio):
    """
    Salidas de riesgo, en orden de prioridad:
      1. Límite de pérdida  → salida A MERCADO (garantiza el corte)
      2. Toma de ganancia   → salida Maker (cobra mejor precio), o detención móvil
                              (a mercado) si TOMA_GANANCIA_FIJA = False
    No dependen del horario ni de la fase: si hay que salir, se sale.
    """
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

    # Con "solo señales" se respeta el modo... salvo el límite de pérdida, que
    # siempre protege el capital.
    if st.session_state.modo_solo_senales and not (
            SALIDAS_IGNORAN_SOLO_SENALES and precio <= umbral_perdida):
        # No ejecuta nada, pero avisa por Telegram para que decidas tú
        hay_aviso = precio <= umbral_perdida or precio >= umbral_ganancia
        clave_aviso = f"aviso_salida_{simbolo}"
        if hay_aviso and not st.session_state.get(clave_aviso):
            st.session_state[clave_aviso] = True
            enviar_telegram(
                f"🔇 **AVISO DE SALIDA {simbolo}**\n"
                f"Precio ${precio:,.0f} vs entrada ${entrada:,.0f} "
                f"({((precio/entrada)-1)*100:+.2f}%)\n"
                f"Modo 'solo señales' activo: el bot NO ejecutó la venta.")
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
        return _cerrar_posicion(
            simbolo, precio,
            f"detención móvil {st.session_state.seguimiento}% desde ${maximo:,.0f}",
            salida_rapida=True)

    return False

def _resumen_aciertos():
    """
    Cuenta aciertos y fallos de la FASE ACTUAL leyendo el historial, y calcula el
    punto de equilibrio según tu TP, tu SL y las comisiones.
    """
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
        # solo la fase actual
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

        # el porcentaje solo viene en las ventas simuladas: es opcional
        porcentaje = re.search(r"PROFIT:[^(]*\(([+-]?[\d.]+)%\)", msg)
        if porcentaje:
            try:
                porcentajes.append(float(porcentaje.group(1)))
            except (TypeError, ValueError):
                pass

    cerradas = aciertos + fallos
    tasa = (aciertos / cerradas * 100) if cerradas else 0.0

    # Punto de equilibrio: cuántos aciertos necesitas para no perder
    comision_ida_vuelta = COMISION * 100 * 2          # 1.2% con COMISION = 0.006
    acierto_neto = st.session_state.toma_ganancia - comision_ida_vuelta
    fallo_neto = st.session_state.limite_perdida + comision_ida_vuelta
    equilibrio = (fallo_neto / (acierto_neto + fallo_neto) * 100
                  if (acierto_neto + fallo_neto) > 0 else 100.0)

    esperanza = 0.0
    if cerradas:
        esperanza = (tasa / 100) * acierto_neto - (1 - tasa / 100) * fallo_neto

    return {
        "aciertos": aciertos,
        "fallos": fallos,
        "cerradas": cerradas,
        "tasa": tasa,
        "ganado": ganado,
        "perdido": perdido,
        "neto": ganado - perdido,
        "ganancia_media_pct": (sum(porcentajes) / len(porcentajes)) if porcentajes else 0.0,
        "equilibrio": equilibrio,
        "esperanza": esperanza,
        "acierto_neto": acierto_neto,
        "fallo_neto": fallo_neto,
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

    # ⭐ FIX: el tramo >=100% pedía $100 con límite de $50 y nunca compraba.
    monto = min(monto_base, MONTO_MAXIMO_POR_OPERACION)
    monto_hoy = float(st.session_state.get("monto_del_dia", 0.0))
    restante_dia = MONTO_MAXIMO_DIARIO - monto_hoy
    if monto <= 0 or restante_dia < monto:
        avisar(f"⚠️ Límite diario alcanzado (${monto_hoy:.2f}/${MONTO_MAXIMO_DIARIO:.2f})", "warning")
        return
    cantidad_ops = int(min(cantidad_ops, restante_dia // monto))
    if cantidad_ops < 1:
        avisar("⚠️ Remanente diario insuficiente para una operación", "warning")
        return

    if st.session_state.posiciones.get(simbolo, 0) > 0:
        return

    precio_maker = precio * 0.998

    if MODO_REAL:
        saldo_real = obtener_saldo_bitso(usar_cache=False)
        if saldo_real:
            mxn_disponible = saldo_real.get("mxn", {}).get("available", 0)
            if mxn_disponible < monto * cantidad_ops:
                avisar(f"⚠️ Saldo insuficiente: ${mxn_disponible:.2f}", "warning")
                return
        libro = "btc_mxn" if simbolo == "BTC" else "eth_mxn"
        cantidad = (monto * 0.999) / precio_maker
        orden = colocar_orden_bitso(libro, "buy", f"{cantidad:.8f}", f"{precio_maker:.2f}")
        if not orden or orden.get("error"):
            avisar(f"❌ Orden Maker {simbolo} falló: "
                   f"{orden.get('error') if orden else 'sin respuesta'}", "error")
            return
        st.session_state[clave_orden] = {
            "oid": orden.get("oid"),
            "side": "buy",
            "sym": simbolo,
            "price": precio_maker,
            "qty": cantidad,
            "monto": monto,
            "cant": cantidad_ops,
            "timestamp": time.time(),
            "confianza": confianza
        }
        st.session_state[clave_compra] = st.session_state.ciclo
        avisar(f"⏳ Orden Maker {simbolo} colocada (oid {orden.get('oid')})", "info")
        enviar_telegram(f"⏳ ORDEN MAKER {simbolo} | Precio: ${precio_maker:,.2f}")
        guardar_datos()  # ⭐ FIX: persistir la orden pendiente
        return

    ejecutadas = 0
    for _ in range(cantidad_ops):
        if st.session_state.saldo >= monto:
            _aplicar_compra(simbolo, monto, precio_maker)
            ejecutadas += 1
    if ejecutadas > 0:
        st.session_state[clave_compra] = st.session_state.ciclo
        guardar_datos()
        msg = (f"🟢 COMPRA [MAKER-SIM] {simbolo} | {ejecutadas}x${monto:.0f} | "
               f"Prob: {probabilidad:.1f}% | Razon: {razon}")
        enviar_telegram(msg)
        st.session_state.operaciones.append((datetime.now(), msg))
        avisar(f"✅ {ejecutadas} compra(s) Maker simulada(s) en {simbolo}", "success")
    else:
        avisar(f"⚠️ Saldo insuficiente para comprar {simbolo}", "warning")

# ===== BARRA LATERAL =====
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

# ══════════════════ BLOQUE 9/10: botones, cartera real, control manual y registro ══════════════════

if st.sidebar.button("Reiniciar simulación"):
    with st.spinner("💾 Creando respaldo..."):
        clave_respaldo, msg = crear_respaldo()
        if clave_respaldo:
            st.sidebar.success("✅ Respaldo: " + str(clave_respaldo[:25]))
            limpiar_respaldos_viejos(maximo_respaldos=10)
        else:
            st.sidebar.warning("⚠️ Sin respaldo: " + str(msg))
    iniciar_estado_nuevo()
    guardar_datos()
    st.rerun()

if st.sidebar.button("📢 Prueba de Telegram"):
    if enviar_telegram("🧠 Bot activo"):
        st.success("Enviado")
    else:
        st.error("No se pudo enviar")

if st.sidebar.button("💾 Guardar datos ahora"):
    exito, mensaje = guardar_datos()
    if exito:
        st.sidebar.success("✅ Datos guardados")
    else:
        st.sidebar.error("❌ Error: " + str(mensaje))

# ===== LIBERAR ÓRDENES PENDIENTES ATASCADAS =====
st.sidebar.markdown("---")
st.sidebar.markdown("**🧹 Órdenes pendientes**")

if st.sidebar.button("🧹 Liberar órdenes pendientes"):
    for simbolo_limpiar in ["BTC", "ETH"]:
        orden_pend = st.session_state.get(f"orden_pendiente_{simbolo_limpiar}")
        if not isinstance(orden_pend, dict):
            st.session_state[f"orden_pendiente_{simbolo_limpiar}"] = None
            continue
        oid_pend = orden_pend.get("oid")
        cancelada = False
        if oid_pend:
            try:
                cancelada = cancelar_orden_bitso(oid_pend)
            except Exception:
                cancelada = False
        st.session_state[f"orden_pendiente_{simbolo_limpiar}"] = None
        st.session_state[f"venta_fallida_{simbolo_limpiar}"] = 0.0
        st.sidebar.write(
            f"**{simbolo_limpiar}**: "
            + ("cancelada en Bitso ✅" if cancelada
               else "liberada localmente (no se pudo cancelar en Bitso — revísala en la app)")
        )
    guardar_datos()
    st.sidebar.success("✅ Órdenes pendientes liberadas")
    st.rerun()

# ===== OLVIDAR BTC (NO VENDERLO) =====
st.sidebar.markdown("**🗑️ Quitar BTC del bot**")

if st.sidebar.button("🗑️ Olvidar BTC (dejar de venderlo)"):
    st.session_state.posiciones["BTC"] = 0.0
    st.session_state.precio_entrada["BTC"] = 0.0
    st.session_state.precio_maximo["BTC"] = 0.0
    st.session_state["venta_fallida_BTC"] = 0.0
    st.session_state["orden_pendiente_BTC"] = None
    guardar_datos()
    st.sidebar.success("✅ BTC olvidado. El bot ya no intentará venderlo. Sigue en tu Bitso.")
    st.rerun()

# ===== REGISTRAR UNA VENTA MANUAL EN EL CONTADOR =====
st.sidebar.markdown("---")
with st.sidebar.expander("📝 Registrar venta manual"):
    st.caption("Úsalo solo para ventas que hiciste TÚ desde la app de Bitso. "
               "No mueve dinero: solo anota la operación para que el contador la cuente.")
    simbolo_manual = st.selectbox("Moneda", ["ETH", "BTC"], key="manual_simbolo")
    neto_manual = st.number_input("Monto neto recibido (MXN)", min_value=0.0, value=0.0,
                                  step=1.0, key="manual_neto")
    ganancia_manual = st.number_input("Ganancia o pérdida (MXN)", value=0.0, step=1.0,
                                      key="manual_ganancia",
                                      help="Positivo si ganaste, negativo si perdiste.")
    porcentaje_manual = st.number_input("Porcentaje (opcional, %)", value=0.0, step=0.1,
                                        key="manual_porcentaje")
    if st.button("📝 Registrar venta manual", key="manual_boton"):
        signo_m = "+" if ganancia_manual > 0 else ""
        resultado_m = "GANANCIA" if ganancia_manual > 0 else "PÉRDIDA"
        msg_m = (f"🔴 VENTA [MANUAL-REGISTRADA] {simbolo_manual} | registrada a mano | "
                 f"Neto: ${neto_manual:.2f} | PROFIT: {signo_m}${ganancia_manual:.2f} "
                 f"({signo_m}{porcentaje_manual:.2f}%) ({resultado_m})")
        st.session_state.operaciones.append((datetime.now(), msg_m))
        guardar_datos()
        st.success(f"✅ Venta de {simbolo_manual} registrada en el contador")
        st.rerun()

# ===== CARTERA REAL DE BITSO =====
st.sidebar.markdown("---")
st.sidebar.markdown("**💰 Cartera real de Bitso**")

if st.sidebar.button("🔍 Ver saldo real de Bitso"):
    saldos = obtener_saldo_bitso(usar_cache=False)
    if saldos is None:
        st.sidebar.error("❌ No se pudo leer el saldo.")
        st.sidebar.write("**Detalle:** " + str(st.session_state.get("error_saldo_bitso")))
        st.sidebar.write("**Llave API:** " + ("cargada ✅" if LLAVE_API_BITSO else "faltante ❌"))
        st.sidebar.write("**Secreto API:** " + ("cargado ✅" if SECRETO_API_BITSO else "faltante ❌"))
        st.sidebar.write("**MODO_REAL:** " + str(MODO_REAL) + " (no hace falta para leer saldo)")
    else:
        hay_algo = False
        for codigo, valores in sorted(saldos.items()):
            if valores["available"] > 0 or valores["total"] > 0:
                st.sidebar.write(
                    f"**{codigo.upper()}**: disponible {valores['available']:.8f} | "
                    f"total {valores['total']:.8f}")
                hay_algo = True
        if not hay_algo:
            st.sidebar.warning("La API respondió, pero todas las monedas están en cero.")

if st.sidebar.button("🔄 Sincronizar cartera con Bitso"):
    saldos = obtener_saldo_bitso(usar_cache=False)
    if not saldos:
        st.sidebar.error("❌ No se pudo leer el saldo real.")
    else:
        mxn = float(saldos.get("mxn", {}).get("available", 0.0))
        cantidad_btc = float(saldos.get("btc", {}).get("available", 0.0))
        cantidad_eth = float(saldos.get("eth", {}).get("available", 0.0))
        precio_btc = obtener_precio_bitso("btc_mxn") or 0.0
        precio_eth = obtener_precio_bitso("eth_mxn") or 0.0

        st.session_state.saldo = mxn
        st.session_state.posiciones["BTC"] = cantidad_btc
        st.session_state.posiciones["ETH"] = cantidad_eth

        # ⭐ Conserva el precio de entrada si ya existe, así no pisa tu TP/SL actuales.
        for simbolo_sync, cantidad_sync, precio_sync in [
            ("BTC", cantidad_btc, precio_btc), ("ETH", cantidad_eth, precio_eth)
        ]:
            if cantidad_sync <= 0:
                st.session_state.precio_entrada[simbolo_sync] = 0.0
                st.session_state.precio_maximo[simbolo_sync] = 0.0
            elif float(st.session_state.precio_entrada.get(simbolo_sync, 0.0) or 0.0) <= 0:
                st.session_state.precio_entrada[simbolo_sync] = precio_sync
                st.session_state.precio_maximo[simbolo_sync] = precio_sync

        # ⭐ Limpia el freno de ventas rechazadas al resincronizar
        st.session_state["venta_fallida_BTC"] = 0.0
        st.session_state["venta_fallida_ETH"] = 0.0

        guardar_datos()
        st.sidebar.success(
            f"✅ Sincronizado: ${mxn:,.2f} MXN | {cantidad_btc:.6f} BTC | {cantidad_eth:.6f} ETH")
        st.rerun()

# ===== GESTIÓN DE RESPALDOS =====
st.sidebar.markdown("---")
with st.sidebar.expander("💾 Gestionar respaldos"):
    st.markdown("**Respaldos disponibles:**")
    respaldos = listar_respaldos()
    if not respaldos:
        st.info("No hay respaldos guardados")
    else:
        st.write("Total: " + str(len(respaldos)) + " respaldos")
        respaldo_seleccionado = st.selectbox(
            "Selecciona un respaldo:",
            options=respaldos,
            format_func=lambda x: x.replace("backup_", "").replace("_", " ")
        )
        columna1, columna2 = st.columns(2)
        with columna1:
            if st.button("📥 Restaurar", key="boton_restaurar"):
                if restaurar_respaldo(respaldo_seleccionado):
                    st.success("✅ Restaurado")
                    st.rerun()
                else:
                    st.error("❌ Error")
        with columna2:
            if st.button("🗑️ Eliminar", key="boton_eliminar"):
                try:
                    url_borrar = URL_FIREBASE + "/backups/" + respaldo_seleccionado + ".json"
                    respuesta = requests.delete(url_borrar, timeout=10)
                    if respuesta.status_code == 200:
                        st.success("🗑️ Eliminado")
                        st.rerun()
                    else:
                        st.error("❌ Error")
                except Exception as e:
                    st.error("❌ " + str(e))
        if st.button("💾 Crear respaldo manual", key="boton_respaldo_manual"):
            with st.spinner("Creando respaldo..."):
                clave, msg = crear_respaldo()
                if clave:
                    st.success("✅ " + str(clave))
                    st.rerun()
                else:
                    st.error("❌ " + str(msg))

# ===== CONTROL MANUAL - VENTA =====
st.sidebar.markdown("---")
st.sidebar.markdown("**🎮 Control manual**")

if st.sidebar.button("💸 Vender TODO"):
    try:
        precio_btc = obtener_precio_bitso("btc_mxn")
        precio_eth = obtener_precio_bitso("eth_mxn")
        precios = {"BTC": precio_btc, "ETH": precio_eth}
        vendido = False
        for simbolo in ["BTC", "ETH"]:
            cantidad = float(st.session_state.posiciones.get(simbolo, 0))
            precio = precios.get(simbolo)
            if cantidad <= 0:
                continue
            if not precio:
                st.sidebar.error(f"❌ Sin precio para {simbolo}")
                continue
            # Venta manual = salida A MERCADO y sin condición de ganancia.
            # _cerrar_posicion ya guarda los datos y evita duplicar órdenes pendientes.
            if _cerrar_posicion(simbolo, precio, "venta manual (Vender TODO)",
                                salida_rapida=True, forzar=True):
                vendido = True
        if vendido:
            st.sidebar.success("✅ Venta(s) procesada(s)")
            st.rerun()
        else:
            st.sidebar.info("No hay posiciones abiertas (o ya había órdenes pendientes)")
    except Exception as e:
        st.sidebar.error("❌ " + str(e))

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

        monto = min(50.0, MONTO_MAXIMO_POR_OPERACION)   # respeta el límite
        precio_objetivo = precio * 0.998
        cantidad = (monto * 0.999) / precio_objetivo

        st.write("**Monto:** $" + str(monto))
        st.write("**Precio objetivo:** $" + str(round(precio_objetivo, 2)))
        st.write("**Cantidad:** " + str(round(cantidad, 8)) + " " + simbolo)

        with st.spinner("Enviando orden a Bitso..."):
            orden = colocar_orden_bitso(libro, "buy", str(round(cantidad, 8)), str(round(precio_objetivo, 2)))

        if orden and not orden.get("error"):
            st.success("✅ Orden colocada: " + str(orden.get("oid")))
            st.json(orden)
            st.session_state[f"orden_pendiente_{simbolo}"] = {
                "oid": orden.get("oid"),
                "side": "buy",
                "sym": simbolo,
                "price": precio_objetivo,
                "qty": cantidad,
                "monto": monto,
                "cant": 1,
                "timestamp": time.time(),
                "confianza": 0,
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

def enviar_senal_telegram(simbolo, tipo, precio, razon, confianza, volumen_onchain,
                          cambio_30d, tendencia_30d):
    try:
        probabilidad = calcular_probabilidad(confianza)
        texto_volumen = f"{volumen_onchain:.2f}B USD" if volumen_onchain is not None else "N/A"
        msg = (f"📢 **SEÑAL {tipo} - {simbolo}**\n"
               f"🎯 Probabilidad: {probabilidad:.1f}%\n"
               f"Precio: ${precio:,.0f}\n"
               f"Razón: {razon}\n"
               f"Volumen: {texto_volumen}\n"
               f"Cambio 30d: {cambio_30d:+.2f}%\n"
               f"Tendencia 30d: {tendencia_30d}")
        enviar_telegram(msg)
        return True
    except Exception:
        return False
# ══════════════════ BLOQUE 10/10: ciclo, panel, contador y refresco automático ══════════════════

def _reconciliar_cartera():
    """
    ⭐ NUEVO: coteja el registro interno con el saldo real de Bitso. Si el bot cree que
    tiene una posición pero Bitso ya no la tiene (porque la vendió y perdió el registro
    de su propia venta), cierra esa posición en el registro para que no queden ventas
    fantasma ni errores de saldo insuficiente, y la anota en el historial para que el
    contador de aciertos la cuente.
    """
    if not MODO_REAL:
        return
    saldos = obtener_saldo_bitso()          # usa la caché de 30 s
    if not saldos:
        return

    for simbolo in ["BTC", "ETH"]:
        cantidad_registro = float(st.session_state.posiciones.get(simbolo, 0.0))
        if cantidad_registro <= 0:
            continue
        # si todavía hay una orden en vuelo, no tocar nada
        if st.session_state.get(f"orden_pendiente_{simbolo}"):
            continue

        cantidad_real = float(saldos.get(simbolo.lower(), {}).get("available", 0.0))
        # solo si desapareció casi todo (venta clara, no redondeo)
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
        avisar(f"🔁 Reconcilié {simbolo}: ya no hay saldo en Bitso. "
               f"Cierre estimado {signo}${ganancia:.2f}", "warning")
        enviar_telegram(msg)
        guardar_datos()

def _ejecutar_ordenes_pendientes():
    """Resuelve las órdenes Maker pendientes y las aplica al registro contable."""
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
                else:  # lado == "sell"
                    cantidad = _a_decimal(datos.get("qty"), 0.0)
                    if cantidad > 0:
                        neto, ganancia = _aplicar_venta(simbolo, precio_ejecucion, cantidad_forzada=cantidad)
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
                enviar_telegram(f"⚠️ Orden Maker {simbolo} cancelada por tiempo agotado. Reintentando.")
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

    # ⭐ FIX: el reinicio diario debe ocurrir ANTES de mostrar los contadores
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

    # ⭐ FIX: antes el primer cálculo de la tendencia 30d podía tardar 60 ciclos
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

    # ===== ÓRDENES MAKER PENDIENTES =====
    _ejecutar_ordenes_pendientes()

    # ⭐ NUEVO: cada 12 ciclos (~1 min) coteja el registro interno con Bitso
    if st.session_state.ciclo % 12 == 0:
        _reconciliar_cartera()

    # ===== SALIDAS POR REGLAS: LÍMITE DE PÉRDIDA, TOMA DE GANANCIA Y DETENCIÓN MÓVIL =====
    for simbolo_salida, precio_salida in [("BTC", btc), ("ETH", eth)]:
        if st.session_state.posiciones.get(simbolo_salida, 0) > 0:
            # la detención móvil necesita saber el máximo alcanzado
            st.session_state.precio_maximo[simbolo_salida] = max(
                float(st.session_state.precio_maximo.get(simbolo_salida, 0.0) or 0.0),
                precio_salida)
        _revisar_salidas(simbolo_salida, precio_salida)

    # ===== FASE DE APRENDIZAJE =====
    ahora = datetime.now()
    try:
        inicio_fase = datetime.fromisoformat(st.session_state.inicio_fase)
    except Exception:
        inicio_fase = ahora
        st.session_state.inicio_fase = ahora.isoformat()
    horas_transcurridas = (ahora - inicio_fase).total_seconds() / 3600
    horas_restantes = max(0, 48 - horas_transcurridas)
    if horas_transcurridas >= 48 and st.session_state.fase_actual == "operando":
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
                f"📊 Ganancia promedio: {signo_total}${resultado.get('profit_promedio', 0):.2f}\n"
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
        enviar_telegram("🔄 **NUEVA FASE DE 2 DÍAS INICIADA**")
        # ⭐ FIX: sin st.rerun() (rompía el fragmento); el ciclo continúa

    # ===== TABLA =====
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
        interfaz["fase"].info(f"📅 **FASE OPERATIVA** — Próximo análisis en {horas_restantes:.1f} horas")
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

    # ===== CARTERA: SALDO REAL DE BITSO =====
    saldo_real = obtener_saldo_bitso()
    columnas = interfaz["metricas"].columns(4)

    if saldo_real:
        mxn_real = float(saldo_real.get("mxn", {}).get("available", 0.0))
        # el total incluye lo reservado en órdenes abiertas
        mxn_total_real = float(saldo_real.get("mxn", {}).get("total", 0.0))
        reservado = max(0.0, mxn_total_real - mxn_real)
        btc_real = float(saldo_real.get("btc", {}).get("available", 0.0))
        eth_real = float(saldo_real.get("eth", {}).get("available", 0.0))
        valor_total_real = mxn_real + (btc_real * btc) + (eth_real * eth)

        columnas[0].metric(
            "Saldo MXN (Bitso)", f"${mxn_real:,.2f}",
            help=f"Disponible para operar. El total de tu cuenta (incluido lo reservado "
                 f"en órdenes abiertas) es ${mxn_total_real:,.2f}."
                 + (f" Diferencia reservada: ${reservado:,.2f}." if reservado > 0.01 else ""))
        columnas[1].metric("Valor total (Bitso)", f"${valor_total_real:,.2f}")
        columnas[2].metric("BTC / ETH (Bitso)", f"{btc_real:.6f} / {eth_real:.6f}")
        columnas[3].metric("Operaciones hoy", st.session_state.ops_del_dia)
        interfaz["cartera"].caption(
            f"🔗 Datos reales de Bitso — BTC ${btc:,.0f} · ETH ${eth:,.0f} MXN | "
            f"📋 Registro interno del bot: ${st.session_state.saldo:,.2f} "
            f"({st.session_state.posiciones.get('BTC', 0):.6f} BTC / "
            f"{st.session_state.posiciones.get('ETH', 0):.6f} ETH)"
            + (f" | 🔒 Reservado en órdenes abiertas: ${reservado:,.2f}"
               if reservado > 0.01 else "")
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

    # ===== POSICIÓN ABIERTA: PUNTO DE SALIDA =====
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

    # ===== CONTADOR DE ACIERTOS VS FALLOS DE LA FASE =====
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
        if resumen["tasa"] >= resumen["equilibrio"]:
            interfaz["aciertos"].success("✅ " + texto_ac + " — vas POR ENCIMA del punto de equilibrio.")
        else:
            interfaz["aciertos"].error("🚨 " + texto_ac + " — vas POR DEBAJO del punto de equilibrio.")

    if st.session_state.ciclo % 5 == 0 and st.session_state.modo_aprendizaje:
        for simbolo in ["BTC", "ETH"]:
            evaluacion = evaluar_rendimiento(simbolo)
            if evaluacion["accion"] == "AUMENTAR_RIESGO":
                st.session_state.umbral_caida = min(0.05, st.session_state.umbral_caida * 1.2)
                st.session_state.toma_ganancia = min(10.0, st.session_state.toma_ganancia * 1.1)
            elif evaluacion["accion"] == "REDUCIR_RIESGO":
                st.session_state.umbral_caida = max(0.001, st.session_state.umbral_caida * 0.8)
                st.session_state.toma_ganancia = max(0.5, st.session_state.toma_ganancia * 0.9)

    for simbolo, precio, senal, confianza_senal, razon in [
        ("BTC", btc, senal_btc, confianza_btc, razon_btc),
        ("ETH", eth, senal_eth, confianza_eth, razon_eth)
    ]:
        tendencia_30d = (st.session_state.tendencia_historica.get(simbolo, {}) or {}).get("tendencia", "NEUTRAL")
        probabilidad_senal = calcular_probabilidad(confianza_senal)
        umbral_valor = st.session_state.confianza_umbral
        st.session_state["ultima_senal_vista"] = {
            "sym": simbolo, "accion": senal, "razon": razon,
            "confianza_senal": confianza_senal, "precio": precio,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "tendencia_30d": tendencia_30d, "umbral": umbral_valor
        }

        if (not st.session_state.modo_solo_senales
                and horario_para_operar
                and st.session_state.fase_actual == "operando"):

            if senal == "BUY" and probabilidad_senal > umbral_valor:
                if st.session_state.posiciones.get(simbolo, 0) == 0:
                    if tendencia_30d != "BAJISTA":
                        volumen = volumen_onchain_btc if simbolo == "BTC" else volumen_onchain_eth
                        if volumen is None or volumen >= VOLUMEN_MINIMO_24H:
                            try:
                                ejecutar_compra_profesional(simbolo, precio, confianza_senal,
                                                            razon, tendencia_30d)
                            except Exception as e:
                                print(f"Error en la compra de {simbolo}: {e}")

            elif senal == "SELL" and probabilidad_senal > umbral_valor:
                if st.session_state.posiciones.get(simbolo, 0) > 0:
                    if tendencia_30d != "ALCISTA":
                        # La señal ya no exige +2.5%: cierra a la par o en ganancia.
                        # Las pérdidas las corta el límite de pérdida de _revisar_salidas().
                        _cerrar_posicion(simbolo, precio,
                                         f"señal SELL ({probabilidad_senal:.1f}%)",
                                         confianza_senal,
                                         minima_ganancia_pct=GANANCIA_MINIMA_VENTA_PCT)

        if probabilidad_senal > umbral_valor and senal != "HOLD":
            clave_marca = f"ultima_senal_enviada_{simbolo}"
            ultimo_envio = st.session_state.get(clave_marca, 0)
            if st.session_state.ciclo - ultimo_envio > 10:
                volumen_onchain = volumen_onchain_btc if simbolo == "BTC" else volumen_onchain_eth
                cambio_30d = (st.session_state.tendencia_historica.get(simbolo, {}) or {}).get("cambio_porcentual", 0)
                if enviar_senal_telegram(simbolo, senal, precio, razon, confianza_senal,
                                         volumen_onchain, cambio_30d, tendencia_30d):
                    st.session_state[clave_marca] = st.session_state.ciclo

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

def _panel():
    """Crea los contenedores del panel y ejecuta un ciclo completo.

    ⭐ FIX arquitectónico: los contenedores viven DENTRO del fragmento, así que el
    refresco periódico actualiza la interfaz sin bloquear el script con un `while True`.
    ⭐ FIX: 'tabla', 'historial' y 'aciertos' son containers (no empty) para que el
    título y el contenido se vean a la vez.
    """
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
