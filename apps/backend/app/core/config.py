from pydantic import field_validator
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
    metar_max_distance_km: float = 30.0
    metar_max_age_minutes: int = 90
    checkwx_daily_limit: int = 198     # Free tier: 200/día — 198 deja margen para el aviso Sentry

    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
