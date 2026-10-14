"""SkyPulse: vacía las suscripciones de alertas push en Upstash (herramienta LOCAL del dueño).

Hay que correrlo ANTES de encender el envío automático: los registros anteriores consintieron solo un aviso
de prueba, así que se dan de baja todos y cada persona se registra de nuevo con el texto nuevo.

Por defecto es un SIMULACRO: cuenta cuántas claves de cada tipo borraría y no toca nada. Para borrar de verdad
hay que pasar --confirmar. Después de borrar vuelve a contar; si quedó algo borrable sale con código 1.
Se puede volver a correr (es idempotente), también después de un fallo a mitad.

Nunca borra la clave de apagado `alertas:apagado` ni nada fuera del prefijo `alertas:`. Solo imprime
cantidades por tipo de clave (nunca ids, endpoints, nombres de clave con ids ni valores). Lee
UPSTASH_REDIS_REST_URL y UPSTASH_REDIS_REST_TOKEN del ENTORNO del proceso; no abre ningún .env.

Códigos de salida: 0 todo bien, 1 quedó algo borrable, 2 Upstash falló, 3 error de uso o de configuración.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from typing import TextIO

from alertas_vaciar_core.cliente import (
    CredentialsError,
    UrllibCommander,
    credentials_from_env,
)
from alertas_vaciar_core.limpieza import (
    KINDS,
    Commander,
    DeletionInterrupted,
    Inventory,
    UpstashError,
    delete_inventory,
    scan_inventory,
)

EXIT_OK = 0
EXIT_LEFTOVERS = 1
EXIT_UPSTASH = 2
EXIT_USAGE = 3


class _Exit(Exception):
    """argparse wanted to exit (help, or a usage error): carry the code instead."""

    def __init__(self, status: int, message: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        raise _Exit(EXIT_USAGE, f"{self.format_usage()}error: {message}\n")

    def exit(self, status: int = 0, message: str | None = None) -> None:  # type: ignore[override]
        raise _Exit(status if status == 0 else EXIT_USAGE, message or "")


def build_parser() -> argparse.ArgumentParser:
    # allow_abbrev=False: `--conf` must never be read as `--confirmar` and delete by accident.
    parser = _Parser(
        prog="alertas_vaciar.py",
        allow_abbrev=False,
        description="Vacía las suscripciones de alertas push en Upstash. Sin --confirmar es un simulacro "
        "(no borra nada). Credenciales: variables de entorno UPSTASH_REDIS_REST_URL y "
        "UPSTASH_REDIS_REST_TOKEN. Códigos de salida: 0 bien, 1 quedó algo borrable, 2 Upstash falló, "
        "3 error de uso o de configuración.",
    )
    parser.add_argument(
        "--confirmar",
        action="store_true",
        help="borra de verdad (sin esto solo cuenta lo que borraría)",
    )
    return parser


def _write_counts(out: TextIO, counts: Mapping[str, int]) -> None:
    out.writelines(f"  {kind.label}: {counts.get(kind.id, 0)}\n" for kind in KINDS)
    out.write(f"  total a borrar: {sum(counts.values())}\n")


def _write_kept(out: TextIO, inventory: Inventory) -> None:
    out.write(
        "Se conservan (no se tocan): "
        f"interruptor de apagado {inventory.protected}, "
        f"otras claves alertas:* no reconocidas {inventory.unknown}\n"
    )


def _progress_text(deleted: Mapping[str, int]) -> str:
    return ", ".join(f"{kind.id} {deleted.get(kind.id, 0)}" for kind in KINDS) + (
        f" (total {sum(deleted.values())})"
    )


def _run(
    args: argparse.Namespace, commander: Commander, out: TextIO, err: TextIO
) -> int:
    mode = "BORRADO (--confirmar)" if args.confirmar else "SIMULACRO (no se borra nada)"
    out.write(f"Vaciado de suscripciones de alertas: {mode}\n")
    try:
        inventory = scan_inventory(commander)
    except UpstashError as problem:
        err.write(f"error: no se pudo leer Upstash ({problem}). No se borró nada.\n")
        return EXIT_UPSTASH

    out.write("Claves a borrar, por tipo:\n")
    _write_counts(out, inventory.counts())
    _write_kept(out, inventory)

    if not args.confirmar:
        out.write(
            "No se borró nada. Para borrar de verdad volvé a correr con --confirmar.\n"
        )
        return EXIT_OK
    if inventory.total == 0:
        out.write("No hay nada para borrar.\n")
        return EXIT_OK

    try:
        deleted = delete_inventory(commander, inventory)
    except DeletionInterrupted as stop:
        err.write(
            f"error: Upstash falló al borrar ({stop.reason}). Se alcanzaron a borrar: "
            f"{_progress_text(stop.deleted)}. Es seguro volver a correr el mismo comando.\n"
        )
        return EXIT_UPSTASH
    out.write(f"Borradas: {_progress_text(deleted)}\n")

    try:
        left = scan_inventory(commander)
    except UpstashError as problem:
        err.write(
            f"error: se borró, pero no se pudo hacer el recuento final ({problem}). "
            "Volvé a correr en simulacro para verificar.\n"
        )
        return EXIT_UPSTASH
    out.write(f"Recuento final: quedan por borrar: {left.total}\n")
    if left.total:
        out.write("ATENCIÓN: quedó algo borrable. Volvé a correr con --confirmar.\n")
        return EXIT_LEFTOVERS
    return EXIT_OK


def _prepare_console(stream: TextIO) -> None:
    """Windows consoles default to cp1252: accents need UTF-8."""
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="replace")


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    commander: Commander | None = None,
) -> int:
    """Run the tool. Streams, environment and the Upstash client can be injected (tests do)."""
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    env = os.environ if environ is None else environ
    if stdout is None:
        _prepare_console(out)
        _prepare_console(err)
    try:
        args = build_parser().parse_args(argv)
    except _Exit as stop:
        (out if stop.status == 0 else err).write(stop.message)
        return stop.status
    try:
        credentials = credentials_from_env(env)
    except CredentialsError as problem:
        err.write(f"error: {problem}\n")
        return EXIT_USAGE
    return _run(args, commander or UrllibCommander(credentials), out, err)


if __name__ == "__main__":
    sys.exit(main())
