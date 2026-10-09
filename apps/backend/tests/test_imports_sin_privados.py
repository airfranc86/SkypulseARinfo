"""Structural test: no module of `app/` imports a `_private` name from ANOTHER module of `app/`.

A leading underscore means "internal to this module". Reaching into it from outside couples two
modules through a name nobody promised to keep. The rule is checked on the syntax tree, so it also
catches imports nobody executes in a test.

Not counted: standard-library and third-party imports (`from os import _exit`), and a module
importing from itself.

Known limit: only `from x import _name` statements are detected. Reaching a private name through a
module attribute (`import app.services.metar as m; m._x`, `from app.services import metar; metar._x`)
or through `importlib` is NOT detected; today a search of `app/` finds none.
"""
from __future__ import annotations

import ast
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"

# (file relative to `app/`, imported-from module, imported name) allowed to stay for now.
# Each entry needs a comment saying who owns the cleanup. The cases of Phase 1b-1
# (services.metar -> taf_decoded, routers.metar -> routers.taf, openmeteo -> routers.niebla)
# are fixed and must not come back here.
KNOWN_EXCEPTIONS: frozenset[tuple[str, str, str]] = frozenset(
    {
        # Outside the aeronautical reports scope (found while adding this test). The day labels
        # belong to the dashboard builder / Open-Meteo split, not to Phase 1b.
        ("services/dashboard_builder.py", "app.services.openmeteo", "_DAY_LABELS_ES"),
    }
)


def _module_of(path: Path, app_dir: Path) -> str:
    parts = path.relative_to(app_dir.parent).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _package_of(path: Path, app_dir: Path) -> str:
    module = _module_of(path, app_dir)
    return module if path.name == "__init__.py" else module.rpartition(".")[0]


def _target_module(node: ast.ImportFrom, path: Path, app_dir: Path) -> str | None:
    """Dotted module an `ImportFrom` reads from, when it belongs to `app`; None otherwise."""
    if node.level:
        base = _package_of(path, app_dir).split(".")
        base = base[: len(base) - (node.level - 1)]
        target = ".".join([*base, *([node.module] if node.module else [])])
    else:
        target = node.module or ""
    return target if target == "app" or target.startswith("app.") else None


def _is_private(name: str) -> bool:
    return name.startswith("_") and not (name.startswith("__") and name.endswith("__"))


def private_cross_imports(app_dir: Path = APP_DIR) -> list[tuple[str, str, str, int]]:
    """(file relative to `app_dir`, module read from, private name, line) for every offender."""
    found: list[tuple[str, str, str, int]] = []
    for path in sorted(app_dir.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        own_module = _module_of(path, app_dir)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            target = _target_module(node, path, app_dir)
            if target is None or target == own_module:
                continue
            for alias in node.names:
                if _is_private(alias.name):
                    found.append((path.relative_to(app_dir).as_posix(), target, alias.name, node.lineno))
    return found


def test_no_private_names_are_imported_across_modules() -> None:
    offenders = [
        f"{file}:{line} imports {name} from {target}"
        for file, target, name, line in private_cross_imports()
        if (file, target, name) not in KNOWN_EXCEPTIONS
    ]
    assert offenders == [], "private cross-module imports:\n" + "\n".join(offenders)


def test_known_exceptions_are_still_needed() -> None:
    present = {(file, target, name) for file, target, name, _ in private_cross_imports()}
    stale = sorted(KNOWN_EXCEPTIONS - present)
    assert stale == [], f"remove from KNOWN_EXCEPTIONS (already fixed): {stale}"


def test_the_detector_finds_private_imports_and_ignores_the_rest(tmp_path: Path) -> None:
    """Guard against a detector that silently finds nothing."""
    app = tmp_path / "app"
    (app / "services").mkdir(parents=True)
    (app / "routers").mkdir()
    for package in (app, app / "services", app / "routers"):
        (package / "__init__.py").write_text("", encoding="utf-8")
    # A module importing its own private name is not a cross-module import.
    (app / "services" / "b.py").write_text("_own = 1\nfrom app.services.b import _own\n", encoding="utf-8")
    (app / "services" / "a.py").write_text(
        "from app.services.b import _hidden, shown\n"  # absolute, private -> offender
        "from .b import _also_hidden\n"  # relative, private -> offender
        "from . import _module\n"  # private submodule of the package -> offender
        "from ..routers.x import _up\n"  # relative, one level up -> offender
        "from app.services.b import __version__\n"  # dunder is not private
        "from os import _exit\n"  # standard library is not counted
        "from third_party import _thing\n",  # neither is a third party
        encoding="utf-8",
    )
    seen = {(file, target, name) for file, target, name, _ in private_cross_imports(app)}
    assert seen == {
        ("services/a.py", "app.services.b", "_hidden"),
        ("services/a.py", "app.services.b", "_also_hidden"),
        ("services/a.py", "app.services", "_module"),
        ("services/a.py", "app.routers.x", "_up"),
    }
