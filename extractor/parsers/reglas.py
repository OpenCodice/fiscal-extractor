"""Parser de la Resolución Miscelánea Fiscal (RMF) — reglas numeradas.

La RMF no es articulado: sus unidades son 'reglas' con numeración jerárquica
(`2.7.1.21.`), agrupadas en Título → Capítulo → Sección. Cada regla viene
precedida por un título descriptivo y suele cerrar con sus fundamentos legales
("CFF 69").

Discriminador real-vs-cita: una regla real arranca con MAYÚSCULA tras el número
("2.3.4. Para los efectos…"); una cita a media oración arranca con minúscula
("2.3.4. y la ficha…") y se descarta.

Fuente: PDF del SAT (publicado en el DOF). Es anual: el documento completo se
sustituye cada ejercicio.
"""
from __future__ import annotations

import re
from datetime import date

import pdfplumber

from ..modelo import Regla
from ..registro import Documento

# Encabezado corrido del DOF, que alterna izquierda/derecha por paridad de página:
#   "DIARIO OFICIAL Lunes 28 de diciembre de 2025" / "<fecha> DIARIO OFICIAL".
DOF_HEADER_RE = re.compile(
    r"^(?:DIARIO OFICIAL\b.*|(?:Lunes|Martes|Miércoles|Jueves|Viernes|Sábado|Domingo)\b.*DIARIO OFICIAL)\s*$"
)
# Pie con número de página: "123" sola, o "(Primera Sección)" etc. (best-effort).
PAGE_NUM_RE = re.compile(r"^\d{1,4}$")

# Una regla: número jerárquico (≥2 niveles) + cuerpo que EMPIEZA con mayúscula.
# La mayúscula descarta las citas a media oración ("2.3.4. y la ficha…").
REGLA_RE = re.compile(r"^(\d+(?:\.\d+)+)\.\s+([A-ZÁÉÍÓÚÑ¿«“].*)$")

# Encabezados estructurales.
TITULO_RE = re.compile(r"^Título\s+(\d+)\.\s*(.*)$")
CAPITULO_RE = re.compile(r"^Capítulo\s+(\d+(?:\.\d+)*)\.\s*(.*)$")
SECCION_RE = re.compile(r"^Sección\s+(\d+(?:\.\d+)*)\.\s*(.*)$")

# Fecha de publicación en el nombre/portada: "Domingo 28 de diciembre de 2025".
MESES = {m: i for i, m in enumerate(
    ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
     "septiembre", "octubre", "noviembre", "diciembre"], start=1)}
PUB_RE = re.compile(r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})")


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
            lineas = []
            for ln in (page.extract_text() or "").splitlines():
                s = ln.strip()
                if DOF_HEADER_RE.match(s) or PAGE_NUM_RE.match(s):
                    continue
                lineas.append(ln)
            partes.append("\n".join(lineas))
    return "\n".join(partes)


def parse(pdf_path: str, doc: Documento) -> list[Regla]:
    return parse_texto(texto_limpio(pdf_path))


def parse_texto(clean_text: str) -> list[Regla]:
    lineas = clean_text.splitlines()
    reglas: list[Regla] = []
    actual: Regla | None = None
    buf: list[str] = []
    cur_titulo = cur_capitulo = cur_seccion = ""

    def flush() -> None:
        if actual is not None:
            # La última línea del buffer es el título de la SIGUIENTE regla; se
            # extrae fuera. Aquí el buffer ya viene sin ella.
            actual.cuerpo = "\n".join(buf).strip()
            reglas.append(actual)

    for raw in lineas:
        line = raw.rstrip()
        s = line.strip()
        if not s:
            buf.append("")
            continue

        mt = TITULO_RE.match(s)
        if mt:
            flush(); actual = None; buf = []
            cur_titulo = f"Título {mt.group(1)}. {mt.group(2)}".strip()
            cur_capitulo = cur_seccion = ""
            continue
        mc = CAPITULO_RE.match(s)
        if mc:
            flush(); actual = None; buf = []
            cur_capitulo = f"Capítulo {mc.group(1)}. {mc.group(2)}".strip()
            cur_seccion = ""
            continue
        ms = SECCION_RE.match(s)
        if ms:
            flush(); actual = None; buf = []
            cur_seccion = f"Sección {ms.group(1)}. {ms.group(2)}".strip()
            continue

        mr = REGLA_RE.match(s)
        if mr:
            # El título descriptivo es la última línea no vacía del buffer actual.
            titulo_regla = ""
            while buf and not buf[-1].strip():
                buf.pop()
            if buf:
                titulo_regla = buf.pop().strip()
            flush()
            actual = Regla(
                numero=mr.group(1), titulo_regla=titulo_regla,
                titulo=cur_titulo, capitulo=cur_capitulo, seccion=cur_seccion,
            )
            buf = [mr.group(2)]                 # cuerpo sin el número (ya retirado)
            continue

        # Se bufferea siempre (aun sin regla activa): así la línea-título que
        # sigue a un encabezado estructural no se pierde antes de la 1ª regla.
        buf.append(line)

    flush()
    return reglas
