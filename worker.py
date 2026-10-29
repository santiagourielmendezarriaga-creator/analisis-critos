# -*- coding: utf-8 -*-
"""
Worker sin pantalla: ejecuta el MISMO código de app.py en un servidor (p. ej. Render),
sin necesidad de una pestaña abierta. Streamlit se sustituye por un "stub" que no dibuja
nada y devuelve los valores por defecto de los controles de la barra lateral.

- Cada `intervalo_actualizacion` segundos ejecuta un ciclo del bot (`_panel`).
- Responde "ok" en / y /health (para el servicio que lo visita y no lo deja dormir).
- Escribe un latido en Firebase (`worker`): mientras sea reciente, el panel de Streamlit
  NO ejecuta ciclos, para no duplicar señales ni órdenes.
- Los secretos se leen de variables de entorno (mismos nombres que en Streamlit).
"""
import importlib.util
import os
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer

os.environ.setdefault("MODO_WORKER", "true")


class _Estado(dict):
    """Imita st.session_state: acceso por clave y por atributo."""
    def __getattr__(self, nombre):
        try:
            return self[nombre]
        except KeyError:
            raise AttributeError(nombre)

    def __setattr__(self, nombre, valor):
        self[nombre] = valor

    def __delattr__(self, nombre):
        self.pop(nombre, None)


class _Nulo:
    """Objeto que acepta cualquier llamada o atributo y no hace nada (contenedores, etc.)."""
    def __call__(self, *args, **kwargs):
        return _Nulo()

    def __getattr__(self, nombre):
        if nombre.startswith("__"):
            raise AttributeError(nombre)
        return _Nulo()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __iter__(self):
        return iter(())

    def __getitem__(self, clave):
        return _Nulo()

    def columns(self, spec, *a, **k):
        cantidad = spec if isinstance(spec, int) else len(spec)
        return [_Nulo() for _ in range(cantidad)]

    def tabs(self, nombres, *a, **k):
        return [_Nulo() for _ in nombres]


class _Interfaz(_Nulo):
    """Controles que devuelven su valor por defecto; lo demás no hace nada."""
    def __init__(self, estado=None, secretos=None):
        self.session_state = estado if estado is not None else _Estado()
        self.secrets = secretos if secretos is not None else {}
        self.sidebar = self if estado is None else _Interfaz()

    def checkbox(self, etiqueta="", value=False, *a, **k):
        return value

    toggle = checkbox

    def number_input(self, etiqueta="", min_value=None, max_value=None, value=None, *a, **k):
        return value if value is not None else (min_value if min_value is not None else 0)

    slider = number_input

    def text_input(self, etiqueta="", value="", *a, **k):
        return value

    def selectbox(self, etiqueta="", options=(), index=0, *a, **k):
        opciones = list(options)
        return opciones[index] if opciones else None

    def button(self, *a, **k):
        return False

    def fragment(self, func=None, *a, **k):
        # Se ejecuta una vez al importar app.py; el bucle del worker lo repite.
        return func if func is not None else (lambda f: f)

    def rerun(self, *a, **k):
        return None

    def stop(self, *a, **k):
        return None


ULTIMO = {"ts": 0.0, "ciclos": 0, "errores": 0, "arranque": time.time()}


class _Salud(BaseHTTPRequestHandler):
    def do_GET(self):
        cuerpo = (f"ok · ciclos={ULTIMO['ciclos']} · errores={ULTIMO['errores']} · "
                  f"último ciclo hace {int(time.time() - ULTIMO['ts'])} s"
                  if ULTIMO["ts"] else "ok · arrancando").encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, *a):
        pass


def _servidor_salud():
    puerto = int(os.environ.get("PORT", "10000"))
    servidor = HTTPServer(("0.0.0.0", puerto), _Salud)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    print(f"🩺 Salud en el puerto {puerto}")


def cargar_app(ruta=None):
    st = _Interfaz()
    sys.modules["streamlit"] = st
    ruta = ruta or os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
    spec = importlib.util.spec_from_file_location("app", ruta)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["app"] = modulo
    spec.loader.exec_module(modulo)   # restaura el estado y ejecuta un primer ciclo
    return modulo, st


def latido(modulo):
    if not modulo.FIREBASE_CONFIGURADO:
        return
    try:
        modulo.requests.put(f"{modulo.URL_FIREBASE}/worker.json", timeout=5, json={
            "ts": time.time(), "ciclo": modulo.st.session_state.get("ciclo", 0),
            "arranque": ULTIMO["arranque"]})
    except Exception as e:
        print(f"Error en el latido: {type(e).__name__}")


def bucle(modulo, st, maximo_ciclos=None):
    n = 0
    while maximo_ciclos is None or n < maximo_ciclos:
        n += 1
        try:
            if n % 6 == 0:
                st.session_state.pop("auto_estado", None)   # releer pausa/reanudar desde Firebase
            modulo._panel()
            ULTIMO["ciclos"] += 1
        except Exception:
            ULTIMO["errores"] += 1
            traceback.print_exc()
        ULTIMO["ts"] = time.time()
        if n % 6 == 1:
            latido(modulo)
        try:
            pausa = max(5, int(st.session_state.get("intervalo_actualizacion", 5)))
        except Exception:
            pausa = 5
        time.sleep(pausa)


def main():
    _servidor_salud()
    modulo, st = cargar_app()
    latido(modulo)
    print("🚀 Worker en marcha")
    bucle(modulo, st)


if __name__ == "__main__":
    main()
