"""Tests de integración para POST /api/v1/aeronautica/wind-shear."""
from __future__ import annotations

import json

import pytest
from httpx import AsyncClient

URL = "/api/v1/aeronautica/wind-shear"

# Perfil completo: 270/10 (ráfaga 18) en superficie, 270/30 a 500 ft, 270/40 a 1.000 ft,
# 20 °C en superficie y 18 °C a 1.000 ft. Capas: 4,0 y 2,0 kt/100 ft → amarillo por cizalladura.
VALID_BODY = {
    "surface_wind_dir_deg": 270,
    "surface_wind_speed_kt": 10,
    "surface_gust_kt": 18,
    "wind_500ft_dir_deg": 270,
    "wind_500ft_speed_kt": 30,
    "wind_1000ft_dir_deg": 270,
    "wind_1000ft_speed_kt": 40,
    "surface_temp_c": 20,
    "temp_1000ft_c": 18,
}

OPTIONAL_FIELDS = (
    "surface_gust_kt",
    "wind_1000ft_dir_deg",
    "wind_1000ft_speed_kt",
    "surface_temp_c",
    "temp_1000ft_c",
)

# El límite de la ruta es 30/min y el limiter no se resetea entre tests: se mantiene bajo el
# total de requests VÁLIDOS (los 422 no llegan a la función decorada y no cuentan).
MINIMAL_BODY = {k: v for k, v in VALID_BODY.items() if k not in OPTIONAL_FIELDS}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_wind_shear_happy_path(async_client: AsyncClient):
    response = await async_client.post(URL, json=VALID_BODY)

    assert response.status_code == 200
    data = response.json()
    assert data["risk"]["level"] == "amarillo"
    assert data["risk"]["code"] == "SHEAR_MODERATE"
    assert data["risk"]["message"]
    assert data["drivers"] == ["shear"]
    calc = data["calculations"]
    assert calc["layers"] == [
        {"from_ft": 0, "to_ft": 500, "shear_kt_per_100ft": 4.0},
        {"from_ft": 500, "to_ft": 1000, "shear_kt_per_100ft": 2.0},
    ]
    assert calc["max_shear_kt_per_100ft"] == 4.0
    assert calc["max_layer"] == {"from_ft": 0, "to_ft": 500}
    assert calc["gust_spread_kt"] == 8.0
    assert calc["thermal"] == {"code": "neutral", "lapse_c_per_1000ft": 2.0}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_response_echoes_inputs(async_client: AsyncClient):
    data = (await async_client.post(URL, json=VALID_BODY)).json()

    assert data["inputs"] == VALID_BODY


@pytest.mark.asyncio
@pytest.mark.integration
async def test_optional_inputs_absent_gives_single_layer_and_null_thermal(async_client: AsyncClient):
    response = await async_client.post(URL, json=MINIMAL_BODY)

    assert response.status_code == 200
    data = response.json()
    assert [(layer["from_ft"], layer["to_ft"]) for layer in data["calculations"]["layers"]] == [(0, 500)]
    assert data["calculations"]["thermal"] is None
    assert data["calculations"]["gust_spread_kt"] == 0.0
    for key in OPTIONAL_FIELDS:
        assert data["inputs"][key] is None, key


@pytest.mark.asyncio
@pytest.mark.integration
async def test_explicit_nulls_for_optional_fields_are_accepted(async_client: AsyncClient):
    body = {**MINIMAL_BODY, **{key: None for key in OPTIONAL_FIELDS}}

    response = await async_client.post(URL, json=body)

    assert response.status_code == 200
    assert response.json()["calculations"]["thermal"] is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_large_gust_spread_forces_red_with_gust_driver(async_client: AsyncClient):
    response = await async_client.post(URL, json={**VALID_BODY, "surface_gust_kt": 40})

    assert response.status_code == 200
    data = response.json()
    assert data["risk"]["level"] == "rojo"
    assert data["risk"]["code"] == "SHEAR_EXTREME"
    assert data["drivers"] == ["gust_spread"]
    assert data["calculations"]["gust_spread_kt"] == 30.0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_gust_equal_to_sustained_speed_is_accepted(async_client: AsyncClient):
    response = await async_client.post(URL, json={**VALID_BODY, "surface_gust_kt": 10})

    assert response.status_code == 200
    assert response.json()["calculations"]["gust_spread_kt"] == 0.0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_upper_layer_can_be_the_max_layer(async_client: AsyncClient):
    body = {**VALID_BODY, "wind_500ft_speed_kt": 12, "wind_1000ft_speed_kt": 60, "wind_1000ft_dir_deg": 270}

    data = (await async_client.post(URL, json=body)).json()

    # 270/10 → 270/12 (0,4) y 270/12 → 270/60 (9,6): naranja por la capa alta.
    assert data["calculations"]["max_layer"] == {"from_ft": 500, "to_ft": 1000}
    assert data["calculations"]["max_shear_kt_per_100ft"] == 9.6
    assert data["risk"]["level"] == "naranja"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_thermal_inversion_is_reported_but_does_not_change_the_level(async_client: AsyncClient):
    body = {**VALID_BODY, "surface_temp_c": 10, "temp_1000ft_c": 14}

    data = (await async_client.post(URL, json=body)).json()

    assert data["calculations"]["thermal"] == {"code": "inversion", "lapse_c_per_1000ft": -4.0}
    assert data["risk"]["level"] == "amarillo"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_values_are_served_with_the_precision_the_level_was_decided_on(async_client: AsyncClient):
    # El router ya no redondea a 2 decimales: el valor servido es el mismo número (a 6 decimales)
    # con el que se decidió el nivel, así que nunca lo contradice.
    body = {
        **MINIMAL_BODY,
        "surface_wind_dir_deg": 0,
        "surface_wind_speed_kt": 3.333,
        "surface_gust_kt": 10,
        "wind_500ft_dir_deg": 0,
        "wind_500ft_speed_kt": 16.67,  # ΔV = 13,337 kt → 2,6674 kt/100 ft
        "surface_temp_c": 20.123,
        "temp_1000ft_c": 18,
    }

    calc = (await async_client.post(URL, json=body)).json()["calculations"]

    assert calc["layers"][0]["shear_kt_per_100ft"] == 2.6674
    assert calc["max_shear_kt_per_100ft"] == 2.6674
    assert calc["gust_spread_kt"] == 6.667
    assert calc["thermal"]["lapse_c_per_1000ft"] == 2.123


@pytest.mark.asyncio
@pytest.mark.integration
async def test_near_threshold_value_is_served_unrounded_and_matches_the_level(async_client: AsyncClient):
    # 19,98 kt a 500 ft con superficie en calma: 3,996 kt/100 ft. Es verde y se sirve 3,996
    # (antes se redondeaba a 4,0, que es el umbral de amarillo: el valor contradecía al nivel).
    body = {**MINIMAL_BODY, "surface_wind_speed_kt": 0, "wind_500ft_speed_kt": 19.98}

    data = (await async_client.post(URL, json=body)).json()

    assert data["risk"]["level"] == "verde"
    assert data["calculations"]["max_shear_kt_per_100ft"] == 3.996
    assert data["calculations"]["layers"][0]["shear_kt_per_100ft"] == 3.996


@pytest.mark.asyncio
@pytest.mark.integration
async def test_float_noise_at_a_boundary_is_not_served_nor_decided_on(async_client: AsyncClient):
    # 10 → 30 kt rumbo 7: la cizalladura exacta es 4,0 (amarillo); en coma flotante cruda daba
    # 3.999999999999999 (verde). Ráfaga 25,1 − 10,1 daba 15.000000000000002 (rojo).
    shear_body = {**MINIMAL_BODY, "surface_wind_dir_deg": 7, "wind_500ft_dir_deg": 7,
                  "surface_wind_speed_kt": 10, "wind_500ft_speed_kt": 30}
    gust_body = {**MINIMAL_BODY, "surface_wind_dir_deg": 7, "wind_500ft_dir_deg": 7,
                 "surface_wind_speed_kt": 10.1, "wind_500ft_speed_kt": 10.1, "surface_gust_kt": 25.1}

    shear = (await async_client.post(URL, json=shear_body)).json()
    gust = (await async_client.post(URL, json=gust_body)).json()

    assert shear["risk"]["level"] == "amarillo"
    assert shear["calculations"]["max_shear_kt_per_100ft"] == 4.0
    assert gust["risk"]["level"] == "verde"
    assert gust["calculations"]["gust_spread_kt"] == 15.0


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize(
    "override",
    [
        {"surface_gust_kt": 5},                                  # ráfaga menor que el sostenido
        {"wind_1000ft_dir_deg": None},                           # solo la rapidez a 1.000 ft
        {"wind_1000ft_speed_kt": None},                          # solo la dirección a 1.000 ft
        {"surface_temp_c": None},                                # solo la temperatura a 1.000 ft
        {"temp_1000ft_c": None},                                 # solo la temperatura de superficie
    ],
)
async def test_cross_field_validators_return_422(async_client: AsyncClient, override):
    response = await async_client.post(URL, json={**VALID_BODY, **override})

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize(
    "override",
    [
        {"surface_wind_dir_deg": 361},
        {"surface_wind_dir_deg": -1},
        {"wind_500ft_dir_deg": 400},
        {"wind_1000ft_dir_deg": 361},
        {"surface_wind_speed_kt": -5},
        {"surface_wind_speed_kt": 101},
        {"surface_gust_kt": 151},
        {"wind_500ft_speed_kt": -1},
        {"wind_500ft_speed_kt": 151},
        {"wind_1000ft_speed_kt": 151},
        {"surface_temp_c": 61},
        {"temp_1000ft_c": -61},
        {"surface_wind_dir_deg": "abc"},
    ],
)
async def test_out_of_range_or_invalid_fields_return_422(async_client: AsyncClient, override):
    response = await async_client.post(URL, json={**VALID_BODY, **override})

    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "invalid_request"
    assert "abc" not in response.text


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize(
    "override",
    [
        {"surface_wind_speed_kt": 987.654},   # fuera de rango
        {"surface_gust_kt": 3.14159},         # falla el validador cruzado (ráfaga < sostenido)
    ],
)
async def test_422_never_echoes_the_received_value(async_client: AsyncClient, override):
    response = await async_client.post(URL, json={**VALID_BODY, **override})

    assert response.status_code == 422
    sent = str(next(iter(override.values())))
    assert sent not in response.text


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize(
    "missing",
    ["surface_wind_dir_deg", "surface_wind_speed_kt", "wind_500ft_dir_deg", "wind_500ft_speed_kt"],
)
async def test_missing_required_field_returns_invalid_request(async_client: AsyncClient, missing):
    body = {k: v for k, v in VALID_BODY.items() if k != missing}

    response = await async_client.post(URL, json=body)

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("field", ["surface_wind_speed_kt", "surface_gust_kt", "wind_500ft_dir_deg", "temp_1000ft_c"])
@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
async def test_non_finite_numbers_return_422_not_500(async_client: AsyncClient, field, token):
    # httpx no serializa NaN/Inf con json=; se manda el JSON crudo que aceptaría json.loads.
    raw = json.dumps({**VALID_BODY, field: "__TOKEN__"}).replace('"__TOKEN__"', token)

    response = await async_client.post(URL, content=raw, headers={"Content-Type": "application/json"})

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cors_preflight_allows_post(async_client: AsyncClient):
    response = await async_client.options(
        URL,
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert "POST" in response.headers["access-control-allow-methods"]
