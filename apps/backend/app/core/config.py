from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    smn_weather_url: str = "https://ws.smn.gob.ar/map_items/weather"
    openmeteo_base_url: str = "https://api.open-meteo.com/v1/forecast"
    usgs_base_url: str = "https://earthquake.usgs.gov/fdsnws/event/1/query"
    smn_max_distance_km: float = 80.0
    smn_max_age_minutes: int = 90
    http_timeout_seconds: float = 5.0
    cache_ttl_seconds: int = 600  # 10 minutos
    log_level: str = "INFO"
    cors_origins: list[str] = [
        "http://localhost:5173",
        "https://skypulse-ar.vercel.app",
        "https://skypulseinfo.vercel.app",
    ]

    windy_api_key: str = ""
    windy_base_url: str = "https://api.windy.com/api/point-forecast/v2"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
