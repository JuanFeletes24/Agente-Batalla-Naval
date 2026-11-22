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


def jugar_episodio(agente, config, seed):
    env = BatallaNavalEnv(config=config, seed=seed)
    obs = env.para_sentidos()
    agente.reiniciar(config, seed=seed)
    tiempo = 0.0
    while not env.done:
        t0 = time.perf_counter()
        accion = agente.elegir_accion(obs)
        tiempo += time.perf_counter() - t0
        obs, _, _, _ = env.step(accion)
    return {
        'ganado': env.ganado,
        'disparos': env.turnos,
        'eficiencia': config.casillas_barco / env.turnos if env.ganado else np.nan,
        'ms_por_jugada': 1000 * tiempo / env.turnos,
    }


def evaluar(agentes, niveles, episodios=100, seed_base=1000, calibrar=False):
    filas = []
    for nivel in niveles:
        cfg = NIVELES[nivel].sin_limite() if calibrar else NIVELES[nivel]
        for nombre_ag, clase in agentes.items():
            agente = clase()
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
        ms_jugada=('ms_por_jugada', 'mean'),
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
