"""Pausa ante el HTTP 429 (corte de circuito) para un proveedor upstream.

Render comparte IP entre muchos servicios, así que Open-Meteo puede responder 429 a todas las llamadas.
Reintentar solo suma al límite y al contador de uso. Con este módulo, el primer 429 abre una pausa:
mientras dure no se sale a la red y el llamador sirve el último dato bueno. Al terminar, pasa UN pedido
de prueba; si vuelve bien se reabre el tráfico y si vuelve con otro 429 la pausa se renueva.

Estado global al proceso (el límite es por IP, no por pedido), con el reloj inyectable para los tests.
No usa ``asyncio``: todo es síncrono y sin awaits, así que es atómico dentro del event loop.
"""
from __future__ import annotations

import math
import time
from typing import Callable

DEFAULT_PAUSE_SECONDS = 120.0
MAX_RETRY_AFTER_SECONDS = 600.0
MIN_RETRY_AFTER_SECONDS = 10.0
PROBE_WINDOW_SECONDS = 15.0


class RateLimitPause:
    """Corte de circuito: ``allow_request`` antes de cada llamada, ``trip``/``record_success`` después."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        default_seconds: float = DEFAULT_PAUSE_SECONDS,
        max_retry_after: float = MAX_RETRY_AFTER_SECONDS,
        min_retry_after: float = MIN_RETRY_AFTER_SECONDS,
        probe_window: float = PROBE_WINDOW_SECONDS,
    ) -> None:
        self._default_clock = clock
        self.clock = clock
        self._default_seconds = default_seconds
        self._max_retry_after = max_retry_after
        self._min_retry_after = min_retry_after
        self._probe_window = probe_window
        self._paused_until = 0.0
        self._probe_until = 0.0
        self._generation = 0
        self._call_took_probe = False

    @property
    def generation(self) -> int:
        """Cuenta los ``trip``. El llamador la lee al empezar un pedido y se la devuelve a ``record_success``."""
        return self._generation

    def allow_request(self) -> bool:
        """True si se puede salir a la red. Tras la pausa concede una sola prueba por ventana.

        Recuerda si ESTA llamada tomó el lugar de la prueba, para que `release_probe` (que va a continuación,
        sin ningún `await` de por medio) lo libere solo en ese caso.
        """
        self._call_took_probe = False
        if self._paused_until == 0.0:
            return True
        now = self.clock()
        if now < self._paused_until:
            return False
        if now < self._probe_until:
            return False  # ya hay una prueba en vuelo: el resto espera su resultado
        self._probe_until = now + self._probe_window
        self._call_took_probe = True
        return True

    def release_probe(self) -> None:
        """Devuelve el lugar de la prueba si la última `allow_request` lo tomó y el pedido no llegó a salir.

        Sin efecto si esa llamada no tomó la prueba (otro pedido sigue con la suya) o si ya se liberó. Hay que
        llamarla justo después de `allow_request`, sin ceder el control entre una y otra.
        """
        if self._call_took_probe:
            self._probe_until = 0.0
            self._call_took_probe = False

    def probe_ticket(self) -> float | None:
        """Identifies the probe window the last `allow_request` took (None if it did not take the probe).

        Read it right after `allow_request`. A pedido que se cancela con la prueba en vuelo se la devuelve a
        `release_probe_ticket`; el boleto evita liberar la prueba de OTRO pedido si ya hubo un `trip`/éxito y
        otro llamador tomó una ventana nueva.
        """
        return self._probe_until if self._call_took_probe else None

    def release_probe_ticket(self, ticket: float | None) -> None:
        """Libera la prueba si todavía es la ventana de `ticket` (la de un pedido que no llegó a resolver)."""
        if ticket is not None and self._probe_until == ticket:
            self._probe_until = 0.0

    def trip(self, retry_after: float | None = None) -> None:
        """Abre (o renueva) la pausa tras un 429. Una pausa en curso nunca se acorta.

        Un ``Retry-After`` utilizable (finito, positivo y hasta el tope) se respeta, con un piso: un
        encabezado de 1 s no puede dar una pausa de 1 s. Si no, rige la pausa por defecto.
        """
        self._generation += 1
        seconds = self._default_seconds
        if (
            retry_after is not None
            and math.isfinite(retry_after)
            and 0.0 < retry_after <= self._max_retry_after
        ):
            seconds = max(retry_after, self._min_retry_after)
        self._paused_until = max(self._paused_until, self.clock() + seconds)
        self._probe_until = 0.0
        self._call_took_probe = False

    def record_success(self, generation: int | None = None) -> None:
        """La llamada salió bien: se cierra la pausa y el tráfico vuelve a fluir.

        ``generation`` es la de ``generation`` al empezar el pedido. Si hubo un ``trip`` desde entonces
        (un 429 llegó mientras el pedido seguía en vuelo), su éxito es anterior a ese 429 y no cierra
        la pausa: solo la prueba o un pedido posterior al último 429 puede hacerlo.
        """
        if generation is not None and generation != self._generation:
            return
        self._paused_until = 0.0
        self._probe_until = 0.0
        self._call_took_probe = False

    def remaining(self) -> float:
        """Segundos que faltan para que termine la pausa (0 si no hay pausa)."""
        if self._paused_until == 0.0:
            return 0.0
        return max(0.0, self._paused_until - self.clock())

    def reset(self) -> None:
        """Vuelve al estado inicial y restaura el reloj del constructor. Lo usan los tests."""
        self._paused_until = 0.0
        self._probe_until = 0.0
        self._call_took_probe = False
        self.clock = self._default_clock


# Instancia única de Open-Meteo: ``services/openmeteo.py`` la consulta antes de cada llamada.
openmeteo_pause = RateLimitPause()

# Instancia única de AWC (aviationweather.gov): ``services/reportes_aeronauticos/awc.py`` la consulta antes de
# cada pedido de METAR o TAF y un 429 la abre para ambos.
awc_pause = RateLimitPause()
