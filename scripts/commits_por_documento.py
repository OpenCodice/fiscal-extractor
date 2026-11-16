#!/usr/bin/env python3
"""Convierte los cambios sin commit de un repo de datos en un commit por documento.

El historial de cada documento debe contar solo su propia historia: `git log --
lgs/` no puede mostrar la reforma de otra ley. Un documento es una carpeta de
primer nivel (`lgs/`) más su `metadata/lgs/`. Lo que no pertenece a ningún
documento (índices compartidos, README) va en un último commit aparte.

Uso: commits_por_documento.py <repo> <asuntos.json> "<asunto del resto>"
`asuntos.json` es {clave: título del commit}. Un documento con cambios y sin
título usa "Actualización de <clave>".
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _git(repo: str, *args: str) -> str:
    return subprocess.run(["git", "-C", repo, *args], check=True,
                          capture_output=True, text=True).stdout


def cambios(repo: str) -> list[str]:
    """Rutas cambiadas (incluidas nuevas y borradas), relativas al repo."""
    salida = _git(repo, "status", "--porcelain", "-z", "--no-renames", "-uall")
    return [e[3:] for e in salida.split("\0") if e]


def agrupar(rutas: list[str], documentos: set[str]) -> tuple[dict[str, list[str]], list[str]]:
    por_doc: dict[str, list[str]] = {}
    resto: list[str] = []
    for r in rutas:
        partes = r.split("/")
        doc = partes[1] if partes[0] == "metadata" and len(partes) > 2 else partes[0]
        if len(partes) > 1 and doc in documentos:
            por_doc.setdefault(doc, []).append(r)
        else:
            resto.append(r)
    return por_doc, resto


def main(repo: str, asuntos_json: str, asunto_resto: str) -> int:
    a = Path(asuntos_json)
    asuntos = json.loads(a.read_text(encoding="utf-8")) if a.exists() else {}
    rutas = cambios(repo)
    # Un documento es cualquier carpeta de primer nivel con artículos (.md); así
    # también se separan los que cambiaron sin título declarado.
    documentos = {r.split("/")[0] for r in rutas if r.endswith(".md") and r.count("/") == 1}
    documentos |= set(asuntos)
    por_doc, resto = agrupar(rutas, documentos)
    for doc in sorted(por_doc):
        _git(repo, "add", "-A", "--", *por_doc[doc])
        _git(repo, "commit", "-q", "-m", asuntos.get(doc) or f"Actualización de {doc}")
        print(f"{doc}: {asuntos.get(doc) or 'Actualización de ' + doc}")
    if resto:
        _git(repo, "add", "-A", "--", *resto)
        _git(repo, "commit", "-q", "-m", asunto_resto)
        print(f"resto ({len(resto)} archivos): {asunto_resto}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
