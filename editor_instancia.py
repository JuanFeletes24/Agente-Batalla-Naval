"""
Modelo del editor de instancias de Batalla Naval, sin ninguna dependencia de interfaz.

Guarda los parametros que el usuario puede cambiar y la posicion de cada barco colocado a mano.
La pestaña "Editor" de app_qt.py solo dibuja este modelo y le reenvia los clics.

    ed = EditorInstancia()                      # parte del nivel Medio
    ed.cambiar_dimensiones(8, 8)
    ed.puede_colocar('Crucero', 2, 3, 'H')      # True/False segun solapes y adyacencia
    ed.colocar('Crucero', 2, 3, 'H')
    ed.completa                                 # True cuando todos los barcos estan colocados
    inst = ed.a_instancia(manual=True)          # ValueError si falta algo o no es valida

Las reglas de colocacion son las del entorno (ambientes.BatallaNavalEnv): dentro del tablero,
sin solaparse y, si 'permitir_adyacentes' es False, sin tocarse ni en diagonal.
"""

from typing import Dict, List, Optional, Tuple

from ambientes import BatallaNavalEnv
from dificultad import ConfigDificultad, FLOTA_CLASICA, NIVELES
from instancia import CLAVE_PERSONALIZADA, Instancia

MIN_LADO, MAX_LADO = 3, 15
MAX_LONGITUD = MAX_LADO

Celda = Tuple[int, int]


class EditorInstancia:

    def __init__(self, config: ConfigDificultad = None):
        base = config or NIVELES['medio']
        self.colocados: Dict[str, Tuple[int, int, str]] = {}     # nombre -> (fila, col, 'H'|'V')
        self._copiar_config(base)

    # -- parametros -------------------------------------------------------------
    def _copiar_config(self, cfg: ConfigDificultad) -> None:
        self.filas, self.columnas = cfg.filas, cfg.columnas
        self.flota: Dict[str, int] = dict(cfg.flota)
        self.colocacion = cfg.colocacion
        self.permitir_adyacentes = cfg.permitir_adyacentes
        self.max_disparos: Optional[int] = cfg.max_disparos
        self.prob_ruido = cfg.prob_ruido
        self.mostrar_flota_restante = cfg.mostrar_flota_restante

    def a_config(self) -> ConfigDificultad:
        """Configuracion con los parametros actuales (ValueError si no son coherentes)."""
        return ConfigDificultad(
            nombre='Personalizado', filas=self.filas, columnas=self.columnas,
            flota=dict(self.flota), colocacion=self.colocacion,
            permitir_adyacentes=self.permitir_adyacentes, max_disparos=self.max_disparos,
            prob_ruido=self.prob_ruido, mostrar_flota_restante=self.mostrar_flota_restante)

    def cambiar_dimensiones(self, filas: int, columnas: int) -> List[str]:
        """Cambia el tamaño del tablero. Devuelve los barcos que ya no caben (y se quitan)."""
        self.filas = max(MIN_LADO, min(MAX_LADO, int(filas)))
        self.columnas = max(MIN_LADO, min(MAX_LADO, int(columnas)))
        return self.revalidar()

    def cambiar_adyacencia(self, permitir: bool) -> List[str]:
        self.permitir_adyacentes = bool(permitir)
        return self.revalidar()

    # -- flota ------------------------------------------------------------------
    def poner_barco(self, nombre: str, longitud: int) -> None:
        """Añade un barco a la flota o cambia su longitud (si estaba colocado, se quita)."""
        nombre = nombre.strip()
        if not nombre:
            raise ValueError("El barco necesita un nombre.")
        if not 1 <= longitud <= MAX_LONGITUD:
            raise ValueError(f"La longitud debe estar entre 1 y {MAX_LONGITUD}.")
        self.flota[nombre] = int(longitud)
        self.colocados.pop(nombre, None)

    def quitar_barco(self, nombre: str) -> None:
        if len(self.flota) <= 1:
            raise ValueError("La flota debe tener al menos un barco.")
        self.flota.pop(nombre, None)
        self.colocados.pop(nombre, None)

    def restaurar_flota(self, flota: dict = None) -> None:
        self.flota = dict(flota or FLOTA_CLASICA)
        self.colocados.clear()

    # -- colocacion -------------------------------------------------------------
    @staticmethod
    def posiciones(r: int, c: int, longitud: int, orientacion: str) -> List[Celda]:
        return BatallaNavalEnv._posiciones(r, c, longitud, orientacion)

    def _celdas_ocupadas(self, excluir: str = None) -> set:
        ocupadas = set()
        for nombre, (r, c, o) in self.colocados.items():
            if nombre != excluir:
                ocupadas.update(self.posiciones(r, c, self.flota[nombre], o))
        return ocupadas

    def puede_colocar(self, nombre: str, r: int, c: int, orientacion: str) -> bool:
        """True si el barco cabe ahi (un barco ya colocado puede moverse: no choca consigo mismo)."""
        if nombre not in self.flota or orientacion not in ('H', 'V'):
            return False
        celdas = self.posiciones(r, c, self.flota[nombre], orientacion)
        if not all(0 <= rr < self.filas and 0 <= cc < self.columnas for rr, cc in celdas):
            return False
        ocupadas = self._celdas_ocupadas(excluir=nombre)
        if any(rc in ocupadas for rc in celdas):
            return False
        if not self.permitir_adyacentes:
            for rr, cc in celdas:
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        if (rr + dr, cc + dc) in ocupadas:
                            return False
        return True

    def colocar(self, nombre: str, r: int, c: int, orientacion: str) -> bool:
        if not self.puede_colocar(nombre, r, c, orientacion):
            return False
        self.colocados[nombre] = (int(r), int(c), orientacion)
        return True

    def quitar(self, nombre: str) -> None:
        self.colocados.pop(nombre, None)

    def limpiar(self) -> None:
        self.colocados.clear()

    def nombre_en(self, r: int, c: int) -> Optional[str]:
        """Barco colocado que ocupa la casilla (r, c), o None."""
        for nombre, (r0, c0, o) in self.colocados.items():
            if (r, c) in self.posiciones(r0, c0, self.flota[nombre], o):
                return nombre
        return None

    def revalidar(self) -> List[str]:
        """Quita los barcos que dejaron de ser validos tras cambiar tablero o reglas."""
        previos = dict(self.colocados)
        self.colocados.clear()
        quitados = []
        for nombre in self.flota:                      # en orden de flota, de forma determinista
            if nombre in previos and not self.colocar(nombre, *previos[nombre]):
                quitados.append(nombre)
        return quitados

    @property
    def pendientes(self) -> List[str]:
        return [n for n in self.flota if n not in self.colocados]

    @property
    def completa(self) -> bool:
        return not self.pendientes

    def disposicion(self) -> list:
        """[(nombre, fila, col, 'H'|'V')] en el orden de la flota (solo los colocados)."""
        return [(n, *self.colocados[n]) for n in self.flota if n in self.colocados]

    def colocar_al_azar(self, seed: int = None) -> None:
        """Rellena el tablero con una disposicion aleatoria valida (que luego se puede editar)."""
        env = BatallaNavalEnv(config=self.a_config(), seed=seed)
        self.colocados = {n: (r, c, o) for n, r, c, o in env.disposicion_actual()}

    # -- instancia --------------------------------------------------------------
    def a_instancia(self, manual: bool) -> Instancia:
        """
        Crea la instancia lista para jugar o resolver. Con manual=True exige que todos los
        barcos esten colocados; con manual=False la flota se coloca al azar segun la semilla.
        """
        config = self.a_config()
        disposicion = None
        if manual:
            if not self.completa:
                raise ValueError("Faltan por colocar: " + ", ".join(self.pendientes))
            disposicion = self.disposicion()
        inst = Instancia(config=config, disposicion=disposicion, clave=CLAVE_PERSONALIZADA)
        inst.validar()
        return inst

    def cargar(self, inst: Instancia) -> None:
        """Pone el editor en el estado de una instancia (p. ej. una leida de un archivo)."""
        self._copiar_config(inst.config)
        self.colocados = {n: (r, c, o) for n, r, c, o in (inst.disposicion or [])}
