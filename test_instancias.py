"""
Pruebas de la logica del punto 2 (editor de instancias y comparacion), sin interfaz grafica.
Ejecutar:  python test_instancias.py     (o:  pytest test_instancias.py)
"""

import os
import tempfile

import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure

from ambientes import BatallaNavalEnv
from comparar import dibujar_comparacion, ejecutar_comparacion, resumen_agentes, COLUMNAS_RESUMEN
from dificultad import NIVELES
from editor_instancia import EditorInstancia
from instancia import Instancia, resolver
from partida import Partida
from sesion_agente import SesionAgente


def _editor_completo():
    ed = EditorInstancia(NIVELES['facil'])                    # 6x6: Crucero 3, Destructor 2, Lancha 2
    assert ed.colocar('Crucero', 0, 0, 'H')
    assert ed.colocar('Destructor', 2, 0, 'V')
    assert ed.colocar('Lancha', 5, 2, 'H')
    return ed


def test_env_conserva_disposicion_manual_tras_reset():
    ed = _editor_completo()
    inst = ed.a_instancia(manual=True)
    env = inst.crear_env(seed=1)
    esperado = sorted(ed.disposicion())
    assert sorted(env.disposicion_actual()) == esperado
    env.reset(seed=99)
    env.reset()
    assert sorted(env.disposicion_actual()) == esperado       # reset NO la reemplaza por una aleatoria


def test_env_disposicion_invalida():
    for malas in ([('Crucero', 0, 0, 'H')],                                      # faltan barcos
                  [('Crucero', 0, 4, 'H'), ('Destructor', 2, 0, 'V'), ('Lancha', 5, 2, 'H')]):  # se sale
        try:
            BatallaNavalEnv(config=NIVELES['facil'], disposicion=malas)
        except ValueError:
            continue
        raise AssertionError("debio lanzar ValueError")


def test_reglas_de_colocacion_del_editor():
    ed = EditorInstancia(NIVELES['facil'])
    assert ed.colocar('Crucero', 0, 0, 'H')
    assert not ed.puede_colocar('Destructor', 0, 1, 'V')       # solapa
    assert ed.puede_colocar('Destructor', 1, 0, 'H')           # adyacente: permitido por defecto
    assert not ed.puede_colocar('Destructor', 0, 5, 'H')       # fuera del tablero
    ed.cambiar_adyacencia(False)
    assert not ed.puede_colocar('Destructor', 1, 0, 'H')       # ahora no pueden tocarse
    assert not ed.puede_colocar('Destructor', 1, 3, 'H')       # ni en diagonal
    assert ed.puede_colocar('Destructor', 2, 0, 'H')
    assert ed.puede_colocar('Crucero', 3, 3, 'V')              # mover un barco ya colocado


def test_cambios_quitan_barcos_invalidos():
    ed = _editor_completo()
    quitados = ed.cambiar_dimensiones(4, 4)
    assert 'Lancha' in quitados and 'Crucero' not in quitados
    assert ed.pendientes == ['Lancha']
    assert ed.colocar('Lancha', 1, 3, 'V')                     # toca en diagonal al Crucero (0,2)
    assert ed.completa
    assert ed.cambiar_adyacencia(False) == ['Lancha']          # al prohibir contacto se quita
    assert ed.pendientes == ['Lancha']


def test_a_instancia_valida():
    ed = EditorInstancia(NIVELES['facil'])
    try:
        ed.a_instancia(manual=True)
        raise AssertionError("debio exigir todos los barcos")
    except ValueError as e:
        assert 'Crucero' in str(e)
    assert not ed.a_instancia(manual=False).manual
    ed.max_disparos = 3
    try:
        ed.a_instancia(manual=False)                           # limite menor que las casillas de barco
        raise AssertionError("debio rechazar el limite")
    except ValueError:
        pass


def test_colocar_al_azar_y_editar():
    ed = EditorInstancia(NIVELES['medio'])
    ed.colocar_al_azar(seed=3)
    assert ed.completa
    nombre = next(iter(ed.flota))
    ed.quitar(nombre)
    assert ed.pendientes == [nombre]


def test_json_ida_y_vuelta():
    ed = _editor_completo()
    ed.prob_ruido, ed.max_disparos, ed.mostrar_flota_restante = 0.1, 30, False
    inst = ed.a_instancia(manual=True)
    with tempfile.TemporaryDirectory() as d:
        ruta = os.path.join(d, 'inst.json')
        inst.guardar(ruta)
        otra = Instancia.cargar(ruta)
    assert otra.config == inst.config and otra.disposicion == inst.disposicion
    assert otra.firma() == inst.firma()
    ed2 = EditorInstancia()
    ed2.cargar(otra)
    assert ed2.completa and ed2.filas == 6 and ed2.prob_ruido == 0.1


def test_json_invalido():
    for datos in ({}, {'config': {'nombre': 'x'}}):
        try:
            Instancia.desde_dict(datos)
        except (ValueError, TypeError):
            continue
        raise AssertionError("debio rechazar el archivo")


def test_sesion_con_instancia_manual_y_retroceso():
    inst = _editor_completo().a_instancia(manual=True)
    s = SesionAgente('caza', 'medio', 5, instancia=inst)       # 'nivel' se ignora con instancia
    assert s.config.filas == 6
    for _ in range(6):
        s.paso()
    s.atras(); s.atras()
    assert sorted(s.env_vista().disposicion_actual()) == sorted(inst.disposicion)


def test_partida_con_semilla_e_instancia():
    p = Partida('medio')
    assert 1 <= p.seed <= 999_999 and 'Semilla' in p.panel_markdown()
    p.nueva_instancia(_editor_completo().a_instancia(manual=True))
    d1 = sorted(p.env.disposicion_actual())
    p.nueva()
    assert sorted(p.env.disposicion_actual()) == d1            # flota manual: igual en cada partida
    assert 'a mano' in p.panel_markdown()
    p2 = Partida('facil')
    s1, seed = sorted(p2.env.disposicion_actual()), p2.seed
    p2.nueva()                                                  # flota al azar nueva, semilla nueva
    p2.env.reset(seed)                                          # la semilla mostrada reproduce la flota
    assert sorted(p2.env.disposicion_actual()) == s1


def test_resolver():
    assert resolver('medio').config.nombre == 'Medio'
    try:
        resolver('personalizada')
        raise AssertionError
    except ValueError:
        pass


def test_comparacion_misma_instancia_y_graficas():
    inst = _editor_completo().a_instancia(manual=True)
    avance = []
    df, errores = ejecutar_comparacion(['aleatorio', 'caza', 'bayes'], inst, n=4, seed_base=10,
                                       progreso=lambda h, t, txt: avance.append((h, t)))
    assert not errores and len(df) == 12 and avance[-1] == (12, 12)
    # misma flota para todos: la instancia es manual
    tabla = resumen_agentes(df)
    assert list(tabla.columns) == COLUMNAS_RESUMEN and len(tabla) == 3
    assert (tabla['Partidas'] == 4).all()
    fig = Figure(figsize=(10, 6))
    dibujar_comparacion(fig, df, inst.config.casillas_barco)
    assert len(fig.axes) == 6
    fig.savefig('/tmp/comparacion_test.png', dpi=80)


def test_comparacion_cancelar_y_agente_roto():
    inst = Instancia.de_nivel('facil')
    df, _ = ejecutar_comparacion(['caza'], inst, n=5, cancelar=lambda: True)
    assert df.empty
    from agents import AGENTES, Agente

    class Roto(Agente):
        def __init__(self, seed=None, config=None):
            super().__init__(name='Roto')
        def make_decision(self, percepts):
            raise RuntimeError("fallo")
    AGENTES['roto'] = Roto
    try:
        df, errores = ejecutar_comparacion(['roto', 'caza'], inst, n=2)
    finally:
        del AGENTES['roto']
    assert 'roto' in errores and set(df['agente']) == {'caza'}


if __name__ == "__main__":
    pruebas = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    for f in pruebas:
        f()
        print("OK ", f.__name__)
    print(f"\n{len(pruebas)} pruebas superadas")
