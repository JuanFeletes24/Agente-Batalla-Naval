"""
Funciones de apoyo para jugar Batalla Naval como persona.
Conversion entre coordenadas internas (fila, columna) y el formato de juego
(letra de columna + numero de fila, por ejemplo 'B5').
"""

import string


def coord_a_texto(r: int, c: int) -> str:
    """(4, 1) -> 'B5'. La columna es letra (A, B, ...) y la fila es numero desde 1."""
    return f"{string.ascii_uppercase[c]}{r + 1}"


def mensaje_feedback(feedback: dict, ruido: bool = False) -> str:
    """
    Convierte el feedback del entorno en una frase para el jugador.
    Si el nivel oculta el nombre del barco (feedback['barco'] es None), no se menciona.
    Con ruido=True el resultado se presenta como una lectura del sonar (puede ser falsa).
    """
    if feedback is None:
        return "Haz clic en una casilla para disparar."
    coord = coord_a_texto(*feedback['coord'])
    barco = feedback['barco']
    res = feedback['resultado']
    if res == 'hundido':
        return f"{coord}: ¡Hundiste el {barco}!" if barco else f"{coord}: ¡Hundiste un barco!"
    if ruido:
        return f"{coord}: el sonar detecta " + ("agua" if res == 'agua' else "un impacto")
    if res == 'agua':
        return f"{coord}: ¡Agua!"
    return f"{coord}: ¡Tocado! (un {barco})" if barco else f"{coord}: ¡Tocado!"


def calificacion(turnos: int, minimo: int) -> str:
    """
    Califica la partida segun cuantos disparos uso el jugador, en proporcion al
    minimo teorico (casillas de barco), para que valga en cualquier tamano de tablero.
    """
    razon = turnos / minimo
    if razon <= 2.0:
        return "Almirante"
    if razon <= 3.0:
        return "Capitan"
    if razon <= 4.0:
        return "Marinero"
    return "Grumete"
