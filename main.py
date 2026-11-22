"""
Batalla Naval para una persona (versiones matplotlib y consola).
Para la version con sprites usa juego_visual.py.

Uso:
    python main.py                         # grafica (clic), nivel medio
    python main.py --nivel experto         # facil | medio | dificil | experto
    python main.py --consola               # version de texto (escribes B5, C3, ...)
    python main.py --semilla 7             # misma flota cada vez (para practicar)

Controles (version grafica):
    clic izquierdo -> disparar   R -> nueva partida   V -> rendirse   Q -> salir
"""

import argparse
import string

import matplotlib.pyplot as plt

from ambientes import BatallaNavalEnv, DESCONOCIDO, AGUA, TOCADO, HUNDIDO
from dificultad import NIVELES, ORDEN_NIVELES
from utils import coord_a_texto, texto_a_coord, mensaje_feedback, calificacion


def estado_flota(env) -> str:
    """Texto sobre la flota respetando lo que el nivel permite mostrar."""
    obs = env.para_sentidos()
    if obs['barcos_vivos'] is None:
        return f"Quedan {obs['n_barcos_vivos']} de {len(env.barcos)} barcos"
    return "Quedan: " + ", ".join(obs['barcos_vivos'])


def texto_disparos(env) -> str:
    lim = env.config.max_disparos
    return f"{env.turnos}" if lim is None else f"{env.turnos}/{lim}"


# ---------------------------------------------------------------------------
# VERSION GRAFICA (matplotlib)
# ---------------------------------------------------------------------------

class JuegoGrafico:

    def __init__(self, config, seed=None):
        self.env = BatallaNavalEnv(config=config, seed=seed)
        self.ruido = config.prob_ruido > 0
        self.mensaje = "Haz clic en una casilla para disparar."
        self.revelado = False
        self.mejor = None

        self.fig, self.ax = plt.subplots(figsize=(7.5, 7))
        self.fig.canvas.manager.set_window_title(f"Batalla Naval - {config.nombre}")
        self.fig.canvas.mpl_connect('button_press_event', self.al_hacer_clic)
        self.fig.canvas.mpl_connect('key_press_event', self.al_presionar_tecla)
        self.dibujar()

    def dibujar(self):
        env = self.env
        env.render(ax=self.ax)

        self.ax.set_xticks([i + 0.5 for i in range(env.columnas)])
        self.ax.set_xticklabels(list(string.ascii_uppercase[:env.columnas]))
        self.ax.set_yticks([i + 0.5 for i in range(env.filas)])
        self.ax.set_yticklabels([str(i + 1) for i in range(env.filas)])
        self.ax.xaxis.tick_top()

        if self.revelado:
            for barco in env.barcos:
                for (r, c) in barco.posiciones:
                    if env.tablero_agente[r, c] == DESCONOCIDO:
                        self.ax.add_patch(plt.Rectangle(
                            (c, r), 1, 1, facecolor='#7F8C8D',
                            edgecolor='black', linewidth=1.2))

        self.ax.set_title(f"{env.config.nombre}  |  Disparos: {texto_disparos(env)}  |  "
                          f"{estado_flota(env)}", fontsize=11, weight='bold', pad=30)
        self.ax.set_xlabel(self.mensaje, fontsize=12, weight='bold')

        reglas = " · ".join(env.config.descripcion()[1:]) or "sin restricciones extra"
        self.fig.text(0.5, 0.015, f"{reglas}    [R] nueva  [V] rendirse  [Q] salir",
                      ha='center', fontsize=8.5, color='#555555')
        self.fig.subplots_adjust(bottom=0.12)
        self.fig.canvas.draw_idle()
        for t in self.fig.texts[:-1]:
            t.remove()

    def al_hacer_clic(self, event):
        env = self.env
        if event.inaxes != self.ax or event.button != 1:
            return
        if env.done or self.revelado:
            self.mensaje = "La partida termino. Pulsa R para jugar de nuevo."
            self.dibujar()
            return

        c, r = int(event.xdata), int(event.ydata)
        if not (0 <= r < env.filas and 0 <= c < env.columnas):
            return
        if env.tablero_agente[r][c] != DESCONOCIDO:
            self.mensaje = f"Ya disparaste en {coord_a_texto(r, c)}. Elige otra casilla."
            self.dibujar()
            return

        env.step((r, c))
        self.mensaje = mensaje_feedback(env.ultimo_feedback, self.ruido)

        if env.ganado:
            t = env.turnos
            rango = calificacion(t, env.config.casillas_barco)
            if self.mejor is None or t < self.mejor:
                self.mejor, extra = t, "¡Nuevo record!"
            else:
                extra = f"(record: {self.mejor})"
            self.mensaje = f"¡VICTORIA en {t} disparos! Rango: {rango}. {extra}  [R] para otra"
        elif env.agotado:
            self.revelado = True
            self.mensaje = "¡Sin disparos! DERROTA. Esta era la flota.  [R] para otra"
        self.dibujar()

    def al_presionar_tecla(self, event):
        if event.key in ('r', 'R'):
            self.env.reset()
            self.revelado = False
            self.mensaje = "Nueva partida. ¡Dispara!"
            self.dibujar()
        elif event.key in ('v', 'V') and not self.env.done:
            self.revelado = True
            self.mensaje = "Te rendiste. Esta era la flota. [R] para jugar de nuevo"
            self.dibujar()
        elif event.key in ('q', 'Q'):
            plt.close(self.fig)

    def jugar(self):
        plt.show()


# ---------------------------------------------------------------------------
# VERSION CONSOLA
# ---------------------------------------------------------------------------

SIMBOLOS = {DESCONOCIDO: '·', AGUA: 'o', TOCADO: 'X', HUNDIDO: '#'}


def imprimir_tablero(env):
    letras = string.ascii_uppercase[:env.columnas]
    print("\n     " + " ".join(letras))
    for r in range(env.filas):
        fila = " ".join(SIMBOLOS[v] for v in env.tablero_agente[r])
        print(f"  {r + 1:>2} {fila}")
    print("\n  · desconocido   o agua   X tocado   # hundido")


def jugar_consola(config, seed=None):
    env = BatallaNavalEnv(config=config, seed=seed)
    ruido = config.prob_ruido > 0
    mejor = None
    print(f"=== BATALLA NAVAL - Nivel {config.nombre} ===")
    for linea in config.descripcion():
        print("  -", linea)
    print("Escribe una casilla (ej. B5) para disparar. 'salir' para terminar.")

    while True:
        imprimir_tablero(env)
        print(f"Disparos: {texto_disparos(env)} | {estado_flota(env)}")

        entrada = input("Disparo > ").strip()
        if entrada.lower() in ('salir', 'q', 'exit'):
            print("¡Hasta la proxima!")
            return
        coord = texto_a_coord(entrada, env.filas, env.columnas)
        if coord is None:
            print(f"Coordenada invalida. Usa letra A-{string.ascii_uppercase[env.columnas-1]} "
                  f"y numero 1-{env.filas}, por ejemplo B5.")
            continue
        if env.tablero_agente[coord] != DESCONOCIDO:
            print("Ya disparaste ahi. Elige otra casilla.")
            continue

        env.step(coord)
        print(">>>", mensaje_feedback(env.ultimo_feedback, ruido))

        if env.done:
            imprimir_tablero(env)
            if env.ganado:
                t = env.turnos
                print(f"\n¡VICTORIA en {t} disparos! Rango: {calificacion(t, config.casillas_barco)}")
                if mejor is None or t < mejor:
                    mejor = t
                    print("¡Nuevo record de la sesion!")
            else:
                print("\n¡Te quedaste sin disparos! DERROTA.")
            if input("¿Jugar otra vez? (s/n) > ").strip().lower() != 's':
                print("¡Hasta la proxima!")
                return
            env.reset()


# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Batalla Naval para una persona")
    parser.add_argument('--consola', action='store_true', help="jugar en modo texto")
    parser.add_argument('--nivel', default='medio', choices=ORDEN_NIVELES)
    parser.add_argument('--semilla', type=int, default=None, help="semilla para la flota")
    args = parser.parse_args()
    config = NIVELES[args.nivel]

    if args.consola:
        jugar_consola(config, seed=args.semilla)
    else:
        JuegoGrafico(config, seed=args.semilla).jugar()


if __name__ == "__main__":
    main()
