# API_Prediction — Estrategia de Fuentes de Datos para Pronóstico Diario

**Estado:** ✅ IMPLEMENTADO
**Creado:** 2026-06-01
**Última revisión:** 2026-06-01
**Implementado:** 2026-06-01
**Prioridad:** P0/P1 — bugs activos en producción (corregidos)
**Owner del plan:** Backend
**Estimación total:** 4–6 horas (2 fixes + refactor + tests + verificación)

---

## 0. Resumen ejecutivo

Dos bugs en producción afectan la confiabilidad del pronóstico de 7 días en `/api/weather/dashboard`:

1. **P0 — Lluvia% siempre 0%** en todos los días para todos los modelos. Causa: la lógica en `routers/weather.py:_build_7d_forecast()` da prioridad a Windy para `precip_prob`, pero la Windy Point Forecast API **no tiene este campo nativo** y el valor derivado internamente es casi siempre `None` o `0`.
2. **P1 — Temperatura máxima con error de 3–5°C** vs ECMWF / Windy UI. Causa: Windy devuelve `temp` instantánea cada 3h; `max(temp_3h)` ≠ máximo diario real del modelo. Open-Meteo provee `temperature_2m_max` como agregado nativo del modelo pero **nunca se usa cuando Windy está disponible**.

**Fix propuesto:** refactor moderado (Opción B) que extrae la lógica de selección de fuente a `_merge_daily_fields()` respaldada por una constante `FIELD_SOURCES`. Cada campo declara su fuente primaria y fallback explícitamente. Sin cambios de schema en la API pública. Compatible hacia atrás.

**Verificable en staging:** `precip_prob > 0` cuando hay lluvia esperada según ECMWF; `temp_max` dentro de ±1°C vs Windy UI.

---

## 1. Contexto y evidencia

### 1.1 Comparativa real (capturada 2026-06-01, ECMWF en SkypulseAR vs Windy)

| Día | App `temp_max` | Windy ECMWF max | Δ | App `precip_prob` | Windy mm (sum 3h slots) |
|-----|----------------|-----------------|---|-------------------|--------------------------|
| Lunes 1 | 15°C | **20°C** | +5 | **0%** | 2.8 mm |
| Martes 2 | 19°C | 15°C | −4 | **0%** | 0.8 mm |
| Miércoles 3 | 17°C | 17°C | 0 | **0%** | 0.2 mm |
| Jueves 4 | 17°C | **20°C** | +3 | **0%** | **6.9 mm** ⚠ |
| Viernes 5 | 19°C | 18°C | −1 | **0%** | 0.6 mm |
| Sábado 6 | 21°C | 18°C | −3 | **0%** | 2.7 mm |
| Domingo 7 | 19°C | — | — | **0%** | — |

El Jueves 4 muestra 0% de probabilidad de lluvia cuando hay 6.9mm acumulados según ECMWF — el usuario podría planificar al aire libre y verse sorprendido.

### 1.2 Causas raíz — verificadas en código

**Bug 1 — `precip_prob = 0%`:**

| Ubicación | Línea | Defecto |
|-----------|-------|---------|
| `services/windy.py` | **375** | `n_total = len(slots) or 1` — el denominador cuenta TODOS los slots horarios, incluyendo los que tienen `precip_3h_mm = None`. El cómputo correcto debería usar `len(precips)` (solo slots con dato). |
| `services/windy.py` | **377** | `precip_prob = (n_rainy / n_total) * 100.0 if precips else None` — cuando `precips` está vacío (Windy devuelve `None` para todos los slots del día, frecuente en días "secos" según GFS), retorna `None`. |
| `routers/weather.py` | **771–775** | Cuando `w is not None` (Windy disponible), `precip_prob = w.precip_prob`. El `precip_probability_max` de Open-Meteo (campo nativo) **solo se usa en el branch `else`** cuando Windy no está disponible. Como Windy casi siempre responde, OM nunca alimenta este campo. |

**Bug 2 — `temp_max` ±3–5°C:**

| Ubicación | Línea | Defecto |
|-----------|-------|---------|
| `services/windy.py` | **358, 382** | `temps = [s.temp_c for s in slots]` + `temp_max_c = round(max(temps), 2)` — máximo de snapshots horarios (resolución 3h). Si el pico térmico real es 17:30 y los slots son `15:00 / 18:00`, ambos slots subestiman el pico real. |
| `services/windy.py` | **124** | `_WINDY_PARAMETERS = ["temp", "rh", "wind", "windGust", "precip", "lclouds", "mclouds", "hclouds", "dewpoint"]` — solicita `temp` (instantánea). La API no expone un campo de máximo diario en el plan gratuito. |
| `routers/weather.py` | **771–773** | Cuando `w is not None`, `temp_max = w.temp_max_c` (max de snapshots 3h). El `temperature_2m_max` de OM (agregado nativo del modelo, ya disponible vía `get_multi_model_daily`) **nunca se usa** cuando Windy está disponible. |

### 1.3 Limitaciones documentadas de Windy Point Forecast API

Confirmado por documentación oficial (NotebookLM `ccca882a`):

| Campo deseado | ¿Existe en Windy API? | Alternativa nativa |
|---------------|----------------------|---------------------|
| `precipitation_probability` | ❌ No | OM `precipitation_probability_max` |
| `temperature_2m_max` (diario) | ❌ No, solo `temp` instantánea | OM `temperature_2m_max` |
| `precip` 3h acumulado | ✅ `past3hprecip-surface` | — |
| `temp` 2m | ✅ `temp-surface` (instantáneo) | — |
| `wind` 10m | ✅ `wind_u-surface` / `wind_v-surface` | — |
| `rh` | ✅ `rh-surface` (instantáneo) | — |
| `ptype` | ✅ Tipo precip (0/1/3/5/7/8) | — |
| `mx2t3` / `mn2t3` | ⚠ Existe en ECMWF IFS, no confirmado si Windy lo expone | Investigar Fase 2 |

---

## 2. Arquitectura propuesta — Opción B: Refactor moderado

### 2.1 Principio

Extraer la lógica actual de selección de fuente (acoplada dentro del loop de `_build_7d_forecast()`) a una función dedicada `_merge_daily_fields()` respaldada por una constante `FIELD_SOURCES`. Cada campo declara explícitamente su fuente primaria, su fallback y el agregador a usar.

Beneficio: la estrategia queda como código auditable. Próximo bug similar tiene una sola línea para investigar (la entrada en `FIELD_SOURCES`).

### 2.2 Diseño de tipos

```python
# apps/backend/app/services/forecast_merge.py  (archivo nuevo)
from typing import Callable, Literal
from dataclasses import dataclass

SourceName = Literal["windy", "openmeteo"]

@dataclass(frozen=True)
class FieldSource:
    """Especificación de cómo construir un campo del DailyEntrySchema."""
    primary: SourceName
    fallback: SourceName | None
    # Extractor del valor desde la entrada de cada fuente; None si la fuente no tiene el campo.
    extract_windy: Callable[["WindyDailyEntry"], float | None] | None
    extract_om: Callable[[list[float]], float | None] | None  # recibe lista de valores OM por modelo
    rationale: str  # documentación inline
```

### 2.3 Tabla `FIELD_SOURCES`

| Campo `DailyEntrySchema` | Primario | Fallback | Extractor primario | Razón |
|--------------------------|----------|----------|--------------------|-------|
| `temp_max` | `openmeteo` | `windy` | `mean(om.temp_max[i])` | OM tiene `temperature_2m_max` como agregado nativo del modelo; el `max(temp_3h)` de Windy subestima picos diurnos. |
| `temp_min` | `openmeteo` | `windy` | `mean(om.temp_min[i])` | Ídem. |
| `precip_prob` | `openmeteo` | `windy` | `max(om.precip_prob_max[i])` | **Windy no tiene este campo nativo.** OM `precipitation_probability_max` es la única fuente confiable. Fallback Windy solo si OM falla en TODOS los modelos. |
| `precip_sum` | `windy` | `openmeteo` | `windy.precip_sum_mm` | Windy `sum(past3hprecip-surface)` agrega 8 slots/día — mayor resolución que OM `precipitation_sum`. |
| `wind_speed_max` | `windy` | `openmeteo` | `windy.wind_speed_max_kmh` | Windy `max(wind_3h_slots)` capta gusts mejor que `wind_speed_10m_max` de OM. |
| `humidity_mean` | `windy` | `openmeteo` | `windy.humidity_mean` | Windy `mean(rh_3h)` tiene mayor resolución temporal. |
| `weather_code` | `openmeteo` | — | `mode(om.weather_codes[i])` | Windy no provee WMO codes. Sin fallback. |
| `confidence_pct` | `openmeteo` | — | `daily_multi.consensus_pct_per_day[i]` | Consenso multi-modelo solo lo provee OM. |
| `snow_level_m` | `windy` | — | derivado de Windy 850hPa | Campo específico ya implementado en `windy.py`. |

**Regla general derivada:**
- Agregados diarios calculados por el modelo (`max`, `min`, `probability_max`) → **Open-Meteo**.
- Acumulaciones y máximos sobre series temporales 3h (precip, viento, humedad) → **Windy**.
- Metadatos de cielo (weather code, UV) → **Open-Meteo** siempre.

### 2.4 Diseño de `_merge_daily_fields()`

```python
def _merge_daily_fields(
    *,
    day_index: int,
    windy_entry: WindyDailyEntry | None,
    om_models: list[DailyForecastDataExt],
    field_sources: dict[str, FieldSource] = FIELD_SOURCES,
    logger: logging.Logger = logger,
) -> dict[str, float | int | None]:
    """
    Construye los campos meteorológicos del día `day_index` aplicando FIELD_SOURCES.

    Cada campo intenta:
      1. Su fuente primaria (Windy o OM).
      2. Si esa devuelve None, su fallback.
      3. Si ambas fallan, retorna None y se loguea WARNING.

    Returns:
        Diccionario con keys: temp_max, temp_min, precip_sum, precip_prob,
        wind_speed_max, humidity_mean. No incluye weather_code (manejado aparte).
    """
    result: dict[str, float | int | None] = {}

    for field_name, spec in field_sources.items():
        primary_val = _extract_from_source(spec.primary, spec, windy_entry, om_models, day_index)
        if primary_val is not None:
            result[field_name] = primary_val
            continue

        if spec.fallback is None:
            result[field_name] = None
            continue

        fallback_val = _extract_from_source(spec.fallback, spec, windy_entry, om_models, day_index)
        result[field_name] = fallback_val

        if fallback_val is None:
            logger.warning(
                "forecast_merge field=%s day_idx=%d primary=%s fallback=%s both_none",
                field_name, day_index, spec.primary, spec.fallback,
            )

    return result
```

---

## 3. Implementación — Fixes inmediatos

### 3.1 Fix 1 — `precip_prob` (P0)

**Cambio mínimo seguro** que ataca el síntoma antes del refactor completo. Se puede aplicar en una sesión separada si urge.

**Archivo:** `apps/backend/app/routers/weather.py`, función `_build_7d_forecast()` (líneas **768–787**).

```python
# ANTES (líneas 769–776):
w = windy_by_date.get(date_str)
if w is not None:
    temp_max = w.temp_max_c
    temp_min = w.temp_min_c
    precip_sum = w.precip_sum_mm
    precip_prob = w.precip_prob
    wind_max = w.wind_speed_max_kmh
else:
    # ... fallback OM

# DESPUÉS — precip_prob siempre desde OM, con fallback a Windy:
w = windy_by_date.get(date_str)
precip_probs_om = _om_vals(i, "precip_prob_max")

if w is not None:
    temp_max = w.temp_max_c
    temp_min = w.temp_min_c
    precip_sum = w.precip_sum_mm
    # precip_prob: OM primario, Windy fallback
    if precip_probs_om:
        precip_prob = max(precip_probs_om)
    else:
        precip_prob = w.precip_prob  # fallback si OM falla
    wind_max = w.wind_speed_max_kmh
else:
    # ... fallback OM existente (sin cambios)
```

**Fix secundario:** `apps/backend/app/services/windy.py`, líneas **375–377**, para que el fallback Windy sea correcto cuando se use.

```python
# ANTES:
n_total = len(slots) or 1
n_rainy = sum(1 for p in precips if p > 0.1)
precip_prob = (n_rainy / n_total) * 100.0 if precips else None

# DESPUÉS:
n_precip_slots = len(precips) or 1   # solo slots con dato (no None)
n_rainy = sum(1 for p in precips if p > 0.1)
precip_prob = (n_rainy / n_precip_slots) * 100.0 if precips else None
```

**Esfuerzo:** 15 min. **Riesgo:** bajo — cambio aislado, cubierto por tests.

### 3.2 Fix 2 — `temp_max` / `temp_min` (P1)

**Archivo:** `apps/backend/app/routers/weather.py`, función `_build_7d_forecast()` (líneas **768–787**).

```python
# DESPUÉS — temp_max/min siempre desde OM, fallback a Windy:
temps_max_om = _om_vals(i, "temp_max")
temps_min_om = _om_vals(i, "temp_min")

if temps_max_om:
    temp_max = round(sum(temps_max_om) / len(temps_max_om), 1)
elif w is not None:
    temp_max = w.temp_max_c   # fallback Windy
else:
    temp_max = None

if temps_min_om:
    temp_min = round(sum(temps_min_om) / len(temps_min_om), 1)
elif w is not None:
    temp_min = w.temp_min_c
else:
    temp_min = None
```

**Esfuerzo:** 15 min. **Riesgo:** bajo — el fallback Windy preserva el comportamiento anterior cuando OM no responde.

### 3.3 Refactor — `_merge_daily_fields()` (Fase 1b, opcional pero recomendado)

Una vez aplicados los dos fixes anteriores, extraer toda la lógica de selección de fuente a `apps/backend/app/services/forecast_merge.py` con `FIELD_SOURCES`. La función `_build_7d_forecast()` queda como orquestador limpio:

```python
def _build_7d_forecast(...) -> list[DailyEntrySchema]:
    ref = next(iter(daily_multi.models.values()))
    today = _Date.today()
    windy_by_date = {d.date: d for d in (windy_daily or [])}
    models_list = _filter_models_list(daily_multi, selected_model)

    entries: list[DailyEntrySchema] = []
    for i, date_str in enumerate(ref.dates):
        merged = _merge_daily_fields(
            day_index=i,
            windy_entry=windy_by_date.get(date_str),
            om_models=models_list,
        )
        # Construir DailyEntrySchema con merged + labels + weather_code + confidence
        entries.append(_build_entry(date_str, merged, ...))

    return entries
```

**Esfuerzo:** 1.5 h (incluye mover código, ajustar imports, tests).

---

## 4. Observabilidad

### 4.1 Logging estructurado

Extender `_build_7d_forecast()` con logs estructurados que permitan diagnosticar qué fuente alimentó cada campo en producción.

```python
# Al final de _merge_daily_fields() para cada día:
logger.info(
    "forecast_merge_complete date=%s windy_available=%s "
    "fields_from_windy=%s fields_from_om=%s fields_none=%s",
    date_str,
    windy_entry is not None,
    fields_from_windy,   # ["precip_sum", "wind_speed_max", "humidity_mean"]
    fields_from_om,      # ["temp_max", "temp_min", "precip_prob"]
    fields_none,         # campos donde primary y fallback dieron None
)
```

### 4.2 Alertas — warnings críticos

| Condición | Log level | Mensaje estructurado |
|-----------|-----------|----------------------|
| `precip_prob is None` para ≥3 días consecutivos | `WARNING` | `forecast_alert kind=precip_prob_missing days={n}` |
| `temp_max is None` en cualquier día | `WARNING` | `forecast_alert kind=temp_max_missing date={date}` |
| Windy disponible pero todos sus campos `None` para un día | `WARNING` | `forecast_alert kind=windy_empty_day date={date}` |
| OM falla en TODOS los modelos para un día | `ERROR` | `forecast_alert kind=om_total_failure date={date}` |
| `precip_prob` difiere de `precip_sum > 0` cuando ambos disponibles | `INFO` | `forecast_anomaly kind=prob_sum_mismatch date={date} prob={p} sum={s}` |

### 4.3 Métricas de fuente (futuro — Fase 2)

Exponer en el response del dashboard un nuevo campo opcional `field_sources` que indica qué fuente alimentó cada campo del primer día (para debug visible en la UI o en una herramienta admin):

```json
{
  "forecast_7d": [...],
  "field_sources_today": {
    "temp_max": "openmeteo",
    "precip_prob": "openmeteo",
    "precip_sum": "windy",
    "wind_speed_max": "windy"
  }
}
```

Esto facilita reportes de incidentes ("hoy todo viene de OM porque Windy cuota agotada").

### 4.4 Métricas de drift entre fuentes (futuro)

Cuando ambas fuentes están disponibles para un campo, loguear la diferencia para detectar drift sistemático:

```python
if windy_entry and temps_max_om:
    delta = abs(windy_entry.temp_max_c - mean(temps_max_om))
    if delta > 3.0:
        logger.info("forecast_drift field=temp_max windy=%.1f om=%.1f delta=%.1f",
                    windy_entry.temp_max_c, mean(temps_max_om), delta)
```

---

## 5. Caching

### 5.1 Estado actual

| Cache | Ubicación | TTL actual | Maxsize |
|-------|-----------|------------|---------|
| Windy raw payload | `services/windy.py:108` | **3600s (1h)** | 256 |
| Open-Meteo daily/hourly | `services/openmeteo.py` (`_CACHE_FORECAST`) | (verificar valor) | (verificar) |
| SMN observaciones | `services/smn.py` | (verificar) | — |

### 5.2 Estrategia propuesta

| Fuente | TTL recomendado | Razón |
|--------|-----------------|-------|
| Windy hourly raw | **3600s (1h)** | Sin cambio. Windy refresca data cada 3–6h pero coordina con `_fetch_events` para deduplicar coroutines. |
| Open-Meteo `get_multi_model_daily` | **3600s (1h)** | OM publica updates frecuentes. 1h equilibra freshness vs carga. |
| Open-Meteo `get_hourly_forecast_ext` | **1800s (30min)** | Datos horarios más sensibles a freshness para "hoy". |
| SMN observación actual | **300s (5min)** | Datos en tiempo real, freshness importa. |

**Cambios concretos:**
- Verificar y unificar el TTL de OM en `openmeteo.py` (probablemente ya está, validar valor).
- Documentar en `core/config.py` los settings: `cache_ttl_windy`, `cache_ttl_om_daily`, `cache_ttl_om_hourly`, `cache_ttl_smn`.

### 5.3 Invalidación manual (debug)

Endpoint admin opcional (Fase 2, requiere auth interna):

```
POST /api/admin/cache/clear?source=windy|openmeteo_daily|openmeteo_hourly|smn
Authorization: Bearer <admin_token>
```

Útil cuando se sospecha que un cache tiene datos corruptos en producción. Out of scope para este plan inicial — solo se documenta.

---

## 6. Tests

### 6.1 Archivo nuevo — `apps/backend/tests/test_forecast_field_sources.py`

```python
# Estructura del test
import pytest
from app.routers.weather import _build_7d_forecast
# Fixtures que construyen MultiModelDailyData y WindyDailyEntry mocks
```

| # | Nombre del test | Condición | Assertion |
|---|-----------------|-----------|-----------|
| T1 | `test_precip_prob_uses_om_when_windy_available` | Windy entry con `precip_prob=0`, OM `precip_prob_max=[60]` | `entry.precip_prob == 60` |
| T2 | `test_precip_prob_not_zero_when_om_has_rain_forecast` | OM `precip_prob_max=[45]`, Windy ausente | `entry.precip_prob == 45` |
| T3 | `test_precip_prob_fallback_to_windy_when_om_none` | OM `precip_prob_max=[]`, Windy `precip_prob=30` | `entry.precip_prob == 30` |
| T4 | `test_temp_max_uses_om_not_windy_snapshots` | OM `temp_max=[22.0]`, Windy `temp_max_c=18.0` | `entry.temp_max == 22.0` |
| T5 | `test_temp_max_fallback_to_windy_when_om_none` | OM `temp_max=[None]`, Windy `temp_max_c=19.0` | `entry.temp_max == 19.0` |
| T6 | `test_temp_max_both_none` | OM vacío, Windy ausente | `entry.temp_max is None` (sin crash) |
| T7 | `test_precip_sum_uses_windy_primary` | Windy `precip_sum_mm=3.5`, OM `precip_sum=[2.1]` | `entry.precip_sum == 3.5` |
| T8 | `test_wind_speed_max_uses_windy_primary` | Windy `wind_speed_max_kmh=45`, OM `wind_speed_max=[32]` | `entry.wind_speed_max == 45.0` |
| T9 | `test_humidity_mean_uses_windy_primary` | Windy `humidity_mean=68`, OM `humidity_mean=[55]` | `entry.humidity` o equivalente |
| T10 | `test_consensus_mode_averages_multiple_om_models` | Mode=consensus, 3 modelos OM con temp_max=[20, 22, 24] | `entry.temp_max == 22.0` |
| T11 | `test_selected_model_filters_om_list` | Mode=ecmwf, solo modelo ecmwf_ifs025 contribuye | OM gfs_seamless ignorado |

### 6.2 Fix del fallback denominador — `apps/backend/tests/test_windy_daily_aggregation.py`

| # | Nombre | Condición | Assertion |
|---|--------|-----------|-----------|
| W1 | `test_precip_prob_denominator_uses_precips_not_slots` | 4 slots con precip (2 con lluvia >0.1), 4 slots con `None` | `precip_prob == 50.0` (no 25.0) |
| W2 | `test_precip_prob_none_when_all_slots_none` | 8 slots con `precip_3h_mm=None` | `precip_prob is None` |
| W3 | `test_precip_prob_zero_when_precips_all_below_threshold` | 8 slots con valores 0.05–0.09 | `precip_prob == 0.0` |

### 6.3 Tests de integración — `apps/backend/tests/test_dashboard_integration.py`

Usando fixtures de respuestas reales (capturadas de Windy/OM):

- `test_dashboard_precip_prob_present_when_rain_expected` — con fixture donde ECMWF muestra 6.9mm en jueves: `forecast_7d[3].precip_prob > 30`
- `test_dashboard_temp_max_within_tolerance_of_om` — `abs(forecast_7d[i].temp_max - om_temp_max[i]) <= 1.0` para todos los días
- `test_dashboard_no_zero_precip_prob_for_full_week_when_rain_expected` — fail si los 7 días tienen `precip_prob == 0` y OM reporta `precip_sum > 0` en algún día

### 6.4 Comando de ejecución

```bash
uv run pytest apps/backend/tests/test_forecast_field_sources.py \
              apps/backend/tests/test_windy_daily_aggregation.py \
              apps/backend/tests/test_dashboard_integration.py -v
```

---

## 7. Plan de rollout

### 7.1 Estrategia

Cambios **API-compatibles** (sin modificar `DailyEntrySchema`, solo los valores). No requiere feature flag — el comportamiento mejora silenciosamente para el frontend.

### 7.2 Pasos ordenados

1. **PR 1 (P0):** Solo Fix 1 + Fix `windy.py:375`. Tests T1, T2, T3, W1, W2, W3.
2. **PR 2 (P1):** Fix 2. Tests T4, T5, T6.
3. **PR 3 (refactor):** Extraer `_merge_daily_fields()` y `FIELD_SOURCES`. Tests T7–T11 + integration.
4. **PR 4 (observabilidad):** Logging estructurado + warnings de alerta.
5. **PR 5 (futuro):** Métricas, field_sources en response, drift detection.

PRs 1 y 2 se pueden mergear el mismo día. PR 3 puede esperar a la siguiente sesión.

### 7.3 Criterios de aceptación

| Criterio | Cómo verificar | Pasa si |
|----------|----------------|---------|
| `precip_prob` no es 0 cuando hay lluvia esperada | `curl /api/weather/dashboard?lat=-31.4&lon=-64.2&model=ecmwf` y comparar con Windy UI ECMWF para el mismo lat/lon | Al menos 1 día con `precip_prob > 0` cuando ECMWF muestra mm > 0.5 |
| `temp_max` coincide con Windy UI ±1°C | Comparar 7 días con captura Windy ECMWF | `abs(app - windy) <= 1.0` en ≥6 de 7 días |
| Tests pasan | `uv run pytest -v` | 100% verde, ≥11 nuevos tests verdes |
| Sin regresión en otros campos | Comparar `precip_sum`, `wind_speed_max`, `humidity_mean` antes/después | Valores idénticos (esos campos no cambian de fuente) |
| Logs en producción muestran fuente correcta | Revisar logs 1h post-deploy | `forecast_merge_complete` aparece, `fields_from_om` contiene `temp_max`, `temp_min`, `precip_prob` |

### 7.4 Rollback

Cada PR es atómico. Si Fix 1 introduce regresión:

```bash
git revert <commit_hash_pr1>
git push origin main
# Vercel/Render redespliega automáticamente
```

Como el cambio es solo de prioridad de campos (sin cambios de schema), no hay datos que migrar. Rollback es instantáneo.

---

## 8. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Impacto | Mitigación |
|---|--------|--------------|---------|------------|
| R1 | OM rate-limit (429) en horas pico causa `precip_prob_max` vacío y `precip_prob` cae a fallback Windy (también `None`) | Media | Alto — vuelve a mostrar 0% | Cache OM 1h reduce frecuencia de llamadas. Logging de alerta ya cubre. Si pasa, usuario ve "0%" pero log alerta → se sabe rápido. |
| R2 | OM `temperature_2m_max` reporta valores anómalos puntuales (ej. spike por GFS) | Baja | Medio — un día con temp irreal | Multi-modelo: el mean across models suaviza outliers. Fase 2 puede agregar validación de rango razonable [−40, +55]. |
| R3 | Fallback Windy se activa por OM down prolongado y el `n_precip_slots` fix introduce comportamiento que tests no cubrían | Baja | Bajo | W1/W2/W3 cubren los 3 escenarios principales. |
| R4 | Frontend asume que `precip_prob` siempre venía de Windy y tiene lógica que rompe con valores OM más altos | Muy baja | Bajo | Schema no cambia. Frontend solo lee el número. Verificar con QA visual en staging. |
| R5 | Refactor introduce bug por mover lógica entre archivos | Media | Medio | PR 3 separada de los fixes; tests T1–T11 + integration deben pasar antes de merge. |
| R6 | Drift entre OM y Windy se hace visible y confunde a usuarios que comparan con otra app | Baja | Bajo | Documentación visible en la UI ("Fuente: Open-Meteo + Windy"). Ya existe `forecast_source` en el response. |

---

## 9. Mejoras futuras

### Fase 2 — ECMWF `mx2t3` / `mn2t3` vía Windy

`mx2t3` (max temp 2m últimas 3h) y `mn2t3` (min temp 2m últimas 3h) existen en ECMWF IFS según documentación oficial. **Acción de investigación:**

1. Hacer una request a Windy Point Forecast API solicitando `mx2t3-surface` y `mn2t3-surface` en `_WINDY_PARAMETERS`.
2. Si la API responde con datos válidos: agregar a Windy daily y usar como `temp_max_c` en modo ECMWF.
3. Si responde con `null` o error: documentar la limitación y mantener OM como primario.

Beneficio esperado: en modo ECMWF, `temp_max` sería ±0.5°C en lugar de ±1°C.

### Fase 3 — `ptype` para diferenciación de precipitación

Windy expone `ptype` (0=sin precip, 1=lluvia, 3=lluvia helada, 5=nieve, 7=mixto, 8=hielo). Usar para:

- Mejorar el ícono del pronóstico diario (actualmente solo WMO code de OM).
- Mostrar "nieve esperada" vs "lluvia esperada" en la UI.
- Refinar la decisión de `snow_level_m`.

### Fase 4 — Dashboard interno de salud de fuentes

Endpoint admin `/api/admin/source-health` que reporte:

- Tasa de éxito por fuente (Windy/OM) en las últimas 24h.
- Latencia P50/P95/P99 por fuente.
- Días con `precip_prob is None` en los últimos 7 días.
- Drift histórico entre Windy y OM por campo.

Out of scope para el plan inmediato.

---

## 10. Checklist de implementación (granular)

### PR 1 — P0 (precip_prob) ✅

- [x] `apps/backend/app/routers/weather.py` — prioridad de `precip_prob` cambiada a OM primario, Windy fallback
- [x] `apps/backend/app/services/windy.py` — fix denominador `len(slots)` → `len(precips) or 1`
- [x] `apps/backend/tests/test_forecast_field_sources.py` — T1, T2, T3 pasando
- [x] `apps/backend/tests/test_windy_daily_aggregation.py` — W1, W2, W3 pasando
- [x] `uv run pytest -v` → 603 tests verdes

### PR 2 — P1 (temp_max/temp_min) ✅

- [x] `apps/backend/app/routers/weather.py` — prioridad de `temp_max`/`temp_min` cambiada a OM primario, Windy fallback
- [x] Tests T4, T5, T6 agregados en `test_forecast_field_sources.py`

### PR 3 — Refactor _merge_daily_fields() ✅

- [x] `apps/backend/app/services/forecast_merge.py` — creado con `FIELD_SOURCES` y `merge_daily_fields()`
- [x] `apps/backend/app/routers/weather.py:_build_7d_forecast()` — reemplazada lógica inline por `merge_daily_fields()`
- [x] Tests T7–T11 en `test_forecast_field_sources.py`
- [x] Tests de integración IT1, IT2, IT3 en `test_dashboard_integration.py`
- [x] `_build_7d_forecast()` < 60 líneas

### Fix adicional — Drizzle detection (no estaba en plan original) ✅

- [x] `apps/backend/app/routers/weather.py:_build_rain_forecast()` — detecta llovizna por condiciones ambientales
  - `current.humidity >= 80 AND current.cloud_cover >= 70` → `status_text="Llovizna posible"`, `confidence_label="media"`
  - Windy slot averages `hum_mean >= 75 AND cloud_mean >= 80` → drizzle por slots próximos
  - `confidence_label` ya no es hardcodeado a "alta"
- [x] `apps/backend/tests/test_rain_forecast_drizzle.py` — D1–D6 pasando

### PR 4 — Observabilidad ⏳ Futuro

- [ ] Logging estructurado `forecast_merge_complete` y `forecast_alert kind=...`
- [ ] Verificar en logs staging que aparecen los logs esperados
- [ ] Documentar formato de logs en README backend

### PR 5 — Futuro (cuando aplique) ⏳

- [ ] Investigar `mx2t3`/`mn2t3` vía Windy
- [ ] Agregar `field_sources_today` al response del dashboard
- [ ] Drift logging entre fuentes
- [ ] Endpoint admin de salud de fuentes

---

## 11. Archivos afectados

| Archivo | Cambio | LOC esperado |
|---------|--------|--------------|
| `apps/backend/app/routers/weather.py` | `_build_7d_forecast()`: prioridad campos, logging | +25 / −10 |
| `apps/backend/app/services/windy.py` | `get_daily_forecast()`: fix denominador `precip_prob` | +2 / −1 |
| `apps/backend/app/services/forecast_merge.py` | **Archivo nuevo** — `FIELD_SOURCES`, `_merge_daily_fields()`, helpers | +150 |
| `apps/backend/app/core/config.py` | Settings `cache_ttl_*` documentados | +5 |
| `apps/backend/tests/test_forecast_field_sources.py` | **Archivo nuevo** — 11 tests | +250 |
| `apps/backend/tests/test_windy_daily_aggregation.py` | **Archivo nuevo** — 3 tests | +60 |
| `apps/backend/tests/test_dashboard_integration.py` | Agregar 3 tests con fixtures | +120 |

---

## 12. Decisiones que requieren confirmación

Antes de implementar, confirmar con el owner:

1. **¿Hacer los 5 PRs en orden o agrupar PR 1+2 en uno solo?** Recomendación: agrupar 1+2 (mismo archivo, mismo riesgo) para no fragmentar.
2. **¿Implementar PR 3 (refactor) en la misma sesión que los fixes?** Recomendación: sí, una vez verdes los fixes — minimiza ida y vuelta sobre el mismo código.
3. **¿Logging estructurado va a Sentry o solo a logs?** Verificar configuración actual de logging del proyecto.
4. **¿Investigar `mx2t3` ahora o dejarlo para Fase 2?** Recomendación: dejarlo — el fix con OM ya cubre el bug.
5. **¿Endpoint admin cache/clear se implementa ahora?** Recomendación: no — solo documentar como mejora futura.

---

## Apéndice A — Comandos útiles

```bash
# Tests
cd "G:\Developer\1Proyectos\SkypulseARinfo"
uv run pytest apps/backend/tests/test_forecast_field_sources.py -v
uv run pytest apps/backend/tests/test_windy_daily_aggregation.py -v
uv run pytest apps/backend/tests/ -v --tb=short

# Verificación manual contra producción
curl "https://api.skypulse.example/api/weather/dashboard?lat=-31.4&lon=-64.2&model=ecmwf" | jq '.forecast_7d[] | {date, temp_max, precip_prob, precip_sum}'

# Inspección de logs (después de PR 4)
grep "forecast_merge_complete\|forecast_alert" backend.log | tail -20
```

## Apéndice B — Referencias

- Windy Point Forecast API (limitaciones confirmadas): NotebookLM cuaderno `ccca882a-155e-4425-84f4-5107a3e6f553`
- Open-Meteo daily endpoint: https://open-meteo.com/en/docs (`temperature_2m_max`, `precipitation_probability_max`)
- ECMWF IFS dataset (campos `mx2t3`, `mn2t3`, `tp`, etc.): NotebookLM `13c24bea-8291-454a-9ac1-5f4dd2e2e217`
- Código fuente actual: `apps/backend/app/routers/weather.py:728–848` (`_build_7d_forecast`), `apps/backend/app/services/windy.py:340–395` (`get_daily_forecast`)
