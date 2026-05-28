# Plan de Ingeniería — Configuración GTM + GA4 + Sentry

**Última actualización:** 2026-05-28  
**Estado del plan:** ✅ Refinado contra el código real del proyecto (post-Ops Wave)

---

## Contexto del Proyecto

```
Stack real verificado:
- Frontend: React 19.2.6, TypeScript 6.0.2, Vite 8.0.12, Tailwind CSS v4.3.0
- Router: react-router-dom v6+ (BrowserRouter / Routes / Route)
- Data fetching: TanStack Query v5.100.11
- Package manager: pnpm (NUNCA npm)
- Despliegue frontend: Vercel
- Backend: Python + FastAPI + uvicorn, despliegue Render detrás de Cloudflare
- Dependencias backend: requirements.txt (pip), sin lock file actualmente

Trackers existentes:
- GTM container: GTM-MBG7GFM2 (ya instalado en index.html)
- GA4 measurement: G-PCYPG8W1ZX (cargado vía gtag.js directo — A REMOVER)

CSP activa (vercel.json, configurada en Ops Wave 2026-05-28):
- default-src 'self'
- script-src 'self' 'unsafe-inline' https://www.googletagmanager.com
- style-src 'self' 'unsafe-inline'           ← falta fonts.googleapis.com
- font-src 'self' data:                       ← falta fonts.gstatic.com
- connect-src 'self' https://skypulse-api-mund.onrender.com
              https://www.google-analytics.com https://www.googletagmanager.com
              https://analytics.google.com    ← falta Sentry
- frame-src 'none'; object-src 'none'

Política anti-PII del proyecto:
- lat/lon redondeados a 2 decimales en logs (precisión ~1.1 km)
- No enviar coordenadas crudas a terceros
- Wave 1 control positivo #13
```

## Objetivo

Configurar GTM + GA4 + Sentry siguiendo buenas prácticas para una app React SPA
con backend FastAPI, **respetando la CSP, el package manager y las convenciones
del proyecto** (anti-PII, code splitting, sin secretos en bundle).

---

## PARTE 0 — Limpieza previa (BLOQUEANTE — hacer antes de PARTE 1)

### 0.1 — Eliminar `gtag.js` directo de `index.html`

`apps/frontend/index.html:16-23` carga GA4 de dos formas (GTM + gtag directo).
Esto genera doble carga y potencial doble tracking si GTM ya tiene una GA4 Config tag.

**Quitar este bloque** del `<head>`:

```html
<!-- BORRAR estas 7 líneas de apps/frontend/index.html -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-PCYPG8W1ZX"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-PCYPG8W1ZX', { send_page_view: false });
</script>
```

**Verificación previa:** abrir GTM (`tagmanager.google.com`, container `GTM-MBG7GFM2`)
y confirmar que existe una tag tipo "Google Analytics: GA4 Configuration" con
Measurement ID `G-PCYPG8W1ZX`. **Si no existe, créala primero** (ver PARTE 2.1)
antes de borrar el snippet directo, o GA4 deja de recibir datos.

### 0.2 — Actualizar CSP en `vercel.json`

La CSP actual rompe Google Fonts y bloquea Sentry. **Reemplazar** el bloque
`Content-Security-Policy` de `apps/frontend/vercel.json` por:

```json
{
  "key": "Content-Security-Policy",
  "value": "default-src 'self'; script-src 'self' 'unsafe-inline' https://www.googletagmanager.com https://www.google-analytics.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' data: https://fonts.gstatic.com; img-src 'self' data: blob: https://www.google-analytics.com https://www.googletagmanager.com; connect-src 'self' https://skypulse-api-mund.onrender.com https://www.google-analytics.com https://www.googletagmanager.com https://analytics.google.com https://*.ingest.sentry.io; worker-src 'self' blob:; frame-src 'none'; object-src 'none'; base-uri 'self'"
}
```

Cambios:
- `style-src`: agregado `https://fonts.googleapis.com` (CSS de Google Fonts)
- `font-src`: agregado `https://fonts.gstatic.com` (woff2 de Google Fonts)
- `img-src`: agregado pixel GA4 + pixel GTM
- `script-src`: agregado `https://www.google-analytics.com` (gtag library)
- `connect-src`: agregado `https://*.ingest.sentry.io` (envío de eventos Sentry)
- `worker-src 'self' blob:`: agregado (requerido por Sentry Replay)

### 0.3 — Crear declaración global de tipos

Para evitar conflictos de `window.dataLayer` entre `useGTMPageView.ts` y
`analytics.ts`, centralizar la declaración en un solo archivo:

```typescript
// apps/frontend/src/types/global.d.ts
export {}

declare global {
  interface Window {
    dataLayer: Record<string, unknown>[]
  }
}
```

Asegurar que `tsconfig.app.json` incluya `src/types/**/*.d.ts` (lo hace por
defecto si `include` apunta a `src`).

---

## PARTE 1 — GTM (Google Tag Manager)

### 1.1 — Snippet GTM en `index.html` (ya instalado, solo verificar)

✅ El snippet ya está bien colocado en `apps/frontend/index.html`:
- `<script>` GTM en `<head>` (líneas 4-10)
- `<noscript><iframe>` inmediatamente después de `<body>` (líneas 32-35)

No tocar nada acá — solo confirmar después de aplicar PARTE 0.1.

### 1.2 — Hook de Data Layer para SPA (React Router)

```typescript
// apps/frontend/src/hooks/useGTMPageView.ts
import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

export function useGTMPageView(): void {
  const location = useLocation()

  useEffect(() => {
    window.dataLayer = window.dataLayer || []
    window.dataLayer.push({
      event: 'virtual_pageview',
      page_path: location.pathname + location.search,
      page_title: document.title,
    })
  }, [location])
}
```

Notas:
- **No** redeclarar `window.dataLayer` acá — vive en `src/types/global.d.ts` (PARTE 0.3).
- Usar `useLocation` de `react-router-dom`. El hook local `@/hooks/useLocation`
  es para GPS, no confundir.

### 1.3 — Invocación en el componente raíz

`App.tsx` ya tiene `BrowserRouter` envolviendo `Routes`. El hook debe vivir
**dentro** del Router. Crear un componente intermedio:

```typescript
// apps/frontend/src/App.tsx (modificación)
import { useGTMPageView } from '@/hooks/useGTMPageView'

function RouterLayout() {
  useGTMPageView()
  return (
    <Routes>
      {/* ... rutas existentes ... */}
    </Routes>
  )
}

function App() {
  return (
    <BrowserRouter>
      <RouterLayout />
    </BrowserRouter>
  )
}
```

### 1.4 — Variables y triggers en GTM (consola web)

Configurar en `tagmanager.google.com` → container `GTM-MBG7GFM2`:

1. **Variable Data Layer** → `page_path` (tipo: Variable de capa de datos, nombre: `page_path`)
2. **Variable Data Layer** → `page_title`
3. **Trigger** → `Virtual Pageview` (tipo: Evento personalizado, nombre: `virtual_pageview`)
4. **Tag GA4 Event** → ver PARTE 2.2

---

## PARTE 2 — GA4 (Google Analytics 4)

### 2.1 — Configuración vía GTM (NO instalar gtag.js directo)

GA4 debe cargarse **solo a través de GTM**. El snippet directo `gtag.js`
ya fue removido en PARTE 0.1.

En GTM:

1. **Tag tipo "Google Analytics: GA4 Configuration"** (si no existe):
   - Measurement ID: `G-PCYPG8W1ZX`
   - Trigger: `All Pages` (única tag de config — carga inicial)
   - Configuración: marcar `send_page_view = false` en *Fields to Set* (el pageview
     SPA lo manda la tag del paso siguiente)

2. **Tag tipo "Google Analytics: GA4 Event"** — pageview SPA:
   - Event name: `page_view`
   - Parameters: `page_location` = `{{Page URL}}`, `page_title` = `{{DLV - page_title}}`
   - Trigger: `Virtual Pageview`

### 2.2 — Enhanced Measurement (evitar duplicar en GTM)

GA4 trae built-in vía **Admin > Property > Data Streams > Web Stream > Enhanced Measurement**:
- Scroll tracking (90% por defecto)
- Outbound clicks
- Site search
- File downloads
- Video engagement

**Activar todo en GA4 Admin** y **no crear tags GTM duplicadas** para scroll u
outbound clicks. Esto evita doble conteo y simplifica el container.

Eventos custom que SÍ requieren tag GTM (no built-in):

| Evento GA4 | Trigger GTM | Descripción |
|---|---|---|
| `view_weather_data` | Custom event desde dataLayer | Usuario consulta datos meteorológicos |
| `view_seismic_data` | Custom event desde dataLayer | Usuario consulta sismos |
| `view_volcano_alert` | Custom event desde dataLayer | Usuario consulta alertas volcánicas |
| `view_fire_danger` | Custom event desde dataLayer | Usuario consulta riesgo de incendio |
| `view_metar` | Custom event desde dataLayer | Usuario consulta aeródromo (cuando S-06 resuelva) |

> Nota: `engagement_time` está cubierto automáticamente por `engagement_time_msec`
> que GA4 envía con cada evento — **no** crear timers en GTM.

### 2.3 — Push de eventos custom desde React

```typescript
// apps/frontend/src/lib/analytics.ts
export function pushEvent(eventName: string, params: Record<string, unknown> = {}): void {
  window.dataLayer = window.dataLayer || []
  window.dataLayer.push({
    event: eventName,
    ...params,
  })
}
```

Uso (ejemplos respetando política anti-PII — sin lat/lon crudos):

```typescript
import { pushEvent } from '@/lib/analytics'

// OK: nombre de ciudad o región (no coordenadas crudas)
pushEvent('view_weather_data', { city: 'Buenos Aires', source: 'SMN' })

// OK: parámetros numéricos sin PII
pushEvent('view_seismic_data', { magnitude: 4.2, region: 'Mendoza' })

// OK: identificador del volcán
pushEvent('view_volcano_alert', { volcano: 'Copahue', alert_level: 'amarillo' })

// EVITAR: enviar lat/lon crudas
// pushEvent('view_weather_data', { lat: -34.6037, lon: -58.3816 })  ← NO
```

---

## PARTE 3 — SENTRY (Error Tracking + Performance)

### 3.1 — Instalación en Frontend (React + Vite)

```bash
pnpm add @sentry/react
pnpm add -D @sentry/vite-plugin
```

### 3.2 — Inicialización (antes de React render)

```typescript
// apps/frontend/src/main.tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import * as Sentry from '@sentry/react'
import './index.css'
import App from './App.tsx'

const SENTRY_DSN = import.meta.env.VITE_SENTRY_DSN

if (SENTRY_DSN && import.meta.env.PROD) {
  Sentry.init({
    dsn: SENTRY_DSN,
    environment: import.meta.env.MODE,
    release: import.meta.env.VITE_VERCEL_GIT_COMMIT_SHA || 'unknown',

    integrations: [
      Sentry.browserTracingIntegration({
        tracePropagationTargets: [
          'localhost',
          /^https:\/\/skypulse-api-mund\.onrender\.com/,
        ],
      }),
      Sentry.replayIntegration({
        maskAllText: true,      // política anti-PII del proyecto
        blockAllMedia: true,
      }),
    ],

    // Performance — 10% en prod (app pública, alta cuota)
    tracesSampleRate: 0.1,

    // Session Replay — 5% normal, 100% en sesiones con error
    replaysSessionSampleRate: 0.05,
    replaysOnErrorSampleRate: 1.0,

    // Filtrar ruido conocido
    beforeSend(event) {
      const firstFrame = event.exception?.values?.[0]?.stacktrace?.frames?.[0]
      if (firstFrame?.filename?.includes('extensions/')) return null
      return event
    },
  })
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Sentry.ErrorBoundary fallback={<p>Ha ocurrido un error inesperado.</p>}>
      <App />
    </Sentry.ErrorBoundary>
  </StrictMode>,
)
```

Notas:
- `enabled` reemplazado por guard `if (SENTRY_DSN && import.meta.env.PROD)` —
  `PROD` es `true` solo en builds de producción (Vite garantiza esto), evita
  envíos en dev, test y staging.
- `release` usa `VITE_VERCEL_GIT_COMMIT_SHA` (Vercel lo inyecta automático en
  build — no requiere variable adicional). Fallback `'unknown'` si falta.
- `maskAllText: true` + `blockAllMedia: true` alinea con política anti-PII.

### 3.3 — Source maps en Vite (sin exponerlos al público)

```typescript
// apps/frontend/vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import svgr from 'vite-plugin-svgr'
import { sentryVitePlugin } from '@sentry/vite-plugin'
import path from 'path'

export default defineConfig({
  plugins: [
    svgr({ /* config existente */ }),
    react(),
    tailwindcss(),
    sentryVitePlugin({
      org: process.env.SENTRY_ORG,
      project: 'skypulse-frontend',
      authToken: process.env.SENTRY_AUTH_TOKEN,
      disable: !process.env.SENTRY_AUTH_TOKEN,  // skip en dev local
    }),
  ],
  build: {
    sourcemap: 'hidden',  // genera .map para upload a Sentry pero NO los referencia en el bundle
  },
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: { /* config existente */ },
})
```

`'hidden'` mantiene el control positivo #5 del audit (.js.map devuelve 403):
Vercel sirve el bundle sin referencia a los `.map`, así que aunque existan no
son descubribles desde el frontend.

### 3.4 — Backend (FastAPI)

Agregar al `apps/backend/requirements.txt`:

```
sentry-sdk[fastapi]>=2.0.0
```

> El plan original sugería `pip install sentry-sdk[fastapi]` directo, pero eso
> no persiste en el deploy de Render. Render reinstala desde `requirements.txt`
> en cada build.

```python
# apps/backend/app/main.py (al inicio, antes de FastAPI())
import os
import sentry_sdk

SENTRY_DSN = os.getenv('SENTRY_DSN')
ENV = os.getenv('ENV', 'dev')

if SENTRY_DSN and ENV == 'prod':
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=ENV,
        release=os.getenv('RENDER_GIT_COMMIT', 'unknown'),
        traces_sample_rate=0.1,
        profiles_sample_rate=0.05,
        send_default_pii=False,   # alineado con anti-PII del proyecto
    )

# FastAPI lo detecta automáticamente — sin middleware manual
app = FastAPI(...)
```

Agregar en `render.yaml`:

```yaml
envVars:
  - key: ENV
    value: prod
  - key: WINDY_API_KEY
    sync: false
  - key: CORS_ORIGINS
    sync: false
  - key: SENTRY_DSN
    sync: false            # ← agregar
```

### 3.5 — Distributed tracing (frontend ↔ backend)

`browserTracingIntegration` ya propaga `sentry-trace` y `baggage` al backend
gracias a `tracePropagationTargets` (configurado en 3.2).

**Problema potencial con Cloudflare:** los planes Free/Pro de Cloudflare pueden
strippear headers no whitelisteados. Verificar en el dashboard:

1. Cloudflare → tu zona → **Rules → Transform Rules → Managed Transforms**
2. Confirmar que no haya regla "Remove visitor IP headers" o similar afectando
   `sentry-trace` / `baggage`.
3. Si los headers no llegan al backend, crear una **Transform Rule** custom
   que los preserve, o ver `https://developers.cloudflare.com/rules/transform/`.

Test rápido: en backend, loggear el header `sentry-trace` de una request del
frontend. Si llega → distributed tracing funciona.

---

## PARTE 4 — VERIFICACIÓN

### Checklist post-implementación

**Limpieza previa (PARTE 0):**
- [ ] `gtag.js` directo removido de `index.html` (B-02)
- [ ] CSP en `vercel.json` actualizada con Sentry + Google Fonts + worker-src
- [ ] `src/types/global.d.ts` creado con declaración de `window.dataLayer`

**GTM (PARTE 1):**
- [ ] Preview Mode de GTM muestra `virtual_pageview` al navegar entre rutas
- [ ] No hay tags GA4 duplicadas (solo una Config tag con `G-PCYPG8W1ZX`)
- [ ] `useGTMPageView()` invocado dentro del `<BrowserRouter>`

**GA4 (PARTE 2):**
- [ ] DebugView (GA4 > Admin > DebugView) muestra `page_view` en cada navegación
- [ ] Enhanced Measurement activado en Data Stream
- [ ] Eventos custom (`view_weather_data`, etc.) aparecen en Realtime
- [ ] **No** hay scroll tracking duplicado (GTM + GA4)
- [ ] Eventos no contienen `lat`/`lon` crudos (revisar payloads en DebugView)

**Sentry (PARTE 3):**
- [ ] `VITE_SENTRY_DSN` configurada en Vercel
- [ ] `SENTRY_AUTH_TOKEN` configurada en Vercel (build env var, no runtime)
- [ ] `SENTRY_ORG` configurada en Vercel
- [ ] `SENTRY_DSN` configurada en Render
- [ ] Test: `throw new Error('Sentry test')` aparece en sentry.io con stack trace legible
- [ ] Test: request al backend genera transacción conectada (distributed tracing)
- [ ] `.js.map` siguen devolviendo 403 en Vercel (control positivo #5 preservado)
- [ ] `sentry-sdk[fastapi]>=2.0.0` agregado a `requirements.txt`

**CSP / Headers:**
- [ ] Fuentes Playfair Display, DM Sans, JetBrains Mono cargan correctamente
- [ ] DevTools → Console no muestra violaciones de CSP
- [ ] Sentry envía eventos sin bloqueos (verificar `*.ingest.sentry.io` en Network)

**Performance:**
- [ ] Lighthouse score Performance ≥ 85 en mobile (sin regresión vs. pre-Sentry)
- [ ] `tracesSampleRate: 0.1` (no `0.2` ni `1.0`) en prod

### Variables de entorno necesarias

| Variable | Dónde se configura | Valor | Visible en bundle |
|---|---|---|---|
| `VITE_SENTRY_DSN` | Vercel (build + runtime) | DSN del proyecto frontend Sentry | ✅ Sí (DSN es público) |
| `VITE_VERCEL_GIT_COMMIT_SHA` | Vercel (auto-inyectado) | Hash del commit | ✅ Sí (no sensible) |
| `SENTRY_AUTH_TOKEN` | Vercel (solo build) | Token de sentry.io > Settings > Auth Tokens | ❌ No (token de upload) |
| `SENTRY_ORG` | Vercel (build) | Slug de la org en Sentry | ❌ No |
| `SENTRY_DSN` | Render (runtime) | DSN del proyecto backend Sentry | – (server-side) |
| `RENDER_GIT_COMMIT` | Render (auto-inyectado) | Hash del commit | – (server-side) |

> Convención del proyecto: variables `VITE_*` se inyectan en el bundle del
> frontend (públicas por diseño). Variables sin prefijo `VITE_` solo viven
> en build/runtime server-side.

---

## PARTE 5 — Privacidad y consideraciones legales

### 5.1 — Ley 25.326 (Argentina) + RGPD (tráfico EU)

GTM, GA4 y Sentry envían datos a terceros (Google, Functional Software Inc.).
Para una app pública sin login, las obligaciones mínimas son:

1. **Nota de privacidad accesible** desde el footer (puede ser una sola página
   o sección de Landing).
2. **Aviso de cookies/tracking** — banner simple o nota visible en el primer
   acceso es suficiente para Argentina; RGPD requiere consentimiento explícito
   antes de cargar trackers (a evaluar según tráfico EU real).
3. **GA4 anonimiza IP por defecto** desde 2023 — no requiere config adicional.
4. **Sentry `send_default_pii: false`** (configurado en 3.4) — no envía IP ni
   user agent identificable.
5. **Replay con `maskAllText: true`** (configurado en 3.2) — no captura texto
   visible que pueda ser PII.

### 5.2 — Datos que NO deben salir del proyecto

Política anti-PII heredada del audit interno:

| Dato | Acción |
|------|--------|
| `lat`/`lon` exactas | NUNCA en eventos GA4, NUNCA en logs Sentry crudos |
| `lat`/`lon` redondeadas a 2 decimales | OK en logs backend (ya implementado) |
| Nombre de ciudad/región | OK en eventos GA4 |
| User agent / IP | Sentry los redacta automáticamente con `send_default_pii: false` |
| API keys (Windy) | NUNCA expuestas — viven en backend env var (ya OK) |

---

## Notas operativas

- **GA4 se gestiona exclusivamente a través de GTM** — nunca instalar `gtag.js`
  directo (esto es lo que cambió en PARTE 0.1).
- **Sentry se instala en el código** (no vía GTM), tanto en frontend como backend.
- **Proyectos separados en Sentry**: `skypulse-frontend` y `skypulse-backend`
  con DSNs distintos. Esto permite cuotas y alertas independientes.
- **En producción, los source maps se uploadean a Sentry durante el build y NO
  se sirven públicamente** (`sourcemap: 'hidden'`).
- **Package manager**: SIEMPRE `pnpm`, NUNCA `npm`.
- **StrictMode + Sentry en dev**: puede generar dobles eventos en hot reload —
  no afecta producción porque Sentry está disabled vía `import.meta.env.PROD`.

---

## Orden de implementación recomendado

1. **PARTE 0** (limpieza previa) — CSP + remover gtag.js + types/global.d.ts
2. **Smoke test post-CSP**: cargar la app, verificar que las fuentes Google
   funcionen y GTM siga cargando. **Sin esto, todo lo demás queda bloqueado.**
3. **PARTE 1** (GTM dataLayer + hook)
4. **PARTE 2** (GA4 config en GTM consola + Enhanced Measurement)
5. **PARTE 3.1–3.3** (Sentry frontend) — instalar, init, source maps
6. **PARTE 3.4** (Sentry backend) — agregar a requirements.txt, init en main.py
7. **PARTE 3.5** (distributed tracing + Cloudflare check)
8. **PARTE 4** (checklist completo)
9. **PARTE 5** (nota de privacidad pública)
