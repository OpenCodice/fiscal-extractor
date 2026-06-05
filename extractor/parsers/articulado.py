"""Parser de articulado (leyes, códigos y reglamentos de la Cámara de Diputados).

Port generalizado de `constitucion-extractor/extractor/parse.py`. La estructura
del PDF oficial es la misma (encabezados de página repetidos, articulado seguido
de Transitorios, notas de reforma 'DOF DD-MM-YYYY'); los cambios respecto a la
CPEUM son:

  - Sufijos ricos: letra ('14-A'), ordinal ('111 Bis'), combinados ('17-H Bis').
  - Títulos/Capítulos en MAYÚSCULAS sin acento ('TITULO PRIMERO', 'CAPITULO I').
  - Sin conteo fijo de artículos; los derogados se conservan como encabezados,
    así la secuencia sigue continua y filtra las citas a otros artículos.
  - Pie de página genérico 'N de M' (no el '414' fijo de la CPEUM).
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import date

import pdfplumber

from ..modelo import Unidad
from ..registro import Documento

# Encabezados de la Cámara que se repiten en cada página (comunes a todo el corpus).
HEADER_PREFIXES = (
    "CÁMARA DE DIPUTADOS",
    "Secretaría General",
    "Secretaría de Servicios",
)

# Inicio de un artículo y sus variantes. Los encabezados reales llevan "Artículo"
# en title-case ('Artículo', CFF/LISR) o en MAYÚSCULAS ('ARTICULO' LAdua,
# 'ARTÍCULO' LFPCA); las citas a media oración usan minúscula ('artículo 27 de
# esta Ley') y NO deben casar. Por eso se aceptan las dos primeras formas pero
# nunca la minúscula.
#   "Artículo 1o.-"  "Artículo 4o.-A.-"  "Artículo 14-A.-"  "ARTICULO 1o."
#   "Artículo 111 Bis.-"  "Artículo 156-Bis."  "Artículo 17-H Bis."  "Artículo 12."
# - La letra exige guion previo y NO debe ir seguida de letra: así "-A" es letra
#   pero "-Bis"/"-BIS" no se confunde con la letra "B".
# - El ordinal (Bis/Ter/...) admite separador espacio, punto o guion, en cualquier caja.
ORDINALES = "Bis|Ter|Qu[aá]ter|Quintus|Quinquies|Sexies|Septies|Octies|Nonies|Decies"
ARTICULO_RE = re.compile(
    r"^(?:Art[íi]culo|ART[IÍ]CULO)\s+(\d+)\s*[oº°]?\.?"  # "Artículo"/"ARTÍCULO" + número

    r"(?:-([A-Z])(?![A-Za-z]))?"                     # letra "-A" PEGADA, una sola letra
    rf"(?:[\s.\-]+(?i:({ORDINALES}))(?:\s+(\d+))?)?"  # ordinal + numeral opcional ("Bis 1")
    r"\s*\.?-?(?:\s|$|\()"                           # separador final
)

# Encabezados de Título / Capítulo en MAYÚSCULAS (con o sin acento).
TITULO_RE = re.compile(r"^T[IÍ]TULO\s+[A-ZÁÉÍÓÚÑ]+(?:\s+[A-ZÁÉÍÓÚÑ]+){0,2}\s*$")
CAPITULO_RE = re.compile(r"^CAP[IÍ]TULO\s+([IVXLCDM]+|[ÚU]NICO|PRIMERO|SEGUNDO)\b.*$")

# Frontera del articulado permanente: el primer encabezado de Transitorios.
TRANSITORIOS_RE = re.compile(
    r"^[ \t]*(?:Artículos?\s+Transitorios?|ARTÍCULOS?\s+TRANSITORIOS?|"
    r"TRANSITORIOS?|T\s*R\s*A\s*N\s*S\s*I\s*T\s*O\s*R\s*I\s*O\s*S)[ \t]*$",
    re.MULTILINE,
)

# Pie de página: "1 de 377", "377 de 377" (número / total, total variable por doc).
PAGE_FOOTER_RE = re.compile(r"^\d{1,4}\s+de\s+\d{1,4}$")

# Fechas de reforma (DOF). Una cláusula puede encadenar varias con coma.
DOF_CLAUSE_RE = re.compile(r"DOF\s+(\d{2}-\d{2}-\d{4}(?:\s*,\s*\d{2}-\d{2}-\d{4})*)")
DATE_RE = re.compile(r"(\d{2})-(\d{2})-(\d{4})")

# Versión del texto = fecha del snapshot. La portada trae "Última Reforma DOF
# DD-MM-YYYY" en las leyes ya reformadas; un documento nuevo sin reformas (p. ej.
# un reglamento reciente) trae en su lugar "Nuevo Reglamento/Código DOF DD-MM-YYYY".
VERSION_RE = re.compile(
    r"[ÚU]ltimas?\s+[Rr]eformas?\s+(?:publicadas?\s+)?DOF\s+(\d{2})-(\d{2})-(\d{4})"
)
NUEVO_RE = re.compile(
    r"Nuev[oa]\s+(?:Código|Reglamento|Ley|Decreto|Disposición)\s+DOF\s+(\d{2})-(\d{2})-(\d{4})"
)

# Marca de artículo derogado que se conserva en el texto.
DEROGADO_RE = re.compile(r"\(?\s*Se\s+deroga", re.IGNORECASE)


def fechas_reforma_en(texto: str) -> list[date]:
    """Todas las fechas DOF presentes en `texto`, únicas y ordenadas."""
    fechas: set[date] = set()
    for clausula in DOF_CLAUSE_RE.findall(texto):
        for d, mo, y in DATE_RE.findall(clausula):
            fechas.add(date(int(y), int(mo), int(d)))
    return sorted(fechas)


def _quitar_encabezados(page_text: str, titulos: tuple[str, ...]) -> str:
    fuera = tuple(t.strip() for t in titulos)
    lineas = []
    for line in page_text.splitlines():
        s = line.strip()
        if s.startswith(HEADER_PREFIXES) or PAGE_FOOTER_RE.match(s) or s in fuera:
            continue
        lineas.append(line)
    return "\n".join(lineas)


def _titulo_corrido(paginas: list[str]) -> tuple[str, ...]:
    """Detecta el título que la Cámara repite como encabezado en cada página.

    Es la primera línea no vacía que más se repite entre páginas (saltando la
    portada). Auto-detectarlo evita codificar a mano el encabezado de cada
    documento —y que un título mal escrito fugue al cuerpo de un artículo cuando
    una página corta a media oración.
    """
    primeras = []
    for t in paginas[1:]:
        for ln in t.splitlines():
            if ln.strip():
                primeras.append(ln.strip())
                break
    if not primeras:
        return ()
    comun, n = Counter(primeras).most_common(1)[0]
    return (comun,) if n >= max(3, len(paginas) // 2) else ()


def texto_limpio(pdf_path: str, doc: Documento) -> str:
    """Texto completo del PDF sin encabezados/pies de página."""
    with pdfplumber.open(pdf_path) as pdf:
        paginas = [page.extract_text() or "" for page in pdf.pages]
    fuera = doc.titulos_encabezado + _titulo_corrido(paginas)
    return "\n".join(_quitar_encabezados(t, fuera) for t in paginas)


def fecha_version(pdf_path: str) -> date | None:
    """Fecha de la última reforma incorporada al PDF = versión del snapshot."""
    with pdfplumber.open(pdf_path) as pdf:
        head = pdf.pages[0].extract_text() or ""
    m = VERSION_RE.search(head) or NUEVO_RE.search(head)
    return date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def _solo_articulado(texto: str) -> str:
    """Recorta antes de los Transitorios (todo lo posterior no es articulado vigente)."""
    m = TRANSITORIOS_RE.search(texto)
    return texto[: m.start()] if m else texto


def parse(pdf_path: str, doc: Documento) -> list[Unidad]:
    """Parsea el PDF de una ley/código/reglamento y devuelve sus unidades."""
    return parse_texto(texto_limpio(pdf_path, doc))


def parse_texto(clean_text: str, start: int = 1) -> list[Unidad]:
    """Segmenta texto ya limpio en unidades. Separado para poder probarlo sin PDF."""
    texto = _solo_articulado(clean_text)
    lineas = texto.splitlines()

    unidades: list[Unidad] = []
    actual: Unidad | None = None
    cur_titulo = ""
    cur_capitulo = ""
    esperado = start                 # número de artículo esperado (valida la secuencia)

    def flush(u: Unidad | None) -> None:
        if u is not None:
            u.cuerpo = u.cuerpo.strip()
            u.fechas_reforma = fechas_reforma_en(u.cuerpo)
            primer = u.cuerpo.split("\n", 1)[0]
            u.derogado = bool(DEROGADO_RE.search(primer))
            unidades.append(u)

    for raw in lineas:
        line = raw.rstrip()
        stripped = line.strip()

        if TITULO_RE.match(stripped) and (actual is None or len(stripped) < 35):
            cur_titulo = stripped
            continue

        if CAPITULO_RE.match(stripped) and (actual is None or len(stripped) < 30):
            cur_capitulo = stripped
            continue

        am = ARTICULO_RE.match(stripped)
        if am:
            numero = int(am.group(1))
            letra = (am.group(2) or "").upper()
            ordinal = (am.group(3) or "").title()
            ord_num = am.group(4) or ""           # numeral tras el ordinal: "Bis 1"
            tiene_sufijo = bool(letra or ordinal)
            # Aceptar solo el siguiente esperado (bare) o una variante del actual.
            # Así se descartan las citas "Artículo 89 de la Constitución".
            es_siguiente = numero == esperado and not tiene_sufijo
            es_variante = (actual is not None and numero == actual.numero
                           and tiene_sufijo)
            if es_siguiente or es_variante:
                flush(actual)
                actual = Unidad(
                    numero=numero, letra=letra, ordinal=ordinal, ord_num=ord_num,
                    titulo=cur_titulo, capitulo=cur_capitulo,
                )
                actual.cuerpo = line + "\n"
                if es_siguiente:
                    esperado = numero + 1
                continue

        if actual is not None:
            actual.cuerpo += line + "\n"

    flush(actual)
    return unidades
