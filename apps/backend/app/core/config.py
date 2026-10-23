from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings

# El dominio público del sitio: el único lugar del backend donde está escrito. `PUBLIC_SITE_URL` lo reemplaza.
_SITIO_POR_DEFECTO = "https://skypulse-ar.vercel.app"
_HOSTS_DE_DESARROLLO = frozenset({"localhost", "127.0.0.1"})
_DEFAULT_CORS = f"http://localhost:5173,{_SITIO_POR_DEFECTO}"


# Cuánto tiene que sobrarle al lock de la evaluación de alertas sobre el plazo de la corrida (ver `Settings`).
MARGEN_DEL_LOCK_SEGUNDOS = 120


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
    # Origen público del sitio (`https://dominio`, sin ruta): el link de las notificaciones push y el User-Agent hacia
    # AWC y el SMN. Un valor que no es un origen https (salvo localhost, para desarrollo) frena el arranque.
    public_site_url: str = _SITIO_POR_DEFECTO

    @field_validator("public_site_url")
    @classmethod
    def _origen_del_sitio(cls, v: str) -> str:
        valor = v.strip().rstrip("/")
        partes = urlsplit(valor)
        es_origen = bool(partes.hostname) and not (partes.path or partes.query or partes.fragment)
        es_seguro = partes.scheme == "https" or (partes.scheme == "http" and partes.hostname in _HOSTS_DE_DESARROLLO)
        if not (es_origen and es_seguro):
            raise ValueError("PUBLIC_SITE_URL debe ser un origen https, por ejemplo https://skypulse-ar.vercel.app")
        return valor

    def site_url(self, ruta: str = "") -> str:
        """Una dirección del mismo origen que el sitio: `site_url("/prevision")`."""
        return f"{self.public_site_url}{ruta}"

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

    # Budget of NEW requests to the Aviation Weather Center (METAR and TAF share it), same mechanism as the
    # Open-Meteo one above: token buckets refilled continuously, only requests that carry a client key are
    # capped, and a refused request behaves like an unavailable one (the caches serve their last good copy;
    # `/api/taf` answers 429 `taf_busy` only when it has nothing cached). `/api/taf?icao=` accepts any 4-character
    # code, so without a budget a sweep of made-up codes spends AWC's limit and AWC then answers 429 to Niebla and
    # the dashboard as well. A user normally costs 1 METAR + 1 TAF request per NEW station (about 20 stations
    # exist and the caches absorb the rest: 5 min for the METAR, 60 min for the TAF), so 6 allows three new
    # stations a minute per client.
    awc_calls_per_client_per_minute: int = Field(default=6, ge=1)
    # Global ceiling across every client: the whole warm-up of the ~20 stations (40 requests) fits in one minute;
    # the steady state is about 5 requests a minute. AWC's own limit is not verified here (we recall ~100/min).
    awc_calls_per_minute: int = Field(default=40, ge=1)
    # Codes that are NOT in the local airports list (`/api/taf?icao=` accepts any 4 characters) also need a token of
    # this separate global bucket, so a sweep of made-up codes can only ever take this many of the global tokens a
    # minute: known stations keep at least `awc_calls_per_minute - awc_unknown_calls_per_minute` (32 by default).
    # Real stations that are missing from the list are rare and cached after the first answer.
    awc_unknown_calls_per_minute: int = Field(default=8, ge=1)

    # Alertas push (FRA-354). La clave privada VAPID firma cada envío: solo vive en el entorno (Render),
    # nunca en el repo, y `repr=False` evita que salga en un `repr(settings)` o en un log. Acepta el valor
    # crudo de 32 bytes en base64url (el formato corto que se pega en Render) o un PEM; ver
    # `services/alertas/envio.py::cargar_vapid`. Vacía = el aviso de prueba responde 503.
    vapid_private_key: str = Field(default="", repr=False)
    # Contacto que declara el VAPID ante los servicios push: `https://...` o `mailto:...`.
    vapid_subject: str = _SITIO_POR_DEFECTO

    # Envío automático de alertas push (FRA-355). QStash llama a `POST /api/alertas/evaluar` y firma cada
    # llamada con un JWT HS256 en la cabecera `Upstash-Signature`; ver `services/alertas/firma_qstash.py`.
    # Las dos claves de firma (actual y siguiente, para rotarlas sin cortar el servicio) solo viven en el
    # entorno (Render): `repr=False` evita que salgan en un `repr(settings)` o en un log. Vacías = el
    # endpoint rechaza todo (falla cerrado).
    qstash_current_signing_key: str = Field(default="", repr=False)
    qstash_next_signing_key: str = Field(default="", repr=False)
    # URL pública exacta a la que QStash llama (https://.../api/alertas/evaluar): el claim `sub` de la
    # firma debe ser igual. Vacía = el endpoint rechaza todo.
    alertas_evaluar_url: str = ""
    # Interruptor de apagado nº 1: el envío automático nace APAGADO. El nº 2 es la clave `alertas:apagado`
    # en Upstash (si existe, apaga; se maneja desde su consola sin redeploy). Apaga cualquiera de los dos.
    # Es el ÚNICO que hace que `/evaluar` mande notificaciones (PR5c), vía `services/alertas/interruptor.py`.
    alertas_envio_activo: bool = False
    # Línea S (FRA-368 / SIGMETs). Apagada por defecto: con SIGMET_ENABLED=False la ruta /api/sigmet
    # responde 404; activa solo tras T7b (FRA-357) confirmado por el dueño.
    sigmet_enabled: bool = False
    # Evaluación en seco (FRA-355, PR5b): con `true` el endpoint evalúa las zonas y CUENTA, pero no manda nada
    # (mandar lo decide solo `alertas_envio_activo`). Apagada por defecto. La clave `alertas:apagado` también la detiene.
    alertas_evaluar_en_seco: bool = False
    # Envio del aviso de LLUVIA persistente (opt-in, lluvia PR 3a): nace APAGADO. Solo cuenta en una corrida que ya manda
    # (`alertas_envio_activo` y la clave `alertas:apagado` siguen mandando) y solo a quien pidio la lluvia. Apagado, la
    # lluvia sigue solo contandose en el log (modo sombra) y el camino de la corrida es identico al de antes.
    alertas_lluvia_activa: bool = False
    # Tope de zonas que consulta cada corrida (una consulta a Open-Meteo por zona); las que sobran quedan
    # `diferidas` (primero van las zonas con más suscriptores). El valor por defecto es el catálogo entero (50
    # ciudades) y no puede pasarlo. El presupuesto de Open-Meteo del trabajo (`job:alertas`) nunca es menor que
    # este tope (ver `services/openmeteo_budget.py`); el tope GLOBAL sigue valiendo para todos.
    alertas_max_zonas_por_corrida: int = Field(default=50, ge=1, le=50)
    # Vida del lock de la corrida (`alertas:lock:evaluar`), en segundos: no se libera, se deja vencer. Tiene que
    # durar más que la firma de QStash (~5 min = 300 s), así que el mismo mensaje no evalúa dos veces: de ahí el
    # mínimo de 330 s.
    alertas_lock_ttl_segundos: int = Field(default=600, ge=330, le=3600)
    # Plazo de la corrida, en segundos: pasado ese tiempo se deja de evaluar zonas y las que faltaron quedan
    # `diferidas` (estado `evaluada_incompleta`). Tiene que ser MENOR que la vida del lock por al menos
    # `MARGEN_DEL_LOCK_SEGUNDOS`: el plazo es cooperativo (un envío en vuelo no se cancela: puede pasarse unos segundos
    # y un reintento sumar otros) y el lock no debe vencer con la corrida todavía andando.
    alertas_plazo_corrida_segundos: int = Field(default=480, ge=60)

    @model_validator(mode="after")
    def _plazo_menor_que_el_lock(self) -> "Settings":
        if self.alertas_plazo_corrida_segundos + MARGEN_DEL_LOCK_SEGUNDOS > self.alertas_lock_ttl_segundos:
            raise ValueError(
                "alertas_plazo_corrida_segundos (el plazo de la corrida) tiene que ser al menos "
                f"{MARGEN_DEL_LOCK_SEGUNDOS} segundos menor que alertas_lock_ttl_segundos"
            )
        return self

    # Asistente de Mora (PR 2b). `asistente_enabled` nace APAGADO: con `false` la ruta `/api/asistente` responde 404
    # (como si no existiera). La clave `skypulse:asistente:apagado` en Upstash es el segundo interruptor (apaga sin
    # redeploy). Los cupos son por día de Argentina: por cliente (se guarda un hash de la clave, nunca la IP) y global.
    asistente_enabled: bool = False
    # Salen de los límites del plan gratuito de Groq (200K tokens por día; una pregunta gasta unos 1.400 a 1.900): unas 100
    # preguntas al día entre todos y 10 por persona. Al 80, 95 y 100 % del global se avisa a Sentry (avisos_de_cupo.py).
    asistente_cupo_cliente_dia: int = Field(default=10, ge=1)
    asistente_cupo_global_dia: int = Field(default=100, ge=1)
    # Largo máximo de la pregunta, en caracteres (se cuenta después de recortar los espacios).
    asistente_pregunta_max: int = Field(default=300, ge=20, le=1000)
    # Plazo para que el modelo conteste; pasado ese tiempo la respuesta es 503 `asistente_no_disponible`.
    asistente_timeout_segundos: float = Field(default=12.0, ge=1.0, le=60.0)
    # Cuánto se recuerda en memoria lo que dijo la clave de apagado (0 = leerla en cada pedido).
    asistente_interruptor_cache_segundos: int = Field(default=60, ge=0, le=600)
    # Secreto (16 caracteres o más, al azar) con el que se firma el campo de cada cliente en los cupos y la etiqueta del
    # log: sin él, un hash de la IP se podría revertir probando las 2^32 direcciones. Solo en Render y en el `.env` local;
    # vacío = el endpoint responde 503 y no cuenta nada (falla cerrado).
    asistente_cupo_secreto: str = Field(default="", repr=False)

    # Modelo de lenguaje del asistente (Fase 3): Groq. Sin `GROQ_API_KEY` el asistente sigue con `ModeloFalso`. La clave va
    # solo en Render y en el `.env` local, nunca en Vercel ni con prefijo `VITE_`. El ID del modelo es configurable por si Groq
    # da de baja el actual. `ASISTENTE_RAZONAMIENTO` (low, medium o high) se manda solo con los `openai/gpt-oss-*` (con otro modelo se ignora,
    # porque Groq rechazaría el parámetro con un 400). `ASISTENTE_MAX_TOKENS` incluye el razonamiento, si el modelo lo cuenta.
    groq_api_key: str = Field(default="", repr=False)
    asistente_modelo: str = Field(default="openai/gpt-oss-20b", min_length=1)
    asistente_max_tokens: int = Field(default=400, ge=100, le=2000)
    asistente_razonamiento: Literal["", "low", "medium", "high"] = "low"

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
