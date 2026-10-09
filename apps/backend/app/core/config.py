from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

_DEFAULT_CORS = "http://localhost:5173,https://skypulse-ar.vercel.app,https://skypulseinfo.vercel.app"


class Settings(BaseSettings):
    smn_weather_url: str = "https://ws.smn.gob.ar/map_items/weather"
    # El feed `map_items/weather` está congelado desde 2022 (sin campo `date`): el "ahora" nunca podía
    # usar el SMN. Apagado por defecto; activar con SMN_ENABLED=true si el feed vuelve a publicar.
    smn_enabled: bool = False
    openmeteo_base_url: str = "https://api.open-meteo.com/v1/forecast"
    usgs_base_url: str = "https://earthquake.usgs.gov/fdsnws/event/1/query"
    smn_max_distance_km: float = 80.0
    smn_max_age_minutes: int = 90
    http_timeout_seconds: float = 5.0
    cache_ttl_seconds: int = 600           # 10 minutos — clima SMN
    cache_ttl_earthquakes_seconds: int = 300    # 5 minutos — USGS sismos (era 6h, causaba datos obsoletos)
    cache_ttl_volcanes_seconds: int = 7200      # 2 horas — OAVV volcanes
    # Avisos oficiales del SMN: feed CAP abierto (RSS + un XML CAP por aviso), licencia CC BY 4.0.
    smn_cap_feed_url: str = "https://ssl.smn.gob.ar/CAP/AR.php"
    cache_ttl_smn_alertas_seconds: int = 1800   # 30 minutos — cada cuánto se relee el RSS del feed CAP
    smn_cap_stale_max_seconds: int = 3600       # 1 hora — hasta cuándo se sirve el último feed leído si el SMN no responde
    smn_cap_document_max_bytes: int = 65536     # 64 KB — tope por XML CAP (los reales pesan 2-5 KB)
    smn_cap_content_failures_before_skip: int = 3  # fallas de contenido seguidas de un XML CAP antes de ponerlo en cuarentena
    log_level: str = "INFO"
    cors_origins: list[str] | str = _DEFAULT_CORS

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        if isinstance(v, list):
            return v
        return []

    checkwx_api_key: str = ""
    checkwx_base_url: str = "https://api.checkwx.com"
    cache_ttl_metar_seconds: int = 1800  # 30 minutos — METAR
    cache_ttl_taf_seconds: int = 3600    # 1 hora — TAF
    metar_timeout_seconds: float = 10.0
    # "Ahora" del dashboard (FRA-320): METAR de AWC como observación si el aeropuerto está cerca y
    # el dato es reciente. Timeout corto: el dashboard no espera más que esto por el METAR.
    metar_observation_timeout_seconds: float = 4.0
    # Un único límite de distancia/antigüedad para el dashboard y para Niebla (inclusivos: 20.0 km y
    # 90 min todavía pasan).
    metar_max_distance_km: float = 20.0
    metar_max_age_minutes: int = 90
    checkwx_daily_limit: int = 198     # Free tier: 200/día — 198 deja margen para el aviso Sentry
    # Global cap of NEW CheckWX calls per minute (token bucket). Cached stations are always served; above the
    # cap new ones get 429 `metar_busy`. Slows a sweep of made-up ICAO codes even if the per-IP limit is dodged.
    checkwx_new_calls_per_minute: int = Field(default=12, ge=1)
    # A failed CheckWX call (5xx, timeout, 401...) is remembered this long: repeating that station neither
    # calls CheckWX nor spends quota. 15 s is the window the frontend retry policy assumes
    # (apps/frontend/src/lib/loadError.ts and retryPolicy.ts).
    checkwx_failure_ttl_seconds: float = Field(default=15.0, ge=1.0)
    # Share of that cap one client (the per-IP rate-limit key) may start per minute, so a single sweeper
    # cannot drain the global bucket for everybody else. A client over its share gets the same `metar_busy`.
    checkwx_new_calls_per_client_per_minute: int = Field(default=3, ge=1)
    # Overall bound of one CheckWX flight (counter reservation + HTTP call + refund): above the HTTP timeout
    # (`metar_timeout_seconds`) and the Upstash timeout, below the point where callers give up.
    checkwx_flight_deadline_seconds: float = Field(default=20.0, ge=1.0)

    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""

    # Último dato bueno de Open-Meteo en Upstash Redis (sin URL/token de Upstash queda apagado). El "ahora" y
    # la niebla duran poco (un "ahora" de muchas horas engaña); el pronóstico, más. La escritura se limita a
    # una por clave cada `write_interval` por proceso para cuidar el presupuesto de comandos del plan gratis.
    # 6 h y no más: el "Actualizado HH:MM" de la web sale de la hora de armado de la respuesta, así que una
    # copia muy vieja pasaría por actual (la edad real del pronóstico llegará en otro cambio).
    openmeteo_last_good_ttl_forecast_seconds: int = 21600    # 6 horas — pronóstico diario y horario
    openmeteo_last_good_ttl_current_seconds: int = 10800     # 3 horas — "ahora" y niebla
    openmeteo_last_good_write_interval_seconds: float = 1800.0  # 30 minutos entre escrituras de una clave
    openmeteo_last_good_timeout_seconds: float = 2.0         # tope de cada lectura/escritura a Redis
    openmeteo_last_good_writes_per_minute: int = 60          # tope global de SET por minuto, además de la ventana por clave

    # Budget of calls that actually go out to Open-Meteo (a cache hit or a shared flight costs nothing). The
    # cache key rounds lat/lon to 2 decimals, so one client can ask for millions of distinct cells at ~5 calls
    # each; this bounds what one client and the whole process may send per minute (token buckets, refilled
    # continuously). Only requests that carry a client key are capped (see `core/client_context.py`): scripts and
    # scheduled jobs are not. A refused call behaves like a failed one: the cache serves the last good copy.
    # A normal visit to one location costs ~6 calls, so 12 leaves room for about two new locations a minute.
    openmeteo_calls_per_client_per_minute: int = Field(default=12, ge=1)
    # Global ceiling across every client. Open-Meteo's free plan also has per-hour and per-day ceilings (we
    # recall 600/min, 5,000/h and 10,000/day: unverified, check their pricing page), so a per-minute cap alone
    # does not protect the daily one; 90 is a margin against bursts, not a daily budget.
    openmeteo_calls_per_minute: int = Field(default=90, ge=1)

    # Alertas push (FRA-354). La clave privada VAPID firma cada envío: solo vive en el entorno (Render),
    # nunca en el repo, y `repr=False` evita que salga en un `repr(settings)` o en un log. Acepta el valor
    # crudo de 32 bytes en base64url (el formato corto que se pega en Render) o un PEM; ver
    # `services/alertas/envio.py::cargar_vapid`. Vacía = el aviso de prueba responde 503.
    vapid_private_key: str = Field(default="", repr=False)
    # Contacto que declara el VAPID ante los servicios push: `https://...` o `mailto:...`.
    vapid_subject: str = "https://skypulse-ar.vercel.app"

    # Clave del límite de pedidos por IP (ver `core/rate_limit.py::client_key`). Render pone Cloudflare delante:
    # Cloudflare escribe `CF-Connecting-IP` con la IP real y agrega al `X-Forwarded-For` (el valor de la
    # izquierda lo manda el cliente). `RATE_LIMIT_TRUST_CF_HEADER=false` ignora `CF-Connecting-IP` (si el
    # servicio llegara a quedar expuesto sin Cloudflare). `RATE_LIMIT_XFF_HOPS` es la posición, contada
    # desde la DERECHA del `X-Forwarded-For`, de la IP del cliente cuando no hay `CF-Connecting-IP`
    # (1 = el último; 3 según una medición de terceros, a confirmar con el registro diagnóstico; máximo 16).
    # Si no coincide con la cadena real y falta `CF-Connecting-IP`, todos comparten una clave ("unverified").
    rate_limit_trust_cf_header: bool = True
    rate_limit_xff_hops: int = Field(default=3, ge=1, le=16)

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
