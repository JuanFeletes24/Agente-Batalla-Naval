"""
Apoyo para visualizar el estado interno de los agentes (sin dependencias de Qt ni pygame).

Contiene:
  - Colores y etiquetas de los tipos de nodo del arbol de MCTS y de las reglas de Caza-Remate.
  - `disponer_arbol`: calcula la posicion (x, y) de cada nodo del resumen del arbol que entrega
    `AgenteMCTS.estado_interno()['arbol']`, para que la interfaz solo tenga que dibujarlo.

Formato del resumen del arbol (diccionarios anidados, sin referencias a nodos vivos):

    {'tipo': 'raiz', 'etiqueta': 'Raíz', 'N': 200, 'hijos': [
        {'tipo': 'seleccionada' | 'interno' | 'frontera', 'etiqueta': 'E5', 'N': 80, 'Q': 0.31,
         'hijos': [
             {'tipo': ..., 'etiqueta': 'agua' | 'impacto' | 'hundido', 'N': 50, 'hijos': [...]},
         ]},
    ]}
"""

# --- paleta del juego (la misma del tablero y de los mensajes de la interfaz) -----------------
C_FONDO = (30, 34, 41)               # #1E2229 gris carbon / pizarra oscuro
C_NODO = (40, 46, 58)                # relleno de los nodos (un tono sobre el fondo)
C_TEXTO = (232, 240, 245)
C_TEXTO_SUAVE = (140, 152, 168)

# borde de cada tipo de nodo del arbol (RGB)
COLOR_NODO = {
    'raiz': (110, 160, 255),          # azul: nodo raiz
    'seleccionada': (255, 209, 102),  # #FFD166 dorado: accion elegida (rama seleccionada)
    'interno': (110, 230, 140),       # verde: nodo interno ya expandido
    'frontera': (140, 152, 168),      # gris: frontera / hoja recien creada
}
ETIQUETA_NODO = {
    'raiz': 'Raíz',
    'seleccionada': 'Rama elegida',
    'interno': 'Interno (expandido)',
    'frontera': 'Frontera (hoja nueva)',
}
# color del resultado de la observacion
COLOR_OBS = {
    'agua': (90, 200, 220),           # cian suave
    'impacto': (255, 125, 60),        # naranja coral
    'hundido': (220, 38, 60),         # carmesi
}
COLOR_RAMA = (255, 209, 102)          # aristas de la rama elegida
COLOR_ARISTA = (90, 100, 115)

# --- reglas de Caza-Remate (RGB) -----------------------------------------------------------
COLOR_REGLA = {
    'caza': (90, 170, 255),           # azul: caza por paridad
    'ortogonal': (255, 150, 60),      # naranja: remate ortogonal simple
    'colineal': (230, 80, 200),       # magenta: remate colineal
}


def a_hex(rgb: tuple) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _filas_hoja(nodo: dict) -> int:
    hijos = nodo.get('hijos') or []
    return max(1, sum(_filas_hoja(h) for h in hijos))


def _podar(nodo: dict, profundidad: int, max_hojas: int) -> dict:
    """Copia del arbol; si hay demasiadas hojas, el ultimo nivel se queda con 1 hijo por nodo."""
    hijos = nodo.get('hijos') or []
    copia = dict(nodo)
    if profundidad == 2 and max_hojas is not None:
        hijos = hijos[:max_hojas]
    copia['hijos'] = [_podar(h, profundidad + 1, max_hojas) for h in hijos]
    return copia


def disponer_arbol(arbol: dict, ancho: float, alto: float, max_filas: int = 18) -> dict:
    """
    Posiciona el arbol de izquierda a derecha (un nivel por columna).

    Devuelve {'nodos': [...], 'aristas': [(i, j, en_rama)], 'niveles': n}; cada nodo es un dict con
    x, y, w, h (esquina superior izquierda y tamano), 'tipo', 'lineas' (texto a mostrar) y 'rama'
    (True si pertenece a la rama de la accion elegida).
    """
    if not arbol:
        return {'nodos': [], 'aristas': [], 'niveles': 0}

    # Si hay demasiadas hojas para la altura disponible, el segundo nivel de acciones se reduce.
    for limite in (2, 1):
        podado = _podar(arbol, 0, limite)
        if _filas_hoja(podado) <= max_filas:
            break

    filas = _filas_hoja(podado)

    def profundidad(n):
        hs = n.get('hijos') or []
        return 1 + max((profundidad(h) for h in hs), default=0)

    niveles = profundidad(podado)
    margen = 6
    col_w = (ancho - 2 * margen) / niveles
    box_w = col_w * 0.82
    fila_h = (alto - 2 * margen) / filas
    box_h = min(36.0, fila_h - 3)
    doble = box_h >= 28                       # con altura suficiente, 2 lineas de texto

    nodos, aristas = [], []

    def colocar(n, nivel, fila0, en_rama):
        hijos = n.get('hijos') or []
        rama = en_rama or n['tipo'] == 'seleccionada'
        indices = []
        f = fila0
        for h in hijos:
            indices.append(colocar(h, nivel + 1, f, rama))
            f += _filas_hoja(h)
        if hijos:
            y_centro = (nodos[indices[0]]['yc'] + nodos[indices[-1]]['yc']) / 2
        else:
            y_centro = margen + (fila0 + 0.5) * fila_h
        detalle = f"N={n['N']}" + (f" Q={n['Q']:.2f}" if n.get('Q') is not None else "")
        if doble:
            lineas = [n['etiqueta'], detalle]
        else:
            lineas = [f"{n['etiqueta']} {detalle}"]
        idx = len(nodos)
        nodos.append({'x': margen + nivel * col_w, 'y': y_centro - box_h / 2, 'yc': y_centro,
                      'w': box_w, 'h': box_h, 'tipo': n['tipo'], 'obs': n.get('obs'), 'lineas': lineas, 'rama': rama})
        for j in indices:
            aristas.append((idx, j, nodos[j]['rama']))
        return idx

    colocar(podado, 0, 0, False)
    return {'nodos': nodos, 'aristas': aristas, 'niveles': niveles}
