"""Descarga y resolución de la URL vigente de cada fuente del registro.

Las fuentes de la Cámara de Diputados son estables (CFF.pdf se actualiza
in-place), pero el SAT publica cada versión con la fecha en el nombre del
archivo (Anexo_7_RMF2026-09012026.pdf). Para esos documentos el registro
declara `indice` + `patron`: aquí se lee la página índice, se juntan los href
que coinciden con el patrón y gana el de fecha DDMMYYYY más reciente. Si la
resolución falla (página caída, patrón sin coincidencias) se levanta excepción:
mejor un job rojo que vigilar un PDF muerto durante meses.
"""
from __future__ import annotations

import re
import shutil
import urllib.request
from urllib.parse import urljoin

UA = "Mozilla/5.0 (fiscal-extractor; vigilancia de reformas)"

_HREF_PDF = re.compile(r'href="([^"]+\.pdf)"', re.IGNORECASE)
_FECHA_NOMBRE = re.compile(r"(\d{2})(\d{2})(\d{4})\.pdf$", re.IGNORECASE)


def descargar(url: str, dest: str) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def _fecha_nombre(href: str) -> tuple[int, int, int]:
    """Fecha DDMMYYYY del nombre del archivo como (año, mes, día) ordenable."""
    m = _FECHA_NOMBRE.search(href)
    if not m:
        return (0, 0, 0)
    dd, mm, yyyy = m.groups()
    return (int(yyyy), int(mm), int(dd))


def _leer_indice(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", errors="replace")


def url_vigente(doc, leer=_leer_indice) -> str:
    """URL del PDF vigente del documento.

    Con `indice` + `patron` se resuelve contra la página índice; si no, es
    `doc.url` tal cual. `leer` es inyectable para tests.
    """
    if not (doc.indice and doc.patron):
        if not doc.url:
            raise LookupError(f"{doc.clave}: sin URL ni página índice en el registro")
        return doc.url
    html = leer(doc.indice)
    patron = re.compile(doc.patron, re.IGNORECASE)
    candidatos = [h for h in _HREF_PDF.findall(html) if patron.search(h)]
    if not candidatos:
        raise LookupError(
            f"{doc.clave}: ningún PDF coincide con {doc.patron!r} en {doc.indice} "
            "(¿cambió la estructura de la página del SAT?)"
        )
    return urljoin(doc.indice, max(candidatos, key=_fecha_nombre))
