"""
Agentes para Batalla Naval.

Todos los agentes siguen la misma interfaz y SOLO ven la observacion que entrega
env.para_sentidos() / env.step() (nunca el tablero oculto):

    agente.restart(seed)                      # al empezar cada partida
    accion = agente.make_decision(percepts)   # devuelve (fila, columna)

Los agentes de Monte Carlo, red bayesiana y DQN deben heredar de `Agente` para
poder evaluarse con evaluar.py bajo las mismas condiciones. Todos se construyen con
`clase(seed=None, config=None)`: `config` es el ConfigDificultad del nivel que van a
jugar (lo necesitan los agentes que dependen del nivel, como el DQN; los demas lo ignoran).

ESTADO INTERNO (opcional, para visualizar y medir)
Despues de cada `make_decision`, la interfaz llama a `agente.estado_interno()`, que describe
la decision que se acaba de tomar. Devuelve un dict con estas claves (todas opcionales):

    'mapa'         ndarray (filas, cols) con un valor por casilla: probabilidad de barco,
                   valor Q, puntaje... Usar NaN en las casillas que no son candidatas.
    'tipo_mapa'    texto corto que dice que es el mapa ('probabilidad', 'valor Q', ...)
    'info'         dict {nombre: valor} con contadores legibles (modo, muestras, ...)
    'evaluaciones' int: cuanto "trabajo" hizo para decidir (casillas puntuadas, muestras de
                   Monte Carlo, configuraciones evaluadas...). Es el equivalente a los
                   "nodos generados" de una busqueda.
    'memoria'      int: tamano aproximado de su estructura principal (en elementos o bytes)

Para no alterar la medicion del tiempo por jugada, `make_decision` solo guarda lo
necesario y `estado_interno` construye el mapa bajo demanda.
"""

import numpy as np

from ambientes import DESCONOCIDO, TOCADO


class Agente:
    def __init__(self, name: str = "Agent", seed: int = None, config=None):
        self.name = name
        self.config = config
        self.rng = np.random.default_rng(seed)

    def restart(self, seed: int = None):
        """Llamado al inicio de cada partida. Con 'seed' la partida es reproducible."""
        if seed is not None:
            self.rng = np.random.default_rng(seed)

    def make_decision(self, percepts: dict) -> tuple:
        raise NotImplementedError("Este método debe ser implementado por la clase hija")

    def estado_interno(self) -> dict:
        """Describe la ULTIMA decision (ver el docstring del modulo). Por defecto, nada."""
        return {}

    @staticmethod
    def casillas_libres(tablero) -> list:
        return [tuple(int(v) for v in rc) for rc in np.argwhere(tablero == DESCONOCIDO)]


class RandomAgent(Agente):
    """Dispara a una casilla desconocida al azar. Es el piso de la comparacion."""

    def __init__(self, seed: int = None, config=None):
        super().__init__(name="RandomAgent", seed=seed, config=config)

    def make_decision(self, percepts: dict) -> tuple:
        self._tablero = percepts['tablero_agente']
        libres = self.casillas_libres(self._tablero)
        self._n = len(libres)
        return libres[int(self.rng.integers(self._n))]

    def estado_interno(self) -> dict:
        mapa = np.where(self._tablero == DESCONOCIDO, 1.0 / self._n, np.nan)
        return {'mapa': mapa, 'tipo_mapa': 'probabilidad uniforme',
                'info': {'casillas libres': self._n}, 'evaluaciones': 0, 'memoria': 0}


class AgenteCazaRemate(Agente):
    """
    Heuristica clasica "hunt & target":
      - Caza: dispara en patron de tablero de ajedrez (todo barco mide >= 2).
      - Remate: tras un impacto, dispara a las casillas vecinas, prefiriendo
        continuar la linea cuando ya hay dos impactos alineados.
    """

    def __init__(self, seed: int = None, config=None):
        super().__init__(name="Caza-Remate", seed=seed, config=config)

    def make_decision(self, percepts: dict) -> tuple:
        t = percepts['tablero_agente']
        objetivo, puntaje = self._remate(t)
        if objetivo is not None:
            self._ult = {'modo': 'remate', 'celdas': puntaje, 'tablero': t}
            return objetivo
        libres = self.casillas_libres(t)
        paridad = [rc for rc in libres if (rc[0] + rc[1]) % 2 == 0]
        pool = paridad if paridad else libres
        self._ult = {'modo': 'caza', 'celdas': {rc: 1.0 for rc in pool}, 'tablero': t}
        return pool[int(self.rng.integers(len(pool)))]

    def estado_interno(self) -> dict:
        u = self._ult
        mapa = np.full(u['tablero'].shape, np.nan)
        for (r, c), v in u['celdas'].items():
            mapa[r, c] = v
        tipo = 'puntaje de remate' if u['modo'] == 'remate' else 'casillas de la caza (ajedrez)'
        return {'mapa': mapa, 'tipo_mapa': tipo,
                'info': {'modo': u['modo'], 'candidatas': len(u['celdas'])},
                'evaluaciones': len(u['celdas']), 'memoria': len(u['celdas'])}

    def _remate(self, t):
        filas, cols = t.shape
        puntaje = {}
        for r, c in np.argwhere(t == TOCADO):
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                rr, cc = r + dr, c + dc
                if not (0 <= rr < filas and 0 <= cc < cols) or t[rr][cc] != DESCONOCIDO:
                    continue
                # bonus si la casilla opuesta tambien es un impacto (linea de 2+)
                pr, pc = r - dr, c - dc
                alineado = 0 <= pr < filas and 0 <= pc < cols and t[pr][pc] == TOCADO
                puntaje[(rr, cc)] = puntaje.get((rr, cc), 0) + (3 if alineado else 1)
        if not puntaje:
            return None, None
        mejor = max(puntaje.values())
        candidatos = [rc for rc, p in puntaje.items() if p == mejor]
        return candidatos[int(self.rng.integers(len(candidatos)))], puntaje


AGENTES = {
    'aleatorio': RandomAgent,
    'caza': AgenteCazaRemate,
}


def _registrar_dqn():
    """El agente DQN solo aparece si PyTorch esta instalado y hay algun modelo entrenado."""
    try:
        from dqn_agent import AgenteDQN, modelos_disponibles
    except ImportError:
        return
    if modelos_disponibles():
        AGENTES['dqn'] = AgenteDQN


_registrar_dqn()
