# Verificación offline de pronósticos (FRA-321)

Mide el error de Tmax/Tmin diarios de GFS y ECMWF contra las observaciones del SMN
(`regtemp`) y compara ECMWF, el promedio (`mean`) y dos variantes (corrección de sesgo y
pesos por inverso del MAE), por anticipación (1 a 7 días) y estación del año.

Es una medición offline: no toca código de producción (`apps/`) ni el legado (`src/`).
No usa claves. Los pronósticos salen de la Previous Runs API de Open-Meteo (uso no
comercial, cupo compartido) y las observaciones del archivo `regtemp` del SMN.

## Cómo correr

Todos los comandos desde la raíz del repo, con el venv del backend (trae `httpx` y `pytest`):

```
PY=apps/backend/.venv/Scripts/python.exe

# 1) Plan sin red: llamadas HTTP, peso estimado y cuántas ya están en caché
$PY scripts/verificacion/medir_tmax_tmin.py --dry-run

# 2) Corrida real (baja regtemp del SMN solo si se pasa --descargar)
$PY scripts/verificacion/medir_tmax_tmin.py --descargar --max-calls 100
# o con un regtemp ya descargado:
$PY scripts/verificacion/medir_tmax_tmin.py --regtemp RUTA/regtemp.txt
```

Opciones útiles: `--estaciones "EZEIZA AERO,SABE"` (nombre SMN o ICAO), `--inicio/--fin`
(por defecto 2025-10-05 a 2026-10-04), `--chunk-dias` (92), `--pausa` (3 s entre llamadas),
`--ventana-tmax/--ventana-tmin` (fuerza la ventana, por ejemplo `03Z` o `"D-1 21Z"`),
`--cache` y `--salida`.

- La caché en disco (`cache/openmeteo/`, clave = SHA-256 de la URL con parámetros) hace que
  repetir una corrida no llame a la red. `--max-calls` es un límite duro de intentos HTTP
  (los reintentos cuentan). Ante 429 persistente la corrida se corta con error claro.
- Resultados en `resultados/`: `resumen.md` (tablas con n), `errores_por_caso.csv`,
  `errores_por_estacion.csv` y `metadatos.json`. Nada de esto se versiona.
- Se piden las fechas con 1 día de relleno (ventanas que cruzan medianoche UTC); el final se
  recorta al día de ayer porque hoy los datos están incompletos.

## Archivador diario de `datohorario` (T3)

`archivar_datohorario.py` guarda el zip diario de observaciones horarias del SMN (TEMP, HUM,
PNM, dirección y velocidad del viento en km/h). El endpoint
(`https://ssl.smn.gob.ar/dpd/zipopendata.php?dato=datohorario`) ignora la fecha y siempre
entrega el último día, así que un día que no se archiva a tiempo no se puede recuperar:
conviene correrlo una vez al día.

```
PY=apps/backend/.venv/Scripts/python.exe
$PY scripts/verificacion/archivar_datohorario.py --dry-run   # descarga y valida, no escribe
$PY scripts/verificacion/archivar_datohorario.py
```

- Destino por defecto: `scripts/verificacion/archivo_datohorario/` (en `.gitignore`);
  cambiarlo con `--destino DIR`. `--url` permite apuntar a otro servidor (tests).
- El nombre sale de `Content-Disposition` y debe ser `DatosHorarios-AAAAMMDD.zip`
  (cualquier otro se rechaza). Se valida que sea un zip íntegro y no vacío; una página HTML de
  error no se guarda.
- Idempotente: mismo nombre y mismos bytes (sha256) no hace nada (código 0). Mismo nombre con
  bytes distintos no pisa el original: guarda `...rev2.zip`, `...rev3.zip` y avisa por stderr.
- Escritura atómica y `manifest.csv` con una línea por corrida (fecha UTC, nombre, bytes,
  sha256, archivo escrito, estado `nuevo`/`ya_archivado`/`revision`; sin rutas absolutas).
- Códigos de salida: 0 éxito (incluye ya archivado), 1 error de red o validación, 2 argumentos
  inválidos. Hasta 2 reintentos con espera ante 5xx y timeouts.
- La programación diaria (tarea programada o cron) está pendiente de decisión del usuario:
  no hay nada programado.

## Tests

```
apps/backend/.venv/Scripts/python.exe -m pytest scripts/verificacion/tests -q -p no:cacheprovider
```

Los tests no usan red: un cliente falso sirve un mundo sintético (ventanas y sesgos
conocidos).

## Módulos

| Módulo | Qué hace |
|--------|----------|
| `regtemp.py` | Parseo del archivo `regtemp` (ancho fijo, latin-1). |
| `stations.py` | 14 estaciones SMN -> ICAO, WMO, lat, lon (AWC `stationinfo`, 2026-10-05; `metar.py` tiene 3 ICAO erróneos que no se usan). |
| `aggregation.py` | Tmax/Tmin diarios desde una serie horaria UTC con ventana y mínimo de horas válidas. |
| `alignment.py` | Ranking por MAE de ventanas candidatas contra el SMN, Tmax y Tmin por separado. |
| `window_selection.py` | Suma el ranking de todas las estaciones y modelos, elige o fuerza la ventana. |
| `metrics.py`, `combos.py` | Errores, sesgo/MAE/RMSE con n; combinaciones; 2 pliegues cronológicos sin fuga; resumen por estación. |
| `openmeteo_client.py` | Cliente HTTP con caché, límite de llamadas, pausa y reintentos con backoff (sin claves). |
| `openmeteo_series.py` | Validación de respuestas, trozos de fechas y unión de series. |
| `pipeline.py` | Plan, descarga, alineación de ventana, casos y métricas. |
| `outputs.py`, `report.py` | `resumen.md`, CSV y `metadatos.json` (tablas en español). |
| `medir_tmax_tmin.py` | CLI de la medición. |
| `archivar_datohorario.py` | Archivador diario del zip `datohorario` del SMN. |

## Qué se verificó de la API (2026-10-05)

Docs leídas: https://open-meteo.com/en/docs/previous-runs-api y
https://open-meteo.com/en/pricing. Endpoint: `https://previous-runs-api.open-meteo.com/v1/forecast`.

Verificado en la doc: `temperature_2m_previous_day1..7` (y día 0 = `temperature_2m`);
la API soporta los mismos modelos que la Forecast API; historial de la mayoría de los modelos
desde enero 2024 y GFS temperatura 2 m desde marzo 2021; regla de peso de la página de
precios (una llamada cubre hasta 10 variables y 14 días; más se cuenta fraccionado: 15 variables
x 14 días = 1,5 y 15 x 28 días = 3,0); límites gratuitos (600/min, 5.000/hora, 10.000/día).

Verificado con 3 llamadas reales (una estación, Ezeiza, 7 días o menos):
1. `models=ecmwf_ifs025,gfs_global`, 2026-09-28 a 2026-10-04: HTTP 200, columnas
   `temperature_2m_<modelo>` y `temperature_2m_previous_day{1..7}_<modelo>`, 168 horas, sin nulos.
2. Mismo pedido para 2025-10-05 a 2025-10-11 (inicio del período): HTTP 200, 168 horas, sin
   nulos en las 16 columnas (ambos modelos tienen `previous_day1..7` en el período).
3. Un solo modelo (`ecmwf_ifs025`, 1 día): las columnas vienen sin sufijo.

`timezone=GMT` devuelve `utc_offset_seconds=0`. La API devuelve el punto de grilla más cercano
(0,25°; Ezeiza -> -34.75/-58.5, elevación 18 m), no la coordenada pedida.

No verificado: cuántos días admite una llamada (se usa 92 por defecto, configurable con
`--chunk-dias`); si el peso se multiplica por la cantidad de modelos (se asume que sí, de forma
conservadora); el comportamiento de la API para fechas del día de hoy; la descarga del zip del
SMN y el nombre del archivo dentro del zip (se toma el primero que contenga `regtemp`).
