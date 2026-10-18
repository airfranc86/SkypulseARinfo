"""Corre los conjuntos dorado y rojo contra el MODELO REAL de Groq y arma un informe. Lo corre el DUEÑO: gasta cupo del día.

    uv run --no-project --python 3.12 --with-requirements requirements.txt python -m tests.asistente.correr_real --listar
    uv run --no-project --python 3.12 --with-requirements requirements.txt python -m tests.asistente.correr_real --max 10

(desde `apps/backend`; la clave `GROQ_API_KEY` se lee del `.env` local, igual que la app, y nunca se imprime.)

Qué corre: los 49 casos del conjunto dorado y las preguntas hostiles del rojo (las otras entradas del rojo prueban al verificador
solo, sin modelo, y ya corren en la suite). Cada caso pasa por el MISMO camino que una pregunta real (`responder`: enrutador, hoja,
modelo, verificador, frases fijas) con la hoja de su escenario. Lo que mide:

- cuántas respuestas el verificador rechaza (y por qué motivo): una tasa alta dice que el prompt o el modelo no sirven;
- cuántos tokens gastó cada pregunta (`usage.total_tokens` de Groq) y cuánto tardó;
- si cada respuesta cumple lo que el conjunto espera (estado, frases que tiene que traer y que no puede traer). Un modelo real
  redacta distinto del falso: una discrepancia es algo para MIRAR, no necesariamente un error;
- una proyección de cuántas preguntas entran por día y por minuto en el plan gratuito y qué cupos conviene configurar.

El plan gratuito tiene 8K tokens por minuto y 200K por día: el script espera entre pregunta y pregunta (`--pausa`) y por eso corre
poco por vez (`--max 10` por defecto; `--desde` sigue donde se quedó; `--todos` corre todo y gasta cerca del 40 % del día).
Pide confirmación antes de gastar (`--si` la saltea) y `--listar` muestra el plan y el costo sin llamar a nadie.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.core import http_client, usage_counter
from app.core.config import settings
from app.services.asistente.modelo import Modelo, ModeloNoDisponible
from app.services.asistente.nucleo import responder
from app.services.asistente.proveedores.groq import ModeloGroq
from app.services.asistente.verificador import MAX_CARACTERES
from tests.asistente import escenarios as esc

DIR = Path(__file__).parent
CONJUNTOS = ("dorado", "rojo", "ambos")

# Los límites del plan gratuito de Groq para openai/gpt-oss-20b y qwen/qwen3.8-27b (consola del dueño, 2026-10-18).
TOKENS_POR_DIA = 200_000
TOKENS_POR_MINUTO = 8_000
TOKENS_TIPICOS_POR_PREGUNTA = 1_400  # estimación previa a medir; el informe da los reales
TOKENS_PESIMISTAS_POR_PREGUNTA = 1_900
MARGEN_DE_SEGURIDAD = 0.9  # nunca planear con el 100 % del día

ESPERA_MAXIMA_SEGUNDOS = 120  # lo más que se espera por un 429 antes de reintentar
MOTIVOS_QUE_FRENAN = frozenset({"sin_clave", "credenciales"})  # sin clave válida, el resto de las preguntas fallaría igual


@dataclass(frozen=True)
class Caso:
    id: str
    conjunto: str
    escenario: str
    pregunta: str
    pagina: str | None
    estado_esperado: str
    contiene: tuple[str, ...]
    no_contiene: tuple[str, ...]


@dataclass(frozen=True)
class Resultado:
    caso: Caso
    estado: str | None  # None: no hubo respuesta (el modelo no estuvo disponible)
    motivos: tuple[str, ...]
    texto: str
    tokens: int | None
    ms: int
    error: str | None
    discrepancias: tuple[str, ...]


# ---------------------------------------------------------------------------------------------------------------- casos y plan

def _leer(nombre: str) -> list[dict[str, Any]]:
    return json.loads((DIR / nombre).read_text(encoding="utf-8"))


def _caso(conjunto: str, c: dict[str, Any]) -> Caso:
    return Caso(
        id=c["id"], conjunto=conjunto, escenario=c["escenario"], pregunta=c["pregunta"], pagina=c.get("pagina"),
        estado_esperado=c.get("estado", "ok"), contiene=tuple(c.get("contiene", [])), no_contiene=tuple(c.get("no_contiene", [])),
    )


def cargar_casos(conjunto: str) -> list[Caso]:
    """Los casos de un conjunto. Del rojo solo las preguntas hostiles: lo demás prueba al verificador, sin modelo."""
    if conjunto not in CONJUNTOS:
        raise ValueError(f"conjunto desconocido: {conjunto!r} (los válidos son {', '.join(CONJUNTOS)})")
    dorado = [_caso("dorado", c) for c in _leer("golden.json")]
    rojo = [_caso("rojo", c) for c in _leer("red.json") if c["tipo"] == "pregunta"]
    return {"dorado": dorado, "rojo": rojo, "ambos": dorado + rojo}[conjunto]


def plan(casos: list[Caso], desde: int, maximo: int | None) -> list[Caso]:
    """Los casos de esta corrida: desde la posición `desde`, hasta `maximo` (None: todos los que siguen)."""
    desde = max(0, desde)
    return casos[desde:] if maximo is None else casos[desde : desde + max(0, maximo)]


def pausa_entre_preguntas(tokens_por_pregunta: int = TOKENS_PESIMISTAS_POR_PREGUNTA, tpm: int = TOKENS_POR_MINUTO) -> int:
    """Segundos entre pregunta y pregunta para no pasar los tokens por minuto, con un segundo de margen."""
    return math.ceil(60 * tokens_por_pregunta / tpm) + 1


# ------------------------------------------------------------------------------------------------------------------ evaluación

def discrepancias(caso: Caso, estado: str, texto: str) -> list[str]:
    """Lo que la respuesta no cumple de lo que el conjunto espera. Vacío = cumple."""
    encontradas: list[str] = []
    if estado != caso.estado_esperado:
        encontradas.append(f"estado {estado} (esperado {caso.estado_esperado})")
    if len(texto) > MAX_CARACTERES:
        encontradas.append(f"larga ({len(texto)} caracteres)")
    encontradas += [f"falta «{frase}»" for frase in caso.contiene if frase not in texto]
    encontradas += [f"sobra «{frase}»" for frase in caso.no_contiene if frase in texto]
    return encontradas


def _p95(valores: list[int]) -> int | None:
    if not valores:
        return None
    ordenados = sorted(valores)
    return ordenados[min(len(ordenados) - 1, math.ceil(0.95 * len(ordenados)) - 1)]


def resumen(resultados: list[Resultado]) -> dict[str, Any]:
    tokens = [r.tokens for r in resultados if r.tokens is not None]
    tiempos = [r.ms for r in resultados]
    motivos = Counter(m for r in resultados for m in r.motivos)
    return {
        "total": len(resultados),
        "ok": sum(r.estado == "ok" for r in resultados),
        "sin_dato": sum(r.estado == "sin_dato" for r in resultados),
        "fuera_de_alcance": sum(r.estado == "fuera_de_alcance" for r in resultados),
        "errores": sum(r.error is not None for r in resultados),
        "motivos": dict(motivos),
        "con_discrepancias": sum(bool(r.discrepancias) for r in resultados),
        "tokens_medidos": len(tokens),
        "tokens_total": sum(tokens),
        "tokens_promedio": round(sum(tokens) / len(tokens)) if tokens else None,
        "tokens_maximo": max(tokens) if tokens else None,
        "ms_promedio": round(sum(tiempos) / len(tiempos)) if tiempos else None,
        "ms_p95": _p95(tiempos),
    }


def proyeccion(promedio: int | None, maximo: int | None) -> dict[str, int] | None:
    """Cuántas preguntas entran en el plan gratuito con lo MEDIDO, y los cupos que conviene configurar (con margen)."""
    if not promedio or not maximo:
        return None
    por_dia_pesimista = int(TOKENS_POR_DIA * MARGEN_DE_SEGURIDAD // maximo)
    cupo_global = max(5, por_dia_pesimista // 5 * 5)
    return {
        "por_dia_tipico": int(TOKENS_POR_DIA * MARGEN_DE_SEGURIDAD // promedio),
        "por_dia_pesimista": por_dia_pesimista,
        "por_minuto": TOKENS_POR_MINUTO // maximo,
        "cupo_global_sugerido": cupo_global,
        "cupo_cliente_sugerido": max(1, cupo_global // 10),
    }


# ------------------------------------------------------------------------------------------------------------------------ informe

def _celda(texto: object, largo: int = 160) -> str:
    """Un texto en una celda de tabla: sin saltos de línea ni barras, y acotado."""
    limpio = " ".join(str(texto).split()).replace("|", "¦")
    return limpio if len(limpio) <= largo else limpio[: largo - 1] + "…"


def formatear_informe(
    resultados: list[Resultado], r: dict[str, Any], p: dict[str, int] | None, ahora: datetime, modelo: str,
) -> str:
    lineas = [
        f"# Mora contra el modelo real: {ahora.strftime('%Y-%m-%d %H:%M')} UTC",
        "",
        f"Modelo: `{modelo}`. Preguntas corridas: {r['total']}.",
        "",
        "## Resumen",
        "",
        f"- Respondidas bien (`ok`): {r['ok']}. Rechazadas por el verificador (`sin_dato`): {r['sin_dato']}. "
        f"Fuera de alcance: {r['fuera_de_alcance']}. Sin respuesta del modelo: {r['errores']}.",
        f"- Motivos de rechazo: {', '.join(f'{m} ×{n}' for m, n in r['motivos'].items()) or 'ninguno'}.",
        f"- Preguntas con alguna discrepancia contra lo que el conjunto espera: {r['con_discrepancias']} "
        "(un modelo real redacta distinto del falso: es para mirar, no necesariamente un error).",
        f"- Tokens: {r['tokens_medidos']} medidos, {r['tokens_total']} en total, promedio {r['tokens_promedio']}, "
        f"máximo {r['tokens_maximo']}.",
        f"- Tiempo por pregunta: promedio {r['ms_promedio']} ms, p95 {r['ms_p95']} ms (el endpoint corta a los 12 s).",
        "",
        "## Qué cupos conviene configurar",
        "",
    ]
    if p is None:
        lineas.append("Sin tokens medidos no se puede proyectar nada (¿el modelo no respondió?).")
    else:
        lineas += [
            f"Con el plan gratuito (200K tokens por día y 8K por minuto, con {int(MARGEN_DE_SEGURIDAD * 100)} % de margen):",
            "",
            f"- Preguntas por día: unas {p['por_dia_tipico']} con el gasto promedio y {p['por_dia_pesimista']} con el máximo medido.",
            f"- Preguntas por minuto de todo el sitio: unas {p['por_minuto']} (si se pasa, Groq responde 429 y Mora pasa al modo degradado).",
            f"- Sugerido: `ASISTENTE_CUPO_GLOBAL_DIA={p['cupo_global_sugerido']}` y `ASISTENTE_CUPO_CLIENTE_DIA={p['cupo_cliente_sugerido']}`.",
        ]
    lineas += [
        "",
        "## Casos",
        "",
        "| Caso | Conjunto | Estado | Tokens | ms | Motivos / discrepancias | Respuesta |",
        "|---|---|---|---|---|---|---|",
    ]
    for res in resultados:
        notas = [*res.motivos, *res.discrepancias] + ([f"error: {res.error}"] if res.error else [])
        lineas.append(
            f"| {res.caso.id} | {res.caso.conjunto} | {res.estado or '-'} | {res.tokens if res.tokens is not None else '-'} "
            f"| {res.ms} | {_celda('; '.join(notas)) or '-'} | {_celda(res.texto)} |"
        )
    return "\n".join(lineas) + "\n"


# ------------------------------------------------------------------------------------------------------------------------ correr

async def _preguntar(caso: Caso, modelo: Modelo) -> Any:
    return await responder(caso.pregunta, esc.ESCENARIOS[caso.escenario](), modelo, pagina=caso.pagina, ahora_utc=esc.AHORA)


async def correr(
    casos: list[Caso], modelo: Modelo, *, pausa: float, dormir: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> list[Resultado]:
    """Pregunta cada caso, esperando `pausa` entre uno y otro. Una falla se reintenta UNA vez (si fue un límite de Groq, tras
    esperar lo que pide, con tope); si sigue fallando queda anotada y la corrida sigue. Sin clave válida se frena enseguida."""
    resultados: list[Resultado] = []
    for posicion, caso in enumerate(casos):
        if posicion > 0:
            await dormir(pausa)
        inicio = time.monotonic()
        respuesta, error = None, None
        for intento in (1, 2):
            try:
                respuesta = await _preguntar(caso, modelo)
                error = None
                break
            except ModeloNoDisponible as exc:
                error = exc.motivo
                if exc.motivo in MOTIVOS_QUE_FRENAN or intento == 2:
                    break
                espera = min(exc.reintentar_en, ESPERA_MAXIMA_SEGUNDOS) if exc.reintentar_en else pausa
                await dormir(espera)
        ms = round((time.monotonic() - inicio) * 1000)
        tokens = getattr(modelo, "tokens_ultima_llamada", None)
        if respuesta is None:
            resultados.append(Resultado(caso, None, (), "", tokens, ms, error, ()))
            if error in MOTIVOS_QUE_FRENAN:
                break
            continue
        resultados.append(Resultado(
            caso, respuesta.estado, tuple(respuesta.motivos), respuesta.texto, tokens, ms, None,
            tuple(discrepancias(caso, respuesta.estado, respuesta.texto)),
        ))
    return resultados


async def _ejecutar(casos: list[Caso], pausa: float) -> list[Resultado]:
    await http_client.create_client()
    usage_counter.configure_memory()
    try:
        return await correr(casos, ModeloGroq(), pausa=pausa)
    finally:
        await http_client.close_client()


# ------------------------------------------------------------------------------------------------------------------ línea de comandos

def _miles(numero: int) -> str:
    return f"{numero:,}".replace(",", ".")


def _costo(n: int, pausa: float) -> str:
    bajo, alto = n * TOKENS_TIPICOS_POR_PREGUNTA, n * TOKENS_PESIMISTAS_POR_PREGUNTA
    minutos = f"{n * pausa / 60:.1f}".replace(".", ",")
    return (
        f"{n} preguntas: unos {_miles(bajo)} a {_miles(alto)} tokens ({bajo * 100 / TOKENS_POR_DIA:.0f} a "
        f"{alto * 100 / TOKENS_POR_DIA:.0f} % de los {_miles(TOKENS_POR_DIA)} del día), unos {minutos} minutos con "
        f"{pausa:g} s entre preguntas"
    )


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="correr_real", description="Corre el dorado y el rojo contra el modelo real de Groq.")
    parser.add_argument("--conjunto", choices=CONJUNTOS, default="ambos")
    parser.add_argument("--desde", type=int, default=0, help="posición del primer caso (para seguir donde se quedó)")
    parser.add_argument("--max", type=int, default=10, help="cuántas preguntas correr (por defecto 10: cuida el cupo del día)")
    parser.add_argument("--todos", action="store_true", help="correr todas las que siguen (gasta cerca del 40 %% del día)")
    parser.add_argument("--pausa", type=float, default=float(pausa_entre_preguntas()), help="segundos entre preguntas")
    parser.add_argument("--listar", action="store_true", help="mostrar el plan y el costo, sin llamar a nadie")
    parser.add_argument("--si", action="store_true", help="no pedir confirmación")
    parser.add_argument("--salida", type=Path, default=None, help="dónde escribir el informe (por defecto docs/reportes/)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _argumentos(argv)
    casos = plan(cargar_casos(args.conjunto), args.desde, None if args.todos else args.max)
    print(f"Plan ({args.conjunto}, desde {args.desde}): {_costo(len(casos), args.pausa)}.")
    if args.listar:
        for caso in casos:
            print(f"  {caso.id}  [{caso.escenario}]  {caso.pregunta}")
        return 0
    if not casos:
        print("No hay casos para correr con esos parámetros.")
        return 0
    if not settings.groq_api_key.strip():
        print("Falta GROQ_API_KEY en el entorno o en el .env local de apps/backend.")
        return 2
    if not args.si and input("Esto gasta cupo del día de Groq. ¿Seguir? [s/N] ").strip().lower() not in {"s", "si", "sí"}:
        print("Cancelado: no se gastó nada.")
        return 1

    resultados = asyncio.run(_ejecutar(casos, args.pausa))
    ahora = datetime.now(timezone.utc)
    informe = formatear_informe(resultados, resumen(resultados), proyeccion(*(_promedio_y_maximo(resultados))), ahora, settings.asistente_modelo)
    salida = args.salida or (DIR.resolve().parents[3] / "docs" / "reportes" / f"mora-real-{ahora.strftime('%Y-%m-%d-%H%M')}.md")
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(informe, encoding="utf-8")
    r = resumen(resultados)
    print(f"Listo: {r['ok']} ok, {r['sin_dato']} rechazadas, {r['errores']} sin respuesta; tokens promedio {r['tokens_promedio']}.")
    print(f"Informe: {salida}")
    return 0 if r["errores"] == 0 else 3


def _promedio_y_maximo(resultados: list[Resultado]) -> tuple[int | None, int | None]:
    r = resumen(resultados)
    return r["tokens_promedio"], r["tokens_maximo"]


if __name__ == "__main__":
    raise SystemExit(main())
