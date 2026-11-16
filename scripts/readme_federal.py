#!/usr/bin/env python3
"""Regenera las tablas del README de leyes-federales desde su fuentes.json.

Lo corre la vigilancia tras cada reconstrucción, para que entren en el mismo PR.
Solo reemplaza los bloques entre marcadores; el resto del README se edita a
mano. Uso: python scripts/readme_federal.py <ruta a leyes-federales>.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Ruta al repo de datos (leyes-federales), primer argumento.
REPO = Path(sys.argv[1]).resolve()
BLOQUES = {
    "DOCUMENTOS": "incluida",
    "EXCLUIDAS": "excluida",
}


def tabla(docs: list[dict], estado: str) -> str:
    docs = sorted((d for d in docs if d.get("estado") == estado),
                  key=lambda d: d["etiqueta"])
    if not docs:
        return "_Ninguna._"
    if estado == "incluida":
        filas = ["| Ley | Carpeta | Artículos | Última reforma incorporada | PDF oficial |",
                 "|---|---|---|---|---|"]
        for d in docs:
            nota = " ⚠️" if d.get("revision_pendiente") else ""
            filas.append(f"| {d['etiqueta']}{nota} | [`{d['clave']}/`]({d['clave']}/) | "
                         f"{d.get('unidades') or '—'} | {d.get('version') or '—'} | "
                         f"[PDF]({d['url']}) |")
        return "\n".join(filas)
    filas = ["| Ley | Motivo | PDF oficial |", "|---|---|---|"]
    for d in docs:
        motivo = (d.get("motivo") or "").replace("|", "\\|")
        if len(motivo) > 220:
            motivo = motivo[:217] + "…"
        filas.append(f"| {d['etiqueta']} | {motivo} | [PDF]({d['url']}) |")
    return "\n".join(filas)


def main() -> int:
    fuentes = REPO / "fuentes.json"
    docs = json.loads(fuentes.read_text("utf-8"))["documentos"] if fuentes.exists() else []
    readme = REPO / "README.md"
    txt = readme.read_text("utf-8")
    for nombre, estado in BLOQUES.items():
        ini, fin = f"<!-- {nombre}:INICIO -->", f"<!-- {nombre}:FIN -->"
        if ini not in txt or fin not in txt:
            print(f"✗ No encontré los marcadores {ini} / {fin} en README.md")
            return 1
        a, b = txt.index(ini) + len(ini), txt.index(fin)
        txt = txt[:a] + "\n\n" + tabla(docs, estado) + "\n\n" + txt[b:]
    readme.write_text(txt, encoding="utf-8")
    n = sum(1 for d in docs if d.get("estado") == "incluida")
    print(f"✓ README: {n} leyes publicadas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
