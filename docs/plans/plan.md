# Plan — SkyPulse V.5: Herramientas Meteorológicas Prácticas (Argentina)

> **Versión 2 — consolidada tras sesión de discovery.**
> Cambios respecto a v1: catálogo refinado (5 tools, sin lavar-coche, sumamos cota-de-nieve y terremotos), fuentes simplificadas (sin Windy, sin API keys), MeteoAsistente IA fuera de V.1, skills UX/UI definidas.

---

## Contexto

SkyPulse es un portal educativo meteorológico estático (HTML/CSS/Tailwind, Vercel). V.4 (radar.html) ya está completa y desplegada. El METAR live funciona vía proxy Vercel → CheckWX.

Esta iteración agrega una nueva sección de **herramientas prácticas para Argentina** inspiradas en Snowy.es — tender la ropa, sensación térmica, cota de nieve, hacer deporte y monitor de terremotos. Datos 100% de fuentes públicas sin keys (SMN + Open-Meteo + USGS).

Stack nuevo: **FastAPI (Python 3.12) + React 19 + Vite + Tailwind + shadcn/ui**.

---

## Decisiones consolidadas

### Catálogo V.1 (5 tools, solo Argentina, sin IA)

| # | Tool | Endpoint | Datos clave |
|---|------|----------|-------------|
| 1 | tender-la-ropa | `/api/tools/tender-ropa` | humidity, wind, precip, hora del día |
| 2 | sensacion-termica | `/api/tools/sensacion-termica` | Heat Index o Wind Chill según condiciones |
| 3 | cota-de-nieve | `/api/tools/cota-de-nieve` | gradiente térmico, 850 hPa, Andes/Patagonia |
| 4 | hacer-deporte | `/api/tools/hacer-deporte` | temp, humidity, precip, viento, mejor hora |
| 5 | terremotos | `/api/tools/terremotos` | USGS bbox AR, magnitud, distancia al usuario |

> **MeteoAsistente IA**: fuera de V.1. Posible Fase 6 si el portal gana tracción.

### Stack técnico

```
Backend (Render free tier)
├── FastAPI ≥ 0.115
├── Python 3.12
├── httpx async (HTTP client)
├── Pydantic v2 + pydantic-settings (validación + config)
├── cachetools (cache TTL en memoria, sin Redis)
└── pytest + pytest-asyncio + respx (testing)

Frontend (Vercel — herramientas.skypulseinfo.vercel.app)
├── React 19
├── Vite
├── TypeScript
├── Tailwind CSS
├── shadcn/ui
├── TanStack Query (cache cliente)
└── React Router

Tooling
├── ruff (lint Python)
├── black + isort (format)
└── bandit (security scan pre-deploy)
```

### Fuentes de datos (todas públicas, sin API keys)

| Fuente | Endpoint | Auth | Uso |
|--------|----------|------|-----|
| SMN Argentina | `https://ws.smn.gob.ar/map_items/weather` | Ninguna | ~180 estaciones oficiales (observación actual) |
| Open-Meteo | `https://api.open-meteo.com/v1/forecast` | Ninguna | ECMWF + GFS + ICON forecast 10 días, 9km nativo |
| USGS FDSN | `https://earthquake.usgs.gov/fdsnws/event/1/query` | Ninguna | Sismos globales filtrables por bbox |

**Bbox Argentina**: `minlat=-55, maxlat=-21, minlon=-74, maxlon=-53`

> **Por qué Open-Meteo y no Windy**: Windy Point Forecast API **no incluye ECMWF** por licencia. Open-Meteo lo ofrece gratis a resolución nativa 9km bajo CC-BY 4.0 desde octubre 2025.

### Variables de entorno

| Variable | Dónde | Default | Descripción |
|----------|-------|---------|-------------|
| `CACHE_TTL_SECONDS` | Backend | `600` | TTL del cache en memoria (10 min) |
| `CORS_ORIGINS` | Backend | ver config.py | Orígenes permitidos para CORS |
| `LOG_LEVEL` | Backend | `INFO` | Nivel de logs |
| `VITE_API_BASE_URL` | Frontend | — | URL del backend Render en producción |

> **No hay API keys**. Las 3 fuentes son públicas. Cero secret management requerido.

### Deploy

- **Backend**: Render free tier, root `apps/backend/`, runtime Python 3.12
- **Frontend**: Nuevo proyecto Vercel apuntando a `apps/frontend/` → `herramientas.skypulseinfo.vercel.app`
- **Link integración**: agregar "🛠 Herramientas" en nav del sitio estático existente

---

## Skills a aplicar durante construcción

### Backend
- `/fastapi-templates` — scaffold consistente
- `/python-patterns` — idioms Python (@dataclass frozen, Protocol, context managers)
- `/api-design` — naming + contratos REST
- `/python-testing` — fixtures pytest, async testing con respx
- `/security-review` — pre-deploy gate

### Frontend
- `/impeccable` + `/ui-ux-pro-max` — diseño distinctive (no genérico)
- `/frontend-design` — componentes (IndexGauge, HourlyTimeline, LocationPicker)
- `/adapt` + `/mobile-design` — responsive (la mayoría usa mobile)
- `/animate` — micro-interacciones en transiciones
- `/audit` — accesibilidad + performance pre-deploy
- `/critique` — UX review antes de mergear cada página

### Cross-cutting
- `/predeploy` — checklist 7-puntos antes de cada push a producción

---

## Estructura de archivos

```
SkypulseARinfo/
├── src/                        # Sitio estático existente (sin cambios)
├── api/                        # Proxy CheckWX existente (sin cambios)
├── apps/
│   ├── backend/                # FastAPI
│   │   ├── app/
│   │   │   ├── main.py         # CORS + lifespan + routers
│   │   │   ├── routers/
│   │   │   │   ├── weather.py     # GET /api/weather/current, /forecast
│   │   │   │   ├── tools.py       # GET /api/tools/{tool}?lat&lon
│   │   │   │   └── earthquakes.py # GET /api/earthquakes/recent?lat&lon
│   │   │   ├── services/
│   │   │   │   ├── smn.py         # Fetch SMN + cache + haversine
│   │   │   │   ├── openmeteo.py   # Forecast multi-modelo (ECMWF/GFS/ICON)
│   │   │   │   ├── usgs.py        # Sismos USGS con bbox AR
│   │   │   │   └── calculators.py # Índices: secado, sensación, cota nieve, deporte
│   │   │   ├── schemas/
│   │   │   │   ├── weather.py
│   │   │   │   ├── tools.py
│   │   │   │   └── earthquakes.py
│   │   │   └── core/
│   │   │       ├── config.py      # Settings (env vars)
│   │   │       └── http_client.py # httpx.AsyncClient compartido
│   │   ├── tests/
│   │   │   ├── conftest.py
│   │   │   ├── test_smn.py
│   │   │   ├── test_openmeteo.py
│   │   │   ├── test_weather_router.py
│   │   │   └── test_calculators.py
│   │   ├── requirements.txt
│   │   ├── pyproject.toml      # ruff + black + pytest config
│   │   └── render.yaml
│   │
│   └── frontend/               # React + Vite
│       ├── src/
│       │   ├── App.tsx
│       │   ├── pages/
│       │   │   ├── TenderRopa.tsx
│       │   │   ├── SensacionTermica.tsx
│       │   │   ├── CotaDeNieve.tsx
│       │   │   ├── HacerDeporte.tsx
│       │   │   └── Terremotos.tsx
│       │   ├── components/
│       │   │   ├── LocationPicker.tsx  # City search + geolocalización
│       │   │   ├── IndexGauge.tsx      # Gauge circular 0-100
│       │   │   ├── HourlyTimeline.tsx  # Strip de 24h
│       │   │   ├── WeatherSummary.tsx  # Condiciones actuales
│       │   │   └── EarthquakeMap.tsx   # Mapa Leaflet AR
│       │   ├── hooks/
│       │   │   ├── useWeather.ts       # TanStack Query
│       │   │   └── useLocation.ts      # Geolocation API
│       │   └── lib/
│       │       ├── api.ts              # Fetch wrapper → backend
│       │       └── cities-ar.ts        # ~50 ciudades AR + lat/lon
│       ├── package.json
│       ├── vite.config.ts
│       └── tailwind.config.ts
└── vercel.json                 # Sin cambios
```

---

## Backend — Contratos de endpoints

### `GET /api/weather/current?lat={lat}&lon={lon}`

Agrega condiciones actuales:
1. Valida `lat ∈ [-55, -21]`, `lon ∈ [-74, -53]` (territorio AR + límite Chile)
2. Busca estación SMN más cercana por haversine
3. Complementa con Open-Meteo (current weather) si SMN está caído
4. Devuelve `CurrentWeather` schema

### `GET /api/weather/forecast?lat={lat}&lon={lon}&model=ecmwf`

Proxy hacia Open-Meteo:
- Variables: `temperature_2m, relative_humidity_2m, wind_speed_10m, wind_direction_10m, precipitation, cloud_cover`
- Modelos: `ecmwf_ifs04` (default) | `gfs_seamless` | `icon_seamless`
- Timezone: `America/Argentina/Buenos_Aires`
- Devuelve array de 48 timestamps

### `GET /api/tools/tender-ropa?lat={lat}&lon={lon}`

```
score = 0
+ 40 si humidity < 60%   (variable más importante)
+ 25 si wind_speed 10–20 km/h
+ 20 si temp > 18°C
+ 15 si precip_next_6h == 0
→ best_window: franja horaria donde score > 70 en próximas 24h
```

### `GET /api/tools/sensacion-termica?lat={lat}&lon={lon}`

```
if temp > 26 AND humidity > 40:
    Heat Index (Rothfusz)
elif temp < 10 AND wind_speed > 5 km/h:
    Wind Chill (Canadian formula)
else:
    feels_like = temp
```

### `GET /api/tools/cota-de-nieve?lat={lat}&lon={lon}`

```
Tres métodos (devolver los 3 + promedio):
1. Alcaide: cota = 150 * (T - 0.5) + altitud_estacion
2. Gradiente térmico: cota = altitud_0°C usando lapso ambiental 6.5°C/km
3. 850 hPa: usar Open-Meteo pressure_level_850 si T_850 < 0°C
Aplicable principalmente: Andes (Mendoza, Neuquén, Río Negro, Chubut, Santa Cruz)
```

### `GET /api/tools/hacer-deporte?lat={lat}&lon={lon}`

```
score = 0
+ 30 si temp 10–25°C
+ 25 si humidity < 70%
+ 25 si precip == 0
+ 20 si wind_speed < 20 km/h
→ best_hour: hora con mayor score en próximas 12h
```

### `GET /api/tools/terremotos?lat={lat}&lon={lon}&radius_km=500`

```
USGS bbox AR + filtro por radio del usuario
Variables: magnitude ≥ 2.5, depth, time, place
Respuesta: lista ordenada por proximidad + magnitud
```

---

## Frontend — UI/UX (shadcn/ui + Tailwind + React Bits)

**Layout global**: sidebar nav izquierda con las 5 herramientas + header con buscador de ciudad.

### Componentes base requeridos (V.1)

| Componente | Tipo | Uso |
|------------|------|-----|
| `LocationPicker` | Input + autocomplete + geolocation | Header global, todas las páginas |
| `IndexGauge` | SVG gauge semicircular 0–100 | Score por tool (rojo<30, amarillo 30–60, verde>60) |
| `HourlyTimeline` | Strip horizontal scrollable 24h | Mostrar evolución del score por hora |
| `WeatherSummary` | Tarjeta con métricas actuales | Temp, humedad, viento, presión |
| `EarthquakeMap` | Mapa Leaflet | Página terremotos |
| **`StatCard`** | **Tarjeta KPI** (shadcn Card + ReactBits ElectricBorder) | Métricas individuales destacadas |
| **`DataTable`** | **Tabla** (shadcn DataTable + Tanstack Table) | Listado últimos sismos, comparativa de modelos |
| **`TrendChart`** | **Gráfico** (Recharts o visx) | Series temporales temp/humedad 24–48h |

### React Bits — librería de animaciones

[reactbits.dev](https://reactbits.dev) — componentes copy-paste estilo shadcn, sin dependencia npm.

| Componente RB | Dónde se aplica | Uso |
|---------------|-----------------|-----|
| `ElectricBorder` | Wrapper de `StatCard` y `IndexGauge` | Bordes animados eléctricos en cards principales |
| `SplashCursor` | Layout root | Cursor con animación de líquido global |
| `Dither` (background) | Hero / landing de `/herramientas` | Fondo dither tipo retro (color púrpura por default) |
| `FadeContent` | Secciones que aparecen al scroll | Fade-in progresivo en cada sección de la página |

**Convención de instalación**: copiar el componente de reactbits.dev a `apps/frontend/src/components/animated/` y modificarlo según el tema (púrpura para Dither, accent del proyecto para ElectricBorder).

### Páginas

- Cada página de tool = `LocationPicker` + `WeatherSummary` + `IndexGauge` + `HourlyTimeline` + sección "Por qué este score" envuelta en `FadeContent`
- Página terremotos: `EarthquakeMap` + `DataTable` con últimos 30 sismos
- Landing `/herramientas`: fondo `Dither` púrpura + grilla de 5 `StatCard` con `ElectricBorder`

**Estado de datos**: TanStack Query con `staleTime: 10min` + shadcn Skeleton loading
**Cursor global**: `SplashCursor` en el `<RootLayout>`

---

## Protocolo de cierre de fase (MANDATORY)

Al completar cualquier fase (1, 1b, 2, 3, 4, 5, 6, …) ejecutar SIEMPRE en este orden:

1. **`/progress-save`** — agregar entrada a `PROGRESS.md` con done / files / tests / next.
2. **`/compact`** — comprimir el contexto antes de arrancar la siguiente fase para no entrar en límites de ventana a mitad de trabajo.

Esta regla es no negociable y se aplica al final de CADA fase, no solo al cierre de sesión. Evita interrupciones por límites de contexto y mantiene historial limpio.

---

## Fases de implementación

### Fase 1 — Backend scaffold + weather endpoint (ESTA SESIÓN)
1. Actualizar `docs/plans/plan.md` ✅
2. Diseñar contrato `/api/weather/current` con architect
3. Scaffold `app/main.py` + CORS + montaje routers
4. `services/smn.py` + cache + haversine
5. `services/openmeteo.py` multi-modelo
6. `routers/weather.py` con endpoint `/api/weather/current`
7. Tests pytest (target 80%+ cobertura)
8. Verificación local con uvicorn
9. Code review paralelo (python-reviewer + security-reviewer + api-qa)

### Fase 2 — Calculadores + 4 endpoints de tools
10. `calculators.py` (tender, sensación, cota, deporte)
11. `routers/tools.py` con 4 endpoints
12. Tests unitarios borde (verano/invierno AR)

### Fase 3 — USGS + endpoint terremotos
13. `services/usgs.py` con bbox AR + filtro por radio
14. `routers/earthquakes.py`
15. Tests con datos USGS reales

### Fase 4 — Frontend scaffold
16. Vite + React + Tailwind + shadcn/ui en `apps/frontend/`
17. React Router con las 5 rutas
18. TanStack Query
19. `LocationPicker` con lista AR

### Fase 5 — Herramientas UI
20. `IndexGauge` (SVG semicircular) — usar `/impeccable` + `/ui-ux-pro-max`
21. `HourlyTimeline`
22. `StatCard` + `DataTable` + `TrendChart` (base shadcn/ui)
23. Integración React Bits: `ElectricBorder` (cards), `SplashCursor` (layout root), `Dither` background púrpura (landing), `FadeContent` (transiciones scroll)
24. 5 páginas con datos reales
25. `/audit` accesibilidad + perf antes de deploy

### Fase 6 — Deploy
26. Deploy backend en Render
27. Crear Vercel project apuntando a `apps/frontend/`
28. Configurar `VITE_API_BASE_URL` en Vercel
29. Agregar link "🛠 Herramientas" en nav del sitio estático
30. `/predeploy` checklist completo

---

## Verificación de aceptación

1. `GET /api/weather/current?lat=-31.4&lon=-64.2` → responde con datos de Córdoba (SMN + Open-Meteo)
2. `GET /api/tools/tender-ropa?lat=-34.6&lon=-58.4` → score 0–100 + best_window
3. `GET /api/tools/cota-de-nieve?lat=-32.9&lon=-68.8` → cota en metros (Mendoza)
4. `GET /api/tools/terremotos?lat=-34.6&lon=-58.4&radius_km=500` → lista últimos sismos en radio
5. Abrir `http://localhost:5173/herramientas/tender-la-ropa` → gauge se renderiza, datos cargan
6. Cambiar ciudad a Mendoza → datos se actualizan (TanStack Query refetch)
7. En producción: `https://herramientas.skypulseinfo.vercel.app` resuelve correctamente
8. CORS: request desde el dominio Vercel al backend Render no es bloqueado
9. Mobile: layouts responsive en iPhone SE (375px) y Pixel (412px)
10. Lighthouse: a11y > 95, performance > 85

---

## Referencias técnicas (NotebookLM)

- **Notebook 1** — `Meteorologia - SkyPulse` (8 fuentes): contexto educativo, catálogo del cielo, AEMET estelas, OHMC, IATA aviación sostenible
- **Notebook 2** — `APIs Meteo Oficiales` (28 fuentes): docs oficiales USGS Earthquake Catalog, ECMWF Open Data, GFS NCEI, Windy Plugins (para V.2 si se publica plugin)

Consultar via `mcp__notebooklm-mcp__notebook_query` cuando necesite específicos parámetros de API o fórmulas meteorológicas.

---

## Out of scope V.1

- MeteoAsistente IA (chat) → Fase 6 opcional, requiere OpenRouter
- Datos OHMC Córdoba (requiere gestión email institucional)
- Datos INTA agrometeorológica (revisar para V.2)
- WRF de SMN (no expone API pública)
- Webcams meteorológicas (Windy Webcams API requiere key)
- Plugin Windy.com (mover a roadmap V.2 si hay tracción)
