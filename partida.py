"""
Estado y reglas de una partida para una persona, sin ninguna dependencia de interfaz.
Lo usa app_qt.py (y se puede reutilizar desde cualquier otra interfaz).
"""

from ambientes import BatallaNavalEnv, DESCONOCIDO
from dificultad import NIVELES
from utils import coord_a_texto, mensaje_feedback, calificacion

MENSAJE_INICIAL = "Haz clic en una casilla del tablero para disparar."


class Partida:

    def __init__(self, nivel: str = 'medio', seed: int = None):
        self.mejores = {}            # mejor marca (menos disparos) por nivel, de esta sesion
        self.nivel = nivel
        self.nuevo_nivel(nivel, seed)

    # -- ciclo de vida -------------------------------------------------------
    def nuevo_nivel(self, nivel: str, seed: int = None):
        self.nivel = nivel
        self.config = NIVELES[nivel]
        self.env = BatallaNavalEnv(config=self.config, seed=seed)
        self._limpiar(MENSAJE_INICIAL)

    def nueva(self):
        self.env.reset()
        self._limpiar("Nueva partida. ¡Dispara!")

    def _limpiar(self, mensaje: str):
        self.revelado = False
        self.ultimo = None           # feedback del ultimo disparo (para resaltarlo)
        self.mensaje = mensaje
        self.tono = 'normal'         # normal | agua | impacto | hundido | victoria | derrota | aviso

    # -- estado --------------------------------------------------------------
    @property
    def terminada(self) -> bool:
        return self.env.done or self.revelado

    @property
    def ruido(self) -> bool:
        return self.config.prob_ruido > 0

    # -- acciones ------------------------------------------------------------
    def rendirse(self):
        if not self.terminada:
            self.revelado = True
            self.tono = 'aviso'
            self.mensaje = "Te rendiste. Esta era la flota. Pulsa «Nueva partida» para jugar de nuevo."

    def disparar(self, r: int, c: int):
        env = self.env
        if self.terminada:
            self.mensaje = "La partida terminó. Pulsa «Nueva partida» para jugar de nuevo."
            self.tono = 'aviso'
            return
        if env.tablero_agente[r][c] != DESCONOCIDO:
            self.mensaje = f"Ya disparaste en {coord_a_texto(r, c)}. Elige otra casilla."
            self.tono = 'aviso'
            return

        env.step((r, c))
        self.ultimo = env.ultimo_feedback
        self.mensaje = mensaje_feedback(self.ultimo, self.ruido)
        self.tono = self.ultimo['resultado']

        if env.ganado:
            t = env.turnos
            rango = calificacion(t, self.config.casillas_barco)
            mejor = self.mejores.get(self.nivel)
            if mejor is None or t < mejor:
                self.mejores[self.nivel] = t
                extra = "¡Nuevo récord!"
            else:
                extra = f"Récord: {mejor}"
            self.mensaje = f"¡VICTORIA en {t} disparos! Rango: {rango}. {extra}"
            self.tono = 'victoria'
        elif env.agotado:
            self.revelado = True
            self.tono = 'derrota'
            hundidos = len(env.barcos) - env.para_sentidos()['n_barcos_vivos']
            self.mensaje = (f"¡Sin disparos! DERROTA: hundiste {hundidos} de {len(env.barcos)} barcos. "
                            f"Esta era la flota.")

    # -- texto para el panel -------------------------------------------------
    def panel_markdown(self) -> str:
        env, cfg = self.env, self.config
        lim = cfg.max_disparos
        disparos = f"{env.turnos}" if lim is None else f"{env.turnos} / {lim}"
        obs = env.para_sentidos()
        lineas = [f"### Nivel {cfg.nombre}",
                  *[f"- {l}" for l in cfg.descripcion()],
                  "",
                  f"**Disparos:** {disparos}",
                  "",
                  f"**Récord en este nivel:** {self.mejores.get(self.nivel, '–')}",
                  ""]
        if obs['barcos_vivos'] is None:
            lineas.append(f"**Barcos restantes:** {obs['n_barcos_vivos']} de {len(env.barcos)} "
                          "(no se sabe cuáles)")
        else:
            lineas.append("**Flota enemiga**")
            lineas.append("")
            for b in env.barcos:
                marca = "✅ hundido" if b.esta_hundido() else f"{b.impactos}/{b.longitud} tocado"
                lineas.append(f"- {b.nombre} ({b.longitud}): {marca}")
        return "\n".join(lineas)
