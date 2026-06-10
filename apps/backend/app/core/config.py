from pydantic import field_validator
from pydantic_settings import BaseSettings

_DEFAULT_CORS = "http://localhost:5173,https://skypulse-ar.vercel.app,https://skypulseinfo.vercel.app"


class Settings(BaseSettings):
    smn_weather_url: str = "https://ws.smn.gob.ar/map_items/weather"
    openmeteo_base_url: str = "https://api.open-meteo.com/v1/forecast"
    usgs_base_url: str = "https://earthquake.usgs.gov/fdsnws/event/1/query"
    smn_max_distance_km: float = 80.0
    smn_max_age_minutes: int = 90
    http_timeout_seconds: float = 5.0
    cache_ttl_seconds: int = 600           # 10 minutos — clima SMN
    cache_ttl_earthquakes_seconds: int = 300    # 5 minutos — USGS sismos (era 6h, causaba datos obsoletos)
    cache_ttl_volcanes_seconds: int = 7200      # 2 horas — OAVV volcanes
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

    windy_api_key: str = ""
    windy_base_url: str = "https://api.windy.com/api/point-forecast/v2"
    windy_model: str = "gfs"  # ecmwf requiere plan pago; gfs disponible en plan gratuito
    windy_timeout_seconds: float = 10.0   # POST pesado con niveles + parámetros múltiples
    cache_ttl_fire_seconds: int = 3600  # 1 hora — riesgo de incendio
    fire_timeout_seconds: float = 10.0    # mismo tipo de request que Windy

    checkwx_api_key: str = ""
    checkwx_base_url: str = "https://api.checkwx.com"
    cache_ttl_metar_seconds: int = 1800  # 30 minutos — METAR
    cache_ttl_taf_seconds: int = 3600    # 1 hora — TAF
    metar_timeout_seconds: float = 10.0
    checkwx_daily_limit: int = 198     # Free tier: 200/día — 198 deja margen para el aviso Sentry

    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
