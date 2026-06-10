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
# - Se tolera un punto espurio tras la palabra ("Artículo. 88.", errata del
#   Reglamento de la Ley Aduanera): la validación de secuencia filtra falsos positivos.
ORDINALES = "Bis|Ter|Qu[aá]ter|Quintus|Quinquies|Sexies|Septies|Octies|Nonies|Decies"
ARTICULO_RE = re.compile(
    r"^(?:Art[íi]culo|ART[IÍ]CULO)\.?\s+(\d+)\s*[oº°]?\.?"  # "Artículo"/"ARTÍCULO" + número

    r"(?:-([A-Z])(?![A-Za-z]))?"                     # letra "-A" PEGADA, una sola letra
    rf"(?:[\s.\-]+(?i:({ORDINALES}))(?:\s+(\d+))?)?"  # ordinal + numeral opcional ("Bis 1")
    r"\s*\.?-?(?:\s|$|\()"                           # separador final
)

# Encabezados de Título / Capítulo / Sección. En los PDF de la Cámara van en
# MAYÚSCULAS; las compilaciones de la normateca del SAT (RISAT) usan Title-case
# ('Título I'). En ambos formatos el NÚMERO va en una línea y el NOMBRE en la
# siguiente:
#     SECCIÓN IV
#     DEL RÉGIMEN SIMPLIFICADO DE CONFIANZA
# por eso el nombre se captura con lookahead (no como grupo de la regex).
# La variante Title-case exige FIN de línea tras el numeral: una cita partida
# por el renglón ("…en los términos de la\nSección II de este Capítulo.") deja
# "Sección II …" al inicio de línea y NO debe casar; el encabezado real es solo
# "Sección I" / "Capítulo XI" / "Título Segundo" a línea completa. El numeral
# puede ser romano u ordinal en palabra ('Título Noveno', 'Sección Primera'),
# con compuesto opcional ('Décimo Primero').
_ORDINAL_TC = (r"(?:Primer[oa]|Segund[oa]|Tercer[oa]|Cuart[oa]|Quint[oa]|"
               r"Sext[oa]|S[ée]ptim[oa]|Octav[oa]|Noven[oa]|D[ée]cim[oa])")
_NUMERAL_TC = rf"(?:[IVXLCDM]+|{_ORDINAL_TC}(?:\s+{_ORDINAL_TC})?)"
TITULO_RE = re.compile(r"^T[IÍ]TULO\s+[A-ZÁÉÍÓÚÑ]+(?:\s+[A-ZÁÉÍÓÚÑ]+){0,2}\s*$"
                       rf"|^T[íi]tulo\s+{_NUMERAL_TC}\s*$")
CAPITULO_RE = re.compile(r"^CAP[IÍ]TULO\s+([IVXLCDM]+|[ÚU]NICO|PRIMERO|SEGUNDO)\b.*$"
                         rf"|^Cap[íi]tulo\s+(?:{_NUMERAL_TC}|[ÚU]nico)\s*$")
SECCION_RE = re.compile(r"^SECCI[OÓ]N\s+([IVXLCDM]+|[ÚU]NICA|PRIMERA|SEGUNDA)\b.*$"
                        rf"|^Secci[óo]n\s+(?:{_NUMERAL_TC}|[ÚU]nica)\s*$")

# ¿Es la línea-nombre de un encabezado? (la que sigue a "SECCIÓN IV"). Con
# `estricto` exige MAYÚSCULAS (formato Cámara): excluye notas de reforma
# ("Sección adicionada DOF…", en minúsculas). Cuando el encabezado mismo vino en
# Title-case (normateca SAT) basta con que inicie en mayúscula sin nota DOF ni
# puntuación de cierre ('De las Facultades previstas en la Ley Federal…' lleva
# minúsculas a media frase, así que exigir caja palabra por palabra no sirve).
def _es_nombre_encabezado(s: str, estricto: bool = True) -> bool:
    if not s or len(s) > 120:
        return False
    if TITULO_RE.match(s) or CAPITULO_RE.match(s) or SECCION_RE.match(s):
        return False
    if ARTICULO_RE.match(s) or PAGE_FOOTER_RE.match(s):
        return False
    letras = [c for c in s if c.isalpha()]
    if not letras:
        return False
    # Un numeral romano solo es el número de un sub-encabezado sin palabra
    # clave ('I' bajo 'Sección Primera' en la Ley Aduanera), nunca un nombre.
    if re.fullmatch(r"[IVXLCDM]+", s):
        return False
    if all(c.isupper() for c in letras):
        return True
    if estricto:
        return False
    return s[0].isupper() and "DOF" not in s and s[-1] not in ".;:,"

# Frontera del articulado permanente: el primer encabezado de Transitorios.
TRANSITORIOS_RE = re.compile(
    r"^[ \t]*(?:Artículos?\s+Transitorios?|ARTÍCULOS?\s+TRANSITORIOS?|"
    r"TRANSITORIOS?|T\s*R\s*A\s*N\s*S\s*I\s*T\s*O\s*R\s*I\s*O\s*S)[ \t]*$",
    re.MULTILINE,
)

# Pie de página: "1 de 377" (Cámara) o "51 / 131" (normateca SAT).
PAGE_FOOTER_RE = re.compile(r"^\d{1,4}\s*(?:de|/)\s*\d{1,4}$")

# Fechas de reforma (DOF). Una cláusula puede encadenar varias con coma.
DOF_CLAUSE_RE = re.compile(r"DOF\s+(\d{2}-\d{2}-\d{4}(?:\s*,\s*\d{2}-\d{2}-\d{4})*)")
DATE_RE = re.compile(r"(\d{2})-(\d{2})-(\d{4})")

# Variante con la fecha en letras, usada por las compilaciones de la normateca
# del SAT: "(DOF 21 de diciembre de 2021)".
MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
         "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10,
         "noviembre": 11, "diciembre": 12}
DOF_LARGA_RE = re.compile(
    r"DOF\s+(\d{1,2})\s+de\s+(" + "|".join(MESES) + r")\s+de\s+(\d{4})",
    re.IGNORECASE,
)

# Versión del texto = fecha del snapshot. La portada trae "Última Reforma DOF
# DD-MM-YYYY" en las leyes ya reformadas; un documento nuevo sin reformas (p. ej.
# un reglamento reciente) trae en su lugar "Nuevo Reglamento/Código DOF DD-MM-YYYY".
VERSION_RE = re.compile(
    r"[ÚU]ltimas?\s+[Rr]eformas?\s+(?:publicadas?\s+)?DOF\s+(\d{2})-(\d{2})-(\d{4})"
)
VERSION_LARGA_RE = re.compile(
    r"[ÚU]ltimas?\s+[Rr]eformas?\s+(?:publicadas?\s+)?" + DOF_LARGA_RE.pattern,
    re.IGNORECASE,
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
    for d, mes, y in DOF_LARGA_RE.findall(texto):
        fechas.add(date(int(y), MESES[mes.lower()], int(d)))
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


def es_ruido_factory(pdf_path: str, doc: Documento):
    """Predicado 'línea es encabezado/pie' para alinear pasajes contra el PDF
    (locate.py). Replica `_quitar_encabezados`: prefijos de la Cámara, pie
    'N de M' y el título corrido del documento."""
    with pdfplumber.open(pdf_path) as pdf:
        paginas = [p.extract_text() or "" for p in pdf.pages]
    titulos = set(doc.titulos_encabezado) | set(_titulo_corrido(paginas))

    def es_ruido(texto: str) -> bool:
        return (texto.startswith(HEADER_PREFIXES) or bool(PAGE_FOOTER_RE.match(texto))
                or texto in titulos)
    return es_ruido


def fecha_version(pdf_path: str) -> date | None:
    """Fecha de la última reforma incorporada al PDF = versión del snapshot."""
    with pdfplumber.open(pdf_path) as pdf:
        head = pdf.pages[0].extract_text() or ""
    m = VERSION_RE.search(head) or NUEVO_RE.search(head)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = VERSION_LARGA_RE.search(head)
    if m:
        return date(int(m.group(3)), MESES[m.group(2).lower()], int(m.group(1)))
    return None


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
    cur_seccion = ""
    # ('titulo'|'capitulo'|'seccion', encabezado, líneas-nombre acumuladas):
    # un encabezado espera su nombre en la(s) línea(s) siguiente(s).
    pendiente: tuple[str, str, list[str]] | None = None
    esperado = start                 # número de artículo esperado (valida la secuencia)

    def flush(u: Unidad | None) -> None:
        if u is not None:
            u.cuerpo = u.cuerpo.strip()
            u.fechas_reforma = fechas_reforma_en(u.cuerpo)
            primer = u.cuerpo.split("\n", 1)[0]
            u.derogado = bool(DEROGADO_RE.search(primer))
            unidades.append(u)

    def _fijar(nivel: str, valor: str) -> None:
        nonlocal cur_titulo, cur_capitulo, cur_seccion
        if nivel == "titulo":
            cur_titulo, cur_capitulo, cur_seccion = valor, "", ""   # nuevo título resetea lo inferior
        elif nivel == "capitulo":
            cur_capitulo, cur_seccion = valor, ""                   # nuevo capítulo resetea sección
        else:
            cur_seccion = valor

    for raw in lineas:
        line = raw.rstrip()
        stripped = line.strip()

        # ¿La línea anterior fue un encabezado esperando su nombre (línea siguiente)?
        if pendiente is not None:
            if not stripped:
                continue                                            # salta blancos entre número y nombre
            nivel, encabezado, partes = pendiente
            # Encabezado en MAYÚSCULAS (Cámara) → nombre en MAYÚSCULAS, una línea;
            # Title-case (normateca SAT) → nombre Title-case, hasta dos líneas
            # (los nombres largos envuelven: 'De las Facultades previstas en…').
            estricto = encabezado.isupper()
            acumulable = not partes or (not estricto and len(partes) < 2)
            if acumulable and _es_nombre_encabezado(stripped, estricto=estricto):
                pendiente = (nivel, encabezado, partes + [stripped])
                continue
            pendiente = None
            nombre = " ".join(partes)
            # 'TÍTULO IV. DE LAS PERSONAS FÍSICAS'; sin nombre: solo número.
            _fijar(nivel, f"{encabezado}. {nombre}" if nombre else encabezado)
            # no 'continue': esta línea puede ser un artículo u otro encabezado

        if TITULO_RE.match(stripped) and (actual is None or len(stripped) < 35):
            pendiente = ("titulo", stripped, [])
            continue

        if CAPITULO_RE.match(stripped) and (actual is None or len(stripped) < 30):
            pendiente = ("capitulo", stripped, [])
            continue

        if SECCION_RE.match(stripped) and (actual is None or len(stripped) < 35):
            pendiente = ("seccion", stripped, [])
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
                    titulo=cur_titulo, capitulo=cur_capitulo, seccion=cur_seccion,
                )
                actual.cuerpo = line + "\n"
                if es_siguiente:
                    esperado = numero + 1
                continue

        if actual is not None:
            actual.cuerpo += line + "\n"

    flush(actual)
    return unidades
