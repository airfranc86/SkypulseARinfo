"""Zonas de alertas push: las ciudades de `apps/frontend/src/lib/cities-ar.ts`.

Una zona = una ciudad. No hay copia automática del frontend: el test de
paridad (`tests/test_alertas_regla.py`) falla si las listas se desalinean.
El `slug` se deriva del nombre (minúsculas, sin tildes, con guiones) porque
el `.ts` no trae `id`.
"""

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Zona:
    slug: str
    nombre: str
    provincia: str
    lat: float
    lon: float


def _slug(nombre: str) -> str:
    sin_tildes = unicodedata.normalize("NFD", nombre).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", sin_tildes.lower()).strip("-")


# (nombre, provincia, lat, lon), en el mismo orden que cities-ar.ts.
_CIUDADES: tuple[tuple[str, str, float, float], ...] = (
    ("Buenos Aires", "CABA", -34.6037, -58.3816),
    ("Córdoba", "Córdoba", -31.4135, -64.181),
    ("Rosario", "Santa Fe", -32.9587, -60.6931),
    ("Mendoza", "Mendoza", -32.8895, -68.8458),
    ("Tucumán", "Tucumán", -26.8083, -65.2176),
    ("La Plata", "Buenos Aires", -34.9205, -57.9536),
    ("Mar del Plata", "Buenos Aires", -38.0, -57.5667),
    ("Salta", "Salta", -24.7859, -65.4117),
    ("Santa Fe", "Santa Fe", -31.6333, -60.7),
    ("San Juan", "San Juan", -31.5375, -68.5364),
    ("Resistencia", "Chaco", -27.46, -58.9867),
    ("Neuquén", "Neuquén", -38.9516, -68.0591),
    ("Santiago del Estero", "Santiago del Estero", -27.7951, -64.2615),
    ("Corrientes", "Corrientes", -27.4692, -58.8306),
    ("Posadas", "Misiones", -27.3671, -55.8964),
    ("San Salvador de Jujuy", "Jujuy", -24.1858, -65.2995),
    ("Bahía Blanca", "Buenos Aires", -38.7196, -62.2724),
    ("Paraná", "Entre Ríos", -31.7333, -60.5333),
    ("Formosa", "Formosa", -26.1775, -58.1781),
    ("San Luis", "San Luis", -33.295, -66.3356),
    ("La Rioja", "La Rioja", -29.4, -66.85),
    ("Catamarca", "Catamarca", -28.4696, -65.7852),
    ("Rawson", "Chubut", -43.3002, -65.1023),
    ("Río Gallegos", "Santa Cruz", -51.6226, -69.2181),
    ("Ushuaia", "Tierra del Fuego", -54.8, -68.3),
    ("Viedma", "Río Negro", -40.8135, -62.9967),
    ("Santa Rosa", "La Pampa", -36.6167, -64.2833),
    ("Bariloche", "Río Negro", -41.1335, -71.3103),
    ("Comodoro Rivadavia", "Chubut", -45.8645, -67.4853),
    ("Tandil", "Buenos Aires", -37.3217, -59.1332),
    ("Junín", "Buenos Aires", -34.5921, -60.9558),
    ("San Rafael", "Mendoza", -34.6177, -68.3301),
    ("Villa Mercedes", "San Luis", -33.675, -65.4597),
    ("Concordia", "Entre Ríos", -31.3927, -58.0199),
    ("Olavarría", "Buenos Aires", -36.8924, -60.3228),
    ("Río Cuarto", "Córdoba", -33.1232, -64.3493),
    ("Moreno", "Buenos Aires", -34.4157, -58.5634),
    ("Zárate", "Buenos Aires", -34.0982, -59.0278),
    ("Pergamino", "Buenos Aires", -33.8899, -60.5705),
    ("San Nicolás", "Buenos Aires", -33.3333, -60.2167),
    ("Lomas de Zamora", "Buenos Aires", -34.7611, -58.4032),
    ("Quilmes", "Buenos Aires", -34.7228, -58.2592),
    ("Lanús", "Buenos Aires", -34.7007, -58.3908),
    ("Morón", "Buenos Aires", -34.6534, -58.6198),
    ("San Miguel", "Buenos Aires", -34.5422, -58.7079),
    ("Malargüe", "Mendoza", -35.4765, -69.5839),
    ("Caleta Olivia", "Santa Cruz", -46.4333, -67.5167),
    ("Puerto Madryn", "Chubut", -42.7682, -65.0366),
    ("Esquel", "Chubut", -42.9144, -71.3187),
    ("El Calafate", "Santa Cruz", -50.3375, -72.2742),
)

ZONAS: tuple[Zona, ...] = tuple(
    Zona(slug=_slug(n), nombre=n, provincia=p, lat=la, lon=lo) for n, p, la, lo in _CIUDADES
)

_POR_SLUG: dict[str, Zona] = {z.slug: z for z in ZONAS}


def zona_por_slug(slug: str) -> Zona | None:
    return _POR_SLUG.get(slug)
