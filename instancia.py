"""
Instancia del problema: configuracion del entorno + disposicion inicial opcional de la flota.

Una instancia es lo que el usuario puede cambiar desde la interfaz (lineamientos, seccion 2.2):
dimensiones, flota, limite de disparos, ruido del sonar, adyacencia, visibilidad de la flota
y, ademas, el ESTADO INICIAL (donde esta cada barco).

    inst = Instancia.de_nivel('medio')                 # nivel predefinido, flota al azar
    inst = Instancia(config, disposicion=[('Crucero', 0, 0, 'H'), ...], clave='personalizada')
    env = inst.crear_env(seed=1000)                    # con 'disposicion' reset() no la cambia
    inst.guardar('mi_instancia.json'); Instancia.cargar('mi_instancia.json')

Si 'disposicion' es None la flota se coloca al azar segun la semilla (como en los niveles).
Sin interfaz: lo usan app_qt.py, sesion_agente.py, partida.py y comparar.py.
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import List, Optional, Tuple

from ambientes import BatallaNavalEnv
from dificultad import ConfigDificultad, NIVELES

CLAVE_PERSONALIZADA = 'personalizada'
VERSION_ARCHIVO = 1

Disposicion = List[Tuple[str, int, int, str]]      # [(nombre, fila, columna, 'H'|'V'), ...]


@dataclass
class Instancia:
    config: ConfigDificultad
    disposicion: Optional[Disposicion] = None
    clave: str = CLAVE_PERSONALIZADA

    # -- construccion -----------------------------------------------------------
    @classmethod
    def de_nivel(cls, nivel: str) -> "Instancia":
        return cls(config=NIVELES[nivel], disposicion=None, clave=nivel)

    @property
    def manual(self) -> bool:
        """True si la flota viene colocada por el usuario (no al azar)."""
        return self.disposicion is not None

    def crear_env(self, seed: int = None) -> BatallaNavalEnv:
        """Entorno nuevo. Con disposicion manual, la flota queda siempre donde se coloco."""
        return BatallaNavalEnv(config=self.config, seed=seed, disposicion=self.disposicion)

    def validar(self) -> None:
        """Lanza ValueError/RuntimeError si la instancia no se puede crear."""
        self.crear_env(seed=0)

    # -- identificacion ---------------------------------------------------------
    def firma(self) -> str:
        """Resumen corto del contenido: dos instancias iguales tienen la misma firma."""
        texto = json.dumps(self.a_dict(), sort_keys=True)
        return hashlib.sha1(texto.encode('utf-8')).hexdigest()[:6]

    @property
    def id_registro(self) -> str:
        """Clave para llevar records: una por nivel, y una por cada instancia personalizada."""
        return self.clave if self.clave != CLAVE_PERSONALIZADA else f"{self.clave}-{self.firma()}"

    # -- (de)serializacion ------------------------------------------------------
    def a_dict(self) -> dict:
        return {
            'version': VERSION_ARCHIVO,
            'config': asdict(self.config),
            'disposicion': None if self.disposicion is None else
            [{'barco': n, 'fila': r, 'columna': c, 'orientacion': o}
             for (n, r, c, o) in self.disposicion],
        }

    @classmethod
    def desde_dict(cls, datos: dict) -> "Instancia":
        try:
            cfg = dict(datos['config'])
            cfg['flota'] = {str(k): int(v) for k, v in cfg['flota'].items()}
            config = ConfigDificultad(**cfg)
            bruto = datos.get('disposicion')
            disposicion = None if bruto is None else [
                (str(d['barco']), int(d['fila']), int(d['columna']), str(d['orientacion']).upper())
                for d in bruto]
        except (KeyError, TypeError, AttributeError) as e:
            raise ValueError(f"Archivo de instancia invalido: {e}") from e
        inst = cls(config=config, disposicion=disposicion, clave=CLAVE_PERSONALIZADA)
        inst.validar()
        return inst

    def guardar(self, ruta: str) -> None:
        with open(ruta, 'w', encoding='utf-8') as f:
            json.dump(self.a_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def cargar(cls, ruta: str) -> "Instancia":
        with open(ruta, encoding='utf-8') as f:
            try:
                datos = json.load(f)
            except json.JSONDecodeError as e:
                raise ValueError(f"El archivo no es un JSON valido: {e}") from e
        return cls.desde_dict(datos)


def resolver(clave: str, personalizada: Optional[Instancia] = None) -> Instancia:
    """Instancia que corresponde a una opcion de los selectores de nivel de la interfaz."""
    if clave == CLAVE_PERSONALIZADA:
        if personalizada is None:
            raise ValueError("Aun no hay una instancia personalizada: crea una en la pestaña Editor.")
        return personalizada
    return Instancia.de_nivel(clave)
