"""Intentos de reparación automática del extractor, por ley y PDF.

Cuando la revisión completa de una ley (o su auditoría) encuentra defectos, la
vigilancia le encarga a un agente reparar el extractor
(`scripts/agente/reparar.sh`). Cada intento queda en
`verificaciones/reparaciones/*.jsonl`: una línea por ley y estado del intento
(`iniciado`, y luego `publicado` o `descartado`), con el sha256 del PDF. El
`iniciado` se publica antes de que el agente trabaje, así que un intento que se
cae a medias también cuenta.

Una ley que llega a TOPE intentos con el mismo PDF y sigue con defectos queda
fuera con su motivo y deja de reintentarse cuando cambia el extractor (ver
`federal.planear` y `federal.cerrar`): ni otra revisión ni otro agente hasta
que cambie su PDF.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

TOPE = 3
REGISTRO = Path(__file__).resolve().parent.parent / "verificaciones" / "reparaciones"


def cargar(registro: str | Path | None = None) -> list[dict]:
    d = Path(registro or REGISTRO)
    res = []
    for archivo in sorted(d.glob("*.jsonl")) if d.is_dir() else []:
        for n, linea in enumerate(archivo.read_text(encoding="utf-8").splitlines(), 1):
            if not linea.strip():
                continue
            try:
                e = json.loads(linea)
            except ValueError:
                print(f"· {archivo.name}:{n}: línea ilegible en el registro de reparaciones",
                      file=sys.stderr)
                continue
            if isinstance(e, dict) and e.get("documento") and e.get("intento"):
                res.append(e)
    return res


def intentos(documento: str, pdf_sha: str | None, registros: list[dict]) -> int:
    """Intentos distintos de reparar `documento` con ese PDF."""
    return len({e["intento"] for e in registros
                if e["documento"] == documento and e.get("pdf") == pdf_sha})


def agotada(documento: str, pdf_sha: str | None, registros: list[dict]) -> bool:
    return intentos(documento, pdf_sha, registros) >= TOPE


def nota_agotada(n: int) -> str:
    return (f" Sin arreglo automático tras {n} intentos: se reintenta cuando "
            f"cambie su PDF.")
