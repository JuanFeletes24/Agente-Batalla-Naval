"""
Batalla Naval para una persona - version visual con pygame.

Usa el motor de ambientes.py (BatallaNavalEnv) para toda la logica y este
archivo solo se encarga de dibujar: fondo de agua, barcos por secciones,
estela animada, explosiones y salpicaduras.

Uso:
    python juego_visual.py
    python juego_visual.py --semilla 7

Controles:
    clic izquierdo -> disparar
    R              -> nueva partida
    V              -> rendirse y ver la flota
    ESC            -> salir
"""

import argparse
import os
import string
import sys

import pygame

from ambientes import BatallaNavalEnv, DESCONOCIDO, AGUA, TOCADO, HUNDIDO
from utils import coord_a_texto, mensaje_feedback, calificacion

# ---------------------------------------------------------------------------
# CONFIGURACION
# ---------------------------------------------------------------------------

FILAS = 10
COLUMNAS = 10
TILE = 64                     # lado de cada casilla en pixeles
MARGEN = 36                   # espacio para las letras/numeros de coordenadas
PANEL_W = 260                 # panel lateral
BARRA_H = 64                  # barra de mensajes inferior
FPS = 60

TABLERO_W = COLUMNAS * TILE
TABLERO_H = FILAS * TILE
OX, OY = MARGEN, MARGEN       # esquina superior izquierda del tablero
ANCHO = MARGEN + TABLERO_W + 16 + PANEL_W
ALTO = MARGEN + TABLERO_H + BARRA_H

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

# Colores
C_PANEL = (14, 33, 48)
C_PANEL_BORDE = (40, 78, 104)
C_TEXTO = (232, 240, 245)
C_TEXTO_SUAVE = (130, 160, 178)
C_AGUA = (140, 210, 255)
C_IMPACTO = (255, 170, 60)
C_HUNDIDO = (255, 90, 80)
C_VICTORIA = (110, 230, 140)
C_GRID = (255, 255, 255, 55)

# Que sprite usa cada barco y que tamano de estela. Cambialo a tu gusto.
# (cuerpo sano, cuerpo destruido, tamano de estela)
SPRITES_BARCO = {
    'Portaaviones': ("ship_large_body", "ship_large_body_destroyed", "big"),
    'Acorazado':    ("ship_medium_body_b", "ship_medium_body_b_destroyed", "big"),
    'Crucero':      ("ship_medium_body", "ship_medium_body_destroyed", "medium"),
    'Submarino':    ("ship_small_b_body", "ship_small_body_b_destroyed", "medium"),
    'Destructor':   ("ship_small_body", "ship_small_body_destroyed", "small"),
}
SPRITE_POR_DEFECTO = ("ship_small_body", "ship_small_body_destroyed", "small")


# ---------------------------------------------------------------------------
# CARGA DE IMAGENES
# ---------------------------------------------------------------------------

def _img(nombre):
    return pygame.image.load(os.path.join(ASSETS, nombre)).convert_alpha()


def cargar_fondo_cuadrado(ruta, ancho, alto):
    """Escala el fondo vertical proporcionalmente y recorta el area necesaria."""
    img = pygame.image.load(ruta).convert()
    w, h = img.get_size()
    factor = max(ancho / w, alto / h)
    img = pygame.transform.smoothscale(img, (int(w * factor), int(h * factor)))
    return img.subsurface(pygame.Rect(0, 0, ancho, alto)).copy()


def cargar_explosion(filas_frames=1, ancho_frame=32):
    """La hoja es de 192x32: 6 cuadros de 32x32."""
    hoja = _img("explosion.png")
    n = hoja.get_width() // ancho_frame
    frames = []
    for i in range(n):
        f = hoja.subsurface(pygame.Rect(i * ancho_frame, 0, ancho_frame, hoja.get_height())).copy()
        frames.append(pygame.transform.scale(f, (TILE, TILE)))
    return frames


def cortar_barco(nombre_archivo, n, horizontal):
    """Escala el barco a 1 x n casillas y lo divide en n secciones."""
    img = _img(nombre_archivo + ".png")
    if img.get_width() > img.get_height():
        img = pygame.transform.rotate(img, 90)
    img = pygame.transform.scale(img, (TILE, TILE * n))
    if horizontal:
        img = pygame.transform.rotate(img, 90)  # la proa queda a la izquierda
        return [img.subsurface(pygame.Rect(i * TILE, 0, TILE, TILE)).copy() for i in range(n)]
    return [img.subsurface(pygame.Rect(0, i * TILE, TILE, TILE)).copy() for i in range(n)]


def cargar_estela(tamano, n, horizontal):
    """Carga los 5 cuadros de la estela, un poco mas grandes que el barco."""
    ancho = int(TILE * 1.25)
    alto = int(TILE * n * 1.15)
    frames = []
    for i in range(5):
        f = _img(f"water_ripple_{tamano}_00{i}.png")
        f = pygame.transform.scale(f, (ancho, alto))
        if horizontal:
            f = pygame.transform.rotate(f, 90)
        frames.append(f)
    return frames


# ---------------------------------------------------------------------------
# ELEMENTOS VISUALES
# ---------------------------------------------------------------------------

class VistaBarco:
    """Representacion grafica de un Barco del entorno."""

    def __init__(self, barco):
        self.barco = barco
        self.casillas = list(barco.posiciones)
        n = len(self.casillas)
        self.horizontal = n > 1 and self.casillas[0][0] == self.casillas[1][0]

        sano, destruido, tam_estela = SPRITES_BARCO.get(barco.nombre, SPRITE_POR_DEFECTO)
        self.sprites_sanos = cortar_barco(sano, n, self.horizontal)
        self.sprites_danados = cortar_barco(destruido, n, self.horizontal)
        self.frames_estela = cargar_estela(tam_estela, n, self.horizontal)

        # rectangulo (en pixeles de pantalla) que ocupa todo el barco
        r0, c0 = self.casillas[0]
        w = TILE * n if self.horizontal else TILE
        h = TILE if self.horizontal else TILE * n
        self.rect = pygame.Rect(OX + c0 * TILE, OY + r0 * TILE, w, h)

    def dibujar(self, pantalla, tablero_agente, revelado, ahora):
        hundido = self.barco.esta_hundido()

        # 1) estela animada, solo cuando se muestra la flota entera (rendicion)
        if revelado and not hundido:
            idx = (ahora // 140) % len(self.frames_estela)
            frame = self.frames_estela[idx]
            pantalla.blit(frame, frame.get_rect(center=self.rect.center))

        # 2) secciones del barco
        for i, (r, c) in enumerate(self.casillas):
            golpeada = tablero_agente[r][c] in (TOCADO, HUNDIDO)
            if not golpeada and not revelado:
                continue  # sigue oculta bajo el agua
            sprite = self.sprites_danados[i] if golpeada else self.sprites_sanos[i]
            pantalla.blit(sprite, (OX + c * TILE, OY + r * TILE))


class ExplosionAnimada:
    def __init__(self, fila, col, frames, retraso=0):
        self.x = OX + col * TILE
        self.y = OY + fila * TILE
        self.frames = frames
        self.indice = 0
        self.inicio = pygame.time.get_ticks() + retraso
        self.terminada = False

    def actualizar(self, ahora):
        if ahora < self.inicio:
            return
        self.indice = (ahora - self.inicio) // 80
        if self.indice >= len(self.frames):
            self.terminada = True

    def dibujar(self, pantalla, ahora):
        if ahora >= self.inicio and not self.terminada:
            pantalla.blit(self.frames[self.indice], (self.x, self.y))


class SalpicaduraAnimada:
    """Anillo que se expande y se desvanece cuando un disparo cae al agua."""
    DURACION = 500

    def __init__(self, fila, col):
        self.centro = (OX + col * TILE + TILE // 2, OY + fila * TILE + TILE // 2)
        self.inicio = pygame.time.get_ticks()
        self.terminada = False
        self.surf = pygame.Surface((TILE * 2, TILE * 2), pygame.SRCALPHA)

    def actualizar(self, ahora):
        if ahora - self.inicio >= self.DURACION:
            self.terminada = True

    def dibujar(self, pantalla, ahora):
        t = min(1.0, (ahora - self.inicio) / self.DURACION)
        radio = int(8 + t * (TILE * 0.55))
        alpha = int(220 * (1 - t))
        self.surf.fill((0, 0, 0, 0))
        pygame.draw.circle(self.surf, (255, 255, 255, alpha),
                           (TILE, TILE), radio, max(1, int(5 * (1 - t)) + 1))
        pantalla.blit(self.surf, (self.centro[0] - TILE, self.centro[1] - TILE))


# ---------------------------------------------------------------------------
# JUEGO
# ---------------------------------------------------------------------------

class JuegoVisual:

    def __init__(self, seed=None):
        pygame.init()
        self.pantalla = pygame.display.set_mode((ANCHO, ALTO))
        pygame.display.set_caption("Batalla Naval")
        self.reloj = pygame.time.Clock()

        self.fuente_titulo = pygame.font.SysFont("segoeui,arial,helvetica,dejavusans", 24, bold=True)
        self.fuente_msg = pygame.font.SysFont("segoeui,arial,helvetica,dejavusans", 26, bold=True)
        self.fuente = pygame.font.SysFont("segoeui,arial,helvetica,dejavusans", 19)
        self.fuente_peq = pygame.font.SysFont("segoeui,arial,helvetica,dejavusans", 15)
        self.fuente_grande = pygame.font.SysFont("segoeui,arial,helvetica,dejavusans", 54, bold=True)

        # assets que no dependen de la partida
        self.fondo = cargar_fondo_cuadrado(os.path.join(ASSETS, "fondo.jpg"), TABLERO_W, TABLERO_H)
        self.frames_explosion = cargar_explosion()
        self.grid = pygame.Surface((TABLERO_W, TABLERO_H), pygame.SRCALPHA)
        for i in range(1, COLUMNAS):
            pygame.draw.line(self.grid, C_GRID, (i * TILE, 0), (i * TILE, TABLERO_H), 2)
        for i in range(1, FILAS):
            pygame.draw.line(self.grid, C_GRID, (0, i * TILE), (TABLERO_W, i * TILE), 2)
        self.velo = pygame.Surface((TABLERO_W, TABLERO_H), pygame.SRCALPHA)
        self.velo.fill((5, 15, 25, 170))

        self.env = BatallaNavalEnv(filas=FILAS, columnas=COLUMNAS, seed=seed)
        self.mejor = None
        self._preparar_partida()

    # -- estado de la partida ------------------------------------------------
    def _preparar_partida(self, mensaje="Haz clic en una casilla para disparar."):
        self.vistas = [VistaBarco(b) for b in self.env.barcos]
        self.efectos = []            # explosiones y salpicaduras activas
        self.revelado = False
        self.mensaje = mensaje
        self.color_msg = C_TEXTO
        self.resumen = ""            # texto de la pantalla de victoria

    def nueva_partida(self):
        self.env.reset()
        self._preparar_partida("Nueva partida. ¡Dispara!")

    def rendirse(self):
        if not self.env.done and not self.revelado:
            self.revelado = True
            self.mensaje = "Te rendiste. Pulsa R para jugar de nuevo."
            self.color_msg = C_TEXTO_SUAVE

    def partida_terminada(self):
        return self.env.done or self.revelado

    # -- accion de disparar --------------------------------------------------
    def disparar(self, r, c):
        if self.partida_terminada():
            return
        if (r, c) not in self.env.acciones_aplicables():
            self.mensaje = f"Ya disparaste en {coord_a_texto(r, c)}. Elige otra casilla."
            self.color_msg = C_TEXTO_SUAVE
            return

        self.env.step((r, c))
        fb = self.env.ultimo_feedback
        self.mensaje = mensaje_feedback(fb)

        if fb['resultado'] == 'agua':
            self.efectos.append(SalpicaduraAnimada(r, c))
            self.color_msg = C_AGUA
        elif fb['resultado'] == 'impacto':
            self.efectos.append(ExplosionAnimada(r, c, self.frames_explosion))
            self.color_msg = C_IMPACTO
        else:  # hundido: explosion en cada seccion, en cascada
            barco = next(b for b in self.env.barcos if b.nombre == fb['barco'])
            for k, (rr, cc) in enumerate(barco.posiciones):
                self.efectos.append(ExplosionAnimada(rr, cc, self.frames_explosion, retraso=k * 110))
            self.color_msg = C_HUNDIDO

        if self.env.done:
            t = self.env.turnos
            minimo = sum(b.longitud for b in self.env.barcos)
            rango = calificacion(t, minimo)
            if self.mejor is None or t < self.mejor:
                self.mejor = t
                extra = "¡Nuevo récord!"
            else:
                extra = f"Récord: {self.mejor}"
            self.resumen = f"{t} disparos  ·  Rango: {rango}  ·  {extra}"
            self.mensaje = "¡VICTORIA! Pulsa R para jugar de nuevo."
            self.color_msg = C_VICTORIA

    # -- eventos -------------------------------------------------------------
    def celda_bajo(self, pos):
        mx, my = pos
        c, r = (mx - OX) // TILE, (my - OY) // TILE
        if 0 <= r < FILAS and 0 <= c < COLUMNAS and mx >= OX and my >= OY:
            return int(r), int(c)
        return None

    def manejar_evento(self, ev):
        if ev.type == pygame.QUIT:
            return False
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            celda = self.celda_bajo(ev.pos)
            if celda:
                self.disparar(*celda)
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_ESCAPE:
                return False
            if ev.key == pygame.K_r:
                self.nueva_partida()
            if ev.key == pygame.K_v:
                self.rendirse()
        return True

    # -- dibujo --------------------------------------------------------------
    def texto(self, fuente, txt, color, pos, centro=False):
        surf = fuente.render(txt, True, color)
        rect = surf.get_rect(center=pos) if centro else surf.get_rect(topleft=pos)
        self.pantalla.blit(surf, rect)
        return rect

    def dibujar_tablero(self, ahora):
        p = self.pantalla
        p.blit(self.fondo, (OX, OY))
        p.blit(self.grid, (OX, OY))

        # marcas permanentes de agua (disparos fallidos)
        for r in range(FILAS):
            for c in range(COLUMNAS):
                if self.env.tablero_agente[r][c] == AGUA:
                    cx, cy = OX + c * TILE + TILE // 2, OY + r * TILE + TILE // 2
                    pygame.draw.circle(p, (225, 240, 250), (cx, cy), 5)
                    pygame.draw.circle(p, (225, 240, 250), (cx, cy), 14, 2)

        for v in self.vistas:
            v.dibujar(p, self.env.tablero_agente, self.revelado, ahora)

        for e in self.efectos:
            e.dibujar(p, ahora)

        # casilla bajo el cursor
        if not self.partida_terminada():
            celda = self.celda_bajo(pygame.mouse.get_pos())
            if celda and self.env.tablero_agente[celda[0]][celda[1]] == DESCONOCIDO:
                s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
                s.fill((255, 255, 255, 50))
                p.blit(s, (OX + celda[1] * TILE, OY + celda[0] * TILE))
                pygame.draw.rect(p, (255, 255, 255),
                                 (OX + celda[1] * TILE, OY + celda[0] * TILE, TILE, TILE), 2)

        # etiquetas de coordenadas
        for i in range(COLUMNAS):
            self.texto(self.fuente, string.ascii_uppercase[i], C_TEXTO_SUAVE,
                       (OX + i * TILE + TILE // 2, OY // 2), centro=True)
        for i in range(FILAS):
            self.texto(self.fuente, str(i + 1), C_TEXTO_SUAVE,
                       (OX // 2, OY + i * TILE + TILE // 2), centro=True)

        # pantalla de victoria (cuando terminan las explosiones)
        if self.env.done and not any(isinstance(e, ExplosionAnimada) for e in self.efectos):
            p.blit(self.velo, (OX, OY))
            cx = OX + TABLERO_W // 2
            self.texto(self.fuente_grande, "¡VICTORIA!", C_VICTORIA, (cx, OY + TABLERO_H // 2 - 30), centro=True)
            self.texto(self.fuente, self.resumen, C_TEXTO, (cx, OY + TABLERO_H // 2 + 28), centro=True)
            self.texto(self.fuente_peq, "Pulsa R para jugar de nuevo", C_TEXTO_SUAVE,
                       (cx, OY + TABLERO_H // 2 + 62), centro=True)

    def dibujar_panel(self):
        p = self.pantalla
        x0 = MARGEN + TABLERO_W + 16
        pygame.draw.rect(p, C_PANEL, (x0, 0, PANEL_W, ALTO))
        pygame.draw.line(p, C_PANEL_BORDE, (x0, 0), (x0, ALTO), 2)
        x = x0 + 20

        self.texto(self.fuente_titulo, "BATALLA NAVAL", C_TEXTO, (x, 18))
        self.texto(self.fuente, f"Disparos: {self.env.turnos}", C_TEXTO, (x, 66))
        rec = self.mejor if self.mejor is not None else "-"
        self.texto(self.fuente_peq, f"Récord de la sesión: {rec}", C_TEXTO_SUAVE, (x, 94))

        self.texto(self.fuente, "Flota enemiga", C_TEXTO, (x, 140))
        y = 176
        for b in self.env.barcos:
            hundido = b.esta_hundido()
            color = C_TEXTO_SUAVE if hundido else C_TEXTO
            r = self.texto(self.fuente_peq, f"{b.nombre} ({b.longitud})", color, (x, y))
            if hundido:
                pygame.draw.line(p, C_HUNDIDO, (r.left, r.centery), (r.right, r.centery), 2)
            for i in range(b.longitud):
                caja = pygame.Rect(x + i * 26, y + 22, 22, 14)
                if i < b.impactos:
                    pygame.draw.rect(p, C_HUNDIDO if hundido else C_IMPACTO, caja, border_radius=3)
                else:
                    pygame.draw.rect(p, C_PANEL_BORDE, caja, 2, border_radius=3)
            y += 56

        ayuda = ["Clic: disparar", "R: nueva partida", "V: rendirse", "ESC: salir"]
        yy = ALTO - 20 - 22 * len(ayuda)
        for linea in ayuda:
            self.texto(self.fuente_peq, linea, C_TEXTO_SUAVE, (x, yy))
            yy += 22

    def dibujar_barra(self):
        p = self.pantalla
        w = MARGEN + TABLERO_W + 16
        pygame.draw.rect(p, C_PANEL, (0, OY + TABLERO_H, w, BARRA_H))
        # si el mensaje no cabe, usa una letra mas pequena
        fuente = self.fuente_msg
        if fuente.size(self.mensaje)[0] > TABLERO_W:
            fuente = self.fuente
        self.texto(fuente, self.mensaje, self.color_msg,
                   (OX + TABLERO_W // 2, OY + TABLERO_H + BARRA_H // 2), centro=True)

    def dibujar(self):
        ahora = pygame.time.get_ticks()
        self.pantalla.fill(C_PANEL)
        self.dibujar_tablero(ahora)
        self.dibujar_panel()
        self.dibujar_barra()

    # -- bucle principal -----------------------------------------------------
    def actualizar(self):
        ahora = pygame.time.get_ticks()
        for e in self.efectos:
            e.actualizar(ahora)
        self.efectos = [e for e in self.efectos if not e.terminada]

    def jugar(self):
        corriendo = True
        while corriendo:
            for ev in pygame.event.get():
                if not self.manejar_evento(ev):
                    corriendo = False
            self.actualizar()
            self.dibujar()
            pygame.display.flip()
            self.reloj.tick(FPS)
        pygame.quit()


def main():
    parser = argparse.ArgumentParser(description="Batalla Naval visual (pygame)")
    parser.add_argument('--semilla', type=int, default=None, help="semilla para la flota")
    args = parser.parse_args()
    JuegoVisual(seed=args.semilla).jugar()


if __name__ == "__main__":
    main()
