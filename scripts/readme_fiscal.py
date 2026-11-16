#!/usr/bin/env python3
"""Regenera la tabla de documentos del README de fiscal-mexicano desde su metadata.
Uso: python scripts/readme_fiscal.py <ruta a fiscal-mexicano>

Mantiene los enlaces a los PDF oficiales y la fecha de la última reforma
sincronizados con el corpus: se corre en CI tras cada reconstrucción (ver
.github/workflows/vigilar-fiscal.yml). Solo reemplaza el bloque entre los
marcadores DOCUMENTOS:INICIO / DOCUMENTOS:FIN; el resto del README se edita a mano.

Lee metadata/documentos.json (qué documentos, versión) y la URL del PDF oficial
del primer pasaje de cada documento.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Ruta al repo de datos (fiscal-mexicano), primer argumento.
REPO = Path(sys.argv[1]).resolve()
INICIO = "<!-- DOCUMENTOS:INICIO -->"
FIN = "<!-- DOCUMENTOS:FIN -->"

# Orden de presentación (más legible que el alfabético de documentos.json).
ORDEN_TIPO = {"ley": 0, "reglamento": 1, "rmf": 2, "anexo-rmf": 3, "rgce": 4,
              "rfa": 5, "criterios": 6}


def url_pdf(clave: str) -> str | None:
    """URL del PDF oficial = url_fuente del primer pasaje del documento."""
    f = REPO / "metadata" / clave / "pasajes.jsonl"
    if not f.exists():
        return None
    with f.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                return json.loads(line).get("url_fuente")
    return None


def tabla() -> str:
    docs = json.loads((REPO / "metadata" / "documentos.json").read_text("utf-8"))["documentos"]
    docs.sort(key=lambda d: (ORDEN_TIPO.get(d.get("tipo"), 9), d["etiqueta"]))
    filas = [
        "| Documento | Última reforma incorporada | PDF oficial |",
        "|---|---|---|",
    ]
    for d in docs:
        url = url_pdf(d["clave"])
        link = f"[Descargar PDF]({url})" if url else "—"
        filas.append(f"| {d['etiqueta']} | {d.get('version') or '—'} | {link} |")
    return "\n".join(filas)


def main() -> int:
    readme = REPO / "README.md"
    txt = readme.read_text("utf-8")
    if INICIO not in txt or FIN not in txt:
        print(f"✗ No encontré los marcadores {INICIO} / {FIN} en README.md")
        return 1
    a = txt.index(INICIO) + len(INICIO)
    b = txt.index(FIN)
    nuevo = txt[:a] + "\n\n" + tabla() + "\n\n" + txt[b:]
    if nuevo != txt:
        readme.write_text(nuevo, "utf-8")
        print("✓ README.md: tabla de documentos actualizada.")
    else:
        print("· README.md: la tabla ya estaba al día.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
