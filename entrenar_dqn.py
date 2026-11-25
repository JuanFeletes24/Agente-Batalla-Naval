"""
Entrenamiento del agente DQN.

Uso:
    python entrenar_dqn.py --nivel facil --episodios 3000
    python entrenar_dqn.py --nivel medio --episodios 3000 --desde models/dqn_facil.pt --eps-inicial 0.3
    python entrenar_dqn.py --nivel dificil --dispositivo cuda --batch 256 --actualizar-cada 4

Guarda:
    models/dqn_<nombre>.pt        pesos entrenados (<nombre> = nivel si no se indica --nombre)
    models/dqn_<nombre>_log.csv   curva de aprendizaje
    models/dqn_<nombre>.png       grafica de la curva

Ingredientes: memoria de repeticion (tensores en el mismo dispositivo que la red),
red objetivo, Double DQN, epsilon-greedy solo entre casillas legales y perdida Huber.

IMPORTANTE: la recompensa moldeada solo se usa para entrenar. Las metricas que
importan (disparos y victorias) se miden despues con evaluar.py, con semillas
distintas (las de entrenamiento empiezan en 10_000_000; las de evaluacion en 1000).
"""

import argparse
import csv
import os
import random
import time

import numpy as np
import torch
import torch.nn as nn

from ambientes import BatallaNavalEnv
from dificultad import NIVELES, ORDEN_NIVELES
from dqn_agent import (RedQ, codificar, q_enmascarado, guardar_modelo, cargar_modelo,
                       ruta_modelo, elegir_dispositivo, CARPETA_MODELOS)

SEMILLA_BASE_ENTRENAMIENTO = 10_000_000


def recompensa_moldeada(resultado: str, done: bool, ganado: bool) -> float:
    """
    Recompensa SOLO para entrenar (el entorno sigue dando -1 por disparo).
    Usa lo que el agente observa (el resultado reportado, no el real).
    """
    r = {'agua': -1.0, 'impacto': 1.0, 'hundido': 3.0}[resultado]
    if done and not ganado:
        r -= 5.0          # se acabaron los disparos
    return r


class Memoria:
    """Memoria de repeticion circular con tensores preasignados en 'dispositivo'."""

    def __init__(self, capacidad: int, forma: tuple, dispositivo):
        self.capacidad, self.dispositivo = capacidad, dispositivo
        self.s = torch.zeros((capacidad,) + forma, dtype=torch.uint8, device=dispositivo)
        self.s2 = torch.zeros_like(self.s)
        self.a = torch.zeros(capacidad, dtype=torch.long, device=dispositivo)
        self.r = torch.zeros(capacidad, dtype=torch.float32, device=dispositivo)
        self.d = torch.zeros(capacidad, dtype=torch.float32, device=dispositivo)
        self.n = 0
        self.i = 0

    def __len__(self):
        return self.n

    def guardar(self, s, a, r, s2, d):
        i = self.i
        self.s[i] = torch.from_numpy(s)
        self.s2[i] = torch.from_numpy(s2)
        self.a[i], self.r[i], self.d[i] = a, r, d
        self.i = (i + 1) % self.capacidad
        self.n = min(self.n + 1, self.capacidad)

    def muestra(self, tam: int):
        idx = torch.randint(0, self.n, (tam,), device=self.dispositivo)
        return self.s[idx].float(), self.a[idx], self.r[idx], self.s2[idx].float(), self.d[idx]


def accion_epsilon(red, estado_np, epsilon, dispositivo):
    """Con probabilidad epsilon dispara a una casilla legal al azar; si no, la de mayor Q."""
    if random.random() < epsilon:
        libres = np.flatnonzero(estado_np[0].ravel() > 0)
        return int(np.random.choice(libres))
    with torch.no_grad():
        x = torch.from_numpy(estado_np).float().unsqueeze(0).to(dispositivo)
        return int(torch.argmax(q_enmascarado(red(x), x)[0]))


def entrenar(args, guardar: bool = True) -> dict:
    dispositivo = elegir_dispositivo(args.dispositivo)
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    random.seed(args.seed)
    if dispositivo.type == 'cuda':
        torch.cuda.manual_seed_all(args.seed)
        torch.backends.cudnn.benchmark = True      # tamanos fijos: cudnn elige el kernel mas rapido

    cfg = NIVELES[args.nivel]
    nombre = args.nombre or args.nivel
    red = cargar_modelo(args.desde, dispositivo) if args.desde else RedQ(args.canales).to(dispositivo)
    red.train()
    objetivo = RedQ(red.canales).to(dispositivo)
    objetivo.load_state_dict(red.state_dict())
    optimizador = torch.optim.Adam(red.parameters(), lr=args.lr)
    perdida_fn = nn.SmoothL1Loss()
    memoria = Memoria(args.memoria, (4, cfg.filas, cfg.columnas), dispositivo)
    print(f"Entrenando nivel {cfg.nombre} en {dispositivo}"
          + (f" ({torch.cuda.get_device_name(0)})" if dispositivo.type == 'cuda' else ""), flush=True)

    registros, pasos = [], 0
    t0 = time.time()
    for ep in range(args.episodios):
        avance = min(1.0, ep / (args.eps_fraccion * args.episodios))
        epsilon = args.eps_inicial + (args.eps_final - args.eps_inicial) * avance
        env = BatallaNavalEnv(config=cfg, seed=SEMILLA_BASE_ENTRENAMIENTO + args.seed * 1_000_000 + ep)
        estado = codificar(env.tablero_agente)
        done = False
        while not done:
            a = accion_epsilon(red, estado, epsilon, dispositivo)
            _, _, done, _ = env.step((a // env.columnas, a % env.columnas))
            r = recompensa_moldeada(env.ultimo_feedback['resultado'], done, env.ganado)
            siguiente = codificar(env.tablero_agente)
            memoria.guardar(estado, a, r, siguiente, float(done))
            estado = siguiente
            pasos += 1

            if len(memoria) >= args.warmup and pasos % args.actualizar_cada == 0:
                s, acc, rew, s2, d = memoria.muestra(args.batch)
                q = red(s).flatten(1).gather(1, acc.unsqueeze(1)).squeeze(1)
                with torch.no_grad():
                    # Double DQN: la red elige la accion, la red objetivo la evalua
                    a2 = q_enmascarado(red(s2), s2).flatten(1).argmax(1, keepdim=True)
                    q2 = objetivo(s2).flatten(1).gather(1, a2).squeeze(1)
                    meta = rew + args.gamma * q2 * (1 - d)   # estado terminal: d=1 anula q2
                perdida = perdida_fn(q, meta)
                optimizador.zero_grad()
                perdida.backward()
                nn.utils.clip_grad_norm_(red.parameters(), 10.0)
                optimizador.step()

            if pasos % args.sync == 0:
                objetivo.load_state_dict(red.state_dict())

        registros.append({'episodio': ep + 1, 'disparos': env.turnos,
                          'ganado': int(env.ganado), 'epsilon': round(epsilon, 3)})
        if (ep + 1) % args.log_cada == 0:
            ult = registros[-args.log_cada:]
            print(f"ep {ep+1:>5}/{args.episodios} | eps {epsilon:.2f} | "
                  f"disparos {np.mean([x['disparos'] for x in ult]):5.1f} | "
                  f"victorias {100*np.mean([x['ganado'] for x in ult]):3.0f}% | "
                  f"{time.time()-t0:5.0f}s", flush=True)
            if guardar:
                guardar_modelo(red, ruta_modelo(nombre))      # punto de guardado

    seg = time.time() - t0
    if guardar:
        red.eval()
        guardar_modelo(red, ruta_modelo(nombre))
        guardar_curva(registros, nombre, args)
        print(f"\nModelo guardado en {ruta_modelo(nombre)}  ({seg:.0f}s)")
    return {'pasos': pasos, 'segundos': seg, 'pasos_por_s': pasos / max(seg, 1e-9)}


def guardar_curva(registros, nombre, args):
    base = os.path.join(CARPETA_MODELOS, f"dqn_{nombre}")
    with open(base + "_log.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=registros[0].keys())
        w.writeheader()
        w.writerows(registros)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        v = min(args.log_cada, len(registros))
        disp = np.array([r['disparos'] for r in registros], dtype=float)
        suav = np.convolve(disp, np.ones(v) / v, mode='valid')
        plt.figure(figsize=(7, 4))
        plt.plot(range(v, len(disp) + 1), suav)
        plt.xlabel("episodio"); plt.ylabel(f"disparos (media movil {v})")
        plt.title(f"DQN - nivel {NIVELES[args.nivel].nombre}")
        plt.grid(alpha=.3); plt.tight_layout()
        plt.savefig(base + ".png", dpi=120)
    except Exception as e:   # la grafica es opcional
        print("No se pudo graficar:", e)


def crear_parser():
    p = argparse.ArgumentParser(description="Entrena un agente DQN de Batalla Naval")
    p.add_argument('--nivel', default='facil', choices=ORDEN_NIVELES)
    p.add_argument('--nombre', default=None,
                   help="nombre del modelo (por defecto el del nivel). Asi no se sobrescribe otro entrenamiento")
    p.add_argument('--episodios', type=int, default=3000)
    p.add_argument('--dispositivo', default='auto', help="auto | cpu | cuda")
    p.add_argument('--desde', default=None, help="modelo .pt para continuar (curriculo)")
    p.add_argument('--canales', type=int, default=64)
    p.add_argument('--lr', type=float, default=1e-3)
    p.add_argument('--gamma', type=float, default=0.9)
    p.add_argument('--batch', type=int, default=64)
    p.add_argument('--actualizar-cada', type=int, default=1,
                   help="un paso de entrenamiento cada N jugadas (4 acelera mucho, sobre todo en GPU)")
    p.add_argument('--memoria', type=int, default=50_000)
    p.add_argument('--warmup', type=int, default=500)
    p.add_argument('--sync', type=int, default=500, help="pasos entre copias a la red objetivo")
    p.add_argument('--eps-inicial', type=float, default=1.0,
                   help="epsilon inicial (usa un valor bajo, p. ej. 0.15, al reanudar con --desde)")
    p.add_argument('--eps-final', type=float, default=0.05)
    p.add_argument('--eps-fraccion', type=float, default=0.6,
                   help="fraccion de episodios en la que epsilon baja de eps-inicial a eps-final")
    p.add_argument('--log-cada', type=int, default=100)
    p.add_argument('--seed', type=int, default=0)
    return p


if __name__ == "__main__":
    entrenar(crear_parser().parse_args())
