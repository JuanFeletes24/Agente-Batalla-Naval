"""
Batalla Naval para una persona.

La computadora esconde la flota y tu intentas hundirla con la menor
cantidad de disparos posible.

Uso:
    python main.py              # version grafica: clic sobre el tablero
    python main.py --consola    # version de texto: escribes B5, C3, ...
    python main.py --semilla 7  # misma flota cada vez (para practicar)

Controles (version grafica):
    clic izquierdo -> disparar
    R              -> nueva partida
    V              -> rendirse y ver la flota
    Q              -> salir
"""

import argparse
import string

import matplotlib.pyplot as plt

from ambientes import BatallaNavalEnv, DESCONOCIDO, AGUA, TOCADO, HUNDIDO
from utils import coord_a_texto, texto_a_coord, mensaje_feedback, calificacion


def disparos_minimos(env) -> int:
    """Casillas ocupadas por la flota = minimo teorico de disparos."""
    return sum(b.longitud for b in env.barcos)


# ---------------------------------------------------------------------------
# VERSION GRAFICA
# ---------------------------------------------------------------------------

class JuegoGrafico:

    def __init__(self, filas=10, columnas=10, seed=None):
        self.env = BatallaNavalEnv(filas=filas, columnas=columnas, seed=seed)
        self.mensaje = "Haz clic en una casilla para disparar."
        self.revelado = False
        self.mejor = None  # mejor marca de la sesion

        self.fig, self.ax = plt.subplots(figsize=(7.5, 7))
        self.fig.canvas.manager.set_window_title("Batalla Naval")
        self.fig.canvas.mpl_connect('button_press_event', self.al_hacer_clic)
        self.fig.canvas.mpl_connect('key_press_event', self.al_presionar_tecla)
        self.dibujar()

    # -- dibujo -------------------------------------------------------------
    def dibujar(self):
        env = self.env
        env.render(ax=self.ax)

        # Etiquetas de juego: letras en columnas, numeros desde 1 en filas
        self.ax.set_xticks([i + 0.5 for i in range(env.columnas)])
        self.ax.set_xticklabels(list(string.ascii_uppercase[:env.columnas]))
        self.ax.set_yticks([i + 0.5 for i in range(env.filas)])
        self.ax.set_yticklabels([str(i + 1) for i in range(env.filas)])
        self.ax.xaxis.tick_top()

        # Si se rindio, marcar los barcos que no se descubrieron
        if self.revelado:
            for barco in env.barcos:
                for (r, c) in barco.posiciones:
                    if env.tablero_agente[r, c] == DESCONOCIDO:
                        self.ax.add_patch(plt.Rectangle(
                            (c, r), 1, 1, facecolor='#7F8C8D',
                            edgecolor='black', linewidth=1.2))

        vivos = [b.nombre for b in env.barcos if not b.esta_hundido()]
        hundidos = [b.nombre for b in env.barcos if b.esta_hundido()]
        self.ax.set_title(
            f"Disparos: {env.turnos}   |   Barcos restantes: {len(vivos)}/{len(env.barcos)}",
            fontsize=13, weight='bold', pad=30)
        self.ax.set_xlabel(self.mensaje, fontsize=12, weight='bold')

        pie = "Flota enemiga: " + ", ".join(
            f"{b.nombre}({b.longitud})" + (" ✔" if b.esta_hundido() else "")
            for b in env.barcos)
        self.fig.text(0.5, 0.015, pie + "    [R] nueva  [V] rendirse  [Q] salir",
                      ha='center', fontsize=8.5, color='#555555')
        self.fig.subplots_adjust(bottom=0.12)
        self.fig.canvas.draw_idle()
        # fig.text se acumularia entre redibujos: lo limpiamos tras pintar
        for t in self.fig.texts[:-1]:
            t.remove()

    # -- eventos ------------------------------------------------------------
    def al_hacer_clic(self, event):
        if event.inaxes != self.ax or event.button != 1:
            return
        if self.env.done or self.revelado:
            self.mensaje = "La partida termino. Pulsa R para jugar de nuevo."
            self.dibujar()
            return

        c, r = int(event.xdata), int(event.ydata)
        if not (0 <= r < self.env.filas and 0 <= c < self.env.columnas):
            return
        if (r, c) not in self.env.acciones_aplicables():
            self.mensaje = f"Ya disparaste en {coord_a_texto(r, c)}. Elige otra casilla."
            self.dibujar()
            return

        self.env.step((r, c))
        self.mensaje = mensaje_feedback(self.env.ultimo_feedback)

        if self.env.done:
            t = self.env.turnos
            rango = calificacion(t, disparos_minimos(self.env))
            if self.mejor is None or t < self.mejor:
                self.mejor = t
                extra = "  ¡Nuevo record!"
            else:
                extra = f"  (record: {self.mejor})"
            self.mensaje = f"¡VICTORIA en {t} disparos! Rango: {rango}.{extra}  [R] para otra"
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


def jugar_consola(filas=10, columnas=10, seed=None):
    env = BatallaNavalEnv(filas=filas, columnas=columnas, seed=seed)
    mejor = None
    print("=== BATALLA NAVAL ===")
    print("Escribe una casilla (ej. B5) para disparar. 'salir' para terminar.")

    while True:
        imprimir_tablero(env)
        vivos = [b.nombre for b in env.barcos if not b.esta_hundido()]
        print(f"Disparos: {env.turnos} | Quedan: {', '.join(vivos)}")

        entrada = input("Disparo > ").strip()
        if entrada.lower() in ('salir', 'q', 'exit'):
            print("¡Hasta la proxima!")
            return
        coord = texto_a_coord(entrada, env.filas, env.columnas)
        if coord is None:
            print(f"Coordenada invalida. Usa letra A-{string.ascii_uppercase[env.columnas-1]} "
                  f"y numero 1-{env.filas}, por ejemplo B5.")
            continue
        if coord not in env.acciones_aplicables():
            print("Ya disparaste ahi. Elige otra casilla.")
            continue

        env.step(coord)
        print(">>>", mensaje_feedback(env.ultimo_feedback))

        if env.done:
            imprimir_tablero(env)
            t = env.turnos
            print(f"\n¡VICTORIA en {t} disparos! Rango: {calificacion(t, disparos_minimos(env))}")
            if mejor is None or t < mejor:
                mejor = t
                print("¡Nuevo record de la sesion!")
            if input("¿Jugar otra vez? (s/n) > ").strip().lower() != 's':
                print("¡Hasta la proxima!")
                return
            env.reset()


# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Batalla Naval para una persona")
    parser.add_argument('--consola', action='store_true', help="jugar en modo texto")
    parser.add_argument('--semilla', type=int, default=None, help="semilla para la flota")
    args = parser.parse_args()

    if args.consola:
        jugar_consola(seed=args.semilla)
    else:
        JuegoGrafico(seed=args.semilla).jugar()


if __name__ == "__main__":
    main()
