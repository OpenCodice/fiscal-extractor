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
# Las ediciones vespertinas anteponen o posponen "(Edición Vespertina)".
DOF_HEADER_RE = re.compile(
    r"^(?:\(Edición \w+\)\s+)?"
    r"(?:DIARIO OFICIAL\b.*|(?:Lunes|Martes|Miércoles|Jueves|Viernes|Sábado|Domingo)\b.*DIARIO OFICIAL\b.*)\s*$"
)
# Pie con número de página: "123" sola, o "(Primera Sección)" etc. (best-effort).
PAGE_NUM_RE = re.compile(r"^\d{1,4}$")

# Candidata a regla: número jerárquico (≥2 niveles) + lo que siga.
REGLA_NUM_RE = re.compile(r"^(\d+(?:\.\d+)+)\.\s+(.*)$")
# Una regla real empieza el cuerpo con mayúscula (o signo de apertura). La
# minúscula delata una cita a media oración ("2.3.4. y la ficha…").
EMPIEZA_MAYUS_RE = re.compile(r"^[A-ZÁÉÍÓÚÑ¿«“(]")
NUM_CTX_RE = re.compile(r"(\d+(?:\.\d+)*)")

# Encabezados estructurales. El punto tras el número es opcional (la RGCE trae
# "Capítulo 1.12 Agencia Aduanal" sin punto), pero el nombre debe empezar en
# MAYÚSCULA o no existir: así una referencia al pie de regla como
# "Capítulo 3.6., Anexos 7, 8, 9 y 10" no envenena el contexto estructural.
TITULO_RE = re.compile(r"^Título\s+(\d+)\.?\s*((?=[A-ZÁÉÍÓÚÑ]).*)?$")
CAPITULO_RE = re.compile(r"^Capítulo\s+(\d+(?:\.\d+)*)\.?\s*((?=[A-ZÁÉÍÓÚÑ]).*)?$")
SECCION_RE = re.compile(r"^Sección\s+(\d+(?:\.\d+)*)\.?\s*((?=[A-ZÁÉÍÓÚÑ]).*)?$")

# Fecha de publicación en el nombre/portada: "Domingo 28 de diciembre de 2025".
MESES = {m: i for i, m in enumerate(
    ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
     "septiembre", "octubre", "noviembre", "diciembre"], start=1)}
PUB_RE = re.compile(r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})")


def es_ruido(texto: str) -> bool:
    """Línea de encabezado/pie del DOF (para alinear pasajes en locate.py)."""
    return bool(DOF_HEADER_RE.match(texto) or PAGE_NUM_RE.match(texto))


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


def _ctx_prefijo(*campos: str) -> str:
    """Número del contexto estructural más específico disponible (sección>cap>tít)."""
    for campo in campos:
        if campo:
            m = NUM_CTX_RE.search(campo)
            if m:
                return m.group(1)
    return ""


def _consistente(numero: str, prefijo: str) -> bool:
    """¿El número de la regla cae bajo el contexto estructural actual?"""
    return not prefijo or numero == prefijo or numero.startswith(prefijo + ".")


def parse_texto(clean_text: str) -> list[Regla]:
    """Reglas de la RMF. Atajo de `reglas_y_anomalias` que descarta el reporte."""
    return reglas_y_anomalias(clean_text)[0]


def reglas_y_anomalias(clean_text: str) -> tuple[list[Regla], list[dict]]:
    """Segmenta en reglas y devuelve también las líneas ambiguas (para auditar).

    Una línea `N.N.N. …` se acepta como regla SOLO si (a) su número concuerda
    con el contexto estructural vigente y (b) el cuerpo empieza en mayúscula. Las
    dos señales juntas son mucho más robustas que la mayúscula sola: el contexto
    descarta citas de otra rama aunque vengan capitalizadas, y la mayúscula
    descarta citas de la misma rama. Lo que no entra se registra como anomalía,
    para no descartar nada en silencio (lo revisa el validador / CI).
    """
    lineas = clean_text.splitlines()
    reglas: list[Regla] = []
    anomalias: list[dict] = []
    actual: Regla | None = None
    buf: list[str] = []
    cur_titulo = cur_capitulo = cur_seccion = ""

    def flush() -> None:
        if actual is not None:
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
            cur_titulo = f"Título {mt.group(1)}. {mt.group(2) or ''}".strip()
            cur_capitulo = cur_seccion = ""
            continue
        mc = CAPITULO_RE.match(s)
        if mc:
            flush(); actual = None; buf = []
            cur_capitulo = f"Capítulo {mc.group(1)}. {mc.group(2) or ''}".strip()
            cur_seccion = ""
            continue
        ms = SECCION_RE.match(s)
        if ms:
            flush(); actual = None; buf = []
            cur_seccion = f"Sección {ms.group(1)}. {ms.group(2) or ''}".strip()
            continue

        mr = REGLA_NUM_RE.match(s)
        if mr:
            numero, resto = mr.group(1), mr.group(2)
            prefijo = _ctx_prefijo(cur_seccion, cur_capitulo, cur_titulo)
            consistente = _consistente(numero, prefijo)
            mayus = bool(EMPIEZA_MAYUS_RE.match(resto))
            if consistente and mayus:
                titulo_regla = ""
                while buf and not buf[-1].strip():
                    buf.pop()
                if buf:
                    titulo_regla = buf.pop().strip()
                flush()
                actual = Regla(
                    numero=numero, titulo_regla=titulo_regla,
                    titulo=cur_titulo, capitulo=cur_capitulo, seccion=cur_seccion,
                )
                buf = [resto]
                continue
            # No es encabezado de regla: es cita (lo común) o un caso ambiguo.
            # Se registra y la línea sigue como cuerpo de la regla en curso.
            if mayus and not consistente:
                # Cita de OTRA rama capitalizada: la mayúscula sola la habría
                # aceptado por error. El contexto la atrapa.
                motivo = "cita_otra_rama_capitalizada"
            elif consistente and not mayus:
                # Concuerda con el contexto pero empieza en minúscula: casi
                # siempre cita de la misma rama; vigilar por si fuera regla real.
                motivo = "consistente_minuscula"
            else:
                motivo = "cita"
            anomalias.append({
                "numero": numero, "motivo": motivo, "contexto": prefijo,
                "texto": resto[:60],
            })

        # Se bufferea siempre (aun sin regla activa): así la línea-título que
        # sigue a un encabezado estructural no se pierde antes de la 1ª regla.
        buf.append(line)

    flush()
    return reglas, anomalias
