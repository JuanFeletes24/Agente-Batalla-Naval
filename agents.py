import ambientes
import random
import numpy as np

# Clase padre Agente

class Agente:
    def __init__(self, name:str = "Agent"):
        self.name = name
        self.action = []
        self.states = []

    def restart(self):
        self.action = []
        self.states = []

    def make_decision(self, state) -> tuple:
        raise NotImplementedError("Este método debe ser implementado por la clase hija")

class RandomAgent(Agente):
    def __init__(self, seed:int = None):
        super().__init__(name="RandomAgent")
        self.seed = seed
        if seed is not None:
            random.seed(seed)

    def make_decision(self, percepts: dict) -> tuple:
        tablero_agente = percepts['tablero_agente']
        filas, columnas = tablero_agente.shape
        return random.choice([(i,j) for i in range(filas) for j in range(columnas) if tablero_agente[i, j] == -1])
                    
