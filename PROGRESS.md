# Progress Log — Latest at top

---

## 2026-09-02 — 3 de los 4 P2 restantes de la auditoría de backend (LatParam/LonParam, imports privados, asimetría tender-ropa)

**Done — P2 #2: `LatParam`/`LonParam` unificados:**
- `earthquakes.py`, `incendios.py`, `niebla.py` ya no redefinen sus propias copias — importan `LatParam`/`LonParam` desde `app.core.params` (mismo patrón que ya usaban `tools.py`/`weather.py`).
- `niebla.py` pasó de `ge=-76` a `ge=-74` para `lon` — quedaba 2° más permisivo que el resto de la API. Confirmado con grep que ningún test dependía del límite viejo (-76), y que `services/emsc.py`/`services/usgs.py` usan `-76` para su propio bbox de *fetch* interno (a propósito, con comentario explícito) — eso es independiente de qué coordenadas de *usuario* acepta el router y no se tocó.
- Imports `Annotated`/`Query` que quedaron sin uso en los 3 routers, eliminados.

**Done — P2 #4: imports privados de `fire_danger.py` a `windy.py`:**
- Promovidos a públicos en `windy.py`: `_fetch_raw`→`fetch_raw`, `_safe_get`→`safe_get`, `_k_to_c`→`k_to_c`, `_AR_TZ`→`AR_TZ` (los 4 símbolos que el audit señaló como API interna compartida cruzando el límite de módulo).
- `fire_danger.py` actualizado (import + todos los call-sites). Cuidado real: `_fetch_raw_fire` es un helper propio de `fire_danger.py` (no viene de windy) — no se tocó, verificado que no colisiona con el rename de `_fetch_raw`.
- `test_windy_concurrent.py` (importa y llama `_fetch_raw` directo, ~9 sites) y `test_fire_danger.py` (2 `patch("...fire_danger._fetch_raw")`) actualizados a los nombres públicos.

**Done — P2 #5: asimetría de fuentes en tender-ropa:**
- `get_tender_ropa` ahora intenta Windy primero (`_windy_hourly_or_none`), igual que `get_hacer_deporte`/`get_lavar_coche` — antes solo llamaba a Open-Meteo directo, así que el score de "hoy" podía diferir del primer día de `/tender-ropa/forecast` (que sí intentaba Windy).
- Detalle no trivial verificado antes de escribir código: `score_tender_ropa(temp_c, humidity, wind_speed_kmh, precip_mm, ...)` ya tiene el mismo orden posicional que espera `_build_hourly_scores_from_windy` — a diferencia de `score_hacer_deporte` (que tiene `precip`/`wind_speed_kmh` invertidos y por eso necesita el closure `_score_fn`), acá se pasa `calculators.score_tender_ropa` directo, sin wrapper.
- Precipitación "próximas 6h": con Open-Meteo son 6 slots horarios; con Windy (slots de 3h) son los 2 primeros slots — mismo criterio "próximas 6h" en ambas fuentes, no un número inventado.
- Ambas ramas (Windy y Open-Meteo) ahora devuelven `source=` (antes la rama Open-Meteo no lo seteaba y quedaba en el default `"unknown"` del schema — sin tests que dependieran de eso).

**Files changed:**
- `apps/backend/app/routers/earthquakes.py`
- `apps/backend/app/routers/incendios.py`
- `apps/backend/app/routers/niebla.py`
- `apps/backend/app/services/windy.py`
- `apps/backend/app/services/fire_danger.py`
- `apps/backend/app/routers/tools.py`
- `apps/backend/tests/test_windy_concurrent.py`
- `apps/backend/tests/test_fire_danger.py`
- `apps/backend/tests/test_tools_router.py` — 3 tests nuevos (`TestTenderRopaWindyPath`)

**Tests:**
- `.venv/Scripts/python.exe -m pytest -q` → **762 passed**, 0 failed (759 + 3 nuevos).
- Hallazgo de proceso durante la primera corrida: los 3 tests nuevos daban 429 porque `TestRateLimiting` (35 requests a `/tender-ropa` para forzar el límite) corre antes en el archivo y el rate-limiter no se resetea entre tests — mismo bucket de IP+endpoint agotado para el resto de la sesión. No es un bug de la limpieza en sí; se resolvió reubicando `TestTenderRopaWindyPath` junto a `TestTenderRopa` (antes de `TestRateLimiting`), con un comentario explicando por qué el orden importa acá.

**Next:**
1. Pendiente de decisión del usuario: commitear y pushear.
2. Queda el último P2: `routers/weather.py` (877 líneas) mezclando routing con lógica de agregación pesada — extraer a `services/dashboard_builder.py`. Es el más grande de los 4, se ataca en esta misma sesión a continuación.

---

## 2026-09-02 — Último P2 de la auditoría: split de `routers/weather.py` (877 → 406 líneas)

**Done:**
- Nuevo `services/dashboard_builder.py` (495 líneas): los 5 helpers pesados que el audit señaló como lógica de negocio disfrazada de routing — `_compute_sun_times`, `_build_synthetic_daily_multi`, `_build_rain_forecast`, `_build_hourly_schema`, `_build_7d_forecast` (más `_wmo_from_windy_daily`, `_rain_label` y la constante `_MONTHS_ES`, dependencias directas de esos 5 que no tenía sentido dejar atrás).
- Las 4 funciones que `routers/weather.py` necesita llamar desde afuera (`build_synthetic_daily_multi`, `build_rain_forecast`, `build_hourly_schema`, `build_7d_forecast`) quedaron **públicas** (sin guión bajo) — mismo criterio que el fix de `fire_danger.py`/`windy.py` de este rato: no repetir en un archivo nuevo, en la misma sesión, el mismo antipatrón de encapsulamiento que el audit acababa de señalar. Las que solo se usan adentro del service (`_compute_sun_times`, `_wmo_from_windy_daily`, `_rain_label`) siguen privadas.
- `_AR_TZ` (zona horaria Argentina) también promovida a `AR_TZ` pública en `dashboard_builder.py` — la necesitan tanto el service (`build_synthetic_daily_multi`, `build_7d_forecast`) como el router (`_parse_ar_dt`), y la dirección correcta de dependencia es router→service, nunca al revés.
- `routers/weather.py` quedó con: los 2 endpoints, los wrappers `_safe_windy_hourly`/`_safe_windy_daily` (fetch, no agregación — se quedan, el audit los distingue explícitamente de los 5 a extraer), `_parse_ar_dt` y el trivial `_get_weather_code_from_current` (no estaba en la lista de 5 del audit, se dejó donde estaba).
- Imports podados en los 5 archivos tocados (routers + los 2 tests) — verificado con un script AST propio (no había `ruff` instalado en el venv) que no quedó ningún import muerto salvo `SOURCE_WINDY` en `weather.py`, que ya estaba sin uso ANTES de esta sesión — no es mío, no se tocó (fuera de alcance de los 4 P2 pedidos).
- 2 tests que importaban `_build_7d_forecast`/`_build_rain_forecast` directo de `app.routers.weather` (`test_forecast_field_sources.py`, `test_rain_forecast_drizzle.py`) actualizados al nuevo import público desde `app.services.dashboard_builder`.

**Files changed:**
- `apps/backend/app/routers/weather.py` (877 → 406 líneas)
- `apps/backend/app/services/dashboard_builder.py` — nuevo (495 líneas)
- `apps/backend/tests/test_forecast_field_sources.py`
- `apps/backend/tests/test_rain_forecast_drizzle.py`

**Tests:**
- `.venv/Scripts/python.exe -m pytest -q` → **762 passed**, 0 failed — mismo número que antes del split (refactor puro, no se agregó ni quitó comportamiento).

**Next:**
1. Los 4 P2 de la auditoría de backend (`docs/plans/auditoria-backend-2026-09-02.md`) quedaron resueltos y verdes en esta sesión. Pendiente de decisión del usuario: commitear y pushear.
2. Quedan los P3 del mismo audit (housekeeping menor — `frozen=True` en schemas de niebla, CORS legado, archivo suelto `=0.1.9`, deprecation warnings, `.env.example`, `pip-audit`) sin atacar, no pedidos todavía.

---

## 2026-09-02 — P1 de la auditoría de backend: rate limiting real detrás del proxy de Render

**Done:**
- Verificado por lectura de código propia (no solo el reporte del subagente) — `render.yaml:7` sin `--forwarded-allow-ips`, `rate_limit.py:7` usa `get_remote_address` (lee `request.client.host`), confirmado con `uvicorn --help` que el default real es `'127.0.0.1'` (o `$FORWARDED_ALLOW_IPS` si estuviera seteada, que no lo está). Render conecta desde su red interna, no loopback — sin el flag, uvicorn ignora `X-Forwarded-For` y todo el tráfico comparte el IP del proxy de Render como key de rate limit.
- Fix: `--forwarded-allow-ips='*'` agregado al `startCommand`. Razonable en este caso porque Render es el único punto de ingreso posible al proceso (no hay forma de conectar directo al puerto interno sin pasar por su proxy).
- Mejora complementaria (pedida por el usuario): `main.py` — el middleware `request_logging` ahora loguea `client=<ip>` usando el mismo `get_remote_address` que el rate limiter, para poder confirmar en los logs de Render post-deploy si el fix realmente diversifica las IPs vistas (antes no se logueaba ningún IP).

**Files changed:**
- `apps/backend/render.yaml`
- `apps/backend/app/main.py`

**Tests:**
- `.venv/Scripts/python.exe -m pytest -q` → 753 passed, sin cambios (es config de despliegue + un campo de logging, no lógica).
- **No verificable end-to-end desde acá** — es un cambio de comportamiento del proxy en producción, sin acceso a logs de Render. Verificar después del deploy: las líneas de log deberían mostrar `client=` con IPs variadas entre requests de distintos usuarios, no siempre la misma.

**Next:**
1. **Commiteado y pusheado** (`d3058a3`).
2. Bug de temperatura de Incendios diagnosticado y corregido — ver próxima entrada.

---

## 2026-09-02 — Bug real en Incendios: temperatura de la madrugada mostrada como "actual"

**Contexto:** usuario reportó Incendios mostrando 10°C cuando la temperatura real en ese momento era 22°C. Primero se descartó que fuera un mock propio (confirmado recargando el navegador compartido sin ningún interceptor activo) — era un reporte real.

**Causa raíz confirmada por lectura de código:** `incendios.py:66` (antes del fix) hacía `current = slots[0]` — tomaba el primer elemento del array que devuelve Windy sin ningún filtro de proximidad a "ahora". El array de Windy no está garantizado a empezar en el momento de la consulta — su primer elemento suele ser el inicio del ciclo de ejecución del modelo GFS, que puede quedar varias horas atrás. Nada en el código verificaba esto: ningún test cubría la alineación temporal (todos usaban payloads sintéticos con un solo timestamp base, sin verificar que el índice 0 correspondiera a "ahora" en ningún sentido real).

Esto no era solo un problema del gauge: el **frontend** (`Incendios.tsx:350`) toma `data?.slots[0]` directamente para los chips de Temperatura/Humedad/Viento/Precipitación — así que corregir solo `current_score` en el backend no alcanzaba, había que asegurar que el array `slots` completo empezara desde el slot correcto.

**Fix:**
- `FireDangerEntry`: nuevo campo `timestamp_s` (epoch), poblado en ambos parsers (`_parse_fire_entries_from_fwi`/`_parse_fire_entries_from_gfs`).
- Nueva función pública `closest_to_now()` en `fire_danger.py` — encuentra el entry cuyo timestamp está más cerca del momento actual.
- `incendios.py`: `_build_response` ahora recorta el array de entries desde el índice del slot más cercano a "ahora" **antes** de construir la respuesta — no solo corrige `current_score`/`current_label`, sino que el array `slots[0]` que expone el JSON ya es el correcto, así que el frontend no necesita ningún cambio. De paso, el timeline ("Próximas 24h") deja de incluir horas ya pasadas, que no aportaban nada al usuario.

**Files changed:**
- `apps/backend/app/services/fire_danger.py`
- `apps/backend/app/routers/incendios.py`
- `apps/backend/tests/test_fire_danger.py` — 4 tests nuevos de `closest_to_now` (incluye el caso "array empieza 6h en el pasado" que reproduce el bug real)
- `apps/backend/tests/test_incendios_router.py` — helper actualizado + 1 test de integración end-to-end reproduciendo el escenario exacto reportado (10°C/22°C)

**Tests:**
- `.venv/Scripts/python.exe -m pytest -q` → **758 passed**, 0 failed (753 + 5 nuevos; 4 tests existentes del router necesitaron el nuevo campo `timestamp_s` en su helper de construcción, sin cambiar su lógica de aserción).
- El test de integración `test_current_reflects_closest_slot_not_raw_index_zero` confirma end-to-end: con un array donde el índice 0 es 6h en el pasado, la respuesta HTTP refleja el slot correcto y el array `slots` queda recortado (2 slots futuros, no los 4 originales).
- No verificable con datos reales de Windy en este entorno (sin `WINDY_API_KEY` local) — el fix está fundamentado en la lógica del código (Windy no garantiza alineación) y confirmado con tests sintéticos que reproducen el escenario exacto reportado.

**Next:**
1. **Commiteado y pusheado** (`eae9db5`). Usuario reportó seguir viendo el bug (esta vez 2°C) justo antes del push — confirmado que era esperado: el fix nunca había llegado a producción, solo estaba en el working tree local desde la sesión anterior. A reverificar una vez termine el deploy de Render.

---

## 2026-09-02 — Spinner de coldstart + P2 #1 de la auditoría (race condition CheckWX)

**Done — spinner de coldstart en PrevisionClima (pedido del usuario, con SVG provisto):**
- `WakingUpNotice` (PrevisionClima.tsx): el punto `animate-ping` reemplazado por el spinner "dual ring" que pasó el usuario (dos arcos SMIL girando en sentidos opuestos, distinta velocidad) — código exacto, solo convertido a JSX/camelCase. Mensaje reescrito a algo más conversacional: "Despertando el servidor — puede tardar unos segundos, es solo la primera vez del día." (antes: "El servicio está despertando..."). Sin gating de `motion-safe:` a propósito — es feedback de carga real, no decoración, y debe seguir siendo legible con `prefers-reduced-motion`.
- Verificado en navegador forzando temporalmente `isWakingUp = true` (revertido después) — las 2 animaciones SMIL confirmadas con los valores exactos del SVG original.

**Done — P2 #1 del reporte de auditoría: race condition (TOCTOU) en el gate de cuota de CheckWX:**
- Causa: `checkwx.py` chequeaba `current_count` e incrementaba en pasos separados por un `await` HTTP real (`_do_http_fetch`) en el medio — sin sincronización, N requests concurrentes con ICAOs distintos podían leer el mismo `current_count` antes de que ninguna incrementara.
- Fix: nuevo `asyncio.Lock` (mismo patrón que `SingleFlightCache`/`windy.py`/`oavv.py`) envolviendo **solo** el chequeo+reserva de cupo — el fetch HTTP real queda deliberadamente fuera del lock para no serializar ICAOs distintos entre sí (eso habría cambiado un problema de cuota en un cuello de botella de latencia).
- Test nuevo de concurrencia real (`asyncio.gather` con 10 ICAOs, límite bajado a 5) — **verificado con ciclo red/green real**: confirmado que el test FALLA sin el lock (`10 == 5`, el contador se pasó al doble del límite) y PASA con el lock. La primera versión del test usaba un mock HTTP instantáneo y pasaba incluso sin el fix — no detectaba nada; hubo que agregar un delay artificial (`asyncio.sleep(0.01)` en el mock) para que las corutinas realmente se entrelacen y el bug se manifieste.

**Files changed:**
- `apps/frontend/src/pages/PrevisionClima.tsx`
- `apps/backend/app/services/checkwx.py`
- `apps/backend/tests/test_checkwx_service.py` — 1 test nuevo

**Tests:**
- Frontend: `npx tsc -b --noEmit` → 0 errores. `npx vite build` → OK. Detector `impeccable` → sin hallazgos.
- Backend: `.venv/Scripts/python.exe -m pytest -q` → **759 passed**, 0 failed.

**Next:**
1. **Commiteado y pusheado** — 2 commits: `fd8947f` (spinner) y `48ce76b` (race condition CheckWX). Usuario va a hacer `/clear` después de esto — ver el resumen de pendientes abajo para la próxima sesión.

**Pendientes al cierre de esta sesión (2026-09-02), para retomar con `/continue`:**
1. **4 P2 del reporte de auditoría** (`docs/plans/auditoria-backend-2026-09-02.md`, no commiteado — regla docs/), sin atacar todavía:
   - #2 `LatParam`/`LonParam` duplicados en 4 routers, con `niebla.py` usando `ge=-76` en vez de `-74` (mismas coordenadas aceptadas en un endpoint, rechazadas en otro).
   - #3 `routers/weather.py` con 877 líneas, mezcla routing con lógica de agregación pesada (excede el techo de 800 líneas del propio estándar del proyecto).
   - #4 `fire_danger.py` importa símbolos con guión bajo (`_fetch_raw`, `_safe_get`, `_k_to_c`, `_AR_TZ`) de `windy.py` — cruza el límite de encapsulamiento de módulo.
   - #5 `/tender-ropa` (hoy) nunca intenta Windy, solo Open-Meteo — asimetría con `/tender-ropa/forecast` (7 días) que sí intenta Windy primero.
2. **Rediseño completo de PrevisionClima con `/impeccable`** — pedido original del usuario, nunca empezado (se priorizaron otros 3-4 hallazgos primero).
3. **Alerta de rotación/intensidad de viento (>60km/h) en la card principal de PrevisionClima** — pedido del usuario, dato ya confirmado disponible (`wind_dir_deg` por hora en el forecast horario), nunca implementado.
4. Verificar en Render (una vez el deploy de `d3058a3` haya corrido): los logs deberían mostrar `client=<ip>` con IPs variadas entre requests de distintos usuarios — confirma si el fix del P1 (rate limiting) funcionó.
5. El umbral de CAPE (1000 J/kg) del veto de tormenta no está validado contra datos reales de la región — revisar si en producción genera falsos positivos/negativos.
**Next:**
1. Pendiente de decisión del usuario: commitear y pushear.

---

## 2026-09-02 — Veto de tormenta/granizo en las 3 herramientas de decisión (secado/lavado/deporte)

**Contexto:** implementación del diagnóstico presentado antes (ver entrada de más abajo con el análisis completo) — el usuario reportó que la app había dicho que se podía hacer deporte al aire libre con pronóstico de tormenta, y efectivamente llovió y cayó granizo. Causa raíz confirmada: ninguna de las 3 funciones de scoring (`score_hacer_deporte`, `score_tender_ropa`, `score_lavar_coche`) recibía nunca el tipo de fenómeno meteorológico — solo miraban milímetros de lluvia. El dato de tormenta/granizo (WMO 95/96/99) ya existía en el sistema pero nunca llegaba a estas 3 funciones, y el propio *fetch* que usan no lo solicitaba a la API.

**Aclaración importante de la misma sesión:** en el camino, el usuario reportó un valor de 38°C en Incendios que parecía un bug de datos real — se confirmó que era un mock de prueba propio (dejado activo en el Browser pane compartido durante la verificación del gauge rediseñado), no un bug del pipeline. Confirmado recargando sin el mock: el backend local sin `WINDY_API_KEY` no puede servir ningún dato de Incendios en absoluto.

**Done:**
- `calculators.py`: nuevo helper `is_storm_wmo_code()` (público) + `_has_storm_risk(weather_code, cape_j_kg)` — dos fuentes de detección porque Open-Meteo expone `weather_code` (WMO) pero Windy no; Windy sí expone CAPE (potencial convectivo), así que el veto revisa cualquiera de los dos según cuál esté disponible. Umbral CAPE ≥1000 J/kg (documentado con la fuente — NOAA SPC — en el comentario, no es un número mágico sin explicar).
- Las 3 funciones de scoring ahora aceptan `weather_code`/`cape_j_kg` opcionales y vetan a "No apto" (score=5) con headline explícito ("Tormenta eléctrica — no...") **antes** de cualquier otro cálculo, cuando se detecta tormenta/granizo — sin importar qué tan buenos sean temperatura/humedad/viento. `score_hacer_deporte` es el que más cambia: antes no tenía ningún veto en absoluto.
- `openmeteo.py`: `weather_code` agregado al fetch y parsing de `HourlyForecastData` (usada por `/tender-ropa` y `/hacer-deporte` fallback) y `DailyForecastData` (usada por `/lavar-coche` y `/tender-ropa/forecast` fallback) — antes ninguna de las dos lo pedía a la API en absoluto.
- `windy.py`: `"cape"` agregado a `_WINDY_PARAMETERS`; nuevo campo `cape_j_kg`/`cape_max_j_kg` en `WindyHourlyEntry`/`WindyDailyEntry` (con default `None` para no romper las 6 construcciones directas que ya existían en tests); `LaundryDayRaw` (estructura intermedia compartida entre Windy y Open-Meteo para `/tender-ropa/forecast`) también extendida.
- `tools.py`: los 7 call-sites actualizados (helpers genéricos `_build_hourly_scores`/`_build_hourly_scores_from_windy` vía kwargs — cuidado real acá: `score_tender_ropa` y `score_hacer_deporte` tienen órdenes de parámetros posicionales distintos, así que pasar el dato nuevo posicionalmente se lo habría asignado al parámetro equivocado en una de las dos; se resolvió con keyword args explícitos). Para el score "actual" (no el desglose horario), se mira una ventana de horas próximas (no solo el instante exacto de la consulta) — el propio reporte del usuario fue justamente eso: la tormenta estaba pronosticada para más tarde, no en el momento exacto de la consulta.

**Files changed:**
- `apps/backend/app/services/calculators.py`
- `apps/backend/app/services/openmeteo.py`
- `apps/backend/app/services/windy.py`
- `apps/backend/app/routers/tools.py`
- `apps/backend/tests/test_calculators.py` — 10 tests nuevos (`TestStormVeto`)
- `apps/backend/tests/test_tools_router.py` — helper extendido + 1 test de integración end-to-end

**Tests:**
- `.venv/Scripts/python.exe -m pytest -q` → **753 passed**, 0 failed (742 base + 11 nuevos). Incluye un test de integración end-to-end que mockea el forecast HTTP y confirma que `weather_code=95` real llega hasta la respuesta del endpoint con `"No apto"` — no solo la lógica aislada de `calculators.py`.
- No se tocó el frontend — el schema `ToolResult` expuesto como JSON no cambió, todos los parámetros nuevos son opcionales internos al backend.

**Next:**
1. **Commiteado y pusheado** — 2 commits separados: `e41de59` (los 3 fixes de UI: ScanText/BorderGlow/Incendios, que habían quedado sin commitear de la entrada anterior) y `1d2c3e1` (el veto de tormenta).
2. Quedan 2 de las 3 tareas grandes de la ronda de UI: alerta de rotación/intensidad de viento en PrevisionClima (dato ya disponible, `wind_dir_deg` por hora), y el rediseño completo de PrevisionClima con `/impeccable`.
3. El umbral CAPE (1000 J/kg) es una decisión razonable pero no validada contra datos reales de la región — vale revisarlo si en la práctica genera demasiados falsos positivos/negativos una vez en producción con la key de Windy real.
4. Usuario pidió una auditoría de backend/API con un subagente (skills `/fastapi-python`, `/python-performance-optimization`, `/python-review`, `/security-review`, `/api-security-audit`) — lanzada en background, ver próxima entrada cuando termine.

---

## 2026-09-02 — 3 fixes de UI en vivo: Radar (texto cortado), glow lento en PrevisionClima, gauge de Incendios

**Contexto:** usuario pidió levantar dev localhost para indicar fixes en vivo. Llegaron 4 pedidos de una vez + un 5to a mitad de turno (violación de la regla de "un deliverable por sesión") — se los reconoció, se hizo de inmediato el fix trivial de Radar, y se preguntó al usuario cómo priorizar el resto de los 4. Eligió "fixes rápidos de performance primero" (gauge Incendios + glow PrevisionClima). Quedan pendientes: lógica de scoring de secado/lavado/deporte (bug de seguridad reportado) y el rediseño completo de PrevisionClima con `/impeccable`.

**Done — Radar, texto cortado a mitad de palabra:**
- Causa real: `ScanText.tsx` (título cinético animado letra por letra) renderizaba **cada carácter** como su propio flex-item dentro de un `display:inline-flex; flexWrap:wrap` — el navegador no tenía forma de saber dónde terminaba una palabra, así que cortaba "lenguaje" en "lengu"/"aje" donde fuera que se agotara el ancho de línea.
- Fix: agrupé las letras por palabra (cada palabra es un único flex-item con `white-space:nowrap`), preservando el timing exacto de la animación letra-por-letra (el índice de delay sigue avanzando igual en los espacios, aunque no se animen). El mismo patrón (`chars.map` sin agrupar por palabra) probablemente está en los componentes hermanos (`ShatterText`, `FrostText`, `MeltText`, `BurnText`, `FogText`, `DriftText`, `RainText`) — no se tocaron, solo queda marcado como sospecha.

**Done — Glow lento en la card principal de PrevisionClima (mobile):**
- Causa real, coincide con un hallazgo ya documentado en el audit B1 pero nunca corregido: `BorderGlow.tsx` monta su listener de `pointermove` **incondicionalmente**, incluso en touch. En un dispositivo táctil, cualquier gesto de scroll/swipe sobre la card genera eventos `pointermove` reales (el dedo moviéndose en contacto con la pantalla) — cada uno dispara el recálculo de 13 capas de `box-shadow` + varios `mask-image` con `conic-gradient` (nada de esto es compositor-only), compitiendo con el propio scroll. Distinto del bug de `ElectricBorder`: acá no hay un loop infinito, es el cursor-tracking reaccionando a movimiento real del dedo.
- Fix: nuevo hook `useCoarsePointer()` (mismo patrón exacto que `useReducedMotion`, mismo directorio). En touch, `BorderGlow` ya no adjunta el listener de `pointermove` ni corre el sweep animado de montaje — reusa la clase `.static-glow` que ya existía (creada para `reducedMotion`), mismo color, sin el costo del tracking. Verificado: 10 eventos `pointermove` sintéticos sobre la card en touch → `--edge-proximity` nunca cambia; en desktop la clase `static-glow` no se aplica.

**Done — Gauge de Incendios rediseñado (decisión de diseño, no bug):**
- Usuario pidió alternativas ("le falta profesionalismo"). Se mostraron 3 mockups comparativos (barra unificada / número protagonista / gauge mejorado) antes de tocar código — eligió la barra unificada.
- Causa de fondo real que la opción elegida resuelve: el gauge circular (`ScoreGauge`, aguja + arco SVG) y la `RiskScaleBar` de arriba (6 celdas de color) decían básicamente lo mismo con dos lenguajes visuales distintos — redundancia real, no solo un tema de pulido.
- Fusioné ambos en un solo componente `RiskScaleBar` (score grande + barra en gradiente continuo con marcador de posición exacta + los mismos 6 chips de nivel debajo), siguiendo el mismo patrón ya usado en `MagnitudeScaleBar` (Terremotos, B5): wrapper con `transform` en vez de animar `left` directamente, gateado por `motion-safe:`. `ScoreGauge` (el SVG viejo) se eliminó — ya no se usa en ningún lado de este archivo. El chunk de Incendios bajó de 11.93 kB a 11.12 kB.
- Verificado con datos mockeados vía interceptor de `fetch` (el backend local no tiene `WINDY_API_KEY`, sin eso no hay datos reales de Incendios) — casos "Bajo" (20.8) y "Muy alto" (82.3, confirma el borde/glow resaltado que antes vivía en el bloque del gauge, ahora derivado internamente del mismo `HIGH_RISK_LABELS` Set que ya usaba el hero callout).

**Files changed:**
- `apps/frontend/src/components/animated/ScanText.tsx`
- `apps/frontend/src/components/animated/BorderGlow.tsx`
- `apps/frontend/src/hooks/useCoarsePointer.ts` — nuevo
- `apps/frontend/src/pages/Incendios.tsx`

**Tests:**
- `npx tsc -b --noEmit` → 0 errores.
- `npx vite build` → OK.
- Detector mecánico de `impeccable` sobre los 4 archivos → sin hallazgos.
- Verificado en navegador para los 3 — ver el detalle de cada uno arriba.

**Next:**
1. Pendiente de decisión del usuario: commitear y pushear.
2. Quedan 2 tareas grandes de la ronda original: lógica de scoring de secado de ropa/lavado de auto/hacer deporte (bug de seguridad — "llovió y cayó granizo pero la lógica decía que se podía estar al aire libre"), y el rediseño completo de PrevisionClima con `/impeccable`.
3. Sospecha sin confirmar: el bug de "letra por letra rompe wrap de palabras" de `ScanText` probablemente está en `ShatterText`/`FrostText`/`MeltText`/`BurnText`/`FogText`/`DriftText`/`RainText` también.

---

## 2026-08-31 — Lag de scroll en Terremotos, causa real: `ElectricBorder` nunca se pausaba

**Done:**
- Usuario confirmó que el lag de scroll seguía tras el fix del tick de 1s (commit `7e17dba`) — ese fix era real y necesario pero no era la causa dominante.
- **Causa raíz real**: `ElectricBorder.tsx` (usado 3 veces en Terremotos, para los StatCard "Sismos encontrados"/"Más cercano"/"Mayor magnitud"; también compartido con CotaDeNieve y Volcanes) corre un `requestAnimationFrame` **continuo e infinito** que nunca se pausaba — ni fuera de pantalla, ni durante scroll. Cada frame recalcula ruido Perlin de 10 octavas sobre ~270 puntos de muestra, dos veces por punto (`xn`/`yn`), ×3 instancias simultáneas, 60 veces por segundo — compitiendo directamente por el hilo principal con los frames de scroll del navegador. El propio playbook de `impeccable animate` (usado en la sesión de B5) ya advertía explícitamente: *"Any nonessential loop must stop when offscreen or hidden"* — acá faltaba además pausarlo durante scroll activo, que es el momento exacto reportado.
- **Fix**: el loop ahora se pausa (cancela el RAF en curso, no re-agenda el siguiente) en dos casos — (1) mientras el usuario scrollea activamente (listener de `scroll` con debounce de 150ms para reanudar), y (2) cuando el componente sale de la vista (`IntersectionObserver`, `rootMargin: 100px`). Al reanudar, se resetea `lastFrameTimeRef` para que el primer frame post-pausa no calcule un `deltaTime` gigante y haga "saltar" el ruido — la reanudación es indistinguible visualmente de que nunca se hubiera pausado.
- **Verificación con dificultad real de entorno**: el navegador embebido de esta sesión nunca tiene foco real del SO (`document.hidden` permanece `true` de forma persistente), lo que hace que Chrome throttlee/congele nativamente tanto `requestAnimationFrame` como `IntersectionObserver` — cualquier medición basada en `setTimeout`/RAF reales del navegador daba resultados incoherentes (0 llamadas incluso en reposo). Se resolvió reemplazando `requestAnimationFrame`/`cancelAnimationFrame` por una cola determinística controlada manualmente (`Map` + función `__tick()` propia, sin depender de ningún timer real del navegador) y agregando instrumentación de debug temporal (removida antes de dejar el archivo final) directamente en el código para observar la secuencia real de eventos. Confirmado end-to-end: en reposo las 3 instancias dibujan normalmente; al hacer scroll las 3 cancelan su frame pendiente (0 actividad durante scroll sostenido); tras dejar de scrollear, las 3 vuelven a dibujar con `isScrolling:false`.

**Files changed:**
- `apps/frontend/src/components/animated/ElectricBorder.tsx`

**Tests:**
- `npx tsc -b --noEmit` → 0 errores.
- `npx vite build` → OK, 2.02s. El hash del chunk `ElectricBorder-*.js` quedó idéntico al de un build intermedio con la instrumentación de debug ya removida — confirma que no quedó ningún residuo del código de diagnóstico.
- Detector mecánico de `impeccable` → sin hallazgos.
- Verificado en navegador con la cola determinística descripta arriba (ver Done) — sin poder usar el flujo normal de RAF real por la limitación de foco del entorno, documentada explícitamente para no repetir el mismo intento fallido en otra sesión.

**Next:**
1. **Commiteado y pusheado** (`8354b6e`).
2. El mismo componente `ElectricBorder` se usa en CotaDeNieve y Volcanes (Grupo B del audit) — este fix las beneficia automáticamente sin tocarlas, al ser un componente compartido.
3. Si el usuario reporta que TODAVÍA hay lag perceptible tras este fix (por ejemplo en dispositivos de gama baja incluso sin scroll), el siguiente paso sería reducir el costo base del shader (menos `samples`/`OCTAVES`) — no se tocó en esta sesión para minimizar el riesgo de alterar el efecto visual sin necesidad confirmada.

---

## 2026-08-31 — Bugs en vivo (Terremotos): popover EMSC desbordado en mobile + lag de scroll

**Done:**
- Usuario reportó dos bugs reales en producción vía captura de `/terremotos` en mobile: (1) el popover de `ModelBadge` ("EMSC · Europa") se corta contra el borde derecho de la pantalla, y (2) la página laguea al hacer scroll (confirmado por el usuario que no es caché — probó borrando cookies/caché sin cambios).
- **Causa raíz del bug 1**: `ModelPopover` posicionaba con `left:0`/`right:0` fijos según un prop `align` hardcodeado por variante (`header` → siempre `align="left"`), sin considerar dónde cae el trigger real en el viewport. Con "Córdoba · radio 2000 km" (más largo que "Buenos Aires"), el badge EMSC queda cerca del borde derecho, y el popover de 256px se abre hacia la derecha desde ahí, saliéndose de pantalla.
- **Fix bug 1**: `ModelPopover` ahora mide la posición real del botón (`getBoundingClientRect`, vía `useLayoutEffect` para no flashear) y se posiciona con `position: fixed` + `left` clampeado a los bordes del viewport (16px de margen mínimo). Eliminado el prop `align` (ya no hace falta, el clamp resuelve ambos lados automáticamente). Efecto colateral positivo: `position: fixed` también escapa del recorte de contenedores con `overflow-x: auto` (tablas), donde `absolute` quedaría cortado igual. Se agregó un listener de `scroll` que cierra el popover (antes solo click-outside/Escape) — necesario porque `fixed` ya no sigue al trigger si el usuario scrollea con el popover abierto.
- **Causa raíz del bug 2**: `useSyncedLabel` (el hook detrás de "Sincronizado hace Xs") se llamaba directamente en el componente de página `Terremotos` (`Terremotos.tsx:175`, antes del fix). Su `setInterval` de 1s vive en un `useState` que, al estar en el componente padre, forzaba un re-render de **toda la página** cada segundo — tabla completa de sismos, `MagnitudeScaleBar`, los 3 `StatCard`/`ElectricBorder` — no solo del pequeño texto que necesitaba actualizarse. Esto ya estaba documentado como P2 en el audit B1 ("re-render de página completa cada 1s en Terremotos", acción #5, asignado a `$impeccable optimize`) pero nunca se había corregido.
- **Fix bug 2**: nuevo componente `SyncedLabel` que llama a `useSyncedLabel` internamente — el tick de 1s y su `setState` quedan aislados ahí, así que solo ese `<span>` re-renderiza cada segundo. El componente padre ya no llama al hook.

**Files changed:**
- `apps/frontend/src/components/ui/ModelBadge.tsx`
- `apps/frontend/src/pages/Terremotos.tsx`

**Tests:**
- `npx tsc -b --noEmit` → 0 errores.
- `npx vite build` → OK, 2.31s.
- Detector mecánico de `impeccable` sobre ambos archivos → sin hallazgos.
- Verificado en navegador (dev server + backend local): reproducido el layout exacto del bug ("Córdoba · radio 2000 km" vía el buscador de ciudad) y forzado el caso extremo (botón empujado al borde real del viewport vía JS) — el popover quedó siempre dentro de pantalla (`overflowsRight: false`, `overflowsLeft: false`). Para el lag: `MutationObserver` sobre la tabla de sismos durante 3.5s → **0 mutaciones** (antes del fix, hubiera mutado ~3 veces); confirmado en paralelo que el label "Sincronizado hace Xs" sigue contando en vivo (51s → 54s en la misma ventana), o sea la funcionalidad visible no se rompió, solo se aisló el re-render.

**Next:**
1. **Commiteado y pusheado** (`7e17dba`, solo los 2 archivos de código).
2. El mismo patrón de "hook con tick de 1s en el componente de página" podría existir en otras páginas con badges de sincronización similares — no se auditó el resto del sitio en esta sesión, queda para otra si se prioriza.

---

## 2026-08-31 — Plan B Fase B5: `$impeccable animate` — transición en las escalas de gravedad

**Done:**
- Motion thesis acordado con el usuario antes de tocar código (sin `shape` previo — B5 no tenía brief, se armó el thesis inspeccionando el lenguaje de motion existente): `ScoreGauge` (Incendios/LavarCoche) ya era el "mejor ejemplo" señalado por el audit B1 (`motion-safe:[transition:...]`, gateado por `prefers-reduced-motion` vía Tailwind), pero los dos componentes de "escala de gravedad" del sitio (`MagnitudeScaleBar` en Terremotos, `DangerScale` en Volcanes) cambiaban de estado sin ninguna transición — el indicador saltaba en vez de comunicar que el dato cambió.
- `MagnitudeScaleBar.tsx`: el punto de magnitud activa pasó de `left: %` + `transform: translateX(-50%)` estático a un patrón de dos capas — wrapper externo animado por `transform: translateX(%)` (compositor-only, evita animar `left` que es layout-driving) + dot interno con su propio `translateX(-50%)` fijo para centrarse. Color y glow del dot también transicionan (`motion-safe:[transition:all_0.6s_ease]`) cuando cambia de nivel.
- `DangerScale.tsx`: mismo mecanismo (`motion-safe:[transition:all_0.6s_ease]`) en cada segmento — sin necesidad de la técnica de dos capas porque no hay movimiento posicional, solo color/glow.
- Reusa exactamente el mecanismo ya probado de `ScoreGauge`, sin inventar timing ni easing nuevo (0.6s, `cubic-bezier(0.16,1,0.3,1)` para el desplazamiento — misma curva de "llegada confiada" que recomienda el propio playbook de `animate`). `prefers-reduced-motion` queda cubierto gratis por el variant `motion-safe:` de Tailwind (mismo mecanismo que ya usa `ScoreGauge`, no se reimplementó).
- Explícitamente fuera de scope: el "glow de severidad" (`BorderGlow`/`ElectricBorder`) — su inconsistencia ya está asignada a `$impeccable clarify` en el audit, no a `animate`.

**Files changed:**
- `apps/frontend/src/components/ui/MagnitudeScaleBar.tsx`
- `apps/frontend/src/components/ui/DangerScale.tsx`

**Tests:**
- `npx tsc -b --noEmit` → 0 errores.
- `npx vite build` → OK, 1.96s.
- Detector mecánico de `impeccable` (`detect.mjs`) sobre ambos archivos → sin hallazgos.
- Verificado en navegador (dev server + backend local levantado para esta verificación): `MagnitudeScaleBar` en Terremotos con datos reales — el dot de "M3" renderiza con `transform: translateX(...)` computado y `transition: transform 0.6s cubic-bezier(...)` presente en el wrapper, `transition: 0.6s` (all) en el dot interno. No se pudo forzar un cambio real de magnitud entre refetches para ver la animación en curso (mismos eventos sísmicos recientes) — el mecanismo de transición está confirmado por CSS computado, el comportamiento de interpolación en sí es estándar del navegador.

**Next:**
1. Con B5 (parcial: `animate`) cerrado, Plan B queda completo en su forma acordada — `colorize` no se corrió (no hubo necesidad real detectada: el sitio ya usa color con criterio, ver hallazgos positivos de B1).
2. **Commiteado y pusheado** (`501c705`, solo los 2 archivos de código — mismo criterio de siempre, `CLAUDE.md`/`PROGRESS.md`/`docs/`/`PRODUCT.md` excluidos).

---

## 2026-08-31 — Plan B Fase B4: `$impeccable adapt` — touch targets + fallback mobile

**Done:**
- Fuente del scope: acción #7 del reporte B1 (`docs/plans/plan-b1-audit-2026-08-31.md`), patrón sistémico #4 (touch targets) y #7 (truncamiento sin fallback) — no se corrió un `shape` nuevo, el audit ya traía ubicación exacta línea por línea.
- **Touch targets <44px → 44px** (patrón ya usado en el proyecto, `min-h-[Npx]`, sin mecanismos nuevos):
  - `components/ui/ModelBadge.tsx` (variants `inline` y `header`, compartido en 4 páginas: PrevisionClima, HacerDeporte, TenderRopa, LavarCoche): `min-h-[28px]` → `min-h-[44px]`.
  - `Metar.tsx`: tabs de región (modal ICAO) y tabs de "Ejemplos reales anotados" — sin `min-h` antes (~22-25px reales), ahora `min-h-[44px] inline-flex items-center justify-center`.
  - `Nubes.tsx` (`pillStyle()`, botones Todo/dropdown Nubes/Aeronáutico): `minHeight: '34px'` (fix previo insuficiente) → `'44px'`.
- **Terremotos.tsx** (ícono de mapa 13px en la tabla desktop, P3): decisión consciente de **no** llevarlo a 44×44 — es un ícono suelto dentro de una fila de tabla densa de escritorio (la vista mobile-cards ya cumple 44px desde el refactor de Terremotos). Se usó `padding: 6, margin: -6` (expande el área clickeable a 25×25 sin desplazar el layout de la fila) — cumple el mínimo WCAG 2.5.8 AA (24×24), no el AAA de 44×44 que sí aplica en mobile.
- **Lluvias.tsx**: la columna "Duración típica" (`hidden sm:table-cell`) no tenía ningún fallback mobile — a diferencia de "Cuándo aparece", que sí tenía un bloque `sm:hidden` dedicado. **Hallazgo adicional no documentado en B1**: por el desalineamiento de breakpoints (`sm` en la columna/bloque mobile vs `md` en la otra columna), "Cuándo aparece" quedaba invisible en el rango 640-767px — ni la tabla lo mostraba (esperaba `md`) ni el bloque mobile (se ocultaba en `sm`). Fix: alineados ambos breakpoints a `md` (columna de tabla + bloque mobile) y extendido el bloque mobile para incluir también "Duración típica" — una sola fuente de verdad por rango de viewport, sin gaps.
- **Niebla.tsx**: grid del catálogo de niebla (`repeat(auto-fill, minmax(300px, 1fr))`) causaba overflow horizontal bajo 300px+padding de ancho útil. Fix de una línea, patrón CSS estándar: `minmax(min(300px, 100%), 1fr)` — la columna nunca excede el ancho disponible, sin tocar el comportamiento en pantallas grandes.

**Files changed:**
- `apps/frontend/src/components/ui/ModelBadge.tsx`
- `apps/frontend/src/pages/Metar.tsx`
- `apps/frontend/src/pages/Nubes.tsx`
- `apps/frontend/src/pages/Terremotos.tsx`
- `apps/frontend/src/pages/Lluvias.tsx`
- `apps/frontend/src/pages/Niebla.tsx`

**Tests:**
- `npx tsc -b --noEmit` → 0 errores.
- `npx vite build` → OK, 2.02s.
- Verificado en navegador (dev server local + backend local levantado esta sesión para Terremotos, `.venv` ya existente): alturas reales medidas vía `getBoundingClientRect()` — región/ejemplos de Metar y filtros de Nubes en 44px+, ModelBadge en 44px (variant `header`, página Terremotos), ícono de mapa de Terremotos en 25×25 con el layout de fila intacto. Niebla a 320px de viewport: `scrollWidth === innerWidth` (sin overflow). Lluvias a 700px (el gap que encontré): tarjetas mobile muestran Duración y Cuándo para las 10 nubes del catálogo.

**Next:**
1. Con B4 cerrado, queda B5 (`$impeccable animate`/`colorize`, opcional, solo si se prioriza) como último bloque de Plan B.
2. **Commiteado y pusheado** (`916749f`, solo los 6 archivos de código — `CLAUDE.md`/`PROGRESS.md`/`docs/`/`PRODUCT.md` excluidos por regla del proyecto). B1-B3 ya estaban commiteados de antes (`3f28d9c` y anteriores) — confirmado al revisar `git log` al inicio de esta sesión, la duda de sesiones previas sobre "cómo agrupar B3+B4" ya no aplica.

---

## 2026-08-31 — Plan B Fase B3: Briefs 8 y 9 aplicados + hallazgo real de tooling local

**Done — Brief 8 (LavarCoche.tsx):**
- `LABEL_COLOR['No apto']`: `#b91c1c` (~2.9:1) → `#ff6b6b` (verificado a mano: ~7.0:1 sobre navy). Es el mismo valor que el token `--color-crit-soft`, pero **se dejó como hex crudo a propósito** (con comentario explicando por qué): `barColor` se concatena más abajo como `${barColor}20`/`${barColor}40` (alpha-suffix hex de 8 dígitos) — un `var(--color-crit-soft)` ahí rompería esa interpolación y produciría un color CSS inválido. Encontrado revisando los usos de `LABEL_COLOR` antes de aplicar el fix ingenuo que me había propuesto en el brief original.

**Done — Brief 9 (Landing.tsx):**
- Pills de fuente de datos: `rgba(200,168,75,0.65)` → `0.85` (verificado: ~5.95:1, con margen). Ese mismo valor (0.85) ya era usado en otras dos etiquetas de la misma página ("Herramientas"/"Guías meteorológicas") — confirma que es consistente con una convención ya existente en el archivo, no un valor inventado.

**Hallazgo importante — `vite build` local no refleja el chunk de entrada:**
- Al verificar Brief 9, noté que el hash del chunk `index-*.js` (App.tsx + Landing.tsx, "critical path") no cambiaba entre builds pese a tocar esos archivos. Investigado: **incluso el texto original de Landing.tsx/App.tsx (anterior a cualquier cambio de esta sesión) está ausente del `dist/assets/index-*.js` local**, con `dist/` y `node_modules/.vite` completamente limpiados. Confirmado que el resto de los chunks lazy-loaded (Metar, Nubes, Terremotos, Incendios, Niebla, LavarCoche) SÍ reflejan los cambios correctamente — el problema es específico del chunk de entrada en este `rolldown-vite v8.0.13` local.
- **No es un problema de mi código ni de esta sesión**: `tsc -b --noEmit` pasa limpio siempre, y el dev server (`preview_start`, usado durante toda la sesión) renderiza Landing/App correctamente con los valores reales — confirmado ahora mismo con `getComputedStyle` en vivo (`rgba(200, 168, 75, 0.85)` en las 3 etiquetas). El despliegue real pasa por el build de Vercel (entorno limpio, ajeno a esto). Queda como algo a investigar aparte si en algún momento se necesita confiar en un `vite build` local para el critical path — por ahora, usar `tsc` + dev server como fuente de verdad para App.tsx/Landing.tsx.
- **Incidente propio durante la investigación**: probé revertir a HEAD con `git stash` encadenado con `&&` a una serie de comandos de diagnóstico; el `grep` intermedio no encontró coincidencias (exit code 1 — comportamiento normal de grep sin matches), lo que cortó la cadena `&&` antes de llegar al `git stash pop` planeado. Los Briefs 3–9 quedaron en el stash, no perdidos — recuperados con `git stash pop` en cuanto lo noté, verificado archivo por archivo que el contenido correcto volvió. Lección: nunca encadenar `git stash ... && comandos-que-pueden-fallar ... && git stash pop` en un solo comando — el pop debe ser un paso separado e incondicional.

**Files changed:**
- `apps/frontend/src/pages/LavarCoche.tsx`
- `apps/frontend/src/pages/Landing.tsx`

**Tests:**
- `npx tsc -b --noEmit` → 0 errores (verificado también después de recuperar el stash).
- `npx vite build` → OK, exit 0 (ver salvedad del chunk de entrada arriba).
- Verificado en dev server real: pills de Landing con el color correcto confirmado vía `getComputedStyle`. LavarCoche no se pudo verificar visualmente (depende de datos reales, backend local no disponible) — confirmado por lectura de código.

**Next:**
1. **Los 9 briefs de B2 están completos.** Ningún commit hecho todavía desde Brief 2 (`44826ae`) — 7 briefs (3 al 9) esperando decisión del usuario sobre cómo commitear (juntos, separados, etc.).
2. Plan B: quedan B4 (aplicar P0/P1 restantes — ya cubierto por estos 9 briefs) y B5 (animate/colorize, opcional) si se prioriza más adelante.

---

## 2026-08-31 — Plan B Fase B3: Briefs 6 y 7 aplicados (Incendios + Niebla, componente compartido)

**Done:**
- Nuevo componente compartido `components/ui/HourlyAccessibleList.tsx` (`<ul className="sr-only">` con `aria-label`) — alternativa textual para gráficos de barras horarias cuyo dato real solo vive en `title` (hover-only) o dentro de un `role="img"`. Tal como sugería el Brief 7, se hizo una sola vez y se reusa en los dos timelines en vez de reimplementarlo.
- `Incendios.tsx` (`RiskTimeline`): `HourlyAccessibleList` con las 8 franjas horarias (hora + nivel de riesgo + puntaje), sin tocar el gráfico visual de barras.
- `Niebla.tsx` (`VisibilityTimeline`): mismo patrón, 12 franjas (hora + visibilidad en km + nivel de niebla). Nota de la auditoría original corregida al implementar: las etiquetas de hora y nivel de niebla YA eran texto plano fuera del `role="img"` (no estaban ocultas), pero vivían en dos filas paralelas sin asociación hora↔nivel para un lector de pantalla — la lista nueva las empareja en un solo ítem legible.

**Files changed:**
- `apps/frontend/src/components/ui/HourlyAccessibleList.tsx` — nuevo
- `apps/frontend/src/pages/Incendios.tsx`
- `apps/frontend/src/pages/Niebla.tsx`

**Tests:**
- `npx tsc -b --noEmit` → 0 errores.
- `npx vite build` → OK, 2.08s, nuevo chunk `HourlyAccessibleList` de 0.24 kB.
- Verificado en navegador: ambas páginas cargan sin errores de consola nuevos (502 del proxy preexistente, sin backend local). No se pudo ver la lista con datos reales (dependen del backend), confirmado por lectura de código en cambio.

**Next:**
1. Gate de commit cumplido en los 5 briefs pendientes (3, 4, 5, 6, 7) — el usuario decide cuándo commitear.
2. Quedan 2 briefs puntuales: LavarCoche (contraste), Landing (contraste).

---

## 2026-08-31 — Plan B Fase B3: Briefs 4 y 5 aplicados (Nubes + Terremotos)

**Done — Brief 4 (Nubes.tsx):**
- `cloud.name`/`item.name` (`CloudCardItem`/`AeroCardItem`): `<div>` → `<h3>`, sin cambiar clases visuales. Verificado en navegador: jerarquía `h1` (1) → `h2` (6 secciones) → `h3` (18 ítems de catálogo), sin salto.
- 5 instancias de contraste (`opacity` 0.5/0.6/0.7 en subtítulos, nota de "fenómeno invisible", curiosidades x2, footer) subidas a 0.75 — mismo cálculo que Metar.

**Done — Brief 5 (Terremotos.tsx):**
- El `<span role="status">` que envolvía el texto que tickea cada segundo ("Sincronizado hace Xs") perdió el `role="status"` — sigue tickeando visualmente igual, ya no le spammea a lectores de pantalla.
- Nuevo `useSyncAnnouncement(dataUpdatedAt)`: región `sr-only` separada con `role="status"`/`aria-live="polite"` que solo cambia de texto cuando `dataUpdatedAt` cambia de verdad (refetch real), con hora legible ("Datos actualizados a las HH:MM:SS") — nunca con el tick del reloj.
- Verificado en navegador: la región sr-only no cambia en 2.2s de espera (sin refetch real), y ningún span visible conserva `role="status"`.

**Files changed:**
- `apps/frontend/src/pages/Nubes.tsx`
- `apps/frontend/src/pages/Terremotos.tsx`

**Tests:**
- `npx tsc -b --noEmit` → 0 errores.
- `npx vite build` → OK, 2.07s.
- Verificación en navegador (JS directo sobre el DOM) para ambos fixes, ver arriba.

**Next:**
1. Gate de commit cumplido en ambos — pendiente confirmación del usuario (el usuario pidió encadenar briefs antes de decidir sobre el commit).
2. Quedan 4 briefs puntuales: Incendios (RiskTimeline), Niebla (VisibilityTimeline), LavarCoche (contraste), Landing (contraste).

---

## 2026-08-31 — Plan B Fase B3: Brief 3 aplicado — Metar.tsx (contraste + modal + teclado)

**Done:**
- Contraste: 7 instancias de `--color-muted-foreground` con `opacity` 0.4/0.5/0.6 subidas a 0.75 (calculado a mano: ~4.69:1 contra `#060d1a`, con margen sobre el mínimo AA de 4.5:1 — a 0.72 daba ~4.40:1, insuficiente). De paso, mismo fix en el país de `IcaoRow` (mismo patrón, no estaba en la lista original de 7 pero es el mismo bug).
- Modal ICAO: `role="dialog"`, `aria-modal="true"`, `aria-labelledby` apuntando al título; botón de cerrar con `aria-label`; focus trap real (Tab cicla dentro del modal, wrap en ambos extremos); foco vuelve al botón "Ver ICAO" al cerrar (por Escape, click afuera, botón ✕, o selección de aeródromo) via un `closeModal()` centralizado.
- `IcaoRow`: convertido de `<div onClick>` a `<button>` real — accesible por teclado nativamente (Enter/Space), sin necesidad de `role`/`tabIndex`/`onKeyDown` manual.

**Files changed:**
- `apps/frontend/src/pages/Metar.tsx`

**Tests:**
- `npx tsc -b --noEmit` → 0 errores.
- `npx vite build` → OK, 13.69s (warning de timing de `vite-plugin-svgr`, infra, no relacionado).
- Verificado en navegador vía `javascript_tool`: modal abre con `role="dialog"`/`aria-modal`/label correcto, foco inicial en el buscador, Tab desde el último elemento vuelve al primero (trap funcionando), Escape cierra y devuelve el foco al botón "Ver ICAO", filas del listado son `<button>` reales. 2 de las 7 instancias de contraste verificadas visualmente en la carga inicial (las otras 5 viven dentro de bloques condicionales que requieren un METAR real — sin backend local, no se pudieron ver renderizadas, confirmadas por diff de código en cambio).

**Next:**
1. Gate de commit cumplido — pendiente confirmación del usuario para commitear y pushear.
2. Quedan 6 briefs puntuales: Nubes (headings+contraste), Terremotos (live region), Incendios (RiskTimeline), Niebla (VisibilityTimeline), LavarCoche (contraste), Landing (contraste).

---

## 2026-08-31 — Plan B Fase B3: Brief 2 aplicado — `aria-expanded` en los 5 acordeones

**Done:**
- `Metar.tsx` (`GlosarioSection`): `aria-expanded`/`aria-controls="metar-glosario-content"` en el botón, `id` agregado al contenido (componente único en la página, id estático).
- `Radar.tsx` (`ExerciseCard`, 3 instancias): `aria-expanded`/`aria-controls` con `useId()` para evitar colisión de ids entre las 3 tarjetas.
- `Nubes.tsx` (3 widgets): toggle aeronáutico en `CloudCardItem` (`useId()`, se repite 13 veces vía el catálogo — verificado que cada instancia genera un id único), `QuickIdGuide` (id estático, componente único), dropdown de familias en `FilterBar` (id estático, confirmado que `FilterBar` se renderiza una sola vez en la página antes de asumir que no colisiona).
- Verificado en navegador (dev server local) con JS directo sobre el DOM: los 3 tipos de botón (Metar, Radar, Nubes×3) togglean `aria-expanded` de `false`→`true` al click y el `id` referenciado por `aria-controls` existe en el DOM una vez expandido, en las 3 páginas.

**Files changed:**
- `apps/frontend/src/pages/Metar.tsx`
- `apps/frontend/src/pages/Radar.tsx`
- `apps/frontend/src/pages/Nubes.tsx`

**Tests:**
- `npx tsc -b --noEmit` (apps/frontend) → 0 errores.
- `npx vite build` → OK, 1.89s, bump de tamaño mínimo esperado en los 3 chunks tocados (Metar/Nubes/Radar).
- Verificación en navegador vía `javascript_tool` (no visual/screenshot, inspección directa del DOM) — comportamiento correcto confirmado en los 3 archivos.

**Next:**
1. Gate de commit cumplido — pendiente confirmación del usuario para commitear y pushear.
2. Quedan 7 briefs puntuales de B2 (Metar contraste+modal+teclado, Nubes headings+contraste, Terremotos live region, Incendios RiskTimeline, Niebla VisibilityTimeline, LavarCoche contraste, Landing contraste) — uno por sesión.

---

## 2026-08-31 — Plan B Fase B3: Brief 1 aplicado — gate de `prefers-reduced-motion`

**Done:**
- Nuevo hook compartido `useReducedMotion()` (`hooks/useReducedMotion.ts`) — reactivo a cambios en caliente de la preferencia (a diferencia del `useMotionPreferences` congelado que ya existía en `App.tsx`), SSR-safe.
- `App.tsx`: `useMotionPreferences` ahora deriva `enableAnimations` del hook compartido en vez de duplicar el `matchMedia`; `enableHeavyEffects` (capacidad de hardware, no accesibilidad) sin tocar.
- `BorderGlow.tsx`/`.css`: con reduced-motion, no se monta el listener de `pointermove` ni el sweep al montar — se agrega clase `static-glow` que renderiza el glow a opacidad fija en el mismo color semántico (`--glow-color`), sin el wedge direccional del cursor. Cubre de un saque a `WeatherHero`/PrevisionClima, `LaundryDayCard`/TenderRopa, `SportBlock`/HacerDeporte y `CotaDeNieve`.
- `ElectricBorder.tsx`: con reduced-motion, no arranca el `requestAnimationFrame` ni se renderiza el canvas — las capas de glow estático (ya existentes, mismo color) quedan como fallback. Cubre `Terremotos` (3 instancias) y de paso `Volcanes` (su condicional a `alert_level` no se tocó, sigue intacto).
- 4 `animate-ping` sueltos (`PrevisionClima`, `LavarCoche`, `CotaDeNieve`, `Incendios`) migrados a `motion-safe:animate-ping` — mismo patrón que ya usaba bien `ScoreGauge` (Incendios, sin tocar). En los 4 casos ya había un punto sólido del mismo color debajo del ping, así que el significado se preserva sin animación.
- Fuera de alcance (queda para otro brief/sesión): los `animate-ping` de `Terremotos`, `Metar`, `Lluvias`, `Nubes` no forman parte del Brief 1.

**Files changed:**
- `apps/frontend/src/hooks/useReducedMotion.ts` — nuevo
- `apps/frontend/src/App.tsx`
- `apps/frontend/src/components/animated/BorderGlow.tsx`, `BorderGlow.css`
- `apps/frontend/src/components/animated/ElectricBorder.tsx`
- `apps/frontend/src/pages/{PrevisionClima,LavarCoche,CotaDeNieve,Incendios}.tsx`

**Tests:**
- `npx tsc -b --noEmit` (apps/frontend) → 0 errores (verificado por el agente y de forma independiente).
- `npx vite build` → OK, 2.05s, sin warnings nuevos, tamaños de bundle sin cambios llamativos.
- Verificación en navegador (dev server local): Terremotos carga sin errores de consola nuevos (los únicos errores son 502 del proxy a producción por falta de backend local corriendo, preexistente y no relacionado a este cambio). **No pude confirmar visualmente el glow animado en vivo** porque las páginas tocadas dependen de datos reales (backend local no levantado en esta sesión) — verificado por lectura de diff en cambio, no por QA visual completo.

**Next:**
1. Gate de commit del proyecto (tests verdes + código importante) ya se cumple — pendiente de confirmación del usuario para commitear y pushear.
2. Quedan 8 briefs de B2 por aplicar (Brief 2 compartido + 7 puntuales) — uno por sesión según la convención del proyecto.

---

## 2026-08-31 — Plan B Fase B2: briefs de diseño (`/impeccable shape`, sin código)

**Done:**
- Traducidos los 12 P1 de B1 (9 páginas afectadas: Landing, PrevisionClima, LavarCoche, Terremotos, Incendios, Niebla, Metar, Radar, Nubes) a 9 briefs de fix accionables en `docs/plans/plan-b2-shape-briefs-2026-08-31.md` (no commiteado, regla docs/).
- Consolidación clave: 2 briefs compartidos resuelven 5 pertenencias de página de un saque — Brief 1 (gate de `prefers-reduced-motion` reusable, cubre PrevisionClima + parte de LavarCoche + de paso 3 P2 en otras páginas) y Brief 2 (`aria-expanded` en los 5 acordeones, cubre Metar + Radar + parte de Nubes). Los otros 7 briefs son puntuales por página.
- No fue una interview de shape desde cero — el "qué"/"por qué" ya estaba resuelto por `PRODUCT.md` + el audit de B1 (ubicación, estándar violado, impacto); B2 fue traducir eso a scope/boundaries accionables para B3, marcando explícitamente qué NO tocar (ej. el `borderLeft` de severidad en Nubes, ya confirmado como uso legítimo).

**Files changed:**
- `docs/plans/plan-b2-shape-briefs-2026-08-31.md` — nuevo

**Tests:** N/A — solo briefs de diseño, sin cambios de código.

**Next:**
1. Confirmación del usuario sobre las decisiones asumidas marcadas en los briefs (ej. Brief 1: el estado reducido de movimiento usa el mismo color semántico, solo sin animación) antes de pasar a B3.
2. B3: aplicar los fixes, empezando por los 2 briefs compartidos (mayor cobertura por menor esfuerzo).

---

## 2026-08-31 — Plan B Fase B1: auditoría técnica de las 15 páginas (sin código)

**Done:**
- Corrido `impeccable detect` (mecánico) sobre `pages/` + `components/` → 4 hallazgos base.
- Delegado el audit manual a 3 agentes en paralelo (5 páginas c/u), checklist fusionado `/impeccable audit` + `/audit` (A11y, Performance, Theming, Responsive, Anti-Patterns), con contexto de `.impeccable.md` para no confundir dispositivos semánticos de severidad con "AI slop".
- Reporte consolidado escrito en `docs/plans/plan-b1-audit-2026-08-31.md` (no commiteado, regla docs/): Audit Health Score global 14.6/20 ("Bueno"), 0 P0 / 12 P1 / 35 P2 / 12 P3 en 15 páginas. Dimensión más floja: Accessibility (2.2/4) — contraste vía `opacity`, `prefers-reduced-motion` ignorado por casi toda animación de producto, timelines sin equivalente accesible, algunos interactivos sin semántica de teclado. Nada bloquea funcionalidad (0 P0).
- Patrones sistémicos identificados: (1) reduced-motion solo protege el shader decorativo de fondo, ninguna animación de producto lo respeta; (2) ~55+ colores hardcodeados que duplican tokens `--color-*` ya definidos (Lluvias.tsx es la única página 100% en tokens); (3) `aria-expanded` faltante en 5 acordeones; (4) touch targets <44px repetidos; (5) 2 timelines (Incendios, Niebla) con datos horarios solo en `title` hover-only; (6) el "glow de severidad" (`ElectricBorder`/`BorderGlow`) se aplica sin criterio uniforme entre páginas; (7) bug latente por violación de Rules of Hooks en `ModelBadge.tsx:102-108` (P2 hoy, riesgo de crash si algún día llega un `model` no tipado).

**Files changed:**
- `docs/plans/plan-b1-audit-2026-08-31.md` — nuevo, reporte completo

**Tests:** N/A — fase de solo lectura, sin cambios de código.

**Next:**
1. Usuario decide próxima fase: B2 (`/impeccable shape` sobre páginas con P0/P1 — ninguna con P0, así que B2 tomaría las 15 con al menos 1 P1: Metar, Nubes, Terremotos, Incendios, Niebla, LavarCoche, PrevisionClima, Landing) o directamente B3 (aplicar fixes, 1 página por sesión) empezando por los P1 de accesibilidad.
2. Recomendación propia: atacar A11y primero (mayor volumen de P1, mayor riesgo real para el usuario objetivo del producto) antes que Theming (alto volumen pero bajo riesgo).

---

## 2026-08-29 — Plan B: `/impeccable init` — PRODUCT.md creado

**Done:**
- Ubicado "Plan B" en `docs/plans/auditoria-2026-08-28.md` (sección 6, `/impeccable` + `/audit`, 5 fases). El usuario pidió solo el paso `init` de esa suite (no B1-B5).
- Confirmada la dedup de `.impeccable.md` ya resuelta (raíz = fuente de verdad, sesión previa de housekeeping).
- Corrida `node context.mjs` del skill `impeccable` → confirmó `NO_PRODUCT_MD`, sin `DESIGN.md`.
- **Discrepancia real encontrada y resuelta con el usuario**: `README.md`/`CLAUDE.md` (raíz) describen un sistema narrativo de tarjetas por fenómeno (prompt de imagen + "cómo se ve/qué significa/acción"), pero la app en vivo (`Landing.tsx`, 15 páginas) es un dashboard cuantitativo con datos reales de SMN/GFS/ECMWF/USGS/EMSC/CheckWX — no hay generación dinámica de contenido en el backend. Confirmado con el usuario: **ambos son producto activo** (el dashboard + la dirección narrativa, hoy materializada como catálogo estático en Nubes/Desastres). También confirmado: sin evidencia de uso real todavía (no inventar métricas/testimonios).
- `PRODUCT.md` creado en la raíz del proyecto siguiendo el schema `impeccable:product-schema 1`: Platform, Users, Product Purpose, Positioning, Operating Context, Capabilities and Constraints, Brand Commitments, Evidence on Hand, Product Principles. `## Stack` omitido (codebase existente ya lo responde: React 19+Vite+TanStack Query+Tailwind v4 / FastAPI 0.136.1). `## Accessibility & Inclusion` omitido (sin requisito confirmado).
- Sin generación de imágenes disponible en este harness → `buildPath` no aplica, no se preguntó ni se escribió `.impeccable/config.json`. Live mode no configurado — fuera de alcance del pedido ("solo el init por ahora").

**Files changed:**
- `PRODUCT.md` — nuevo

**Tests:** N/A — solo documentación de producto, sin cambios de código.

**Next:**
1. Alcance de la próxima sesión: seguir con B1 (`/impeccable audit` + `/audit` sobre las 15 páginas) si el usuario lo prioriza, u otra rama (Plan A P2/P3 pendientes, commit+push de Terremotos).
2. `PRODUCT.md` es nuevo — decidir si se commitea (repo público, mismo criterio que otros archivos internos: preguntar antes).

---

## 2026-08-28 — Refactor Terremotos: polling 60s, sync badge, mobile cards, Google Maps

**Done:**
- Corregidas 2 premisas incorrectas del brief del usuario antes de implementar: no hay WebSocket en el frontend (todo ya es TanStack Query), y `distance_km` no es "distancia a Salta" — es dinámico, calculado por el backend contra la ubicación real del usuario. Confirmado con `grep` antes de tocar nada.
- `useEarthquakes`: `refetchInterval: 60_000` (60s, no 30s — confirmado con el usuario porque 30s desalinearía con el TTL backend de 300s, mismo antipatrón de la Fase 1).
- Badge "Sincronizado hace Xs" (tick en vivo cada 1s) + botón de refresco manual con spinner.
- Link a Google Maps por evento (`?q=lat,lon`) — icono en tabla desktop, botón táctil 44px en tarjetas mobile.
- Profundidad reformateada: "Profundidad: X km (desde la superficie)".
- **Bug real confirmado**: `depth_km`/`distance_km` tenían `hidden sm:table-cell` — desaparecían completamente en mobile (<640px). Fix: tabla solo en `hidden sm:block` (DataTable, usado solo en esta página) + nuevo layout de tarjetas `flex-col` para mobile con todo visible sin truncar.
- Probado en navegador real: dev server local + backend local (`.venv/Scripts/python.exe -m uvicorn`), viewports 375px y 800px — confirmado visualmente. El proxy de Vite a producción falla por CORS (solo permite el origen de Vercel), por eso se usó el backend local en vez de apuntar `.env.local` a Render.
- Creado `.claude/launch.json` para poder usar `preview_start` con el frontend en sesiones futuras.
- Cruzado con Plan B en el reporte de auditoría: el hallazgo de columnas ocultas en mobile es un caso de referencia para la fase B1 (audit) del `/impeccable`.

**Files changed:**
- `apps/frontend/src/hooks/useWeather.ts` — `refetchInterval` en `useEarthquakes`
- `apps/frontend/src/pages/Terremotos.tsx` — badge sync, refresh, Maps links, mobile cards, fix columnas ocultas
- `.claude/launch.json` — nuevo, config de dev server
- `docs/plans/auditoria-2026-08-28.md` — sección nueva (no commiteado, regla docs/)

**Tests:**
- `tsc --noEmit` → 0 errores. `vite build` → OK.
- Backend no tocado — sin cambios de tests.
- Verificación manual en navegador (mobile + desktop) — ver arriba.

**Next:**
1. Commitear y pushear — pendiente.
2. `.env.local` local quedó con un comentario no-op (gitignorado, no afecta nada).

---

## 2026-08-28 — P2/P3 de Fase 3 cerrados (6 de 7), pendiente commit+push

**Done:**
- **#3 (P2)** 429 con info real: `ApiError.retryAfter` capturado del header `Retry-After`; `request()` en `api.ts` agrega "Reintentá en Ns." al mensaje.
- **#4 (P2) — deliberadamente NO corregido.** `/api/metar` sin contrato Pydantic: poner `response_model` estricto sobre un passthrough de CheckWX en producción sin corpus real de respuestas es más riesgo (podría rechazar con 500 una respuesta válida) que beneficio. Necesita datos reales primero, queda como iniciativa aparte.
- **#5 (P2) — arreglo parcial.** `forecast_source` agregado a la interface TS de `WeatherDashboardResponse` (cierra la deriva de contrato). No toqué `pageModel()` en `PrevisionClima.tsx` — el badge `'mixed'` ya significa otra cosa (SMN+GFS actual, no Windy+OM del forecast); redefinir esa semántica es decisión de producto, no bug mecánico.
- **#6 (P2)** `stale` propagado a `/api/weather/dashboard`: `CurrentDetailedSchema.stale` (backend) + `CurrentDetailed.stale?` (frontend) + `stale=current.meta.stale` en el router. Test nuevo `test_dashboard_current_stale_flag_propagates`.
- **#7 (P2)** Sin reintentos sobre 4xx: nuevo `isClientError()` en `useWeather.ts`, aplicado en `COLD_START_RETRY` y en el `retry` default global de `App.tsx`.
- **#8 (P3)** `source` agregado a `SnowLevelResponse`/`CarWashForecastResponse` en `api.ts` (solo tipo, sin UI).
- **#9 (P3)** `Niebla.tsx VisibilityBlock` muestra `error.message` real en vez de texto hardcodeado.

**Files changed:**
- `apps/backend/app/schemas/weather.py` — `CurrentDetailedSchema.stale`
- `apps/backend/app/routers/weather.py` — `stale=current.meta.stale`
- `apps/backend/tests/test_dashboard_integration.py` — test nuevo de regresión
- `apps/frontend/src/lib/api.ts` — `ApiError.retryAfter`, `forecast_source`, `stale`, 2× `source`
- `apps/frontend/src/hooks/useWeather.ts` — `isClientError()`, `COLD_START_RETRY` actualizado
- `apps/frontend/src/App.tsx` — `retry` default usa `isClientError()`
- `apps/frontend/src/pages/Niebla.tsx` — `error.message` real
- `docs/plans/auditoria-2026-08-28.md` — Fase 3 P2/P3 marcados (no commiteado, regla docs/)

**Tests:**
- Backend: `.venv/Scripts/python.exe -m pytest -q` → **742 passed** (741 + 1 nuevo), 0 failed
- Frontend: `tsc --noEmit` → 0 errores. `vite build` → OK, 1.98s

**Next:**
1. Commitear y pushear — incluye también el fix del bug en vivo de `PrevisionClima.tsx` (aviso "despertando" pegado) de la entrada anterior. Pedido explícito del usuario, pendiente de ejecutar.
2. #4 (contrato `/api/metar`) y la semántica del badge de `forecast_source` quedan como iniciativas separadas si se priorizan.

---

## 2026-08-28 — Bug en vivo: aviso "despertando" queda pegado para siempre (PrevisionClima)

**Done:**
- Usuario reportó `/prevision` mostrando "El servicio está despertando" por 10+ minutos. Verificado con curl directo: backend sano (`/health` 200 en 0.7s, `/api/weather/dashboard` con datos reales en 1.2s) — el problema era 100% frontend, no una caída real.
- **Causa raíz**: `PrevisionClima.tsx` calculaba `isWakingUp = !data && failureCount > 0 && isColdStart(failureReason)`. `failureCount`/`failureReason` de TanStack Query solo se resetean al tener éxito, NUNCA al agotar los reintentos — así que si los 4 reintentos de cold-start (`COLD_START_RETRY`, hasta ~50s) fallan, la query queda en estado `error` para siempre pero `isWakingUp` sigue en `true`. Eso suprime el bloque `{error && !isWakingUp && <ErrorMessage/>}` — el aviso de "despertando" queda pegado sin salida, sin mostrar nunca el mensaje de error ya escrito ("Recargá la página en unos segundos"), y sin ninguna forma de recuperarse salvo recargar manualmente.
- Probablemente disparado por la ventana real de downtime durante el redeploy de Render de hace un rato (cambio de credenciales de Upstash) — el backend tardó más que la ventana de reintentos, la tab quedó atrapada en el estado roto y nunca se reintentó sola (`refetchOnWindowFocus: false`).
- **Fix**: agregado `isFetching` a la condición (`!data && isFetching && failureCount > 0 && isColdStart(failureReason)`) — una vez que los reintentos se agotan, `isFetching` pasa a `false` y el flujo cae naturalmente al `ErrorMessage` ya existente.

**Files changed:**
- `apps/frontend/src/pages/PrevisionClima.tsx`

**Tests:**
- `tsc --noEmit` → 0 errores
- `vite build` → OK, 14.28s

**Next:**
1. Commitear y pushear — pendiente confirmación (bug en vivo, prioridad alta, pero no se pushea sin pedido explícito).
2. Seguir con el resto de los P2/P3 de la Fase 3 documentados.

---

## 2026-08-28 — Confirmado: Upstash reconectado, Plan A cerrado end-to-end

**Done:**
- Usuario confirmó log de arranque de Render: `checkwx_counter=redis` — las credenciales nuevas de Upstash cargaron bien, el gate de cuota y el contador de la Fase 2 vuelven a persistir en Redis (no en modo degradado `MemoryCounter`).
- Con esto, **Plan A queda 100% cerrado**: las 4 fases hechas, verificadas y confirmadas, incluyendo el hallazgo imprevisto de la base Upstash borrada (que a su vez explicó el Incidente B de Sentry de una sesión anterior).

**Files changed:**
- `docs/plans/auditoria-2026-08-28.md` — confirmación final agregada (no commiteado, regla docs/)

**Tests:** N/A — confirmación operativa vía logs, sin cambios de código.

**Next:**
1. Riesgo sin resolver, no urgente: Upstash free vuelve a borrar la base tras 14 días de inactividad — considerar upgrade a plan pago o heartbeat periódico.
2. P2/P3 de Fase 3 sin corregir (documentados): 429 sin `Retry-After`, `/api/metar` sin contrato Pydantic, `forecast_source`/`stale` no propagados, campos `source` faltantes, mensaje hardcodeado en Niebla.
3. Plan B (`/impeccable`, 5 fases) disponible como próximo bloque si se prioriza.

---

## 2026-08-28 — Hallazgo real de Fase 4 punto 12: base de Upstash borrada por inactividad

**Done:**
- Al chequear el counter de CheckWX en Upstash (punto 12, delegado al usuario), encontró la base `skypulse-checkwx` (AWS us-east-1) en estado `DELETED` — borrado automático por 14 días de inactividad (plan free de Upstash).
- **Explica retroactivamente el Incidente B de Sentry** (cerrado hoy más temprano con el fix fail-open de `UpstashRedis`/`RedisCounter`) — los `ConnectError: Name or service not known` no eran un blip transitorio, la base ya no existía.
- Intento de `Restore` en Upstash falló ("No Databases Available") — exige crear la base destino primero. Decidido no restaurar: los datos son solo contadores de cuota, desechables.
- Usuario creó base Upstash nueva, actualizó `UPSTASH_REDIS_REST_URL`/`UPSTASH_REDIS_REST_TOKEN` en Render, redeploy en curso al cierre de esta sesión.

**Files changed:**
- `docs/plans/auditoria-2026-08-28.md` — Fase 4 punto 12 actualizado con el hallazgo real (no commiteado, regla docs/)

**Tests:** N/A — incidente operativo/infra, sin cambios de código.

**Next:**
1. **Verificar en el próximo arranque de sesión o pedirle al usuario**: buscar en logs de Render la línea `checkwx_counter=redis` (`main.py:76`) — confirma que las credenciales nuevas cargaron. Si aparece `checkwx_counter=memory` (`main.py:79`), el redeploy no tomó las env vars nuevas.
2. Riesgo a futuro sin resolver: Upstash free vuelve a borrar la base tras 14 días de inactividad. Opciones no implementadas: upgrade a plan pago, o heartbeat periódico — pendiente de decisión del usuario, no urgente.
3. Con esto, Plan A queda completo (Fases 1-4) salvo esta confirmación pendiente de logs.

---

## 2026-08-28 — Plan A Fase 4: cierre del P0 — Plan A completo (Fases 1-4)

**Done:**
- Punto 11 (destino de `apps/frontend/api/metar.js`): ya estaba resuelto antes de esta sesión — camino (a) recomendado, ejecutado en `94cd6e6` de una sesión previa (lambda borrada, `Metar.tsx` usa `BASE_URL`). Confirmado HOY que está en producción: Vercel API muestra el último deployment `READY`/production como exactamente el commit `8036d6b` (que incluye `94cd6e6` en su historia). Verificación en vivo: `GET https://skypulse-ar.vercel.app/api/metar?icao=SAEZ` → 200 `text/html` (fallback SPA, no la lambda) — confirma que no queda ningún resto del bypass.
- Punto 12 (re-verificar counter CheckWX): delegado al usuario — no tengo acceso a Upstash/Render desde esta sesión. Key a chequear: `skypulse:checkwx:counter:2026-08-28`.
- **Plan A completo**: Fase 1 (mapa de consumo), Fase 2 (instrumentación mínima), Fase 3 (auditoría de contrato + 2 P1 corregidos), Fase 4 (cierre del P0, ya resuelto + confirmado en producción esta sesión).

**Files changed:**
- `docs/plans/auditoria-2026-08-28.md` — Fase 4 marcada cerrada (no commiteado, regla docs/)

**Tests:** N/A — verificación vía Vercel API + curl en vivo, sin cambios de código.

**Next:**
1. Usuario chequea Upstash para confirmar el counter (punto 12) cuando pueda.
2. P2/P3 restantes de Fase 3 (429 sin `Retry-After`, `/api/metar` sin contrato Pydantic, `forecast_source`/`stale` no propagados, campos `source` faltantes, mensaje hardcodeado en Niebla) quedan documentados para otra sesión si se priorizan.
3. Plan B (`/impeccable`, 5 fases) sigue disponible como próximo bloque de trabajo si el usuario lo elige.

---

## 2026-08-28 — Plan A Fase 3: fix de los 2 P1 encontrados en la auditoría

**Done:**
- `apps/frontend/src/lib/api.ts`: nueva `extractErrorMessage()` con precedencia `message` (top-level) → `detail` (string) → `detail.message` (objeto anidado) → `error` (slowapi) → fallback `HTTP ${status}`. Corrige que `outside_argentina` (422) se mostrara como `"[object Object]"` — el backend manda `detail` como objeto, el código viejo lo pasaba directo a `new Error()`. Efecto colateral: 429 ahora también muestra el texto real de slowapi (antes caía siempre al fallback genérico).
- `apps/frontend/src/pages/Metar.tsx`: `fetchTAF` ya no silencia errores (`if (!res.ok) return` + catch vacío) — nuevo estado `tafError`, seteado en ambos caminos de fallo, reseteado en cada nueva búsqueda. `MetarResult` muestra una nota de tono bajo cuando el TAF falló, distinta del caso legítimo "sin TAF vigente para este aeródromo" (no marcado como error).

**Files changed:**
- `apps/frontend/src/lib/api.ts`
- `apps/frontend/src/pages/Metar.tsx`
- `docs/plans/auditoria-2026-08-28.md` — Fase 3 fixes documentados (no commiteado, regla docs/)

**Tests:**
- `./node_modules/.bin/tsc --noEmit` (apps/frontend) → 0 errores
- `./node_modules/.bin/vite build` (apps/frontend) → OK, 17.68s, sin warnings nuevos
- Backend no tocado — suite de Python sin cambios (sigue en 741 passed de la Fase 2)

**Next:**
1. Fase 4 sigue bloqueada por decisión pendiente (§7 punto 3 del reporte): destino de `apps/frontend/api/metar.js`.
2. P2/P3 restantes de la Fase 3 (429 sin `Retry-After` leído, `/api/metar` sin contrato Pydantic, `forecast_source`/`stale` no propagados, campos `source` faltantes, mensaje hardcodeado en Niebla) quedan documentados para otra sesión si el usuario los prioriza.
3. Nada de esto está commiteado.

---

## 2026-08-28 — Plan A Fase 3: auditoría de contrato front↔back (sin código)

**Done:**
- Contraste campo por campo de 8 endpoints con schema Pydantic vs interfaces TS de `apps/frontend/src/lib/api.ts`. 7/8 alineados. Discrepancias: `WeatherCurrentResponse` (lat/lon/weather_code/observed_at faltan en TS, hook no usado en ninguna página), `SnowLevelResponse`/`CarWashForecastResponse` (`source` faltante), `WeatherDashboardResponse` (`forecast_source` calculado por el backend pero nunca expuesto al frontend — el usuario no ve si el pronóstico 7d es mixto Windy+OM o solo OM fallback; `stale` tampoco se propaga a este endpoint aunque `aggregate_current()` ya lo calcula).
- `/api/metar` (CheckWX) confirmado sin ningún contrato Pydantic (`dict[str, Any]`, sin `response_model`) — el endpoint de mayor riesgo estructural del sistema.
- **2 bugs P1 reales encontrados en manejo de errores** (no corregidos, quedan para aprobación explícita — regla del proyecto de no tocar código en fases de auditoría):
  1. `outside_argentina` (422) se muestra al usuario como `"[object Object]"` literal — `api.ts:25` hace `body.detail ?? fallback` sin validar que `detail` sea string; el backend manda un objeto. Afecta 10/11 endpoints geolocalizados.
  2. `Metar.tsx → fetchTAF` silencia errores por completo (`if (!res.ok) return` + catch vacío) — sin feedback visible si el TAF falla.
- 5 hallazgos P2 (429 sin mensaje útil, `/api/metar` sin contrato, `forecast_source`/`stale` no propagados, reintento inútil sobre 422) y 2 P3 (campos `source` faltantes, mensaje hardcodeado en Niebla) documentados con severidad en el reporte.

**Files changed:**
- `docs/plans/auditoria-2026-08-28.md` — sección Fase 3 completada (no commiteado, regla docs/)

**Tests:** N/A — fase de solo lectura, sin cambios de código.

**Next:**
1. Usuario decide: ¿corregir los 2 P1 ahora (misma sesión, según regla del proyecto para bugs P1), o pasar a Fase 4?
2. Fase 4 sigue bloqueada por decisión pendiente (§7 punto 3 del reporte): destino de `apps/frontend/api/metar.js`.

---

## 2026-08-28 — Plan A Fase 2: instrumentación mínima (contador upstream + hit-rate)

**Done:**
- `RedisCounter` (`core/counter.py`) generalizado con `namespace: str = "checkwx"` — default retrocompatible, keys de cuota CheckWX sin cambios (verificado: `test_checkwx_counter.py` 23/23 verdes intacto).
- Nuevo `core/usage_counter.py`: `record(provider)` fire-and-forget (`asyncio.create_task` + `set()` module-level con `add_done_callback`, evita GC de la task en vuelo), fail-open ante Upstash caído, sin latencia agregada al camino de respuesta. `configure_redis()`/`configure_memory()` wireados en `main.py` lifespan (reusa el mismo objeto `UpstashRedis` que ya usa CheckWX).
- Instrumentados 8 puntos reales de fetch HTTP en 7 servicios: `smn`, `open_meteo` (7 puntos), `windy` (windy.py + fire_danger.py, mismo proveedor), `usgs`, `emsc`, `oavv` (por imagen), `metar_awc`. `checkwx.py` sin tocar (ya tiene su propio gate).
- `SingleFlightCache.stats()` nuevo (`core/cache.py`): `{hits, fetches, hit_rate}`, contadores dentro de los locks ya existentes.
- Sin endpoint nuevo — lectura manual vía Upstash Data Browser, mismo patrón que el contador de CheckWX.
- Trabajo delegado a un agente (python-pro) con diseño completo pre-resuelto; se cortó una vez por límite de sesión y se retomó con `SendMessage` sobre el mismo `agentId` sin perder contexto ni rehacer trabajo.

**Files changed:**
- `apps/backend/app/core/cache.py`, `counter.py`, `main.py`
- `apps/backend/app/services/{emsc,fire_danger,metar,oavv,openmeteo,smn,usgs,windy}.py`
- `apps/backend/app/core/usage_counter.py` — nuevo
- `apps/backend/tests/test_usage_counter.py`, `test_metar_service.py` — nuevos
- `apps/backend/tests/{test_emsc,test_fire_danger,test_oavv,test_openmeteo,test_openmeteo_cache,test_smn,test_usgs,test_windy}.py` — aserciones agregadas
- `docs/plans/auditoria-2026-08-28.md` — Fase 2 marcada hecha (no commiteado, regla docs/)

**Tests:**
- `.venv/Scripts/python.exe -m pytest -q` (apps/backend) → **741 passed**, 0 failed (baseline 725) — corrido por el agente y verificado de forma independiente.

**Next:**
1. Usuario decide si sigue con Fase 3 (contrato front↔back) en otra sesión, según regla de una fase por sesión.
2. Fase 4 sigue bloqueada por decisión pendiente (§7 punto 3 del reporte): destino de `apps/frontend/api/metar.js`.
3. Nada de esto está commiteado — 11 archivos modificados + 3 nuevos en el working tree.

---

## 2026-08-28 — Plan A Fase 1: mapa de consumo de API (estático, sin código)

**Done:**
- Mapeo completo backend (7 routers × 13 servicios) y frontend (15 páginas × 12 hooks TanStack Query) vía 2 agentes Explore en paralelo, cruzado a mano contra TTLs de caché.
- Tabla página→hook→endpoint→fuentes upstream→TTL backend→`staleTime` frontend en `docs/plans/auditoria-2026-08-28.md` (sección "Fase 1").
- **5 de 10 páginas con datos desalineadas** (`staleTime` menor al TTL backend real): TenderRopa, LavarCoche, HacerDeporte, CotaDeNieve (parcial), Niebla — refetch hacia Render que siempre pega caché, sin traer dato más fresco.
- Confirmado: `/api/weather/dashboard` y `/api/niebla` "gather de 5/4 fuentes" son en realidad 3 proveedores reales cada uno (Windy y Open-Meteo comparten una sola llamada HTTP cacheada detrás de varios branches del gather).
- Hallazgos extra registrados (no corregidos, quedan para otra fase/sesión): solo `openmeteo.py` usa `SingleFlightCache`+stale-cache (el resto de servicios no tiene fallback ante fallo upstream); 3 hooks/endpoints huérfanos sin consumidor (`useWeatherCurrent`, `useTenderRopa`, `useSensacionTermica`); `Metar.tsx` sin ningún control de caché de cliente; `Niebla.tsx→TafExpandCard` hace fetch imperativo fuera de `useQuery`; `settings.cache_ttl_fire_seconds` es config muerta; `fire_danger.py` sin dedupe single-flight.
- Corrección al reporte original: son 15 páginas, no 14.

**Files changed:**
- `docs/plans/auditoria-2026-08-28.md` — sección Fase 1 completada (no commiteado, regla docs/)

**Tests:** N/A — fase de solo lectura, sin cambios de código.

**Next:**
1. Usuario decide si sigue con Fase 2 (instrumentación) en otra sesión, según regla de una fase por sesión.
2. Fase 4 sigue bloqueada por decisión pendiente (§7 punto 3 del reporte): destino de `apps/frontend/api/metar.js`.

---

## 2026-08-28 — Housekeeping + Sentry desbloqueado + fix Upstash fail-open

**Done:**
- Housekeeping: duplicado `.impeccable.md` resuelto (raíz = fuente de verdad), draft viejo `test_wind_utils.py` ya no existía (scratchpad limpiado solo). `CHECKWX_KEY` borrada de Vercel (usuario).
- **Regla nueva confirmada por el usuario:** nunca commitear `CLAUDE.md`/`PROGRESS.md`/`.impeccable.md` (raíz) sin pedido explícito — repo público. Un commit de housekeeping se hizo sin preguntar y se deshizo (`git reset HEAD~1`, no estaba pusheado).
- Sentry conectado vía `/mcp` interactivo (org `ajconsultingit`, proyecto `skypulse-backend`). 4 issues `unresolved` = 2 incidentes reales:
  - **Incidente A** (P1, sin cerrar): cascada "ambas fuentes no disponibles" en `/api/weather/dashboard` — Open-Meteo `resource_exhausted` (rate limit) + SMN caído a la vez. 34 occurrences desde 2026-06-05, activo.
  - **Incidente B** (P1, **cerrado esta sesión**): `/api/metar` caía con 500 no manejado si Upstash fallaba DNS/timeout.
- **Fix Incidente B:** `UpstashRedis._call()` (`upstash.py`) captura `httpx.HTTPError` → `UpstashUnavailableError`. `RedisCounter` (`counter.py`) degrada por método: `get`→0 (fail-open del gate), `incr`→0 (no pierde la respuesta CheckWX ya pagada), `alert_already_sent`→True (fail-safe, no floodea alertas), `mark_alert_sent`→swallow+log.
- 4 tests nuevos (C6) en `test_checkwx_counter.py` simulan `httpx.ConnectError` vía `respx`.
- `docs/plans/auditoria-2026-08-28.md` actualizado: sección 4 (Sentry) con diagnóstico completo, Plan A Fase 0/0.5 marcadas hechas.

**Files changed:**
- `apps/backend/app/core/upstash.py` — `UpstashUnavailableError` + try/except en `_call()`
- `apps/backend/app/core/counter.py` — `RedisCounter` degrada en las 4 operaciones
- `apps/backend/tests/test_checkwx_counter.py` — sección C6, 4 tests nuevos
- `docs/plans/auditoria-2026-08-28.md` — no commiteado (regla docs/)

**Tests:**
- `.venv/Scripts/python.exe -m pytest -q` (desde `apps/backend/`, venv vive ahí no en la raíz) → **721 passed**, 0 failed

**Next:**
1. ✅ Fix Upstash (0.5a) commiteado y pusheado: `fed183c`.
2. ✅ Incidente A (0.5b) cerrado — ver entrada siguiente.
3. Vercel Web Analytics sigue en 404 (rama sin mergear).
4. Working tree docs/ sigue sucio intencionalmente (regla del proyecto).
5. Plan A: quedan Fase 1 (mapa de consumo estático), Fase 2 (instrumentación), Fase 3 (contrato front↔back) — no arrancadas, alcance para otra sesión.

---

## 2026-08-28 — Plan A: cierre Incidente A (cascada Open-Meteo rate limit) — stale-while-error

**Done:**
- Diagnóstico: `fetch_with_retry` ya reintentaba 429/5xx; el hueco real era `SingleFlightCache` — al fallar el fetch (tras agotar retries) cacheaba `None` por 15s sin memoria del último valor bueno. Si Open-Meteo rate-limitea justo al vencer el TTL (600s) Y SMN también falla → 503 directo, aunque hubiera datos válidos minutos antes.
- Decisión confirmada con el usuario: (1) fix cache-wide en `SingleFlightCache`, no solo en `openmeteo.get_current()`; (2) exponer `stale` al frontend, no ocultarlo.
- `core/cache.py`: nuevo `_stale_cache` (TTLCache, `stale_ttl = ttl × 6` por defecto) que guarda el último resultado exitoso por clave. En fallo (excepción o `None`), sirve ese valor en vez de `None`/propagar. Las 3 instancias de `SingleFlightCache` en `openmeteo.py` (8 fetchers) heredan el comportamiento sin cambios propios.
- `weather_aggregator.py`: `SourceMeta.fetched_at` ahora usa `om.fetched_at` real (antes usaba `now` del aggregator, mentía sobre la frescura del dato servido desde el fallback). Nuevo campo `SourceMeta.stale` (`bool`, umbral 15 min, desacoplado del TTL interno del caché).
- `schemas/weather.py` + `apps/frontend/src/lib/api.ts`: campo `stale` agregado al contrato.
- 6 tests nuevos: 2 en `test_openmeteo_cache.py` (stale sirve el objeto exacto tras TTL vencido + sin stale previo sigue devolviendo `None`), 2 en `test_weather_aggregator.py` (`meta.stale` true/false según edad), tests existentes sin tocar (siguen pasando igual).

**Files changed:**
- `apps/backend/app/core/cache.py` — `_stale_cache` + fallback en `get_or_fetch()`
- `apps/backend/app/services/weather_aggregator.py` — `fetched_at` real + campo `stale`
- `apps/backend/app/schemas/weather.py` — `SourceMeta.stale: bool`
- `apps/frontend/src/lib/api.ts` — `meta.stale: boolean`
- `apps/backend/tests/test_openmeteo_cache.py`, `test_weather_aggregator.py` — 6 tests nuevos
- `docs/plans/auditoria-2026-08-28.md` — Fase 0.5b marcada hecha (no commiteado, regla docs/)

**Tests:**
- `.venv/Scripts/python.exe -m pytest -q` (apps/backend) → **725 passed**, 0 failed
- `./node_modules/.bin/tsc --noEmit` (apps/frontend — corepack pnpm roto, usar binario directo) → 0 errores

**Next:**
1. Commitear y pushear (pendiente confirmación explícita — no commitear sin pedido).
2. Con esto, Plan A Fase 0 + 0.5 quedan cerradas. Fases 1–4 (mapa de consumo, instrumentación, contrato front↔back, Web Analytics) quedan para otra sesión.

---

## 2026-08-28 — Auditoría full-stack + sync de deploy + cierre P0 CheckWX

**Contexto:** primer contacto de la sesión con el repo. Se pidió sumarizar
estado (repo + Sentry + deploy Vercel), auditar consumo de API, y plan de
uso de `/impeccable`. Reporte completo en
`docs/plans/auditoria-2026-08-28.md` (sin commitear — vive solo en local,
por la regla de este proyecto de no commitear `docs/` sin pedido explícito).

**Done:**
- Auditoría completa del repo: mapa de servicios backend (13), routers (7),
  páginas frontend (14), fuentes externas (SMN/Open-Meteo/Windy/USGS/EMSC/
  OAVV/CheckWX) con TTLs de caché.
- **P0 encontrado y CERRADO:** `Metar.tsx` llamaba `fetch('/api/metar')` con
  path relativo → resolvía contra la lambda `apps/frontend/api/metar.js`
  (bypasea CheckWX directo), NO contra el backend FastAPI. Se saltaba gate
  de cuota (198/mes), caché TTL, counter Upstash y alertas Sentry. Fix:
  `Metar.tsx` ahora usa `BASE_URL` (`VITE_API_BASE_URL`, ya seteada en
  Vercel), lambda bypass eliminada.
- **Deploy sincronizado:** local `main` estaba 43 commits atrás de
  `origin/main`, y producción corría una rama (`claude/sumariza-Jss0p`) con
  2 commits que nunca se mergearon a `main`. Fast-forward limpio
  (`git merge --ff-only`), sin conflictos — la rama desplegada era subset
  de main + 2 commits.
- Working tree local sucio (legado `src/*.html`, `openspec/` sin trackear)
  → commiteado. `test_wind_utils.py` local resultó ser un DRAFT VIEJO,
  superado por una versión mejor que ya trajo el merge (commit `aa07a5d`)
  → se movió a scratchpad en vez de commitearse encima.
- Verificado antes de pushear: `pnpm run build` (tsc + vite) limpio,
  backend `pytest` (via `.venv/Scripts/python.exe -m pytest`, NO es
  proyecto `uv` — usa `requirements-lock.txt`) → **717 passed**.
- Pusheado a `origin/main`: `a2ab92a..94cd6e6`.
- Servidor MCP de Sentry agregado (`claude mcp add --transport http sentry
  https://mcp.sentry.dev/mcp`) — falta autenticar vía `/mcp` interactivo
  (esta sesión es no interactiva, no puede completar OAuth).

**Files changed (commits ya en `origin/main`):**
- `d2c0071` — borra `src/` legado (7 archivos) + agrega `openspec/config.yaml`
- `94cd6e6` — `apps/frontend/src/lib/api.ts` (export `BASE_URL`),
  `apps/frontend/src/pages/Metar.tsx` (fetch usa `BASE_URL`),
  elimina `apps/frontend/api/metar.js`

**Tests:**
- `pnpm run build` → OK, sin errores de tipos
- `.venv/Scripts/python.exe -m pytest -q` (apps/backend) → 717 passed, 0 failed

**Next (en orden, una cosa por sesión):**
1. **Vos:** correr `/mcp` en sesión interactiva, loguear Sentry, reiniciar
   sesión acá para que el MCP quede disponible.
2. Con Sentry legible → Fase 0 del Plan A: leer issues 7d/30d de
   `ajconsultingit`, agrupar por endpoint.
3. Decisión pendiente: ¿descartar el draft viejo de `test_wind_utils.py`
   parqueado en scratchpad, o revisarlo por si tiene algo útil?
4. Decisión pendiente: borrar `CHECKWX_KEY` de Vercel (env var huérfana,
   ya no la usa nada). `VITE_API_BASE_URL` se queda — es la que usa todo
   el resto del cliente.
5. Decisión pendiente: duplicado de `.impeccable.md` (raíz, borrado sin
   commitear, vs. `docs/plans/.impeccable.md`, sin trackear) — elegir una
   fuente de verdad de diseño antes de correr `/impeccable`.
6. Vercel Web Analytics sigue en 404 — rama `vercel/install-vercel-web-
   analytics-l5pf0e` nunca mergeada.
7. Elegir alcance de la próxima sesión: Plan A (auditoría de consumo de
   API, 4 fases) o Plan B (`/impeccable` + `/audit`, 5 fases) — ambos
   detallados en `docs/plans/auditoria-2026-08-28.md`.

---

## 2026-06-01 — METAR Observability Fase MVP: verificación end-to-end ✅

**Done:**
- Upstash Redis configurado en Render → `checkwx_counter=redis` confirmado en logs de startup
- Request real SAEZ → 200 con payload CheckWX completo
- Counter `skypulse:checkwx:counter:2026-06` en Upstash Data Browser confirmado
- `METAR_Observability.md` actualizado: Fase MVP 100% completa (checklist cerrado)

**Files changed:**
- `docs/plans/METAR_Observability.md` — checklist MVP cerrado, estado actualizado

**Tests:** sin cambios — 18 passed (suite METAR)

**Next:**
- Fase B: stale-fallback + single-flight (opcional — ahorra ~30% cuota)
- Fase C: cron Render monitor (detección pasiva cada 6h)
- Fase D: webhook Discord/Telegram (opcional)
- Awaiting user direction

---

## 2026-06-01 — METAR Observability Fase MVP: documentación cerrada + push

**Done:**
- `METAR_Observability.md` actualizado: estado → ✅ FASE MVP IMPLEMENTADA
- Tabla de estado de implementación (archivos creados, tests implementados vs. planificados)
- Verificación Sentry: SDK v2.61.0 confirmado, init solo en ENV=prod, push_scope() deprecado (funcional + noqa)
- Corrección de umbrales en el doc: 80%→159, 95%→189 (división entera `int(count*100/198)`)
- `render.yaml` + `METAR_Observability.md` commiteados y pusheados
- 18 tests del MVP verdes (S1×3, S4×2, N1×2, N2, N3, N4, tags, R1–R7)

**Files changed:**
- `apps/backend/render.yaml` — UPSTASH_REDIS_REST_URL y TOKEN agregados (faltaban)
- `docs/plans/METAR_Observability.md` — estado MVP ✅, checklist, Sentry audit, corrección umbrales

**Tests:**
- `uv run pytest test_checkwx_service.py test_checkwx_notifier.py test_metar_router.py -v`
- Result: **18 passed**, 0 failed

**Next:**
- Usuario debe: crear cuenta Upstash, obtener REST URL + TOKEN, setearlos en Render dashboard
- Fases B (stale + single-flight), C (cron Render), D (webhook) pendientes cuando el usuario lo decida

---

## 2026-06-01 — API_Prediction plan cerrado: drizzle fix + 9 tests nuevos

**Done:**
- `_build_rain_forecast()`: detección de llovizna por condiciones ambientales (humidity≥80 + cloud_cover≥70 → "Llovizna posible" / "media"; Windy slot averages hum≥75+cloud≥80 también activan)
- `confidence_label` ya no es hardcodeado a "alta" — varía según condiciones
- 6 tests unitarios de drizzle (D1–D6): todos los escenarios de umbral cubiertos
- 3 tests de integración del plan API_Prediction §6.3 (IT1–IT3): precip_prob, temp_max tolerancia, no-all-zero
- `docs/plans/API_Prediction.md` actualizado: estado ✅ IMPLEMENTADO, checklist completo

**Files changed:**
- `apps/backend/app/routers/weather.py` — drizzle risk detection en `_build_rain_forecast()`
- `apps/backend/tests/test_rain_forecast_drizzle.py` — **nuevo**, 6 tests D1–D6
- `apps/backend/tests/test_dashboard_integration.py` — **nuevo**, 3 tests IT1–IT3
- `docs/plans/API_Prediction.md` — status cerrado, checklist actualizado

**Tests:**
- `uv run pytest --tb=short -q` → **603 passed**, 0 failed

**Next:**
- Awaiting user direction (PR 4 Observabilidad o nueva feature)

---

## 2026-06-01 — LavarCoche.tsx pulido visual (escala aptitud + humedad int + colores labels)

**Done:**
- `QualityScaleBar`: segmentos inactivos usan `opacity: 0.55` uniforme (todos en su color real, sin distinción activo/inactivo). Fix perceptual: verde no aparece más brillante que el resto.
- Labels de la escala: todos muestran su color (`q.color`) en lugar de solo el activo. Best day sigue en negrita.
- Humedad en `DayRow`: `{day.humidity}%` → `{Math.round(day.humidity)}%` (entero, sin decimales).
- "No apto" color: `#9b2020` → `#b91c1c` (visible a 25% opacidad en versión anterior, ahora irrelevante por cambio de diseño).

**Files changed:**
- `apps/frontend/src/pages/LavarCoche.tsx` — 4 commits de pulido visual

**Tests:**
- `pnpm exec tsc --noEmit` → 0 errores

**Commits:** `eccb54c` → `d325813` → `9ac1581` → `044a4f9` → `a4c6c0d` · **Push:** ✅ origin/main

**Next:**
- Awaiting user direction

---

## 2026-06-01 — score_lavar_coche veto humedad + distinción visual Regular/No apto

**Done:**
- `score_lavar_coche`: penalties de humedad aumentados (>65→-8, >70→-18, >80→-30) + hard cap ≥70%→max 74 → nunca "Excelente" con humedad alta. Headline específico cuando humidity ≥80%.
- 10 tests nuevos en `TestLavarCoche` cubriendo caps y edge cases (0 tests previos existían).
- `LavarCoche.tsx`: `LABEL_COLOR` map con 4 colores distintos — "No apto" usa `#9b2020` (crimson) vs "Regular" `#e05545`. `QUALITY_SCALE`, badges y barra de score ahora derivan color de `LABEL_COLOR[day.label]`. `scoreInfo` agrega rama `score<30` con fondo más oscuro.

**Files changed:**
- `apps/backend/app/services/calculators.py` — `score_lavar_coche` veto humedad + headline
- `apps/backend/tests/test_calculators.py` — `TestLavarCoche` clase nueva (10 tests) + import
- `apps/frontend/src/pages/LavarCoche.tsx` — `LABEL_COLOR`, `QUALITY_SCALE`, `scoreInfo`, `DayRow`

**Tests:**
- `uv run pytest` → 581 passed, 0 failed
- `pnpm exec tsc --noEmit` → 0 errores

**Commit:** `6b4d92a` · **Push:** ✅ origin/main

**Next:**
- Awaiting user direction

---

## 2026-06-01 — Wave robustez completa + UI fixes + Tender Ropa veto

**Done:**
- Fix 2 (Option A): multi-modelo real `["gfs_seamless", "ecmwf_ifs025"]` en `get_multi_model_daily`; consenso ahora informa divergencia real
- Selector de modelo GFS/ECMWF/Consenso en Previsión: backend `?model=` param, frontend toggle en `Forecast7d.tsx`, estado en `PrevisionClima.tsx`
- Fix iconos horarios: `days=2→7` en `get_hourly_forecast_ext` — ya no muestra cielo despejado desde el miércoles
- 6 badge inconsistencies frontend: `confidenceColor()` util compartida en `lib/confidence.ts`, importada en Forecast7dCards/Table/Chart, RainForecastCard, SportBlock null-guard, LaundryDayCard null-guard + umbrales 70→75/45→50
- LavarCoche: QUALITY_SCALE 'Bueno' amarillo corregido a `#f0a030`
- Fog labels: backend `_classify_visibility` renombrado Niebla→Neblina (500m–1km) / Niebla densa→Niebla (<500m)
- Niebla.tsx: VISIBILITY_SCALE con campo `note`, explicación científica Bruma vs Neblina en FOG_TYPES
- Tender Ropa veto por humedad: ≥65% → 0 pts, ≥70% → cap 44 ("Regular" techo), ≥80% → cap 25 ("No apto"); headlines + reason actualizados

**Files changed:**
- `apps/backend/app/services/openmeteo.py` — Fix2: 2 modelos; fog labels renombrados
- `apps/backend/app/routers/weather.py` — `days=7`, `model` param, `_build_7d_forecast` selector
- `apps/backend/app/routers/niebla.py` — docstring fog labels
- `apps/backend/app/services/calculators.py` — Tender Ropa veto humedad + headlines
- `apps/backend/tests/test_calculators.py` — 3 tests renombrados/actualizados + 2 nuevos veto tests
- `apps/backend/tests/test_openmeteo_extended.py` — fog label tests renombrados, both-models test
- `apps/frontend/src/lib/confidence.ts` — nuevo util `confidenceColor()`
- `apps/frontend/src/lib/api.ts` — `weatherDashboard` acepta `model?`
- `apps/frontend/src/hooks/useWeather.ts` — `useWeatherDashboard` acepta `model`
- `apps/frontend/src/pages/PrevisionClima.tsx` — state `forecastModel`
- `apps/frontend/src/pages/Niebla.tsx` — VISIBILITY_SCALE notes + FOG_TYPES Bruma
- `apps/frontend/src/components/clima/Forecast7d.tsx` — toggle GFS/ECMWF/Consenso
- `apps/frontend/src/components/clima/Forecast7dCards.tsx`, `Table.tsx`, `Chart.tsx` — `confidenceColor` import
- `apps/frontend/src/components/clima/RainForecastCard.tsx`, `SportBlock.tsx` — null-guards
- `apps/frontend/src/components/ui/LaundryDayCard.tsx` — null-guard + umbrales
- `apps/frontend/src/pages/LavarCoche.tsx` — QUALITY_SCALE color fix
- `apps/frontend/src/components/ui/ModelBadge.tsx` — null-guard `!meta`

**Tests:**
- `uv run pytest` → 571 passed, 0 failed
- `pnpm exec tsc --noEmit` → 0 errores (verificado antes del commit)

**Commits:** `04a3116` (Fix2 + badges + fog + hourly) · `a41c22d` (iconos + selector + Tender Ropa veto)

**Next:**
- Pendientes menores — ver sección pendientes en PROGRESS.md

---

## 2026-06-01 — Fix 4c: fetch_with_retry helper + test suite fixes

**Done:**
- `fetch_with_retry` implementado en `http_client.py`: retry en 429/5xx/Timeout/TransportError, backoff exponencial ±25% jitter, respeto de Retry-After con cap
- `openmeteo.py`: todos los `_fetch()` internos migrados a `fetch_with_retry`
- Tests nuevos: `test_fetch_with_retry.py` (13 tests), incluye integración `get_current` 429→200
- Tests fixes: `test_openmeteo_extended.py` — `_mock_http_client` migrado a `client.request` + `status_code` como int; 6 tests de timeout actualizados

**Files changed:**
- `apps/backend/app/core/http_client.py` — `_backoff_delay` + `fetch_with_retry`, limits httpx
- `apps/backend/app/services/openmeteo.py` — todos los `_fetch()` usan `fetch_with_retry`
- `apps/backend/tests/test_fetch_with_retry.py` — nuevo (13 tests)
- `apps/backend/tests/test_openmeteo_extended.py` — `_mock_http_client` y 6 timeout tests adaptados

**Tests:**
- `uv run pytest` → 568 passed, 0 failed

**Next:**
- Fix 2 (pendiente decisión): multi-model Open-Meteo consensus (Option A: restaurar / Option B: simplificar)
- Badge inconsistencies (deferred): 6 issues identificados en cards del frontend

---

## 2026-05-30 — Fase 2 animated titles: RainText + ScanText

**Done:**
- `RainText.tsx`: letras caen rápido como gotas, stagger mínimo (lluvia simultánea), aplicado en Lluvias.tsx
- `ScanText.tsx`: letras se revelan L→R con flash verde radar, `animationFillMode:'both'` para que colapsen a opacity:0 al click y se revelen en secuencia, aplicado en Radar.tsx
- `index.css`: agregados @keyframes charRain, charScan
- Patrón custom header: h1 existente → `sr-only` (a11y preservada), div `aria-hidden` con componente animado al costado
- Roadmap actualizado: Lluvias ✅, Radar ✅

**Files changed:**
- `apps/frontend/src/index.css` — charRain + charScan keyframes
- `apps/frontend/src/components/animated/RainText.tsx` — nuevo
- `apps/frontend/src/components/animated/ScanText.tsx` — nuevo
- `apps/frontend/src/pages/Lluvias.tsx` — h1 sr-only + RainText
- `apps/frontend/src/pages/Radar.tsx` — h1 sr-only + ScanText

**Tests:**
- `pnpm exec tsc --noEmit` → 0 errores

**Next:**
- Fase 3 opcional: DriftText → Nubes

---

## 2026-05-30 — Fase 1 animated titles: MeltText + FogText + FrostText

**Done:**
- `MeltText.tsx`: letras se derriten hacia abajo como lava, stagger izquierda→derecha, aplicado en Volcanes.tsx
- `FogText.tsx`: letras se desvanecen con blur y deriva aleatoria (sin orden — la niebla no tiene dirección), aplicado en Niebla.tsx
- `FrostText.tsx`: letras tiemblan, se congelan en azul hielo y suben como vapor, stagger derecha→izquierda, aplicado en CotaDeNieve.tsx
- `index.css`: agregados @keyframes charMelt, charFog, charFrost
- Roadmap actualizado: Volcanes ✅, Niebla ✅, CotaDeNieve ✅

**Files changed:**
- `apps/frontend/src/index.css` — charMelt + charFog + charFrost keyframes
- `apps/frontend/src/components/animated/MeltText.tsx` — nuevo
- `apps/frontend/src/components/animated/FogText.tsx` — nuevo
- `apps/frontend/src/components/animated/FrostText.tsx` — nuevo
- `apps/frontend/src/pages/Volcanes.tsx` — titleNode MeltText
- `apps/frontend/src/pages/Niebla.tsx` — titleNode FogText
- `apps/frontend/src/pages/CotaDeNieve.tsx` — titleNode FrostText
- `docs/plans/animated-titles-roadmap.md` — estado actualizado

**Tests:**
- `pnpm exec tsc --noEmit` → 0 errores

**Next:**
- Fase 2: RainText (Lluvias) + ScanText (Radar) — headers editoriales custom, patrón diferente

---

## 2026-05-30 — ShatterText + BurnText: reemplazo matter-js + animación de fuego

**Done:**
- Reemplazado `FallingText` (matter-js ~90 kB gzip) por `ShatterText` (CSS puro): chunk Terremotos 98 kB → 12.6 kB (−87%)
- Eliminado `matter-js` y `@types/matter-js` del `package.json`
- Creado `BurnText.tsx`: letras individuales arden y suben como ceniza al hacer click (stagger izquierda→derecha)
- Extendido `PageHeader` con prop `titleNode?: ReactNode` (backwards-compatible, h1 queda sr-only para a11y)
- `Incendios.tsx` usa `BurnText` vía `titleNode`

**Files changed:**
- `apps/frontend/src/index.css` — @keyframes shatterFall + charBurn
- `apps/frontend/src/components/animated/ShatterText.tsx` — nuevo componente CSS-only
- `apps/frontend/src/components/animated/BurnText.tsx` — nuevo componente CSS-only
- `apps/frontend/src/components/animated/FallingText.tsx` — eliminado
- `apps/frontend/src/components/ui/PageHeader.tsx` — prop titleNode opcional
- `apps/frontend/src/pages/Terremotos.tsx` — FallingText → ShatterText
- `apps/frontend/src/pages/Incendios.tsx` — BurnText vía titleNode
- `apps/frontend/package.json` — removido matter-js + @types/matter-js

**Tests:**
- `pnpm exec tsc --noEmit` → 0 errores
- `pnpm build` → 0 errores, chunks verificados

**Next:**
- Awaiting user direction

---

## 2026-05-30 — S-15 bundle analysis + parsing.py coverage

**Done:**
- S-15: bundle analizado — critical path 318 kB raw / 101 kB gzip (sano); Terremotos 98 kB por matter-js (ya lazy-loaded, sin impacto en critical path); sin acción requerida
- utils/parsing.py: cobertura 75% → 100% con 6 tests parametrizados (cubre ValueError y TypeError branches)
- auditoria-seguridad.md: todos los ítems cerrados, resumen ejecutivo 65/65 (100%), doc actualizado

**Files changed:**
- `apps/backend/tests/test_parsing.py` — creado, 6 tests parametrizados
- `docs/plans/auditoria-seguridad.md` — resumen ejecutivo 100%, roadmap y mapa de archivos cerrados

**Tests:**
- `uv run pytest tests/` → 529 passed, 0 failed

**Next:**
- Awaiting user direction — auditoría completada al 100%

---

## 2026-05-29 — P3 token migration: hex → CSS vars

**Done:**
- Migré 28 hex literals directos a CSS vars en 15 archivos
- Excluídos correctamente: template literals, rgba(), gradients, datos en arrays, WMO colors, DANGER_COLORS, FOG_COLOR_OVERRIDE
- Build TypeScript limpio (0 errores)
- Commit `546f91e`: `refactor(tokens): migrate hex literals to CSS vars across 15 files`

**Files changed:**
- `components/clima/Forecast7dTable.tsx`, `HourlyStrip.tsx`, `RainForecastCard.tsx`, `SportBlock.tsx`
- `components/ui/ModelStatusBar.tsx`
- `pages/CotaDeNieve.tsx`, `Desastres.tsx`, `LavarCoche.tsx`, `Lluvias.tsx`, `Nubes.tsx`
- `pages/PrevisionClima.tsx`, `Radar.tsx`, `TenderRopa.tsx`, `Terremotos.tsx`, `Volcanes.tsx`

**Next:**
- Push a main (pendiente decisión usuario)
- Manual config pendiente: Vercel env vars VITE_SENTRY_DSN / SENTRY_AUTH_TOKEN / SENTRY_ORG · Render SENTRY_DSN
- GTM console: GA4 Config tag + Virtual Pageview trigger + GA4 Event SPA tag

---

## 2026-05-29 — P2 Desastres: reorganización card + empty state ✅

**Done:**
- `Desastres.tsx` — acción (`Acción`) movida de la última posición a justo después del DangerScale+badge — visible sin scroll para contenido safety-critical
- `Desastres.tsx` — empty state defensivo cuando `visible.length === 0`: emoji + mensaje centrado

**Files changed:**
- `apps/frontend/src/pages/Desastres.tsx`

**Tests:** `pnpm run build` → ✓ 1.48s ✅

**Next:**
- P3 restante: DANGER_COLORS hex no migrables (template literal `${activeColor}88` en glow)
- GTM/GA4/Sentry: `docs/plans/config-gtm-ga4-sentry.md` (sin empezar)
- P2 PrevisionClima: header antes de datos (polish opcional)

---

## 2026-05-29 — Fase 3 + P1 PrevisionClima + P3 tokens (paralelo) ✅

**Fase 3 — /bolder Nubes + Metar:**
- `DangerScale.tsx` — glow `boxShadow` en segmentos activos cuando `level >= 4`
- `Nubes.tsx` — hero callout `animate-ping` rojo cuando hay nubes `dangerLevel === 5` visibles; borde izquierdo 3px crit/warn en cards con dangerLevel 4-5
- `Metar.tsx` — hero callout `animate-ping` IFR (rojo) / LIFR (violeta `--color-fog`); LIFR CAT_STYLES corregido a `rgba(204,102,255,...)`

**P1 PrevisionClima — badge modelo durante fetch:**
- `modelBadge` en `PageHeader` ahora condicionado a `data ? ... : undefined` — no muestra `gfs` incorrecto durante carga

**P3 — 15 reemplazos de tokens semánticos:**
- `Lluvias.tsx` — 7 reemplazos: `BADGE_STYLES.{maybe,yes,heavy,crit}.color` + ping/dot/párrafo `animate-ping`
- `Desastres.tsx` — 5 reemplazos: `BADGE_STYLE.{crit,warn,watch}.color`, label "Acción", link fuente
- `Incendios.tsx` — 3 reemplazos: badge crítico, value span, badge fuente (ternario)
- Skipeados correctamente: template literals alfa, DANGER_COLORS (glow usa `${activeColor}88`), MagnitudeScaleBar gradientes, colores no semánticos

**Files changed:**
- `components/ui/DangerScale.tsx`
- `pages/Nubes.tsx`, `pages/Metar.tsx`, `pages/PrevisionClima.tsx`
- `pages/Lluvias.tsx`, `pages/Desastres.tsx`, `pages/Incendios.tsx`

**Tests:** `pnpm run build` → ✓ 1.47s ✅

**Next:**
- P2 Desastres: DangerScale enterrado bajo descripción + sin empty state para filtro vacío
- P3 restante: DANGER_COLORS (`activeColor` actualmente en template literal `${activeColor}88` de glow)
- Fase 3 Nubes/Metar: `/bolder` completado ✅

---

## 2026-05-29 — P1 Desastres.tsx — touch targets + color token ✅

- Filter bar: `py-1.5` → `py-3` (32px → ≥44px, WCAG AA touch targets)
- Description color: `rgba(226,232,240,.82)` → `var(--color-muted-foreground)`
- `tsc --noEmit` → 0 errores

**Next:** Fase 3 diferida (/bolder Nubes + Metar) · P1 PrevisionClima (badge modelo durante fetch) · P3 tokens 27 archivos

---

## 2026-05-29 — Fases 4 + 5 auditoría frontend (paralelo) ✅

**Fase 4 — PageHeader + UI/UX audit:**
- `Volcanes.tsx` → header hardcodeado reemplazado por `<PageHeader>` (import agregado, 25 líneas → 6 líneas)
- Auditoría `PrevisionClima.tsx`: P1 (badge modelo incorrecto durante fetch inicial), P2 (header fuera del skeleton), P3 (hex hardcodeado `#c8a84b`)
- Auditoría `Desastres.tsx`: P1 (filter bar 32px < 44px WCAG, color `rgba(226,232,240,.82)` fuera de tokens), P2 (DangerScale enterrado, sin empty state para filtro vacío), P3 (header sin comentario de excepción, imágenes sin crossOrigin)

**Fase 5 — Code quality:**
- `DangerScale.tsx` → runtime guard agregado (`import.meta.env.DEV`, correcto para Vite)
- `HourlyTimeline.tsx` → eliminado (0 imports, sucesor es `HourlyStrip`)
- `IntensityScaleBar` → sin `activeLevel` (página educativa estática, sin datos en tiempo real)
- Auditoría tokens P3: 27 archivos con hex literales candidatos a `var(--color-*)` (no urgente)

**Fase 3 → diferida** (hero callouts Nubes + Metar — /bolder)

**Files changed:**
- `apps/frontend/src/pages/Volcanes.tsx` — PageHeader migration
- `apps/frontend/src/components/ui/DangerScale.tsx` — runtime guard
- `apps/frontend/src/components/ui/HourlyTimeline.tsx` — eliminado

**Tests:** `pnpm run build` → ✓ 1.47s ✅

**Next:**
- Fase 3 diferida: /bolder Nubes + Metar (hero callouts, DangerScale 4-5 glow, FlightCatBadge)
- P1 Desastres: filter bar touch targets (py-1.5 → py-3), color rgba hardcodeado
- P1 PrevisionClima: badge modelo durante fetch inicial
- P3 mantenimiento: migrar 27 archivos de hex literales a `var(--color-*)`

---

## 2026-05-29 — Fase 2 auditoría frontend — borderRadius → clases Tailwind ✅

**Done:**
- `Niebla.tsx` — 17 `borderRadius` inline → Tailwind (`rounded-full`, `rounded-2xl`, `rounded-[10px]`, etc.)
- `Terremotos.tsx` — dot de magnitud `50%` → `rounded-full`
- `Nubes.tsx` — `pillStyle()` reestructurada: `borderRadius` eliminado, `rounded-full` en los 3 `<button>` consumidores
- `components/ui/InfiniteNavRail.tsx` → `rounded-full`
- `components/ui/ScrollToTopBubble.tsx` — 2 ocurrencias → `rounded-full`
- `components/ui/MagnitudeScaleBar.tsx` — dot activo → `rounded-full`
- `components/ui/TrendChart.tsx` — 2 barras → `rounded-full`
- Excepción justificada: `Niebla.tsx:532` `'4px 4px 2px 2px'` (barra gráfica asimétrica, sin equiv. Tailwind)

**Criterio de done:**
- `rg "borderRadius:" src/pages` → solo `Niebla.tsx:532` ✅
- `rg "borderRadius:" src/components/ui` → 0 resultados ✅
- `pnpm run build` → ✓ 2.26s ✅

**Next:**
- Fase 3 — /bolder: `Nubes.tsx` + `Metar.tsx` (hero callouts, flight category badges)
- O Fase 4 — /ui-ux-pro-max full audit

---

## 2026-05-29 — Fase 1 auditoría frontend — tokens + colores + DangerScale ✅

**Done:**
- `index.css` → tokens `--color-crit-soft: #ff6b6b` y `--color-fog: #cc66ff` agregados al bloque `@theme`
- `Nubes.tsx` → 4 correcciones `rgba(39,174,96,...)` → `rgba(62,207,122,...)` + `DANGER_COLORS[1] #27ae60` → `#3ecf7a`
- `Metar.tsx` → VFR badge `rgba(39,174,96,...)` → `rgba(62,207,122,...)`
- `LaundryDayCard.tsx` → badge "Baja confianza" `#e07b30` / `rgba(224,117,48,...)` → `#f0a030` / `rgba(240,160,48,...)`
- `CotaDeNieve.tsx` → opacidad scale bar inactiva `0.22` → `0.25`
- `components/ui/DangerScale.tsx` → creado con `DangerLevel`, `DANGER_COLORS`, `DangerScale` exportados
- `Nubes.tsx` + `Desastres.tsx` → eliminadas copias locales, import desde componente compartido
- Fix `verbatimModuleSyntax`: `import { type DangerLevel }` en Nubes.tsx

**Files changed:**
- `apps/frontend/src/index.css`
- `apps/frontend/src/pages/Nubes.tsx`
- `apps/frontend/src/pages/Metar.tsx`
- `apps/frontend/src/pages/CotaDeNieve.tsx`
- `apps/frontend/src/pages/Desastres.tsx`
- `apps/frontend/src/components/ui/LaundryDayCard.tsx`
- `apps/frontend/src/components/ui/DangerScale.tsx` ← nuevo

**Tests:** `pnpm run build` → ✓ 0 errores, built in 2.23s

**Next:**
- Fase 2 — Pills & Badges (shapes): eliminar `borderRadius` hardcodeados en `Niebla.tsx` y otras páginas
- O Fase 3 — /bolder: `Nubes.tsx` + `Metar.tsx`

---

## 2026-05-29 — Desastres: +3 fenómenos + correcciones factuales + planes docs ✅

**Done:**
- `Desastres.tsx` — 8 correcciones factuales (Patricia 325→345 km/h, Valdivia, Tornados San Justo 1973, Incendios Corrientes 2022, Inundaciones curiosidad, Huracanes 48h, acción sin "ruta oficial", etiqueta Tsunamis)
- `Desastres.tsx` — 3 nuevos fenómenos: Ola de calor / Granizo severo / Erupción volcánica (familia, dangerLevel, badge, contenido completo)
- Header actualizado: "Siete" → "Diez fenómenos"
- `CATALOG_desastres.md` eliminado → consolidado en `docs/plans/catalog-desastres-expansion.md`
- `docs/plans/frontend-audit-visual-consistency.md` — plan de auditoría frontend (5 fases, revisado por Opus 4.7)

**Files changed:**
- `apps/frontend/src/pages/Desastres.tsx` — 8 correcciones + 3 entradas nuevas
- `docs/plans/catalog-desastres-expansion.md` — fuente de verdad única del catálogo (7 activos + 3 propuestos → ahora 10 activos)
- `docs/plans/frontend-audit-visual-consistency.md` — plan creado
- `docs/CATALOG_desastres.md` — eliminado

**Tests:** `pnpm exec tsc --noEmit` → 0 errores

**Commit:** `fd36bdb` · **Push:** ✅ origin/main

**Next:**
- Ejecutar Fase 1 del plan de auditoría frontend (`index.css` tokens + DangerScale compartido + correcciones de color)
- Implementar plan GTM/GA4/Sentry (`docs/plans/config-gtm-ga4-sentry.md`)

---

## 2026-05-29 — Auditoría visual + refinamiento catálogo desastres ✅

**Done:**
- Plan de auditoría frontend completo creado y revisado por Opus 4.7
- Corrección crítica: propuesta `src/lib/colors.ts` eliminada → adoptar tokens `@theme` existentes en `index.css`
- `CATALOG_desastres.md` — 10 correcciones factuales y de contenido aplicadas
- Plan de expansión del catálogo creado con 3 nuevos fenómenos listos para implementar

**Files changed:**
- `docs/plans/frontend-audit-visual-consistency.md` — plan completo (5 fases) revisado por Opus, riesgos documentados
- `docs/CATALOG_desastres.md` — correcciones: Valdivia (% viviendas), Patricia (325→345 km/h), Tornados (Tri-State→San Justo 1973), Incendios (Australia→Corrientes 2022 + acción sin "ruta oficial"), Inundaciones (curiosidad→física del agua), Tsunamis (etiqueta acortada), capitalización uniforme en acciones
- `docs/plans/catalog-desastres-expansion.md` — 3 tarjetas propuestas: Ola de calor / Granizo severo / Erupción volcánica

**Tests:** sin cambios de código — no aplica

**Next:**
- Ejecutar Fase 1 del plan de auditoría frontend (`index.css` tokens + correcciones de color + DangerScale compartido)
- Aprobar e implementar los 3 fenómenos nuevos del catálogo en `Desastres.tsx`

---

## 2026-05-28 — gauge fix + PROGRESS.md compression ✅

- `Incendios.tsx` — eliminado `/ 100` del texto central del gauge SVG (quedó solo el número).
- `PROGRESS.md` — comprimido 1351 → 56 líneas (historial → tabla).

**Commit:** `46e067f` · **Tests:** 0 errores TS

**Next:** Awaiting user direction.

---

## 2026-05-28 — /bolder: Lluvias + CotaDeNieve + Radar + CSP fix ✅

- `Lluvias.tsx` — `IntensityScaleBar` (5 niveles), hero callout `animate-ping` (Cumulonimbo/Mammatus), filas `crit` tintadas, fix BAN1 educational cards (`borderLeftWidth:3px` → full tinted border).
- `CotaDeNieve.tsx` — `SnowLevelBar` (4 niveles), semáforo `animate-ping` cuando cota < 1000m.
- `Radar.tsx` — fix BAN1: intro cards y rec cards sin border-left/border-top stripe.
- `vercel.json` — CSP `img-src` + wikimedia, unsplash, zmescience, ucar (fix imágenes Desastres + Nubes).

**Commit:** `047e14f` · **Tests:** 0 errores TS

**Next:** Verificar `/api/metar` en producción. TenderRopa/Volcanes/Desastres: NO aplicar /bolder.

---

## 2026-05-28 — Wave 7 + /bolder Incendios & LavarCoche + S-09 ops ✅

- `Incendios.tsx` — `RiskScaleBar` (6 niveles), hero callout `animate-ping`, glow ambiental, `ConditionChip` crítico, peak risk row tintada.
- **S-06** — `/api/metar` (CheckWX): ICAO validation, `/decoded`+`/taf`, rate limit 20/min, `config.py`, `render.yaml` (CHECKWX_API_KEY), `Metar.tsx` (encodeURIComponent).
- **S-09** — `requirements-lock.txt` (28 paquetes pinneados) + `requirements-dev.txt` pinneado + `render.yaml` → `pip install -r requirements-lock.txt`.
- `LavarCoche.tsx` — `QualityScaleBar` (4 niveles), hero callout `animate-ping`, row backgrounds tintados, score escalado, chip `🌧 Xmm`.

**Commits:** `3b7f90f`, `561eafd`, `b5de2db`, `8e982dd` · **Tests:** 523 passed, 0 errores TS

---

## 2026-05-28 — UX/Visual: Terremotos + Niebla + SplashCursor + /bolder ✅

- `App.tsx` — SplashCursor simplificado.
- `Terremotos.tsx` — top 10 + "Ver N más", `MagnitudeScaleBar` al tope, `/bolder` (filas tintadas, dot pulsante, hero callout M≥4.5).
- `Niebla.tsx` — colores perceptualmente distintos, barra segmentada, `fog_label` visible.

**Commits:** `feeeddf`, `1025878`, `2648c4b` · **Tests:** 0 errores TS

---

## Historial (2026-05-19 → 2026-05-28)

| Fecha | Sesiones | Alcance |
|-------|----------|---------|
| 2026-05-28 | Wave 6a/6b: audit + ops | TS strict, Python cleanup, tests S-10→S-13, CORS, CSP v1, rate limits |
| 2026-05-28 | Audit Wave 5 + incendios | Dead imports, httpx migration, code splitting, IndexGauge → pill |
| 2026-05-27 | Niebla fixes (3 sesiones) | TAF hourly, fog inference, AWC timeout, slots AR redondos, timezone-aware |
| 2026-05-27 | feat(earthquakes) | EMSC primario + USGS fallback (`b5c8427`) |
| 2026-05-26 | Audit Wave 3+4 | Dead code, code splitting, useWeather hooks |
| 2026-05-26 | Incendios + Forecast7d | Windy FWI, GFS fallback, DayArc fix, luna Meeus, scroll-snap 7d cards |
| 2026-05-23 | Nav (2 sesiones) | InfiniteNavRail marquee 2 filas → drag interactivo + blur lateral |
| 2026-05-23 | Features (3 sesiones) | Volcanes Fases 1-3 (OAVV), Meteocons animados, Terremotos LUGAR+refresh |
| 2026-05-22 | Fixes (3 sesiones) | METAR parsing, SMN date, GPS, OM 429, badge temperatura |
| 2026-05-21 | Fases 6b–6d | ModelStatusBar, TenderRopa fórmula, SportBlock, UI polish |
| 2026-05-21 | Fases 6e–6g | BorderGlow, RainForecastCard, UX audit, pre-deploy audit |
| 2026-05-20 | Fases 5b–6a | React Bits, tool cota de nieve, TenderRopa 7d, GlowCard |
| 2026-05-19 | Fases 1–3 | FastAPI scaffold, /api/weather/current, calculadores, USGS terremotos |
| 2026-05-19 | Fases 4–5 | Frontend Vite+React+Tailwind v4, routing, integración frontend→backend |
