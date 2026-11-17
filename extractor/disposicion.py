"""Dónde vive cada documento dentro de su repo de datos.

Dos disposiciones, según la clave:

  - Corpus (fiscal-mexicano, leyes-federales): clave plana ('lgs'). Las
    unidades en `lgs/NNN.md` y la metadata en `metadata/lgs/`.
  - Estatal (leyes-estatales): clave '<estado>/<ley>' ('jalisco/codigo-civil'),
    como la constitución de cada estado que produce constitucion-extractor:
    `jalisco/codigo-civil/articulos/NNN.md` y `jalisco/codigo-civil/metadata/`.
    Así cada ley de un estado queda en una sola carpeta junto a su constitución
    y `git log -- jalisco/codigo-civil/` es toda su historia.

`scripts/trailers.py` (`_dir_articulos`, `_dir_metadata`) aplica la misma
regla al leer los commits; una prueba exige que coincidan.
"""
from __future__ import annotations

from pathlib import Path


def es_estatal(clave: str) -> bool:
    return "/" in clave


def rel_unidades(clave: str) -> str:
    return f"{clave}/articulos" if es_estatal(clave) else clave


def rel_metadata(clave: str) -> str:
    return f"{clave}/metadata" if es_estatal(clave) else f"metadata/{clave}"


def rutas(clave: str) -> tuple[str, str]:
    """Las carpetas del documento, relativas al repo (unidades, metadata)."""
    return rel_unidades(clave), rel_metadata(clave)


def dir_unidades(repo: str | Path, clave: str) -> Path:
    return Path(repo) / rel_unidades(clave)


def dir_metadata(repo: str | Path, clave: str) -> Path:
    return Path(repo) / rel_metadata(clave)


def indices(repo: str | Path) -> list[Path]:
    """`articulos.json` de cada documento del repo que produce este extractor.
    En un repo estatal solo cuentan las leyes del registro activo: las
    constituciones (`<estado>/constitucion/`) son de constitucion-extractor."""
    from .registro import DOCUMENTOS
    repo = Path(repo)
    planos = sorted(repo.glob("metadata/*/articulos.json"))
    estatales = sorted(p for p in (dir_metadata(repo, d.clave) / "articulos.json"
                                   for d in DOCUMENTOS if es_estatal(d.clave)) if p.exists())
    return planos + estatales


def unidad_de_ruta(ruta: str | Path) -> tuple[str, str] | None:
    """(clave, unidad) de la ruta de un .md de unidad de algún documento del
    registro activo ('lgs/004.md', 'jalisco/codigo-civil/articulos/004.md')."""
    from .registro import POR_CLAVE
    p = Path(ruta)
    if p.suffix != ".md":
        return None
    padre = p.parent.as_posix()
    if padre in POR_CLAVE and not es_estatal(padre):
        return padre, p.stem
    if p.parent.name == "articulos" and p.parent.parent.as_posix() in POR_CLAVE:
        return p.parent.parent.as_posix(), p.stem
    return None
