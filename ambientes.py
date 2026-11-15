import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import seaborn as sns


# CONSTANTES DE CASILLAS Y FLOTA POR DEFECTO

DESCONOCIDO = -1 # Casilla aun no explorada
AGUA = 0 # Disparo que cayo al agua
TOCADO = 1 # Disparo que le dio a un barco
HUNDIDO = 2 # Casilla que ocupa un barco que fue hundido

# DICCIONARIO DE LOS BARCOS

FLOTA_DEFAULT = {
    'Portaaviones': 5,
    'Acorazado': 4,
    'Crucero': 3,
    'Submarino': 3,
    'Destructor': 2
}

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
    Clase del entorno de batalla naval
    """

    def __init__(self, filas: int = 10, columnas: int = 10, flota: dict = None, seed: int = None):
        self.filas = filas
        self.columnas = columnas
        self.flota_config = flota.copy() if flota is not None else FLOTA_DEFAULT.copy()
        self.rng = np.random.default_rng(seed) 
        self.seed = seed
        self.tablero_oculto = np.zeros((filas, columnas), dtype=int)
        self.tablero_agente = np.full((filas, columnas), DESCONOCIDO, dtype=int)
        self.barcos = []
        self.turnos = 0
        self.done = False
        self.recompensa_acumulada = 0
        self.ultimo_feedback = None
        self.reset(seed)

    def validar_posicion(self, r: int, c: int, longitud: int, orientacion: str) -> bool:
        if orientacion == 'H':
            if 0 <= r < self.filas and 0 <= c and (c + longitud) <= self.columnas:
                for i in range(longitud):
                    if self.tablero_oculto[r][c+i] != 0:
                        return False
                return True
            else:
                return False
        elif orientacion == 'V':
            if 0 <= c < self.columnas and 0 <= r and (r + longitud) <= self.filas:
                for i in range(longitud):
                    if self.tablero_oculto[r+i][c] != 0:
                        return False
                return True
            else:
                return False
        else:
            return False

    def colocar_barco(self, nombre: str, r: int, c: int, orientacion: str) -> bool:
        longitud = self.flota_config[nombre]

        if  not self.validar_posicion(r, c, longitud, orientacion):
            return False

        if orientacion == 'H':
            posiciones = [(r, c+i) for i in range(longitud)]
        elif orientacion == 'V':
            posiciones = [(r+i, c) for i in range(longitud)]
        else:
            return False    
        
        barco = Barco(nombre, longitud)
        barco.posiciones = posiciones
        self.barcos.append(barco)
        id_barco = len(self.barcos)
                
        for coordenada in posiciones:
            fila, columna = coordenada
            self.tablero_oculto[fila][columna] = id_barco

        return True

    def colocar_flota_aleatoria(self) -> None:
        for barco in self.flota_config.items():
            colocado = False
            while not colocado:
                nombre, longitud = barco
                orientacion = self.rng.choice(['H', 'V'])
                r = int(self.rng.integers(0, self.filas))
                c = int(self.rng.integers(0, self.columnas))
                colocado = self.colocar_barco(nombre, r, c, orientacion)

    def reset(self, seed: int = None) -> dict:
        if seed is not None:
            self.rng = np.random.default_rng(seed)
            self.seed = seed

        self.tablero_oculto.fill(0)
        self.tablero_agente.fill(DESCONOCIDO)

        self.barcos = []
        self.turnos = 0
        self.done = False
        self.recompensa_acumulada = 0
        self.ultimo_feedback = None

        self.colocar_flota_aleatoria()
        return self.para_sentidos()

    def acciones_aplicables(self) -> list:
        return [(r, c) for r in range(self.filas) for c in range(self.columnas) if self.tablero_agente[r][c] == DESCONOCIDO]

    def test_objetivo(self) -> bool:
        return all(barco.esta_hundido() for barco in self.barcos)

    def para_sentidos(self) -> dict:
        return {
            'tablero_agente': self.tablero_agente.copy(),
            'barcos_vivos': [barco.nombre for barco in self.barcos if not barco.esta_hundido()],
            'ultimo_feedback': self.ultimo_feedback,
            'turnos': self.turnos
        }

    def step(self, accion: tuple) -> tuple:
        if accion not in self.acciones_aplicables():
            raise ValueError(f"Accion {accion} no es aplicable en el estado actual.")

        self.turnos += 1
        recompensa = -1
        self.recompensa_acumulada += recompensa


        id_barco  = self.tablero_oculto[accion]
        if id_barco == 0:
            self.tablero_agente[accion] = AGUA
            feedback = {'resultado': 'agua', 'barco': None, 'coord': accion}
        elif id_barco > 0:
            barco = self.barcos[id_barco - 1]
            barco.recibir_impacto(accion)
            if barco.esta_hundido():
                for coord in barco.posiciones:
                    self.tablero_agente[coord] = HUNDIDO
                feedback = {'resultado': 'hundido', 'barco': barco.nombre, 'coord': accion}
            else:
                self.tablero_agente[accion] = TOCADO
                feedback = {'resultado': 'impacto', 'barco': barco.nombre, 'coord': accion}
        
        self.ultimo_feedback = feedback
        self.done = self.test_objetivo()

        info = {'recompensa_acumulada': self.recompensa_acumulada, 'turnos': self.turnos}
        return self.para_sentidos(), recompensa , self.done, info

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

    def render(self, mapa_calor: np.ndarray = None):
        fig, ax = plt.subplots(figsize=(7, 6))

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
        
        ax.set_title(f"Turno: {self.turnos} | Barcos vivos: {len([b for b in self.barcos if not b.esta_hundido()])}/5 | Recompensa: {self.recompensa_acumulada}", fontsize=13, weight='bold', pad=12)
        plt.tight_layout()
        plt.show()           




