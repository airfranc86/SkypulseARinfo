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

El workflow `.github/workflows/isobaras.yml` pregunta por un ciclo nuevo **cada 20 minutos** (a los minutos 7, 27 y 47 de
cada hora, nunca a la hora en punto, que es cuando GitHub más atrasa las corridas programadas). NOAA publica un ciclo cada
6 horas (00, 06, 12 y 18 UTC, completo unas 4 h 45 min después), pero GitHub retrasa las corridas programadas, a veces por
horas, y descarta algunas: preguntando seguido, una corrida tardía o perdida atrasa el mapa unos minutos y no un ciclo
entero. Si el ciclo ya está publicado, la corrida termina en segundos sin desplegar nada, así que preguntar seguido casi
no cuesta (el repo es público). También se puede lanzar a mano desde Actions → isobaras → Run workflow. Solo publica desde
`main`.

El trabajo `test` corre en cada pull request que toque `scripts/isobaras/**` o el workflow, y antes de cada publicación
(en las corridas programadas y a mano): como `main` no tiene protección de rama, es lo que impide que un `main` roto
llegue a los usuarios. El trabajo `generar` solo arranca si `test` pasó, y baja y arma los archivos si hay ciclo nuevo;
el trabajo `desplegar`, el único con el entorno de Pages y los permisos de escritura, solo corre en ese caso: las
corridas que no encuentran nada nuevo no dejan registros de despliegue.

### Si GitHub igual atrasa las corridas

La programación de GitHub es "lo mejor posible", sin garantía de horario. Si el mapa sigue mostrando el aviso de
"isobaras no actualizadas" con frecuencia, hay una segunda capa gratuita y confiable: un disparador externo que lance el
workflow por la API de GitHub, por ejemplo con un horario de QStash (plan Free) cada 20 minutos que haga
`POST https://api.github.com/repos/airfranc86/SkypulseARinfo/actions/workflows/isobaras.yml/dispatches` con el cuerpo
`{"ref":"main"}`. Necesita un token fino de GitHub limitado a este repositorio con el único permiso *Actions: Read and
write*, que se guarda como encabezado reenviado en el propio QStash: **nunca** en el repositorio ni en el chat. Ojo con
el alcance: ese permiso también puede cancelar, repetir o borrar corridas y lanzar cualquier otro workflow del repo, y
cada disparo corre también `test`, así que conviene un token con vencimiento y revisarlo si se sospecha de una fuga.

## Qué hacer si falla

- **El job quedó en rojo:** Pages sigue sirviendo el último deploy bueno; el mapa muestra la edad del dato (aviso a las
  12 h, aviso fuerte a las 36 h). Mirá el log del paso que ejecuta `isobaras_core.pipeline` (en Actions aparece como
  "Run uv run python -m isobaras_core.pipeline …").
- **Código 2 ("no se publica"):** ninguno de los últimos cuatro ciclos (unas 18 horas) tiene el índice de las 41 horas.
  Si un ciclo todavía se está subiendo, el pipeline usa el anterior y termina en "ciclo ya publicado" (código 0), así
  que el código 2 indica algo más serio: un corte de NOAA o un cambio en el bucket. Mirá
  https://www.nco.ncep.noaa.gov/pmb/nwprod/prodstat/ y, si el bucket cambió, el `ciclo.py`.
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
| `base.py` | Arma una sola vez el fondo del mapa (costas y fronteras de Natural Earth, recortadas y simplificadas). |
| `ciudades.py` | Arma una sola vez la lista de ciudades del mapa (Natural Earth, 6 países, con nivel según el tamaño) como un módulo de TypeScript. |
| `pipeline.py` | La corrida completa que ejecuta el workflow. |
| `descarga.py` | Baja una hora y la describe (para probar a mano). |

## Fuentes y licencias

Datos: NOAA GFS, del conjunto abierto `noaa-gfs-bdp-pds` (Open Data on AWS). Las isobaras son datos de NOAA
**modificados por SkyPulse**: no se debe dar a entender que son originales ni que NOAA avala a SkyPulse ni está
afiliada a él (así lo piden las condiciones de ese conjunto). Fondo del mapa (costas, fronteras y ciudades): Natural Earth,
de dominio público, de uso comercial permitido y sin atribución obligatoria (el mapa la nombra igual). No hay ninguna
clave ni servidor de mapas de terceros. Los créditos están en la página "De dónde salen los datos".

## El fondo del mapa (costas y fronteras)

`apps/frontend/public/mapa/base.json` se genera una sola vez con `isobaras_core/base.py` y se commitea; la web lo lee
de su propio sitio. Baja tres capas de Natural Earth (costa a 1:50 millones, fronteras entre países a 1:50 millones y
límites de provincias a 1:10 millones: la de 1:50 solo trae las provincias de unos pocos países, entre los que no está
Argentina), las recorta a una caja un poco más grande que lo que el mapa deja ver (lat −74 a 0, lon −102 a −18) y las
simplifica (0,03°). Pesa ~50 KB (~20 KB con gzip). Solo hay que volver a generarlo si cambia la caja o la tolerancia:

```bash
uv run python -m isobaras_core.base      # baja ~25 MB de GitHub y reescribe apps/frontend/public/mapa/base.json
```

Las Malvinas salen como costa y sin ninguna línea de frontera (se bajan solo las fronteras terrestres).

## Las ciudades del mapa

`apps/frontend/src/lib/mapa/ciudadesDatos.ts` se genera una sola vez con `isobaras_core/ciudades.py` y se commitea; la web
lo importa (no pide nada a la red). Baja los lugares poblados de Natural Earth v5.1.2 (~5 MB), se queda con los de
Argentina, Chile, Uruguay, Paraguay, Bolivia y Brasil que caen en la zona de los datos (lat −62 a −12, lon −90 a −30) y
les da un nivel: 1 (capitales nacionales y ciudades de más de 1,5 millones: siempre se ven), 2 (capitales de
provincia de más de 50 mil habitantes y ciudades de más de 500 mil) y 3 (el resto, solo con zoom). Brasil pide más
gente en los tres niveles, porque en la zona tiene ~240 lugares, muchos de ellos suburbios. Un lugar que no es capital
y está a menos de 0,5° de uno más grande se descarta (Santo André junto a São Paulo). Los nombres que dos países
comparten llevan el país: "Concepción (CL)".

La fuente tiene datos viejos en esta región, así que el script lleva dos tablas chicas y explícitas
(`EXCLUIDAS` y `RENOMBRADAS`). Solo hay que volver a generar el archivo si cambia la zona, los países o los umbrales:

```bash
uv run python -m isobaras_core.ciudades      # baja ~5 MB de GitHub y reescribe ciudadesDatos.ts
```

Qué ciudades se dibujan en cada zoom y cómo no se pisan los nombres lo decide `apps/frontend/src/lib/mapa/ciudades.ts`.
Las Malvinas no aparecen como ciudad de ningún país: la fuente las archiva bajo el Reino Unido, que no está en la lista.
