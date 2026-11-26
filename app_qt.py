"""
Interfaz de escritorio (PySide6) de Batalla Naval.
Pestañas: "Jugar", "Ver agente" (reglas de Caza-Remate, mapas de calor), "Árbol MCTS" (arbol de
busqueda), "Comparar" (tabla y graficas de varios agentes sobre la misma instancia) y "Editor de
instancias" (parametros y flota colocada a mano).

El tablero lo dibuja pygame en memoria (render_pygame.py, con sprites y animaciones) y
Qt lo muestra, le reenvia los clics y aporta los controles (nivel, botones, paneles).

Uso:
    pip install PySide6
    python app_qt.py
"""

import random
import sys

import pandas as pd
from PySide6.QtCore import Qt, QTimer, QElapsedTimer, QPointF, QRectF, QThread, Signal
from PySide6.QtGui import QColor, QFont, QImage, QKeySequence, QPainter, QPalette, QPen
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QGroupBox,
                               QHBoxLayout, QInputDialog, QLabel, QListWidget, QMainWindow,
                               QMessageBox, QProgressBar, QPushButton, QScrollArea, QSlider,
                               QSpinBox, QSizePolicy, QTableWidget, QTableWidgetItem, QTabWidget,
                               QVBoxLayout, QWidget, QFormLayout)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

import pygame

from agents import AGENTES
from comparar import dibujar_comparacion, ejecutar_comparacion, resumen_agentes
from dificultad import COLOCACIONES, NIVELES, ORDEN_NIVELES
from editor_instancia import EditorInstancia, MAX_LADO, MAX_LONGITUD, MIN_LADO
from instancia import CLAVE_PERSONALIZADA, Instancia, resolver
from partida import Partida
from render_pygame import AREA, C_FONDO, MARGEN, RenderizadorPygame, TAMANO
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


def colores_tema(paleta: QPalette):
    """(fondo, boton) del tema actual como QColor. En un tema oscuro el boton siempre queda mas
    claro que el fondo; ese mismo tono se usa en los botones del editor y en las graficas."""
    fondo = paleta.color(QPalette.Window)
    boton = paleta.color(QPalette.Button)
    if fondo.lightness() < 128 and boton.lightness() <= fondo.lightness():
        boton = fondo.lighter(135)
    return fondo, boton


def describir_instancia(inst: Instancia) -> str:
    c = inst.config
    return f"{c.nombre} {c.filas}x{c.columnas}, flota {'manual' if inst.manual else 'al azar'}"


def poner_opcion_personalizada(combo: QComboBox, inst: Instancia):
    """Añade (o actualiza) la opcion 'Personalizada' al final de un selector de nivel."""
    texto = f"Personalizada (flota {'manual' if inst.manual else 'al azar'})"
    i = combo.findData(CLAVE_PERSONALIZADA)
    if i < 0:
        combo.addItem(texto, CLAVE_PERSONALIZADA)
    else:
        combo.setItemText(i, texto)


def seleccionar_personalizada(combo: QComboBox):
    """Elige 'Personalizada' en el selector sin disparar currentIndexChanged."""
    combo.blockSignals(True)
    combo.setCurrentIndex(combo.findData(CLAVE_PERSONALIZADA))
    combo.blockSignals(False)


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
        self.personalizada = None            # Instancia creada en el editor (o None)
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
        self.btn_comparar = QPushButton("Comparar con los agentes")
        self.btn_comparar.setToolTip("Disponible al terminar la partida: los agentes juegan esta "
                                     "misma flota y se compara su desempeño con el tuyo.")
        self.btn_comparar.setEnabled(False)

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
        derecha.addWidget(self.btn_comparar)
        derecha.addWidget(self.panel, 1)
        raiz = QHBoxLayout(self)
        raiz.addLayout(izquierda)
        raiz.addLayout(derecha, 1)                 # la columna derecha ocupa el ancho disponible

        self.tablero.clic.connect(self.al_clic)
        self.tablero.movimiento.connect(self.al_mover)
        self.nivel.currentIndexChanged.connect(self.al_cambiar_nivel)
        btn_nueva.clicked.connect(self.al_nueva)
        btn_rendir.clicked.connect(self.al_rendirse)
        self.btn_comparar.clicked.connect(self.al_comparar)

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
        self.btn_comparar.setEnabled(p.terminada)

    # -- instancia personalizada ----------------------------------------------
    def poner_personalizada(self, inst: Instancia, seleccionar: bool = False):
        """Recibe la instancia del editor; si se pide (o ya estaba elegida) empieza a jugarla."""
        self.personalizada = inst
        poner_opcion_personalizada(self.nivel, inst)
        if seleccionar or self.nivel.currentData() == CLAVE_PERSONALIZADA:
            seleccionar_personalizada(self.nivel)
            self.al_cambiar_nivel(None)

    def al_comparar(self):
        DialogoHumanoVsMaquina(self.partida, self).exec()

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
        self.partida.nueva_instancia(resolver(self.nivel.currentData(), self.personalizada))
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
        self.personalizada = None          # Instancia creada en el editor (o None)
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
        self.lbl_marg = QLabel("Mapa de calor del agente bayesiano")
        self.cmb_marg = QComboBox()                 # combinado o la marginal de un barco
        self.lbl_marg.hide()
        self.cmb_marg.hide()
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
        derecha.addWidget(self.lbl_marg)
        derecha.addWidget(self.cmb_marg)
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
        self.cmb_marg.currentIndexChanged.connect(self.marcar_sucio)
        for chk in (self.chk_mapa, self.chk_flota, self.chk_orden, self.chk_reglas):
            chk.toggled.connect(self.marcar_sucio)

        self.cambiar_velocidad()
        self.nueva_sesion()

    # -- sesion ---------------------------------------------------------------
    def nueva_sesion(self, *_):
        self.detener()
        self.historial.clear()
        try:
            inst = resolver(self.cmb_nivel.currentData(), self.personalizada)
            self.sesion = SesionAgente(self.cmb_agente.currentData(), inst.clave,
                                       self.spin_semilla.value(), instancia=inst)
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

    def poner_personalizada(self, inst: Instancia, seleccionar: bool = False):
        """Recibe la instancia del editor; si se pide (o ya estaba elegida) la juega el agente."""
        self.personalizada = inst
        poner_opcion_personalizada(self.cmb_nivel, inst)
        if seleccionar or self.cmb_nivel.currentData() == CLAVE_PERSONALIZADA:
            seleccionar_personalizada(self.cmb_nivel)
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
        self.actualizar_marginales(ult['interno'] if ult else None)
        self.cambio.emit()
        self.lbl_pos.setText(f"Jugada {s.posicion} / {len(s.historial)}")

    def interno_actual(self):
        """(clave del agente, estado interno de la jugada vista, jugada vista, jugadas hechas)."""
        s = self.sesion
        if s is None:
            return None, None, 0, 0
        ult = s.ultima_vista()
        return self.cmb_agente.currentData(), (ult['interno'] if ult else None), s.posicion, len(s.historial)

    def actualizar_marginales(self, interno):
        """Llena el selector con 'Combinado' y un barco por cada marginal (solo agente bayesiano)."""
        marg = (interno or {}).get('marginales') or []
        actual = self.cmb_marg.currentData()
        self.cmb_marg.blockSignals(True)
        self.cmb_marg.clear()
        self.cmb_marg.addItem("Combinado: P(barco | evidencia)", None)
        for m in marg:
            self.cmb_marg.addItem(f"Solo el barco: {m['etiqueta']}", m['etiqueta'])
        i = self.cmb_marg.findData(actual) if actual is not None else 0
        self.cmb_marg.setCurrentIndex(max(i, 0))              # si ese barco ya se hundio, vuelve al combinado
        self.cmb_marg.blockSignals(False)
        self.lbl_marg.setVisible(bool(marg))
        self.cmb_marg.setVisible(bool(marg))

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
            barco = self.cmb_marg.currentData()
            if mapa is not None and barco is not None:        # marginal de un barco concreto
                for m in interno.get('marginales') or []:
                    if m['etiqueta'] == barco:
                        mapa = m['mapa']
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


PALETA_BARCOS = [QColor(79, 163, 224), QColor(240, 160, 48), QColor(88, 194, 125),
                 QColor(224, 96, 90), QColor(169, 139, 220), QColor(217, 194, 74),
                 QColor(92, 200, 200)]


class TableroEditorWidget(QWidget):
    """
    Tablero del editor de instancias: dibuja el modelo (EditorInstancia) con QPainter y emite los
    clics. La esquina superior-izquierda del barco queda en la casilla donde se hace clic.
    """
    clic = Signal(int, int, object)          # fila, columna, boton del raton
    girar = Signal()                         # rueda del raton

    def __init__(self, modelo: EditorInstancia):
        super().__init__()
        self.modelo = modelo
        self.activo = None                   # nombre del barco que se esta colocando
        self.horizontal = True
        self.hover = None
        self.setFixedSize(*TAMANO)
        self.setMouseTracking(True)

    @property
    def lado(self) -> int:
        return AREA // max(self.modelo.filas, self.modelo.columnas)

    def celda_desde_pixel(self, x, y):
        if x < MARGEN or y < MARGEN:
            return None
        c, r = int((x - MARGEN) // self.lado), int((y - MARGEN) // self.lado)
        if 0 <= r < self.modelo.filas and 0 <= c < self.modelo.columnas:
            return r, c
        return None

    def paintEvent(self, _):
        m, t = self.modelo, self.lado
        ancho, alto = m.columnas * t, m.filas * t
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(*C_FONDO))
        p.fillRect(MARGEN, MARGEN, ancho, alto, QColor(24, 64, 96))          # agua
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        for i in range(m.columnas + 1):
            p.drawLine(MARGEN + i * t, MARGEN, MARGEN + i * t, MARGEN + alto)
        for i in range(m.filas + 1):
            p.drawLine(MARGEN, MARGEN + i * t, MARGEN + ancho, MARGEN + i * t)

        p.setPen(QColor(130, 160, 178))                                      # etiquetas A-L / 1-12
        for i in range(m.columnas):
            p.drawText(QRectF(MARGEN + i * t, 0, t, MARGEN), Qt.AlignCenter, chr(65 + i))
        for i in range(m.filas):
            p.drawText(QRectF(0, MARGEN + i * t, MARGEN, t), Qt.AlignCenter, str(i + 1))

        fuente = p.font()
        fuente.setBold(True)
        fuente.setPointSize(max(7, min(11, t // 6)))
        p.setFont(fuente)
        for k, nombre in enumerate(m.flota):                                 # barcos colocados
            if nombre not in m.colocados:
                continue
            r, c, o = m.colocados[nombre]
            n = m.flota[nombre]
            w, h = (n * t, t) if o == 'H' else (t, n * t)
            rect = QRectF(MARGEN + c * t + 3, MARGEN + r * t + 3, w - 6, h - 6)
            color = PALETA_BARCOS[k % len(PALETA_BARCOS)]
            elegido = nombre == self.activo
            p.setPen(QPen(QColor(255, 235, 90) if elegido else color.darker(160), 3 if elegido else 2))
            p.setBrush(color)
            p.drawRoundedRect(rect, 8, 8)
            largo = rect.width() if o == 'H' else rect.height()
            texto = p.fontMetrics().elidedText(f"{nombre} ({n})", Qt.ElideRight, int(largo) - 8)
            p.setPen(QColor(10, 20, 30))
            if o == 'H':
                p.drawText(rect, Qt.AlignCenter, texto)
            else:                                                            # texto girado
                p.save()
                p.translate(rect.center())
                p.rotate(90)
                p.drawText(QRectF(-rect.height() / 2, -rect.width() / 2, rect.height(), rect.width()),
                           Qt.AlignCenter, texto)
                p.restore()

        if self.hover is not None:                                           # vista previa
            r, c = self.hover
            if m.nombre_en(r, c):                                            # clic = mover ese barco
                p.fillRect(MARGEN + c * t, MARGEN + r * t, t, t, QColor(255, 235, 90, 70))
            elif self.activo in m.flota:
                o = 'H' if self.horizontal else 'V'
                bien = m.puede_colocar(self.activo, r, c, o)
                color = QColor(90, 220, 130, 120) if bien else QColor(235, 80, 70, 130)
                for rr, cc in m.posiciones(r, c, m.flota[self.activo], o):
                    if 0 <= rr < m.filas and 0 <= cc < m.columnas:
                        p.fillRect(MARGEN + cc * t + 1, MARGEN + rr * t + 1, t - 2, t - 2, color)

    def mousePressEvent(self, e):
        celda = self.celda_desde_pixel(e.position().x(), e.position().y())
        if celda is not None:
            self.clic.emit(celda[0], celda[1], e.button())

    def mouseMoveEvent(self, e):
        celda = self.celda_desde_pixel(e.position().x(), e.position().y())
        if celda != self.hover:
            self.hover = celda
            self.update()

    def leaveEvent(self, _):
        self.hover = None
        self.update()

    def wheelEvent(self, e):
        self.girar.emit()


class PestanaEditor(QWidget):
    """
    Editor de instancias: parametros del entorno (tablero, flota, limite de disparos, ruido,
    adyacencia, visibilidad de la flota) y colocacion manual de los barcos (estado inicial).
    La instancia resultante se puede guardar/cargar en JSON y usar en Jugar, Ver agente o Comparar.
    """
    usar = Signal(str, object)               # destino ('jugar' | 'agente' | 'comparar'), Instancia

    def __init__(self):
        super().__init__()
        self.modelo = EditorInstancia()
        self._cargando = False
        self.tablero = TableroEditorWidget(self.modelo)
        self.tablero.activo = next(iter(self.modelo.flota))
        self.estado = QLabel()
        self.estado.setWordWrap(True)
        self.estado.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.estado.setMinimumHeight(60)

        # -- parametros --
        self.spin_filas = QSpinBox()
        self.spin_cols = QSpinBox()
        for sp in (self.spin_filas, self.spin_cols):
            sp.setRange(MIN_LADO, MAX_LADO)
        self.chk_sin_limite = QCheckBox("Sin límite de disparos")
        self.spin_limite = QSpinBox()
        self.spin_limite.setRange(1, 999)
        self.spin_ruido = QSpinBox()
        self.spin_ruido.setRange(0, 49)
        self.spin_ruido.setSuffix(" %")
        self.spin_ruido.setToolTip("Probabilidad de que el sonar reporte mal un disparo (agua ↔ impacto).")
        self.cmb_colocacion = QComboBox()
        self.cmb_colocacion.addItems(list(COLOCACIONES))
        self.cmb_colocacion.setToolTip("Solo afecta a la colocación aleatoria: 'bordes' sesga los barcos hacia los bordes.")
        self.chk_adyacentes = QCheckBox("Permitir barcos en contacto")
        self.chk_visible = QCheckBox("Mostrar la flota restante al jugador")
        grupo_params = QGroupBox("Parámetros del entorno")
        form = QFormLayout(grupo_params)
        form.addRow("Filas", self.spin_filas)
        form.addRow("Columnas", self.spin_cols)
        form.addRow(self.chk_sin_limite)
        form.addRow("Máx. disparos", self.spin_limite)
        form.addRow("Ruido del sonar", self.spin_ruido)
        form.addRow("Colocación aleatoria", self.cmb_colocacion)
        form.addRow(self.chk_adyacentes)
        form.addRow(self.chk_visible)

        # -- flota --
        self.lista = QListWidget()
        self.lista.setMaximumHeight(140)
        btn_add, btn_del = QPushButton("Añadir…"), QPushButton("Quitar")
        btn_len, btn_clasica = QPushButton("Longitud…"), QPushButton("Flota clásica")
        grupo_flota = QGroupBox("Flota (elige el barco que vas a colocar)")
        v = QVBoxLayout(grupo_flota)
        v.addWidget(self.lista)
        for fila_btns in ((btn_add, btn_del), (btn_len, btn_clasica)):
            fila = QHBoxLayout()
            for b in fila_btns:
                fila.addWidget(b)
            v.addLayout(fila)

        # -- colocacion --
        self.btn_girar = QPushButton()
        self.btn_girar.setShortcut(QKeySequence("R"))
        btn_azar, btn_limpiar = QPushButton("Colocar al azar"), QPushButton("Limpiar tablero")
        self.chk_manual = QCheckBox("Usar mi disposición (si no, la flota se coloca al azar según la semilla)")
        self.chk_manual.setStyleSheet("QCheckBox { padding: 2px 0; }")
        grupo_col = QGroupBox("Estado inicial (posición de los barcos)")
        v = QVBoxLayout(grupo_col)
        v.addWidget(self.btn_girar)
        fila = QHBoxLayout()
        fila.addWidget(btn_azar)
        fila.addWidget(btn_limpiar)
        v.addLayout(fila)
        v.addWidget(self.chk_manual)

        # -- usar / guardar --
        btn_jugar = QPushButton("Jugar con esta instancia")
        btn_agente = QPushButton("Ver agentes en esta instancia")
        btn_comparar = QPushButton("Comparar algoritmos en esta instancia")
        btn_guardar, btn_cargar = QPushButton("Guardar…"), QPushButton("Cargar…")
        grupo_usar = QGroupBox("Usar la instancia")
        v = QVBoxLayout(grupo_usar)
        for b in (btn_jugar, btn_agente, btn_comparar):
            v.addWidget(b)
        fila = QHBoxLayout()
        fila.addWidget(btn_guardar)
        fila.addWidget(btn_cargar)
        v.addLayout(fila)

        contenido = QWidget()
        col = QVBoxLayout(contenido)
        for g in (grupo_params, grupo_flota, grupo_col, grupo_usar):
            col.addWidget(g)
        col.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(contenido)
        scroll.setMinimumWidth(390)
        scroll.setFrameShape(QScrollArea.NoFrame)          # mismo fondo que las otras pestañas
        scroll.viewport().setAutoFillBackground(False)
        contenido.setAutoFillBackground(False)

        izquierda = QVBoxLayout()
        izquierda.addWidget(self.tablero)
        izquierda.addWidget(self.estado)
        izquierda.addStretch(1)
        raiz = QHBoxLayout(self)
        raiz.addLayout(izquierda)
        raiz.addWidget(scroll, 1)

        # -- conexiones --
        self.tablero.clic.connect(self.al_clic)
        self.tablero.girar.connect(self.al_girar)
        self.btn_girar.clicked.connect(self.al_girar)
        for w in (self.spin_filas, self.spin_cols, self.spin_limite, self.spin_ruido):
            w.valueChanged.connect(self.al_cambiar_parametros)
        for w in (self.chk_sin_limite, self.chk_adyacentes, self.chk_visible):
            w.toggled.connect(self.al_cambiar_parametros)
        self.cmb_colocacion.currentIndexChanged.connect(self.al_cambiar_parametros)
        self.lista.currentRowChanged.connect(self.al_elegir_barco)
        btn_add.clicked.connect(self.al_anadir_barco)
        btn_del.clicked.connect(self.al_quitar_barco)
        btn_len.clicked.connect(self.al_cambiar_longitud)
        btn_clasica.clicked.connect(self.al_flota_clasica)
        btn_azar.clicked.connect(self.al_colocar_azar)
        btn_limpiar.clicked.connect(self.al_limpiar)
        btn_jugar.clicked.connect(lambda *_: self.al_usar('jugar'))
        btn_agente.clicked.connect(lambda *_: self.al_usar('agente'))
        btn_comparar.clicked.connect(lambda *_: self.al_usar('comparar'))
        btn_guardar.clicked.connect(self.al_guardar)
        btn_cargar.clicked.connect(self.al_cargar)

        self.aplicar_estilo()
        self.sincronizar_controles()
        self.refrescar()

    def aplicar_estilo(self):
        """Cajas de seccion sin borde (solo el titulo) y botones mas claros que el fondo."""
        _, boton = colores_tema(self.palette())
        texto = self.palette().color(QPalette.ButtonText).name()
        self.setStyleSheet(f"""
            QGroupBox {{ border: none; margin-top: 18px; padding-top: 2px; font-weight: bold; }}
            QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left;
                                left: 0px; padding: 0px; }}
            QGroupBox QWidget {{ font-weight: normal; }}
            QPushButton {{ background-color: {boton.name()}; color: {texto}; border: none;
                           border-radius: 5px; padding: 6px 12px; }}
            QPushButton:hover {{ background-color: {boton.lighter(115).name()}; }}
            QPushButton:pressed {{ background-color: {boton.darker(115).name()}; }}
            QPushButton:disabled {{ color: {self.palette().color(QPalette.Disabled, QPalette.ButtonText).name()}; }}
        """)

    # -- sincronizacion modelo <-> controles ---------------------------------------
    def sincronizar_controles(self):
        m = self.modelo
        self._cargando = True
        self.spin_filas.setValue(m.filas)
        self.spin_cols.setValue(m.columnas)
        self.chk_sin_limite.setChecked(m.max_disparos is None)
        self.spin_limite.setValue(m.max_disparos if m.max_disparos is not None
                                  else max(1, 3 * sum(m.flota.values())))
        self.spin_limite.setEnabled(m.max_disparos is not None)
        self.spin_ruido.setValue(int(round(100 * m.prob_ruido)))
        self.cmb_colocacion.setCurrentText(m.colocacion)
        self.chk_adyacentes.setChecked(m.permitir_adyacentes)
        self.chk_visible.setChecked(m.mostrar_flota_restante)
        self._cargando = False

    def al_cambiar_parametros(self, *_):
        if self._cargando:
            return
        m = self.modelo
        quitados = m.cambiar_dimensiones(self.spin_filas.value(), self.spin_cols.value())
        for n in m.cambiar_adyacencia(self.chk_adyacentes.isChecked()):
            if n not in quitados:
                quitados.append(n)
        m.max_disparos = None if self.chk_sin_limite.isChecked() else self.spin_limite.value()
        m.prob_ruido = self.spin_ruido.value() / 100
        m.colocacion = self.cmb_colocacion.currentText()
        m.mostrar_flota_restante = self.chk_visible.isChecked()
        self.spin_limite.setEnabled(not self.chk_sin_limite.isChecked())
        if quitados:
            self.tablero.activo = quitados[0]
        self.refrescar(("Se quitaron del tablero por no ser válidos con estos parámetros: "
                        + ", ".join(quitados)) if quitados else None)

    def llenar_lista(self):
        m = self.modelo
        self.lista.blockSignals(True)
        self.lista.clear()
        for nombre, largo in m.flota.items():
            marca = "✔ colocado" if nombre in m.colocados else "pendiente"
            self.lista.addItem(f"{nombre} ({largo}) — {marca}")
        if self.tablero.activo in m.flota:
            self.lista.setCurrentRow(list(m.flota).index(self.tablero.activo))
        self.lista.blockSignals(False)

    def refrescar(self, mensaje: str = None):
        m = self.modelo
        if self.tablero.activo not in m.flota:               # el barco activo ya no existe
            self.tablero.activo = m.pendientes[0] if m.pendientes else None
        self.llenar_lista()
        self.btn_girar.setText("Orientación: " + ("horizontal" if self.tablero.horizontal else "vertical")
                               + "  (tecla R o rueda del ratón)")
        self.tablero.update()
        if mensaje is None:
            if self.tablero.activo:
                mensaje = (f"Colocando: {self.tablero.activo} ({m.flota[self.tablero.activo]}). "
                           "Clic = colocar · clic sobre un barco = moverlo · clic derecho = quitarlo.")
            elif m.completa:
                mensaje = "Flota completa. Ya puedes usar la instancia o guardarla."
            else:
                mensaje = "Elige un barco en la lista para colocarlo."
        casillas = sum(m.flota.values())
        self.estado.setText(f"{mensaje}\nColocados {len(m.colocados)} de {len(m.flota)} barcos · "
                            f"{casillas} casillas de barco en {m.filas * m.columnas} "
                            f"({casillas / (m.filas * m.columnas):.0%})")

    # -- tablero -------------------------------------------------------------------
    def al_girar(self, *_):
        self.tablero.horizontal = not self.tablero.horizontal
        self.refrescar()

    def al_elegir_barco(self, fila):
        nombres = list(self.modelo.flota)
        if 0 <= fila < len(nombres):
            self.tablero.activo = nombres[fila]
            self.refrescar()

    def al_clic(self, r, c, boton):
        m = self.modelo
        nombre = m.nombre_en(r, c)
        if boton == Qt.RightButton:
            if nombre:
                m.quitar(nombre)
                self.tablero.activo = nombre
                self.refrescar(f"Quitaste el barco {nombre}.")
            return
        if boton != Qt.LeftButton:
            return
        if nombre:                                            # recoger el barco para moverlo
            m.quitar(nombre)
            self.tablero.activo = nombre
            self.chk_manual.setChecked(True)
            self.refrescar(f"Moviendo {nombre}: haz clic en la nueva posición (R para girarlo).")
            return
        activo = self.tablero.activo
        if activo is None:
            self.refrescar("Elige un barco en la lista para colocarlo.")
            return
        if m.colocar(activo, r, c, 'H' if self.tablero.horizontal else 'V'):
            self.chk_manual.setChecked(True)
            self.tablero.activo = m.pendientes[0] if m.pendientes else None
            self.refrescar()
        else:
            motivo = "se sale del tablero, choca con otro barco" + \
                     (" o toca a otro barco" if not m.permitir_adyacentes else "")
            self.refrescar(f"No se puede colocar el {activo} ahí: {motivo}.")

    def al_colocar_azar(self):
        try:
            self.modelo.colocar_al_azar(random.randint(1, 999_999))
        except (ValueError, RuntimeError) as e:
            QMessageBox.warning(self, "No se pudo colocar la flota", str(e))
            return
        self.chk_manual.setChecked(True)
        self.tablero.activo = None
        self.refrescar("Disposición aleatoria colocada: puedes mover o quitar cualquier barco.")

    def al_limpiar(self):
        self.modelo.limpiar()
        self.tablero.activo = self.modelo.pendientes[0]
        self.refrescar("Tablero vacío.")

    # -- flota ---------------------------------------------------------------------
    def al_anadir_barco(self):
        nombre, ok = QInputDialog.getText(self, "Nuevo barco", "Nombre del barco:")
        if not ok:
            return
        largo, ok = QInputDialog.getInt(self, "Nuevo barco", "Longitud (casillas):", 3, 1, MAX_LONGITUD)
        if not ok:
            return
        try:
            self.modelo.poner_barco(nombre, largo)
        except ValueError as e:
            QMessageBox.warning(self, "Barco no válido", str(e))
            return
        self.tablero.activo = nombre.strip()
        self.refrescar()

    def al_quitar_barco(self):
        if self.tablero.activo is None:
            return
        try:
            self.modelo.quitar_barco(self.tablero.activo)
        except ValueError as e:
            QMessageBox.warning(self, "No se puede quitar", str(e))
            return
        self.tablero.activo = None
        self.refrescar()

    def al_cambiar_longitud(self):
        nombre = self.tablero.activo
        if nombre is None:
            return
        largo, ok = QInputDialog.getInt(self, "Longitud", f"Longitud de «{nombre}»:",
                                        self.modelo.flota[nombre], 1, MAX_LONGITUD)
        if ok:
            self.modelo.poner_barco(nombre, largo)
            self.refrescar()

    def al_flota_clasica(self):
        self.modelo.restaurar_flota()
        self.tablero.activo = next(iter(self.modelo.flota))
        self.refrescar("Flota clásica restaurada (5 barcos).")

    # -- usar, guardar y cargar ----------------------------------------------------
    def crear_instancia(self):
        """Instancia con el estado actual del editor, o None (avisando) si no es valida."""
        try:
            return self.modelo.a_instancia(manual=self.chk_manual.isChecked())
        except (ValueError, RuntimeError) as e:
            QMessageBox.warning(self, "Instancia no válida", str(e))
            self.refrescar(f"Instancia no válida: {e}")
            return None

    def al_usar(self, destino):
        inst = self.crear_instancia()
        if inst is not None:
            self.refrescar(f"Instancia lista: {describir_instancia(inst)}.")
            self.usar.emit(destino, inst)

    def al_guardar(self):
        inst = self.crear_instancia()
        if inst is None:
            return
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar instancia", "instancia.json",
                                              "Instancias (*.json)")
        if not ruta:
            return
        try:
            inst.guardar(ruta)
        except OSError as e:
            QMessageBox.warning(self, "No se pudo guardar", str(e))
            return
        self.refrescar(f"Instancia guardada en {ruta}")

    def al_cargar(self):
        ruta, _ = QFileDialog.getOpenFileName(self, "Cargar instancia", "", "Instancias (*.json)")
        if not ruta:
            return
        try:
            inst = Instancia.cargar(ruta)
        except (ValueError, OSError, RuntimeError) as e:
            QMessageBox.warning(self, "No se pudo cargar", str(e))
            return
        self.modelo.cargar(inst)
        self.chk_manual.setChecked(inst.manual)
        self.tablero.activo = self.modelo.pendientes[0] if self.modelo.pendientes else None
        self.sincronizar_controles()
        self.refrescar(f"Instancia cargada: {describir_instancia(inst)}.")


class TrabajoComparacion(QThread):
    """Ejecuta comparar.ejecutar_comparacion en otro hilo para que la ventana no se congele."""
    progreso = Signal(int, int, str)
    listo = Signal(object, object)           # DataFrame (o None), {clave: error}

    def __init__(self, claves, instancia, n, seed_base, parent=None):
        super().__init__(parent)
        self.claves, self.instancia, self.n, self.seed_base = list(claves), instancia, n, seed_base
        self.cancelado = False

    def cancelar(self):
        self.cancelado = True

    def run(self):
        try:
            df, errores = ejecutar_comparacion(
                self.claves, self.instancia, self.n, self.seed_base,
                progreso=lambda h, t, txt: self.progreso.emit(h, t, txt),
                cancelar=lambda: self.cancelado)
        except Exception as e:               # no dejar morir el hilo en silencio
            df, errores = None, {'*': f"{type(e).__name__}: {e}"}
        self.listo.emit(df, errores)


# columnas donde se resalta el mejor agente: True = mayor es mejor, False = menor es mejor
MEJOR_COLUMNA = {'Victorias (%)': True, 'Disparos (media)': False, 'Eficiencia': True,
                 'Óptimas (%)': True, 'Brecha al óptimo': False, 'Recompensa acum.': True,
                 'Tiempo/jugada (ms)': False, 'Tiempo/partida (s)': False,
                 'Evaluaciones': False, 'Memoria máx.': False, 'Tiempo CPU (s)': False, 
                 'Nodos generados': False, 'Nodos expandidos': False}
DECIMALES_COLUMNA = {'Partidas': 0, 'Disparos (mín.)': 0, 'Disparos (máx.)': 0, 'Evaluaciones': 0,
                     'Memoria máx.': 0, 'Tiempo/partida (s)': 3, 'Tiempo CPU (s)': 3, 'Nodos generados': 0, 'Nodos expandidos': 0}


def llenar_tabla(tabla: QTableWidget, resumen: pd.DataFrame):
    """Muestra una fila por agente; resalta en verde el mejor valor de cada metrica comparable."""
    tabla.clear()
    tabla.setRowCount(len(resumen))
    tabla.setColumnCount(len(resumen.columns))
    tabla.setHorizontalHeaderLabels(list(resumen.columns))
    tabla.setVerticalHeaderLabels([str(n) for n in resumen.index])
    negrita = QFont()
    negrita.setBold(True)
    for j, col in enumerate(resumen.columns):
        serie = resumen[col]
        mejor = None
        if col in MEJOR_COLUMNA and serie.nunique() > 1:
            mejor = serie.max() if MEJOR_COLUMNA[col] else serie.min()
        for i, v in enumerate(serie):
            texto = "–" if pd.isna(v) else f"{v:.{DECIMALES_COLUMNA.get(col, 2)}f}"
            it = QTableWidgetItem(texto)
            it.setTextAlignment(Qt.AlignCenter)
            if mejor is not None and v == mejor:
                it.setForeground(QColor(110, 230, 140))
                it.setFont(negrita)
            tabla.setItem(i, j, it)
    tabla.resizeColumnsToContents()


class PestanaComparar(QWidget):
    """
    Compara varios agentes sobre la misma instancia: la partida i usa la semilla (base + i) para
    todos, asi que comparten flota y ruido. Muestra la tabla de metricas y graficas comparativas.
    """

    def __init__(self):
        super().__init__()
        self.personalizada = None
        self.instancia = None              # instancia de la ultima comparacion
        self.trabajo = None
        self.df = None

        self.cmb_nivel = QComboBox()
        for k in ORDEN_NIVELES:
            self.cmb_nivel.addItem(NIVELES[k].nombre, k)
        self.cmb_nivel.setCurrentIndex(ORDEN_NIVELES.index(NIVEL_POR_DEFECTO))
        self.chk_agentes = {}
        grupo_agentes = QGroupBox("Agentes a comparar")
        v = QVBoxLayout(grupo_agentes)
        for clave, clase in AGENTES.items():
            chk = QCheckBox(clase().name)
            chk.setChecked(True)
            self.chk_agentes[clave] = chk
            v.addWidget(chk)
        self.spin_n = QSpinBox()
        self.spin_n.setRange(1, 500)
        self.spin_n.setValue(10)
        self.spin_n.setToolTip("1 = una sola instancia (misma semilla para todos); más = lote de partidas.")
        self.spin_semilla = QSpinBox()
        self.spin_semilla.setRange(0, 999_999)
        self.spin_semilla.setValue(1000)
        self.btn_ejecutar = QPushButton("Ejecutar comparación")
        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.setEnabled(False)
        self.btn_csv = QPushButton("Exportar partidas (CSV)…")
        self.btn_csv.setEnabled(False)
        self.barra = QProgressBar()
        self.lbl_estado = QLabel("Elige agentes y pulsa «Ejecutar comparación».")
        self.lbl_estado.setWordWrap(True)
        self.lbl_estado.setTextFormat(Qt.RichText)
        self.lbl_estado.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        form = QFormLayout()
        form.addRow("Nivel / instancia", self.cmb_nivel)
        form.addRow("Partidas por agente", self.spin_n)
        form.addRow("Semilla base", self.spin_semilla)
        izq = QVBoxLayout()
        izq.addLayout(form)
        izq.addWidget(QLabel("Misma semilla = misma flota para todos los agentes."))
        izq.addWidget(grupo_agentes)
        izq.addWidget(self.btn_ejecutar)
        izq.addWidget(self.btn_cancelar)
        izq.addWidget(self.barra)
        izq.addWidget(self.lbl_estado, 1)
        izq.addWidget(self.btn_csv)
        panel = QWidget()
        panel.setLayout(izq)
        panel.setFixedWidth(300)

        self.tabla = QTableWidget(0, 0)
        self.tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabla.setSelectionMode(QTableWidget.NoSelection)
        self.tabla.setMaximumHeight(200)
        self.figura = Figure(figsize=(9, 5.2))
        self.figura.patch.set_facecolor('#2d2d2d')
        self.canvas = FigureCanvasQTAgg(self.figura)
        self.canvas.setMinimumHeight(360)
        der = QVBoxLayout()
        der.addWidget(QLabel("<b>Tabla comparativa</b> (en verde, el mejor de cada métrica)"))
        der.addWidget(self.tabla)
        der.addWidget(self.canvas, 1)

        raiz = QHBoxLayout(self)
        raiz.addWidget(panel)
        raiz.addLayout(der, 1)

        self.btn_ejecutar.clicked.connect(self.ejecutar)
        self.btn_cancelar.clicked.connect(self.cancelar)
        self.btn_csv.clicked.connect(self.exportar)

    def poner_personalizada(self, inst: Instancia, seleccionar: bool = False):
        self.personalizada = inst
        poner_opcion_personalizada(self.cmb_nivel, inst)
        if seleccionar:
            seleccionar_personalizada(self.cmb_nivel)

    # -- ejecucion -----------------------------------------------------------------
    def alternar_ejecucion(self, ejecutando: bool):
        self.btn_ejecutar.setEnabled(not ejecutando)
        self.btn_cancelar.setEnabled(ejecutando)
        for w in (self.cmb_nivel, self.spin_n, self.spin_semilla, *self.chk_agentes.values()):
            w.setEnabled(not ejecutando)

    def ejecutar(self):
        claves = [k for k, chk in self.chk_agentes.items() if chk.isChecked()]
        if not claves:
            self.lbl_estado.setText("Elige al menos un agente.")
            return
        try:
            inst = resolver(self.cmb_nivel.currentData(), self.personalizada)
        except ValueError as e:
            self.lbl_estado.setText(str(e))
            return
        self.instancia = inst
        n, semilla = self.spin_n.value(), self.spin_semilla.value()
        self.alternar_ejecucion(True)
        self.barra.setRange(0, len(claves) * n)
        self.barra.setValue(0)
        self.lbl_estado.setText(f"Ejecutando sobre {describir_instancia(inst)}…")
        self.trabajo = TrabajoComparacion(claves, inst, n, semilla, self)
        self.trabajo.progreso.connect(self.al_progreso)
        self.trabajo.listo.connect(self.al_terminar)
        self.trabajo.start()

    def cancelar(self):
        if self.trabajo is not None:
            self.trabajo.cancelar()
            self.lbl_estado.setText("Cancelando…")

    def detener(self):
        """Para el hilo si sigue corriendo (al cerrar la ventana)."""
        if self.trabajo is not None and self.trabajo.isRunning():
            self.trabajo.cancelar()
            self.trabajo.wait()

    def al_progreso(self, hechas, total, texto):
        self.barra.setMaximum(total)
        self.barra.setValue(hechas)
        self.lbl_estado.setText(texto)

    def al_terminar(self, df, errores):
        cancelado = self.trabajo.cancelado
        self.trabajo.wait()
        self.trabajo.deleteLater()
        self.trabajo = None
        self.alternar_ejecucion(False)
        avisos = [f'<span style="color:#ff5a50">{clave if clave != "*" else "Error"}: {msg}</span>'
                  for clave, msg in errores.items()]
        if df is None or df.empty:
            self.lbl_estado.setText("<br>".join(["Sin resultados."] + avisos))
            return
        self.df = df
        llenar_tabla(self.tabla, resumen_agentes(df))
        dibujar_comparacion(self.figura, df, self.instancia.config.casillas_barco,
                            fondo_ejes=colores_tema(self.palette())[1].name())
        self.canvas.draw_idle()
        self.btn_csv.setEnabled(True)
        semilla = int(df['seed'].min())
        hechas = len(df) // max(1, df['agente'].nunique())
        resumen = (f"{'Cancelado: ' if cancelado else ''}{len(df)} partidas sobre "
                   f"{describir_instancia(self.instancia)} (semillas {semilla} a {semilla + hechas - 1}).")
        self.lbl_estado.setText("<br>".join([resumen] + avisos))

    def exportar(self):
        if self.df is None:
            return
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar partidas", "comparacion.csv", "CSV (*.csv)")
        if ruta:
            try:
                self.df.to_csv(ruta, index=False)
            except OSError as e:
                QMessageBox.warning(self, "No se pudo guardar", str(e))


class DialogoHumanoVsMaquina(QDialog):
    """Los agentes juegan la misma flota (misma semilla e instancia) que acaba de jugar la persona."""

    def __init__(self, partida: Partida, parent=None):
        super().__init__(parent)
        env, cfg = partida.env, partida.config
        self.setWindowTitle("Tú contra los algoritmos")
        self.resize(820, 400)
        self.minimo = cfg.casillas_barco
        self.humano = {'ganado': env.ganado, 'agotado': env.agotado, 'disparos': env.turnos}
        info = QLabel(f"Instancia: {describir_instancia(partida.instancia)} · semilla {partida.seed}. "
                      "Cada agente juega exactamente la misma flota que tú.")
        info.setWordWrap(True)
        self.tabla = QTableWidget(0, 6)
        self.tabla.setHorizontalHeaderLabels(["Jugador", "Resultado", "Disparos", "Eficiencia",
                                              "Brecha al óptimo", "ms / jugada"])
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabla.setSelectionMode(QTableWidget.NoSelection)
        self.barra = QProgressBar()
        self.veredicto = QLabel("Los agentes están jugando…")
        self.veredicto.setWordWrap(True)
        self.veredicto.setTextFormat(Qt.RichText)
        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.clicked.connect(self.accept)
        v = QVBoxLayout(self)
        v.addWidget(info)
        v.addWidget(self.tabla, 1)
        v.addWidget(self.barra)
        v.addWidget(self.veredicto)
        v.addWidget(btn_cerrar)

        claves = list(AGENTES)
        self.barra.setRange(0, len(claves))
        self.trabajo = TrabajoComparacion(claves, partida.instancia, 1, partida.seed, self)
        self.trabajo.progreso.connect(lambda h, t, _txt: (self.barra.setMaximum(t), self.barra.setValue(h)))
        self.trabajo.listo.connect(self.al_terminar)
        self.trabajo.start()

    def fila(self, jugador, ganado, resultado, disparos, ms=None, negrita=False):
        eficiencia = f"{self.minimo / disparos:.2f}" if ganado else "–"
        brecha = f"{disparos - self.minimo}" if ganado else "–"
        valores = (jugador, resultado, str(disparos), eficiencia, brecha,
                   "–" if ms is None else f"{ms:.2f}")
        i = self.tabla.rowCount()
        self.tabla.insertRow(i)
        fuente = QFont()
        fuente.setBold(negrita)
        for j, texto in enumerate(valores):
            it = QTableWidgetItem(texto)
            it.setFont(fuente)
            if j:
                it.setTextAlignment(Qt.AlignCenter)
            self.tabla.setItem(i, j, it)

    def al_terminar(self, df, errores):
        self.trabajo.wait()
        h = self.humano
        resultado_h = "Ganó" if h['ganado'] else ("Perdió: sin disparos" if h['agotado'] else "Se rindió")
        self.fila("Tú", h['ganado'], resultado_h, h['disparos'], negrita=True)
        ganadores = []
        if df is not None:
            for _, f in df.iterrows():
                gano = bool(f['ganado'])
                self.fila(f['nombre'], gano, "Ganó" if gano else "Perdió: sin disparos",
                          int(f['disparos']), f['ms_por_jugada'])
                if gano:
                    ganadores.append((int(f['disparos']), f['nombre']))
        self.tabla.resizeColumnsToContents()
        lineas = []
        if h['ganado']:
            puesto = 1 + sum(1 for d, _ in ganadores if d < h['disparos'])
            total = 1 + (0 if df is None else len(df))          # los que no ganaron quedan por detras
            lineas.append(f"Quedaste en el puesto <b>{puesto}</b> de {total} "
                          f"con {h['disparos']} disparos.")
        elif ganadores:
            lineas.append("No hundiste toda la flota; los agentes que ganaron lo lograron en "
                          f"{min(d for d, _ in ganadores)} disparos o más.")
        if ganadores:
            d, nombre = min(ganadores)
            lineas.append(f"Mejor agente: <b>{nombre}</b> con {d} disparos (óptimo teórico: {self.minimo}).")
        lineas += [f'<span style="color:#ff5a50">{k if k != "*" else "Error"}: {m}</span>'
                   for k, m in errores.items()]
        self.veredicto.setText("<br>".join(lineas))

    def done(self, resultado):
        if self.trabajo is not None and self.trabajo.isRunning():
            self.trabajo.cancelar()
            self.trabajo.wait()
        super().done(resultado)


class Ventana(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Batalla Naval")
        self.pestanas = QTabWidget()
        self.jugar = PestanaJugar()
        self.pestanas.addTab(self.jugar, "Jugar")
        self.editor = PestanaEditor()
        self.agente = PestanaAgente()
        self.pestanas.addTab(self.agente, "Ver agente")
        self.arbol = PestanaArbol(self.agente)
        self.pestanas.addTab(self.arbol, "Árbol MCTS")
        self.comparar = PestanaComparar()
        self.pestanas.addTab(self.comparar, "Comparar")
        self.pestanas.addTab(self.editor, "Editor de instancias")
        self.setCentralWidget(self.pestanas)
        self.editor.usar.connect(self.usar_instancia)

    def usar_instancia(self, destino: str, inst: Instancia):
        """La instancia del editor queda disponible como 'Personalizada' en Jugar, Ver agente
        y Comparar; en la pestaña de destino se elige y se abre."""
        destinos = {'jugar': self.jugar, 'agente': self.agente, 'comparar': self.comparar}
        for clave, pestana in destinos.items():
            pestana.poner_personalizada(inst, seleccionar=(clave == destino))
        self.pestanas.setCurrentWidget(destinos[destino])

    def closeEvent(self, evento):
        self.comparar.detener()
        super().closeEvent(evento)


def main():
    app = QApplication(sys.argv)
    ventana = Ventana()
    ventana.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
