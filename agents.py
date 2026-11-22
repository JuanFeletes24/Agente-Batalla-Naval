"""
Agentes para Batalla Naval.

Todos los agentes siguen la misma interfaz y SOLO ven la observacion que entrega
env.para_sentidos() / env.step() (nunca el tablero oculto):

    agente.restart(seed)                  # al empezar cada partida
    accion = agente.make_decision(percepts)   # devuelve (fila, columna)
"""

import numpy as np
from ambientes import DESCONOCIDO, TOCADO


class Agente:
    def __init__(self, name: str = "Agent", seed: int = None):
        self.name = name
        self.rng = np.random.default_rng(seed)
        self.action = []   # historial opcional, lo llenan las subclases que lo necesiten
        self.states = []

    def restart(self, seed: int = None):
        """Llamado al inicio de cada partida. Con 'seed' la partida es reproducible."""
        self.action = []
        self.states = []
        if seed is not None:
            self.rng = np.random.default_rng(seed)

    def make_decision(self, percepts: dict) -> tuple:
        raise NotImplementedError("Este método debe ser implementado por la clase hija")

    @staticmethod
    def casillas_libres(tablero) -> list:
        return [tuple(int(v) for v in rc) for rc in np.argwhere(tablero == DESCONOCIDO)]


class RandomAgent(Agente):
    """Dispara a una casilla desconocida al azar. Es el piso de la comparacion."""

    def __init__(self, seed: int = None):
        super().__init__(name="RandomAgent", seed=seed)

    def make_decision(self, percepts: dict) -> tuple:
        libres = self.casillas_libres(percepts['tablero_agente'])
        return libres[int(self.rng.integers(len(libres)))]


class AgenteCazaRemate(Agente):
    """
    Heuristica clasica "hunt & target":
      - Caza: dispara en patron de tablero de ajedrez (todo barco mide >= 2).
      - Remate: tras un impacto, dispara a las casillas vecinas, prefiriendo
        continuar la linea cuando ya hay dos impactos alineados.
    """

    def __init__(self, seed: int = None):
        super().__init__(name="Caza-Remate", seed=seed)

    def make_decision(self, percepts: dict) -> tuple:
        t = percepts['tablero_agente']
        objetivo = self._remate(t)
        if objetivo is not None:
            return objetivo
        libres = self.casillas_libres(t)
        paridad = [rc for rc in libres if (rc[0] + rc[1]) % 2 == 0]
        pool = paridad if paridad else libres
        return pool[int(self.rng.integers(len(pool)))]

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
            return None
        mejor = max(puntaje.values())
        candidatos = [rc for rc, p in puntaje.items() if p == mejor]
        return candidatos[int(self.rng.integers(len(candidatos)))]


AGENTES = {
    'aleatorio': RandomAgent,
    'caza': AgenteCazaRemate,
}