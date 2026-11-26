"""
Una partida jugada por un agente, que se puede avanzar, retroceder y revisar. Sin interfaz.

    s = SesionAgente('caza', 'medio', seed=1000)
    s.paso()          # avanza: ejecuta una jugada nueva del agente, o reproduce una ya hecha
    s.atras()         # retrocede una jugada (solo cambia lo que se VE; no borra el historial)
    s.env_vista()     # entorno en la posicion que se esta viendo (para dibujar)
    s.historial       # lista de jugadas con feedback, tiempo y estado interno del agente

Retroceder es exacto porque el entorno es determinista: con la misma semilla y las mismas
acciones se reconstruye cualquier momento de la partida, sin guardar el estado del agente.

Con la misma semilla, cualquier agente enfrenta la misma flota (y el mismo ruido del sonar):
asi se comparan agentes sobre exactamente la misma partida. Las semillas de evaluar.py
empiezan en 1000: usar 1000, 1001... reproduce esas partidas.
"""

import time

import numpy as np

from agents import AGENTES
from ambientes import BatallaNavalEnv
from instancia import Instancia
from utils import mensaje_feedback


class SesionAgente:

    def __init__(self, clave_agente: str, nivel: str, seed: int, instancia: Instancia = None):
        """
        'nivel' es la clave de un nivel predefinido. Con 'instancia' (p. ej. creada en el
        editor, con la flota colocada a mano) se usa esa en lugar del nivel.
        """
        self.seed = seed
        self.instancia = instancia if instancia is not None else Instancia.de_nivel(nivel)
        self.config = self.instancia.config
        self.env = self.instancia.crear_env(seed)                     # entorno "en vivo"
        self.agente = AGENTES[clave_agente](config=self.config)
        self.agente.restart(seed=seed)                   # puede lanzar FileNotFoundError (DQN sin modelo)
        self.obs = self.env.para_sentidos()
        self.historial = []                               # un dict por jugada
        self.posicion = 0                                 # cuantas jugadas se estan "viendo"
        self._env_pasado = None                           # entorno reconstruido para revisar
        self._pos_pasado = -1

    # -- estado ---------------------------------------------------------------
    @property
    def nombre_agente(self) -> str:
        return self.agente.name

    @property
    def en_vivo(self) -> bool:
        """True si se esta viendo la ultima jugada (no una anterior)."""
        return self.posicion == len(self.historial)

    @property
    def terminada(self) -> bool:
        """True si la partida real ya termino (ganada o sin disparos)."""
        return self.env.done

    @property
    def al_final(self) -> bool:
        return self.en_vivo and self.terminada

    # -- avanzar / retroceder -------------------------------------------------
    def paso(self):
        """
        Avanza una jugada. Si se estaba revisando el pasado, reproduce la siguiente jugada ya
        hecha; si se esta al dia, ejecuta una nueva del agente. Devuelve el registro de la
        jugada, o None si no hay nada mas que jugar.
        """
        if not self.en_vivo:
            self.posicion += 1
            return self.historial[self.posicion - 1]
        if self.terminada:
            return None

        t0 = time.perf_counter()
        c0 = time.process_time()
        accion = self.agente.make_decision(self.obs)
        cpu_ms = 1000 * (time.process_time() - c0)
        ms = 1000 * (time.perf_counter() - t0)          # el estado interno NO se cuenta en el tiempo
        interno = self._copiar_interno(self.agente.estado_interno())
        accion = tuple(int(v) for v in accion)
        self.obs, _, _, info = self.env.step(accion)
        fb = dict(self.env.ultimo_feedback)
        self.historial.append({'turno': self.env.turnos, 'coord': accion, 'resultado': fb['resultado'],
                               'real': info['resultado_real'], 'ms': ms, 'feedback': fb,
                               'interno': interno,
                               'cpu_ms': cpu_ms})
        self.posicion = len(self.historial)
        return self.historial[-1]

    def atras(self) -> bool:
        """Retrocede una jugada. Devuelve False si ya estaba en el inicio."""
        if self.posicion == 0:
            return False
        self.posicion -= 1
        return True

    @staticmethod
    def _copiar_interno(interno: dict) -> dict:
        copia = dict(interno or {})
        if copia.get('mapa') is not None:
            copia['mapa'] = np.array(copia['mapa'], dtype=float)
        return copia

    # -- que mostrar ----------------------------------------------------------
    def env_vista(self) -> BatallaNavalEnv:
        """Entorno tal como estaba tras 'posicion' jugadas (el vivo, si se esta al dia)."""
        if self.en_vivo:
            return self.env
        if self._env_pasado is None or self._pos_pasado > self.posicion:
            self._env_pasado = self.instancia.crear_env(self.seed)
            self._pos_pasado = 0
        while self._pos_pasado < self.posicion:            # avanza incrementalmente
            self._env_pasado.step(self.historial[self._pos_pasado]['coord'])
            self._pos_pasado += 1
        return self._env_pasado

    def jugadas_vistas(self) -> list:
        return self.historial[:self.posicion]

    def ultima_vista(self):
        return self.historial[self.posicion - 1] if self.posicion else None

    def orden(self) -> dict:
        """{(fila, col): numero de jugada} para numerar el tablero."""
        return {r['coord']: r['turno'] for r in self.jugadas_vistas()}

    def mensaje(self) -> tuple:
        """(texto, tono) de la jugada que se esta viendo o del resultado final."""
        if self.al_final:
            env = self.env
            if env.ganado:
                return (f"{self.nombre_agente} ganó en {env.turnos} disparos "
                        f"(eficiencia {self.config.casillas_barco / env.turnos:.2f})", 'victoria')
            hundidos = len(env.barcos) - self.obs['n_barcos_vivos']
            return (f"{self.nombre_agente} perdió: se acabaron los disparos "
                    f"({hundidos} de {len(env.barcos)} barcos hundidos)", 'derrota')
        ult = self.ultima_vista()
        if ult is None:
            return (f"{self.nombre_agente}: pulsa «Paso» o «Reproducir» para empezar", 'normal')
        texto = f"Jugada {ult['turno']}: " + mensaje_feedback(ult['feedback'], self.config.prob_ruido > 0)
        if not self.en_vivo:
            texto += "   (revisando)"
        return texto, ult['resultado']

    def resumen_markdown(self) -> str:
        """Panel de datos de la jugada que se esta viendo, incluido el estado interno del agente."""
        env, cfg = self.env_vista(), self.config
        h = self.jugadas_vistas()
        lim = cfg.max_disparos
        n = lambda r: sum(1 for x in h if x['resultado'] == r)
        ms = [x['ms'] for x in h]
        lineas = [f"### {self.nombre_agente} · nivel {cfg.nombre}",
                  f"**Semilla:** {self.seed}", "",
                  f"**Disparos:** {len(h)}" + (f" / {lim}" if lim else "") + f" · **Recompensa:** {-len(h)}", "",
                  f"Agua: {n('agua')} · Impactos: {n('impacto')} · Hundidos: {n('hundido')}", ""]
        if ms:
            lineas += [f"**Tiempo por jugada:** última {ms[-1]:.2f} ms · media {sum(ms)/len(ms):.2f} ms", ""]
        vivos = [b for b in env.barcos if not b.esta_hundido()]
        if cfg.mostrar_flota_restante:
            lineas.append("**Flota:** " + ", ".join(
                f"{b.nombre}{' ✅' if b.esta_hundido() else ''}" for b in env.barcos))
        else:
            lineas.append(f"**Barcos restantes:** {len(vivos)} de {len(env.barcos)}")

        ult = self.ultima_vista()
        if ult and ult['interno']:
            i = ult['interno']
            lineas += ["", "#### Estado interno del agente (en esta jugada)"]
            gen = sum(x['interno'].get('nodos_generados', 0) for x in h if x['interno'])
            exp = sum(x['interno'].get('nodos_expandidos', 0) for x in h if x['interno'])
            lineas.append(f"- Nodos generados / expandidos (acum.): {gen} / {exp}")
            if i.get('tipo_mapa'):
                lineas.append(f"- Mapa: {i['tipo_mapa']}")
            for k, v in (i.get('info') or {}).items():
                lineas.append(f"- {k}: {v}")
            evals = sum(x['interno'].get('evaluaciones', 0) for x in h if x['interno'])
            mems = [x['interno'].get('memoria') for x in h if x['interno'].get('memoria') is not None]
            lineas.append(f"- Evaluaciones acumuladas: {evals}")
            if mems:
                lineas.append(f"- Memoria aproximada (máx.): {max(mems)}")
        return "\n".join(lineas)
