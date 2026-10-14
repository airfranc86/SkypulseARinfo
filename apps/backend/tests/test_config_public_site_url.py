"""PUBLIC_SITE_URL: the one place the public domain of the site is declared (backend)."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.services.alertas import envio
from app.services.reportes_aeronauticos import awc
from app.services import smn_alertas

SITIO = "https://skypulse-ar.vercel.app"


def _ajustes(**valores: str) -> Settings:
    return Settings(_env_file=None, **valores)


def test_por_defecto_es_el_sitio_actual() -> None:
    assert _ajustes().public_site_url == SITIO


def test_se_normaliza_sin_barra_final() -> None:
    assert _ajustes(public_site_url="https://skypulse.example/").public_site_url == "https://skypulse.example"
    assert _ajustes(public_site_url="  https://skypulse.example  ").public_site_url == "https://skypulse.example"


def test_acepta_localhost_sin_https_para_desarrollo() -> None:
    assert _ajustes(public_site_url="http://localhost:5173").public_site_url == "http://localhost:5173"


@pytest.mark.parametrize("malo", ["", "skypulse.example", "http://skypulse.example", "javascript:alert(1)", "https://", "https://a.b/ruta"])
def test_rechaza_lo_que_no_es_un_origen_https(malo: str) -> None:
    with pytest.raises(ValidationError):
        _ajustes(public_site_url=malo)


def test_site_url_arma_direcciones_del_mismo_origen() -> None:
    ajustes = _ajustes(public_site_url="https://skypulse.example/")
    assert ajustes.site_url() == "https://skypulse.example"
    assert ajustes.site_url("/prevision") == "https://skypulse.example/prevision"


def test_el_comportamiento_de_hoy_no_cambia() -> None:
    assert envio.URL_ALERTAS == f"{SITIO}/prevision"
    assert awc.AWC_USER_AGENT == f"SkyPulse/1.0 (+{SITIO})"
    assert smn_alertas._HEADERS["User-Agent"] == f"SkyPulse/1.0 (+{SITIO})"
    assert _ajustes().vapid_subject == SITIO
