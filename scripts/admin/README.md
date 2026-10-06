# Monitor local de SkyPulse (FRA-329)

Mini monitor de administración para el dueño: corre **en tu PC, en la terminal**, no forma
parte de producción y **no escribe nada** (solo pedidos GET; a Upstash solo le manda el
comando `GET`). No usa dependencias externas: alcanza con Python 3.12 o más.

## Qué muestra

1. **Cupos del día**: los contadores `skypulse:<servicio>:counter:AAAA-MM-DD` (día UTC) que
   escribe el backend en Upstash, contra su cupo: Open-Meteo 10.000 por día y CheckWX 198.
   Barra de uso y estado: OK, ATENCIÓN desde el 70 %, CRÍTICO desde el 90 %. También muestra,
   sin cupo propio, `smn_alertas` y `metar_awc`. Una clave ausente cuenta 0; si Upstash no
   responde lo dice y sigue.
2. **Estado de producción** (`skypulse-api-mund.onrender.com`): `/api/weather/dashboard`
   (`model=consensus`) para Córdoba, Buenos Aires y Resistencia, más `/api/niebla` y
   `/api/alertas-smn`. Muestra HTTP, latencia, fuente y motivo del "ahora", estación METAR y
   distancia, antigüedad del dato y modelos del pronóstico. Marca 429, 503 y respuestas de
   más de 3 s. `available: no` en los avisos del SMN no alarma: esa fuente está caída y se sabe.
3. **Fuentes externas**, directo desde tu PC (la IP **no** es la de Render): AWC METAR de SACO,
   feed CAP del SMN (cantidad de ítems), endpoint viejo de avisos del SMN (hoy 404: "caído
   conocido") y **una** consulta a Open-Meteo, que cuenta contra el cupo de la IP de tu PC.
4. **Comparación de modelos**: tabla de 7 días por ciudad con temperatura y lluvia de GFS y
   ECMWF contra la fila que ve el usuario. Marca `DESACUERDO` cuando un modelo supera 0,9 mm
   y el otro no (0,9 exacto no supera) y cuenta los días. Si falta un modelo, lo dice.
5. **Resumen** con una línea por sección y el estado general.

## Cómo correrlo

Desde la raíz del repo, con el Python del venv del backend:

```
PY=G:/Developer/1Proyectos/SkypulseAR/apps/backend/.venv/Scripts/python.exe
$PY scripts/admin/monitor.py --env-file RUTA/AL/ARCHIVO.env
```

| Opción | Efecto |
|---|---|
| `--env-file RUTA` | Archivo con `UPSTASH_REDIS_REST_URL` y `UPSTASH_REDIS_REST_TOKEN`. Sin esto se omite la sección 1 con un aviso. |
| `--ciudades cordoba,caba,resistencia` | Ciudades a consultar (las tres por defecto). La niebla usa la primera. |
| `--sin-fuentes` | Omite la sección 3. |
| `--no-modelos` | Omite la sección 4. |
| `--json` | Misma información en JSON, sin colores. |

Las credenciales se cargan **en tiempo de ejecución** con un parser propio de `CLAVE=valor`
(acepta comentarios, comillas, `export` y UTF-8 o UTF-16) y no se imprimen nunca, ni en la
salida ni en los errores. Si Upstash falta en el archivo, el error nombra las variables, no
los valores. Colores ANSI solo en una terminal; se apagan con `NO_COLOR=1`.

Las variables de Upstash viven en Render. Si tu `.env` local del backend no las tiene,
pasá con `--env-file` un archivo que sí las tenga.

## Códigos de salida

| Código | Significado |
|---|---|
| 0 | Todo OK |
| 1 | ATENCIÓN (cupo desde 70 %, respuesta lenta, falta un modelo, una fuente externa falla, Upstash sin respuesta) |
| 2 | CRÍTICO (cupo desde 90 %, producción con 429, 503 u otro error, sin respuesta) |
| 3 | Error de uso o de configuración (opción inválida, archivo ilegible, faltan variables) |

## Costo en llamadas

Una corrida completa hace 13 pedidos: 4 a Upstash, 5 a producción (3 ciudades, niebla y
avisos) y 4 a fuentes externas. Cada `dashboard` puede hacer que el backend consulte Open-Meteo
desde la IP de Render si no está en su caché, así que no lo corras en bucle.

## Tests

```
$PY -m pytest scripts/admin/tests -q -p no:cacheprovider
ruff check scripts/admin
```

Los tests no usan red externa ni credenciales reales: clientes HTTP falsos y dos servidores
locales en `127.0.0.1`.
