# -*- coding: utf-8 -*-
"""
Resumen diario para un canal de Telegram. Solo LEE los datos del bot y manda UN mensaje al día.
No opera, no usa las llaves de Bitso y no usa IA: todas las cifras las calcula el código con las
mismas funciones del panel (calcular_estadisticas_senales y calcular_estadisticas_bloqueadas).

Qué dice el mensaje (solo datos agregados; nada de saldos, llaves, posiciones ni operaciones)
  - Señales enviadas y bloqueadas por la segunda IA en las últimas 24 h.
  - Resultado observado de las señales enviadas a 1, 4 y 24 h (acumulado), con la advertencia de
    "pocas señales" mientras no haya muestra suficiente.
  - Qué habría pasado con las señales bloqueadas si se hubieran enviado.
  - El aviso de que es un simulador educativo, no asesoría financiera y que se puede perder dinero.
  No dice "probabilidad de acierto": la "probabilidad" del bot es fuerza de señal, no una frecuencia.

Cómo se enciende (en Render, variables de entorno; apagado por defecto)
  CANAL_RESUMEN=vista_previa   manda el mensaje SOLO a tu chat privado (TELEGRAM_CHAT_ID), con el
                               encabezado "VISTA PREVIA", para que lo revises antes de publicar
  CANAL_RESUMEN=publicar       lo manda al canal indicado en CANAL_RESUMEN_ID
  CANAL_RESUMEN=no             apagado (por defecto)
  CANAL_RESUMEN_ID=@nombre     canal público (o su id numérico -100…). Es una variable propia: NO es
                               TELEGRAM_CANAL_ID, así que no cambia a dónde van las señales
  CANAL_RESUMEN_HORA=20        hora de CDMX a partir de la cual sale el mensaje (0-23)
El bot debe ser administrador del canal con permiso para publicar mensajes.

Qué NO hace (por diseño)
  - En Firebase solo escribe en su propia ruta (resumen_publico), para no repetir el mensaje del día.
    Todo lo demás es GET. El bot no lee esa ruta.
  - No cambia TP, SL, umbral, pesos, comisión ni el anti-spam, y no toca el modo real.
"""
import re
import threading
import time
import traceback
from collections import Counter
from datetime import datetime, timedelta, timezone

ZONA_CDMX = timezone(timedelta(hours=-6))
MODOS = ("no", "vista_previa", "publicar")
RUTA_REGISTRO = "resumen_publico"      # única ruta de Firebase donde escribe
CADA_SEGUNDOS = 600                    # cuántas veces mira si ya toca (no envía más de uno al día)
MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
AVISO = ("Simulador educativo: no se opera con dinero real. No es asesoría financiera. "
         "Operar criptomonedas puede hacerte perder dinero. Los resultados pasados no garantizan "
         "resultados futuros.")


def _fecha_texto(momento):
    d = datetime.fromtimestamp(momento, ZONA_CDMX)
    return f"{d.day} {MESES[d.month - 1]} {d.year}"


def _pct(texto):
    """'33.3%' -> '33.3 %' (como se escribe en español)."""
    return str(texto).replace("%", " %")


def _plazo(clave):
    """'4h' -> '4 h'."""
    return clave[:-1] + " h" if clave.endswith("h") else clave


def _ts(registro):
    """Marca de tiempo del registro como número (0 si falta o no es un número)."""
    try:
        return float(registro.get("ts", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _desde(registros):
    """' desde el 5 nov 2026' con la fecha del registro más antiguo (vacío si no hay ninguna)."""
    marcas = [t for t in (_ts(r) for r in registros) if t > 0]
    return f" desde el {_fecha_texto(min(marcas))}" if marcas else ""


def _lista(datos):
    if isinstance(datos, dict):
        return [v for v in datos.values() if isinstance(v, dict)]
    if isinstance(datos, list):
        return [v for v in datos if isinstance(v, dict)]
    return []


def _leer(app, ruta, **params):
    r = app.requests.get(app._url_registro(ruta), params=params or None, timeout=8)
    if r.status_code != 200:
        raise RuntimeError(f"Firebase respondió {r.status_code}")
    return r.json()


def leer_registros(app):
    """(señales enviadas, señales bloqueadas). Las bloqueadas son None si no se pudieron leer, para
    no decir '0 bloqueadas' cuando en realidad no se supo."""
    senales = _lista(_leer(app, "senales", orderBy='"$key"', limitToLast=1000))
    try:
        bloqueadas = _lista(_leer(app, app.RUTA_BLOQUEADAS, orderBy='"$key"', limitToLast=500))
    except Exception as e:
        print(f"Resumen público: no pude leer las bloqueadas ({type(e).__name__}); salen sin esa parte.")
        bloqueadas = None
    return senales, bloqueadas


def construir_mensaje(app, senales, bloqueadas, ahora):
    """Texto plano del resumen. Función pura: no toca la red."""
    limite = ahora - 86400

    def reciente(r):
        return _ts(r) >= limite

    # Solo el motor actual pasa por Telegram; el motor v2 es un experimento que solo se registra.
    del_motor_actual = [r for r in senales if r.get("motor", "actual") == "actual"]
    enviadas = [r for r in del_motor_actual if reciente(r)]
    lineas = [f"📊 Resumen del día · {_fecha_texto(ahora)}",
              "Simulador educativo: no se opera con dinero real.", "", "Últimas 24 h"]
    monedas = Counter(r.get("simbolo", "?") for r in enviadas)
    detalle = ", ".join(f"{m} {n}" for m, n in sorted(monedas.items()))
    lineas.append(f"· Señales enviadas: {len(enviadas)}" + (f" ({detalle})" if detalle else ""))
    if bloqueadas is not None:
        lineas.append(f"· Bloqueadas por la segunda IA: {sum(1 for r in bloqueadas if reciente(r))}")

    pocas = False
    filas, _, _ = app.calcular_estadisticas_senales(senales)
    todas = {f["Plazo"]: f for f in filas if f["Grupo"] == "Todas"}
    lineas += ["", f"Resultado observado de las señales enviadas (acumulado{_desde(del_motor_actual)})"]
    if not todas:
        lineas.append("· Todavía no hay señales con resultado evaluado.")
    for clave in ("1h", "4h", "24h"):
        f = todas.get(clave)
        if not f:
            continue
        marca = " ⚠️" if str(f.get("Muestra", "")).startswith("⚠️") else ""
        pocas = pocas or bool(marca)
        lineas.append(f"· A {_plazo(clave)}: {f['Evaluadas']} evaluadas, {f['Aciertos']} acertaron "
                      f"({_pct(f['% acierto'])}), retorno medio {_pct(f['Retorno medio'])}{marca}")

    filas_b = app.calcular_estadisticas_bloqueadas(bloqueadas) if bloqueadas else []
    if filas_b:
        d_b = _desde(bloqueadas)
        lineas += ["", "Si se hubieran enviado las señales bloqueadas" + (f" (registradas{d_b})" if d_b else "")]
        for f in filas_b:
            marca = " ⚠️" if str(f.get("Muestra", "")).startswith("⚠️") else ""
            pocas = pocas or bool(marca)
            lineas.append(f"· A {_plazo(f['Plazo'])}: {f['Evaluadas']} evaluadas, {f['Habrían acertado']} "
                          f"habrían acertado ({_pct(f['% acierto'])}), retorno medio "
                          f"{_pct(f['Retorno medio'])}{marca}")

    comision = float(app.COMISION_TAKER) * 2 * 100
    lineas += ["", "Acierto = el precio se movió en la dirección de la señal al cumplirse el plazo. "
                   f"Los retornos son antes de comisiones (el simulador usa {comision:.2f} % de ida y vuelta)."]
    if pocas:
        lineas.append(f"Las filas marcadas con ⚠️ tienen menos de {app.MUESTRA_MINIMA_CONFIABLE} señales "
                      "evaluadas: esas cifras todavía no permiten concluir nada.")
    lineas += ["", AVISO]
    return "\n".join(lineas)


def _enviar(app, chat_id, texto):
    """True solo si Telegram respondió 200. Nunca escribe el token ni la URL en los logs."""
    try:
        r = app.requests.post(f"https://api.telegram.org/bot{app.TOKEN_TELEGRAM}/sendMessage",
                              json={"chat_id": chat_id, "text": texto[:4000],
                                    "disable_web_page_preview": True}, timeout=8)
        if r.status_code != 200:
            print(f"Resumen público: Telegram respondió {r.status_code}; no se marcó como enviado.")
            return False
        return True
    except Exception as e:
        print(f"Resumen público: no pude enviar ({type(e).__name__}).")
        return False


def _canal_valido(canal):
    return bool(re.fullmatch(r"@[A-Za-z][A-Za-z0-9_]{4,31}", canal) or re.fullmatch(r"-100\d{5,}", canal))


class Resumen:
    def __init__(self, app, modo="vista_previa", canal="", hora=20, reloj=time.time):
        self.app = app
        self.modo = modo
        self.canal = canal
        self.hora = hora
        self.reloj = reloj
        self._hecho = {}      # clave -> fecha (CDMX) del último envío, en memoria

    def _clave(self):
        return "publicado" if self.modo == "publicar" else "vista_previa"

    def _ya_enviado(self, clave, hoy):
        datos = _leer(self.app, f"{RUTA_REGISTRO}/{clave}")
        return isinstance(datos, dict) and datos.get("fecha") == hoy

    def _anotar(self, clave, hoy, ahora):
        try:
            self.app.requests.put(self.app._url_registro(f"{RUTA_REGISTRO}/{clave}"),
                                  json={"fecha": hoy, "ts": ahora, "modo": self.modo}, timeout=8)
        except Exception as e:
            print(f"Resumen público: no pude anotar el envío ({type(e).__name__}).")

    def revisar(self):
        """Envía el resumen si ya es la hora y hoy no salió. True/False si intentó enviar; None si no tocaba."""
        ahora = self.reloj()
        d = datetime.fromtimestamp(ahora, ZONA_CDMX)
        if d.hour < self.hora:
            return None
        hoy = d.strftime("%Y-%m-%d")
        clave = self._clave()
        if self._hecho.get(clave) == hoy:
            return None
        try:
            if self._ya_enviado(clave, hoy):
                self._hecho[clave] = hoy
                return None
            senales, bloqueadas = leer_registros(self.app)
        except Exception as e:
            # sin saber si ya salió hoy no se arriesga a duplicar un mensaje público
            print(f"Resumen público: no pude leer Firebase ({type(e).__name__}); lo intento después.")
            return None
        texto = construir_mensaje(self.app, senales, bloqueadas, ahora)
        if self.modo == "publicar":
            ok = _enviar(self.app, self.canal, texto)
        else:
            ok = _enviar(self.app, self.app.CHAT_ID_TELEGRAM,
                         "🔎 VISTA PREVIA (solo la ves tú; no se publicó nada)\n\n" + texto)
        if ok:
            self._hecho[clave] = hoy
            self._anotar(clave, hoy, ahora)
            print(f"Resumen público: enviado ({self.modo}).")
        return ok


def _entero(app, nombre, defecto, minimo, maximo):
    try:
        valor = int(float(app._secreto(nombre, defecto)))
    except (TypeError, ValueError):
        valor = defecto
    return max(minimo, min(maximo, valor))


def iniciar(app, retraso_inicial=90):
    """Arranca el resumen en un hilo aparte. Devuelve el hilo, o None si está apagado o falta algo."""
    modo = str(app._secreto("CANAL_RESUMEN", "no") or "no").strip().lower().replace("-", "_")
    if modo not in MODOS:
        print(f"Resumen público: CANAL_RESUMEN='{modo}' no es válido (no / vista_previa / publicar); queda apagado.")
        return None
    if modo == "no":
        print("Resumen público: apagado (CANAL_RESUMEN no vale vista_previa ni publicar).")
        return None
    faltan = [n for n, ok in (("FIREBASE_URL/FIREBASE_RUTA", app.FIREBASE_CONFIGURADO),
                              ("TELEGRAM_TOKEN", bool(app.TOKEN_TELEGRAM)),
                              ("TELEGRAM_CHAT_ID (para la vista previa)",
                               modo == "publicar" or bool(app.CHAT_ID_TELEGRAM))) if not ok]
    if faltan:
        print("Resumen público: apagado, falta configurar " + " y ".join(faltan) + ".")
        return None
    canal = str(app._secreto("CANAL_RESUMEN_ID", "") or "").strip()
    if modo == "publicar" and not _canal_valido(canal):
        print("Resumen público: CANAL_RESUMEN_ID debe ser @nombre_del_canal o un id que empiece con -100; "
              "no se publica nada y queda en vista_previa.")
        modo = "vista_previa"
        if not app.CHAT_ID_TELEGRAM:
            print("Resumen público: apagado, falta TELEGRAM_CHAT_ID para la vista previa.")
            return None
    resumen = Resumen(app, modo=modo, canal=canal, hora=_entero(app, "CANAL_RESUMEN_HORA", 20, 0, 23))

    def bucle():
        time.sleep(retraso_inicial)
        while True:
            try:
                resumen.revisar()
            except Exception:
                traceback.print_exc()
            time.sleep(CADA_SEGUNDOS)

    hilo = threading.Thread(target=bucle, name="resumen_publico", daemon=True)
    hilo.start()
    destino = "tu chat privado (vista previa)" if modo == "vista_previa" else f"el canal {canal}"
    print(f"📣 Resumen diario en marcha: modo {modo}, a {destino}, desde las {resumen.hora}:00 de CDMX")
    return hilo
