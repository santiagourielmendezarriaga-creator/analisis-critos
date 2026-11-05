# -*- coding: utf-8 -*-
"""
Agente vigía del bot: SOLO LEE y AVISA. No opera.

Qué hace
  1. Cada cierto tiempo revisa, con reglas fijas, que el bot esté vivo (latido en Firebase) y que
     el motor v2 siga chequeando. Si algo no cuadra te manda un aviso por Telegram.
  2. Una vez al día (por defecto después de las 8:00 de CDMX) te manda un resumen: señales de
     las últimas 24 h, compra periódica simulada y prueba de tendencia en vivo. Las cifras del
     resumen las calcula el código (las mismas funciones del bot); un modelo de IA (Groq) solo
     agrega una "lectura" de 2-3 frases usando esas herramientas.

Qué NO puede hacer (por diseño)
  - No escribe en Firebase: solo hace GET. Su memoria (cuándo avisó) vive en el proceso.
  - No compra ni vende, y no toca las llaves de Bitso: no tiene ninguna herramienta para eso.
  - No escribe en el canal público de Telegram: solo en tu chat privado (TELEGRAM_CHAT_ID).
  - La IA no manda mensajes: solo devuelve texto, y es este código quien lo envía.
  - Tiene tope de pasos por consulta a la IA y de mensajes por día.

Cómo se enciende (en Render, variables de entorno; apagado por defecto)
  VIGIA=true                    enciende el vigía dentro del worker
  VIGIA_HORA_RESUMEN=8          hora de CDMX del resumen diario (0-23)
  VIGIA_MINUTOS=30              cada cuántos minutos revisa
  VIGIA_USAR_IA=true            false = resumen solo con las cifras, sin IA
"""
import json
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone

ZONA_CDMX = timezone(timedelta(hours=-6))
MAX_PASOS = 6                    # vueltas máximas del agente con la IA
MAX_MENSAJES_DIA = 10            # tope de mensajes de Telegram en 24 h
MAX_TEXTO_IA = 700               # largo máximo de la lectura de la IA
UMBRAL_LATIDO_MIN = 10           # el worker late cada ~30-60 s
UMBRAL_V2_HORAS = 2              # el motor v2 chequea cada 15 min
ENFRIAMIENTO_ALERTA_HORAS = 6    # no repite el mismo aviso antes de este tiempo
HERRAMIENTAS = ("estado_del_bot", "senales_recientes", "compra_periodica", "tendencia_en_vivo")

# Descripción de las herramientas que ve la IA (formato compatible con Groq/OpenAI).
ESQUEMA = [
    {"type": "function", "function": {
        "name": "estado_del_bot",
        "description": "Minutos desde el último latido del bot y estado del último chequeo del motor v2.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "senales_recientes",
        "description": "Cuántas señales hubo en las últimas horas, por motor y tipo, y cuál fue la última.",
        "parameters": {"type": "object", "properties": {"horas": {"type": "integer"}}}}},
    {"type": "function", "function": {
        "name": "compra_periodica",
        "description": "Resultado de la compra periódica SIMULADA (100 MXN por moneda cada 7 días).",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "tendencia_en_vivo",
        "description": "Resultado en vivo de la regla fija de tendencia diaria contra comprar y mantener.",
        "parameters": {"type": "object", "properties": {}}}},
]

PROMPT_SISTEMA = (
    "Eres el vigía de un bot de señales de criptomonedas que opera SOLO EN SIMULACIÓN. "
    "Únicamente puedes leer datos con tus herramientas. Consulta las cuatro herramientas y luego "
    "escribe una lectura de 2 a 3 frases en español: qué se ve normal y qué merece atención. "
    "Usa solo cifras que devuelvan las herramientas; no inventes nada. No recomiendes comprar, "
    "vender ni cambiar montos. Si hay pocos datos, dilo. Texto plano, sin viñetas ni formato."
)


def _hace(minutos):
    if minutos is None:
        return "sin dato"
    if minutos < 90:
        return f"{minutos:.0f} min"
    if minutos < 48 * 60:
        return f"{minutos / 60:.0f} h"
    return f"{minutos / 1440:.0f} d"


def _limpiar_lectura(texto):
    """Una sola línea, sin caracteres de formato de Telegram y con largo acotado."""
    t = " ".join(str(texto or "").replace("*", "").replace("_", "").replace("`", "").split())
    if len(t) > MAX_TEXTO_IA:
        t = t[:MAX_TEXTO_IA]
        corte = t.rfind(".")
        t = t[:corte + 1] if corte > 200 else t.rstrip() + "…"
    return t


class Vigia:
    def __init__(self, app, modelo=None, reloj=time.time, hora_resumen=8, usar_ia=True):
        self.app = app
        self.reloj = reloj
        self.hora_resumen = hora_resumen
        self._modelo = modelo
        self.usar_ia = usar_ia and (modelo is not None or bool(getattr(app, "GROQ_API_KEY", "")))
        self._alertas = {}        # tipo de aviso -> momento del último envío
        self._enviados = []       # momentos de los mensajes enviados (tope diario)
        self._resumen_fecha = None
        self._memo = {}

    # ------------------------------------------------------------ lectura (solo GET)
    def _leer(self, ruta, **params):
        r = self.app.requests.get(self.app._url_registro(ruta), params=params or None, timeout=8)
        if r.status_code != 200:
            raise RuntimeError(f"Firebase respondió {r.status_code}")
        return r.json()

    def _tool(self, nombre, **kw):
        """Ejecuta una herramienta una sola vez por revisión (así cifras e IA coinciden)."""
        clave = (nombre, json.dumps(kw, sort_keys=True))
        if clave not in self._memo:
            self._memo[clave] = getattr(self, nombre)(**kw)
        return self._memo[clave]

    # ------------------------------------------------------------ herramientas
    def estado_del_bot(self):
        ahora = self.reloj()
        w = self._leer("worker")
        ts = float(w["ts"]) if isinstance(w, dict) and w.get("ts") else None
        d = self._leer("v2_diagnostico")
        v2 = None
        if isinstance(d, dict) and d.get("ts"):
            v2 = {"chequeo_hace_min": round((ahora - float(d["ts"])) / 60, 1)}
            for m in ("BTC", "ETH"):
                v2[m] = (d.get(m) or {}).get("resultado", "?") if isinstance(d.get(m), dict) else "?"
        return {"latido_hace_min": None if ts is None else round((ahora - ts) / 60, 1), "motor_v2": v2}

    def senales_recientes(self, horas=24):
        horas = max(1, min(int(horas), 168))
        ahora = self.reloj()
        # $key es el orden en que Firebase guarda las señales; no requiere índices.
        datos = self._leer("senales", orderBy='"$key"', limitToLast=500)
        regs = [v for v in datos.values() if isinstance(v, dict)] if isinstance(datos, dict) else []
        recientes = sorted((r for r in regs if float(r.get("ts", 0) or 0) >= ahora - horas * 3600),
                           key=lambda r: float(r.get("ts", 0) or 0))
        por_motor, por_tipo = {}, {}
        for r in recientes:
            m = r.get("motor", "actual")
            por_motor[m] = por_motor.get(m, 0) + 1
            por_tipo[r.get("tipo", "?")] = por_tipo.get(r.get("tipo", "?"), 0) + 1
        ultima = None
        if recientes:
            u = recientes[-1]
            ultima = {"simbolo": u.get("simbolo"), "tipo": u.get("tipo"), "motor": u.get("motor", "actual"),
                      "probabilidad": u.get("probabilidad"),
                      "hace_min": round((ahora - float(u.get("ts", 0) or 0)) / 60, 1)}
        return {"horas": horas, "total": len(recientes), "por_motor": por_motor,
                "por_tipo": por_tipo, "ultima": ultima}

    def compra_periodica(self):
        datos = self._leer("dca_vivo")
        compras = list(datos.values()) if isinstance(datos, dict) else []
        precios = {"BTC": self.app.obtener_precio_bitso("btc_mxn"),
                   "ETH": self.app.obtener_precio_bitso("eth_mxn")}
        res = self.app.resultado_dca_vivo(compras, precios)
        if not res:
            return {"compras": len(compras), "nota": "aún sin compras simuladas, o sin precio de Bitso"}
        salida = {"compras": res["compras"], "desde": res["desde"]}
        for m in ("BTC", "ETH"):
            salida[m] = {"invertido": round(res[m]["invertido"], 2), "valdria_hoy": round(res[m]["valor"], 2),
                         "resultado_pct": round(res[m]["pct"], 2)}
        return salida

    def tendencia_en_vivo(self):
        datos = self._leer("tendencia_vivo")
        registros = list(datos.values()) if isinstance(datos, dict) else []
        res = self.app.resultado_tendencia_vivo(registros)
        if not res:
            return {"dias": len(registros), "nota": "aún pocos días guardados (se necesitan al menos 2)"}
        salida = {"dias": res["dias"], "desde": res["desde"]}
        for m in ("BTC", "ETH"):
            salida[m] = {"regla_pct": round(res[m]["regla"], 2), "mantener_pct": round(res[m]["mantener"], 2),
                         "dentro": bool(res[m]["dentro"])}
        return salida

    # ------------------------------------------------------------ envío (solo chat privado)
    def _enviar(self, texto):
        ahora = self.reloj()
        self._enviados = [t for t in self._enviados if ahora - t < 86400]
        if len(self._enviados) >= MAX_MENSAJES_DIA:
            print("Vigía: tope diario de mensajes alcanzado; no se envía.")
            return False
        if not getattr(self.app, "TELEGRAM_CONFIGURADO", False):
            return False
        if self.app.enviar_telegram(texto[:3500]):    # nunca el canal público
            self._enviados.append(ahora)
            return True
        return False

    # ------------------------------------------------------------ avisos con reglas fijas
    def revisar_alertas(self):
        self._memo = {}
        alertas = []
        try:
            estado = self._tool("estado_del_bot")
        except Exception as e:
            alertas.append(("firebase", f"⚠️ Vigía: no pude leer Firebase ({type(e).__name__}). "
                                        "Revisa que la base siga activa."))
        else:
            latido = estado["latido_hace_min"]
            if latido is None or latido > UMBRAL_LATIDO_MIN:
                alertas.append(("latido", "⚠️ Vigía: el bot no registra latido "
                                          f"({'nunca' if latido is None else 'hace ' + _hace(latido)}). "
                                          "Revisa el worker en Render."))
            v2 = estado["motor_v2"]
            if v2 and v2["chequeo_hace_min"] > UMBRAL_V2_HORAS * 60:
                alertas.append(("v2", "⚠️ Vigía: el motor v2 no chequea desde hace "
                                      f"{_hace(v2['chequeo_hace_min'])} (normalmente cada 15 min)."))
        enviados = []
        ahora = self.reloj()
        for tipo, texto in alertas:
            if ahora - self._alertas.get(tipo, 0) < ENFRIAMIENTO_ALERTA_HORAS * 3600:
                continue
            if self._enviar(texto):
                self._alertas[tipo] = ahora
                enviados.append(tipo)
        return enviados

    # ------------------------------------------------------------ resumen diario
    def datos_del_dia(self):
        datos = {}
        for clave, nombre, kw in (("estado", "estado_del_bot", {}), ("senales", "senales_recientes", {"horas": 24}),
                                  ("dca", "compra_periodica", {}), ("tendencia", "tendencia_en_vivo", {})):
            try:
                datos[clave] = self._tool(nombre, **kw)
            except Exception as e:
                datos[clave] = {"error": type(e).__name__}
        return datos

    @staticmethod
    def formatear_hechos(datos, fecha):
        """Texto con las cifras exactas; no interviene la IA."""
        out = [f"🛰️ Vigía del bot · {fecha}"]
        e = datos.get("estado", {})
        if "error" in e:
            out.append("• Bot: no pude leer su estado")
        else:
            t = f"• Bot: último latido hace {_hace(e.get('latido_hace_min'))}"
            if e.get("motor_v2"):
                v = e["motor_v2"]
                t += f" · motor v2 chequeó hace {_hace(v['chequeo_hace_min'])} (BTC {v['BTC']}, ETH {v['ETH']})"
            out.append(t)
        s = datos.get("senales", {})
        if "error" in s:
            out.append("• Señales: no pude leerlas")
        else:
            t = f"• Señales en {s['horas']} h: {s['total']}"
            if s["total"]:
                t += " (" + ", ".join(f"{k} {n}" for k, n in sorted(s["por_motor"].items())) + ")"
                u = s["ultima"]
                t += f" · última: {u['simbolo']} {u['tipo']} {u['probabilidad']}% hace {_hace(u['hace_min'])}"
            out.append(t)
        d = datos.get("dca", {})
        if "error" in d:
            out.append("• Compra periódica simulada: no pude leerla")
        elif "nota" in d:
            out.append(f"• Compra periódica simulada: {d['nota']}")
        else:
            out.append(f"• Compra periódica simulada: {d['compras']} compras desde {d['desde']} · "
                       f"BTC {d['BTC']['resultado_pct']:+.1f}% · ETH {d['ETH']['resultado_pct']:+.1f}%")
        tr = datos.get("tendencia", {})
        if "error" in tr:
            out.append("• Tendencia en vivo: no pude leerla")
        elif "nota" in tr:
            out.append(f"• Tendencia en vivo: {tr['nota']}")
        else:
            partes = " · ".join(f"{m} regla {tr[m]['regla_pct']:+.1f}% vs mantener {tr[m]['mantener_pct']:+.1f}%"
                                for m in ("BTC", "ETH"))
            out.append(f"• Tendencia en vivo ({tr['dias']} días): {partes}")
        return "\n".join(out)

    def resumen_diario(self):
        self._memo = {}
        ahora = datetime.fromtimestamp(self.reloj(), ZONA_CDMX)
        texto = self.formatear_hechos(self.datos_del_dia(), ahora.strftime("%Y-%m-%d"))
        if self.usar_ia:
            try:
                lectura = self.lectura_ia()
            except Exception as e:
                print(f"Vigía: la IA no pudo opinar ({type(e).__name__}); se envían solo las cifras.")
                lectura = ""
            if lectura:
                texto += "\n\n🤖 Lectura del agente (IA): " + lectura
        return texto + "\n\nSimulación y datos educativos; no es asesoría financiera."

    # ------------------------------------------------------------ el agente (IA con herramientas de lectura)
    def _llamar_groq(self, mensajes):
        a = self.app
        r = a.requests.post(a.GROQ_URL, headers={"Authorization": f"Bearer {a.GROQ_API_KEY}"}, timeout=40,
                            json={"model": a.GROQ_MODELO, "messages": mensajes, "tools": ESQUEMA,
                                  "tool_choice": "auto", "temperature": 0.2})
        if r.status_code != 200:
            raise RuntimeError(f"Groq respondió {r.status_code}")
        return r.json()["choices"][0]["message"]

    def _ejecutar(self, nombre, argumentos):
        """Solo corre herramientas de la lista; cualquier error vuelve a la IA como texto."""
        if nombre not in HERRAMIENTAS:
            return json.dumps({"error": "herramienta desconocida"})
        try:
            args = json.loads(argumentos or "{}")
            kw = {"horas": args.get("horas", 24)} if nombre == "senales_recientes" and isinstance(args, dict) else {}
            return json.dumps(self._tool(nombre, **kw), ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": type(e).__name__})

    def lectura_ia(self):
        modelo = self._modelo or self._llamar_groq
        mensajes = [{"role": "system", "content": PROMPT_SISTEMA},
                    {"role": "user", "content": "Consulta las herramientas y escribe la lectura de hoy."}]
        for _ in range(MAX_PASOS):
            msg = modelo(mensajes)
            llamadas = msg.get("tool_calls") or []
            if not llamadas:
                return _limpiar_lectura(msg.get("content"))
            mensajes.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": llamadas})
            for c in llamadas:
                f = c["function"]
                mensajes.append({"role": "tool", "tool_call_id": c["id"],
                                 "content": self._ejecutar(f["name"], f.get("arguments"))})
        return ""

    # ------------------------------------------------------------ una vuelta de revisión
    def revisar(self):
        self.revisar_alertas()
        ahora = datetime.fromtimestamp(self.reloj(), ZONA_CDMX)
        hoy = ahora.strftime("%Y-%m-%d")
        if ahora.hour >= self.hora_resumen and self._resumen_fecha != hoy:
            if self._enviar(self.resumen_diario()):
                self._resumen_fecha = hoy


def _entero(app, nombre, defecto, minimo, maximo):
    try:
        valor = int(float(app._secreto(nombre, defecto)))
    except (TypeError, ValueError):
        valor = defecto
    return max(minimo, min(maximo, valor))


def iniciar(app, retraso_inicial=300):
    """Arranca el vigía en un hilo aparte. Devuelve el hilo, o None si está apagado o falta algo."""
    if not app._a_booleano(app._secreto("VIGIA", False), False):
        return None
    if not (app.FIREBASE_CONFIGURADO and app.TELEGRAM_CONFIGURADO):
        print("Vigía: apagado, necesita Firebase y Telegram configurados.")
        return None
    vigia = Vigia(app, hora_resumen=_entero(app, "VIGIA_HORA_RESUMEN", 8, 0, 23),
                  usar_ia=app._a_booleano(app._secreto("VIGIA_USAR_IA", True), True))
    cada = _entero(app, "VIGIA_MINUTOS", 30, 5, 240) * 60

    def bucle():
        time.sleep(retraso_inicial)      # deja que el bot arranque y escriba su primer latido
        while True:
            try:
                vigia.revisar()
            except Exception:
                traceback.print_exc()
            time.sleep(cada)

    hilo = threading.Thread(target=bucle, name="vigia", daemon=True)
    hilo.start()
    print(f"👁️ Vigía en marcha (solo lectura y avisos; IA: {'sí' if vigia.usar_ia else 'no'})")
    return hilo
