"""Fixtures compartidas de las pruebas del asistente."""
import pytest

from app.core.config import settings
from app.services.asistente import cupos, interruptor


@pytest.fixture(autouse=True)
def sin_clave_de_groq(monkeypatch):
    """Una clave en el `.env` local de quien corre las pruebas no puede volver real el modelo de un test que no la pide."""
    monkeypatch.setattr(settings, "groq_api_key", "")


@pytest.fixture(autouse=True)
def interruptor_sin_memoria():
    """El interruptor recuerda su última lectura 60 s y los cupos recuerdan a los agotados: cada prueba arranca sin eso."""
    interruptor.olvidar()
    cupos.olvidar()
    yield
    interruptor.olvidar()
    cupos.olvidar()
