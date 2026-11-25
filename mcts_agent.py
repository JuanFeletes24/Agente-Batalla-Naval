import math
import numpy as np
from itertools import combinations
from ambientes import DESCONOCIDO, AGUA, TOCADO, HUNDIDO, FLOTA_DEFAULT
from agents import Agente

class NodoMCTS:
    def __init__(self, padre=None, accion_entrada=None, obs_entrada=None):
        self.padre = padre
        self.accion_entrada = accion_entrada
        self.obs_entrada = obs_entrada
        self.visitas = 0
        self.valor_accion = {}
        self.visitas_accion = {}
        self.hijos = {}

    def seleccionar_accion(self, acciones_legales:list, c_param:float = 1.414) -> tuple:
        for accion in acciones_legales:
            if accion not in self.valor_accion:
                return accion 
        
        ucb = {}

        for accion in acciones_legales:
            n_a = self.visitas_accion[accion]
            q_medio = self.valor_accion[accion] / n_a
            exploracion = c_param * math.sqrt(math.log(self.visitas) / n_a)
            ucb[accion] = q_medio + exploracion
        
        return max(ucb, key=ucb.get)    

    def obtener_o_crear_hijo(self, accion:tuple, obs:str) -> 'NodoMCTS':
        if (accion, obs) not in self.hijos:
            self.hijos[(accion, obs)] = NodoMCTS(padre=self, accion_entrada=accion, obs_entrada=obs)
        return self.hijos[(accion, obs)]

    def actualizar(self, accion:tuple, recompensa:float):
        self.visitas += 1
        self.visitas_accion[accion] = self.visitas_accion.get(accion, 0) + 1
        self.valor_accion[accion] = self.valor_accion.get(accion, 0.0) + recompensa

class AgenteMCTS(Agente):
    def __init__(self, seed: int = None, config=None, n_simulaciones: int = 200, c_param: float = 1.414):
        super().__init__(name="MCTS", seed=seed, config=config)
        self.n_simulaciones = n_simulaciones
        self.c_param = c_param
        self.flota_config = dict(config.flota) if config is not None else dict(FLOTA_DEFAULT)
        self.permitir_adyacentes = True if config is None else config.permitir_adyacentes

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
                return candidatas[int(self.rng.integers(len(candidatas)))]
            else:
                return todos[:k]

    def _es_colocacion_valida(self, posiciones: list, tablero_obs: np.ndarray, tablero_hip: np.ndarray) -> bool:
        filas, cols = tablero_obs.shape
        for (r, c) in posiciones:
            if not (0 <= r < filas and 0 <= c < cols):
                return False
            if tablero_obs[r, c] == AGUA or tablero_obs[r, c] == HUNDIDO:
                return False
            if tablero_hip[r, c] != 0:
                return False
            if not self.permitir_adyacentes:
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        r2, c2 = r + dr, c + dc
                        if 0 <= r2 < filas and 0 <= c2 < cols:
                            if tablero_hip[r2, c2] != 0 or tablero_obs[r2, c2] == HUNDIDO:
                                return False

        return any(tablero_obs[r, c] == DESCONOCIDO for r, c in posiciones)

    def _generar_hipotesis(self, tablero_obs: np.ndarray, longitudes: list) -> tuple:
        for _ in range(30):
            tablero_hip = np.zeros_like(tablero_obs, dtype = int)
            posiciones_barcos = []
            pendientes = sorted(longitudes, reverse=True)
            tocados = [tuple(int(v) for v in rc) for rc in np.argwhere(tablero_obs == TOCADO)]

            while tocados and pendientes:
                tr, tc = tocados[0]
                opciones = []
                for L in set(pendientes):
                    for d in range(L):
                        L_horizontales = [(tr, tc - d + i) for i in range(L)]
                        L_verticales = [(tr - d + i, tc) for i in range(L)]
                        posibles = [L_horizontales, L_verticales]
                        for pos in posibles:
                            if self._es_colocacion_valida(pos, tablero_obs, tablero_hip):
                                opciones.append(pos)
                if opciones:
                    mejor_cob = max(sum(1 for t in tocados if t in pos) for pos in opciones)
                    mejores = [pos for pos in opciones if sum(1 for t in tocados if t in pos) == mejor_cob]
                    seleccion = mejores[int(self.rng.integers(len(mejores)))]
                    posiciones_barcos.append(seleccion)
                    tablero_hip[tuple(zip(*seleccion))] = len(posiciones_barcos)
                    pendientes.remove(len(seleccion))
                    tocados = [t for t in tocados if t not in seleccion]
                else:
                    tocados.pop(0)

            filas, cols = tablero_obs.shape
            for L in pendientes:
                for _ in range(200):
                    orient = str(self.rng.choice(['H', 'V']))
                    r = int(self.rng.integers(filas))
                    c = int(self.rng.integers(cols))
                    pos = [(r, c + i) for i in range(L)] if orient == 'H' else [(r + i, c) for i in range(L)]
                    if self._es_colocacion_valida(pos, tablero_obs, tablero_hip):
                        posiciones_barcos.append(pos)
                        tablero_hip[tuple(zip(*pos))] = len(posiciones_barcos)
                        break
            if len(posiciones_barcos) == len(longitudes):
                return tablero_hip, posiciones_barcos
        return tablero_hip, posiciones_barcos


    def _acciones_candidatas(self, tablero_sim: np.ndarray) -> list:
        alineadas = set()
        vecinas = set()
        filas, cols = tablero_sim.shape

        for r,c in np.argwhere(tablero_sim == TOCADO):
            r, c = int(r), int(c)
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                (rr, cc) = (r + dr, c + dc)
                if 0 <= rr < filas and 0 <= cc < cols and tablero_sim[rr, cc] == DESCONOCIDO:
                    pr, pc = r - dr, c - dc
                    if 0 <= pr < filas and 0 <= pc < cols and tablero_sim[pr, pc] == TOCADO:
                        alineadas.add((rr, cc))
                    else:
                        vecinas.add((rr, cc))
        if alineadas:
            alineadas = list(alineadas)
            self.rng.shuffle(alineadas)
            return alineadas
        elif vecinas:
            vecinas = list(vecinas)
            self.rng.shuffle(vecinas)
            return vecinas
        
        libres = self.casillas_libres(tablero_sim) 
        par = [rc for rc in libres if (rc[0] + rc[1]) % 2 == 0]
        res = par if par else libres
        self.rng.shuffle(res)
        return res

    @staticmethod
    def _simular_disparo(tablero_sim: np.ndarray, accion: tuple, tablero_hip: np.ndarray, pos_barcos: list) -> tuple:
        r, c = accion
        id_barco = tablero_hip[r, c]
        if id_barco == 0: 
            tablero_sim[r, c] = AGUA
            return ('agua', 0.0)
        elif id_barco > 0:
            tablero_sim[r, c] = TOCADO
            pos = pos_barcos[id_barco - 1]
            if all(tablero_sim[rr, cc] in (TOCADO, HUNDIDO) for rr, cc in pos):
                for rr, cc in pos:
                    tablero_sim[rr, cc] = HUNDIDO
                return ('hundido', 1.0)
            return ('impacto', 0.7)
    
    def make_decision(self, percepts: dict) -> tuple:
        tablero_obs = percepts['tablero_agente']
        raiz = NodoMCTS()
        pasos_sim = 0
        nodos_creados = 1
        gamma = 0.8

        for _ in range(self.n_simulaciones):
            longitudes = self._barcos_restantes(percepts)
            tablero_hip, pos_barcos = self._generar_hipotesis(tablero_obs, longitudes)
            tablero_sim = tablero_obs.copy()

            nodo = raiz
            camino = []
            for _ in range(3):
                cand = self._acciones_candidatas(tablero_sim)
                if not cand or (pos_barcos and all(tablero_sim[r, c] == HUNDIDO for b in pos_barcos for r, c in b)):
                    break
                accion = nodo.seleccionar_accion(cand, self.c_param)
                obs_res, r_inm = self._simular_disparo(tablero_sim, accion, tablero_hip, pos_barcos)
                pasos_sim += 1
                camino.append((nodo, accion, r_inm))
                es_nuevo = (accion, obs_res) not in nodo.hijos
                if es_nuevo:
                    nodos_creados += 1

                nodo = nodo.obtener_o_crear_hijo(accion, obs_res)

                if es_nuevo:
                    break

            retorno = 0.0 
            factor = 1.0

            for _ in range(5):
                cand = self._acciones_candidatas(tablero_sim)
                if not cand or (pos_barcos and all(tablero_sim[r, c] == HUNDIDO for b in pos_barcos for r, c in b)):
                    break
                acc_r = cand[int(self.rng.integers(len(cand)))]
                _, r_paso = self._simular_disparo(tablero_sim, acc_r, tablero_hip, pos_barcos)
                pasos_sim += 1
                retorno += factor * r_paso
                factor *= gamma

            for nodo_p, acc_p, r_p in reversed(camino):
                retorno = r_p + gamma * retorno
                nodo_p.actualizar(acc_p, retorno)

        self._ult = {
            'raiz': raiz,
            'tablero': tablero_obs,
            'evals': pasos_sim,
            'nodos': nodos_creados
        }

        if not raiz.visitas_accion:
            return self.casillas_libres(tablero_obs)[0]

        return max(raiz.visitas_accion, key=lambda a: (raiz.visitas_accion[a], raiz.valor_accion[a] / raiz.visitas_accion[a]))

    def estado_interno(self) -> dict:
        if not hasattr(self, '_ult'):
            return {}
        u = self._ult
        raiz = u['raiz']
        mapa = np.full(u['tablero'].shape, np.nan, dtype=float)

        for (r,c), n_a in raiz.visitas_accion.items():
            mapa[r,c] = raiz.valor_accion[(r,c)] / n_a

        return {
            'mapa': mapa,
            'tipo_mapa': 'valor Q estimado (MCTS)',
            'info': {'simulaciones':raiz.visitas, 'candidatas exploradas':len(raiz.visitas_accion), 'nodos en el arbol': u['nodos']},
            'evaluaciones': u['evals'],
            'memoria': u['nodos']
        }
 


  

  

  

