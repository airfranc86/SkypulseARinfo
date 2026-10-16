"""The network layer against a throwaway local HTTP server (no internet needed)."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from isobaras_core import red

CUERPO = bytes(range(256)) * 4  # 1024 bytes


class _Manejador(BaseHTTPRequestHandler):
    llamadas: dict[str, int] = {}

    def log_message(self, *args):  # keep the test output clean
        pass

    def _contar(self) -> int:
        n = self.llamadas.get(self.path, 0) + 1
        self.llamadas[self.path] = n
        return n

    def do_HEAD(self):
        self._contar()
        if self.path == "/existe":
            self.send_response(200)
        elif self.path == "/prohibido":
            self.send_response(403)
        elif self.path == "/inestable" and self.llamadas[self.path] == 1:
            self.send_response(503)
        elif self.path == "/inestable":
            self.send_response(200)
        else:
            self.send_response(404)
        self.end_headers()

    def do_GET(self):
        n = self._contar()
        if self.path == "/ignora-range":  # a server that sends everything even if a range was asked
            self.send_response(200)
            self.send_header("Content-Length", str(len(CUERPO)))
            self.end_headers()
            self.wfile.write(CUERPO)
        elif self.path == "/rango":
            inicio, fin = self.headers["Range"].removeprefix("bytes=").split("-")
            datos = CUERPO[int(inicio) : (int(fin) + 1) if fin else None]
            self.send_response(206)
            self.send_header("Content-Length", str(len(datos)))
            self.end_headers()
            self.wfile.write(datos)
        elif self.path == "/idx":
            self.send_response(200)
            self.send_header("Content-Length", "5")
            self.end_headers()
            self.wfile.write(b"hola\n")
        elif self.path == "/enorme-sin-rango":
            self.send_response(200)
            self.send_header("Content-Length", str(red.MAX_SIN_RANGO + 10))
            self.end_headers()
            self.wfile.write(b"x" * (red.MAX_SIN_RANGO + 10))
        elif self.path == "/inestable-get" and n == 1:
            self.send_response(503)
            self.end_headers()
        elif self.path == "/inestable-get":
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()


@pytest.fixture
def servidor(monkeypatch):
    monkeypatch.setattr(red, "ESPERA_S", 0)
    _Manejador.llamadas = {}
    http = ThreadingHTTPServer(("127.0.0.1", 0), _Manejador)
    hilo = threading.Thread(target=http.serve_forever, daemon=True)
    hilo.start()
    yield f"http://127.0.0.1:{http.server_address[1]}"
    http.shutdown()
    http.server_close()


def test_existe_es_true_con_200_y_false_con_403_y_404(servidor):
    assert red.existe(servidor + "/existe") is True
    assert red.existe(servidor + "/prohibido") is False
    assert red.existe(servidor + "/no-esta") is False


def test_existe_reintenta_un_503_pasajero(servidor):
    assert red.existe(servidor + "/inestable") is True
    assert _Manejador.llamadas["/inestable"] == 2


def test_fetch_con_rango_pide_los_bytes_justos_y_exige_206(servidor):
    assert red.fetch(servidor + "/rango", (10, 19)) == CUERPO[10:20]


def test_fetch_con_rango_abierto_trae_hasta_el_final(servidor):
    assert red.fetch(servidor + "/rango", (1000, None)) == CUERPO[1000:]


def test_un_servidor_que_ignora_el_rango_se_rechaza_sin_leer_todo(servidor):
    with pytest.raises(red.ErrorDeRed) as e:
        red.fetch(servidor + "/ignora-range", (0, 9))
    assert "206" in str(e.value)
    assert _Manejador.llamadas["/ignora-range"] == 1  # a protocol mismatch is not retried


def test_fetch_sin_rango_trae_el_cuerpo_chico(servidor):
    assert red.fetch(servidor + "/idx") == b"hola\n"


def test_fetch_sin_rango_rechaza_un_cuerpo_gigante(servidor):
    with pytest.raises(red.ErrorDeRed) as e:
        red.fetch(servidor + "/enorme-sin-rango")
    assert "tope" in str(e.value)


def test_un_404_del_get_no_se_reintenta(servidor):
    with pytest.raises(red.ErrorDeRed):
        red.fetch(servidor + "/no-esta", (0, 9))
    assert _Manejador.llamadas["/no-esta"] == 1


def test_un_503_del_get_si_se_reintenta(servidor):
    assert red.fetch(servidor + "/inestable-get") == b"ok"
    assert _Manejador.llamadas["/inestable-get"] == 2
