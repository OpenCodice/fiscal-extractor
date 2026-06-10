"""Descarga y resolución de la URL vigente de cada fuente del registro.

Las fuentes de la Cámara de Diputados son estables (CFF.pdf se actualiza
in-place), pero el SAT publica cada versión con la fecha en el nombre del
archivo (Anexo_7_RMF2026-09012026.pdf). Para esos documentos el registro
declara `indice` + `patron`: aquí se lee la página índice, se juntan los href
que coinciden con el patrón y gana el de fecha DDMMYYYY más reciente.

La normateca legacy del SAT (wwwmat.sat.gob.mx/normatividad) es distinta: los
href son blobs opacos del CMS (/cs/Satellite?...blobwhere=NNN) cuyo ID cambia
con cada versión, y lo único estable es el TEXTO del ancla ("RISAT"). Para esos
documentos el registro declara `indice` + `texto_enlace` y aquí se resuelve el
href cuyo ancla coincide.

Si la resolución falla (página caída, patrón sin coincidencias) se levanta
excepción: mejor un job rojo que vigilar un PDF muerto durante meses.
"""
from __future__ import annotations

import re
import shutil
import ssl
import urllib.request
from html import unescape
from urllib.parse import urljoin

UA = "Mozilla/5.0 (fiscal-extractor; vigilancia de reformas)"

# La normateca legacy del SAT (wwwmat.sat.gob.mx) negocia una llave DH que
# OpenSSL 3 rechaza por corta (DH_KEY_TOO_SMALL). SECLEVEL=1 la admite SIN
# desactivar la verificación del certificado. Solo se habla con *.gob.mx.
_SSL_GOB = ssl.create_default_context()
_SSL_GOB.set_ciphers("DEFAULT:@SECLEVEL=1")

_HREF_PDF = re.compile(r'href="([^"]+\.pdf)"', re.IGNORECASE)
_FECHA_NOMBRE = re.compile(r"(\d{2})(\d{2})(\d{4})\.pdf$", re.IGNORECASE)
_ANCLA = re.compile(r"""<a\s[^>]*?href=["']([^"']+)["'][^>]*>(.*?)</a>""",
                    re.IGNORECASE | re.DOTALL)


def descargar(url: str, dest: str) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180, context=_SSL_GOB) as r, \
            open(dest, "wb") as f:
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
    with urllib.request.urlopen(req, timeout=60, context=_SSL_GOB) as r:
        return r.read().decode("utf-8", errors="replace")


def url_vigente(doc, leer=_leer_indice) -> str:
    """URL del PDF vigente del documento.

    Con `indice` + `texto_enlace` gana el href cuyo texto de ancla coincide;
    con `indice` + `patron` se resuelve contra los href de la página índice;
    si no, es `doc.url` tal cual. `leer` es inyectable para tests.
    """
    if doc.indice and doc.texto_enlace:
        pagina = leer(doc.indice)
        ancla = re.compile(doc.texto_enlace, re.IGNORECASE)
        candidatos = [unescape(href) for href, texto in _ANCLA.findall(pagina)
                      if ancla.fullmatch(re.sub(r"<[^>]+>", "", texto).strip())]
        if not candidatos:
            raise LookupError(
                f"{doc.clave}: ningún enlace con texto {doc.texto_enlace!r} en "
                f"{doc.indice} (¿cambió la estructura de la página del SAT?)"
            )
        return urljoin(doc.indice, candidatos[0])
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
