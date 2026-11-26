"""
Interfaz de escritorio (PySide6) de Batalla Naval - PROTOTIPO: pestañas "Jugar" y "Ver agente".
La pestaña "Árbol MCTS" muestra el árbol de búsqueda; "Ver agente" muestra las reglas de Caza-Remate.

El tablero lo dibuja pygame en memoria (render_pygame.py, con sprites y animaciones) y
Qt lo muestra, le reenvia los clics y aporta los controles (nivel, botones, paneles).

Uso:
    pip install PySide6
    python app_qt.py
"""

import random
import sys

from PySide6.QtCore import Qt, QTimer, QElapsedTimer, QPointF, QRectF, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPalette, QPen
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QHBoxLayout, QLabel,
                               QListWidget, QMainWindow, QPushButton, QSlider, QSpinBox,
                               QSizePolicy, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

import pygame

from agents import AGENTES
from dificultad import NIVELES, ORDEN_NIVELES
from partida import Partida
from render_pygame import RenderizadorPygame, TAMANO
from sesion_agente import SesionAgente
from utils import coord_a_texto
from visualizacion import (C_TEXTO, C_TEXTO_SUAVE, COLOR_ARISTA, COLOR_NODO,
                           COLOR_OBS, COLOR_RAMA, COLOR_REGLA, ETIQUETA_NODO, a_hex, disponer_arbol)

NIVEL_POR_DEFECTO = 'medio'
FPS = 30

COLOR_TONO = {            # color del mensaje segun lo ocurrido
    'normal': '#e8f0f5', 'agua': '#8cd2ff', 'impacto': '#ffaa3c', 'hundido': '#ff5a50',
    'victoria': '#6ee68c', 'derrota': '#ff5a50', 'aviso': '#82a0b2',
}


class TableroWidget(QWidget):
    """Muestra la superficie de pygame y emite los clics y el movimiento del raton."""
    clic = Signal(int, int)
    movimiento = Signal(object)          # (x, y) o None cuando el raton sale

    def __init__(self):
        super().__init__()
        self.setFixedSize(*TAMANO)
        self.setMouseTracking(True)
        self._imagen = None

    def mostrar(self, superficie: pygame.Surface):
        ancho, alto = superficie.get_size()
        datos = pygame.image.tobytes(superficie, "RGB")
        self._imagen = QImage(datos, ancho, alto, 3 * ancho, QImage.Format_RGB888).copy()
        self.update()

    def paintEvent(self, _):
        if self._imagen is not None:
            QPainter(self).drawImage(0, 0, self._imagen)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clic.emit(int(e.position().x()), int(e.position().y()))

    def mouseMoveEvent(self, e):
        self.movimiento.emit((int(e.position().x()), int(e.position().y())))

    def leaveEvent(self, _):
        self.movimiento.emit(None)


class ArbolWidget(QWidget):
    """Dibuja el resumen del arbol de MCTS (izquierda -> derecha) con la estetica del tablero."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(420, 440)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._arbol = None

    def poner(self, arbol):
        self._arbol = arbol
        self.update()

    def _fondo(self, p):
        """Fondo liso del mismo color que la ventana de la interfaz."""
        p.fillRect(self.rect(), QColor(45,45,45))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        self._fondo(p)
        if not self._arbol:
            p.setPen(QColor(*C_TEXTO_SUAVE))
            p.drawText(self.rect(), Qt.AlignCenter, "El árbol aparece tras la primera jugada")
            return
        d = disponer_arbol(self._arbol, self.width(), self.height(),
                           max_filas=max(18, self.height() // 30))
        nodos = d['nodos']
        for i, j, rama in d['aristas']:                     # primero las aristas (quedan debajo)
            a, b = nodos[i], nodos[j]
            p1 = QPointF(a['x'] + a['w'], a['yc'])
            p2 = QPointF(b['x'], b['yc'])
            p.setPen(QPen(QColor(*(COLOR_RAMA if rama else COLOR_ARISTA)), 2 if rama else 1))
            p.drawLine(p1, p2)
        fuente = p.font()
        fuente.setPointSize(9 if self.width() > 600 else 8)
        p.setFont(fuente)
        negrita = QFont(fuente)
        negrita.setBold(True)
        for n in nodos:
            rect = QRectF(n['x'], n['y'], n['w'], n['h'])
            borde = QColor(*COLOR_NODO[n['tipo']])
            lapiz = QPen(borde, 1)                          # borde fino
            if n['tipo'] == 'frontera':
                lapiz.setStyle(Qt.DashLine)                 # hoja nueva: borde punteado
            p.setPen(lapiz)
            p.setBrush(self.palette().color(QPalette.Button))      # tono de los botones de la UI
            p.drawRoundedRect(rect, 5, 5)
            if n.get('obs'):                                # franja del color del resultado
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(*COLOR_OBS[n['obs']]))
                p.drawRoundedRect(QRectF(rect.x() + 3, rect.y() + 5, 3, rect.height() - 10), 1.5, 1.5)
            color_txt = QColor(*COLOR_OBS[n['obs']]) if n.get('obs') else QColor(*C_TEXTO)
            p.setFont(negrita)
            p.setPen(color_txt)
            if len(n['lineas']) == 2:
                p.drawText(QRectF(rect.x(), rect.y() + 2, rect.width(), rect.height() / 2),
                           Qt.AlignCenter, n['lineas'][0])
                p.setFont(fuente)
                p.setPen(QColor(*C_TEXTO_SUAVE))
                p.drawText(QRectF(rect.x(), rect.y() + rect.height() / 2 - 2, rect.width(),
                                  rect.height() / 2), Qt.AlignCenter, n['lineas'][1])
            else:
                p.drawText(rect, Qt.AlignCenter, n['lineas'][0])
            p.setFont(fuente)


class PestanaArbol(QWidget):
    """
    Pestaña "Árbol MCTS": copia del tablero y de los controles de "Ver agente" (manejan la misma
    partida), el arbol de busqueda de la jugada vista y, a la derecha, leyenda y acciones de la raiz.
    Solo tiene contenido de arbol cuando el agente elegido es MCTS.
    """

    def __init__(self, origen):
        super().__init__()
        self.origen = origen                       # la PestanaAgente de la que lee y a la que controla

        # -- columna izquierda: tablero (copia), mensaje y controles --
        self.tablero = TableroWidget()
        self.mensaje = QLabel()
        self.mensaje.setAlignment(Qt.AlignCenter)
        self.btn_reiniciar = QPushButton("Reiniciar partida")
        self.btn_atras = QPushButton("|◀ Atrás")
        self.btn_paso = QPushButton("Paso ▶|")
        self.btn_play = QPushButton("▶ Reproducir")
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(origen.slider.minimum(), origen.slider.maximum())
        self.slider.setValue(origen.slider.value())
        self.lbl_vel = QLabel()
        izq = QVBoxLayout()
        izq.addWidget(self.tablero)
        izq.addWidget(self.mensaje)
        izq.addWidget(self.btn_reiniciar)
        fila = QHBoxLayout()
        for b in (self.btn_atras, self.btn_paso, self.btn_play):
            fila.addWidget(b)
        izq.addLayout(fila)
        fila = QHBoxLayout()
        fila.addWidget(QLabel("Velocidad"))
        fila.addWidget(self.slider, 1)
        fila.addWidget(self.lbl_vel)
        izq.addLayout(fila)
        izq.addStretch(1)

        # -- centro: estado y arbol --
        self.estado = QLabel()
        self.estado.setStyleSheet("font-weight: bold; font-size: 15px;")
        self.arbol = ArbolWidget()
        centro = QVBoxLayout()
        centro.addWidget(self.estado)
        centro.addWidget(self.arbol, 1)

        # -- derecha: leyenda y tabla --
        self.leyenda = QLabel()
        self.leyenda.setTextFormat(Qt.RichText)
        self.leyenda.setWordWrap(True)
        self.tabla = QTableWidget(0, 4)
        self.tabla.setHorizontalHeaderLabels(["Acción", "N", "Q medio", "Nota"])
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabla.setSelectionMode(QTableWidget.NoSelection)
        self.tabla.horizontalHeader().setStretchLastSection(True)
        der = QVBoxLayout()
        der.addWidget(QLabel("<b>Leyenda</b>"))
        der.addWidget(self.leyenda)
        der.addWidget(QLabel("<b>Acciones de la raíz</b> (las más visitadas)"))
        der.addWidget(self.tabla, 1)
        panel_der = QWidget()
        panel_der.setLayout(der)
        panel_der.setFixedWidth(330)

        raiz = QHBoxLayout(self)
        raiz.addLayout(izq)
        raiz.addLayout(centro, 1)
        raiz.addWidget(panel_der)

        # -- conexiones: los controles mueven la misma sesion de "Ver agente" --
        self.btn_reiniciar.clicked.connect(lambda *_: origen.nueva_sesion())
        self.btn_atras.clicked.connect(lambda *_: origen.atras())
        self.btn_paso.clicked.connect(lambda *_: origen.paso_manual())
        self.btn_play.clicked.connect(lambda *_: origen.btn_play.setChecked(not origen.btn_play.isChecked()))
        self.slider.valueChanged.connect(origen.slider.setValue)
        origen.slider.valueChanged.connect(self.sincronizar)
        origen.btn_play.toggled.connect(self.sincronizar)
        origen.espejos.append(self.tablero)
        origen.sucio = True
        origen.cambio.connect(self.actualizar)
        self.actualizar()

    def sincronizar(self, *_):
        """Deja el boton de reproducir y el slider iguales a los de 'Ver agente'."""
        self.btn_play.setText(self.origen.btn_play.text())
        self.slider.blockSignals(True)
        self.slider.setValue(self.origen.slider.value())
        self.slider.blockSignals(False)
        self.lbl_vel.setText(f"{self.slider.value()} jug./s")

    def _vacio(self, texto):
        self.estado.setText(texto)
        self.arbol.poner(None)
        self.leyenda.setText("")

    def actualizar(self):
        self.mensaje.setText(self.origen.mensaje.text())
        self.mensaje.setStyleSheet(self.origen.mensaje.styleSheet())
        self.sincronizar()
        clave, interno, pos, total = self.origen.interno_actual()
        self.tabla.setRowCount(0)
        if clave != 'mcts':
            self._vacio("Elige el agente MCTS en la pestaña «Ver agente» para ver su árbol.")
            return
        if not interno or not interno.get('arbol'):
            self._vacio("MCTS: aún no hay jugada. Pulsa «Paso».")
            return
        info = interno.get('info') or {}
        self.estado.setText(f"MCTS · jugada {pos} / {total} · acción elegida: {info.get('acción elegida', '-')}"
                            f" · {info.get('simulaciones', 0)} simulaciones")
        self.arbol.poner(interno['arbol'])
        cuadro = lambda rgb, t: f'<span style="color:{a_hex(rgb)}">&#9632;</span> {t}'
        self.leyenda.setText("<br>".join(
            [cuadro(COLOR_NODO[k], ETIQUETA_NODO[k]) for k in COLOR_NODO]
            + [cuadro(COLOR_OBS[k], f"Observación: {k}") for k in COLOR_OBS]
            + ["Línea amarilla = rama elegida.",
               "Nodo: <b>N</b> = visitas, <b>Q</b> = valor medio."]))
        filas = interno.get('acciones_raiz') or []
        mejor_q = max((f['Q'] for f in filas), default=None)
        self.tabla.setRowCount(len(filas))
        for i, f in enumerate(filas):
            notas = []
            if i == 0:
                notas.append("elegida")
            if f['Q'] == mejor_q:
                notas.append("mayor Q")
            for j, v in enumerate((f['etiqueta'], str(f['N']), f"{f['Q']:.3f}", ", ".join(notas))):
                it = QTableWidgetItem(v)
                if i == 0:
                    it.setForeground(QColor(*COLOR_RAMA))
                self.tabla.setItem(i, j, it)
        self.tabla.resizeColumnsToContents()


class PestanaJugar(QWidget):

    def __init__(self):
        super().__init__()
        self.partida = Partida(NIVEL_POR_DEFECTO)
        self.render = RenderizadorPygame()
        self.render.configurar(self.partida.env)
        self.reloj = QElapsedTimer()
        self.reloj.start()
        self.hover = None
        self.sucio = True

        self.tablero = TableroWidget()
        self.mensaje = QLabel()
        self.mensaje.setAlignment(Qt.AlignCenter)
        self.mensaje.setStyleSheet("font-size: 17px; font-weight: bold; padding: 6px;")
        self.panel = QLabel()
        self.panel.setTextFormat(Qt.MarkdownText)
        self.panel.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.panel.setWordWrap(True)
        self.panel.setMinimumWidth(280)
        self.panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.nivel = QComboBox()
        for k in ORDEN_NIVELES:
            self.nivel.addItem(NIVELES[k].nombre, k)
        self.nivel.setCurrentIndex(ORDEN_NIVELES.index(NIVEL_POR_DEFECTO))
        btn_nueva = QPushButton("Nueva partida")
        btn_rendir = QPushButton("Rendirse")

        izquierda = QVBoxLayout()
        izquierda.addWidget(self.tablero)
        izquierda.addWidget(self.mensaje)
        izquierda.addStretch(1)
        derecha = QVBoxLayout()
        derecha.addWidget(QLabel("Nivel de dificultad"))
        derecha.addWidget(self.nivel)
        fila = QHBoxLayout()
        fila.addWidget(btn_nueva)
        fila.addWidget(btn_rendir)
        derecha.addLayout(fila)
        derecha.addWidget(self.panel, 1)
        raiz = QHBoxLayout(self)
        raiz.addLayout(izquierda)
        raiz.addLayout(derecha, 1)                 # la columna derecha ocupa el ancho disponible

        self.tablero.clic.connect(self.al_clic)
        self.tablero.movimiento.connect(self.al_mover)
        self.nivel.currentIndexChanged.connect(self.al_cambiar_nivel)
        btn_nueva.clicked.connect(self.al_nueva)
        btn_rendir.clicked.connect(self.al_rendirse)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000 // FPS)
        self.actualizar_textos()
        self.tick()

    # -- bucle de dibujo ------------------------------------------------------
    def final(self):
        env = self.partida.env
        if env.ganado:
            return ("¡VICTORIA!", self.partida.mensaje)
        if env.agotado:
            return ("DERROTA", self.partida.mensaje)
        return None

    def tick(self):
        """Redibuja solo si cambio algo o hay animaciones en curso."""
        env = self.partida.env
        if self.sucio or self.render.hay_animacion(env, self.partida.revelado):
            ahora = self.reloj.elapsed()
            sup = self.render.dibujar(env, self.partida.revelado, ahora,
                                      hover=None if self.partida.terminada else self.hover,
                                      final=self.final())
            self.tablero.mostrar(sup)
            self.sucio = False

    def actualizar_textos(self):
        p = self.partida
        self.mensaje.setText(p.mensaje)
        self.mensaje.setStyleSheet(
            f"font-size: 17px; font-weight: bold; padding: 6px; color: {COLOR_TONO[p.tono]};")
        self.panel.setText(p.panel_markdown())

    # -- eventos --------------------------------------------------------------
    def al_mover(self, pos):
        celda = None if pos is None else self.render.celda_desde_pixel(*pos, self.partida.env)
        if celda != self.hover:
            self.hover = celda
            self.sucio = True

    def al_clic(self, x, y):
        celda = self.render.celda_desde_pixel(x, y, self.partida.env)
        if celda is None:
            return
        turnos = self.partida.env.turnos
        self.partida.disparar(*celda)
        if self.partida.env.turnos != turnos:               # el disparo se realizo
            self.render.lanzar_efectos(self.partida.env, self.partida.ultimo, self.reloj.elapsed())
        self.actualizar_textos()
        self.sucio = True

    def al_cambiar_nivel(self, _):
        self.partida.nuevo_nivel(self.nivel.currentData())
        self.render.configurar(self.partida.env)
        self.actualizar_textos()
        self.sucio = True

    def al_nueva(self):
        self.partida.nueva()
        self.render.configurar(self.partida.env)
        self.actualizar_textos()
        self.sucio = True

    def al_rendirse(self):
        self.partida.rendirse()
        self.actualizar_textos()
        self.sucio = True


class PestanaAgente(QWidget):
    """Elegir un agente y un nivel, y verlo jugar: paso a paso, hacia atras o en reproduccion."""
    cambio = Signal()            # la jugada vista o el agente cambiaron (la usa la pestaña del arbol)

    def __init__(self):
        super().__init__()
        self.sesion = None
        self.espejos = []                  # otros TableroWidget que muestran este mismo tablero
        self.render = RenderizadorPygame()
        self.reloj = QElapsedTimer()
        self.reloj.start()
        self.sucio = True

        self.tablero = TableroWidget()
        self.mensaje = QLabel()
        self.mensaje.setAlignment(Qt.AlignCenter)
        self.panel = QLabel()
        self.panel.setTextFormat(Qt.MarkdownText)
        self.panel.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.panel.setWordWrap(True)
        self.historial = QListWidget()
        self.historial.setMaximumHeight(120)

        self.cmb_agente = QComboBox()
        for clave, clase in AGENTES.items():
            self.cmb_agente.addItem(clase().name, clave)
        if 'caza' in AGENTES:                       # agente inicial: el heuristico, mas ilustrativo
            self.cmb_agente.setCurrentIndex(list(AGENTES).index('caza'))
        self.cmb_nivel = QComboBox()
        for k in ORDEN_NIVELES:
            self.cmb_nivel.addItem(NIVELES[k].nombre, k)
        self.cmb_nivel.setCurrentIndex(ORDEN_NIVELES.index(NIVEL_POR_DEFECTO))
        self.spin_semilla = QSpinBox()
        self.spin_semilla.setRange(0, 999_999)
        self.spin_semilla.setValue(1000)
        btn_azar = QPushButton("Semilla aleatoria")
        btn_reiniciar = QPushButton("Reiniciar partida")
        self.btn_atras = QPushButton("|◀ Atrás")
        self.btn_paso = QPushButton("Paso ▶|")
        self.btn_play = QPushButton("▶ Reproducir")
        self.btn_play.setCheckable(True)
        btn_fin = QPushButton("Terminar partida")
        self.lbl_pos = QLabel("Jugada 0 / 0")
        self.lbl_pos.setAlignment(Qt.AlignCenter)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(1, 20)
        self.slider.setValue(3)
        self.lbl_vel = QLabel()
        self.chk_mapa = QCheckBox("Mostrar el mapa de calor (lo que el agente valora)")
        self.chk_mapa.setChecked(True)
        self.chk_flota = QCheckBox("Mostrar la flota oculta")
        self.chk_orden = QCheckBox("Numerar el orden de los disparos")
        self.chk_orden.setChecked(True)
        self.chk_reglas = QCheckBox("Colorear casillas candidatas por regla (Caza-Remate)")
        self.chk_reglas.setChecked(True)
        self.reglas = QLabel()              # Caza-Remate: reglas y casillas candidatas
        self.reglas.setTextFormat(Qt.RichText)
        self.reglas.setWordWrap(True)
        self.reglas.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        izquierda = QVBoxLayout()
        izquierda.addWidget(self.tablero)
        izquierda.addWidget(self.mensaje)         # distancia fija bajo el tablero
        izquierda.addWidget(self.reglas)
        izquierda.addStretch(1)
        derecha = QVBoxLayout()
        for texto, w in (("Agente", self.cmb_agente), ("Nivel de dificultad", self.cmb_nivel)):
            derecha.addWidget(QLabel(texto))
            derecha.addWidget(w)
        derecha.addWidget(QLabel("Semilla (misma semilla = misma flota)"))
        fila = QHBoxLayout()
        fila.addWidget(self.spin_semilla, 1)
        fila.addWidget(btn_azar)
        derecha.addLayout(fila)
        derecha.addWidget(btn_reiniciar)
        fila = QHBoxLayout()
        fila.addWidget(self.btn_atras)
        fila.addWidget(self.btn_paso)
        fila.addWidget(self.btn_play)
        derecha.addLayout(fila)
        derecha.addWidget(self.lbl_pos)
        fila = QHBoxLayout()
        fila.addWidget(QLabel("Velocidad"))
        fila.addWidget(self.slider, 1)
        fila.addWidget(self.lbl_vel)
        derecha.addLayout(fila)
        derecha.addWidget(btn_fin)
        derecha.addWidget(self.chk_mapa)
        derecha.addWidget(self.chk_flota)
        derecha.addWidget(self.chk_orden)
        derecha.addWidget(self.chk_reglas)
        derecha.addWidget(self.panel, 1)
        derecha.addWidget(QLabel("Jugadas"))
        derecha.addWidget(self.historial)
        raiz = QHBoxLayout(self)
        raiz.addLayout(izquierda)
        raiz.addLayout(derecha)
        self.setMinimumWidth(1060)

        self.timer_juego = QTimer(self)            # reproduccion automatica
        self.timer_juego.timeout.connect(self.paso)
        self.timer = QTimer(self)                  # dibujo
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000 // FPS)

        self.cmb_agente.currentIndexChanged.connect(self.nueva_sesion)
        self.cmb_nivel.currentIndexChanged.connect(self.nueva_sesion)
        self.spin_semilla.editingFinished.connect(self.nueva_sesion)
        btn_azar.clicked.connect(self.semilla_aleatoria)
        btn_reiniciar.clicked.connect(self.nueva_sesion)
        self.btn_atras.clicked.connect(self.atras)
        self.btn_paso.clicked.connect(self.paso_manual)
        self.btn_play.toggled.connect(self.alternar_reproduccion)
        btn_fin.clicked.connect(self.terminar)
        self.slider.valueChanged.connect(self.cambiar_velocidad)
        for chk in (self.chk_mapa, self.chk_flota, self.chk_orden, self.chk_reglas):
            chk.toggled.connect(self.marcar_sucio)

        self.cambiar_velocidad()
        self.nueva_sesion()

    # -- sesion ---------------------------------------------------------------
    def nueva_sesion(self, *_):
        self.detener()
        self.historial.clear()
        try:
            self.sesion = SesionAgente(self.cmb_agente.currentData(),
                                       self.cmb_nivel.currentData(), self.spin_semilla.value())
        except FileNotFoundError as e:            # p. ej. DQN sin modelo para este nivel
            self.sesion = None
            self.mensaje.setText(str(e))
            self.mensaje.setStyleSheet(f"font-size: 14px; padding: 6px; color: {COLOR_TONO['derrota']};")
            self.panel.setText("")
            self.reglas.setText("")
            self.cambio.emit()
            self.lbl_pos.setText("Jugada 0 / 0")
            self.sucio = True
            return
        self.render.configurar(self.sesion.env)
        self.actualizar_textos()
        self.sucio = True

    def semilla_aleatoria(self):
        self.spin_semilla.setValue(random.randint(1, 999_999))
        self.nueva_sesion()

    # -- avanzar y retroceder ---------------------------------------------------
    def paso(self):
        """Avanza una jugada (la usan el boton y la reproduccion automatica)."""
        s = self.sesion
        if s is None or s.al_final:
            self.detener()
            return
        try:
            registro = s.paso()
        except Exception as e:                    # un agente con un error no debe cerrar la app
            self.detener()
            self.mensaje.setText(f"Error del agente: {e}")
            return
        if registro is not None:
            self.render.lanzar_efectos(s.env_vista(), registro['feedback'], self.reloj.elapsed())
            if self.historial.count() < registro['turno']:        # jugada nueva (no reproducida)
                self.historial.addItem(
                    f"{registro['turno']:>3}.  {coord_a_texto(*registro['coord'])}  →  "
                    f"{registro['resultado']}   ({registro['ms']:.2f} ms)")
            self.historial.setCurrentRow(registro['turno'] - 1)
        if s.al_final:
            self.detener()
        self.actualizar_textos()
        self.sucio = True

    def paso_manual(self):
        self.detener()
        self.paso()

    def atras(self):
        self.detener()
        s = self.sesion
        if s is not None and s.atras():
            self.render.limpiar_efectos()
            if s.posicion:
                self.historial.setCurrentRow(s.posicion - 1)
            else:
                self.historial.clearSelection()
            self.actualizar_textos()
            self.sucio = True

    def terminar(self):
        """Juega hasta el final de golpe (con agentes lentos la ventana tarda en responder)."""
        self.detener()
        while self.sesion is not None and not self.sesion.al_final:
            self.paso()

    # -- reproduccion ---------------------------------------------------------
    def alternar_reproduccion(self, activo):
        if activo and (self.sesion is None or self.sesion.al_final):
            self.btn_play.setChecked(False)
            return
        self.btn_play.setText("⏸ Pausa" if activo else "▶ Reproducir")
        if activo:
            self.timer_juego.start(self.intervalo())
        else:
            self.timer_juego.stop()

    def detener(self):
        self.timer_juego.stop()
        if self.btn_play.isChecked():
            self.btn_play.blockSignals(True)
            self.btn_play.setChecked(False)
            self.btn_play.blockSignals(False)
        self.btn_play.setText("▶ Reproducir")

    def intervalo(self) -> int:
        return int(1000 / self.slider.value())

    def cambiar_velocidad(self, *_):
        self.lbl_vel.setText(f"{self.slider.value()} jug./s")
        if self.timer_juego.isActive():
            self.timer_juego.start(self.intervalo())

    # -- dibujo ---------------------------------------------------------------
    def marcar_sucio(self, *_):
        self.sucio = True

    def actualizar_textos(self):
        s = self.sesion
        texto, tono = s.mensaje()
        self.mensaje.setText(texto)
        self.mensaje.setStyleSheet(
            f"font-size: 17px; font-weight: bold; padding: 6px; color: {COLOR_TONO.get(tono, COLOR_TONO['normal'])};")
        self.panel.setText(s.resumen_markdown())
        ult = s.ultima_vista()
        self.reglas.setText(self.texto_reglas(ult['interno'] if ult else None))
        self.cambio.emit()
        self.lbl_pos.setText(f"Jugada {s.posicion} / {len(s.historial)}")

    def interno_actual(self):
        """(clave del agente, estado interno de la jugada vista, jugada vista, jugadas hechas)."""
        s = self.sesion
        if s is None:
            return None, None, 0, 0
        ult = s.ultima_vista()
        return self.cmb_agente.currentData(), (ult['interno'] if ult else None), s.posicion, len(s.historial)

    def texto_reglas(self, interno) -> str:
        """Leyenda de Caza-Remate: reglas, casillas candidatas por regla y regla disparada."""
        if self.cmb_agente.currentData() != 'caza':
            return ""
        if not interno:
            return "<b>Reglas de Caza-Remate:</b> aún no hay jugada."
        activa = interno.get('categoria_activa')
        cats = interno.get('categorias') or {}
        lineas = ["<b>Reglas de Caza-Remate</b> (casillas candidatas)"]
        for k, texto in (interno.get('leyenda') or {}).items():
            cuantas = [coord_a_texto(*rc) for rc, v in cats.items() if v == k]
            if not cuantas:
                continue
            lista = ", ".join(sorted(cuantas)) if len(cuantas) <= 6 else f"{len(cuantas)} casillas"
            t = f"{texto}: {lista}"
            lineas.append(f'<span style="color:{a_hex(COLOR_REGLA[k])}">&#9632;</span> '
                          + (f"<b>{t} ← regla disparada</b>" if k == activa else t))
        ult = self.sesion.ultima_vista()
        lineas.append(f"Acción ejecutada: <b>{coord_a_texto(*ult['coord'])}</b> (borde amarillo)")
        return "<br>".join(lineas)

    def tick(self):
        s = self.sesion
        if s is None:
            return
        revelado = self.chk_flota.isChecked()
        env = s.env_vista()
        if self.sucio or self.render.hay_animacion(env, revelado):
            ult = s.ultima_vista()
            interno = ult['interno'] if ult else {}
            mapa = interno.get('mapa') if (ult and self.chk_mapa.isChecked()) else None
            cats = interno.get('categorias') if (ult and self.chk_reglas.isChecked()) else None
            if cats:
                cats = {rc: COLOR_REGLA[k] for rc, k in cats.items()}
            sup = self.render.dibujar(
                env, revelado, self.reloj.elapsed(),
                numeros=s.orden() if self.chk_orden.isChecked() else None,
                resaltar=ult['coord'] if ult else None, mapa=mapa, categorias=cats)
            self.tablero.mostrar(sup)
            for espejo in self.espejos:
                espejo.mostrar(sup)
            self.sucio = False


class Ventana(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Batalla Naval")
        pestanas = QTabWidget()
        self.jugar = PestanaJugar()
        pestanas.addTab(self.jugar, "Jugar")
        self.agente = PestanaAgente()
        pestanas.addTab(self.agente, "Ver agente")
        self.arbol = PestanaArbol(self.agente)
        pestanas.addTab(self.arbol, "Árbol MCTS")
        self.setCentralWidget(pestanas)


def main():
    app = QApplication(sys.argv)
    ventana = Ventana()
    ventana.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
