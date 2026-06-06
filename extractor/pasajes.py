"""Pasajes citables a nivel PÁRRAFO, con su ubicación en el PDF.

Un pasaje = un párrafo (o fracción/inciso) del cuerpo de una unidad, con todo lo
necesario para citarlo y resaltarlo: id, cita legal, texto, y —vía locate.py—
la página del PDF y los rectángulos. Es capa derivada (se regenera); la fuente
de verdad sigue siendo el `.md`.

Funciona para los tres tipos de unidad (artículo, regla, criterio): solo necesita
`.clave`, `.etiqueta`/`.numero` y `.cuerpo`.
"""
from __future__ import annotations

from .normalize import normalize_body
from .registro import Documento


def _bloques(cuerpo: str, etiqueta: str) -> list[str]:
    """Párrafos del cuerpo normalizado, sin las notas de reforma (en cursiva)."""
    out = []
    for b in normalize_body(cuerpo, etiqueta).split("\n\n"):
        b = b.strip()
        if not b or (b.startswith("_") and b.endswith("_")):
            continue
        out.append(b)
    return out


def _cita_base(unidad, doc: Documento) -> str:
    if doc.parser == "reglas":
        return f"Regla {unidad.numero} {doc.sigla}"
    if doc.parser == "criterios":
        return f"Criterio {unidad.numero}"
    return f"{unidad.etiqueta.rstrip('.')} {doc.sigla}"          # "Artículo 27 CFF"


def pasajes_de(unidad, doc: Documento) -> list[dict]:
    base = _cita_base(unidad, doc)
    out = []
    for n, texto in enumerate(_bloques(unidad.cuerpo, unidad.etiqueta), start=1):
        out.append({
            "id": f"{doc.clave}/{unidad.clave}.p{n}",
            "documento": doc.clave,
            "clave_unidad": unidad.clave,
            "parrafo": n,
            "cita": f"{base}, párrafo {n}",
            "texto": texto,
            "fuente": doc.etiqueta,
            "url_fuente": doc.url,
            "archivo_texto": f"{doc.clave}/{unidad.clave}.md",
            # `coordenadas` (pagina + rects) lo agrega locate.annotate().
        })
    return out


def todos_los_pasajes(unidades: list, doc: Documento) -> list[dict]:
    return [p for u in unidades for p in pasajes_de(u, doc)]
