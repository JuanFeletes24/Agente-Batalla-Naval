"""
Niveles de dificultad de Batalla Naval.

La dificultad es una CONFIGURACION DEL ENTORNO: una persona y cualquier agente
(Monte Carlo, red bayesiana, DQN, ...) enfrentan exactamente el mismo problema
cuando usan el mismo nivel. Los recursos del agente (simulaciones, episodios de
entrenamiento, tamano de la red) NO forman parte de la dificultad.

Parametros:
  filas, columnas          tamano del tablero
  flota                    {nombre: longitud}
  colocacion               'uniforme'  -> posiciones al azar
                           'bordes'    -> sesgo: los barcos tienden a tocar los bordes
  permitir_adyacentes      False -> ningun barco puede tocar a otro (ni en diagonal)
  max_disparos             None = sin limite; si se agota, se pierde
  prob_ruido               probabilidad de que el sonar reporte mal un disparo
                           (agua <-> impacto). El anuncio de "hundido" siempre es real.
  mostrar_flota_restante   False -> no se informa que barcos quedan ni el nombre
                           del barco tocado/hundido (solo cuantos quedan)
"""

from dataclasses import dataclass, field, replace
from typing import Dict, Optional

FLOTA_CLASICA = {
    'Portaaviones': 5,
    'Acorazado': 4,
    'Crucero': 3,
    'Submarino': 3,
    'Destructor': 2,
}

COLOCACIONES = ('uniforme', 'bordes')


@dataclass(frozen=True)
class ConfigDificultad:
    nombre: str
    filas: int = 10
    columnas: int = 10
    flota: Dict[str, int] = field(default_factory=lambda: dict(FLOTA_CLASICA))
    colocacion: str = 'uniforme'
    permitir_adyacentes: bool = True
    max_disparos: Optional[int] = None
    prob_ruido: float = 0.0
    mostrar_flota_restante: bool = True

    def __post_init__(self):
        if self.colocacion not in COLOCACIONES:
            raise ValueError(f"colocacion debe ser una de {COLOCACIONES}")
        if not 0.0 <= self.prob_ruido < 0.5:
            raise ValueError("prob_ruido debe estar en [0, 0.5)")
        if not self.flota or min(self.flota.values()) < 1:
            raise ValueError("la flota debe tener al menos un barco de longitud >= 1")
        if self.casillas_barco > self.filas * self.columnas:
            raise ValueError("la flota no cabe en el tablero")
        if self.max_disparos is not None and self.max_disparos < self.casillas_barco:
            raise ValueError("max_disparos no puede ser menor que las casillas de barco")

    # --- cantidades derivadas -------------------------------------------------
    @property
    def casillas_barco(self) -> int:
        """Minimo teorico de disparos para ganar (feedback perfecto)."""
        return sum(self.flota.values())

    @property
    def densidad(self) -> float:
        """Fraccion del tablero ocupada por barcos (menor = mas dificil)."""
        return self.casillas_barco / (self.filas * self.columnas)

    def sin_limite(self) -> "ConfigDificultad":
        """Misma configuracion pero sin limite de disparos (util para calibrar)."""
        return replace(self, max_disparos=None)

    def descripcion(self) -> list:
        """Lineas cortas que resumen las reglas del nivel."""
        lineas = [f"Tablero {self.filas}x{self.columnas}, {len(self.flota)} barcos "
                  f"({self.casillas_barco} casillas, {self.densidad:.0%})"]
        if self.max_disparos is not None:
            lineas.append(f"Limite: {self.max_disparos} disparos")
        if self.prob_ruido > 0:
            lineas.append(f"Sonar con ruido ({self.prob_ruido:.0%} de error)")
        if not self.mostrar_flota_restante:
            lineas.append("Flota restante oculta")
        if not self.permitir_adyacentes:
            lineas.append("Barcos sin contacto entre si")
        if self.colocacion == 'bordes':
            lineas.append("Barcos sesgados hacia los bordes")
        return lineas


# ---------------------------------------------------------------------------
# NIVELES (los limites de disparos se calibraron con evaluar.py --calibrar)
# ---------------------------------------------------------------------------

NIVELES = {
    'facil': ConfigDificultad(
        nombre='Fácil', filas=6, columnas=6,
        flota={'Crucero': 3, 'Destructor': 2, 'Lancha': 2},
        max_disparos=None),
    'medio': ConfigDificultad(
        nombre='Medio', filas=8, columnas=8,
        flota={'Acorazado': 4, 'Crucero': 3, 'Submarino': 3, 'Destructor': 2},
        max_disparos=40),
    'dificil': ConfigDificultad(
        nombre='Difícil', filas=10, columnas=10,
        flota=dict(FLOTA_CLASICA),
        max_disparos=55, mostrar_flota_restante=False),
    'experto': ConfigDificultad(
        nombre='Experto', filas=12, columnas=12,
        flota=dict(FLOTA_CLASICA),
        max_disparos=80, mostrar_flota_restante=False, prob_ruido=0.06),
}

ORDEN_NIVELES = ['facil', 'medio', 'dificil', 'experto']


def obtener_nivel(nombre: str) -> ConfigDificultad:
    clave = nombre.lower().replace('á', 'a').replace('í', 'i')
    if clave not in NIVELES:
        raise ValueError(f"Nivel desconocido '{nombre}'. Opciones: {ORDEN_NIVELES}")
    return NIVELES[clave]
