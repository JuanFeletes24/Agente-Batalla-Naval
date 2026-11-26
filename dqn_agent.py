"""
Agente Deep Q-Learning (DQN) para Batalla Naval - version minima.

- Entrada: el tablero que ve el agente, convertido a 4 canales binarios
  (desconocido, agua, tocado, hundido).
- Red: totalmente convolucional, con UN valor Q por casilla. Por eso el mismo
  modelo puede usarse en tableros de cualquier tamano.
- Las casillas ya disparadas se enmascaran (Q = -inf): nunca se repite un disparo.

Este archivo contiene lo que comparten el entrenamiento (entrenar_dqn.py) y el
agente que juega (AgenteDQN). Requiere PyTorch.
"""

import os
import unicodedata

import numpy as np
import torch
import torch.nn as nn

from ambientes import DESCONOCIDO, AGUA, TOCADO, HUNDIDO
from agents import Agente

CARPETA_MODELOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")



# Representacion del estado


def codificar(tablero: np.ndarray) -> np.ndarray:
    """tablero (H, W) con valores -1/0/1/2  ->  array uint8 (4, H, W) de ceros y unos."""
    return np.stack([tablero == DESCONOCIDO, tablero == AGUA,
                     tablero == TOCADO, tablero == HUNDIDO]).astype(np.uint8)



# Red

class RedQ(nn.Module):
    """Convolucional completa: (B, 4, H, W) -> (B, H, W), un Q por casilla."""

    def __init__(self, canales: int = 64):
        super().__init__()
        self.canales = canales
        self.red = nn.Sequential(
            nn.Conv2d(4, canales, 3, padding=1), nn.ReLU(),
            nn.Conv2d(canales, canales, 3, padding=1), nn.ReLU(),
            nn.Conv2d(canales, canales, 3, padding=1), nn.ReLU(),
            nn.Conv2d(canales, canales, 3, padding=1), nn.ReLU(),
            nn.Conv2d(canales, 1, 1),
        )

    def forward(self, x):
        return self.red(x).squeeze(1)


def q_enmascarado(q: torch.Tensor, estado: torch.Tensor) -> torch.Tensor:
    """Pone -inf a las casillas ya disparadas (canal 0 = desconocido)."""
    legal = estado[:, 0] > 0.5
    return q.masked_fill(~legal, float('-inf'))


# Guardar / cargar modelos

def clave_nivel(config) -> str:
    """'Fácil' -> 'facil' (coincide con las claves de NIVELES)."""
    texto = unicodedata.normalize('NFD', config.nombre.lower())
    return ''.join(ch for ch in texto if unicodedata.category(ch) != 'Mn')


def ruta_modelo(clave: str) -> str:
    return os.path.join(CARPETA_MODELOS, f"dqn_{clave}.pt")


def elegir_dispositivo(preferencia: str = 'auto') -> torch.device:
    """'auto' usa la GPU NVIDIA (CUDA) si PyTorch la detecta; si no, la CPU."""
    if preferencia == 'auto':
        return torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    if preferencia.startswith('cuda') and not torch.cuda.is_available():
        raise RuntimeError(
            "PyTorch no detecta la GPU (torch.cuda.is_available() es False). "
            "Instala la version con CUDA desde pytorch.org o usa --dispositivo cpu.")
    return torch.device(preferencia)


def guardar_modelo(red: RedQ, ruta: str):
    """Guarda los pesos siempre en CPU: el archivo sirve igual con o sin GPU."""
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    pesos = {k: v.detach().cpu() for k, v in red.state_dict().items()}
    torch.save({'canales': red.canales, 'pesos': pesos}, ruta)


def cargar_modelo(ruta: str, dispositivo='cpu') -> RedQ:
    datos = torch.load(ruta, map_location='cpu')
    red = RedQ(datos['canales'])
    red.load_state_dict(datos['pesos'])
    red.to(dispositivo)
    red.eval()
    return red


def modelos_disponibles() -> list:
    if not os.path.isdir(CARPETA_MODELOS):
        return []
    return [f for f in os.listdir(CARPETA_MODELOS) if f.startswith("dqn_") and f.endswith(".pt")]


# Agente que juega con un modelo ya entrenado

class AgenteDQN(Agente):
    """
    Elige siempre la casilla de mayor Q entre las no disparadas.
    Carga automaticamente models/dqn_<nivel>.pt segun el 'config' recibido (o la 'ruta'
    indicada); el modelo se lee la primera vez que empieza una partida (restart).
    """

    def __init__(self, seed: int = None, config=None, ruta: str = None):
        super().__init__(name="DQN", seed=seed, config=config)
        self.ruta = ruta
        self.red = None

    def restart(self, seed: int = None):
        super().restart(seed)
        if self.red is None:
            self.red = cargar_modelo(self._ruta_modelo())

    def _ruta_modelo(self) -> str:
        if self.ruta is None and self.config is None:
            raise ValueError("AgenteDQN necesita 'config' (el nivel) o 'ruta' a un modelo .pt")
        ruta = self.ruta or ruta_modelo(clave_nivel(self.config))
        if not os.path.exists(ruta):
            nivel = f" --nivel {clave_nivel(self.config)}" if self.config is not None else ""
            raise FileNotFoundError(
                f"No hay modelo entrenado en {ruta}. Entrena uno con: python entrenar_dqn.py{nivel}")
        return ruta

    @torch.no_grad()
    def make_decision(self, percepts: dict) -> tuple:
        t = percepts['tablero_agente']
        x = torch.from_numpy(codificar(t)).float().unsqueeze(0)
        q = q_enmascarado(self.red(x), x)[0]
        self._q = q.numpy()
        idx = int(torch.argmax(q))
        return (idx // t.shape[1], idx % t.shape[1])

    def estado_interno(self) -> dict:
        legal = np.isfinite(self._q)
        mapa = np.where(legal, self._q, np.nan)
        params = sum(p.numel() for p in self.red.parameters())
        return {'mapa': mapa, 'tipo_mapa': 'valor Q',
                'info': {'Q maximo': round(float(self._q[legal].max()), 3),
                         'Q medio': round(float(self._q[legal].mean()), 3),
                         'parametros de la red': params},
                'evaluaciones': int(legal.sum()), 
                'memoria': params,
                'nodos_generados': int(legal.sum()),
                'nodos_expandidos': 1
                }
