"""Assets of the plate, embedded as ``data:`` URIs so the render never touches the network.

- Logo: ``apps/frontend/public/Logo.png`` (the one the web uses).
- Sky icons: the Meteocons SVGs of the web (``apps/frontend/src/assets/meteocons``), without their
  animations so the screenshot is always the same, complete frame.
- Fonts: the app uses DM Sans and Playfair Display from Google Fonts, which needs internet. Drop
  their files (``.woff2``, ``.woff``, ``.ttf`` or ``.otf``) into ``plantillas/fuentes`` and they are
  embedded; without them the plate uses the system fonts named in ``plantillas/base.css``.
"""

from __future__ import annotations

import base64
import re
import xml.etree.ElementTree as ET  # nosec B405 - parses the repository's own icon files only
from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "apps" / "frontend"
LOGO_PATH = FRONTEND_DIR / "public" / "Logo.png"
METEOCONS_DIR = FRONTEND_DIR / "src" / "assets" / "meteocons"
FONTS_DIR = Path(__file__).resolve().parent / "plantillas" / "fuentes"

_ICON_KEY = re.compile(r"[a-z]+(?:-[a-z]+)*")
_SVG_NS = "http://www.w3.org/2000/svg"
_XLINK_NS = "http://www.w3.org/1999/xlink"
_ANIMATION_TAGS = frozenset({"animate", "animateTransform", "animateMotion", "set"})
ET.register_namespace("", _SVG_NS)
ET.register_namespace("xlink", _XLINK_NS)
_FONT_TYPES = {".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf", ".otf": "font/otf"}
_FONT_FAMILIES = {"dmsans": "DM Sans", "playfairdisplay": "Playfair Display"}
_FONT_WEIGHTS = {
    "thin": 100, "extralight": 200, "light": 300, "regular": 400, "medium": 500,
    "semibold": 600, "bold": 700, "extrabold": 800, "black": 900,
}
_VARIABLE_WEIGHTS = "100 1000"


class AssetError(Exception):
    """An asset the plate needs is missing or unreadable."""


def data_uri(content: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def strip_svg_animation(svg: str) -> str:
    """A static frame of an animated SVG: animations removed, fade-in elements left visible.

    Meteocons draw raindrops and snowflakes with ``opacity="0"`` and fade them in by animation, so
    removing the animations alone would leave an empty cloud: those elements are made visible.
    """
    try:
        root = ET.fromstring(svg)  # nosec B314 - trusted local file
    except ET.ParseError as exc:
        raise AssetError(f"Ícono SVG inválido: {exc}") from exc
    for parent in list(root.iter()):
        animations = [child for child in parent if _local(child.tag) in _ANIMATION_TAGS]
        fades_in = any(child.get("attributeName") == "opacity" for child in animations)
        if fades_in and parent.get("opacity") == "0":
            del parent.attrib["opacity"]
        for child in animations:
            parent.remove(child)
    return ET.tostring(root, encoding="unicode")


def logo_data_uri(path: Path = LOGO_PATH) -> str:
    try:
        return data_uri(path.read_bytes(), "image/png")
    except OSError as exc:
        raise AssetError(f"No se pudo leer el logo de SkyPulse ({path}): {exc}") from exc


def icon_data_uri(icon: str | None, folder: Path = METEOCONS_DIR) -> str | None:
    """Static sky icon for a whole day; None when the key is unknown (the text still says the sky)."""
    if not icon or not _ICON_KEY.fullmatch(icon):
        return None
    day_icon = icon.replace("-night", "-day")
    path = folder / f"{day_icon}.svg"
    if not path.is_file():
        return None
    try:
        svg = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise AssetError(f"No se pudo leer el ícono {path}: {exc}") from exc
    return data_uri(strip_svg_animation(svg).encode("utf-8"), "image/svg+xml")


def _font_face(path: Path) -> str | None:
    mime = _FONT_TYPES.get(path.suffix.lower())
    family_key, _, style = path.stem.partition("-")
    family_key = family_key.split("[", 1)[0].lower()
    family = _FONT_FAMILIES.get(family_key)
    if mime is None or family is None:
        return None
    variable = "[" in path.stem
    weight = _VARIABLE_WEIGHTS if variable else str(_FONT_WEIGHTS.get(style.lower(), 400))
    try:
        uri = data_uri(path.read_bytes(), mime)
    except OSError as exc:
        raise AssetError(f"No se pudo leer la fuente {path}: {exc}") from exc
    return (
        f"@font-face{{font-family:'{family}';font-weight:{weight};font-style:normal;"
        f"font-display:block;src:url({uri})}}"
    )


def font_faces_css(folder: Path = FONTS_DIR) -> str:
    """``@font-face`` rules for the app fonts found in `folder`; empty when there are none."""
    if not folder.is_dir():
        return ""
    faces = (_font_face(path) for path in sorted(folder.iterdir()) if path.is_file())
    return "\n".join(face for face in faces if face)
