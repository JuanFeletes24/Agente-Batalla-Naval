"""
Renderizador de pygame SIN ventana y SIN variables globales.

Pygame dibuja el tablero en una superficie en memoria (driver de video 'dummy') y
otra interfaz (por ejemplo Qt) muestra esa superficie. Asi se conservan los sprites,
la estela animada, las explosiones y las salpicaduras del juego original.

    r = RenderizadorPygame()
    r.configurar(env)                          # al empezar una partida o cambiar de nivel
    r.lanzar_efectos(env, env.ultimo_feedback, ahora_ms)   # tras cada disparo
    superficie = r.dibujar(env, revelado, ahora_ms, hover=(r, c), final=("¡VICTORIA!", "..."))
    celda = r.celda_desde_pixel(x, y)          # (fila, col) o None

El tiempo ('ahora_ms') lo entrega quien llama, asi las animaciones no dependen de pygame.time.
"""

import os

# Debe fijarse ANTES de importar pygame: nunca abrir una ventana propia.
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import numpy as np
import pygame

from ambientes import DESCONOCIDO, AGUA, TOCADO, HUNDIDO

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

AREA = 600        # el tablero ocupa siempre 600x600 px (la casilla se ajusta al nivel)
MARGEN = 34       # espacio para las etiquetas A-L / 1-12
TAMANO = (MARGEN + AREA, MARGEN + AREA)

C_FONDO = (14, 33, 48)
C_TEXTO_SUAVE = (130, 160, 178)
C_TEXTO = (232, 240, 245)
C_IMPACTO = (255, 170, 60)
C_HUNDIDO = (255, 90, 80)
C_VICTORIA = (110, 230, 140)
C_GRID = (255, 255, 255, 55)

# (cuerpo sano, cuerpo destruido, tamano de estela)
SPRITES_BARCO = {
    'Portaaviones': ("ship_large_body", "ship_large_body_destroyed", "big"),
    'Acorazado':    ("ship_medium_body_b", "ship_medium_body_b_destroyed", "big"),
    'Crucero':      ("ship_medium_body", "ship_medium_body_destroyed", "medium"),
    'Submarino':    ("ship_small_b_body", "ship_small_body_b_destroyed", "medium"),
    'Destructor':   ("ship_small_body", "ship_small_body_destroyed", "small"),
    'Lancha':       ("ship_small_b_body", "ship_small_body_b_destroyed", "small"),
}
SPRITE_POR_DEFECTO = ("ship_small_body", "ship_small_body_destroyed", "small")


def _img(nombre):
    return pygame.image.load(os.path.join(ASSETS, nombre)).convert_alpha()


# ---------------------------------------------------------------------------
# Barco y efectos (la geometria llega por parametro: nada global)
# ---------------------------------------------------------------------------

class _VistaBarco:
    def __init__(self, barco, tile, idx):
        self.barco = barco
        self.idx = idx            # posicion del barco en env.barcos (vale para entornos reconstruidos)
        self.casillas = list(barco.posiciones)
        n = len(self.casillas)
        self.horizontal = n > 1 and self.casillas[0][0] == self.casillas[1][0]
        sano, destruido, tam_estela = SPRITES_BARCO.get(barco.nombre, SPRITE_POR_DEFECTO)
        self.sanos = self._cortar(sano, n, tile)
        self.danados = self._cortar(destruido, n, tile)
        self.estela = self._estela(tam_estela, n, tile)

        r0, c0 = self.casillas[0]
        w = tile * n if self.horizontal else tile
        h = tile if self.horizontal else tile * n
        self.rect = pygame.Rect(MARGEN + c0 * tile, MARGEN + r0 * tile, w, h)

    def _cortar(self, archivo, n, tile):
        img = _img(archivo + ".png")
        if img.get_width() > img.get_height():
            img = pygame.transform.rotate(img, 90)
        img = pygame.transform.scale(img, (tile, tile * n))
        if self.horizontal:
            img = pygame.transform.rotate(img, 90)       # la proa queda a la izquierda
            return [img.subsurface(pygame.Rect(i * tile, 0, tile, tile)).copy() for i in range(n)]
        return [img.subsurface(pygame.Rect(0, i * tile, tile, tile)).copy() for i in range(n)]

    def _estela(self, tamano, n, tile):
        ancho, alto = int(tile * 1.25), int(tile * n * 1.15)
        frames = []
        for i in range(5):
            f = pygame.transform.scale(_img(f"water_ripple_{tamano}_00{i}.png"), (ancho, alto))
            frames.append(pygame.transform.rotate(f, 90) if self.horizontal else f)
        return frames


class _Explosion:
    def __init__(self, fila, col, tile, inicio):
        self.pos = (MARGEN + col * tile, MARGEN + fila * tile)
        self.inicio = inicio

    def terminada(self, ahora, n_frames):
        return (ahora - self.inicio) // 80 >= n_frames

    def dibujar(self, lienzo, ahora, frames):
        if ahora >= self.inicio:
            idx = (ahora - self.inicio) // 80
            if idx < len(frames):
                lienzo.blit(frames[idx], self.pos)


class _Salpicadura:
    DURACION = 500

    def __init__(self, fila, col, tile, inicio):
        self.centro = (MARGEN + col * tile + tile // 2, MARGEN + fila * tile + tile // 2)
        self.tile = tile
        self.inicio = inicio

    def terminada(self, ahora, _n=None):
        return ahora - self.inicio >= self.DURACION

    def dibujar(self, lienzo, ahora, _frames=None):
        t = min(1.0, max(0.0, (ahora - self.inicio) / self.DURACION))
        radio = int(8 + t * (self.tile * 0.55))
        alpha = int(220 * (1 - t))
        s = pygame.Surface((self.tile * 2, self.tile * 2), pygame.SRCALPHA)
        pygame.draw.circle(s, (255, 255, 255, alpha), (self.tile, self.tile), radio,
                           max(1, int(5 * (1 - t)) + 1))
        lienzo.blit(s, (self.centro[0] - self.tile, self.centro[1] - self.tile))


# ---------------------------------------------------------------------------
# Renderizador
# ---------------------------------------------------------------------------

class RenderizadorPygame:

    def __init__(self):
        pygame.init()
        pygame.display.set_mode((1, 1))          # superficie minima: el driver es 'dummy'
        fam = "dejavusans,segoeui,arial,helvetica"
        self.f_etiqueta = pygame.font.SysFont(fam, 18)
        self.f_titulo = pygame.font.SysFont(fam, 54, bold=True)
        self.f_sub = pygame.font.SysFont(fam, 18)
        self.lienzo = pygame.Surface(TAMANO)
        self.tile = AREA // 10
        self.vistas, self.efectos = [], []
        self.frames_explosion = []
        self.fondo = self.grid = self.velo = self.banda = None

    # -- preparar una partida -------------------------------------------------
    def configurar(self, env):
        """Recalcula tamanos y sprites. Llamar al iniciar partida o cambiar de nivel."""
        self.tile = AREA // max(env.filas, env.columnas)
        t = self.tile
        ancho, alto = env.columnas * t, env.filas * t

        fondo = pygame.image.load(os.path.join(ASSETS, "fondo.jpg")).convert()
        f = max(ancho / fondo.get_width(), alto / fondo.get_height())
        fondo = pygame.transform.smoothscale(
            fondo, (int(fondo.get_width() * f) + 1, int(fondo.get_height() * f) + 1))
        self.fondo = fondo.subsurface(pygame.Rect(0, 0, ancho, alto)).copy()

        self.grid = pygame.Surface((ancho, alto), pygame.SRCALPHA)
        for i in range(1, env.columnas):
            pygame.draw.line(self.grid, C_GRID, (i * t, 0), (i * t, alto), 2)
        for i in range(1, env.filas):
            pygame.draw.line(self.grid, C_GRID, (0, i * t), (ancho, i * t), 2)
        self.velo = pygame.Surface((ancho, alto), pygame.SRCALPHA)
        self.velo.fill((5, 15, 25, 170))
        self.banda = pygame.Surface((ancho, 150), pygame.SRCALPHA)
        self.banda.fill((5, 15, 25, 205))

        hoja = _img("explosion.png")                      # 192x32: 6 cuadros de 32x32
        self.frames_explosion = [
            pygame.transform.scale(hoja.subsurface(pygame.Rect(i * 32, 0, 32, 32)).copy(), (t, t))
            for i in range(hoja.get_width() // 32)]

        self.f_valor = pygame.font.SysFont("dejavusans,segoeui,arial,helvetica", max(9, t // 6))
        self.f_numero = pygame.font.SysFont("dejavusans,segoeui,arial,helvetica", max(11, t // 4), bold=True)
        self.vistas = [_VistaBarco(b, t, i) for i, b in enumerate(env.barcos)]
        self.efectos = []

    # -- efectos --------------------------------------------------------------
    def lanzar_efectos(self, env, feedback, ahora):
        """Anima el resultado REPORTADO del ultimo disparo (con ruido puede no ser real)."""
        if feedback is None:
            return
        r, c = feedback['coord']
        t = self.tile
        if feedback['resultado'] == 'agua':
            self.efectos.append(_Salpicadura(r, c, t, ahora))
        elif feedback['resultado'] == 'impacto':
            self.efectos.append(_Explosion(r, c, t, ahora))
        else:  # hundido: explosiones en cascada sobre cada seccion
            barco = env.barcos[env.tablero_oculto[r][c] - 1]
            for k, (rr, cc) in enumerate(barco.posiciones):
                self.efectos.append(_Explosion(rr, cc, t, ahora + k * 110))

    def hay_explosiones(self):
        return any(isinstance(e, _Explosion) for e in self.efectos)

    def hay_animacion(self, env, revelado):
        """True si hay algo moviendose (para saber si hace falta redibujar)."""
        if self.efectos:
            return True
        return revelado and any(not b.esta_hundido() for b in env.barcos)

    def _limpiar(self, ahora):
        n = len(self.frames_explosion)
        self.efectos = [e for e in self.efectos if not e.terminada(ahora, n)]

    # -- geometria ------------------------------------------------------------
    def celda_desde_pixel(self, x, y, env):
        if x < MARGEN or y < MARGEN:
            return None
        c, r = int((x - MARGEN) // self.tile), int((y - MARGEN) // self.tile)
        if 0 <= r < env.filas and 0 <= c < env.columnas:
            return r, c
        return None

    # -- dibujo ---------------------------------------------------------------
    def dibujar(self, env, revelado, ahora, hover=None, final=None, numeros=None, resaltar=None,
                mapa=None):
        """
        Devuelve la superficie con el tablero.
          hover : (fila, col) bajo el cursor, o None.
          final : (titulo, subtitulo) para la pantalla de victoria/derrota, o None.
          numeros : {(fila, col): n} para numerar el orden de los disparos, o None.
          resaltar: (fila, col) de la ultima jugada (borde amarillo), o None.
          mapa    : matriz (filas, cols) con un valor por casilla (NaN = sin valor) que se
                    dibuja como mapa de calor, o None.
        """
        self._limpiar(ahora)
        p, t = self.lienzo, self.tile
        tab = env.tablero_agente
        ruido = env.config.prob_ruido > 0
        ancho, alto = env.columnas * t, env.filas * t

        p.fill(C_FONDO)
        p.blit(self.fondo, (MARGEN, MARGEN))
        p.blit(self.grid, (MARGEN, MARGEN))
        if mapa is not None:
            self._mapa_calor(mapa)

        for r in range(env.filas):
            for c in range(env.columnas):
                cx, cy = MARGEN + c * t + t // 2, MARGEN + r * t + t // 2
                if tab[r][c] == AGUA:
                    pygame.draw.circle(p, (225, 240, 250), (cx, cy), 5)
                    pygame.draw.circle(p, (225, 240, 250), (cx, cy), t // 4 + 3, 2)

        for v in self.vistas:
            if revelado and not env.barcos[v.idx].esta_hundido():
                frame = v.estela[(ahora // 140) % len(v.estela)]
                p.blit(frame, frame.get_rect(center=v.rect.center))
            for i, (r, c) in enumerate(v.casillas):
                estado = tab[r][c]
                # con sonar ruidoso un "tocado" no es fiable: no se dibuja el sprite
                golpeada = estado == HUNDIDO or (estado == TOCADO and not ruido)
                if golpeada or revelado:
                    p.blit(v.danados[i] if golpeada else v.sanos[i],
                           (MARGEN + c * t, MARGEN + r * t))

        if ruido:
            for r in range(env.filas):
                for c in range(env.columnas):
                    if tab[r][c] == TOCADO:
                        self._marca_sonar(r, c)

        for e in self.efectos:
            e.dibujar(p, ahora, self.frames_explosion)

        if hover is not None and not final and tab[hover[0]][hover[1]] == DESCONOCIDO:
            s = pygame.Surface((t, t), pygame.SRCALPHA)
            s.fill((255, 255, 255, 50))
            x, y = MARGEN + hover[1] * t, MARGEN + hover[0] * t
            p.blit(s, (x, y))
            pygame.draw.rect(p, (255, 255, 255), (x, y, t, t), 2)

        if resaltar is not None:
            pygame.draw.rect(p, (255, 235, 90),
                             (MARGEN + resaltar[1] * t, MARGEN + resaltar[0] * t, t, t), 3)
        if numeros:
            for (r, c), n in numeros.items():
                self._numero(n, MARGEN + c * t + 3, MARGEN + r * t + 1)

        for i in range(env.columnas):
            self._texto(self.f_etiqueta, chr(65 + i), C_TEXTO_SUAVE,
                        (MARGEN + i * t + t // 2, MARGEN // 2))
        for i in range(env.filas):
            self._texto(self.f_etiqueta, str(i + 1), C_TEXTO_SUAVE,
                        (MARGEN // 2, MARGEN + i * t + t // 2))

        # pantalla final, cuando terminan las explosiones
        if final and not self.hay_explosiones():
            titulo, sub = final
            cx, cy = MARGEN + ancho // 2, MARGEN + alto // 2
            if env.ganado:
                p.blit(self.velo, (MARGEN, MARGEN))
                color = C_VICTORIA
            else:
                p.blit(self.banda, (MARGEN, cy - 75))    # banda: deja ver la flota revelada
                color = C_HUNDIDO
            self._texto(self.f_titulo, titulo, color, (cx, cy - 20))
            self._texto(self.f_sub, sub, C_TEXTO, (cx, cy + 30))
        return p

    def _texto(self, fuente, txt, color, centro):
        s = fuente.render(txt, True, color)
        self.lienzo.blit(s, s.get_rect(center=centro))

    def limpiar_efectos(self):
        self.efectos = []

    def _mapa_calor(self, mapa):
        """Colorea cada casilla segun su valor (azul = bajo, amarillo = medio, rojo = alto)."""
        m = np.asarray(mapa, dtype=float)
        validos = np.isfinite(m)
        if not validos.any():
            return
        lo, hi = m[validos].min(), m[validos].max()
        norm = (m - lo) / (hi - lo) if hi > lo else np.full_like(m, 0.4)   # todos iguales: tono uniforme
        t = self.tile
        celda = pygame.Surface((t, t), pygame.SRCALPHA)
        for r, c in zip(*np.nonzero(validos)):
            x = float(norm[r, c])
            if x < 0.5:
                color = (60 + int(390 * x), 120 + int(220 * x), 255 - int(350 * x))        # azul -> amarillo
            else:
                color = (255, 230 - int(340 * (x - 0.5)), 80 - int(80 * (x - 0.5)))        # amarillo -> rojo
            celda.fill((*color, 45 + int(135 * x)))
            self.lienzo.blit(celda, (MARGEN + int(c) * t, MARGEN + int(r) * t))
            if t >= 48 and x >= 0.3 and hi > lo:          # el valor numerico, si cabe y aporta
                v = m[r, c]
                txt = f"{v:.2f}" if abs(v) < 100 else f"{v:.0f}"
                s = self.f_valor.render(txt, True, (255, 255, 255))
                borde = self.f_valor.render(txt, True, (0, 0, 0))
                px = MARGEN + int(c) * t + t // 2 - s.get_width() // 2
                py = MARGEN + int(r) * t + t - s.get_height() - 2
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    self.lienzo.blit(borde, (px + dx, py + dy))
                self.lienzo.blit(s, (px, py))

    def _numero(self, n, x, y):
        """Numero con contorno oscuro: legible sobre agua, sprites y explosiones."""
        txt = str(n)
        borde = self.f_numero.render(txt, True, (0, 0, 0))
        for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1), (0, 2), (0, -2), (2, 0), (-2, 0)):
            self.lienzo.blit(borde, (x + dx, y + dy))
        self.lienzo.blit(self.f_numero.render(txt, True, (255, 255, 255)), (x, y))

    def _marca_sonar(self, r, c):
        p, t = self.lienzo, self.tile
        cx, cy = MARGEN + c * t + t // 2, MARGEN + r * t + t // 2
        k = t // 4
        pygame.draw.circle(p, (60, 25, 10), (cx, cy), t // 3 + 2)
        pygame.draw.circle(p, C_IMPACTO, (cx, cy), t // 3, 3)
        pygame.draw.line(p, C_IMPACTO, (cx - k, cy - k), (cx + k, cy + k), 3)
        pygame.draw.line(p, C_IMPACTO, (cx - k, cy + k), (cx + k, cy - k), 3)
