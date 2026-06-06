"""Parser de criterios del SAT — normativos (Anexo 7) y no vinculativos (Anexo 3).

Cada criterio se identifica por 'N/LEY/TIPO' (`10/IVA/N`, `25/ISR/NV`, `1/CFF/PI`),
trae un rubro y un cuerpo, y se agrupa por ley (`I. Criterios del CFF`) y por
estado (`A. Vigentes` / `B. Derogados`).

El documento abre con un índice ('Contenido') que repite cada identificador (solo
el rubro, sin cuerpo). Como cada criterio aparece dos veces —en el índice y en el
contenido real—, se deduplica quedándose con la aparición de **cuerpo más largo**
(la real); así se descarta el índice sin depender de su formato exacto.

Fuente: PDF del SAT (anexos de la RMF, publicados en el DOF). Vigencia anual.
"""
from __future__ import annotations

import re
from datetime import date

import pdfplumber

from ..modelo import Criterio
from ..registro import Documento
from .reglas import DOF_HEADER_RE, PAGE_NUM_RE, MESES, PUB_RE

# Identificador de criterio al inicio de línea: "10/IVA/N <rubro>".
CRITERIO_RE = re.compile(r"^(\d+)/([A-ZÁÉÍÓÚ]+)/([A-Z]+)\s+(.*)$")
# Sección por ley: "I. Criterios del CFF", "II. Criterios de la Ley del ISR".
SECCION_RE = re.compile(r"^([IVXLC]+)\.\s+Criterios\b.*$")
# Estado: "A. Vigentes" / "B. Derogados" (con o sin dos puntos del índice).
ESTADO_RE = re.compile(r"^[AB]\.\s+(Vigentes|Derogados):?\s*$")


def fecha_publicacion(pdf_path: str) -> date | None:
    with pdfplumber.open(pdf_path) as pdf:
        head = pdf.pages[0].extract_text() or ""
    m = PUB_RE.search(head)
    if not m:
        return None
    mes = MESES.get(m.group(2).lower())
    return date(int(m.group(3)), mes, int(m.group(1))) if mes else None


def texto_limpio(pdf_path: str) -> str:
    partes = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            lineas = [ln for ln in (page.extract_text() or "").splitlines()
                      if not (DOF_HEADER_RE.match(ln.strip()) or PAGE_NUM_RE.match(ln.strip()))]
            partes.append("\n".join(lineas))
    return "\n".join(partes)


def parse(pdf_path: str, doc: Documento) -> list[Criterio]:
    return parse_texto(texto_limpio(pdf_path))


def parse_texto(clean_text: str) -> list[Criterio]:
    """Segmenta en criterios y deduplica índice vs contenido (cuerpo más largo)."""
    lineas = clean_text.splitlines()
    bloques: list[tuple[Criterio, list[str]]] = []
    actual: Criterio | None = None
    buf: list[str] = []
    cur_seccion = ""
    cur_estado = "vigente"

    def cerrar() -> None:
        if actual is not None:
            actual.cuerpo = "\n".join(buf).strip()
            bloques.append((actual, buf.copy()))

    for raw in lineas:
        s = raw.strip()
        if not s:
            buf.append("")
            continue

        me = ESTADO_RE.match(s)
        if me:
            cerrar(); actual = None; buf = []
            cur_estado = "derogado" if me.group(1).lower().startswith("derog") else "vigente"
            continue
        msec = SECCION_RE.match(s)
        if msec:
            cerrar(); actual = None; buf = []
            cur_seccion = s
            continue

        mc = CRITERIO_RE.match(s)
        if mc:
            cerrar()
            numero = f"{mc.group(1)}/{mc.group(2)}/{mc.group(3)}"
            actual = Criterio(
                numero=numero, ley=mc.group(2), tipo=mc.group(3),
                rubro=mc.group(4).strip(), seccion=cur_seccion, estado=cur_estado,
            )
            buf = []
            continue

        if actual is not None:
            buf.append(raw)

    cerrar()

    # Dedup: por identificador, conservar la aparición con el cuerpo más largo
    # (la real; la del índice 'Contenido' casi no tiene cuerpo).
    mejor: dict[str, Criterio] = {}
    for crit, cuerpo_lines in bloques:
        largo = len("\n".join(cuerpo_lines).strip())
        if crit.numero not in mejor or largo > len(mejor[crit.numero].cuerpo):
            mejor[crit.numero] = crit
    return list(mejor.values())
