"""
Script de prueba y verificacion del entorno BatallaNavalEnv.
Permite visualizar:
1. Vista Omnisciente (Verdad Terreno) con los 5 barcos ocultos.
2. Vista del Agente tras varios disparos (Agua, Tocado y Hundido).
3. Vista del Agente con Mapa de Calor de probabilidades superpuesto.
"""

import time
import numpy as np
import matplotlib.pyplot as plt
from ambientes import BatallaNavalEnv, AGUA, TOCADO, HUNDIDO

def probar_entorno():
    print("=" * 60)
    print("INICIANDO PRUEBA DEL ENTORNO BATALLA NAVAL")
    print("=" * 60)

    # 1. Crear el entorno con una semilla fija para reproducibilidad
    semilla = 41
    env = BatallaNavalEnv(filas=10, columnas=10, seed=semilla)
    print(f"\n[1] Entorno creado exitosamente con semilla {semilla}.")
    print(f"    - Dimensiones: {env.filas}x{env.columnas}")
    print(f"    - Barcos colocados: {len(env.barcos)}")
    for b in env.barcos:
        print(f"      * {b.nombre} (tamano: {b.longitud}) en {b.posiciones}")

    # 2. Mostrar la verdad terreno (Vista Omnisciente)
    print("\n[2] Mostrando 'pintar_todo()' (Cierra la ventana para continuar)...")
    env.pintar_todo()

    # 3. Mostrar la vista inicial del agente (todo niebla / desconocido)
    print("\n[3] Mostrando 'render()' inicial del agente (todo desconocido)...")
    env.render()

    # 4. Simular disparos inteligentes para ver todos los estados:
    # Vamos a disparar a un par de casillas de agua y luego a hundir el Destructor (longitud 2)
    print("\n[4] Simulando disparos controlados:")
    
    # Disparos al agua conocidos (viendo las coordenadas del Destructor)
    destructor = [b for b in env.barcos if b.nombre == 'Destructor'][0]
    print(f"    - Destructor ubicado en: {destructor.posiciones}")
    
    # Tiro 1: Agua
    tiro_agua = (0, 0) if (0, 0) not in destructor.posiciones else (0, 1)
    obs, r, done, info = env.step(tiro_agua)
    print(f"    -> Disparo en {tiro_agua}: Feedback = {obs['ultimo_feedback']['resultado'].upper()}")

    # Tiro 2: Primer impacto al Destructor
    tiro_impacto = destructor.posiciones[0]
    obs, r, done, info = env.step(tiro_impacto)
    print(f"    -> Disparo en {tiro_impacto}: Feedback = {obs['ultimo_feedback']['resultado'].upper()} en {obs['ultimo_feedback']['barco']}")

    # Mostrar como se ve el impacto
    print("\n    Mostrando tablero del agente con 1 agua y 1 impacto...")
    env.render()

    # Tiro 3: Segundo impacto al Destructor (¡HUNDIDO!)
    tiro_hundido = destructor.posiciones[1]
    obs, r, done, info = env.step(tiro_hundido)
    print(f"    -> Disparo en {tiro_hundido}: Feedback = {obs['ultimo_feedback']['resultado'].upper()} ({obs['ultimo_feedback']['barco']})")

    # Mostrar como se ve el barco completamente hundido
    print("\n    Mostrando tablero del agente con el Destructor HUNDIDO...")
    env.render()

    # 5. Probar el render con un Mapa de Calor sintetico
    print("\n[5] Probando 'render()' con Mapa de Calor de probabilidades superpuesto...")
    # Creamos un mapa sintetico con valores entre 0.0 y 1.0 (simulando la creencia del agente)
    mapa_sintetico = np.zeros((10, 10))
    for r in range(10):
        for c in range(10):
            # Mayor probabilidad cerca del centro
            mapa_sintetico[r, c] = np.exp(-((r - 5)**2 + (c - 5)**2) / 20.0)
    
    env.render(mapa_calor=mapa_sintetico)

    print("\n" + "=" * 60)
    print("¡TODAS LAS PRUEBAS DE VISUALIZACION COMPLETADAS CON EXITO!")
    print("=" * 60)

if __name__ == "__main__":
    probar_entorno()
