#!/usr/bin/env python3
"""Valida los trailers de cada commit de un PR de un repo de datos.

Lo llama `revisar-pr.yml` de cada repo de datos. El PR se fusiona con rebase,
así que cada commit llega tal cual al historial: todos deben llevar trailers
bien formados, un título coherente con ellos y listas de artículos que
coincidan exactamente con su diff (ver scripts/trailers.py).

Uso: validar_commits.py <repo> <base> [<head>]

Este archivo existe idéntico en constitucion-extractor y en fiscal-extractor
(scripts/validar_commits.py): cualquier cambio se hace en los dos.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trailers as tr  # noqa: E402


def _git(repo: str, *args: str) -> str:
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True,
                          text=True).stdout


def esquema(repo: str, rev: str) -> str:
    raiz = _git(repo, "ls-tree", "--name-only", rev).split()
    if "articulos" in raiz:
        return "cpeum"
    for d in _git(repo, "ls-tree", "-d", "--name-only", rev).split():
        if subprocess.run(["git", "-C", repo, "cat-file", "-e", f"{rev}:{d}/constitucion"],
                          capture_output=True).returncode == 0:
            return "estatal"
    return "corpus"


def rutas_de(documento: str) -> list[str]:
    e = tr.esquema_de(documento)
    if e == "cpeum":
        return ["articulos", "metadata", "fuente"]
    if e == "estatal":
        return [documento]
    return [documento, f"metadata/{documento}"]


def fuente_anterior(repo: str, commit: str, documento: str) -> str | None:
    """Fuente-Sha256 de la publicación anterior del documento, si la declara."""
    revs = _git(repo, "log", "--format=%H", "-n", "50", f"{commit}^", "--",
                *rutas_de(documento)).split()
    for rev in revs:
        _, t = tr.parsear(_git(repo, "log", "-1", "--format=%B", rev))
        if tr.valor(t, "Documento") == documento:
            sha = tr.valor(t, "Fuente-Sha256")
            if sha:
                return sha
    return None


def validar_commit(repo: str, commit: str, esq: str) -> list[str]:
    titulo, t = tr.parsear(_git(repo, "log", "-1", "--format=%B", commit))
    padres = _git(repo, "log", "-1", "--format=%P", commit).split()
    antes = padres[0] if padres else None
    rutas = _git(repo, "diff-tree", "-r", "--no-commit-id", "--name-only", "--no-renames", "-z",
                 *([antes] if antes else ["--root"]), commit).split("\0")
    rutas = [r for r in rutas if r]
    errores = tr.validar(titulo, t, rutas, tr.lector_git(repo, antes),
                         tr.lector_git(repo, commit), esq)
    doc, sha = tr.valor(t, "Documento"), tr.valor(t, "Fuente-Sha256")
    if not errores and tr.valor(t, "Tipo") == "reforma" and doc and sha:
        if fuente_anterior(repo, commit, doc) == sha:
            errores.append("reforma con la misma Fuente-Sha256 que la publicación anterior")
    return errores


def main(repo: str, base: str, head: str = "HEAD") -> int:
    commits = _git(repo, "rev-list", "--no-merges", "--reverse", f"{base}..{head}").split()
    esq = esquema(repo, head)
    fallas = 0
    for c in commits:
        errores = validar_commit(repo, c, esq)
        titulo = _git(repo, "log", "-1", "--format=%s", c).strip()
        if errores:
            fallas += 1
            print(f"✗ {c[:9]} {titulo}")
            for e in errores:
                print(f"    {e}")
        else:
            print(f"✓ {c[:9]} {titulo}")
    print(f"{len(commits)} commits, {fallas} con trailers inválidos")
    return 1 if fallas else 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__.split("\n\n")[2], file=sys.stderr)
        sys.exit(2)
    sys.exit(main(*sys.argv[1:4]))
