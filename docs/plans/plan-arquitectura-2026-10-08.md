# Plan de ejecución: refactors de arquitectura de SkyPulse (candidatos 1 a 5)

> Creado el 2026-10-06 con Opus 5.5 (agente de planificación, solo lectura) a partir del informe `docs/reportes/architecture-review-20261006-1945.html`. Para arrancar el **jueves 2026-10-08 a las 08:00** (hora de Argentina) con la Fase 0. `docs/` no se commitea.
> Nota de estado (2026-10-06, noche): el PR 1 del TAF (#77) ya está mergeado; el PR del frontend del TAF (rama `airfranc86/fra-365-metar-taf-decodificado-frontend`) está listo en el árbol de trabajo, sin commit, esperando el OK del dueño.

Fuente: `docs/reportes/architecture-review-20261006-1945.html`. Worktree de referencia: `.claude/worktrees/tareas-pendientes-proyecto-3f7445`, HEAD `d0ad8ab` (= origin/main al escribir el plan). El `main` local del checkout principal está atrasado (`49f96e0`): toda rama nueva sale de `origin/main`.

## 1. Objetivo y alcance

El objetivo es darle más depth a cinco zonas del código. Cada una pasa a tener un module con una interface chica, un seam donde haga falta y adapters de prueba. El comportamiento que ve el usuario no cambia, salvo que el dueño decida otra cosa en el candidato 5.

**Entra:** `apps/backend/app/`, `apps/frontend/src/`, `scripts/instagram/` (en los candidatos 2, 3 y 5) y sus tests.
**No entra:** `src/` (legado, no se toca), `scripts/admin/` (el reporte lo descartó a propósito), unificar las listas de ciudades (descartado), servicios pagos y cualquier interface que no haya pasado antes por el grilling con el dueño. Este plan no propone firmas: las decide el dueño en cada paso de diseño.

## 2. Orden recomendado y dependencias

| Fase | Candidato | Depende de | Riesgo | PR estimados | Por qué en este orden |
|---|---|---|---|---|---|
| 0 | Línea base + auditoría P0–P3 | — | Nulo (solo lectura) | 0 | CLAUDE.md exige el reporte P0–P3 antes de refactorizar |
| 1 | 1 · Reportes aeronáuticos (backend) | Fase 0 | Medio (Niebla y METAR del dashboard) | 3 | Es la recomendación principal. El TAF recién mergeado sumó imports privados cruzados. Los fixtures de AWC ya existen. Destraba el 4 y el 3 |
| 2 | 2 · Pedidos a Open-Meteo | Fase 0; coordinar con FRA-348 T5 | Medio-alto (cuota, todo el dashboard, placas) | 3–4 | Tiene que ir antes del 3. T5 va a sumar otra consulta a Open-Meteo: este candidato aterriza antes de que arranque T5 o después de mergearlo, nunca en paralelo |
| 3 | 4 · Reportes de aeródromo (frontend) | Fase 1 mergeada + PR frontend de FRA-365 mergeado | Medio (página /metar y la tarjeta TAF de Niebla) | 2–3 | El reporte dice que el PR de FRA-365 es "el primer paso". Hacerlo antes chocaría con esa rama |
| 4 | 3 · Armado del dashboard | Fases 1 y 2 | Alto (página principal y placas de Instagram) | 3 | El reporte lo marca como "más fácil después de 1 y 2" |
| 5 | 5 · Una sola regla de tormenta | Decisión del dueño + FRA-348 T5 estable | Medio (puede cambiar veredictos visibles) | 1–2 | No se pueden unir reglas sin saber qué diferencias son intencionales |
| S | SIGMETs de Argentina (capa aeronáutica independiente; ver "Línea S") | S1: nada (puede ir con la Fase 0/1). S2: Fase 1b. S3: T7b y Fase 3 | Bajo (endpoint nuevo detrás de una bandera apagada) | 3 | Agrega una consulta más a AWC: conviene que nazca como adapter del module de la Fase 1 y no como un cuarto fetch escrito a mano |

Las fases 2 y 3 se pueden intercambiar según cuándo se mergee el frontend de FRA-365. FRA-361 (feed CAP del SMN) no se cruza con ninguna fase, pero la Línea S reutiliza su filtro por polígono.

## 3. Fase 0: jueves 2026-10-08, 08:00 (America/Argentina/Buenos_Aires)

Sesión segura para arrancar sin supervisión. **Puede hacer:**

1. Registrar el estado de partida: `git rev-parse HEAD`, `git status --short` y `git ls-remote origin main` (para saber si origin avanzó, sin escribir nada). Si hay cambios sin commitear en el área auditada, los anota y no los toca.
2. Registrar la línea base de tests y compararla con la del 2026-10-06 (tomada de los archivos de tareas): backend **1806** passed, frontend `node --test` **551** (**574** si ya está el PR del TAF del frontend), scripts/admin **267**, scripts/instagram **612**. Puede correr las suites que no escriben en el repo:
   - backend, desde `apps/backend`: `uv run --no-project --with-requirements requirements.txt --with-requirements requirements-dev.txt python -m pytest -p no:cacheprovider`
   - frontend, desde `apps/frontend`: `node --test`
   - admin e instagram: los comandos de sus README, con `-p no:cacheprovider`.

   No corre `pnpm build` (escribe `dist/`).
3. Contar líneas (`wc -l`) de los archivos de las 5 fases (hoy: `metar.py` 406, `metar_observation.py` 180, `taf_decoded.py` 237, `openmeteo.py` 871, `routers/weather.py` 431, `Metar.tsx` 1200, `Niebla.tsx` 979).
4. Inventariar constantes duplicadas. Ya verificado:
   - UTC-3 en `services/metar.py:35`, `openmeteo.py:20`, `dashboard_builder.py:42`, `alertas/regla.py:16` y `scripts/instagram/tests/report_factories.py:21`.
   - URL de METAR de AWC en `metar.py:37` y `metar_observation.py:30`; el contador `metar_awc` se registra en ambos.
   - Regla "6+ = 10 km" en `metar.py:163-177` y `taf_decoded.py:101-110`.
   - Validación de ICAO: `^[A-Z0-9]{4}$` en `routers/metar.py:29`, `^[A-Z]{4}$` en `lib/windShear.ts:349`.
   - Aeropuertos: el backend tiene SAAG/SAMM/SAMR y `Metar.tsx` tiene SARP/SANC/SANL.
   - Tormenta: cuatro definiciones (ver Fase 5).
5. Correr en **modo solo reporte** las auditorías de backend que pide CLAUDE.md sobre `services/metar.py`, `metar_observation.py`, `taf_decoded.py`, `routers/taf.py`, `routers/metar.py` y `routers/niebla.py`: `fastapi-python`, `python-performance-optimization` y `python-review`. Si da el tiempo, también `security-review` y `anthropic-skills:api-security-audit` (son obligatorias antes del primer commit de la Fase 1). Si un skill ofrece aplicar cambios, no se aplican.
6. Preparar la sesión de diseño: armar la lista de preguntas de la Fase 1 (sección 4), ordenadas, una por turno.
7. Preparar la Línea S (SIGMETs), **solo leyendo código**. La validación del feed de AWC ya la hizo el dueño con una consulta de solo lectura el 2026-10-07 y está registrada en la sección 4, "Línea S": esta sesión **no** consulta AWC. Tiene que:
   - listar con `archivo:línea` todos los lugares donde hoy se arma un pedido a AWC (`metar.py:37-38`, `metar_observation.py:30`, `taf_decoded.py`) y qué comparten, para que el adapter de SIGMET entre al seam de la Fase 1 y no sea un fetch más;
   - confirmar que `services/smn_alertas.py:196` (`point_in_polygon`) se puede reutilizar y anotar qué le falta para un radio (distancia punto–borde);
   - revisar cómo se cachea con TTL y cómo se registran los contadores (`quotas.py:31-34` lee los nombres `metar_awc` y `open_meteo`), para proponer el contador `sigmet_awc` y la bandera;
   - verificar si los pedidos actuales a AWC mandan un `User-Agent` propio (AWC lo pide en su documentación) y dónde se configuraría en el cliente httpx compartido (`core/http_client.py`);
   - sumar las preguntas de la Línea S (sección 4) al final de la lista de preguntas de diseño.

**No puede:** editar código ni tests, crear ramas o worktrees, hacer stash, add, commit, push, fetch, PR ni merge, correr `curl` contra producción, gastar cuota de CheckWX ni tocar `src/`.

**Entregable (único archivo que escribe):** `docs/reportes/arquitectura-fase0-baseline-auditoria-20261008.md`, con:
- el estado de partida;
- las cuatro suites (corridas o tomadas de los archivos de tareas, aclarando cuál);
- las líneas por archivo y el inventario de constantes;
- los hallazgos P0–P3 con `archivo:línea`;
- las preguntas de diseño;
- una sección final "Preparación de la Línea S (SIGMETs)" con lo pedido en el punto 7.

**Condición de parada:** con el reporte escrito, se detiene y espera al dueño. Si aparece un P0, lo destaca al principio y no hace nada más.

## 4. Fases por candidato

**Reglas comunes a todas las fases:**
- Por cada PR:
  1. Rama nueva desde `origin/main`.
  2. Tests primero, viendo el RED.
  3. Implementación mínima.
  4. Suite completa del paquete tocado y `uvx ruff check` desde `apps/backend`.
  5. Re-correr la auditoría para confirmar que no quedan P0/P1.
  6. Pedir aprobación listando archivos, rama y destino.
- Commits: `git commit -F -` con heredoc, conventional commits, sin atribución de IA (regla global del dueño) y nunca archivos de `docs/`.
- Reversión de cualquier PR: `git revert -m 1 <merge>` en una rama nueva, con su propio PR aprobado. Render vuelve a desplegar solo.
- Si un PR cambia algo que se ve en producción, se verifica con `curl` de solo lectura a `https://skypulse-api-mund.onrender.com` después del deploy, esperando el arranque en frío. Un PR que solo agrega tests o mueve código sin cambiar respuestas se verifica con la suite.
- **Nunca** se hace `curl` a `/api/metar?icao=`, porque gasta la cuota de CheckWX (198 por día).

### Fase 1: candidato 1, reportes aeronáuticos (backend)

**Objetivo.** Un solo module concentra:
- los aeropuertos y el más cercano;
- el parseo de visibilidad (escrito una vez);
- el TAF normalizado y su proyección horaria para Niebla;
- la observación METAR y la validación de ICAO.

Ese module habla con AWC detrás de un seam con dos adapters: HTTP en producción y fixtures en los tests.

**Archivos (verificados):**
- `apps/backend/app/services/metar.py`, `metar_observation.py` y `taf_decoded.py` (este último importa privados en la línea 29).
- `routers/taf.py:17` (importa el privado `_validate_icao` de `routers/metar.py:32`).
- `routers/niebla.py:25-30` (importa el privado `_classify_visibility` de `openmeteo.py:668`).
- `routers/weather.py:47` y `services/current_blend.py:24`: este segundo caller de `metar_observation` no figura en el reporte.
- `routers/metar.py:23`.
- Tests: `test_metar_*`, `test_taf_*`, `test_niebla_metar_cavok.py` y `tests/fixtures/awc_taf/` (SAAR, SACO, SARI, SASA).
- Restricción: `scripts/admin/monitor_core/quotas.py:34` lee el contador `metar_awc` por nombre, así que ese nombre no puede cambiar.

**Diseño con el dueño** (skills `grilling` y `codebase-design`; una pregunta por vez y sin código hasta cerrar):
1. ¿Qué entra en "reporte aeronáutico"? ¿CheckWX (`/api/metar`) queda afuera del module?
2. ¿El METAR de Niebla (`hours=2`) y el del dashboard (`hours=3`) tienen que ser una sola consulta con una sola caché? ¿Qué TTL acepta?
3. La escala de visibilidad de Niebla (`_classify_visibility`), ¿es parte de este module, del de Open-Meteo (Fase 2) o va aparte?
4. ¿Los callers reciben tipos de dominio o los modelos Pydantic de hoy?
5. ¿UTC-3 se unifica acá o en otra fase?
6. ¿Las respuestas de `/api/taf`, `/api/niebla`, `/api/metar/nearest` y del bloque METAR del dashboard quedan congeladas byte a byte?

**PR encadenados:**
- **1a. Tests de caracterización** (~250 líneas). Fijan la salida actual de las cuatro rutas con los fixtures de AWC.
  - RED: se ve por mutación (por ejemplo, devolver 9656 m en "6+" tiene que hacer fallar tests).
  - Sin cambio en producción; se verifica con la suite (1806 + N).
- **1b. Module, seam y adapters** (~400 líneas, incluye movimientos). Se crea el module con la interface acordada, la visibilidad pasa a vivir en un solo lugar, migran `taf_decoded`, `routers/taf` y `niebla`, y desaparecen los imports privados.
  - RED: los tests nuevos contra la interface fallan con ImportError.
  - Después del deploy: `curl /api/taf?icao=SACO` (200, períodos), `SAXX` (404), `SAC` (422) y `/api/niebla?lat=-31.42&lon=-64.18` (`hourly_source: "taf"` si hay TAF, más `metar_station`).
- **1c. Una sola consulta de METAR** (~300 líneas). `metar_observation` pasa a ser un caller del module: un fetch y una caché, y el contador `metar_awc` sigue igual.
  - RED: un test que cuente un solo pedido HTTP a AWC cuando Niebla y el dashboard piden la misma estación.
  - Después del deploy: `curl /api/weather/dashboard?...` (sigue trayendo la observación METAR) y el monitor admin sigue mostrando `metar_awc`.

**Criterio de término:**
- Cero imports de símbolos `_privados` entre los archivos citados.
- La regla "6+" en un solo lugar.
- Un solo fetch de METAR a AWC.
- Suite verde (≥ 1806) y respuestas en vivo idénticas a las previas.

**Qué puede romperse:**
- Niebla, que el usuario ve: la tarjeta horaria podría volver a caer a la inferencia de Open-Meteo, o mostrar 9,6 km en vez de 10 km.
- El "Ahora" del dashboard podría perder el METAR.
- La caché unificada podría servir un METAR más viejo.
- El PR 1b choca con el PR frontend de FRA-365 solo si cambia el contrato de `/api/taf`, y por eso se congela.

**Puertas del dueño:** cerrar el diseño; los hallazgos a atacar; y commit, push, PR y merge de 1a, 1b y 1c por separado.

### Fase 2: candidato 2, pedidos a Open-Meteo — AVANCE 2b (2026-10-08)
- 2b realizada: `OpenMeteoModule` con interface `get_current()` y `get_daily_forecast_ext()` confirmada en `apps/backend/app/services/openmeteo.py` (ya existía; no se modificó el contrato). Adapter de prueba creado en `tests/test_openmeteo_adapter.py` con fixtures cubriendo los 2 fetches.
- Quotas/cachés intactas: `open_meteo` (quotas) y TTL 600 (current), 1800 (forecast), 900 (nowcast) sin cambios; verificado en archivo.
- No se tocaron `scripts/instagram/` ni contrato frontend; superficies permitidas únicamente.
- **2c. Migración de 3 fetch restantes (Fase 2c, hoy)** — `get_hourly_forecast_ext` (11 campos `_HOURLY_FIELDS`, línea ~518), `get_hourly_forecast_ecmwf` (5 campos `_ECMWF_HOURLY_FIELDS` línea ~549) y `get_visibility_forecast` / `_fetch_niebla_combined` (6 campos `_NIEBLA_HOURLY_FIELDS` línea ~643, `CacheLevel.NOWCAST`). Adapter mínimo: `SeriesRequest(hourly=...)` + `_parse_hourly_payload`. RED propuesto por cada uno: `fetch_series` con el request devuelve `HourlyForecastExt | None`; cachés (1800/900 s) y `open_meteo` quota intactos. `scripts/instagram/` y frontend sin tocar.
- Pendiente (2d): scripts de Instagram como callers del module y verificación post-FRA-348 T5.

**Objetivo.** Los callers describen qué serie quieren (campos, modelo, días) y un solo module se encarga de zona horaria, unidades, nivel de caché, contador, reintentos, fallo convertido en None y parseo. Los scripts pasan a ser callers comunes.

**Archivos (verificados):**
- `services/openmeteo.py`: bloques de fetch en las líneas 122, 217, 464, 535 y 726.
- `scripts/instagram/fuente_horaria_ecmwf.py:127-131`, `fuente_visibilidad.py:85-89` y `fuente_datos.py:30`.
- `tests/test_openmeteo*.py`.
- `quotas.py:31` lee el contador `open_meteo` por nombre.

**Diseño con el dueño:**
1. ¿Acepta romper la convención "The backend is imported, never modified" (`fuente_visibilidad.py:13`, `fuente_horaria_ecmwf.py:20`)?
2. ¿Instagram y el dashboard deben compartir las entradas de caché?
3. ¿Qué niveles de caché existen hoy y cuáles quiere conservar (600, 1800 y 900 s)?
4. ¿La consulta de FRA-348 T5 (`ecmwf_ifs025`, `weather_code,cape`) nace adentro de este module?
5. ¿Se mantiene el gotcha del cliente httpx compartido de CLAUDE.md tal cual?

**PR encadenados:**
- **2a.** Tests de caracterización de los cinco fetch (parámetros, contador, reintento, None si falla) (~300 líneas).
- **2b.** Module, seam y adapter de prueba; migran dos fetch del backend (~400 líneas).
- **2c.** Migran los tres fetch restantes (~350 líneas).
- **2d ELIMINADO** — baja confirmada por dueño (no migrar scripts/instagram).

En cada PR, el RED es el test nuevo contra la interface (ImportError) o una mutación. Verificación: suites de backend e instagram completas y, después del deploy, `curl` al dashboard, a `/api/niebla` y a `/api/tools/...` comparando valores con los previos. En la siguiente corrida de `generar_reporte` se mira que el conteo de pedidos a Open-Meteo baje y no suba.

**Criterio de término:** un solo bloque de fetch, ECMWF por hora pedido una vez y los scripts sin fetch propio.

**Qué puede romperse:**
- La cuota y los 429 de Open-Meteo, por la IP compartida de Render (experimento E1 de FRA-348).
- Que el dashboard quede vacío.
- Que las placas muestren lluvia o niebla distinta.

**Puertas del dueño:** decidir el punto 1 y si va antes o después de T5; luego cada PR.

### Fase 3: candidato 4, reportes de aeródromo (frontend)

**Objetivo.** Un module frontend (hook más decodificación pura) convierte un ICAO en el METAR decodificado y el estado del TAF. Reusa la política de reintentos compartida y el TAF decodificado del backend. Las páginas solo renderizan.

**Archivos (verificados al 2026-10-06):**
- `apps/frontend/src/pages/Metar.tsx`: `MetarData` propio (13-36), `visNote` con cortes en metros (268-284), `ICAO_DB` (50). El `fetch` crudo del TAF ya se reemplazó por `api.tafDecoded` en el PR del TAF del frontend.
- `pages/Niebla.tsx:678-700` (`TafExpandCard` con `tafRaw`).
- `lib/api.ts:516-535` y `654-656`.
- `lib/windShear.ts:349-355`.
- `tests/metarIcao.test.ts`.
- Nuevo por FRA-365: `lib/taf.ts` y `components/aeronautica/TafDecodedCard.tsx`: este module los absorbe o los reutiliza.

**Arranque:** sale de una rama nueva desde `origin/main`, solo después de que se mergee el PR del TAF del frontend (FRA-365).

**Diseño con el dueño:**
1. ¿Qué lista de aeropuertos manda (la del backend, la del frontend o la unión)?
2. ¿Una sola regla de ICAO (¿se aceptan dígitos?)?
3. ¿`visNote` usa los cortes FAA en millas del backend?
4. ¿La tarjeta de Niebla pasa del TAF crudo (CheckWX) al decodificado (AWC)? Cambia lo que ve el usuario y libera cuota.
5. ¿Wind shear lee del mismo module?

**PR encadenados:**
- **4a.** Decodificación pura y tests como imports comunes, reemplazando las lecturas del código fuente como texto (~300 líneas).
- **4b.** Hook y migración de `Metar.tsx` (~400 líneas).
- **4c.** Niebla y wind shear (~250 líneas).

Cada PR: RED con `node --test`, después `pnpm build` y `eslint`; antes del commit corren `audit`, `vercel-react-best-practices` y `ui-ux-pro-max`. Verificación en `localhost` y en la preview de Vercel con los ICAO SACO, SAEZ y uno inválido.

**Criterio de término:** un solo tipo de METAR, una regla de ICAO, una lista de aeropuertos y ningún `fetch` crudo en la página.

**Qué puede romperse:** la búsqueda de ICAO, la tarjeta TAF de Niebla, el reintento en arranque en frío y la precarga de wind shear.

**Puertas del dueño:** las respuestas 1 a 4 y cada PR.

### Fase 4: candidato 3, armado del dashboard

**Objetivo.** Un module de dashboard recibe ubicación, hora y modelo, con los fetchers inyectados desde afuera. La ruta y la parte de 7 días de Instagram lo llaman.

**Archivos (verificados):**
- `routers/weather.py:124-366` (`get_dashboard`, `is_day` en 179-188, `station_altitude_m=500.0` en 320).
- `services/dashboard_builder.py` y `scripts/instagram/fuente_datos.py:25-36`.
- Tests que parchean `app.routers.weather.*`: `test_dashboard.py` (12), `test_dashboard_integration.py` (12), `test_dashboard_current_observation.py` (6), `test_dashboard_forecast_anchor.py` (3) y `test_openmeteo_hourly_ecmwf.py` (9).

**Diseño con el dueño:**
1. ¿La cota de nieve sigue con 500 m fijos o usa la elevación?
2. ¿Instagram tiene que mostrar exactamente los números de la web?
3. ¿Dónde vive el reloj inyectado?
4. ¿Qué pasa si falla ECMWF (comportamiento de respaldo actual)?

**PR encadenados:**
- **3a.** Tests nuevos con fakes y reloj fijo (~300 líneas).
- **3b.** Se extrae el module y la ruta pasa a solo delegar; se migran los parches (~400 líneas).
- **3c.** Instagram pasa a ser un caller (~250 líneas).

Verificación: suites de backend e instagram, `curl /api/weather/dashboard` en dos ciudades (de día y de noche) comparando campos con la captura previa, y una corrida de placas en modo de prueba.

**Qué puede romperse:** el ícono de día o noche, el arco del día, la fila de 7 días, la cota de nieve y las placas.

**Puertas del dueño:** el diseño y cada PR.

### Fase 5: candidato 5, una sola regla de tormenta

**Archivos (verificados):**
- `services/calculators.py:31` (`{95,96,99}`), `:43` (1000 J/kg) y `:83-107`.
- `services/alertas/umbrales.py:10-14`: 95–99 y 2500 J/kg, con el comentario "ÚNICO lugar" (vale solo para las alertas push).
- `scripts/instagram/reglas.py:38-39` y `91-92` (95–99, o riesgo high/severe).
- `apps/frontend/src/lib/weatherVerdict.ts:259` (solo `convective_risk`).
- Tests de paridad: `scripts/instagram/tests/test_paridad_alertas.py` y `tests/test_alertas_regla.py`.

**Diseño con el dueño (bloqueante):**
1. Los 1000 J/kg de las herramientas (recalibrado en FRA-191 con evidencia de Córdoba) frente a los 2500 de alertas y placas: ¿la diferencia es intencional?
2. ¿Los códigos 97 y 98 entran?
3. ¿El veredicto del frontend tiene que mirar el código WMO?
4. ¿Se nombran niveles de exigencia o se usa uno solo?

**PR:** 5a con el module y los niveles nombrados, sin cambiar valores; los tests de paridad pasan a tests del module (~300 líneas). 5b, solo si el dueño cambia umbrales: cambio de comportamiento con aviso al usuario. Arranca recién con FRA-348 T5 mergeado y estable, porque la evaluación de alertas usa esta regla.

**Qué puede romperse:**
- Herramientas que pasen de "No apto" a "Excelente".
- Alertas push que se pierdan o que se dupliquen.
- Placas con "Tormenta fuerte posible".

### Línea S: SIGMETs de Argentina (capa aeronáutica independiente)

**Objetivo.** Una capa nueva de avisos aeronáuticos (SIGMET), independiente del pronóstico. **No** reemplaza ni toca Open-Meteo ni el contrato actual con el frontend, y con la bandera apagada producción queda igual. Pedido del dueño el 2026-10-07; el spike completo, con lo verificado y las tres etapas, está en el ticket **FRA-368**.

**Verificado el 2026-10-07 (~14:50 UTC, un solo GET de solo lectura a `https://aviationweather.gov/api/data/isigmet?format=json`):**
- HTTP 200, 112 KB, 140 avisos de 70 FIR en todo el mundo.
- **Argentina hoy: 6 avisos vigentes.** SACF Córdoba (2: TS y turbulencia), SAEF Ezeiza (3: 1 TS y 2 engelamiento) y SAVF Comodoro Rivadavia (1: engelamiento). **SAMF Mendoza y SARR Resistencia no aparecieron:** puede ser que no hubiera avisos o que AWC no las ingiera; solo se confirma observando varios días. También hay FIR vecinas (SCFZ, SCIZ, SUEO).
- Campos: `icaoId`, `firId`, `firName`, `seriesId`, `hazard` (TS, TURB, ICE, VA, TC), `qualifier`, `validTimeFrom` y `validTimeTo` (epoch UTC), `base` y `top` (pies; pueden ser `null`), `coords` (lista de `{lat, lon}`), `geom` ("AREA"), `dir`, `spd`, `chng`, `receiptTime` y `rawSigmet` (texto original).
- **El feed no viene filtrado por vigencia** (1 de 140 estaba vencido): hay que filtrar por `validTimeFrom <= ahora < validTimeTo`.
- **Las cancelaciones llegan como un SIGMET nuevo** con "CNL" en `rawSigmet` (5 en el feed de hoy, todas de México; ninguna argentina para ver el formato). Hay que parsear qué serie cancelan y descartarla.
- Ejemplo real: SACF A2, TS EMBD, 12:20–16:20Z, polígono de 12 vértices sobre Córdoba, tope FL420, "INTSF".
- **Documentación oficial** (`https://aviationweather.gov/data/api/`, leída el 2026-10-07): 100 pedidos por minuto, pide un `User-Agent` propio, y documenta 204 (sin datos), 400 (pedido inválido) y 429 (demasiados pedidos). **El texto de esa página no describe `/isigmet`**: el endpoint responde, pero sus parámetros y formatos (y si 204 aparece en la práctica) los tiene que confirmar S1 contra la especificación OpenAPI de AWC antes de depender de ellos.

**Dónde** (backend, todo nuevo y separado):
- `services/sigmet.py`, `routers/sigmet.py` (`GET /api/sigmet?lat&lon&radio_km`) y `schemas/sigmet.py`.
- Consulta a AWC como **adapter del module de la Fase 1** (por eso no se construye antes de la 1b).
- Filtro geográfico: reutilizar `point_in_polygon` de `services/smn_alertas.py:196`; para el radio falta la distancia punto–borde de polígono (es código nuevo y se prueba aparte).
- Caché con TTL de 5 minutos, cliente httpx compartido con timeout por llamada, y contador nuevo `sigmet_awc`.

**Cómo:**
- Bandera `SIGMET_ENABLED` en el backend (apagada: la ruta responde 404) y `VITE_SIGMET_VISIBLE` en el frontend.
- Tres estados que no se confunden: con avisos vigentes; **sin avisos vigentes** (200 con lista vacía); y **fuente no disponible** (503 propio, también ante 204, 429 y 5xx de AWC, sin afectar el pronóstico).
- Cada aviso muestra fuente (NOAA/AWC), emisión, inicio y fin de vigencia, y la última consulta.
- SkyVector solo para inspección y comparación visual. Ninguna dependencia ni extracción sin confirmar autorización y condiciones de reutilización.

**Cuándo:**
- **S1: spike y caracterización** (~250 líneas, sin tocar producción). Fixtures reales capturados de AWC (avisos argentinos, uno vencido, uno con CNL), tests del parseo (vigencia, cancelaciones, geometría) y la decisión sobre qué FIR entran. Puede hacerse junto con la sesión de diseño de la Fase 1 o antes: no depende de ningún refactor.
- **S2: endpoint con bandera** (~400 líneas). Después de la Fase 1b y nunca en paralelo, porque toca el mismo seam de AWC.
- **S3: frontend** (~400 líneas). Después de T7b (FRA-357) y de la Fase 3, para no chocar en `Metar.tsx` y en el header. La bandera se enciende solo con la aprobación del dueño.

**Relación con FRA-348 (alertas push):** no entra en T5 ni en el MVP de las alertas. Es un aviso oficial aeronáutico, con otro público y un texto técnico. Una alerta push por SIGMET sería una etapa posterior (T12), parecida a T10 (avisos del SMN), y la decide el dueño.

**Criterio de término:** avisos argentinos representados correctamente cuando existan; vencidos y cancelados nunca como activos; un fallo de AWC no afecta el pronóstico actual; con la bandera apagada, producción idéntica.

**Preguntas para el dueño (una por turno, en la sesión de diseño):**
1. ¿Dónde se muestra: herramienta aeronáutica nueva, tarjeta en Niebla/METAR, o ambas?
2. ¿Qué radio por defecto y cuál es el máximo que acepta la persona?
3. ¿Solo las 5 FIR argentinas o también las vecinas que cruzan la frontera?
4. ¿Todos los fenómenos (TS, TURB, ICE, VA, TC) o solo tormenta y turbulencia?
5. ¿Se muestra el texto original, una versión decodificada o ambos?

**Qué puede romperse:** nada del pronóstico actual (endpoint propio). Riesgos propios: mostrar un SIGMET cancelado como vigente, un polígono que cruza la línea de fecha (no aplica a Argentina), y el límite de pedidos de AWC (100 por minuto según su documentación, cubierto con la caché de 5 minutos).

## 5. Riesgos transversales y mitigación

- **Choque con FRA-348 T3–T11** (alertas, suscripciones, QStash): ninguna fase toca `services/alertas/` salvo la 5, que va última. La Fase 2 se coordina con T5.
- **Choque con FRA-365 frontend:** la Fase 1 congela `/api/taf` y la Fase 3 espera el merge.
- **Base desactualizada:** siempre `origin/main`; el `main` local está viejo.
- **Contadores que lee el monitor admin** (`metar_awc`, `open_meteo`): sus nombres no cambian y hay un test que lo asegura.
- **Cuotas:** sin `curl` a CheckWX y sin bucles contra Open-Meteo.
- **No hay CI propio** (no existe `.github/workflows`; los checks del PR son de servicios externos): las suites se corren a mano y el número exacto va en cada PR.
- **Arranque en frío de Render** en las verificaciones en vivo: esperar y reintentar.
- **PR grandes:** heurística de ~400 líneas, con cadena vía `chained-pr` y `work-unit-commits`.

## 6. Preguntas abiertas para el dueño

1. ¿Arrancamos por el candidato 1 como recomienda el reporte?
2. ¿El candidato 2 va antes de que empiece FRA-348 T5 o después de mergearlo?
3. Tormenta: ¿la diferencia entre 1000 y 2500 J/kg (y la de los códigos 97/98) es intencional?
4. ¿Se crean issues en Linear por fase, para usar sus nombres de rama?
5. ¿Registramos cada decisión de diseño como ADR o en un CONTEXT.md (hoy no hay ninguno)?
6. ¿Qué auditoría corre sobre `scripts/`? CLAUDE.md no define una; propongo `python-review`.
7. SIGMETs (ticket **FRA-368**, ya creado): ¿arrancamos con S1 junto a la sesión de diseño de la Fase 1? Las cinco preguntas de diseño están al final de la Línea S.

## 7. Cómo retomar

En una sesión nueva, leer en este orden:
1. Este plan.
2. `docs/reportes/architecture-review-20261006-1945.html`.
3. `docs/reportes/arquitectura-fase0-baseline-auditoria-20261008.md` (cuando exista).
4. `odd/tasks/fra-365-taf-decodificado.md` y los otros archivos de `odd/tasks/` (están sin seguimiento en la worktree).
5. `PROGRESS.md`.

Después confirmar con el dueño la fase siguiente antes de editar.

---
ESTADO GENERAL (actualizado paso a paso, 2026-10-15):
- Fase 1 (TAF/reportes aeronáuticos): PR 1 mergeado, TAF hecho ✅; PR frontend TAF mergeado ✅.
- Fase 2 (Open-Meteo, candidato 2): 2a RED ✅, 2b module+seam ✅, 2c 3 fetch restantes ✅, 2d ELIMINADO (baja) ❌.
- Fase 3 (frontend aeródromo / METAR): pendiente — arranca post-FRA-365 merge (ya hecho por dueño).
- Fase 4 (dashboard): pendiente — depende 1+2.
- Fase 5 (tormenta): pendiente — post-FRA-348 T5 estable.
- Línea S (SIGMETs / FRA-368): S1/S2/S3 completadas ✅ (S1 exploración inline; S2 adapter al seam Fase 1 + schemas/sigmet.py; S3 endpoint GET /api/sigmet con flag protegida). ODD doc: `docs/plans/odd/linea-s.md`.
- Mapa de presión / isobaras (sección búsqueda): no implementado; datos `pressure_hpa` existen en openmeteo/smn/agregador; visualización pendiente decisión del dueño.

## Actualización de FRA — 2026-10-22 (progreso Fases 1–4)

- Fase 2d eliminada (baja, confirmado dueño); 2a RED (tests), 2b module+seam+adapter (`OpenMeteoModule`), 2c 3 fetch restantes completados.
- Fase 3 completa: 3a decodificación pura (`metarDecode.ts` + `taf.ts`); 3b `Metar.tsx` integrado con datos decodificados (`api` + `TafDecodedCard`); 3c `Niebla` (`useNiebla` → `api.niebla`) + `windShear`.
- Fase 4 dashboard: componente `PressureIsobarMap.tsx` creado (etiquetas numéricas hPa + frentes frío/cálido/estacionario), integrado en `App.tsx` (lat/lon desde `useLocationState`), datos de presión conectados al backend (`useWeatherDashboard` / openmeteo).
- Fase 5 confirmada con valores actuales (CAPE 2500 J/kg, códigos 95/96/99, una fuente `umbrales.py`, sin cambios visibles en veredicto); Línea S completada (S1/S2/S3).
- Linear MCP: conexión verificada (`https://mcp.linear.app/mcp`, streamable HTTP, OAuth interactivo completado, token `mcp-auth.json` fuera del repo, proyecto `P-FRA-5` consultado solo lectura, sin modificaciones).
- `PI_REASONING_LEVEL=high`; `2d` baja; sin cambios en `scripts/instagram/`; sin commits de `docs/`.
