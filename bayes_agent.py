from itertools import combinations
import numpy as np
from ambientes import DESCONOCIDO, AGUA, TOCADO, HUNDIDO, FLOTA_DEFAULT
from agents import Agente

class AgenteBayesiano(Agente):

    def __init__(self, seed: int = None, config=None):
        super().__init__(name="Red Bayesiana", seed=seed, config=config)
        self.flota_config = dict(config.flota) if config is not None else dict(FLOTA_DEFAULT)
        self.permitir_adyacentes = True if config is None else config.permitir_adyacentes
        self.colocacion = 'uniforme' if config is None else config.colocacion
        self.prob_ruido = 0.0 if config is None else float(config.prob_ruido)

    def _barcos_restantes(self, percepts:dict) -> list:
        if percepts['barcos_vivos'] is not None:
            return [self.flota_config[nombre] for nombre in percepts['barcos_vivos']]
        else:
            todos = list(self.flota_config.values())
            k = percepts['n_barcos_vivos']
            hundidas = int(np.sum(percepts['tablero_agente'] == HUNDIDO))
            suma_objetivo = sum(todos) - hundidas
            candidatas = [list(c) for c in combinations(todos, k) if sum(c) == suma_objetivo]
            if candidatas:
                return candidatas[0]
            else:
                return todos[:k]

    def _nombres_restantes(self, percepts: dict, longitudes: list) -> list:
        """Etiqueta de cada barco vivo (su nombre, o 'Barco de L' si la flota esta oculta)."""
        if percepts['barcos_vivos'] is not None:
            return [f"{nombre} ({self.flota_config[nombre]})" for nombre in percepts['barcos_vivos']]
        nombres = []
        for i, L in enumerate(longitudes):
            repetidos = longitudes.count(L) > 1
            nombres.append(f"Barco de {L}" + (f" (#{longitudes[:i + 1].count(L)})" if repetidos else ""))
        return nombres

    def _prior_posicion(self, pos: list, filas: int, cols: int) -> float:
        if self.colocacion == 'bordes':
            for (r,c) in pos:
                if r in (0, filas - 1) or c in (0, cols - 1):
                    return 1.0
            return 0.15
        return 1.0

    def _verosimilitud_posicion(self, pos: list, tablero_obs: np.ndarray, rho: float) -> float:
        filas, cols = tablero_obs.shape
        eps = self.prob_ruido
        for (r,c) in pos:
            if tablero_obs[r,c] == HUNDIDO:
                return 0.0

        if not self.permitir_adyacentes:
            for (r, c) in pos:
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        r2, c2 = r + dr, c + dc
                        if 0 <= r2 < filas and 0 <= c2 < cols and tablero_obs[r2, c2] == HUNDIDO:
                            return 0.0
                        
        if eps == 0.0 and all(tablero_obs[r, c] == TOCADO for r, c in pos):
            return 0.0

        peso = 1.0

        denom_tocado = rho * (1.0 - eps) + (1.0 - rho) * eps
        denom_agua = rho * eps + (1.0 - rho) * (1.0 - eps)

        for (r,c) in pos:
            if tablero_obs[r,c] == AGUA:
                if eps == 0.0:
                    return 0.0
                elif eps > 0.0:
                    peso *= eps / max(1e-9, denom_agua)
            elif tablero_obs[r, c] == TOCADO:
                if denom_tocado == 0.0:
                    peso *= 1e6
                else:
                    peso *= (1.0 - eps) / denom_tocado
        return peso


    def _marginal_barco(self, longitud: int, tablero_obs: np.ndarray, rho: float) -> tuple:
        filas, cols = tablero_obs.shape
        configs = []
        pesos = []
        generadas = 0

        for r in range(filas):
            for c in range(cols - longitud + 1):
                pos = [(r, c + i) for i in range(longitud)]
                verosim = self._verosimilitud_posicion(pos, tablero_obs, rho)
                generadas += 1
                if verosim > 0.0:
                    w = self._prior_posicion(pos, filas, cols) * verosim
                    configs.append(pos)
                    pesos.append(w)
        if longitud > 1:
            for r in range(filas - longitud + 1):
                for c in range(cols):
                    pos = [(r + i, c) for i in range(longitud)]
                    verosim = self._verosimilitud_posicion(pos, tablero_obs, rho)
                    generadas += 1
                    if verosim > 0.0:
                        w = self._prior_posicion(pos, filas, cols) * verosim
                        configs.append(pos)
                        pesos.append(w)

        pk = np.zeros((filas, cols), dtype=float)
        if not configs:
            return (pk, 0, generadas)
        suma_pesos = sum(pesos)
        for pos, w in zip(configs, pesos): 
            prob = w / suma_pesos
            for (rr,cc) in pos:
                pk[rr, cc] += prob
        return (np.clip(pk, 0.0, 1.0), len(configs), generadas)

    def _calcular_mapa_posterior(self, percepts: dict) -> tuple:
        tablero_obs = percepts['tablero_agente']
        filas, cols = tablero_obs.shape
        longitudes = self._barcos_restantes(percepts)
        k = len(longitudes)
        p_ningun_barco = np.ones((filas, cols), dtype=float)
        total_configs = 0
        marginales = []                     # un mapa por barco vivo: P(ese barco ocupa la casilla)
        nombres = self._nombres_restantes(percepts, longitudes)
        total_generadas = 0

        for L in longitudes:
            otras = sum(longitudes) - L
            rho = min(0.5, otras / (filas * cols)) if k > 1 else 0.0
            pk, n_cfg, n_gen = self._marginal_barco(L, tablero_obs, rho)
            total_generadas += n_gen
            total_configs += n_cfg
            p_ningun_barco *= (1.0 - pk)
            marginales.append({'etiqueta': nombres[len(marginales)], 'longitud': L,
                               'mapa': np.where(tablero_obs == DESCONOCIDO, pk, np.nan),
                               'configs': n_cfg})

        mapa_post = 1.0 - p_ningun_barco
        mapa = np.where(tablero_obs == DESCONOCIDO, mapa_post, np.nan)

        return (mapa, total_configs, total_generadas, len(longitudes), marginales)

    def make_decision(self, percepts: dict) -> tuple:
        mapa, n_configs, n_generadas, n_barcos, marginales = self._calcular_mapa_posterior(percepts)
        max_p = float(np.nanmax(mapa))
        mejores = [tuple(int(v) for v in rc) for rc in np.argwhere(np.isclose(mapa, max_p, atol=1e-12))]
        elegida = mejores[int(self.rng.integers(len(mejores)))]
        self._ult = {'mapa': mapa, 'configs': n_configs, 'barcos': n_barcos, 'max_p': max_p,
                     'marginales': marginales, 'generadas':n_generadas}
        return elegida

    def estado_interno(self) -> dict:
        if not hasattr(self, '_ult'):
            return {}

        u = self._ult

        return {
            'mapa': u['mapa'],
            'tipo_mapa': 'probabilidad a posteriori P(Barco | e)',
            'info': {'P maxima': round(u['max_p'], 4), 'hipotesis evaluadas': u['configs'], 'barcos en red': u['barcos']},
            'marginales': u['marginales'],           # mapas por barco, para elegirlos en la interfaz
            'evaluaciones': u['configs'],
            'memoria': u['configs'] + int(u['mapa'].size),
            'nodos_generados': u['generadas'],
            'nodos_expandidos': u['configs']
        }
        

        

            


  


  

  