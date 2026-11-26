# Lista de Pendientes del Proyecto — Batalla Naval

Documento de control basado en la auditoría del código actual frente a **Lineamientos - Proyecto Final.pdf** (*Representación y solución automática de problemas — Universidad del Rosario*).

---

## Estado Actual (Ya implementado)
- [x] **Entorno base y niveles (`ambientes.py`, `dificultad.py`)**: Tableros configurables, 4 niveles (`Fácil`, `Medio`, `Difícil`, `Experto`), límite de disparos, ocultamiento de flota restante, restricción de adyacencia, sesgo a bordes y ruido de sonar.
- [x] **Interfaz base (`app_qt.py`, `render_pygame.py`, `partida.py`, `sesion_agente.py`)**: Pestañas *"Jugar"* y *"Ver agente"*, animaciones con sprites, controles de reproducción (*Reproducir/Pausa*, *Paso adelante*, *Atrás*, *Terminar*, *Velocidad*), numeración de jugadas y capa de mapa de calor sobre el tablero.
- [x] **Agentes actuales (`agents.py`, `mcts_agent.py`, `dqn_agent.py`, `entrenar_dqn.py`)**: `RandomAgent`, `AgenteCazaRemate`, `AgenteMCTS` y `AgenteDQN` (con entrenamiento Double DQN).
- [x] **Evaluación por consola (`evaluar.py`)**: Comparación con semillas compartidas midiendo porcentaje de victorias, media/desviación de disparos, eficiencia y ms/jugada.

---

## 1. Visualización del Proceso de Búsqueda de los Algoritmos *(Requisito Sección 2.2 — 10 pts)*

Los lineamientos exigen: *"Animación del proceso de búsqueda: nodos expandidos, frontera, nodos visitados o reglas activadas, diferenciados visualmente"* y *"Visualización del estado interno del algoritmo en pantalla"*.

- [x] **Visualización parcial de la expansión del árbol en MCTS (`mcts_agent.py` + `app_qt.py`)**:
  - Actualmente MCTS solo proyecta el mapa de calor de valores $Q$ en la raíz, pero no muestra la estructura del árbol explorado.
  - **En `mcts_agent.py` (`estado_interno`)**: Exportar un resumen compacto del subárbol de la jugada actual (no el árbol completo para mantener legibilidad), incluyendo:
    - El **nodo raíz** ($N$ total de simulaciones).
    - Las **Top $K$ acciones más visitadas** desde la raíz (p. ej. Top 4 o Top 5 casillas candidatas, incluyendo siempre la acción elegida) con sus estadísticas $(N(a), Q(a))$.
    - Sus ramas hijas de observación (`agua`, `impacto`, `hundido`) y las principales respuestas del segundo nivel.
    - Etiqueta del tipo de nodo para diferenciarlos por color: **raíz**, **rama seleccionada**, **nodos internos expandidos** ($N > 1$) y **nodos frontera / hojas recién creadas** ($N = 1$).
  - **En `app_qt.py` (`PestanaAgente`)**: Añadir un panel o subvista gráfica que dibuje dinámicamente este subárbol en cada jugada (actualizándose también al avanzar paso a paso o retroceder con `|◀ Atrás`).
- [x] **Diferenciación visual de reglas activadas en Caza-Remate (`agents.py` + `app_qt.py`)**:
  - Mostrar explícitamente qué regla se disparó en el turno actual (*Regla de caza por paridad de ajedrez*, *Regla de remate ortogonal simple* o *Regla de remate colineal por impactos alineados*) diferenciando en color las casillas candidatas de cada regla.
- [x] **Detalle visual en DQN (`dqn_agent.py` + `app_qt.py`)**:
  - Mantener el mapa de calor de valores $Q(s, a)$ e indicar claramente en el panel interno la acción $\arg\max Q$, el rango $[Q_{\min}, Q_{\max}]$ y cuántas casillas fueron enmascaradas ($Q = -\infty$).

---

## 2. Interfaz Gráfica e Interactividad *(Requisito Sección 2.2 — 10 pts)*

- [x] **Generador y Editor de Instancias en la GUI (`app_qt.py` + `ambientes.py` + `instancia.py` + `editor_instancia.py`)**:
  - Nueva pestaña **"Editor de instancias"**:
    - **Configurador de parámetros**: filas × columnas, composición de la flota (añadir, quitar, cambiar longitud, restaurar la clásica), límite de disparos (o sin límite), ruido del sonar, sesgo de colocación aleatoria, barcos adyacentes y mostrar/ocultar la flota restante. Los parámetros incoherentes (p. ej. límite menor que las casillas de barco) se rechazan con un aviso.
    - **Editor manual del estado inicial**: clic = colocar, clic sobre un barco = moverlo, clic derecho = quitarlo, `R` o rueda = girar H/V; vista previa verde/roja según la validez (solapes y contacto según la regla de adyacencia). Botones *Colocar al azar* y *Limpiar tablero*.
    - **Persistencia**: guardar/cargar la instancia en JSON.
  - `BatallaNavalEnv` acepta `disposicion=[(nombre, fila, col, 'H'|'V'), ...]`; con ella `reset()` conserva la flota en lugar de generar una aleatoria.
  - La instancia del editor aparece como opción **"Personalizada"** en los selectores de nivel de *Jugar*, *Ver agente* y *Comparar* (botones *Jugar / Ver agentes / Comparar en esta instancia*).
- [x] **Ventana o Pestaña de Comparación de Algoritmos (`app_qt.py` + `comparar.py`)**:
  - Nueva pestaña **"Comparar"**: elige nivel o instancia personalizada, agentes, partidas por agente y semilla base (la partida *i* usa la semilla *base + i* para todos los agentes; con 1 partida se comparan sobre una única instancia). Se ejecuta en un hilo aparte, con barra de progreso y botón *Cancelar*. Un agente que no puede jugar (p. ej. DQN sin modelo) se reporta sin tumbar a los demás.
  - **Tabla comparativa** (resalta el mejor valor de cada métrica) con victorias, disparos (media/desv./mín./máx.), eficiencia, óptimas, brecha al óptimo, recompensa acumulada, tiempo por jugada y por partida, evaluaciones y memoria.
  - **Gráficas**: victorias, boxplot de disparos (con el óptimo teórico), eficiencia, tiempo por partida, evaluaciones y memoria. Exportación de todas las partidas a CSV.
  - *Pendiente (ver punto 3)*: separar "nodos generados" de "nodos expandidos"; hoy se muestra `evaluaciones` como equivalente a nodos generados.
- [x] **Comparación Humano vs. Máquina desde la pestaña "Jugar" *(Opcional recomendado)***:
  - El panel de *Jugar* muestra la **semilla** (y si la flota es manual o al azar). Al terminar la partida se habilita **"Comparar con los agentes"**: todos los agentes juegan exactamente esa flota y se muestra una tabla (resultado, disparos, eficiencia, brecha, ms/jugada) y tu puesto.
- [x] **Limitación conocida**: el agente DQN solo existe para los niveles entrenados (`models/dqn_<nivel>.pt`); con una instancia personalizada se informa de que no hay modelo y los demás agentes funcionan con normalidad.

## 3. Métricas Experimentales y Heurísticas *(Requisito Sección 2.2 — 15 pts)*

- [ ] **Completar todas las métricas obligatorias en `evaluar.py` y en la GUI**:
  Actualmente `evaluar.py` reporta victorias, disparos, eficiencia y ms/jugada, pero faltan métricas exigidas textualmente en los lineamientos:
  - **Tiempo total de ejecución** por partida (además del tiempo medio por jugada).
  - **Nodos generados y nodos expandidos** (recolectar las evaluaciones/nodos desde `agente.estado_interno()`, separando nodos generados vs. expandidos en búsqueda con árbol).
  - **Memoria aproximada** (registrar el pico máximo de `estado_interno()['memoria']` por partida).
  - **Longitud y costo de la solución** (explicitar longitud = disparos realizados y costo/recompensa acumulada $= -\text{disparos}$).
  - **Optimalidad y éxito/fallo** (indicar explícitamente si encontró la solución o falló por límite de disparos, si alcanzó el óptimo teórico `disparos == casillas_barco` y la brecha respecto al óptimo `disparos - casillas_barco`).
- [ ] **Comparación de al menos dos heurísticas diferentes**:
  - Los lineamientos recomiendan: *"Para algoritmos con heurística, se recomienda incluir al menos dos heurísticas diferentes y comparar su efecto"*.
  - Parametrizar al menos dos variantes heurísticas comparables (por ejemplo, en MCTS: búsqueda con heurística de paridad + remate colineal vs. búsqueda sin poda de paridad / *rollout* uniforme).
- [ ] **Modelos entrenados de DQN para todos los niveles (`models/`)**:
  - Verificar que estén entrenados y guardados en el repositorio los pesos para los 4 niveles (`dqn_facil.pt`, `dqn_medio.pt`, `dqn_dificil.pt`, `dqn_experto.pt`), evitando errores de `FileNotFoundError` al cambiar de nivel en la GUI o en `evaluar.py`.

---

## 4. Aspectos Técnicos y Entregables Finales *(Secciones 2.3 y 3 — 40 pts entre Informe y Sustentación)*

- [ ] **Actualizar `requirements.txt`**:
  - Agregar las librerías faltantes que hoy usa el proyecto: `pygame-ce`, `PySide6`, `torch` y `jupyter`.
- [ ] **Depurar o actualizar scripts antiguos rotos (`main.py`, `test_ambiente.py`)**:
  - Tras los cambios recientes en `ambientes.py` (donde se retiraron `render()` y `pintar_todo()`) y en `utils.py` (donde se retiró `texto_a_coord`), `main.py` y `test_ambiente.py` fallan al ejecutarse. Deben actualizarse o retirarse antes de la entrega final.
- [ ] **Crear el Notebook de Python obligatorio (`.ipynb`)**:
  - Requisito de la Sección 2.3: *"Notebook de python donde se realice la creación de una instancia del entorno, se muestre sus principales métodos y atributos, y ejemplifique la aplicación de los algoritmos utilizados"*.
- [ ] **Completar `README.md`**:
  - Incluir descripción del proyecto, estructura de archivos, instrucciones paso a paso de instalación y ejecución, y **capturas de pantalla** de la interfaz y las comparaciones.
- [ ] **Verificar estilo y documentación PEP 8** en todos los módulos `.py`.
- [ ] **Informe Técnico (formato artículo corto, 1–4 páginas, 11 pt, márgenes 2,5 cm — 100% autoría propia)**:
  1. Formalización del entorno $(S, A, R, T, \text{Objetivo})$ y caracterización (parcialmente observable, discreto, finito, etc.).
  2. Tipo de agente y justificación.
  3. Algoritmos implementados con complejidad teórica en tiempo/espacio, completitud y optimalidad.
  4. Diseño experimental, tablas/gráficas reproducibles y análisis comparativo.
  5. Conclusiones, limitaciones y mejoras futuras.
  6. **Declaración explícita del uso de IA** (detallando en qué partes de la interfaz o formato se usó, respetando la autoría propia del entorno, algoritmos y documento).
- [ ] **Repositorio Git y Sustentación (10 a 15 minutos)**:
  - Confirmar que **todos los integrantes** tengan commits registrados en el historial de Git y preparar la defensa individual del código y la teoría.
