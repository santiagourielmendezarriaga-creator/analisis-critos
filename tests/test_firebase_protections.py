"""Ejercita funciones aisladas sin importar la app ni conectar servicios reales.

Importar app.py ejecuta el panel, por lo que extraemos sus funciones mediante AST.
"""
import ast
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


def cargar_funciones(archivo, nombres, contexto):
    arbol = ast.parse((ROOT / archivo).read_text(encoding="utf-8"))
    nodos = [nodo for nodo in arbol.body
             if isinstance(nodo, ast.FunctionDef) and nodo.name in nombres]
    assert {nodo.name for nodo in nodos} == set(nombres)
    exec(compile(ast.Module(body=nodos, type_ignores=[]), archivo, "exec"), contexto)
    return contexto


class FirebaseTests(unittest.TestCase):
    def setUp(self):
        self.ss = {}
        self.requests = SimpleNamespace(get=Mock(), put=Mock())
        self.st = SimpleNamespace(session_state=self.ss, sidebar=Mock(), rerun=Mock())
        self.ctx = cargar_funciones("app.py", {
            "_auto_guardar", "_auto_pausar", "_auto_sidebar", "auto_comprar",
            "_worker_activo", "_panel", "restaurar_desde_archivo",
        }, {
            "st": self.st, "requests": self.requests, "_auto_ruta": lambda: "https://example.invalid",
            "_auto_puede_operar": lambda: (True, ""), "avisar": Mock(), "_auto_aviso": Mock(),
            "OPERAR_AUTOMATICO": True, "ES_WORKER": False, "FIREBASE_CONFIGURADO": True,
            "URL_FIREBASE": "https://example.invalid", "SEGUNDOS_LATIDO_WORKER": 120,
            "time": SimpleNamespace(time=lambda: 1000),
        })

    def test_guardado_verifica_http_y_excepciones(self):
        for respuesta, esperado in ((SimpleNamespace(status_code=200), True),
                                    (SimpleNamespace(status_code=403), False),
                                    (TimeoutError(), False)):
            with self.subTest(respuesta=respuesta):
                self.requests.put.side_effect = respuesta if isinstance(respuesta, Exception) else None
                self.requests.put.return_value = respuesta
                self.assertEqual(self.ctx["_auto_guardar"]({"pausado": True}), esperado)
                self.assertEqual(self.ss["auto_guardado_fallido"], not esperado)

    def test_pausa_no_se_anuncia_como_confirmada_ante_error(self):
        self.requests.put.return_value = SimpleNamespace(status_code=500)
        estado = {"pausado": False}
        self.ctx["_auto_pausar"](estado, "motivo")
        self.assertTrue(estado["pausado"])
        self.assertTrue(self.ss["auto_guardado_fallido"])
        self.assertIn("No se pudo guardar", self.ctx["_auto_aviso"].call_args.args[0])

    def test_reanudacion_fallida_conserva_pausa_local(self):
        estado = {"pausado": True, "motivo": "manual", "perdidas_seguidas": 2}
        self.ctx["_auto_estado"] = lambda: estado
        self.st.sidebar.button.return_value = True
        self.requests.put.return_value = SimpleNamespace(status_code=500)
        self.ctx["_auto_sidebar"]()
        self.assertEqual(estado, {"pausado": True, "motivo": "manual", "perdidas_seguidas": 2})
        self.assertTrue(self.ss["auto_guardado_fallido"])
        self.st.sidebar.error.assert_called()
        self.st.rerun.assert_not_called()

    def test_pausa_manual_fallida_advierte_que_servidor_puede_seguir(self):
        estado = {"pausado": False, "motivo": ""}
        self.ctx["_auto_estado"] = lambda: estado
        self.st.sidebar.button.return_value = True
        self.requests.put.return_value = SimpleNamespace(status_code=500)
        self.ctx["_auto_sidebar"]()
        self.assertTrue(estado["pausado"])
        self.assertIn("servidor podría seguir operando", self.st.sidebar.error.call_args.args[0])
        self.st.rerun.assert_not_called()

    def test_compra_bloqueada_si_estado_no_fue_guardado(self):
        self.ss["auto_guardado_fallido"] = True
        self.ctx["obtener_saldo_bitso"] = Mock()
        self.ctx["auto_comprar"]("BTC", 100, 80, True, None)
        self.ctx["obtener_saldo_bitso"].assert_not_called()

    def test_estado_worker_distingue_ausencia_de_error(self):
        casos = [
            (200, {"ts": 990}, True), (200, {"ts": 800}, False),
            (200, None, False), (500, None, None), (200, {"ts": "invalido"}, None),
            (200, {"otro": 1}, None),
        ]
        for codigo, datos, esperado in casos:
            with self.subTest(codigo=codigo, datos=datos):
                self.ss.clear()
                self.requests.get.side_effect = None
                self.requests.get.return_value = SimpleNamespace(status_code=codigo, json=lambda: datos)
                self.assertIs(self.ctx["_worker_activo"](), esperado)
        self.ss.clear()
        self.requests.get.side_effect = TimeoutError()
        self.assertIsNone(self.ctx["_worker_activo"]())

    def test_panel_no_opera_si_estado_worker_es_desconocido(self):
        espacio = Mock()
        self.st.container = Mock(return_value=espacio)
        self.st.empty = Mock(return_value=espacio)
        self.ctx["_worker_activo"] = lambda: None
        self.ctx["ejecutar_ciclo"] = Mock()
        self.ctx["_panel"]()
        self.ctx["ejecutar_ciclo"].assert_not_called()
        espacio.error.assert_called_once()

    def test_panel_espera_si_no_puede_recuperar_el_estado(self):
        espacio = Mock()
        self.st.container = Mock(return_value=espacio)
        self.st.empty = Mock(return_value=espacio)
        self.ss["_cedido"] = True
        self.ctx["_worker_activo"] = lambda: False
        self.ctx["restaurar_desde_archivo"] = Mock(return_value=False)
        self.ctx["ejecutar_ciclo"] = Mock()
        self.ctx["_panel"]()
        self.assertTrue(self.ss["_cedido"])
        self.ctx["ejecutar_ciclo"].assert_not_called()
        self.ctx["restaurar_desde_archivo"].assert_called_once_with(iniciar_si_falla=False)

    def test_panel_reanuda_al_recuperar_el_estado(self):
        espacio = Mock()
        self.st.container = Mock(return_value=espacio)
        self.st.empty = Mock(return_value=espacio)
        self.ss["_cedido"] = True
        self.ctx["_worker_activo"] = lambda: False
        self.ctx["restaurar_desde_archivo"] = Mock(return_value=True)
        self.ctx["ejecutar_ciclo"] = Mock()
        self.ctx["_panel"]()
        self.assertFalse(self.ss["_cedido"])
        self.ctx["ejecutar_ciclo"].assert_called_once()

    def test_restauracion_fallida_no_reinicia_estado_en_relevo(self):
        self.ctx["cargar_datos"] = lambda: None
        self.ctx["iniciar_estado_nuevo"] = Mock()
        self.assertFalse(self.ctx["restaurar_desde_archivo"](iniciar_si_falla=False))
        self.ctx["iniciar_estado_nuevo"].assert_not_called()

    def test_worker_conserva_estado_local_si_fallo_el_guardado(self):
        for fallo in (True, False):
            with self.subTest(fallo=fallo):
                ss = {"auto_estado": {"pausado": True}, "auto_guardado_fallido": fallo}
                fake_st = SimpleNamespace(session_state=ss)
                modulo = SimpleNamespace(_panel=Mock())
                contexto = cargar_funciones("worker.py", {"bucle"}, {
                    "time": SimpleNamespace(time=lambda: 1000, sleep=lambda _: None),
                    "ULTIMO": {"ciclos": 0, "errores": 0, "ts": 0},
                    "traceback": SimpleNamespace(print_exc=Mock()), "latido": Mock(),
                })
                with patch.dict(sys.modules, {"vigia": SimpleNamespace(atender_solicitudes=Mock())}):
                    contexto["bucle"](modulo, fake_st, maximo_ciclos=6)
                self.assertEqual("auto_estado" in ss, fallo)


if __name__ == "__main__":
    unittest.main()
