"""
Batalla Naval para una persona - version visual con pygame.

Usa el motor de ambientes.py (BatallaNavalEnv) y los niveles de dificultad de
dificultad.py. Este archivo solo dibuja: fondo de agua, barcos por secciones,
estela animada, explosiones y salpicaduras.

Uso:
    python juego_visual.py                    # nivel medio
    python juego_visual.py --nivel experto    # facil | medio | dificil | experto
    python juego_visual.py --semilla 7        # misma flota en la primera partida

Controles:
    clic izquierdo -> disparar
    1-4 (o clic en el panel) -> cambiar de nivel y empezar de nuevo
    R -> nueva partida      V -> rendirse y ver la flota      ESC -> salir
"""

import argparse
import os
import string

import pygame

from ambientes import BatallaNavalEnv, DESCONOCIDO, AGUA, TOCADO, HUNDIDO
from dificultad import NIVELES, ORDEN_NIVELES
from utils import coord_a_texto, mensaje_feedback, calificacion

# ---------------------------------------------------------------------------
# CONFIGURACION
# ---------------------------------------------------------------------------

AREA = 640                    # el tablero ocupa siempre 640x640 px (la casilla se ajusta)
MARGEN = 36                   # espacio para letras/numeros de coordenadas
PANEL_W = 260
BARRA_H = 64
FPS = 60
OX, OY = MARGEN, MARGEN       # esquina superior izquierda del tablero
ANCHO = MARGEN + AREA + 16 + PANEL_W
ALTO = MARGEN + AREA + BARRA_H
PANEL_X = MARGEN + AREA + 16

# Geometria que depende del nivel (la fija configurar_geometria)
FILAS = COLUMNAS = 10
TILE = AREA // 10
TABLERO_W = TABLERO_H = AREA


def configurar_geometria(filas, columnas):
    global FILAS, COLUMNAS, TILE, TABLERO_W, TABLERO_H
    FILAS, COLUMNAS = filas, columnas
    TILE = AREA // max(filas, columnas)
    TABLERO_W, TABLERO_H = columnas * TILE, filas * TILE


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

# Sprite de cada barco: (cuerpo sano, cuerpo destruido, tamano de estela)
SPRITES_BARCO = {
    'Portaaviones': ("ship_large_body", "ship_large_body_destroyed", "big"),
    'Acorazado':    ("ship_medium_body_b", "ship_medium_body_b_destroyed", "big"),
    'Crucero':      ("ship_medium_body", "ship_medium_body_destroyed", "medium"),
    'Submarino':    ("ship_small_b_body", "ship_small_body_b_destroyed", "medium"),
    'Destructor':   ("ship_small_body", "ship_small_body_destroyed", "small"),
    'Lancha':       ("ship_small_b_body", "ship_small_body_b_destroyed", "small"),
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


def cargar_explosion(ancho_frame=32):
    """La hoja es de 192x32: 6 cuadros de 32x32."""
    hoja = _img("explosion.png")
    frames = []
    for i in range(hoja.get_width() // ancho_frame):
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
    ancho, alto = int(TILE * 1.25), int(TILE * n * 1.15)
    frames = []
    for i in range(5):
        f = pygame.transform.scale(_img(f"water_ripple_{tamano}_00{i}.png"), (ancho, alto))
        frames.append(pygame.transform.rotate(f, 90) if horizontal else f)
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

        r0, c0 = self.casillas[0]
        w = TILE * n if self.horizontal else TILE
        h = TILE if self.horizontal else TILE * n
        self.rect = pygame.Rect(OX + c0 * TILE, OY + r0 * TILE, w, h)

    def dibujar(self, pantalla, tablero_agente, revelado, ahora, ruido):
        hundido = self.barco.esta_hundido()

        # estela animada: solo cuando se muestra la flota entera
        if revelado and not hundido:
            frame = self.frames_estela[(ahora // 140) % len(self.frames_estela)]
            pantalla.blit(frame, frame.get_rect(center=self.rect.center))

        for i, (r, c) in enumerate(self.casillas):
            estado = tablero_agente[r][c]
            # con sonar ruidoso un "tocado" no es fiable: se dibuja como marca neutra
            # (el sprite solo aparece cuando el barco esta confirmado como hundido)
            golpeada = estado == HUNDIDO or (estado == TOCADO and not ruido)
            if not golpeada and not revelado:
                continue
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

    def __init__(self, nivel='medio', seed=None):
        pygame.init()
        self.pantalla = pygame.display.set_mode((ANCHO, ALTO))
        pygame.display.set_caption("Batalla Naval")
        self.reloj = pygame.time.Clock()

        fam = "segoeui,arial,helvetica,dejavusans"
        self.fuente_titulo = pygame.font.SysFont(fam, 24, bold=True)
        self.fuente_msg = pygame.font.SysFont(fam, 26, bold=True)
        self.fuente = pygame.font.SysFont(fam, 19)
        self.fuente_peq = pygame.font.SysFont(fam, 15)
        self.fuente_grande = pygame.font.SysFont(fam, 54, bold=True)

        # botones de nivel (2x2) en el panel
        self.botones = []
        for i, clave in enumerate(ORDEN_NIVELES):
            rect = pygame.Rect(PANEL_X + 20 + (i % 2) * 108, 58 + (i // 2) * 30, 104, 26)
            self.botones.append((rect, clave))

        self.seed = seed          # solo se usa para la primera partida
        self.mejores = {}         # mejor marca de la sesion por nivel
        self._cargar_nivel(nivel)

    # -- estado de la partida ------------------------------------------------
    def _cargar_nivel(self, nivel):
        """Cambia de nivel: recalcula la geometria, recursos graficos y crea el entorno."""
        self.nivel = nivel
        self.config = NIVELES[nivel]
        self.ruido = self.config.prob_ruido > 0
        configurar_geometria(self.config.filas, self.config.columnas)

        self.fondo = cargar_fondo_cuadrado(os.path.join(ASSETS, "fondo.jpg"), TABLERO_W, TABLERO_H)
        self.frames_explosion = cargar_explosion()
        self.grid = pygame.Surface((TABLERO_W, TABLERO_H), pygame.SRCALPHA)
        for i in range(1, COLUMNAS):
            pygame.draw.line(self.grid, C_GRID, (i * TILE, 0), (i * TILE, TABLERO_H), 2)
        for i in range(1, FILAS):
            pygame.draw.line(self.grid, C_GRID, (0, i * TILE), (TABLERO_W, i * TILE), 2)
        self.velo = pygame.Surface((TABLERO_W, TABLERO_H), pygame.SRCALPHA)
        self.velo.fill((5, 15, 25, 170))
        self.banda = pygame.Surface((TABLERO_W, 150), pygame.SRCALPHA)
        self.banda.fill((5, 15, 25, 205))

        self.env = BatallaNavalEnv(config=self.config, seed=self.seed)
        self.seed = None
        self._preparar_partida()

    def _preparar_partida(self, mensaje=None):
        self.vistas = [VistaBarco(b) for b in self.env.barcos]
        self.efectos = []
        self.revelado = False
        self.mensaje = mensaje or "Haz clic en una casilla para disparar."
        self.color_msg = C_TEXTO
        self.resumen = ""

    def nueva_partida(self):
        self.env.reset()
        self._preparar_partida("Nueva partida. ¡Dispara!")

    def cambiar_nivel(self, nivel):
        self._cargar_nivel(nivel)
        self.mensaje = f"Nivel {self.config.nombre}. ¡Dispara!"

    def rendirse(self):
        if not self.partida_terminada():
            self.revelado = True
            self.mensaje = "Te rendiste. Pulsa R para jugar de nuevo."
            self.color_msg = C_TEXTO_SUAVE

    def partida_terminada(self):
        return self.env.done or self.revelado

    # -- accion de disparar --------------------------------------------------
    def disparar(self, r, c):
        if self.partida_terminada():
            return
        if self.env.tablero_agente[r][c] != DESCONOCIDO:
            self.mensaje = f"Ya disparaste en {coord_a_texto(r, c)}. Elige otra casilla."
            self.color_msg = C_TEXTO_SUAVE
            return

        self.env.step((r, c))
        fb = self.env.ultimo_feedback
        self.mensaje = mensaje_feedback(fb, self.ruido)

        # los efectos muestran lo que el sonar REPORTA (puede no ser verdad con ruido)
        if fb['resultado'] == 'agua':
            self.efectos.append(SalpicaduraAnimada(r, c))
            self.color_msg = C_AGUA
        elif fb['resultado'] == 'impacto':
            self.efectos.append(ExplosionAnimada(r, c, self.frames_explosion))
            self.color_msg = C_IMPACTO
        else:  # hundido: explosion en cascada sobre cada seccion del barco
            barco = self.env.barcos[self.env.tablero_oculto[r][c] - 1]
            for k, (rr, cc) in enumerate(barco.posiciones):
                self.efectos.append(ExplosionAnimada(rr, cc, self.frames_explosion, retraso=k * 110))
            self.color_msg = C_HUNDIDO

        if self.env.ganado:
            t = self.env.turnos
            rango = calificacion(t, self.config.casillas_barco)
            mejor = self.mejores.get(self.nivel)
            if mejor is None or t < mejor:
                self.mejores[self.nivel] = t
                extra = "¡Nuevo récord!"
            else:
                extra = f"Récord: {mejor}"
            self.resumen = f"{t} disparos  ·  Rango: {rango}  ·  {extra}"
            self.mensaje = "¡VICTORIA! Pulsa R para jugar de nuevo."
            self.color_msg = C_VICTORIA
        elif self.env.agotado:
            self.revelado = True      # se muestra donde estaba la flota
            hundidos = len(self.env.barcos) - self.env.para_sentidos()['n_barcos_vivos']
            self.resumen = f"Hundiste {hundidos} de {len(self.env.barcos)} barcos"
            self.mensaje = "¡Sin disparos! Pulsa R para intentarlo de nuevo."
            self.color_msg = C_HUNDIDO

    # -- eventos -------------------------------------------------------------
    def celda_bajo(self, pos):
        mx, my = pos
        if mx < OX or my < OY:
            return None
        c, r = (mx - OX) // TILE, (my - OY) // TILE
        if 0 <= r < FILAS and 0 <= c < COLUMNAS:
            return int(r), int(c)
        return None

    def manejar_evento(self, ev):
        if ev.type == pygame.QUIT:
            return False
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            for rect, clave in self.botones:
                if rect.collidepoint(ev.pos):
                    self.cambiar_nivel(clave)
                    return True
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
            for i, clave in enumerate(ORDEN_NIVELES):
                if ev.key in (pygame.K_1 + i, pygame.K_KP1 + i):
                    self.cambiar_nivel(clave)
        return True

    # -- dibujo --------------------------------------------------------------
    def texto(self, fuente, txt, color, pos, centro=False):
        surf = fuente.render(txt, True, color)
        rect = surf.get_rect(center=pos) if centro else surf.get_rect(topleft=pos)
        self.pantalla.blit(surf, rect)
        return rect

    @staticmethod
    def _ajustar(txt, fuente, ancho):
        """Divide un texto en lineas que quepan en 'ancho' pixeles."""
        lineas, actual = [], ""
        for palabra in txt.split():
            prueba = (actual + " " + palabra).strip()
            if fuente.size(prueba)[0] <= ancho:
                actual = prueba
            else:
                lineas.append(actual)
                actual = palabra
        if actual:
            lineas.append(actual)
        return lineas

    def _marca_sonar(self, r, c):
        """Marca neutra de 'sonar detecto algo' (con ruido no se sabe si es real)."""
        p = self.pantalla
        cx, cy = OX + c * TILE + TILE // 2, OY + r * TILE + TILE // 2
        k = TILE // 4
        pygame.draw.circle(p, (60, 25, 10), (cx, cy), TILE // 3 + 2)
        pygame.draw.circle(p, C_IMPACTO, (cx, cy), TILE // 3, 3)
        pygame.draw.line(p, C_IMPACTO, (cx - k, cy - k), (cx + k, cy + k), 3)
        pygame.draw.line(p, C_IMPACTO, (cx - k, cy + k), (cx + k, cy - k), 3)

    def dibujar_tablero(self, ahora):
        p = self.pantalla
        tab = self.env.tablero_agente
        p.blit(self.fondo, (OX, OY))
        p.blit(self.grid, (OX, OY))

        for r in range(FILAS):
            for c in range(COLUMNAS):
                if tab[r][c] == AGUA:
                    cx, cy = OX + c * TILE + TILE // 2, OY + r * TILE + TILE // 2
                    pygame.draw.circle(p, (225, 240, 250), (cx, cy), 5)
                    pygame.draw.circle(p, (225, 240, 250), (cx, cy), TILE // 4 + 3, 2)

        for v in self.vistas:
            v.dibujar(p, tab, self.revelado, ahora, self.ruido)

        if self.ruido:
            for r in range(FILAS):
                for c in range(COLUMNAS):
                    if tab[r][c] == TOCADO:
                        self._marca_sonar(r, c)

        for e in self.efectos:
            e.dibujar(p, ahora)

        # casilla bajo el cursor
        if not self.partida_terminada():
            celda = self.celda_bajo(pygame.mouse.get_pos())
            if celda and tab[celda[0]][celda[1]] == DESCONOCIDO:
                s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
                s.fill((255, 255, 255, 50))
                x, y = OX + celda[1] * TILE, OY + celda[0] * TILE
                p.blit(s, (x, y))
                pygame.draw.rect(p, (255, 255, 255), (x, y, TILE, TILE), 2)

        # etiquetas de coordenadas
        for i in range(COLUMNAS):
            self.texto(self.fuente, string.ascii_uppercase[i], C_TEXTO_SUAVE,
                       (OX + i * TILE + TILE // 2, OY // 2), centro=True)
        for i in range(FILAS):
            self.texto(self.fuente, str(i + 1), C_TEXTO_SUAVE,
                       (OX // 2, OY + i * TILE + TILE // 2), centro=True)

        # pantalla final (cuando terminan las explosiones)
        if self.env.done and not any(isinstance(e, ExplosionAnimada) for e in self.efectos):
            cx, cy = OX + TABLERO_W // 2, OY + TABLERO_H // 2
            if self.env.ganado:
                p.blit(self.velo, (OX, OY))
                titulo, color = "¡VICTORIA!", C_VICTORIA
            else:
                p.blit(self.banda, (OX, cy - 75))   # banda: deja ver la flota revelada
                titulo, color = "DERROTA", C_HUNDIDO
            self.texto(self.fuente_grande, titulo, color, (cx, cy - 30), centro=True)
            self.texto(self.fuente, self.resumen, C_TEXTO, (cx, cy + 28), centro=True)
            self.texto(self.fuente_peq, "Pulsa R para jugar de nuevo", C_TEXTO_SUAVE,
                       (cx, cy + 56), centro=True)

    def dibujar_panel(self):
        p = self.pantalla
        env, cfg = self.env, self.config
        pygame.draw.rect(p, C_PANEL, (PANEL_X, 0, PANEL_W, ALTO))
        pygame.draw.line(p, C_PANEL_BORDE, (PANEL_X, 0), (PANEL_X, ALTO), 2)
        x = PANEL_X + 20

        self.texto(self.fuente_titulo, "BATALLA NAVAL", C_TEXTO, (x, 18))

        # selector de nivel
        for i, (rect, clave) in enumerate(self.botones):
            activo = clave == self.nivel
            pygame.draw.rect(p, (40, 110, 150) if activo else C_PANEL, rect, border_radius=5)
            pygame.draw.rect(p, C_TEXTO if activo else C_PANEL_BORDE, rect, 2, border_radius=5)
            self.texto(self.fuente_peq, f"{i + 1}  {NIVELES[clave].nombre}",
                       C_TEXTO if activo else C_TEXTO_SUAVE, rect.center, centro=True)

        lim = cfg.max_disparos
        disparos = f"{env.turnos}" if lim is None else f"{env.turnos} / {lim}"
        color = C_HUNDIDO if lim is not None and lim - env.turnos <= 5 else C_TEXTO
        self.texto(self.fuente, f"Disparos: {disparos}", color, (x, 126))
        rec = self.mejores.get(self.nivel, "-")
        self.texto(self.fuente_peq, f"Récord en este nivel: {rec}", C_TEXTO_SUAVE, (x, 152))

        y = 176
        for linea in cfg.descripcion():
            for k, sub in enumerate(self._ajustar("· " + linea, self.fuente_peq, PANEL_W - 40)):
                self.texto(self.fuente_peq, ("   " if k else "") + sub, C_TEXTO_SUAVE, (x, y))
                y += 17

        y = max(y + 12, 250)
        self.texto(self.fuente, "Flota enemiga", C_TEXTO, (x, y))
        y += 32
        if cfg.mostrar_flota_restante:
            for b in env.barcos:
                hundido = b.esta_hundido()
                r = self.texto(self.fuente_peq, f"{b.nombre} ({b.longitud})",
                               C_TEXTO_SUAVE if hundido else C_TEXTO, (x, y))
                if hundido:
                    pygame.draw.line(p, C_HUNDIDO, (r.left, r.centery), (r.right, r.centery), 2)
                for i in range(b.longitud):
                    caja = pygame.Rect(x + i * 24, y + 20, 20, 12)
                    lleno = hundido or (i < b.impactos and not self.ruido)
                    if lleno:
                        pygame.draw.rect(p, C_HUNDIDO if hundido else C_IMPACTO, caja, border_radius=3)
                    else:
                        pygame.draw.rect(p, C_PANEL_BORDE, caja, 2, border_radius=3)
                y += 44
        else:
            total = len(env.barcos)
            vivos = env.para_sentidos()['n_barcos_vivos']
            self.texto(self.fuente_peq, f"Barcos restantes: {vivos} de {total}", C_TEXTO, (x, y))
            self.texto(self.fuente_peq, "(no se sabe cuáles)", C_TEXTO_SUAVE, (x, y + 20))
            for i in range(total):
                caja = pygame.Rect(x + i * 36, y + 46, 30, 16)
                if i < total - vivos:
                    pygame.draw.rect(p, C_HUNDIDO, caja, border_radius=3)
                else:
                    pygame.draw.rect(p, C_PANEL_BORDE, caja, 2, border_radius=3)

        ayuda = ["Clic: disparar", "1-4: cambiar de nivel", "R: nueva partida",
                 "V: rendirse", "ESC: salir"]
        yy = ALTO - 16 - 20 * len(ayuda)
        for linea in ayuda:
            self.texto(self.fuente_peq, linea, C_TEXTO_SUAVE, (x, yy))
            yy += 20

    def dibujar_barra(self):
        pygame.draw.rect(self.pantalla, C_PANEL, (0, OY + AREA, PANEL_X, BARRA_H))
        fuente = self.fuente_msg
        if fuente.size(self.mensaje)[0] > AREA:
            fuente = self.fuente
        self.texto(fuente, self.mensaje, self.color_msg,
                   (OX + AREA // 2, OY + AREA + BARRA_H // 2), centro=True)

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
    parser.add_argument('--nivel', default='medio', choices=ORDEN_NIVELES)
    parser.add_argument('--semilla', type=int, default=None, help="semilla de la primera partida")
    args = parser.parse_args()
    JuegoVisual(nivel=args.nivel, seed=args.semilla).jugar()


if __name__ == "__main__":
    main()
