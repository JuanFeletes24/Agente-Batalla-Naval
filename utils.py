"""
Funciones de apoyo para jugar Batalla Naval como persona.
Conversion entre coordenadas internas (fila, columna) y el formato de juego
(letra de columna + numero de fila, por ejemplo 'B5').
"""

import string


def coord_a_texto(r: int, c: int) -> str:
    """(4, 1) -> 'B5'. La columna es letra (A, B, ...) y la fila es numero desde 1."""
    return f"{string.ascii_uppercase[c]}{r + 1}"


def texto_a_coord(texto: str, filas: int = 10, columnas: int = 10):
    """
    'B5' (o 'b5', ' B 5 ') -> (4, 1).
    Devuelve None si el texto no es una coordenada valida para el tablero.
    """
    texto = texto.strip().upper().replace(" ", "")
    if len(texto) < 2 or texto[0] not in string.ascii_uppercase:
        return None
    c = string.ascii_uppercase.index(texto[0])
    if not texto[1:].isdigit():
        return None
    r = int(texto[1:]) - 1
    if 0 <= r < filas and 0 <= c < columnas:
        return (r, c)
    return None


def mensaje_feedback(feedback: dict) -> str:
    """Convierte el feedback del entorno en una frase para el jugador."""
    if feedback is None:
        return "Haz clic en una casilla para disparar."
    coord = coord_a_texto(*feedback['coord'])
    if feedback['resultado'] == 'agua':
        return f"{coord}: ¡Agua!"
    if feedback['resultado'] == 'impacto':
        return f"{coord}: ¡Tocado! (un {feedback['barco']})"
    return f"{coord}: ¡Hundiste el {feedback['barco']}!"


def calificacion(turnos: int, minimo: int) -> str:
    """Califica la partida segun cuantos disparos uso el jugador."""
    if turnos <= minimo + 15:
        return "Almirante"
    if turnos <= minimo + 35:
        return "Capitan"
    if turnos <= minimo + 55:
        return "Marinero"
    return "Grumete"
