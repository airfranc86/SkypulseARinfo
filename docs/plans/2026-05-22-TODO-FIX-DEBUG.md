# TODO-FIX-DEBUG — 2026-05-22

Estado: **PENDIENTE**

---

## [1] ✅ METAR API — RESUELTO (2026-05-22)

**Contexto:**  
La función `apps/frontend/api/metar.js` devolvía HTTP 500.  
Root cause: `package.json` tiene `"type": "module"` → Node interpreta todos los `.js` como ESM.  
El handler usaba `module.exports` (CommonJS) → syntax error silencioso.

**Fix aplicado:** commit `526fac3`  
Convertido a `export default async function handler(req, res)`.  
Simplificado `vercel.json` (eliminado rewrite `/api/(.*)` innecesario).

**Acción pendiente:**  
Confirmar en `https://skypulse-ar.vercel.app/metar` que el widget responde con datos reales (SAEZ, EGLL, etc.) y no retorna 500.  
Si sigue fallando → ejecutar agente `debugger` con foco en Vercel function runtime + env var `CHECKWX_KEY`.

**Archivos involucrados:**
- `apps/frontend/api/metar.js`
- `apps/frontend/vercel.json`
- `apps/frontend/package.json` (`"type": "module"`)

---

## [2] Terremotos — Mejoras UI (brainstorming pendiente)

**Contexto:**  
Task planificada pero no iniciada por límite de contexto.  
Se pidió ejecutar agentes de diseño/debug para estos dos cambios:

### 2a — Columna "Fecha" mobile-responsive en DataTable

**Problema:** el texto de la columna `Fecha` se corta o desborda en pantallas pequeñas.  
**Acción:** revisar `src/pages/Terremotos.tsx` — el `DataTable` usa columnas fijas; ajustar con `truncate`, `min-w-0`, o mostrar fecha compacta (`DD/MM HH:mm`) en mobile via responsive variants de Tailwind v4.

### 2b — Barra visual de escala de magnitud Mw

**Problema:** el usuario no sabe qué significa M2.0, M5.0, M7.0+ sin referencia.  
**Acción:** implementar un componente `MagnitudeScale` debajo de la tabla.  
Design spec:
- Mobile-first, design system dark gold `#c8a84b`
- Segmentos de escala con comparaciones domésticas:
  - M < 2.0 → inapreciable
  - M 2.0–3.9 → camión pasando cerca
  - M 4.0–4.9 → ventilador industrial / ventanas vibran
  - M 5.0–5.9 → explosión grande / daños menores
  - M 6.0–6.9 → daños estructurales severos
  - M 7.0+ → catastrófico
- Resaltar el rango del sismo más reciente visible en la tabla

**Archivos a modificar:**
- `apps/frontend/src/pages/Terremotos.tsx`
- (opcional) extraer `MagnitudeScale.tsx` en `src/components/`

---

## Orden de resolución sugerido

1. Verificar METAR en prod → si OK, cerrar [1]
2. Implementar [2a] (fix rápido, < 30 min)
3. Implementar [2b] (nuevo componente, ~1h)
4. Build + deploy → verificar ambos en mobile

---
