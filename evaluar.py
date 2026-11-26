"""
Evaluacion comparativa de agentes en los distintos niveles de dificultad.

Todos los agentes juegan las MISMAS partidas (mismas semillas => misma flota y
mismo ruido), lo que hace la comparacion justa.

Uso:
    python evaluar.py                                   # todos los niveles y agentes
    python evaluar.py --episodios 200 --niveles medio dificil
    python evaluar.py --agentes caza --calibrar         # percentiles SIN limite de disparos
    python evaluar.py --csv resultados.csv

Para agregar un agente nuevo: heredar de agents.Agente y registrarlo en agents.AGENTES.
"""

import argparse
import time

import numpy as np
import pandas as pd

from ambientes import BatallaNavalEnv
from agents import AGENTES
from dificultad import NIVELES, ORDEN_NIVELES


def jugar_episodio(agente, config, seed, disposicion=None):
    """
    Juega una partida completa y devuelve sus metricas.
    Con 'disposicion' [(nombre, fila, col, 'H'|'V'), ...] la flota queda donde el usuario
    la coloco (instancia manual); si es None se coloca al azar segun la semilla.

    El tiempo solo cuenta lo que tarda el agente en decidir (make_decision).
    El estado interno se pide fuera del cronometro para no inflar el tiempo.
    """
    env = BatallaNavalEnv(config=config, seed=seed, disposicion=disposicion)
    obs = env.para_sentidos()
    agente.restart(seed=seed)
    tiempo = 0.0
    tiempo_cpu = 0.0
    nodos_generados = 0
    nodos_expandidos = 0
    evaluaciones = 0        
    memoria_max = 0           
    while not env.done:
        c0 = time.process_time()
        t0 = time.perf_counter()
        accion = agente.make_decision(obs)
        tiempo += time.perf_counter() - t0
        tiempo_cpu += time.process_time() - c0
        interno = agente.estado_interno() or {}
        evaluaciones += interno.get('evaluaciones', 0)
        nodos_generados += interno.get('nodos_generados', interno.get('evaluaciones', 0))
        nodos_expandidos += interno.get('nodos_expandidos', 0)
        memoria_max = max(memoria_max, interno.get('memoria', 0))
        obs, _, _, _ = env.step(accion)
    minimo = config.casillas_barco          
    return {
        'ganado': env.ganado,
        'disparos': env.turnos,
        'costo': -env.recompensa_acumulada,
        'eficiencia': minimo / env.turnos if env.ganado else np.nan,
        'optimo': bool(env.ganado and env.turnos == minimo),
        'brecha': env.turnos - minimo if env.ganado else np.nan,
        'ms_por_jugada': 1000 * tiempo / env.turnos,
        'tiempo_total_s': tiempo,
        'evaluaciones': evaluaciones,
        'memoria_max': memoria_max,
        'recompensa': env.recompensa_acumulada,
        'cpu_ms_por_jugada': 1000 * tiempo_cpu / env.turnos,
        'tiempo_cpu_s': tiempo_cpu,
        'nodos_generados': nodos_generados,
        'nodos_expandidos': nodos_expandidos,
    }

def evaluar(agentes, niveles, episodios=100, seed_base=1000, calibrar=False):
    filas = []
    for nivel in niveles:
        cfg = NIVELES[nivel].sin_limite() if calibrar else NIVELES[nivel]
        for nombre_ag, clase in agentes.items():
            agente = clase(config=cfg)
            for i in range(episodios):
                res = jugar_episodio(agente, cfg, seed_base + i)
                filas.append({'nivel': nivel, 'agente': nombre_ag, 'seed': seed_base + i, **res})
    return pd.DataFrame(filas)


def resumen(df):
    g = df.groupby(['nivel', 'agente'], sort=False)
    out = g.agg(
        victorias_pct=('ganado', lambda x: 100 * x.mean()),
        disparos_media=('disparos', 'mean'),
        disparos_std=('disparos', 'std'),
        eficiencia=('eficiencia', 'mean'),
        optimas_pct=('optimo', lambda x: 100 * x.mean()),
        brecha_media=('brecha', 'mean'),
        ms_jugada=('ms_por_jugada', 'mean'),
        tiempo_partida_s=('tiempo_total_s', 'mean'),
        evaluaciones_media=('evaluaciones', 'mean'),
        memoria_max=('memoria_max', 'max'),
        recompensa_media=('recompensa', 'mean'),
        cpu_ms_jugada=('cpu_ms_por_jugada', 'mean'),
        tiempo_cpu_s=('tiempo_cpu_s', 'mean'),
        nodos_gen=('nodos_generados', 'mean'),
        nodos_exp=('nodos_expandidos', 'mean')
    ).round(2)
    return out



def percentiles(df):
    g = df.groupby(['nivel', 'agente'], sort=False)['disparos']
    return pd.DataFrame({
        'p25': g.quantile(.25), 'mediana': g.quantile(.5), 'p75': g.quantile(.75),
        'p90': g.quantile(.9), 'max': g.max()}).round(1)


def main():
    p = argparse.ArgumentParser(description="Evalua agentes en los niveles de dificultad")
    p.add_argument('--episodios', type=int, default=100)
    p.add_argument('--niveles', nargs='+', default=ORDEN_NIVELES, choices=ORDEN_NIVELES)
    p.add_argument('--agentes', nargs='+', default=list(AGENTES), choices=list(AGENTES))
    p.add_argument('--seed', type=int, default=1000, help="semilla base")
    p.add_argument('--calibrar', action='store_true',
                   help="ignora el limite de disparos y muestra percentiles de disparos")
    p.add_argument('--csv', default=None, help="guarda todas las partidas en un CSV")
    args = p.parse_args()

    agentes = {k: AGENTES[k] for k in args.agentes}
    df = evaluar(agentes, args.niveles, args.episodios, args.seed, args.calibrar)

    pd.set_option('display.width', 140)
    pd.set_option('display.max_columns', None)
    if args.calibrar:
        print("\nDisparos necesarios para ganar SIN limite (usar para fijar max_disparos):\n")
        print(percentiles(df))
    else:
        print("\nResultados con las reglas reales de cada nivel:\n")
        print(resumen(df))
    if args.csv:
        df.to_csv(args.csv, index=False)
        print(f"\nPartidas guardadas en {args.csv}")


if __name__ == "__main__":
    main()