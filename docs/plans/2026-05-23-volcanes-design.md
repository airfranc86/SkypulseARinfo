# Diseño — Sección "Volcanes" · SkyPulse AR

**Fecha:** 2026-05-23  
**Estado:** Aprobado  
**Cache:** 2 horas (backend TTL + frontend staleTime + refetchInterval)

---

## Contexto

SEGEMAR OAVV monitorea 10 volcanes activos en Argentina. Su sitio no expone una API JSON — el nivel de alerta se publica únicamente como imagen PNG dinámica (`show_alerta.php?id=X`). El sistema usa 4 niveles: **verde → amarillo → naranja → rojo**.

---

## Arquitectura de datos

```
SEGEMAR PNG (show_alerta.php?id=X)
        ↓  httpx fetch × 10 volcanes (paralelo)
  Pillow → sampleo píxeles centrales → alert_level string
        ↓
  TTLCache 2h (backend in-memory)
        ↓
  GET /api/volcanes  →  JSON estructurado
        ↓
  useVolcanes() — React Query staleTime + refetchInterval 2h
       ↙                         ↘
Volcanes page                Nav item badge
(banner si ≥ naranja)        (dot top-right si has_active_alert)
```

---

## Catálogo de volcanes

| id SEGEMAR | Nombre              | Provincia          | Ranking riesgo |
|-----------|---------------------|--------------------|----------------|
| 1         | Lanín               | Argentina-Chile     | —              |
| 2         | Copahue             | Neuquén            | 1              |
| 3         | Planchón-Peteroa    | Argentina-Chile     | —              |
| 4         | Laguna del Maule    | Argentina-Chile     | —              |
| 5         | San José            | Argentina-Chile     | —              |
| 6         | Tupungatito         | Argentina-Chile     | —              |
| 7         | Maipo               | Argentina-Chile     | —              |
| 8         | Tromen              | Neuquén            | —              |
| 15        | Isla Decepción      | Antártida Argentina | —              |
| 16        | Domuyo              | Neuquén            | —              |

---

## Schema backend (Python/Pydantic)

```python
AlertLevel = Literal["verde", "amarillo", "naranja", "rojo"]

ALERT_HEX: dict[str, str] = {
    "verde":    "#3ecf7a",
    "amarillo": "#f0a030",
    "naranja":  "#e05545",
    "rojo":     "#ff3333",
}

class Volcan(BaseModel):
    id: int
    name: str
    province: str
    alert_level: AlertLevel
    alert_color_hex: str       # derivado de ALERT_HEX
    lat: float
    lon: float
    segemar_url: str           # /monitoreo-volcanico/{slug}/
    ranking: int | None        # ranking riesgo OAVV; None si no aplica

class VolcanesResponse(BaseModel):
    total: int
    has_active_alert: bool     # True si cualquier volcán ≥ naranja
    volcanes: list[Volcan]
```

---

## Detección de color — Pillow

```python
from statistics import mean
from PIL import Image
import io

def detect_alert_level(image_bytes: bytes) -> AlertLevel:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    w, h = img.size
    # Sampleo franja central horizontal (evita bordes y logos Photoshop)
    samples = [img.getpixel((x, h // 2)) for x in range(w // 4, 3 * w // 4, 10)]
    r = mean(s[0] for s in samples)
    g = mean(s[1] for s in samples)
    b = mean(s[2] for s in samples)
    # Umbrales empíricos — paleta SEGEMAR (imagen 1050×133px)
    if r > 180 and g < 80:               return "rojo"
    if r > 180 and g < 140 and b < 80:  return "naranja"
    if r > 160 and g > 140 and b < 80:  return "amarillo"
    return "verde"
```

Punto de ajuste único si SEGEMAR rediseña las imágenes.

---

## Backend — nuevos archivos

```
apps/backend/app/
  schemas/volcanes.py      # Volcan, VolcanesResponse, AlertLevel, ALERT_HEX
  services/oavv.py         # fetch PNG × 10, detect_alert_level, TTLCache 2h
  routers/volcanes.py      # GET /api/volcanes
```

Cambios en archivos existentes:
- `app/main.py` → incluir router volcanes
- `app/core/config.py` → `cache_ttl_volcanes_seconds: int = 7200`
- `pyproject.toml` / `requirements.txt` → agregar `Pillow`

---

## Frontend — nuevos archivos

```
apps/frontend/src/
  pages/Volcanes.tsx        # página completa
  hooks/useWeather.ts       # agregar useVolcanes() (STALE_VOLCANES = 2h)
  lib/api.ts                # agregar api.volcanes()
```

Cambios en archivos existentes:
- `App.tsx` → ruta `/volcanes`, nav item en NAV_TOOLS, badge logic en RootLayout

---

## UI de la página

### Banner de alerta (solo si `has_active_alert`)
```tsx
// Fondo tintado + borde completo — SIN side-stripe border
<div style={{
  background: 'rgba(224,85,69,.06)',
  border: '1px solid rgba(224,85,69,.35)',
  borderRadius: '12px',
  padding: '16px 20px',
}}>
  <p>🌋 Alerta volcánica activa: [nombres de volcanes en naranja/rojo]</p>
  <p>Seguí el monitoreo oficial en oavv.segemar.gob.ar</p>
</div>
```

### Grid de cards
- **Copahue** (ranking 1): `col-span-2` en el grid — destaque por datos, no por decoración
- **Resto**: `grid auto-fit minmax(240px, 1fr)`
- Chip de alert level usa tokens del design system: `--color-safe/watch/warn/crit`

### Badge nav (top-right, no inline)
```tsx
<span style={{ position: 'relative' }}>
  🌋 Volcanes
  {hasAlert && (
    <span style={{
      position: 'absolute', top: '-4px', right: '-6px',
      width: '7px', height: '7px', borderRadius: '50%',
      background: '#e05545', animation: 'pulse 1.5s infinite',
    }} />
  )}
</span>
```

### Footer de sección
```
OAVV · SEGEMAR · Fuente oficial · Caché 2h
```

---

## Reglas impeccable aplicadas

- ✅ Sin `border-left` > 1px como accent stripe — usar `border` completo + fondo tintado
- ✅ Sin grilla idéntica — Copahue destacado por ranking, no por decoración
- ✅ Badge nav top-right, no inline, no rompe legibilidad del label
- ✅ Tokens semánticos existentes: `--color-safe/watch/warn/crit`
- ✅ Loading skeleton: mismo patrón `animate-pulse` + `--color-muted` que Terremotos.tsx
- ✅ Freshness indicator: una línea, no timestamp completo

---

## Cache

| Capa | TTL | Razón |
|------|-----|-------|
| Backend TTLCache | 2h | Boletines OAVV son diarios; 2h captura cambios sin saturar |
| React Query staleTime | 2h | No refetchea innecesariamente en navegación |
| React Query refetchInterval | 2h | Auto-refresh en background mientras la page está abierta |
