import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import seaborn as sns

from dificultad import ConfigDificultad, FLOTA_CLASICA


# CONSTANTES DE CASILLAS Y FLOTA POR DEFECTO

DESCONOCIDO = -1 # Casilla aun no explorada
AGUA = 0 # Disparo que cayo al agua
TOCADO = 1 # Disparo que le dio a un barco
HUNDIDO = 2 # Casilla que ocupa un barco que fue hundido

# DICCIONARIO DE LOS BARCOS

FLOTA_DEFAULT = dict(FLOTA_CLASICA)

# CLASE BARCO

class Barco:

    """
    Clase Barco, permite rastrear el estado del barco en la 
    rejilla y la ubicacion de cade nave de forma individual
    """

    def __init__(self, nombre: str, longitud: int):
        self.nombre = nombre
        self.longitud = longitud
        self.posiciones = []
        self.impactos = 0

    def esta_hundido(self) -> bool:
        return self.impactos >= self.longitud 

    def recibir_impacto(self, coord: tuple):
        if coord in self.posiciones:
            self.impactos += 1

# CLASE ENTORNO BATALLA NAVAL            
    
class BatallaNavalEnv:

    """
    Clase del entorno de batalla naval.

    La dificultad se define con un ConfigDificultad (ver dificultad.py):
        env = BatallaNavalEnv(config=NIVELES['medio'], seed=1)
    Tambien se puede usar la firma anterior (filas, columnas, flota).

    Estados de fin de partida:
        env.ganado   -> toda la flota fue hundida
        env.agotado  -> se acabaron los disparos permitidos (derrota)
        env.done     -> ganado o agotado
    """

    def __init__(self, filas: int = 10, columnas: int = 10, flota: dict = None,
                 seed: int = None, config: ConfigDificultad = None):
        if config is None:
            config = ConfigDificultad(
                nombre="Personalizado", filas=filas, columnas=columnas,
                flota=dict(flota) if flota is not None else dict(FLOTA_DEFAULT))
        self.config = config
        self.filas = config.filas
        self.columnas = config.columnas
        self.flota_config = dict(config.flota)
        self.rng = np.random.default_rng(seed)
        # generador aparte para el ruido del sonar: no altera la colocacion de la flota
        self.rng_ruido = np.random.default_rng(None if seed is None else [seed, 7919])
        self.seed = seed
        self.tablero_oculto = np.zeros((self.filas, self.columnas), dtype=int)
        self.tablero_agente = np.full((self.filas, self.columnas), DESCONOCIDO, dtype=int)
        self.barcos = []
        self.turnos = 0
        self.done = False
        self.ganado = False
        self.agotado = False
        self.recompensa_acumulada = 0
        self.ultimo_feedback = None
        self.reset(seed)

    # ---- colocacion de la flota -------------------------------------------

    @staticmethod
    def _posiciones(r: int, c: int, longitud: int, orientacion: str) -> list:
        if orientacion == 'H':
            return [(r, c + i) for i in range(longitud)]
        return [(r + i, c) for i in range(longitud)]

    def validar_posicion(self, r: int, c: int, longitud: int, orientacion: str) -> bool:
        if orientacion not in ('H', 'V'):
            return False
        posiciones = self._posiciones(r, c, longitud, orientacion)
        for (rr, cc) in posiciones:
            if not (0 <= rr < self.filas and 0 <= cc < self.columnas):
                return False
            if self.tablero_oculto[rr][cc] != 0:
                return False
        if not self.config.permitir_adyacentes:
            for (rr, cc) in posiciones:
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        r2, c2 = rr + dr, cc + dc
                        if (0 <= r2 < self.filas and 0 <= c2 < self.columnas
                                and self.tablero_oculto[r2][c2] != 0):
                            return False
        return True

    def colocar_barco(self, nombre: str, r: int, c: int, orientacion: str) -> bool:
        longitud = self.flota_config[nombre]

        if not self.validar_posicion(r, c, longitud, orientacion):
            return False

        posiciones = self._posiciones(r, c, longitud, orientacion)

        barco = Barco(nombre, longitud)
        barco.posiciones = posiciones
        self.barcos.append(barco)
        id_barco = len(self.barcos)

        for (fila, columna) in posiciones:
            self.tablero_oculto[fila][columna] = id_barco

        return True

    def _toca_borde(self, posiciones: list) -> bool:
        return any(r in (0, self.filas - 1) or c in (0, self.columnas - 1)
                   for (r, c) in posiciones)

    def _intentar_colocar_flota(self) -> bool:
        for nombre, longitud in self.flota_config.items():
            for _ in range(2000):
                orientacion = str(self.rng.choice(['H', 'V']))
                r = int(self.rng.integers(0, self.filas))
                c = int(self.rng.integers(0, self.columnas))
                if not self.validar_posicion(r, c, longitud, orientacion):
                    continue
                if self.config.colocacion == 'bordes':
                    pos = self._posiciones(r, c, longitud, orientacion)
                    # los barcos lejos del borde se aceptan solo con probabilidad baja
                    if not self._toca_borde(pos) and self.rng.random() > 0.15:
                        continue
                self.colocar_barco(nombre, r, c, orientacion)
                break
            else:
                return False
        return True

    def colocar_flota_aleatoria(self) -> None:
        for _ in range(200):
            self.tablero_oculto.fill(0)
            self.barcos = []
            if self._intentar_colocar_flota():
                return
        raise RuntimeError("No se pudo colocar la flota con esta configuracion")

    # ---- ciclo de vida -----------------------------------------------------

    def reset(self, seed: int = None) -> dict:
        if seed is not None:
            self.rng = np.random.default_rng(seed)
            self.rng_ruido = np.random.default_rng([seed, 7919])
            self.seed = seed

        self.tablero_oculto.fill(0)
        self.tablero_agente.fill(DESCONOCIDO)

        self.barcos = []
        self.turnos = 0
        self.done = False
        self.ganado = False
        self.agotado = False
        self.recompensa_acumulada = 0
        self.ultimo_feedback = None

        self.colocar_flota_aleatoria()
        return self.para_sentidos()

    def acciones_aplicables(self) -> list:
        if self.done:
            return []
        return [(r, c) for r in range(self.filas) for c in range(self.columnas)
                if self.tablero_agente[r][c] == DESCONOCIDO]

    def test_objetivo(self) -> bool:
        return all(barco.esta_hundido() for barco in self.barcos)

    def disparos_restantes(self):
        """None si no hay limite."""
        if self.config.max_disparos is None:
            return None
        return self.config.max_disparos - self.turnos

    def para_sentidos(self) -> dict:
        """
        Observacion para el agente (solo informacion que el jugador puede conocer).
        'barcos_vivos' es None cuando el nivel oculta la flota restante.
        """
        vivos = [b for b in self.barcos if not b.esta_hundido()]
        return {
            'tablero_agente': self.tablero_agente.copy(),
            'barcos_vivos': [b.nombre for b in vivos] if self.config.mostrar_flota_restante else None,
            'n_barcos_vivos': len(vivos),
            'ultimo_feedback': self.ultimo_feedback,
            'turnos': self.turnos,
            'disparos_restantes': self.disparos_restantes(),
        }

    # ---- paso del entorno --------------------------------------------------

    def step(self, accion: tuple) -> tuple:
        if self.done:
            raise ValueError("La partida ya termino. Usa reset().")
        accion = tuple(int(v) for v in accion)
        r, c = accion
        if not (0 <= r < self.filas and 0 <= c < self.columnas) \
                or self.tablero_agente[r][c] != DESCONOCIDO:
            raise ValueError(f"Accion {accion} no es aplicable en el estado actual.")

        self.turnos += 1
        recompensa = -1
        self.recompensa_acumulada += recompensa

        # --- resultado REAL del disparo
        id_barco = self.tablero_oculto[accion]
        barco = None
        if id_barco == 0:
            real = 'agua'
        else:
            barco = self.barcos[id_barco - 1]
            barco.recibir_impacto(accion)
            real = 'hundido' if barco.esta_hundido() else 'impacto'

        # --- resultado REPORTADO (el sonar puede fallar; "hundido" siempre es real)
        reportado = real
        if real in ('agua', 'impacto') and self.config.prob_ruido > 0 \
                and self.rng_ruido.random() < self.config.prob_ruido:
            reportado = 'impacto' if real == 'agua' else 'agua'

        if reportado == 'agua':
            self.tablero_agente[accion] = AGUA
        elif reportado == 'impacto':
            self.tablero_agente[accion] = TOCADO
        else:
            for coord in barco.posiciones:
                self.tablero_agente[coord] = HUNDIDO

        # --- nombre del barco: solo si el nivel lo permite y no delata el ruido
        nombre = None
        if self.config.mostrar_flota_restante and barco is not None:
            if reportado == 'hundido' or (reportado == 'impacto' and self.config.prob_ruido == 0):
                nombre = barco.nombre

        feedback = {'resultado': reportado, 'barco': nombre, 'coord': accion}
        self.ultimo_feedback = feedback

        # --- fin de partida
        self.ganado = self.test_objetivo()
        limite = self.config.max_disparos
        self.agotado = (not self.ganado) and limite is not None and self.turnos >= limite
        self.done = self.ganado or self.agotado

        info = {'recompensa_acumulada': self.recompensa_acumulada, 'turnos': self.turnos,
                'ganado': self.ganado, 'agotado': self.agotado,
                'resultado_real': real}   # solo para registro/depuracion, no para los agentes
        return self.para_sentidos(), recompensa, self.done, info

    def pintar_todo(self) -> None:
        fig, ax = plt.subplots(figsize=(7, 7))

        # Definimos las dimensiones del tablero
        ax.set_xlim(0, self.columnas)
        ax.set_ylim(0, self.filas)

        # Invertimos el eje para que la fila 0 esté en la parte superior
        ax.invert_yaxis()

        for r in range(self.filas): 
            for c in range(self.columnas):

                # Si la casilla es de un barco, la pintamos de gris
                if self.tablero_oculto[r][c] > 0:
                    color_fondo = '#7F8C8D' 

                # Si la casilla es agua, la pintamos de azul
                else:
                    color_fondo = '#3498DB'

                rect = patches.Rectangle((c, r), 1, 1, facecolor=color_fondo, edgecolor='black', linewidth=1.2)
                ax.add_patch(rect)

                # Revisamos la casilla en el tablero del agente para determinar si ha sido disparada
                estado_disparo = self.tablero_agente[r, c]
                if estado_disparo == AGUA:
                    ax.text(c + 0.5, r + 0.5, 'O', color='#2980B9', fontsize=18, ha='center', va='center', weight='bold')
                elif estado_disparo in [TOCADO, HUNDIDO]:
                    ax.text(c + 0.5, r + 0.5, 'X', color='#C0392B', fontsize=20, ha='center', va='center', weight='bold')

        # Etiquetas y titulo
        ax.set_xticks([i + 0.5 for i in range(self.columnas)])
        ax.set_xticklabels([str(i) for i in range(self.columnas)])
        ax.set_yticks([i + 0.5 for i in range(self.filas)])
        ax.set_yticklabels([str(i) for i in range(self.filas)])

        ax.set_title(f"Vista Omnisciente (Verdad Terreno) | Turno: {self.turnos}", fontsize=13, weight='bold', pad=12)
        plt.tight_layout()
        plt.show()

    def render(self, mapa_calor: np.ndarray = None, ax=None):
        """
        Dibuja el tablero del agente. Si se pasa un 'ax', dibuja sobre el
        (sin abrir otra figura ni llamar a plt.show), util para juegos interactivos.
        """
        propio = ax is None
        if propio:
            fig, ax = plt.subplots(figsize=(7, 6))
        else:
            ax.clear()

        if mapa_calor is not None:
            sns.heatmap(mapa_calor, annot=True, fmt=".2f", cmap="coolwarm", cbar=True, square=True, ax=ax)
        else:
            # Definimos las dimensiones del tablero
            ax.set_xlim(0, self.columnas)
            ax.set_ylim(0, self.filas)
            
            # Invertimos el eje para que la fila 0 esté en la parte superior
            ax.invert_yaxis()
        
        for r in range(self.filas): 
            for c in range(self.columnas):      

                estado_disparo = self.tablero_agente[r, c]

                # Determinamos el color de la casilla
                if estado_disparo == DESCONOCIDO:
                    # Si hay mapa de calor, dejamos la casilla transparente para ver el gradiente
                    color_fondo = 'none' if mapa_calor is not None else '#2C3E50'
                elif estado_disparo == AGUA:
                    color_fondo = '#D4EEF9'  # Celeste claro
                elif estado_disparo == TOCADO:
                    color_fondo = '#F5B7B1'  # Rojo suave
                elif estado_disparo == HUNDIDO:
                    color_fondo = '#922B21'  # Rojo oscuro / quemado

                # Construimos cada cuadricula
                rect = patches.Rectangle((c, r), 1, 1, facecolor=color_fondo, edgecolor='black', linewidth=1.2)
                ax.add_patch(rect)


                # Simbolos sobre las casillas disparadas
                if estado_disparo == AGUA:
                    ax.text(c + 0.5, r + 0.5, 'O', color='#2980B9', fontsize=16, ha='center', va='center', weight='bold')
                elif estado_disparo in [TOCADO, HUNDIDO]:
                    ax.text(c + 0.5, r + 0.5, 'X', color='#C0392B', fontsize=18, ha='center', va='center', weight='bold')
                
        # Etiquetas y titulo
        ax.set_xticks([i + 0.5 for i in range(self.columnas)])
        ax.set_xticklabels([str(i) for i in range(self.columnas)])
        ax.set_yticks([i + 0.5 for i in range(self.filas)])
        ax.set_yticklabels([str(i) for i in range(self.filas)])
        
        ax.set_title(f"Turno: {self.turnos} | Barcos vivos: {len([b for b in self.barcos if not b.esta_hundido()])}/{len(self.barcos)} | Recompensa: {self.recompensa_acumulada}", fontsize=13, weight='bold', pad=12)
        if propio:
            plt.tight_layout()
            plt.show()
