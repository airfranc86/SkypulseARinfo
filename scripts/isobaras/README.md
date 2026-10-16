# Isobaras: el pipeline del mapa de presión

Genera los archivos que lee la página `/mapa` de SkyPulse a partir de la presión a nivel del mar del modelo GFS de
NOAA (0,25°, hasta 5 días —120 horas— desde la corrida del modelo, en pasos de 3 horas) y los publica en GitHub
Pages. No toca el backend ni Render.

## Qué produce

Un `manifest.json` y un `isobaras_fNNN.json` por hora de pronóstico (41 horas: f000, f003 … f120; f000 es la hora de
la corrida del modelo, que ya tiene unas 5 horas cuando se publica). Cada archivo trae las curvas cada 4 hPa, dónde
van las etiquetas y los centros de alta y baja. El formato (contrato v1) está en `isobaras_core/formato.py` y su espejo
en `apps/frontend/src/lib/isobaras/formato.ts`; los dos lados se prueban contra los mismos archivos de
`apps/frontend/tests/fixtures/isobaras/`. Los archivos de un ciclo pesan ~370 KB en total (~110–130 KB con gzip).

## Cómo correrlo a mano

Hace falta [uv](https://docs.astral.sh/uv/). Desde esta carpeta:

```bash
uv sync --locked                                   # instala lo fijado en uv.lock
uv run pytest -q                                   # los tests (no usan internet)
uv run python -m isobaras_core.descarga --f 0      # baja y decodifica una hora, sin generar nada
uv run python -m isobaras_core.pipeline --salida out            # genera las 41 horas en ./out
uv run python -m isobaras_core.pipeline --dry-run               # hace todo menos escribir
```

La corrida completa tarda ~2 minutos (descarga ~41 MB de NOAA). `out/` y `data/` están en el `.gitignore`. El
pipeline se niega a escribir en un directorio con archivos que no son suyos.

**Ojo:** antes de bajar nada, el pipeline mira qué ciclo sirve Pages (`--publicado-url`, por defecto el sitio del
proyecto). Si ya es el elegido (o uno más nuevo), termina con "ciclo ya publicado" y no genera nada. Para forzar una
corrida completa a mano, apuntalo a una URL que no responda:

```bash
uv run python -m isobaras_core.pipeline --salida out --publicado-url http://127.0.0.1:9
```

Códigos de salida del pipeline: `0` listo (o "ciclo ya publicado"), `2` ningún ciclo reciente tiene el índice de las
41 horas (no se publica), `3` el índice no trae PRMSL, `4` error de red o de datos. Con `--github-output` escribe
`publicar=true|false` y `ciclo=…` para el workflow.

## Cuándo corre solo

El workflow `.github/workflows/isobaras.yml` corre a las 04:45, 10:45, 16:45 y 22:45 UTC (4 h 45 min después de cada
corrida del modelo de NOAA: 00, 06, 12 y 18 UTC) y otra vez una hora después como reintento. Si el ciclo ya está
publicado, termina sin desplegar. También se puede lanzar a mano desde Actions → isobaras → Run workflow. Solo publica
desde `main`. El trabajo `test` corre además en cada pull request que toque `scripts/isobaras/**` o el workflow.

## Qué hacer si falla

- **El job quedó en rojo:** Pages sigue sirviendo el último deploy bueno; el mapa muestra la edad del dato (aviso a las
  12 h, aviso fuerte a las 36 h). Mirá el log del paso que ejecuta `isobaras_core.pipeline` (en Actions aparece como
  "Run uv run python -m isobaras_core.pipeline …").
- **Código 2 ("no se publica"):** NOAA todavía no terminó de subir el ciclo (llega fuera de orden). El reintento de una
  hora después suele resolverlo. Si pasa varias veces seguidas, revisá https://www.nco.ncep.noaa.gov/pmb/nwprod/prodstat/
- **Código 4 con "no se pudo bajar":** el bucket público de NOAA (`noaa-gfs-bdp-pds`) no respondió; reintentar.
- **`eccodes` no se instala en Linux:** las ruedas de `eccodes`, `eccodeslib` y `eckitlib` están fijadas en `uv.lock`
  para Python 3.12 (el workflow lo fija). El trabajo `test` de cada pull request lo prueba en `ubuntu-latest`.

## Cómo está armado

| Módulo | Qué hace |
|---|---|
| `ciclo.py` | Elige el ciclo completo más reciente (el `.idx` de las 41 horas) y arma las URL. |
| `idx.py` | Lee el `.idx` y encuentra el rango de bytes de una variable (PRMSL pesa ~1 MB, no los ~500 MB del archivo). |
| `grib.py` | Decodifica el GRIB2 con eccodes leyendo la orientación del propio mensaje: latitud ascendente, longitud de −180 a 180. |
| `red.py` | Lo único que usa internet (solo biblioteca estándar): exige 206 con el rango pedido, topa lo que lee, reintenta 5xx. |
| `curvas.py` | Suaviza (sigma de 2 celdas), traza cada 4 hPa con contourpy, simplifica (Douglas-Peucker de 0,03°) y ubica etiquetas. |
| `centros.py` | Altas y bajas: extremo de una ventana de ~5° que se destaca 2 hPa, a más de 1° del borde y fuera de terreno de más de 1500 m. |
| `formato.py` | El contrato v1: lee y valida (con topes de tamaño) y escribe el manifest y los archivos de hora. |
| `hora.py` | Arma cada archivo de hora y el manifest, y los valida con el lector del contrato antes de escribirlos. |
| `pipeline.py` | La corrida completa que ejecuta el workflow. |
| `descarga.py` | Baja una hora y la describe (para probar a mano). |

## Fuentes y licencias

Datos: NOAA GFS, del conjunto abierto `noaa-gfs-bdp-pds` (Open Data on AWS). Las isobaras son datos de NOAA
**modificados por SkyPulse**: no se debe dar a entender que son originales ni que NOAA avala a SkyPulse ni está
afiliada a él (así lo piden las condiciones de ese conjunto). Fondo del mapa: CARTO, con la atribución
"© OpenStreetMap contributors, © CARTO" (clave gratuita en la variable `VITE_CARTO_API_KEY` de Vercel; si falta, el
mapa muestra las isobaras sobre el color liso del tema). Los créditos están en la página "De dónde salen los datos".
