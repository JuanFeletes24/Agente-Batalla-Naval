"""
Comparacion de algoritmos sobre la misma instancia, sin ninguna dependencia de interfaz.

    df, errores = ejecutar_comparacion(['caza', 'mcts'], instancia, n=20, seed_base=1000)
    resumen_agentes(df)                        # tabla: una fila por agente
    dibujar_comparacion(figura, df, minimo)    # graficas en una matplotlib.figure.Figure

Todos los agentes juegan las MISMAS partidas: la partida i usa la semilla seed_base + i, asi que
comparten flota (y ruido del sonar). Con una instancia de flota manual, la flota es siempre la
misma. Con n = 1 se comparan los agentes sobre una unica instancia.

La pestaña "Comparar" de app_qt.py y el dialogo Humano vs. Maquina usan este modulo.
"""

import numpy as np
import pandas as pd
from matplotlib.colors import to_hex, to_rgb

from agents import AGENTES
from evaluar import jugar_episodio
from instancia import Instancia

# Columnas de la tabla comparativa (clave -> formato). Se calculan en resumen_agentes().
COLUMNAS_RESUMEN = [
    'Partidas', 'Victorias (%)', 'Disparos (media)', 'Disparos (desv.)', 'Disparos (mín.)',
    'Disparos (máx.)', 'Eficiencia', 'Óptimas (%)', 'Brecha al óptimo', 'Recompensa acum.',
    'Tiempo/jugada (ms)', 'Tiempo/partida (s)', 'Evaluaciones', 'Memoria máx.',
    'Tiempo CPU (s)','Nodos generados', 'Nodos expandidos',
    ]


def nombre_agente(clave: str) -> str:
    """Nombre legible del agente registrado con esa clave."""
    return AGENTES[clave]().name


def ejecutar_comparacion(claves, instancia: Instancia, n: int = 10, seed_base: int = 1000,
                         progreso=None, cancelar=None):
    """
    Juega n partidas por agente sobre la instancia y devuelve (DataFrame, errores).

      progreso(hechas, total, texto): se llama tras cada partida (opcional).
      cancelar(): si devuelve True se detiene y se devuelven las partidas ya jugadas.
      errores: {clave: mensaje} de los agentes que no pudieron jugar (p. ej. DQN sin modelo
               para ese nivel); no impiden que los demas se comparen.
    """
    config = instancia.config
    filas, errores = [], {}
    total = len(claves) * n
    for k, clave in enumerate(claves):
        try:
            agente = AGENTES[clave](config=config)
            nombre = agente.name
            for i in range(n):
                if cancelar is not None and cancelar():
                    return pd.DataFrame(filas), errores
                res = jugar_episodio(agente, config, seed_base + i, instancia.disposicion)
                filas.append({'agente': clave, 'nombre': nombre, 'seed': seed_base + i, **res})
                if progreso is not None:
                    progreso(k * n + i + 1, total, f"{nombre}: partida {i + 1} de {n}")
        except Exception as e:                       # un agente roto no debe tumbar la comparacion
            errores[clave] = str(e) if isinstance(e, FileNotFoundError) else f"{type(e).__name__}: {e}"
            filas = [f for f in filas if f['agente'] != clave]     # sin resultados parciales
            if progreso is not None:
                progreso((k + 1) * n, total, f"{clave}: no se pudo ejecutar")
    return pd.DataFrame(filas), errores


def resumen_agentes(df: pd.DataFrame) -> pd.DataFrame:
    """Una fila por agente con todas las metricas (ver COLUMNAS_RESUMEN)."""
    if df.empty:
        return pd.DataFrame(columns=COLUMNAS_RESUMEN)
    g = df.groupby('nombre', sort=False)
    tabla = pd.DataFrame({
        'Partidas': g.size(),
        'Victorias (%)': 100 * g['ganado'].mean(),
        'Disparos (media)': g['disparos'].mean(),
        'Disparos (desv.)': g['disparos'].std(ddof=0),
        'Disparos (mín.)': g['disparos'].min(),
        'Disparos (máx.)': g['disparos'].max(),
        'Eficiencia': g['eficiencia'].mean(),               # solo partidas ganadas
        'Óptimas (%)': 100 * g['optimo'].mean(),
        'Brecha al óptimo': g['brecha'].mean(),              # solo partidas ganadas
        'Recompensa acum.': -g['costo'].mean(),
        'Tiempo/jugada (ms)': g['ms_por_jugada'].mean(),
        'Tiempo/partida (s)': g['tiempo_total_s'].mean(),
        'Evaluaciones': g['evaluaciones'].mean(),
        'Memoria máx.': g['memoria_max'].max(),
        'Tiempo CPU (s)': g['tiempo_cpu_s'].mean(),
        'Nodos generados': g['nodos_generados'].mean(),
        'Nodos expandidos': g['nodos_expandidos'].mean(),
    })
    return tabla[COLUMNAS_RESUMEN]


# ---------------------------------------------------------------------------
# Graficas
# ---------------------------------------------------------------------------
PALETA = ["#A6E9B1", '#FFB74D', '#BA68C8', '#4FC3F7', '#E57373', '#d9c24a', '#5cc8c8']
FONDO_FIGURA, FONDO_EJES, TEXTO = '#2d2d2d', '#1f1f1f', '#e8f0f5'


def _mezcla(color, hacia='#ffffff', t=0.25):
    """Mezcla 'color' con 'hacia' (t = 0 deja el color, t = 1 da 'hacia'); devuelve '#rrggbb'."""
    a, b = np.array(to_rgb(color)), np.array(to_rgb(hacia))
    return to_hex(a + (b - a) * t)


def _estilo(ax, titulo, ylabel=None, fondo=FONDO_EJES):
    ax.set_facecolor(fondo)
    ax.set_title(titulo, color=TEXTO, fontsize=10)
    if ylabel:
        ax.set_ylabel(ylabel, color=TEXTO, fontsize=8)
    ax.tick_params(colors=TEXTO, labelsize=8)
    for lado in ax.spines.values():
        lado.set_color(_mezcla(fondo, '#ffffff', 0.25))
    ax.grid(axis='y', color=_mezcla(fondo, '#ffffff', 0.15), linewidth=0.5)
    ax.set_axisbelow(True)


def _barras(ax, nombres, valores, errores=None, titulo='', ylabel=None, log=False, fmt="{:.2f}",
            fondo=FONDO_EJES):
    """Barras por agente con el valor encima. Escala log solo si ayuda (todos > 0 y rango amplio)."""
    valores = np.nan_to_num(np.asarray(valores, dtype=float))
    _estilo(ax, titulo, ylabel, fondo)
    x = np.arange(len(nombres))
    ax.bar(x, valores, color=[PALETA[i % len(PALETA)] for i in range(len(nombres))],
           yerr=errores, ecolor='#bbbbbb', capsize=3)
    positivos = valores[valores > 0]
    if log and len(positivos) == len(valores) and valores.max() / valores.min() > 50:
        ax.set_yscale('log')
        positivos = valores[valores > 0]
    if log and len(positivos) == len(valores) and valores.max() / valores.min() > 50:
        ax.set_yscale('log')
    elif log and len(positivos) > 0 and valores.max() > 0.05:
        ax.set_yscale('symlog', linthresh=1e-3)

    for xi, v in zip(x, valores):
        ax.annotate(fmt.format(v), (xi, v), ha='center', va='bottom', color=TEXTO, fontsize=7,
                    xytext=(0, 2), textcoords='offset points')

    ax.set_xticks(x)
    ax.set_xticklabels(nombres, rotation=20, ha='right')


def dibujar_comparacion(fig, df: pd.DataFrame, minimo: int = None, fondo_ejes: str = None) -> None:
    """
    Dibuja 6 graficas comparativas en 'fig' (una matplotlib.figure.Figure):
    victorias, disparos (boxplot), eficiencia, tiempo por partida, evaluaciones y memoria.
    'minimo' (casillas de barco) dibuja el optimo teorico en la grafica de disparos.
    'fondo_ejes' (color '#rrggbb') es el fondo de cada grafica; la interfaz le pasa el color de sus botones.
    """
    fig.clear()
    fig.patch.set_facecolor(FONDO_FIGURA)
    fondo = fondo_ejes or FONDO_EJES
    if df.empty:
        return
    nombres = list(dict.fromkeys(df['nombre']))
    g = df.groupby('nombre', sort=False)
    media = lambda col: [g[col].mean()[n] for n in nombres]
    desv = lambda col: [g[col].std(ddof=0)[n] for n in nombres]
    ejes = fig.subplots(2, 3)

    _barras(ejes[0][0], nombres, [100 * v for v in media('ganado')], titulo='Victorias',
            ylabel='% de partidas ganadas', fmt="{:.0f}%", fondo=fondo)
    ejes[0][0].set_ylim(0, 115)

    ax = ejes[0][1]                                                   # boxplot de disparos
    _estilo(ax, 'Disparos por partida', 'disparos', fondo)
    cajas = ax.boxplot([df.loc[df['nombre'] == n, 'disparos'] for n in nombres], patch_artist=True,
                       medianprops={'color': '#ffffff'}, whiskerprops={'color': '#bbbbbb'},
                       capprops={'color': '#bbbbbb'}, flierprops={'markeredgecolor': '#bbbbbb'})
    for i, caja in enumerate(cajas['boxes']):
        caja.set_facecolor(PALETA[i % len(PALETA)])
    ax.set_xticks(range(1, len(nombres) + 1))
    ax.set_xticklabels(nombres, rotation=20, ha='right')
    if minimo:
        ax.axhline(minimo, color='#6ee68c', linestyle='--', linewidth=1)
        ax.annotate('óptimo teórico', (len(nombres) + 0.45, minimo), color='#6ee68c', fontsize=7,
                    ha='right', va='bottom')
    ax2 = ejes[1][1]
    _estilo(ax2, 'Nodos generados vs. expandidos', 'nodos por partida', fondo)
    x = np.arange(len(nombres))
    v_gen = np.nan_to_num(np.asarray(media('nodos_generados'), dtype=float))
    v_exp = np.nan_to_num(np.asarray(media('nodos_expandidos'), dtype=float))
    ax2.bar(x - 0.18, v_gen, 0.35, label='Generados', color='#4FC3F7')
    ax2.bar(x + 0.18, v_exp, 0.35, label='Expandidos', color='#FFB74D')
    if np.max(v_gen) > 50:
        ax2.set_yscale('symlog', linthresh=1)
    ax2.set_xticks(x)
    ax2.set_xticklabels(nombres, rotation=20, ha='right')
    ax2.legend(fontsize=7, facecolor=fondo, labelcolor=TEXTO)

    ax_rec = ejes[0][2]
    _estilo(ax_rec, 'Recompensa media acumulada', 'recompensa', fondo)
    for i, n in enumerate(nombres):
        serie = df.loc[df['nombre'] == n, 'recompensa'].to_numpy(dtype=float)
        iters = np.arange(1, len(serie) + 1)
        media_acum = np.cumsum(serie) / iters
        marcador = 'o' if len(serie) <= 15 else None
        ax_rec.plot(iters, media_acum, color=PALETA[i % len(PALETA)], linewidth=1.6,
                    marker=marcador, markersize=4, label=n)
    if minimo:
        ax_rec.axhline(-minimo, color='#6ee68c', linestyle='--', linewidth=1, label='óptimo')
    ax_rec.set_xlabel('partida (iteración)', color=TEXTO, fontsize=8)
    ax_rec.legend(fontsize=6.5, facecolor=fondo, labelcolor=TEXTO)

    _barras(ejes[1][0], nombres, media('tiempo_cpu_s'), errores=desv('tiempo_cpu_s'),
            titulo='Tiempo CPU por partida', ylabel='segundos CPU', log=True, fmt="{:.3f}", fondo=fondo)
    _barras(ejes[1][2], nombres, [g['memoria_max'].max()[n] for n in nombres],
            titulo='Memoria aproximada (máx.)', ylabel='elementos', log=True, fmt="{:.0f}", fondo=fondo)
    fig.tight_layout()
