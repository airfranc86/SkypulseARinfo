"""Fixtures compartidas de las pruebas del asistente."""
import pytest

from app.services.asistente import cupos, interruptor


@pytest.fixture(autouse=True)
def interruptor_sin_memoria():
    """El interruptor recuerda su última lectura 60 s y los cupos recuerdan a los agotados: cada prueba arranca sin eso."""
    interruptor.olvidar()
    cupos.olvidar()
    yield
    interruptor.olvidar()
    cupos.olvidar()
