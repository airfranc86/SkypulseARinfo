"""El CORS por defecto: el dominio legado ya no está; localhost y el frontend activo sí."""
from __future__ import annotations

import pytest

from app.core.config import Settings

DOMINIO_LEGADO = "skypulseinfo.vercel.app"
ORIGENES_ESPERADOS = ["http://localhost:5173", "https://skypulse-ar.vercel.app"]


@pytest.fixture
def cors_por_defecto(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Los orígenes con los que arranca la app sin `CORS_ORIGINS` en el entorno ni `.env`."""
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    return Settings(_env_file=None).cors_origins  # type: ignore[call-arg]


def test_el_cors_por_defecto_no_incluye_el_dominio_legado(cors_por_defecto: list[str]) -> None:
    assert not any(DOMINIO_LEGADO in origen for origen in cors_por_defecto)


def test_el_cors_por_defecto_conserva_localhost_y_el_frontend_activo(cors_por_defecto: list[str]) -> None:
    assert cors_por_defecto == ORIGENES_ESPERADOS


def test_el_valor_declarado_del_campo_tampoco_menciona_el_dominio_legado() -> None:
    declarado = Settings.model_fields["cors_origins"].default
    assert DOMINIO_LEGADO not in str(declarado)


def test_cors_origins_sigue_siendo_configurable_por_entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "https://uno.example.test, https://dos.example.test")
    assert Settings(_env_file=None).cors_origins == [  # type: ignore[call-arg]
        "https://uno.example.test",
        "https://dos.example.test",
    ]
