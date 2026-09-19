# CLAUDE.md — SkyPulse

## Generación de tarjetas de contenido (Nubes / Desastres)

Para generar, redactar o ajustar tarjetas de contenido de fenómenos (meteorológicos en Nubes, o de impacto global en Desastres) — prompt de imagen + tarjeta corta con formato fijo —, usá el skill `skypulse-content-card`. Ese skill define el formato completo, el catálogo, los guardrails y el módulo extendido de Desastres Naturales; no lo dupliques acá.

---

## ⚠️ Límites de Alcance — Activo vs Legado

### Mapa de proyectos

| Directorio | URL de deploy | Estado |
|-----------|--------------|--------|
| `apps/frontend/` | `https://skypulse-ar.vercel.app` | ✅ **Activo** — todo el trabajo va aquí |
| `apps/backend/` | Backend en Render | ✅ **Activo** — todo el trabajo va aquí |
| `src/` | `https://skypulseinfo.vercel.app` | ❌ **LEGADO — NO TOCAR** |

### Regla CRÍTICA e irrevocable

> **`src/` y `skypulseinfo.vercel.app` son proyectos LEGADOS.**
> No se deben hacer cambios en ningún archivo dentro de `src/`.
> No se deben hacer auditorías, refactorizaciones, ni correcciones sobre `skypulseinfo.vercel.app`.
> TODO el desarrollo ocurre EXCLUSIVAMENTE en `apps/`.

Si algo en `src/` parece roto o mejorable → ignorarlo. No es nuestro proyecto activo.

---

## Suite de Auditoría — Stack SkyPulse

Este proyecto usa **FastAPI (Python)** + **React + TypeScript + Vite + Tailwind v4**.
Antes de proponer cualquier cambio de código, activá el skill correspondiente según la tarea y presentá un reporte de hallazgos (P0–P3). **No hacer cambios a ciegas** — toda refactorización debe estar fundamentada en los resultados del skill.

### Severidad de hallazgos

| Nivel | Criterio | Acción |
|-------|----------|--------|
| **P0** | Seguridad crítica / dato incorrecto / build roto | Detener y corregir antes de continuar |
| **P1** | Bug con impacto en usuario / test roto / fuga de API key | Corregir en la misma sesión |
| **P2** | Degradación de performance / deuda técnica significativa | Reportar y planificar |
| **P3** | Mejora de calidad / naming / accesibilidad menor | Registrar para futura iteración |

### 1. Auditoría de Frontend

Activar cuando: se toca cualquier archivo en `apps/frontend/src/`.

```
/audit          → UI/UX, accesibilidad (WCAG), contraste, touch targets
/vercel-react-best-practices → Performance React/Vite, bundle size, lazy loading, memoización
/ui-ux-pro-max  → Design system compliance, responsive, motion, patrones de interacción
```

### 2. Auditoría de Backend

Activar cuando: se toca cualquier archivo en `apps/backend/app/`.

```
/fastapi-python            → Arquitectura de la API, dependency injection, schemas Pydantic
/python-performance-optimization → Cuellos de botella, async patterns, caching TTL, N+1 queries
/python-review             → PEP8, type hints, error handling, inmutabilidad
```

### 3. Auditoría de Seguridad

Activar antes de cualquier commit que toque: routers, config, servicios externos, variables de entorno.

```
/security-review      → Escaneo full-stack: secrets, CORS, rate limiting, input validation
/api-security-audit   → Endpoints FastAPI: autenticación, autorización, exposición de datos
```

### 4. Pre-deploy

Activar antes de cualquier push a producción.

```
/predeploy → 7 checks: .gitignore, env vars, secrets hardcodeados, URLs hardcodeadas,
             tests (suite completa), tipos vs schema, TODOs críticos
```

### Flujo obligatorio antes de refactorizar

1. Correr el skill correspondiente a la zona de cambio
2. Presentar reporte P0–P3 al usuario
3. Confirmar qué hallazgos se van a atacar en esta sesión
4. Implementar solo los cambios acordados
5. Re-correr el skill para verificar que los P0/P1 están resueltos

### Gotcha — cliente httpx compartido

`apps/backend/app/core/http_client.py` provee un singleton `AsyncClient` compartido.
Al migrar un servicio de `async with httpx.AsyncClient(...) as client:` a `get_client()`:

1. **Eliminar `import httpx`** del servicio, pero **re-importar explícitamente** las excepciones que se usan en `except`:
   ```python
   from httpx import HTTPStatusError, TimeoutException as HttpxTimeout
   ```
   Si quedó `except httpx.TimeoutException:` con `httpx` no importado → `NameError` en runtime.

2. **Tests**: El fixture `init_shared_http_client` (autouse en conftest.py) inicializa el singleton antes de cada test. `respx.mock` intercepta al cliente compartido correctamente.

3. **Timeout por call**: el singleton no tiene timeout global; pasar `timeout=settings.http_timeout_seconds` en cada `.get()`/`.post()`.

### Gotcha — Windy (plan Testing)

La key de Windy de producción es del plan *Testing* (gratis): según [su página de precios](https://api.windy.com/point-forecast/pricing) "returns randomly shuffled and slightly modified data" y no sirve para producción (además `past3hprecip` llega en metros, no en mm). **No mostrarle al usuario nada que salga de Windy** (`services/windy.py`). El dashboard de Previsión ya sale entero de Open-Meteo; las herramientas (tender-ropa, hacer-deporte, lavar-coche, cota de nieve, incendios) todavía lo consumen y están pendientes de migrar. Para validar un dato de pronóstico, compararlo con Open-Meteo GFS en los mismos instantes UTC: una serie física real tiene autocorrelación alta entre franjas vecinas (la de Windy daba −0,10).

---

## Reglas Git — este proyecto

> Estas reglas son adicionales a las globales en `~/.claude/CLAUDE.md`.

- **Nunca incluir archivos de `docs/` en un commit o push**, salvo que el usuario lo pida explícitamente.
- Los archivos de `docs/` son documentación interna (planes, auditorías, GTM, etc.) que no va al repositorio remoto.
- Si al hacer `git add` o `git commit` hay archivos de `docs/` staged → detener y avisar antes de continuar.

---

## Cuaderno NotebookLM — Fuente de verdad del proyecto

El proyecto tiene un cuaderno NotebookLM permanente con información técnica verificada:

- **ID:** `ccca882a-155e-4425-84f4-5107a3e6f553`
- **URL:** `https://notebooklm.google.com/notebook/ccca882a-155e-4425-84f4-5107a3e6f553`

**Protocolo obligatorio:**
- Antes de tomar decisiones técnicas sobre fuentes de datos, APIs externas o arquitectura, consultá este cuaderno.
- Cuando se complete una wave de auditoría o se agregue una feature significativa, actualizá el cuaderno con los nuevos hallazgos.
- El cuaderno es la fuente de referencia más confiable sobre el estado actual del proyecto.

Para actualizar: usá la herramienta `mcp__notebooklm-mcp__notebook_query` con el ID del cuaderno.
