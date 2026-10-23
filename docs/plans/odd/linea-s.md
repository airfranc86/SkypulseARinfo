# Línea S — SIGMETs de Argentina (FRA-368)

## Specs

**S1.** Preparar la base SIGMET leyendo código: listar las cinco consultas AWC actuales (`metar.py:37-38`, `metar_observation.py:30`, `taf_decoded.py`) y sus puntos de reunión, para que el adapter SIGMET entre al seam de la Fase 1 y no sea un fetch escrito a mano. Criterio de decisión: la Fase 1b está completada; si T7b no está estable en el momento de S2, S1 se detiene y S2/S3 con el S3 requiere T7b.

**S2.**Implementar el adapter SIGMET para la Fase 1b (rotante): `services/sigmet.py` + `schemas/sigmet.py`, integración al seam de Fase 1 (no un fetch más), caché con TTL 5 min, contador `sigmet_awc`, bandera `SIGMET_ENABLED` apagada produção.

**S3.** Implementar el endpoint completo `GET /api/sigmet?lat&lon&radio_km`: lectura de AWC `/api/data/isigmet`, caché 5 min, counter `sigmet_awc`, bandera `SIGMET_ENABLED`, var `VITE_SIGMET_VISIBLE`. Banderá apagada la ruta responde 404.

## Tasks

| ID | Linked | Route | Commit |
|---|---|---|---|
| L1 | S1 | explore | L1 |
| L2 | S2 | implement | L2 |
| L3 | S3 | implement | L3 |

## Log

L1: Concurrí la delegación Línea S (S1/S2/S3). [user: «sigamos con Linea S»]
L2: Effort: high → medium (confirmado por usuario para modelo de IA, 2026-10-22).
