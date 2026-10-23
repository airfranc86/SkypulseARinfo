# Línea S SIGMET adapter entra al seam de la Fase 1

**Contexto:** La capa SIGMET (FRA-368) debe consultar AWC (`/api/data/isigmet`) sin duplicar el cliente HTTP ni el módulo de pronóstico meteorológico.

**Decisión:** El adapter SIGMET (`services/sigmet.py`) usa el cliente compartido del módulo de la Fase 1 (`metar.py`) como única referencia; el endpoint `/api/sigmet` responde con 404 mientras `SIGMET_ENABLED` sea `False`, protegiendo producción. No se crea ningún fetch independiente fuera de este adapter.

**Por qué:** Evita duplicación del cliente AWC (cupo de 100/min), mantiene el contrato de Fase 1 intacto y permite un rollout progresivo (bandera). Difícil de revertir porque cualquier cambio en el cliente AWC afectaría ambas rutas simultáneamente.

**Estado:** accepted
**Consecuencias:** Si T7b (FRA-357) no está estable en producción, `SIGMET_ENABLED` debe permanecer `False`; el adapter existe pero no expone datos nuevos hasta que la bandera se active con confirmación del dueño.
