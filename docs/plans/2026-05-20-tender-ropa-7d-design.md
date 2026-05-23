# Design: Tender Ropa — 7-Day Forecast

**Date:** 2026-05-20  
**Status:** Approved  
**Scope:** New endpoint + redesigned page (does NOT touch existing endpoints)

---

## Problem

The current `/api/tools/tender-ropa` endpoint returns data for today only. Users need to plan laundry days in advance (7-day horizon).

---

## Decision: Data Source Priority

| Priority | Source | Scope |
|----------|--------|-------|
| 1st | Windy Point Forecast API (ECMWF model) | New endpoints |
| 2nd | Open-Meteo | Fallback if Windy fails |
| Note | Full app-wide Windy migration → separate session |

---

## Backend

### New endpoint
`GET /api/tools/tender-ropa/forecast?lat=&lon=`

### Windy API call
```
POST https://api.windy.com/api/point-forecast/v2
{
  "lat": <float>, "lon": <float>,
  "model": "ecmwf",
  "parameters": ["temp", "rh", "wind_u", "wind_v", "past3hprecip"],
  "levels": ["surface"],
  "key": "<WINDY_API_KEY>"
}
```

### Daily aggregation (hourly → daily)
- `temp_max_c` / `temp_min_c` — max/min of day
- `humidity_mean` — daily average
- `wind_speed_kmh` — magnitude of wind vector (u²+v²)^0.5, mean
- `precip_sum_mm` — sum of past3hprecip per day
- `precip_prob` — % of hours with precip > 0.1 mm

### Score reuse
Apply existing `score_tender_ropa(temp, humidity, wind_speed, precip)` per day using daily aggregates.

### Confidence curve (NOAA official — scijinks.gov/forecast-reliability)
```python
CONFIDENCE = [95, 93, 90, 87, 83, 80, 75]  # day 0 → day 6
CONFIDENCE_LABEL = {range(85, 101): "Alta", range(70, 85): "Media", range(0, 70): "Baja"}
```

### New schema
```python
class LaundryDay(BaseModel, frozen=True):
    date: str
    day_label: str
    score: int
    label: Literal["Excelente", "Bueno", "Regular", "No apto"]
    headline: str
    temp_max_c: float
    humidity: float
    wind_speed_kmh: float
    precip_prob: float
    is_best: bool
    confidence_pct: int
    confidence_label: Literal["Alta", "Media", "Baja"]

class LaundryForecastResponse(BaseModel, frozen=True):
    days: list[LaundryDay]
    source: str  # "windy_ecmwf" | "openmeteo_fallback"
```

### Files to create/modify
- `app/core/config.py` — add `windy_api_key`, `windy_base_url`
- `app/services/windy.py` — NEW, Windy client with TTLCache + asyncio.Lock
- `app/schemas/tools.py` — add LaundryDay + LaundryForecastResponse
- `app/routers/tools.py` — add GET /tender-ropa/forecast endpoint

---

## Frontend

### New hook
`useTenderRopaForecast(lat, lon)` in `hooks/useWeather.ts`

### Component: LaundryDayCard
```
┌─────────────────────────────────────────────────────┐
│  [Mini gauge]  Miércoles 21             [95% ALTA]  │
│   score: 87   Buenas condiciones                    │
│               ─────────────────────────────────     │
│               🌡 24°  💧 45%  💨 12 km/h  🌧 5%    │
└─────────────────────────────────────────────────────┘
```

- Left: `IndexGauge` size=80, score number
- Center: day label bold, headline muted, 4 condition chips
- Right: confidence badge (green ≥85%, yellow 70-84%, orange <70%)
- Best day: gold border `#c8a84b` + "✦ Mejor día" chip replaces confidence badge
- Hover: `scale(1.01)` + border opacity increase
- Animation: `FadeContent` stagger, +60ms delay per card

### TenderRopa.tsx rewrite
- Remove: IndexGauge hero, HourlyTimeline, StatCards grid
- Add: 7× `LaundryDayCard` in vertical list
- Header: Shirt icon + "Tender ropa" + city (unchanged)

---

## Planned (separate session)
- Migrate ALL existing endpoints to use Windy as primary + Open-Meteo as fallback
- Update footer: show active model per endpoint
- Add global accuracy indicator

---

## Sources
- NOAA forecast reliability: https://scijinks.gov/forecast-reliability/
- Windy Point Forecast API: https://api.windy.com/point-forecast/docs
