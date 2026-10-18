"""El modelo de Groq (API compatible con OpenAI), por el cliente httpx compartido y sin SDK.

Una llamada por pregunta, con las instrucciones y la hoja de `prompt.py`. Cualquier falla sube como `ModeloNoDisponible` con una
etiqueta corta (`motivo`) y, si se sabe, cuántos segundos esperar: nunca el cuerpo de la respuesta de Groq, la pregunta, la
hoja ni la clave. Ante un 429 se abre una pausa (`groq_pause`, como las de Open-Meteo y AWC): mientras dure no sale ningún
pedido, y pasada la pausa pasa UN pedido de prueba. El router convierte todo esto en 503 `asistente_no_disponible` y el navegador
cae al modo degradado.

Detalles de la API (verificados en la documentación de Groq): el tope de salida es `max_completion_tokens` (`max_tokens` está
en desuso) y `reasoning_effort` solo acepta `low`, `medium` o `high` en los modelos `openai/gpt-oss-*`; con otro modelo el
parámetro da un 400, por eso solo se manda con esos modelos (y `ASISTENTE_RAZONAMIENTO` vacío tampoco lo manda). Una respuesta vacía o cortada por el tope (el
razonamiento puede gastar los tokens de salida) no se usa: se descarta como falla en vez de mostrar una oración a medias.
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from typing import Any

import httpx

from app.core import usage_counter
from app.core.config import settings
from app.core.http_client import get_client
from app.core.rate_limit_pause import PROBE_WINDOW_SECONDS, groq_pause
from app.services.asistente.hoja_datos import Hoja
from app.services.asistente.modelo import ModeloNoDisponible
from app.services.asistente.prompt import construir_mensajes

logger = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
USAGE_PROVIDER = "llm_groq"
_TEMPERATURA = 0.2  # una respuesta factual: poca variación
_MODELOS_CON_RAZONAMIENTO = "openai/gpt-oss-"  # los únicos que aceptan `reasoning_effort` low, medium o high


def _reintentar_en(response: httpx.Response) -> float | None:
    """`Retry-After` en segundos, o `None` si falta o no es un número usable (la forma de fecha HTTP no se usa)."""
    crudo = response.headers.get("Retry-After")
    if crudo is None:
        return None
    try:
        segundos = float(crudo)
    except ValueError:
        return None
    return segundos if math.isfinite(segundos) and segundos >= 0.0 else None


def _cuerpo(pregunta: str, hoja: Hoja) -> dict[str, Any]:
    cuerpo: dict[str, Any] = {
        "model": settings.asistente_modelo,
        "messages": construir_mensajes(pregunta, hoja),
        "max_completion_tokens": settings.asistente_max_tokens,
        "temperature": _TEMPERATURA,
        "stream": False,
    }
    if settings.asistente_razonamiento and settings.asistente_modelo.startswith(_MODELOS_CON_RAZONAMIENTO):
        cuerpo["reasoning_effort"] = settings.asistente_razonamiento
        cuerpo["include_reasoning"] = False  # el razonamiento no se usa: no hace falta recibirlo
    return cuerpo


def _texto_de(response: httpx.Response) -> str:
    """El texto de la respuesta; `ModeloNoDisponible` si no se puede leer, está vacío o lo cortó el tope de tokens."""
    try:
        eleccion = response.json()["choices"][0]
        contenido = eleccion["message"]["content"]
        corte = eleccion.get("finish_reason")
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        raise ModeloNoDisponible("respuesta_ilegible") from None
    if corte == "length":  # primero: si el razonamiento gastó el tope, el contenido llega vacío y el motivo es este
        raise ModeloNoDisponible("respuesta_cortada")
    if not isinstance(contenido, str) or not contenido.strip():
        raise ModeloNoDisponible("respuesta_vacia")
    return contenido.strip()


def _segundos(valor: float) -> int:
    return max(1, math.ceil(valor))


class ModeloGroq:
    """Cumple el protocolo `Modelo`. La clave se lee de la configuración en cada llamada y no se guarda en el objeto."""

    async def generar(self, pregunta: str, hoja: Hoja) -> str:
        clave = settings.groq_api_key.strip()
        if not clave:
            raise ModeloNoDisponible("sin_clave")
        if not groq_pause.allow_request():
            raise ModeloNoDisponible("pausa", _segundos(groq_pause.remaining() or PROBE_WINDOW_SECONDS))  # 0 = hay una prueba en vuelo
        generacion, boleto = groq_pause.generation, groq_pause.probe_ticket()  # justo después de `allow_request`

        inicio = time.monotonic()
        try:
            usage_counter.record(USAGE_PROVIDER)
            response = await get_client().post(
                GROQ_URL,
                json=_cuerpo(pregunta, hoja),
                headers={"Authorization": f"Bearer {clave}"},
                timeout=settings.asistente_timeout_segundos,
            )
        except asyncio.CancelledError:
            groq_pause.release_probe_ticket(boleto)  # una prueba cancelada no puede quedarse con el lugar
            raise
        except httpx.TimeoutException:
            raise ModeloNoDisponible("timeout") from None
        except Exception:  # noqa: BLE001 - red, cliente sin iniciar, etc.: el mensaje podría traer datos del pedido
            raise ModeloNoDisponible("red") from None

        estado = response.status_code
        logger.info("asistente: groq estado=%d ms=%d", estado, (time.monotonic() - inicio) * 1000)
        if estado == 429:
            groq_pause.trip(_reintentar_en(response))
            raise ModeloNoDisponible("limite", _segundos(groq_pause.remaining()))
        if 400 <= estado < 500:
            groq_pause.record_success(generacion)  # Groq contestó (rechazó ESTE pedido): está vivo
            if estado in (401, 403):
                logger.error("asistente: Groq rechazó las credenciales (estado %d): revisar GROQ_API_KEY", estado)
                raise ModeloNoDisponible("credenciales")
            if estado in (400, 404, 422):  # modelo dado de baja o parámetro mal puesto: falla todas las preguntas, hay que enterarse
                logger.error(
                    "asistente: Groq rechazó el pedido (estado %d): revisar ASISTENTE_MODELO y ASISTENTE_RAZONAMIENTO", estado,
                )
            raise ModeloNoDisponible(f"http_{estado}")
        if not 200 <= estado < 300:
            raise ModeloNoDisponible(f"http_{estado}")  # una caída de Groq (5xx) o una redirección no cambia la pausa

        groq_pause.record_success(generacion)
        return _texto_de(response)
