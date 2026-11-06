"""Ejercita funciones aisladas sin importar la app ni conectar servicios reales.

Importar app.py ejecuta el panel, por lo que extraemos sus funciones mediante AST.
"""

import ast
from copy import deepcopy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


def cargar_funciones(archivo, nombres, contexto):
    """Carga funciones aisladas para probarlas sin iniciar servicios."""
    arbol = ast.parse((ROOT / archivo).read_text(encoding="utf-8"))
    nodos = [
        nodo
        for nodo in arbol.body
        if isinstance(nodo, ast.FunctionDef) and nodo.name in nombres
    ]
    assert {nodo.name for nodo in nodos} == set(nombres)
    exec(compile(ast.Module(body=nodos, type_ignores=[]), archivo, "exec"), contexto)
    return contexto


class Estado(dict):
    """Simula el acceso por atributo del estado de Streamlit."""

    def __getattr__(self, nombre):
        """Obtiene un valor del estado por su nombre."""
        return self[nombre]

    def __setattr__(self, nombre, valor):
        """Actualiza el estado mediante el acceso por atributo."""
        self[nombre] = valor


class FirebaseTests(unittest.TestCase):
    def setUp(self):
        """Prepara Firebase simulado y una base de estado confirmada."""
        self.ss = Estado()
        self.requests = SimpleNamespace(get=Mock(), put=Mock())
        self.st = SimpleNamespace(session_state=self.ss, sidebar=Mock(), rerun=Mock())
        self.base = {
            "pausado": False,
            "motivo": "",
            "perdidas_seguidas": 0,
            "costo": {"BTC": 10.0, "ETH": 0.0},
        }
        self.ss["auto_base"] = deepcopy(self.base)
        self.requests.get.return_value = SimpleNamespace(
            status_code=200, json=lambda: deepcopy(self.base), headers={"ETag": '"v1"'}
        )
        self.ctx = cargar_funciones(
            "app.py",
            {
                "_auto_leer",
                "_auto_estado",
                "_auto_conciliar",
                "_auto_recuperar",
                "_auto_guardar",
                "_auto_pausar",
                "_auto_sidebar",
                "auto_comprar",
                "_auto_vender",
                "_worker_activo",
                "_panel",
                "restaurar_desde_archivo",
                "auto_revisar_salidas",
            },
            {
                "deepcopy": deepcopy,
                "_a_booleano": lambda v, d: bool(v),
                "_a_entero": lambda v, d: int(v),
                "_a_decimal": lambda v, d: float(v),
                "st": self.st,
                "requests": self.requests,
                "_auto_ruta": lambda: "https://example.invalid",
                "_auto_puede_operar": lambda: (True, ""),
                "avisar": Mock(),
                "_auto_aviso": Mock(),
                "OPERAR_AUTOMATICO": True,
                "ES_WORKER": False,
                "FIREBASE_CONFIGURADO": True,
                "URL_FIREBASE": "https://example.invalid",
                "SEGUNDOS_LATIDO_WORKER": 120,
                "time": SimpleNamespace(time=lambda: 1000),
            },
        )

    def test_guardado_verifica_http_y_excepciones(self):
        """Guardado verifica http y excepciones."""
        for respuesta, esperado in (
            (SimpleNamespace(status_code=200), True),
            (SimpleNamespace(status_code=403), False),
            (TimeoutError(), False),
        ):
            with self.subTest(respuesta=respuesta):
                self.requests.put.side_effect = (
                    respuesta if isinstance(respuesta, Exception) else None
                )
                self.requests.put.return_value = respuesta
                self.assertEqual(
                    self.ctx["_auto_guardar"](dict(deepcopy(self.base), pausado=True)),
                    esperado,
                )
                self.assertEqual(self.ss["auto_guardado_fallido"], not esperado)

    def test_pausa_no_se_anuncia_como_confirmada_ante_error(self):
        """Pausa no se anuncia como confirmada ante error."""
        self.requests.put.return_value = SimpleNamespace(status_code=500)
        estado = {"pausado": False}
        self.ctx["_auto_pausar"](estado, "motivo")
        self.assertTrue(estado["pausado"])
        self.assertTrue(self.ss["auto_guardado_fallido"])
        self.assertIn("No se pudo guardar", self.ctx["_auto_aviso"].call_args.args[0])

    def test_reanudacion_fallida_conserva_pausa_local(self):
        """Reanudacion fallida conserva pausa local."""
        estado = {"pausado": True, "motivo": "manual", "perdidas_seguidas": 2}
        self.ctx["_auto_estado"] = lambda: estado
        self.st.sidebar.button.return_value = True
        self.requests.put.return_value = SimpleNamespace(status_code=500)
        self.ctx["_auto_sidebar"]()
        self.assertEqual(
            estado, {"pausado": True, "motivo": "manual", "perdidas_seguidas": 2}
        )
        self.assertTrue(self.ss["auto_guardado_fallido"])
        self.st.sidebar.error.assert_called()
        self.st.rerun.assert_not_called()

    def test_pausa_manual_fallida_advierte_que_servidor_puede_seguir(self):
        """Pausa manual fallida advierte que servidor puede seguir."""
        estado = {"pausado": False, "motivo": ""}
        self.ctx["_auto_estado"] = lambda: estado
        self.st.sidebar.button.return_value = True
        self.requests.put.return_value = SimpleNamespace(status_code=500)
        self.ctx["_auto_sidebar"]()
        self.assertTrue(estado["pausado"])
        self.assertIn(
            "servidor podría seguir operando", self.st.sidebar.error.call_args.args[0]
        )
        self.st.rerun.assert_not_called()

    def test_estado_sin_confirmar_no_se_muestra_como_activo(self):
        """Estado sin confirmar no se muestra como activo."""
        self.ss["auto_guardado_fallido"] = True
        self.ctx["_auto_estado"] = lambda: {"pausado": False}
        self.st.sidebar.button.return_value = False
        self.ctx["_auto_sidebar"]()
        self.st.sidebar.success.assert_not_called()
        self.st.sidebar.error.assert_called()

    def test_compra_bloqueada_si_estado_no_fue_guardado(self):
        """Compra bloqueada si estado no fue guardado."""
        self.ss["auto_guardado_fallido"] = True
        self.ctx["obtener_saldo_bitso"] = Mock()
        self.ctx["auto_comprar"]("BTC", 100, 80, True, None)
        self.ctx["obtener_saldo_bitso"].assert_not_called()

    def test_estado_worker_distingue_ausencia_de_error(self):
        """Estado worker distingue ausencia de error."""
        casos = [
            (200, {"ts": 990}, True),
            (200, {"ts": 800}, False),
            (200, None, False),
            (500, None, None),
            (200, {"ts": "invalido"}, None),
            (200, {"otro": 1}, None),
        ]
        for codigo, datos, esperado in casos:
            with self.subTest(codigo=codigo, datos=datos):
                self.ss.clear()
                self.requests.get.side_effect = None
                self.requests.get.return_value = SimpleNamespace(
                    status_code=codigo, json=lambda: datos
                )
                self.assertIs(self.ctx["_worker_activo"](), esperado)
        self.ss.clear()
        self.requests.get.side_effect = TimeoutError()
        self.assertIsNone(self.ctx["_worker_activo"]())

    def test_panel_no_opera_si_estado_worker_es_desconocido(self):
        """Panel no opera si estado worker es desconocido."""
        espacio = Mock()
        self.st.container = Mock(return_value=espacio)
        self.st.empty = Mock(return_value=espacio)
        self.ctx["_worker_activo"] = lambda: None
        self.ctx["ejecutar_ciclo"] = Mock()
        self.ctx["_panel"]()
        self.ctx["ejecutar_ciclo"].assert_not_called()
        espacio.error.assert_called_once()

    def test_panel_espera_si_no_puede_recuperar_el_estado(self):
        """Panel espera si no puede recuperar el estado."""
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
        self.ctx["restaurar_desde_archivo"].assert_called_once_with(
            iniciar_si_falla=False
        )

    def test_panel_reanuda_al_recuperar_el_estado(self):
        """Panel reanuda al recuperar el estado."""
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
        """Restauracion fallida no reinicia estado en relevo."""
        self.ctx["cargar_datos"] = lambda: None
        self.ctx["iniciar_estado_nuevo"] = Mock()
        self.assertFalse(self.ctx["restaurar_desde_archivo"](iniciar_si_falla=False))
        self.ctx["iniciar_estado_nuevo"].assert_not_called()

    def test_worker_conserva_estado_local_si_fallo_el_guardado(self):
        """Worker conserva estado local si fallo el guardado."""
        for fallo in (True, False):
            with self.subTest(fallo=fallo):
                ss = {"auto_estado": {"pausado": True}, "auto_guardado_fallido": fallo}
                fake_st = SimpleNamespace(session_state=ss)
                modulo = SimpleNamespace(
                    _panel=Mock(), _auto_recuperar=Mock(return_value=False)
                )
                contexto = cargar_funciones(
                    "worker.py",
                    {"bucle"},
                    {
                        "time": SimpleNamespace(
                            time=lambda: 1000, sleep=lambda _: None
                        ),
                        "ULTIMO": {"ciclos": 0, "errores": 0, "ts": 0},
                        "traceback": SimpleNamespace(print_exc=Mock()),
                        "latido": Mock(),
                    },
                )
                with patch.dict(
                    sys.modules, {"vigia": SimpleNamespace(atender_solicitudes=Mock())}
                ):
                    contexto["bucle"](modulo, fake_st, maximo_ciclos=6)
                self.assertEqual("auto_estado" in ss, fallo)
                self.assertEqual(modulo._auto_recuperar.call_count, int(fallo))
                self.assertEqual(modulo._panel.call_count, 6)

    def remoto(self, datos, etag='"v1"'):
        """Simula una lectura versionada de Firebase."""
        self.requests.get.side_effect = None
        self.requests.get.return_value = SimpleNamespace(
            status_code=200, json=lambda: deepcopy(datos), headers={"ETag": etag}
        )

    def test_recupera_venta_pendiente_sin_borrar_pausa_remota(self):
        """Cerrar la última posición se confirma sin borrar la pausa de otra instancia."""
        local = deepcopy(self.base)
        local["costo"]["BTC"] = 0.0
        remoto = dict(deepcopy(self.base), pausado=True, motivo="riesgo worker")
        self.ss.update(auto_estado=local, auto_guardado_fallido=True)
        self.remoto(remoto)
        self.requests.put.return_value = SimpleNamespace(status_code=200)
        self.assertTrue(self.ctx["_auto_recuperar"]())
        self.assertTrue(local["pausado"])
        self.assertEqual(local["motivo"], "riesgo worker")
        self.assertEqual(local["costo"]["BTC"], 0.0)
        self.assertFalse(self.ss["auto_guardado_fallido"])
        self.assertEqual(
            self.requests.put.call_args.kwargs["headers"], {"if-match": '"v1"'}
        )

    def test_relevo_concilia_costos_worker_y_pausa_local(self):
        """Antes de restaurar posiciones incorpora costos remotos y confirma la pausa pendiente."""
        local = dict(deepcopy(self.base), pausado=True, motivo="manual")
        remoto = deepcopy(self.base)
        remoto["costo"]["ETH"] = 15.0
        self.ss.update(auto_estado=local, auto_guardado_fallido=True, _cedido=True)
        self.remoto(remoto)
        self.requests.put.return_value = SimpleNamespace(status_code=200)
        espacio = Mock()
        self.st.container = Mock(return_value=espacio)
        self.st.empty = Mock(return_value=espacio)
        self.ctx["_worker_activo"] = lambda: False

        def restaurar(**kwargs):
            """Comprueba la conciliación antes de restaurar posiciones."""
            self.assertTrue(local["pausado"])
            self.assertEqual(local["costo"]["ETH"], 15.0)
            return True

        self.ctx["restaurar_desde_archivo"] = Mock(side_effect=restaurar)
        self.ctx["ejecutar_ciclo"] = Mock()
        self.ctx["_panel"]()
        self.ctx["ejecutar_ciclo"].assert_called_once()
        self.assertFalse(self.ss["_cedido"])

    def test_conflicto_no_sobrescribe_ni_desbloquea_compras(self):
        """Dos cambios incompatibles de costo quedan pendientes aun al reintentar."""
        local = deepcopy(self.base)
        local["costo"]["BTC"] = 0.0
        remoto = dict(deepcopy(self.base), pausado=True, motivo="worker")
        remoto["costo"]["BTC"] = 20.0
        self.ss.update(auto_estado=local, auto_guardado_fallido=True)
        self.remoto(remoto)
        for _ in range(2):
            self.assertFalse(self.ctx["_auto_recuperar"]())
            self.assertTrue(self.ss["auto_guardado_fallido"])
            self.assertEqual(local["costo"]["BTC"], 0.0)
            self.assertTrue(local["pausado"])
        self.requests.put.assert_not_called()

    def test_relevo_no_restaura_posiciones_si_hay_conflicto(self):
        """Un relevo ambiguo no mezcla posiciones nuevas con costos locales pendientes."""
        self.ss.update(auto_guardado_fallido=True, _cedido=True)
        espacio = Mock()
        self.st.container = Mock(return_value=espacio)
        self.st.empty = Mock(return_value=espacio)
        self.ctx["_worker_activo"] = lambda: False
        self.ctx["_auto_recuperar"] = Mock(return_value=False)
        self.ctx["restaurar_desde_archivo"] = Mock()
        self.ctx["ejecutar_ciclo"] = Mock()
        self.ctx["_panel"]()
        self.ctx["restaurar_desde_archivo"].assert_not_called()
        self.ctx["ejecutar_ciclo"].assert_not_called()
        self.assertTrue(self.ss["_cedido"])

    def test_etag_cambiado_no_confirma_y_reintento_conserva_cambios_remotos(self):
        """Un escritor concurrente provoca 412 y se relee antes del siguiente intento."""
        local = deepcopy(self.base)
        local["costo"]["BTC"] = 0.0
        self.ss["auto_estado"] = local
        self.requests.put.return_value = SimpleNamespace(status_code=412)
        self.assertFalse(self.ctx["_auto_recuperar"]())
        self.assertTrue(self.ss["auto_guardado_fallido"])
        self.remoto(dict(deepcopy(self.base), pausado=True, motivo="worker"), '"v2"')
        self.requests.put.return_value = SimpleNamespace(status_code=200)
        self.assertTrue(self.ctx["_auto_recuperar"]())
        self.assertTrue(local["pausado"])
        self.assertEqual(local["costo"]["BTC"], 0.0)
        self.assertEqual(
            self.requests.put.call_args.kwargs["headers"], {"if-match": '"v2"'}
        )

    def test_timeout_tras_guardado_no_duplica_cambio(self):
        """Una escritura aceptada con respuesta perdida se puede confirmar al releer."""
        local = deepcopy(self.base)
        local["perdidas_seguidas"] = 1
        self.ss["auto_estado"] = local
        self.requests.put.side_effect = TimeoutError()
        self.assertFalse(self.ctx["_auto_recuperar"]())
        self.remoto(local)
        self.requests.put.side_effect = None
        self.requests.put.return_value = SimpleNamespace(status_code=200)
        self.assertTrue(self.ctx["_auto_recuperar"]())
        self.assertEqual(local["perdidas_seguidas"], 1)

    def test_lectura_sin_etag_o_con_error_no_escribe(self):
        """No hay guardados incondicionales si no se puede verificar la versión remota."""
        local = deepcopy(self.base)
        for respuesta in (
            SimpleNamespace(status_code=500),
            SimpleNamespace(status_code=200, json=lambda: None, headers={}),
        ):
            self.requests.get.return_value = respuesta
            self.assertFalse(self.ctx["_auto_guardar"](local))
            self.assertTrue(self.ss["auto_guardado_fallido"])
        self.requests.put.assert_not_called()

    def test_worker_recupera_sin_posiciones_y_mantiene_ciclos(self):
        """El reintento periódico recupera una venta pendiente sin necesitar otra venta."""
        local = deepcopy(self.base)
        local["costo"]["BTC"] = 0.0
        self.ss.update(auto_estado=local, auto_guardado_fallido=True, posiciones={})
        self.requests.put.return_value = SimpleNamespace(status_code=200)
        modulo = SimpleNamespace(
            _panel=Mock(), _auto_recuperar=self.ctx["_auto_recuperar"]
        )
        contexto = cargar_funciones(
            "worker.py",
            {"bucle"},
            {
                "time": SimpleNamespace(time=lambda: 1000, sleep=lambda _: None),
                "ULTIMO": {"ciclos": 0, "errores": 0, "ts": 0},
                "traceback": SimpleNamespace(print_exc=Mock()),
                "latido": Mock(),
            },
        )
        with patch.dict(
            sys.modules, {"vigia": SimpleNamespace(atender_solicitudes=Mock())}
        ):
            contexto["bucle"](modulo, self.st, maximo_ciclos=6)
        self.assertFalse(self.ss["auto_guardado_fallido"])
        self.assertEqual(modulo._panel.call_count, 6)
        self.assertEqual(contexto["ULTIMO"]["errores"], 0)

    def test_fallo_guardado_no_impide_salidas_de_proteccion(self):
        """Una pausa pendiente bloquea compras pero permite vender por TP o SL."""
        self.ss.update(
            auto_guardado_fallido=True,
            posiciones={"BTC": 1.0},
            precio_entrada={"BTC": 100.0},
        )
        self.ctx.update(
            AUTO_TP_PCT=5.0, AUTO_SL_PCT=1.0, _auto_vender=Mock(return_value=True)
        )
        for precio in (106.0, 98.0):
            self.ctx["auto_revisar_salidas"]({"BTC": precio})
        self.assertEqual(self.ctx["_auto_vender"].call_count, 2)
        self.assertTrue(self.ss["auto_guardado_fallido"])

    def test_recuperacion_fallida_no_descarta_pausa_local(self):
        """Una caída prolongada conserva la pausa pendiente y el bloqueo de compras."""
        local = dict(deepcopy(self.base), pausado=True, motivo="manual")
        self.ss.update(auto_estado=local, auto_guardado_fallido=True)
        self.requests.get.side_effect = TimeoutError()
        self.assertFalse(self.ctx["_auto_recuperar"]())
        self.assertTrue(local["pausado"])
        self.assertTrue(self.ss["auto_guardado_fallido"])
        self.requests.put.assert_not_called()

    def test_reanudacion_fallida_conserva_costo_remoto_en_reintento(self):
        """Revertir la pausa no debe convertir el costo remoto en una edición local."""
        base = dict(
            deepcopy(self.base), pausado=True, motivo="manual", perdidas_seguidas=2
        )
        local = deepcopy(base)
        remoto = deepcopy(base)
        remoto["costo"]["BTC"] = 30.0
        self.ss.update(auto_base=base, auto_estado=local)
        self.remoto(remoto)
        self.requests.put.return_value = SimpleNamespace(status_code=500)
        self.st.sidebar.button.return_value = True
        self.ctx["_auto_sidebar"]()
        self.assertEqual(local["costo"]["BTC"], 30.0)
        self.assertTrue(local["pausado"])
        self.assertEqual(local["perdidas_seguidas"], 2)
        self.requests.put.return_value = SimpleNamespace(status_code=200)
        self.assertTrue(self.ctx["_auto_recuperar"]())
        self.assertEqual(
            self.requests.put.call_args.kwargs["json"]["costo"]["BTC"], 30.0
        )

    def test_fallo_lectura_restringe_compra_y_permite_venta_protectora(self):
        """Tras limpiar caché, el respaldo permite vender pero no comprar durante una caída."""
        self.ss.update(
            posiciones={"BTC": 1.0},
            precio_entrada={"BTC": 10.0},
            precio_maximo={"BTC": 10.0},
            ops_del_dia=0,
            operaciones=[],
        )
        self.requests.get.side_effect = TimeoutError()
        saldo = Mock(return_value={"btc": {"total": 1.0, "available": 1.0}})
        self.ctx.update(
            obtener_saldo_bitso=saldo,
            _auto_redondear=lambda x: x,
            AUTO_LIBROS={"BTC": "btc_mxn"},
            colocar_orden_bitso=Mock(return_value={"oid": "test"}),
            _auto_fills=lambda *args: {"menor": 11.0, "com_mxn": 0.0, "precio": 11.0},
            guardar_datos=lambda: (True, ""),
            AUTO_MAX_PERDIDAS_SEGUIDAS=2,
            datetime=SimpleNamespace(now=lambda: "ahora"),
        )
        self.ctx["auto_comprar"]("BTC", 10, 80, True, None)
        saldo.assert_not_called()
        self.assertTrue(self.ss["auto_guardado_fallido"])
        self.assertTrue(self.ctx["_auto_vender"]("BTC", 11, "TP"))
        self.ctx["colocar_orden_bitso"].assert_called_once_with(
            "btc_mxn", "sell", "1.00000000", 11, tipo="market"
        )
        self.assertEqual(self.ss["auto_estado"]["costo"]["BTC"], 0.0)
        self.assertTrue(self.ss["auto_guardado_fallido"])
        self.remoto(dict(deepcopy(self.base), pausado=True, motivo="panel"))
        self.requests.put.return_value = SimpleNamespace(status_code=200)
        self.assertTrue(self.ctx["_auto_recuperar"]())
        self.assertTrue(self.ss["auto_estado"]["pausado"])
        self.assertEqual(self.ss["auto_estado"]["costo"]["BTC"], 0.0)

    def test_fallo_lectura_sin_respaldo_bloquea_compra_y_venta(self):
        """Sin ningún estado confirmado no se supone el costo ni se inicia una operación."""
        self.ss.pop("auto_base")
        self.requests.get.side_effect = TimeoutError()
        self.ctx["obtener_saldo_bitso"] = Mock()
        self.ctx["auto_comprar"]("BTC", 10, 80, True, None)
        self.assertFalse(self.ctx["_auto_vender"]("BTC", 11, "TP"))
        self.ctx["obtener_saldo_bitso"].assert_not_called()
        self.assertTrue(self.ss["auto_guardado_fallido"])

    def test_recupera_si_primera_lectura_fallo_sin_respaldo(self):
        """Tras restablecer Firebase, puede recuperarse una primera lectura fallida."""
        self.ss.pop("auto_base")
        self.requests.get.side_effect = TimeoutError()
        self.assertIsNone(self.ctx["_auto_estado"]())
        self.assertTrue(self.ss["auto_guardado_fallido"])
        self.remoto(self.base)
        self.requests.put.return_value = SimpleNamespace(status_code=200)
        self.assertTrue(self.ctx["_auto_recuperar"]())
        self.assertFalse(self.ss["auto_guardado_fallido"])


if __name__ == "__main__":
    unittest.main()
