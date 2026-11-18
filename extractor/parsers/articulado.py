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
import unicodedata
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
# - El numeral con guion va tras el número o la letra ('Artículo 58-1.',
#   'Artículo 195-L-4.', 'Artículo 195-Z-11 Bis.'): la LFD y la LFPCA intercalan
#   así artículos entre dos números.
# - El ordinal (Bis/Ter/...) admite separador espacio, punto o guion, en cualquier caja.
# - Se tolera un punto espurio tras la palabra ("Artículo. 88.", errata del
#   Reglamento de la Ley Aduanera): la validación de secuencia filtra falsos positivos.
ORDINALES = "Bis|Ter|Qu[aá]ter|Quintus|Quinquies|Sexies|Septies|Octies|Nonies|Decies"
ARTICULO_RE = re.compile(
    r"^[\"“]?(?:Art[íi]culo|ART[IÍ]CULO|Art[íi]culos(?=\s+\d+\s*[oº°]?\.-))\.?\s+(\d{1,3}(?:,\d{3})+|\d+)\s*(?:/[oº°]|[oº°])?\.?"  # "Artículo"/"ARTÍCULO" + número ('2/o' de la Ley Orgánica del Ejército)

    r"(?:(?:-(?=[A-Z])|\s(?=[A-Z][.\-]))([A-Z])(?![A-Za-z]))?"  # letra "-A" PEGADA o " A." (118 A.)
    r"(?:-(\d{1,2})(?=[\s.\-(]|$))?"                 # numeral con guion: "58-1", "195-L-4"
    rf"(?:[\s.\-]+(?i:({ORDINALES}))"               # ordinal
    r"(?:[\s\-]+(\d+)(?:\s+([A-Z])(?=[.\-]|\s*$))?)?)?"  # numeral ("Bis 1") y letra ("Bis 35 A.-")
    r"(?:\s*\.?-?(?:\s|$|\()|\.-(?=\S))"             # separador final (o ".-" pegado al texto)
)

# Las leyes estatales (ver estatal.py) admiten además lo que sus PDF escriben y
# los de la Cámara no: el rótulo en plural ('ARTÍCULOS 50.-', 'Artículos 175.'),
# abreviado ('Art. 229.'), el punto pegado al texto ('Artículo 127.Se deroga.',
# 'Artículo 36.A través'), dos puntos ('Artículo 276 Quater: Comete'), el guion
# separado ('ARTÍCULO 29 BIS. - ') o antes del punto ('Artículo 137-.'), la
# letra sin guion ('Artículo 132G.'), el numeral tras punto o pegado al ordinal
# ('Artículo 176-Bis. 3.', 'Artículo 176-Ter2.'), los ordinales latinos más
# allá de Quinquies y sus erratas ('323 Sextus', '135 Quitus', '356 CUARTER').
# Es otra regex para no cambiar la lectura de las leyes federales. El paréntesis
# que sigue al rótulo ('Artículo 58 (Derogado)') es del texto.
ORDINALES_ESTATAL = (ORDINALES + "|Quitus|Quintos|Sextus|Sexties|S[ée]ptimus|Octavus|"
                     "Undecies|Duodecies|Terdecies|Quaterdecies|Cuarter")
ARTICULO_ESTATAL_RE = re.compile(
    r"^[\"“]?(?:Art[íi]culo|ART[IÍ]CULO|\(SIC\)(?=\s+\d+\s+[A-ZÁÉÍÓÚÑ]+\s*\.-)|Art(?=\.\s*\d+(?:\s+[A-Za-z]+)?\.(?:\s|$)|\.\s*\d+\s+\((?:DEROGAD|Derogad)|\.\s*\d+\.-\s?\(\s?(?:DEROGAD|Derogad))|(?:Art[íi]culos|ART[IÍ]CULOS)(?=\s+\d+\s*[oº°]?\.-?\s))\.?\s+(\d{1,3}(?:,\d{3})+|\d+)\s*(?:/[oº°]|[oº°])?\.?"  # "Artículo"/"ARTÍCULO" + número ('2/o' de la Ley Orgánica del Ejército)

    r"(?:(?:-(?=[A-ZÑ])|\s(?=[A-ZÑ][.\-])|(?<=\d)(?=[A-Z]\.))([A-ZÑ])(?![A-Za-zñ]))?"  # letra "-A", " A." (118 A.) o "132G."; "142-Ñ"
    r"(?:-(\d{1,2})(?=[\s.\-(]|$))?"                 # numeral con guion: "58-1", "195-L-4"
    rf"(?:[\s.\-]+(?i:({ORDINALES_ESTATAL}))"         # ordinal
    r"(?:(?:[\s\-]+|\.\s?|(?=\d))(\d+|(?i:uno|dos|tres)|[IVX]{1,4}(?=\s*[.\-]|,\s+\((?:DEROGAD|Derogad)))(?:\s+([A-Z])(?=[.\-]|\s*$))?"  # numeral ("Bis 1", "Bis. 3", "Ter2", "Bis Uno") y letra ("Bis 35 A.-")
    r"|-([A-Z])(?=[.\-]|\s))?)?"                    # letra pegada al ordinal: "221 BIS-A.-"
    r"(?:\s*\.?\s?[-–]?\.?(?:\s|$|(?=\())|\.-(?=\S)"   # separador final ("29 BIS. - ", "137-.", "209 TER. – " o ".-" pegado)
    r"|\.(?=[A-ZÁÉÍÓÚÑ](?:[a-záéíóúñ]|\s))"            # o el punto pegado: "127.Se deroga.", "36.A través"
    r"|:(?=\s)"                                      # o dos puntos: "Artículo 276 Quater: Comete"
    r"|,\s+(?=\((?:DEROGAD|Derogad)))"                 # o coma y nota: "ARTICULO 208 BIS, (DEROGADO, P.O. …)"
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
_BIS_TC = r"(?:\s+(?:Bis|Ter))?"
TITULO_RE = re.compile(r"^T[IÍ]TULO\s+[A-ZÁÉÍÓÚÑ]+(?:\s+[A-ZÁÉÍÓÚÑ]+){0,2}\s*$"
                       rf"|^T[íi]tulo\s+{_NUMERAL_TC}{_BIS_TC}\s*$")
_ORDINAL_MAY = (r"PRIMER[OA]|SEGUND[OA]|TERCER[OA]|CUART[OA]|QUINT[OA]|SEXT[OA]|"
                 r"S[EÉ]PTIM[OA]|OCTAV[OA]|NOVEN[OA]|D[EÉ]CIM[OA]")
CAPITULO_RE = re.compile(rf"^CAP[IÍ]T[UI]LO\s+([IVXLCDM]+|[ÚU]NICO|{_ORDINAL_MAY})\b.*$"
                         rf"|^Cap[íi]tulo\s+(?:{_NUMERAL_TC}|[ÚU]nico){_BIS_TC}\s*$")
# Libro: nivel sobre el Título en los códigos (Código Penal, Código Civil).
LIBRO_RE = re.compile(r"^LIBRO\s+[A-ZÁÉÍÓÚÑ]+(?:\s+[A-ZÁÉÍÓÚÑ]+)?\s*$"
                      rf"|^Libro\s+{_NUMERAL_TC}\s*$")
SECCION_RE = re.compile(rf"^SECCI[OÓ]N\s+([IVXLCDM]+|[ÚU]NICA|{_ORDINAL_MAY})\b.*$"
                        rf"|^Secci[óo]n\s+(?:{_NUMERAL_TC}|[ÚU]nica){_BIS_TC}\s*$")
# Parte: nivel del Código Civil ('PARTE SEGUNDA', 'TERCERA PARTE') y de la Ley de
# Amparo ('Segunda Parte'). Apartado: subdivisión de capítulo ('APARTADO II',
# 'Apartado A'), sin más texto en la línea.
_ORD_PARTE = rf"(?:{_ORDINAL_MAY}|{_ORDINAL_TC})"
PARTE_RE = re.compile(rf"^(?:PARTE|Parte)\s+{_ORD_PARTE}\s*$|^{_ORD_PARTE}\s+(?:PARTE|Parte)\s*$")
APARTADO_RE = re.compile(r"^(?:APARTADO|Apartado)\s+(?:[A-Z]|[IVXLC]+)\s*$")

# ¿Es la línea-nombre de un encabezado? (la que sigue a "SECCIÓN IV"). Con
# `estricto` exige MAYÚSCULAS (formato Cámara): excluye notas de reforma
# ("Sección adicionada DOF…", en minúsculas). Cuando el encabezado mismo vino en
# Title-case (normateca SAT) basta con que inicie en mayúscula sin nota DOF ni
# puntuación de cierre ('De las Facultades previstas en la Ley Federal…' lleva
# minúsculas a media frase, así que exigir caja palabra por palabra no sirve).
def _es_nombre_encabezado(s: str, estricto: bool = True, estatal: bool = False) -> bool:
    if not s or len(s) > 120:
        return False
    if TITULO_RE.match(s) or CAPITULO_RE.match(s) or SECCION_RE.match(s):
        return False
    if (ARTICULO_ESTATAL_RE if estatal else ARTICULO_RE).match(s) or PAGE_FOOTER_RE.match(s):
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
    # Algunos nombres vienen entre comillas: '"De la Información y la Transparencia"'.
    return s.lstrip('"“«')[:1].isupper() and "DOF" not in s and s[-1] not in ".;:,"

# Nombre en caja normal de un encabezado en MAYÚSCULAS. Solo se acepta si el
# bloque desemboca en el siguiente artículo (ver parse_texto); aquí se descartan
# las notas de reforma y lo que no puede ser un nombre.
MAX_LINEAS_ENCABEZADO = 12

# Marca de agua vertical '(Primera Sección)' que pdfplumber reparte en renglones
# sueltos ('(P' / 'rim' / 'e' / 'ra' / 'S' / …). Dentro de un bloque de
# encabezado no es nombre ni texto: no debe cerrar el bloque ni pegarse al
# artículo anterior.
MARCA_AGUA_RE = re.compile(
    r"\(P|rim|e|ra|S|c|ió|n|\)|\(Primera Secci[oó]n\)|\(Segunda Secci[oó]n\)")
MAX_LINEAS_NOMBRE = 3


# Primer renglón de una nota de reforma o de invalidez ('Artículo declarado
# inválido y suprimido …', 'Derogación del inciso declarada inválida …'), a veces
# sin 'DOF' hasta el renglón siguiente.
NOTA_REFORMA_RE = re.compile(
    r"^(?:[A-ZÁÉÍÓÚa-záéíóú]+|Derogaci[oó]n\s+d(?:el|e la))\s+(?:\w+\s+)?"
    r"(?:adicionad|reformad|derogad|declarad|suprimid|recuperad)[oa]s?\b")


def _es_nombre_suelto(s: str, continuacion: bool = False, estatal: bool = False) -> bool:
    if not s or len(s) > 150 or "DOF" in s or s.startswith("("):
        return False
    if NOTA_REFORMA_RE.match(s):
        return False                      # 'Numeral declarado inválido …' es nota, no nombre
    if MARCA_FORMULA_RE.match(s):
        return False
    if (_es_encabezado(s) or (ARTICULO_ESTATAL_RE if estatal else ARTICULO_RE).match(s)
            or PAGE_FOOTER_RE.match(s)):
        return False
    if re.match(r"\[\s*Art[ií]culo\b", s):
        return False                      # '[Artículo 28 Bis. Suprimido]': texto, no nombre
    if estatal and re.fullmatch(r"[A-Z]\)\s+[A-ZÁÉÍÓÚÑ]{2,}(?:\s+[A-ZÁÉÍÓÚÑ]+)*", s):
        return s[-1:] not in ".;:"        # rótulo 'C) DEL SECRETARIO DE FINANZAS' (C, D, L, M no son fracción)
    if re.fullmatch(r"[IVXLCDM]+", s) or re.match(r"^(?:[IVXLCDM]+|[a-zñ])\s*[.)\-–]", s):
        return False                      # numeral solo, fracción 'II.-' o inciso 'a)'
    if estatal and re.match(rf"^[IVXLCDM]+\s+(?:{ORDINALES})\b", s, re.IGNORECASE):
        return False                      # fracción intercalada 'XIII Bis.', 'VI Quater'
    if "$" in s or "...." in s or "…" in s:
        return False                      # importes y puntos guía: renglón de tarifa
    if estatal and re.search(r";\s*[yoeu]?$", s):
        return False                      # fin de una fracción enumerada ('…las mujeres; y')
    # La coma final es de un nombre que sigue en la línea siguiente. Una comilla
    # de cierre no oculta el fin de oración: 'moneda nacional.”' es el final de
    # un párrafo citado, no un rótulo.
    if s.rstrip("\"”»'’")[-1:] in ".;:":
        return False
    inicio = s.lstrip('"“«[')[:1]
    return inicio.islower() if continuacion else inicio.isupper()


def _es_encabezado(s: str) -> bool:
    return bool(TITULO_RE.match(s) or CAPITULO_RE.match(s) or SECCION_RE.match(s)
                or LIBRO_RE.match(s) or PARTE_RE.match(s) or APARTADO_RE.match(s))


# Notas de invalidez de la SCJN ('Denominación declarada inválida por Resolutivos…',
# 'Denominación que "recupera su vigencia…"'), a veces sin 'DOF' en el renglón.
NOTA_SCJN_RE = re.compile(
    r"^(?:Denominaci[oó]n|Cap[ií]tulo|T[ií]tulo|Secci[oó]n)\s+"
    r"(?:declarad[oa]\s+inv[aá]lid[oa]|que\s+[“\"]recupera)")


MARCA_DEROGADO_RE = re.compile(r"\(?\s*(?:Se\s+deroga|Derogad[oa])\s*\)?\.?", re.IGNORECASE)


def _es_nota_de_bloque(s: str) -> bool:
    """Nota de reforma de un encabezado o marca de capítulo derogado."""
    return bool(DOF_CLAUSE_RE.search(s) or DOF_LARGA_RE.search(s)) and len(s) < 200 \
        or bool(NOTA_SCJN_RE.match(s)) \
        or bool(re.fullmatch(r"\(?\s*(?:Se\s+deroga|Derogad[oa])\s*\)?\.?", s,
                             re.IGNORECASE)) \
        or bool(re.fullmatch(r"\[\s*Art[ií]culos?\s[^\]]*Suprimidos?\s*\]", s)) \
        or bool(re.fullmatch(r"Art[ií]culos?\s+\d+(?:\s+(?:al?|y)\s+\d+)?\s*\.?-?\s*"
                             r"Se\s+derogan?\.?", s, re.IGNORECASE))


# Frontera del articulado permanente: el primer encabezado de Transitorios, en
# mayúsculas o en caja de título, con o sin espacios entre letras y con
# 'Artículos'/'Disposiciones' delante: 'TRANSITORIOS', 'T r a n s i t o r i o s',
# 'ARTICULOS TRANSITORIOS:', 'Artículo Transitorio'. En minúsculas no cuenta:
# 'transitorios' solo en una línea es una cita partida a media frase.
_TRANSITORIOS_MAY = r"T\s*R\s*A\s*N\s*S\s*I\s*T\s*O\s*R\s*I\s*[OA]\s*S?"
_TRANSITORIOS_TC = r"T\s*r\s*a\s*n\s*s\s*i\s*t\s*o\s*r\s*i\s*[oa]\s*s?"
TRANSITORIOS_RE = re.compile(
    r"^[ \t]*(?:(?:ART[ÍI]CULOS?|DISPOSICIONES)\s+)?" + _TRANSITORIOS_MAY + r"[ \t]*[:.]?[ \t]*$"
    r"|^[ \t]*(?:(?:Art[íi]culos?|Disposiciones)\s+)?" + _TRANSITORIOS_TC + r"[ \t]*[:.]?[ \t]*$"
    # Compilación de los decretos de reforma al final: 'ARTÍCULOS TRANSITORIOS DE
    # DECRETOS DE REFORMA' (el título puede envolverse en varias líneas).
    r"|^[ \t]*Disposiciones\s+transitorias[ \t]*[:.]?[ \t]*$"
    r"|^[ \t]*(?:ART[ÍI]CULOS\s+)?TRANSITORIOS\s+DE(?:L|\s+LOS)?\s+DECRETOS?\b",
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

# Fecha de una nota de reforma estatal, en letras ('(REFORMADO, G.O. 25 DE MAYO
# DE 2000)') o numérica ('Párrafo reformado G.O. CDMX 08/12/23').
FECHA_LARGA_RE = re.compile(
    r"(\d{1,2})\s+DE\s+(" + "|".join(MESES) + r")\s+(?:DE|DEL)\s+(\d{4})", re.IGNORECASE)
FECHA_NUMERICA_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4}|\d{2})\b")
# Con el mes en romano: '(Ref. P. O. No. 75, 31-X-22)' (Querétaro).
FECHA_ROMANA_RE = re.compile(r"\b(\d{1,2})-\s?(XII|XI|X|IX|VIII|VII|VI|V|IV|III|II|I)-(\d{4}|\d{2})\b")
_MES_ROMANO = {r: n for n, r in enumerate(
    "I II III IV V VI VII VIII IX X XI XII".split(), 1)}


def fechas_en_notas(texto: str, notas: re.Pattern) -> list[date]:
    """Fechas de las notas de reforma de una fuente estatal (renglones que casan
    con `notas`), únicas y ordenadas."""
    out: set[date] = set()
    for ln in texto.splitlines():
        if notas.match(ln.strip()):
            for d, mes, a in FECHA_LARGA_RE.findall(ln):
                try:
                    out.add(date(int(a), MESES[mes.lower()], int(d)))
                except ValueError:
                    continue
            for d, m, a in FECHA_NUMERICA_RE.findall(ln):
                anio = int(a) if len(a) == 4 else 2000 + int(a)
                try:
                    out.add(date(anio, int(m), int(d)))
                except ValueError:
                    continue
            for d, m, a in FECHA_ROMANA_RE.findall(ln):
                # '2-IV-99' es de 1999: las compilaciones empiezan en el siglo XX.
                anio = int(a) if len(a) == 4 else (2000 if int(a) < 50 else 1900) + int(a)
                try:
                    out.add(date(anio, _MES_ROMANO[m], int(d)))
                except ValueError:
                    continue
    return sorted(out)


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


# Marca de agua girada ('DIARIO OFICIAL' / 'Viernes 15 de junio de 2007') que
# pdfplumber reparte en fragmentos de 1 a 3 caracteres: unos en renglones
# propios y otros pegados al final de un renglón de texto. Solo se limpia en las
# páginas donde hay muchos renglones así (la marca está presente).
_FRAGMENTO_RE = re.compile(r"(?:[A-Za-zÁÉÍÓÚáéíóúñ0-9()]{1,3})(?: [A-Za-zÁÉÍÓÚáéíóúñ0-9()]{1,3})*")
_FRAGMENTOS_COLA_RE = re.compile(
    r"(?:\s+(?:d e|0 7 e s|1 5|2 0|dV|ie|rn|ju|io|ió|e c|c c|IA|IO|IC|[DRFL]))+$")
_FRAGMENTOS_MEDIO_RE = re.compile(r"\s(?:d e|0 7 e s)(?=\s)")


def _es_fragmento_marca(s: str) -> bool:
    return bool(s) and len(s) <= 8 and _FRAGMENTO_RE.fullmatch(s) is not None \
        and not re.fullmatch(r"[IVX]+|\d{2,}(?: \d+)*|\d(?: \d+)*(?: \d{2,})(?: \d+)*|[ivx]+", s)


# Definición de una variable tras una fórmula ('i : Cuota prevista…'): el
# renglón suelto de arriba ('t') es la letra del símbolo t_i, no marca de agua.
_DEFINICION_VARIABLE_RE = re.compile(r"^[\w*,]{1,3}(?: [\w*,]{1,3})? ?: \S")


def _quitar_marca_girada(page_text: str) -> str:
    lineas = page_text.splitlines()
    if sum(_es_fragmento_marca(ln.strip()) for ln in lineas) < 8:
        return page_text
    # Una tabla de cuotas con encabezados girados ('$' sueltos en renglones
    # propios) también deja renglones cortos: ahí son datos, no marca de agua.
    if sum(ln.strip() == "$" for ln in lineas) >= 2:
        return page_text
    salida = []
    for i, ln in enumerate(lineas):
        if _es_fragmento_marca(ln.strip()):
            siguiente = lineas[i + 1].strip() if i + 1 < len(lineas) else ""
            if not _DEFINICION_VARIABLE_RE.match(siguiente):
                continue
        if len(ln.strip()) > 12:
            ln = _FRAGMENTOS_COLA_RE.sub("", _FRAGMENTOS_MEDIO_RE.sub("", ln))
        salida.append(ln)
    return "\n".join(salida)


def _quitar_encabezados(page_text: str, titulos: tuple[str, ...],
                        prefijos: tuple[str, ...] = HEADER_PREFIXES) -> str:
    fuera = tuple(t.strip() for t in titulos)
    lineas = []
    for line in page_text.splitlines():
        s = line.strip()
        if (prefijos and s.startswith(prefijos)) or PAGE_FOOTER_RE.match(s) or s in fuera:
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
    umbral = max(min(3, len(paginas) - 1), len(paginas) // 2)   # PDF de 3 páginas: basta con 2
    if n < umbral:
        return ()
    # Un título largo se parte en dos líneas ('… CON RECURSOS' / 'DE PROCEDENCIA
    # ILÍCITA'): la segunda también se repite justo debajo en cada página.
    segundas = []
    for t in paginas[1:]:
        lineas = [ln.strip() for ln in t.splitlines() if ln.strip()]
        if len(lineas) > 1 and lineas[0] == comun:
            segundas.append(lineas[1])
    if segundas:
        segunda, m = Counter(segundas).most_common(1)[0]
        if m >= umbral and not segunda.startswith(HEADER_PREFIXES):
            return (comun, segunda)
    return (comun,)


def _sin_numero_de_pagina(paginas: list[str]) -> list[str]:
    """Quita el número de página suelto ('92') al pie o al encabezado de cada
    página, si el PDF lo pone en la mayoría de ellas (varios estatales; la
    Cámara usa 'N de M'). Solo se quita el renglón que coincide con el número
    de esa página, con el mismo desfase que en las demás: un '10' en una tabla
    no lo es."""
    def extremos(t: str) -> list[tuple[int, int]]:
        lineas = t.split("\n")
        llenas = [k for k, ln in enumerate(lineas) if ln.strip()]
        return [(k, int(lineas[k].strip())) for k in {llenas[0], llenas[-1]}
                if re.fullmatch(r"\d{1,4}", lineas[k].strip())] if llenas else []
    desfases = Counter(n - i for i, t in enumerate(paginas) for _, n in extremos(t))
    if not desfases:
        return paginas
    desfase, veces = desfases.most_common(1)[0]
    if veces < max(3, len(paginas) // 2):
        return paginas
    salida = []
    for i, t in enumerate(paginas):
        lineas = t.split("\n")
        for k, n in extremos(t):
            if n - i == desfase:
                lineas[k] = ""
        salida.append("\n".join(lineas))
    return salida


def limpiar_paginas(paginas: list[str], doc: Documento, formulas: bool = False) -> str:
    """Texto completo sin encabezados/pies, a partir del texto crudo por página.
    Con `formulas`, cada fórmula ilegible se sustituye por su marca."""
    fuera = doc.titulos_encabezado + _titulo_corrido(paginas)
    if doc.medio:
        paginas = _sin_numero_de_pagina(paginas)
    # Las leyes estatales no traen el encabezado de la Cámara, y en ellas un
    # renglón que empieza con 'Secretaría General' es texto ('…el apoyo de la /
    # Secretaría General y sus Coordinaciones'). Algunos de sus PDF escriben
    # acentos descompuestos ('i' + acento: 'Artículo'), que el rótulo no reconoce.
    prefijos = () if doc.medio else HEADER_PREFIXES
    if doc.medio:
        paginas = [unicodedata.normalize("NFC", t) for t in paginas]
    limpias = (_quitar_encabezados(_quitar_marca_girada(t), fuera, prefijos) for t in paginas)
    if doc.medio and doc.notas_previas:
        limpias = (_rotulo_abreviado_completo(t) for t in limpias)
    if doc.notas_en_linea:
        limpias = _notas_aparte(list(limpias), re.compile(doc.notas_en_linea))
    if not formulas:
        return "\n".join(limpias)
    # Se detecta sobre el texto ya unido: una fórmula que cruza el salto de
    # página es una sola y lleva la marca de la página donde empieza.
    lineas, pagina_de = [], []
    for n, t in enumerate(limpias, 1):
        partes = t.split("\n")
        lineas += partes
        pagina_de += [n] * len(partes)
    return sustituir_formulas("\n".join(lineas), pagina_de)


# 'Art. 54.- Para la inscripción…' o 'Art. 134. La cancelación…' (Código Civil
# de Nuevo León): el rótulo abreviado. Se lee como 'Artículo 54.-', igual que el
# encabezado '# Artículo 54.' de su unidad: así la nota previa y el rótulo de la
# propia unidad que le sigue se reconocen como tales (verificar.cobertura).
_ROTULO_ABREVIADO_RE = re.compile(
    r"(?m)^Art(?=\.\s*\d+(?:\s+[A-Za-z]+(?:\s+[IVX]+)?)?\.-?(?:\s|$))\.?")


def _rotulo_abreviado_completo(texto: str) -> str:
    return _ROTULO_ABREVIADO_RE.sub("Artículo", texto)


def _notas_aparte(paginas: list[str], nota: re.Pattern) -> list[str]:
    """Cada nota a renglón seguido en su propio renglón, sin el salto que la
    partía. Una nota que cruza el salto de página (arranca en los últimos renglones
    de una y sigue en los primeros de la siguiente) se junta en la primera."""
    salida = []
    recorte = 0   # lo que la nota partida de la página anterior se llevó de esta
    for i, texto in enumerate(paginas):
        texto = texto[recorte:].removeprefix("\n") if recorte else texto
        recorte = 0
        # Una nota entre paréntesis que arranca al final de la página y sigue en
        # los primeros renglones de la siguiente se busca sobre ambas.
        sigue = "\n".join(paginas[i + 1].split("\n")[:3]) if i + 1 < len(paginas) else ""
        partes, previo = [], 0
        for m in nota.finditer(texto + "\n" + sigue if sigue else texto):
            if m.start() >= len(texto):
                break
            if m.end() > len(texto):
                # La nota cruza el salto de página: queda completa en esta y la
                # siguiente pierde su resto (si la unión no es una nota entera
                # que cierra en esos renglones, no se toca).
                recorte = m.end() - len(texto) - 1
                texto = texto + "\n" + sigue[:recorte]
            antes = texto[previo:m.start()].rstrip(" \t")
            # '…o de particulares;' / 'y (Ref. …)': la conjunción que cierra la
            # fracción viene en el renglón de la nota; es del texto anterior.
            antes = re.sub(r"(?<=\S)\n(y|o|e|u|y/o)$", r" \1", antes)
            partes.append(antes + ("\n" if antes and not antes.endswith("\n") else ""))
            # Una fecha partida en su guion ('1-' / 'IX-17') se une sin espacio.
            partes.append(re.sub(r"\s*\n\s*", " ", re.sub(r"(?<=\d-)\s*\n\s*|\s*\n\s*(?=-)", "", m.group(0))))
            previo = m.end()
            # Un dígito suelto pegado a la nota y al fin de renglón ('…19-VIII-24)9')
            # es una marca del PDF, no texto.
            pegado = re.match(r"\d{1,2}(?=\n|$)", texto[previo:])
            if pegado:
                previo += pegado.end()
            if previo < len(texto) and texto[previo] != "\n":
                partes.append("\n")
                previo += len(texto[previo:]) - len(texto[previo:].lstrip(" \t"))
        salida.append("".join(partes) + texto[previo:])
    return salida


def texto_limpio(pdf_path: str, doc: Documento) -> str:
    """Texto que segmenta el parser: sin encabezados/pies y con las fórmulas
    ilegibles ya sustituidas por su marca."""
    with pdfplumber.open(pdf_path) as pdf:
        paginas = [page.extract_text() or "" for page in pdf.pages]
    return limpiar_paginas(paginas, doc, formulas=True)


# Cortes de párrafo por la geometría del PDF (leyes estatales). En texto plano
# un renglón justificado que termina en punto ('…a juicio de la autoridad
# judicial;' / 'si la reincidencia fuere…') no se distingue del final de un
# párrafo, ni el final de un párrafo sin punto ('…la normatividad
# correspondiente' / 'El o la titular…') de un renglón que sigue. En el PDF sí:
# entre párrafos hay más espacio que entre renglones, y un renglón que no es el
# último de su párrafo no deja sitio para la primera palabra del siguiente
# (justificado llega al margen; sin justificar, se queda antes, pero sin sitio).
_MIN_RENGLONES_MARGEN = 5
_INTERLINEADO_NORMAL = 1.3     # × el interlineado: renglones del mismo párrafo
_MIN_FRECUENCIA_INTERLINEADO = 0.25   # del paso más común, para contar como interlineado
_MIN_PARTE_RENGLON = 12        # caracteres de una parte de renglón para ubicarla
_INTERLINEADO_PARRAFO = 1.5    # × el interlineado: espacio entre párrafos
# Un renglón que acabó con sitio de sobra y sin más espacio que el normal cierra
# su párrafo solo si cierra también la oración o el inciso ('…; y', '…; o') y
# el siguiente no sigue en minúscula: si no, es un salto forzado a media oración
# ('…a través de la Dirección' / 'General del Registro Civil.') y se decide
# como siempre, por el texto.
_CIERRA_RE = re.compile(r"(?:[.:;)]|[;,]\s+[yoeu])$")
_ACABA_EN_PARTICULA_RE = re.compile(r"\b(?:de|del|la|las|el|los|lo|al|en|con|por|para|un|una|su|sus|que)$")
_ACABA_EN_CONJUNCION_RE = re.compile(r"\b[ou]$")
_FRACCION_ROMANA_RE = re.compile(r"^[IVX]{1,5}\.\s+[A-ZÁÉÍÓÚÑ]")
_INCISO_MAYUSCULA_RE = re.compile(r"^[A-Z]\)\s+\S")
_ABRE_PARRAFO_RE = re.compile(r"^(?:[^a-záéíóúüñ]|[a-zñ]{1,4}[.)]\s)")   # o un inciso: 'd. ', 'ii) '


def _renglones_con_geometria(pdf) -> list[list[dict]]:
    """Por página, sus renglones con texto y posición, en el mismo orden y con
    el mismo texto que `extract_text`. Una página donde no coinciden queda sin
    renglones (sin geometría: su corte lo decide el texto, como siempre)."""
    paginas, margenes = [], []
    for page in pdf.pages:
        lineas = page.extract_text_lines()
        texto = page.extract_text() or ""
        if [ln["text"] for ln in lineas] != texto.split("\n"):
            lineas = []
        # El margen derecho es donde acaban los renglones justificados: el
        # final más común de la página, o del documento si la página tiene pocos.
        margenes.append(Counter(round(ln["x1"]) for ln in lineas if ln["x1"] > page.width * 0.6))
        paginas.append([{"texto": unicodedata.normalize("NFC", ln["text"]).strip(),
                         "top": ln["top"], "x1": ln["x1"],
                         "palabra": _ancho_primera_palabra(ln["chars"])} for ln in lineas])
    total = sum(margenes, Counter())
    general = total.most_common(1)[0][0] if total else None
    for renglones, m in zip(paginas, margenes):
        (propio, veces), = m.most_common(1) or [(None, 0)]
        for r in renglones:
            r["margen"] = propio if veces >= _MIN_RENGLONES_MARGEN else general
    return paginas


def _ancho_primera_palabra(chars: list[dict]) -> float | None:
    """Lo que ocuparía la primera palabra del renglón al final del anterior,
    con el espacio que la separa (un cuarto del cuerpo de la letra)."""
    visibles = [c for c in chars if c["text"].strip()]
    if not visibles:
        return None
    fin = visibles[0]
    for c in visibles[1:]:
        if c["x0"] - fin["x1"] > 1.0 or c["top"] > fin["bottom"]:
            break
        fin = c
    return fin["x1"] - visibles[0]["x0"] + 0.25 * visibles[0]["size"]


def _sin_sitio(a: dict, b: dict) -> bool | None:
    """¿El renglón `a` acabó porque la primera palabra de `b` no cabía?"""
    if a["margen"] is None or b["palabra"] is None:
        return None
    return a["margen"] - a["x1"] < b["palabra"]


def _interlineado(paginas: list[list[dict]]) -> float | None:
    """El paso entre renglones del mismo párrafo: el menor paso frecuente entre
    renglones seguidos. Si casi todo el texto son párrafos de un renglón, el paso
    más común es el de párrafo a párrafo (el doble) y no el interlineado."""
    pasos = Counter(round(b["top"] - a["top"]) for p in paginas for a, b in zip(p, p[1:])
                    if b["top"] > a["top"])
    if not pasos:
        return None
    mayor = pasos.most_common(1)[0][1]
    return float(min(paso for paso, veces in pasos.items()
                     if veces >= _MIN_FRECUENCIA_INTERLINEADO * mayor))


def cortes_geometricos(paginas: list[list[dict]], texto: str) -> dict[tuple[str, str], bool]:
    """(renglón, renglón siguiente) del texto limpio → True si el PDF abre ahí
    un párrafo, False si el primero sigue en el segundo. Solo los pares que la
    geometría decide; un par que aparece dos veces con decisiones distintas se
    descarta. Cada renglón del texto se busca, en orden, entre los renglones de
    las páginas (los encabezados y pies quitados no tienen pareja)."""
    paso = _interlineado(paginas)
    if not paso:
        return {}
    crudos = [(n, k, r) for n, p in enumerate(paginas) for k, r in enumerate(p)]
    lineas = [ln.strip() for ln in texto.split("\n")]
    ubicados: list[int | None] = []
    j = 0
    for s in lineas:
        hallado = None
        sigue_en_renglon = False
        # Una nota entre paréntesis se repite idéntica por todo el texto: ubicarla
        # arrastraría la búsqueda hasta otra copia más adelante.
        if s and not (s.startswith("(") and s.endswith(")")):
            for m in range(j, min(j + 8, len(crudos))):
                crudo = crudos[m][2]["texto"]
                if crudo == s or (len(s) >= _MIN_PARTE_RENGLON and crudo.endswith(" " + s)):
                    hallado = m
                    break
                # El texto limpio separa a veces del final del renglón su nota
                # ('…desplazamiento;' / '(Adición P. O. No. 38, 11-V-18)'): la
                # primera parte ubica el renglón, y la nota queda en el mismo.
                if len(s) >= _MIN_PARTE_RENGLON and crudo.startswith(s + " "):
                    hallado, sigue_en_renglon = m, True
                    break
        if hallado is not None:
            j = hallado if sigue_en_renglon else hallado + 1
        ubicados.append(hallado)

    def decide(a: int, b: int) -> bool | None:
        (pa, ka, ra), (pb, kb, rb) = crudos[a], crudos[b]
        if pa == pb:
            if kb != ka + 1:
                return None
            salto = rb["top"] - ra["top"]
            if salto >= _INTERLINEADO_PARRAFO * paso:
                # Un renglón que acaba en una palabra que no puede cerrar un
                # párrafo ('…del Poder Ejecutivo del') sigue en el siguiente aunque
                # el PDF deje entre ambos el espacio de un párrafo.
                # (salvo si lo que sigue es una fracción: 'integrado por' / 'I. La…').
                if (_ACABA_EN_PARTICULA_RE.search(ra["texto"])
                        and not _CIERRA_RE.search(ra["texto"])
                        and not _FRACCION_ROMANA_RE.match(rb["texto"])):
                    return False
                # Igual con la conjunción 'o'/'u' ('…unidades privativas o' /
                # 'que pertenezcan…'), si lo que sigue abre en minúscula.
                if (_ACABA_EN_CONJUNCION_RE.search(ra["texto"])
                        and not _CIERRA_RE.search(ra["texto"])
                        and len(ra["texto"].split()) >= 3
                        and re.match(r"[a-záéíóúüñ]", rb["texto"])
                        and not re.match(r"[a-zñ]{1,4}[.)]\s", rb["texto"])):
                    return False
                return True
            if salto <= 0 or salto > _INTERLINEADO_NORMAL * paso:
                return None
        elif pb != pa + 1:
            return None
        sin_sitio = _sin_sitio(ra, rb)
        if sin_sitio is None:
            return None
        if sin_sitio:
            return False
        if _CIERRA_RE.search(ra["texto"]) and _ABRE_PARRAFO_RE.match(rb["texto"]):
            return True
        # Un inciso en mayúscula ('B) El Secretario…') tras un renglón que acabó
        # con sitio de sobra abre su propio párrafo aunque el anterior no cierre.
        if _INCISO_MAYUSCULA_RE.match(rb["texto"]):
            return True
        return None

    cortes: dict[tuple[str, str], bool | None] = {}
    for i in range(len(lineas) - 1):
        a, b = ubicados[i], ubicados[i + 1]
        if a is None or b is None:
            continue
        par = (lineas[i], lineas[i + 1])
        d = decide(a, b)
        cortes[par] = d if cortes.get(par, d) == d else None
    return {par: d for par, d in cortes.items() if d is not None}


def texto_y_cortes(pdf_path: str, doc: Documento) -> tuple[str, dict[tuple[str, str], bool]]:
    """`texto_limpio` y, sobre ese mismo texto, sus `cortes_geometricos`."""
    with pdfplumber.open(pdf_path) as pdf:
        paginas = [page.extract_text() or "" for page in pdf.pages]
        geometria = _renglones_con_geometria(pdf)
    texto = limpiar_paginas(paginas, doc, formulas=True)
    return texto, cortes_geometricos(geometria, texto)


# Fórmulas matemáticas compuestas en el PDF con fuentes de símbolos: pdfplumber
# las entrega como renglones de fragmentos sueltos ('i,t', '\uf03d', 'i,t\uf02d 1')
# sin orden legible. No se pueden reconstruir, así que se sustituyen por una marca
# que remite a la página del PDF; el texto legible alrededor ('Donde:' y las
# definiciones de variables) se conserva tal cual.
MARCA_FORMULA = "[Fórmula: consultar el PDF oficial, página {pagina}]"
MARCA_FORMULA_RE = re.compile(r"^\[Fórmula: consultar el PDF oficial(?:, página \d+)?\]$")
# Viñetas de las fuentes Symbol y Wingdings (zona de uso privado): no son álgebra.
_VINETAS = set("\uf0b7\uf0a7\uf0a8\uf0d8\uf076")
# Signos de operación de la fuente Symbol ('(', ')', '*', '+', '−', '=', '×', '÷',
# '√', 'Σ' y las piezas de corchetes y llaves). Una tabla de palomitas o de
# viñetas también trae glifos de esa zona, pero no estos.
_SIMBOLO_RE = re.compile(
    r"[=∑Σ√×÷\uf028\uf029\uf02a\uf02b\uf02d\uf03d\uf0b4\uf0b8\uf0d6\uf0e5\uf0e6-\uf0fb]")
_PALABRA_RE = re.compile(
    r"^[(\[¿¡\"“«]*(?:[a-záéíóúüñ]{4,}|[A-ZÁÉÍÓÚÑ][a-záéíóúüñ]{3,})[.,;:)\]\"”»]*$")
_FUNCIONALES = frozenset("de la el en los las del que por con se al lo su un una es son "
                         "y o a e".split())
MIN_LINEAS_FORMULA = 3
MIN_TOKENS_FORMULA = 5
MIN_CORTOS_FORMULA = 0.6


def _linea_de_formula(s: str) -> bool:
    """Renglón sin ninguna palabra: ni palabras de cuatro letras o más ni
    funcionales ('de', 'la', 'y')."""
    toks = s.split()
    return bool(toks) and not any(
        _PALABRA_RE.match(t) or t.strip("()[].,;:\"“”") in _FUNCIONALES for t in toks)


def es_formula(lineas: list[str]) -> bool:
    """¿Un grupo de renglones sin palabras es una fórmula desarmada? Varios
    renglones, casi todo fragmentos de 1 a 3 caracteres y algún signo de la
    fuente de símbolos o '='. Una fila de tarifa ('$0.01 $1.92 1.92%') no lleva
    esos signos y una fórmula legible de un renglón no llega al mínimo."""
    lineas = [s.strip() for s in lineas if s.strip()]
    toks = [t for s in lineas for t in s.split() if not set(t) <= _VINETAS]
    if len(lineas) < MIN_LINEAS_FORMULA or len(toks) < MIN_TOKENS_FORMULA:
        return False
    if sum(len(t) <= 3 for t in toks) < MIN_CORTOS_FORMULA * len(toks):
        return False
    return any(_SIMBOLO_RE.search(t) for t in toks)


def bloques_de_formula(texto: str) -> list[tuple[int, int]]:
    """Rangos de renglones [ini, fin) que forman cada fórmula del texto."""
    lineas = texto.split("\n")
    bloques: list[tuple[int, int]] = []
    i = 0
    while i < len(lineas):
        if not _linea_de_formula(lineas[i]):
            i += 1
            continue
        j = i
        while j < len(lineas) and (_linea_de_formula(lineas[j]) or not lineas[j].strip()):
            j += 1
        while j > i and not lineas[j - 1].strip():
            j -= 1
        if es_formula(lineas[i:j]):
            bloques.append((i, j))
        i = j
    return bloques


def sustituir_formulas(texto: str, pagina: int | list[int] | None = None) -> str:
    """El texto con cada fórmula en un párrafo propio con su marca. `pagina` es
    la página del texto o, renglón por renglón, la de cada uno."""
    lineas = texto.split("\n")
    for ini, fin in reversed(bloques_de_formula(texto)):
        n = pagina[ini] if isinstance(pagina, list) else pagina
        marca = (MARCA_FORMULA.format(pagina=n) if n is not None
                 else MARCA_FORMULA.replace(", página {pagina}", ""))
        lineas[ini:fin] = ["", marca, ""]
    return "\n".join(lineas)


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


# Portada de las compilaciones estatales: 'Última reforma publicada en la G.O.
# CDMX / el 20 de agosto de 2026' (en uno o dos renglones).
VERSION_ESTATAL_RE = re.compile(
    r"[ÚU]ltima\s+reforma\s+publicada\b.{0,120}?(\d{1,2})\s+de\s+(" + "|".join(MESES)
    + r")\s+(?:de|del)\s+(\d{4})", re.IGNORECASE | re.DOTALL)
# Las que no la traen en la portada cierran con una tabla de los decretos que las
# reformaron ('TABLA DE REFORMAS Y ADICIONES', Jalisco), cada uno con su fecha de
# publicación abreviada: '…del Código Civil del Estado de Jalisco.- Jun. 18 de 2026'.
TABLA_REFORMAS_RE = re.compile(r"^TABLA DE REFORMAS(?: Y ADICIONES)?\s*$", re.MULTILINE)
_MES_CORTO = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7,
              "ago": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dic": 12}
FECHA_TABLA_RE = re.compile(
    r"\b(" + "|".join(sorted(_MES_CORTO, key=len, reverse=True)) +
    r")\.?\s*(\d{1,2})\s*(?:de|del)\s+(\d{4})", re.IGNORECASE)
PAGINAS_TABLA = 60
# Las de Querétaro abren con su 'Ficha Genealógica': la versión primigenia y el
# historial de cambios, cada uno con su fecha de publicación (dd/mm/aaaa),
# hasta 'Todas las fechas de la tabla son expresadas en el formato dd/mm/aaaa'.
FICHA_RE = re.compile(r"Ficha\s+Geneal[óo]gica")
FIN_FICHA_RE = re.compile(r"Todas\s+las\s+fechas\s+de\s+la\s+tabla")
PAGINAS_FICHA = 15


def _fecha_ficha(pdf) -> date | None:
    """La fecha más reciente de la ficha genealógica de la portada."""
    texto = ""
    for page in pdf.pages[:PAGINAS_FICHA]:
        texto += (page.extract_text() or "") + "\n"
        fin = FIN_FICHA_RE.search(texto)
        if fin:
            fechas = []
            for d, m, a in re.findall(r"\b(\d{2})/(\d{2})/(\d{4})\b", texto[:fin.start()]):
                try:
                    fechas.append(date(int(a), int(m), int(d)))
                except ValueError:
                    continue
            return max(fechas) if fechas else None
    return None


def _fecha_tabla_reformas(pdf) -> date | None:
    """La publicación más reciente de la tabla de reformas al final del PDF."""
    finales = []
    for page in reversed(pdf.pages[-PAGINAS_TABLA:]):
        finales.insert(0, page.extract_text() or "")
        texto = "\n".join(finales)
        m = TABLA_REFORMAS_RE.search(texto)
        if m:
            fechas = []
            for mes, dia, anio in FECHA_TABLA_RE.findall(texto[m.end():]):
                try:
                    fechas.append(date(int(anio), _MES_CORTO[mes.lower()], int(dia)))
                except ValueError:
                    continue
            return max(fechas) if fechas else None
    return None


def fecha_version(pdf_path: str, doc: Documento | None = None) -> date | None:
    """Fecha de la última reforma incorporada al PDF = versión del snapshot."""
    with pdfplumber.open(pdf_path) as pdf:
        head = pdf.pages[0].extract_text() or ""
        m = VERSION_RE.search(head) or NUEVO_RE.search(head)
        if m:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        m = VERSION_LARGA_RE.search(head)
        if m:
            return date(int(m.group(3)), MESES[m.group(2).lower()], int(m.group(1)))
        if doc is None or not doc.medio:
            return None
        # Ley estatal: su portada o su tabla de reformas.
        m = VERSION_ESTATAL_RE.search(head)
        if m:
            return date(int(m.group(3)), MESES[m.group(2).lower()], int(m.group(1)))
        if FICHA_RE.search(head):
            return _fecha_ficha(pdf)
        return _fecha_tabla_reformas(pdf)


# Otro artículo del decreto que expidió la ley ('ARTÍCULO SEGUNDO.- ……….',
# 'ARTÍCULOS TERCERO A OCTAVO. ………'): los de la ley llevan número, los del
# decreto ordinal en palabra. Tras el último artículo de la ley ya no es articulado.
ARTICULO_DECRETO_RE = re.compile(
    r"^[ \t]*ART[ÍI]CULOS?\s+(?:PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO|S[ÉE]PTIMO|"
    r"OCTAVO|NOVENO|D[ÉE]CIMO|[ÚU]NICO)\b", re.MULTILINE)
# En las leyes estatales, 'VER ARTICULO SEGUNDO TRANSITORIO DEL DECRETO…' es una
# cita partida por el renglón (notas del editor en la CDMX), no otro artículo
# del decreto.
ARTICULO_DECRETO_ESTATAL_RE = re.compile(ARTICULO_DECRETO_RE.pattern + r"(?!\s+TRANSITORIO)",
                                         re.MULTILINE)
# Capítulo con la errata 'CÁPITULO' (Código Civil de la CDMX).
CAPITULO_ESTATAL_RE = re.compile(r"^C[AÁ]P" + CAPITULO_RE.pattern[4:])


def _solo_articulado(texto: str, estatal: bool = False) -> str:
    """Recorta antes de los Transitorios (todo lo posterior no es articulado vigente)."""
    m = TRANSITORIOS_RE.search(texto)
    if m:
        texto = texto[: m.start()]
    primero = next((x for x in re.finditer(r"^.*$", texto, re.MULTILINE)
                    if ARTICULO_RE.match(x.group().strip())), None)
    if primero:
        d = (ARTICULO_DECRETO_ESTATAL_RE if estatal else ARTICULO_DECRETO_RE).search(
            texto, primero.end())
        if d:
            texto = _sin_rotulo_final(texto[: d.start()])
    return texto


def _sin_rotulo_final(texto: str) -> str:
    """Quita los renglones finales que solo son el rótulo en mayúsculas del
    artículo del decreto que sigue ('DISPOSICIONES DE VIGENCIA TEMPORAL DE LA
    LEY DEL IMPUESTO SOBRE LA' / 'RENTA', antes del 'ARTÍCULO NOVENO')."""
    lineas = texto.rstrip().split("\n")
    while lineas:
        s = lineas[-1].strip()
        letras = [c for c in s if c.isalpha()]
        if not s:
            lineas.pop()
        elif (letras and all(c.isupper() for c in letras) and s[-1] not in ".;:)"
              and not ARTICULO_RE.match(s) and not re.fullmatch(r"[IVXLCDM]+\.?", s)):
            lineas.pop()
        else:
            break
    return "\n".join(lineas) + "\n"


# Los epígrafes de las leyes estatales ('De quiénes pueden solicitar el registro
# y de la calificación registral', 'Juicio para la protección de los derechos
# político-electorales del Ciudadano') caben en un renglón corto y no llevan
# coma; el final de un párrafo sin punto ('En este último caso, declarará
# también improcedente la solicitud de divorcio') sí suele llevarla.
EPIGRAFE_MAX_ESTATAL = 80


def es_rotulo_corto(s: str, maximo: int = EPIGRAFE_MAX_ESTATAL) -> bool:
    return len(s) <= maximo and "," not in s


def parse(pdf_path: str, doc: Documento) -> list[Unidad]:
    """Parsea el PDF de una ley/código/reglamento y devuelve sus unidades. En
    una ley estatal, cada unidad lleva los cortes de párrafo que dice la
    geometría del PDF (los usa `normalize_body`)."""
    cortes = None
    if doc.medio:
        texto, cortes = texto_y_cortes(pdf_path, doc)
    else:
        texto = texto_limpio(pdf_path, doc)
    unidades = parse_texto(texto, huecos=doc.huecos, estatal=bool(doc.medio),
                           epigrafe_max=EPIGRAFE_MAX_ESTATAL if doc.medio else None,
                           notas=re.compile(doc.notas) if doc.notas else None,
                           notas_previas=re.compile(doc.notas_previas) if doc.notas_previas else None)
    for u in unidades:
        u.cortes = cortes
    return unidades


NIVELES = ("titulo", "capitulo", "seccion", "epigrafe")


_ORDINALES_ART = ("PRIMERO", "SEGUNDO", "TERCERO", "CUARTO", "QUINTO", "SEXTO",
                  "S[ÉE]PTIMO", "OCTAVO", "NOVENO", "D[ÉE]CIMO")
_ART_ORDINAL_RE = re.compile(
    rf"^([ \t]*)ART[ÍI]CULO\s+({'|'.join(_ORDINALES_ART)})\b(?=\s*\.?-)", re.MULTILINE)


_FIRMA_CONGRESO_RE = re.compile(r"^.*\b[DS]\. ?[PS]\.-.*$", re.MULTILINE)


def _articulos_ordinales(texto: str) -> str:
    """Leyes breves expedidas como decreto cuyos artículos van en ordinal en
    palabra ('ARTICULO PRIMERO.- …'): si el texto no tiene ningún artículo con
    número, esos renglones se numeran ('Artículo 1.- …') antes de segmentar. El
    texto del artículo no cambia, solo el rótulo."""
    antes = TRANSITORIOS_RE.search(texto)
    cuerpo, resto = (texto[: antes.start()], texto[antes.start():]) if antes else (texto, "")
    if any(ARTICULO_RE.match(ln.strip()) for ln in cuerpo.splitlines()):
        return texto

    def num(m: re.Match) -> str:
        palabra = m.group(2).upper().replace("É", "E")
        i = next(k for k, o in enumerate(_ORDINALES_ART, 1)
                 if re.fullmatch(o.replace("[ÉE]", "E"), palabra))
        return f"{m.group(1)}Artículo {i}"
    # Las firmas del Congreso ('…, D. P.- …, S. P.- …Rúbricas."') y la fórmula de
    # promulgación que siguen al último artículo no son del artículo.
    firma = _FIRMA_CONGRESO_RE.search(cuerpo)
    if firma:
        cuerpo = cuerpo[: firma.start()]
    return _ART_ORDINAL_RE.sub(num, cuerpo) + resto


# Tras el número, una cita sigue con minúscula ('Artículo 89 de la Constitución'):
# un salto en la numeración nunca se acepta sobre una línea así.
_CITA_TRAS_NUMERO_RE = re.compile(r"^\s*[a-záéíóúñ]")


def _ultima_aparicion(lineas: list[str], art: re.Pattern = ARTICULO_RE) -> dict[int, int]:
    """Número de artículo (sin sufijo) → último renglón donde abre un artículo."""
    ult: dict[int, int] = {}
    for i, raw in enumerate(lineas):
        am = art.match(raw.strip())
        if am and not (am.group(2) or am.group(3) or am.group(4)):
            ult[int(am.group(1).replace(",", ""))] = i
    return ult


MAX_RENGLONES_NOTA = 4
MAX_RENGLONES_NOTA_EDITOR = 8     # la nota del editor ('N. DE E. …') es más larga


def _parentesis_cerrados(texto: str) -> bool:
    return texto.count("(") <= texto.count(")")


_NOTA_EDITOR_RE = re.compile(r"N\.\s?DE\s?E\.")


_NOTA_ENCABEZADO_RE = re.compile(
    r"(?:Cap[íi]tulos?|T[íi]tulos?|Secci[óo]n(?:es)?|Libros?)\s+"
    r"(?:adicionad|reformad|derogad|reubicad|recorrid|aclarad)[oa]s?\b", re.IGNORECASE)


def _nota_abierta(nota: str) -> bool:
    """¿La nota sigue en el renglón siguiente? Si no cerró su paréntesis o, la
    nota del editor ('N. DE E. EN RELACIÓN CON …', sin paréntesis), si no cerró
    la oración."""
    return (not _parentesis_cerrados(nota)
            or (bool(_NOTA_EDITOR_RE.match(nota)) and not nota.rstrip().endswith(".")))


def _notas_al_final(u: Unidad | None, notas_previas: re.Pattern | None) -> list[str]:
    """Quita del final del cuerpo de `u` los renglones de nota que anotan al
    artículo siguiente y los devuelve en orden. Si el cuerpo quedaría vacío
    (el artículo solo es su nota: '(DEROGADO, G.O. …)'), se queda con ellas."""
    if u is None or notas_previas is None:
        return []
    lineas = u.cuerpo.rstrip("\n").split("\n")
    j, grupos, inicios = len(lineas), [], []
    while j > 1:
        if not lineas[j - 1].strip():
            j -= 1
            continue
        # La nota puede ocupar varios renglones: abre en uno que casa con la
        # regex y cierra su paréntesis justo en el último (no antes).
        # La nota del editor ('N. DE E. …') no lleva paréntesis: ocupa desde su
        # renglón inicial hasta uno que cierra la oración.
        def cierra(k: int) -> bool:
            if _NOTA_EDITOR_RE.match(lineas[k].strip()):
                return (lineas[j - 1].rstrip().endswith(".")
                        and not any(lineas[m].rstrip().endswith(".") for m in range(k, j - 1)))
            return (_parentesis_cerrados("\n".join(lineas[k:j]))
                    and (k == j - 1 or not _parentesis_cerrados("\n".join(lineas[k:j - 1]))))
        k = next((k for k in range(j - 1, max(0, j - 1 - MAX_RENGLONES_NOTA_EDITOR), -1)
                  if notas_previas.match(lineas[k].strip())
                  and (j - k <= MAX_RENGLONES_NOTA
                       or _NOTA_EDITOR_RE.match(lineas[k].strip()))
                  and cierra(k)), None)
        if k is None or k == 0:
            break
        grupos.insert(0, "\n".join(ln.strip() for ln in lineas[k:j]))
        inicios.insert(0, k)
        j = k
    notas = grupos
    if not notas:
        return []
    m = ARTICULO_ESTATAL_RE.match(lineas[0].strip())
    queda = "\n".join(lineas[:j])
    primera = lineas[0].strip()[m.end():] if m else lineas[0]
    if not (primera.strip() or any(ln.strip() for ln in lineas[1:j])):
        # El artículo solo es sus notas: las suyas son las previas que ya se le
        # pusieron y la que seguía a su rótulo; las demás anotan al siguiente
        # ('ARTICULO 2448 G.- (DEROGADO …)' / '(ADICIONADO …)' del 2448 H).
        propias = getattr(u, "n_previas", 0) + 1
        if len(grupos) <= propias:
            return []
        j = inicios[propias]
        queda, notas = "\n".join(lineas[:j]), grupos[propias:]
    u.cuerpo = queda + "\n"
    return notas


def _notas_antes(lineas: list[str], notas_previas: re.Pattern | None) -> list[str]:
    """Las notas previas pegadas al primer artículo (lo anterior a él no es de
    ningún artículo y se descarta, pero su nota sí es suya)."""
    if notas_previas is None:
        return []
    u = Unidad(numero=0)
    u.cuerpo = "\n".join(["Artículo 0.", "-", *lineas[-(MAX_RENGLONES_NOTA * 3):]])
    return _notas_al_final(u, notas_previas)


_EPIGRAFE_MARGINAL_MAX = 100
_EPIGRAFE_ENVUELTO_DESDE = 72        # largo de renglón desde el que el rótulo envuelve


def _epigrafes_marginales(lineas: list[str], ART: re.Pattern,
                          notas: re.Pattern | None) -> tuple[list[str], dict[int, str]]:
    """Ley estatal cuyo PDF pone en el renglón del rótulo el epígrafe marginal
    del artículo ('Artículo 1. Sujetos obligados', y el texto en el renglón
    siguiente; el epígrafe puede envolver a un segundo renglón). Solo si casi
    todos sus rótulos son así (la ley entera, no un artículo suelto). Devuelve
    las líneas con el rótulo solo y, por índice de la línea nueva, su epígrafe,
    que va al contexto de la unidad y no a su cuerpo."""
    def candidato(ln: str):
        m = ART.match(ln.strip())
        if not m:
            return None
        resto = ln.strip()[m.end():].strip()
        if (resto and resto[0].isupper() and len(resto) <= _EPIGRAFE_MARGINAL_MAX
                and resto[-1] not in ".;:,)"):
            return m, resto
        return m, None

    todos = [candidato(ln) for ln in lineas]

    def sigue_mayuscula(i: int) -> bool:
        sig = next((x.strip() for x in lineas[i + 1:i + 3] if x.strip()), "")
        return sig[:1].isupper() or sig[:1] == "("

    def texto_en_mayusculas(i: int) -> bool:
        """El renglón del rótulo y el siguiente van ambos en MAYÚSCULAS: es un
        texto escrito todo en mayúsculas (Código Penal de Nuevo León) cuyo primer
        renglón no cierra con puntuación, no un epígrafe seguido de su texto."""
        resto = lineas[i].strip()[todos[i][0].end():].strip()
        sig = next((x.strip() for x in lineas[i + 1:i + 3] if x.strip()), "")
        return resto.isupper() and sig.isupper() and not (notas is not None and notas.match(sig))

    # Solo cuentan los rótulos cortos: un primer renglón de texto que envuelve
    # llega al margen, y el que cierra sin puntuación es lo normal en cualquier ley.
    rotulos = [i for i, c in enumerate(todos) if c]
    marginales = [i for i in rotulos if todos[i][1] and len(lineas[i].strip()) < _EPIGRAFE_ENVUELTO_DESDE
                  and sigue_mayuscula(i) and not texto_en_mayusculas(i)]
    if len(rotulos) < 10 or len(marginales) < 0.6 * len(rotulos):
        return lineas, {}
    salida: list[str] = []
    epigrafes: dict[int, str] = {}
    i = 0
    while i < len(lineas):
        c = todos[i]
        if not (c and c[1]) or texto_en_mayusculas(i):
            salida.append(lineas[i])
            i += 1
            continue
        m, resto = c
        ln = lineas[i].strip()
        epi, j = resto, i + 1
        k = i + 1
        while k < len(lineas) and not lineas[k].strip():
            k += 1
        sig = lineas[k].strip() if k < len(lineas) else ""
        # El epígrafe envuelve a un segundo renglón corto y sin puntuación
        # interior (el rótulo llega casi al margen).
        if (len(ln) >= _EPIGRAFE_ENVUELTO_DESDE and sig and len(sig) <= 50
                and not re.search(r"[,:;]", sig) and not ART.match(sig)
                and not re.match(r"(?:[IVXLCDM]+|[a-zñ]|\d+)[.)]\s", sig)
                and not (notas is not None and notas.match(sig))):
            epi, j = f"{resto} {sig}", k + 1
        elif not (sig[:1].isupper() or sig[:1] == "("):
            # Sin segundo renglón de epígrafe y con texto que sigue en minúscula:
            # el rótulo es el primer renglón de un texto que envuelve.
            salida.append(lineas[i])
            i += 1
            continue
        epigrafes[len(salida)] = epi
        previo = next((x.strip() for x in reversed(salida) if x.strip()), "")
        salida.append(lineas[i].strip()[:m.end()])
        i = j
        # La misma nota de reforma antes del rótulo y tras el epígrafe es una sola
        # (la de antes pasa a ser la primera línea del artículo): el epígrafe,
        # que va al contexto, no deja texto entre las dos copias.
        if (notas is not None and i < len(lineas) and previo and lineas[i].strip() == previo
                and notas.match(previo)):
            i += 1
    return salida, epigrafes


def parse_texto(clean_text: str, start: int = 1, *, huecos: bool = False,
                notas: re.Pattern | None = None,
                notas_previas: re.Pattern | None = None,
                epigrafe_max: int | None = None, estatal: bool = False) -> list[Unidad]:
    """Segmenta texto ya limpio en unidades. Separado para poder probarlo sin PDF.

    La numeración se exige continua (así se descartan las citas a otros
    artículos al inicio de renglón). Con `huecos` (PDF que omite los artículos
    derogados, como varios estatales) se acepta saltar a un número mayor solo
    si ninguno de los que faltan vuelve a aparecer como artículo en el resto
    del texto: si apareciera, el salto sería una cita.

    Las fechas de reforma salen de las notas 'DOF DD-MM-AAAA' y, en una fuente
    estatal, de los renglones que casan con `notas`.

    Con `notas_previas`, las notas de reforma que el PDF pone justo antes de un
    artículo ('(REFORMADO, G.O. …)') abren ese artículo en vez de cerrar el
    anterior: quedan como su primer párrafo, en el mismo orden que en el PDF.

    `estatal` lee además lo que escriben los PDF estatales y no los de la Cámara
    (rótulos de `ARTICULO_ESTATAL_RE`, 'CÁPITULO', notas que siguen en otro
    renglón, fracciones 'XIII Bis.' que no son epígrafe…). Sin él, la lectura de
    las leyes federales es la de siempre.

    `epigrafe_max` limita el largo de un rótulo sin palabra clave: en las
    fuentes cuyos párrafos no siempre cierran con punto, el último renglón de un
    artículo ('…se atenderá el principio de paridad') parecería un epígrafe del
    siguiente y su texto se perdería.
    """
    ART = ARTICULO_ESTATAL_RE if estatal else ARTICULO_RE
    texto = _solo_articulado(_articulos_ordinales(clean_text), estatal)
    if estatal:
        # El PDF escribe a veces la 'I' por el 1 en el número ('ARTÍCULO 22I BIS').
        texto = re.sub(r"(?m)^((?:ART[ÍI]CULO|Art[íi]culo)\s+\d+)I(?=\s+(?i:bis|ter|qu[aá]ter)\b)",
                       r"\g<1>1", texto)
    if estatal:
        # Glifos sueltos que el PDF deja en un renglón ('|', '.') y el título de
        # estructura que comparte renglón con el final del artículo ('…menor de
        # edad. TÍTULO SEPTIMO'): no son texto del artículo.
        texto = re.sub(r"(?m)^[ \t]*[|.][ \t]*\n", "", texto)
        texto = re.sub(rf"(?m)^(.*\S[.;:])[ \t]+(T[ÍI]TULO\s+(?:{_ORDINAL_MAY}))[ \t]*$",
                       r"\1\n\2", texto)
    lineas = texto.splitlines()
    marginales: dict[int, str] = {}
    if estatal:
        lineas, marginales = _epigrafes_marginales(lineas, ART, notas)
    ultima = _ultima_aparicion(lineas, ART) if huecos else {}

    def nombre_suelto(s: str, continuacion: bool = False) -> bool:
        # Una nota de reforma de la ley estatal ('FRACCIÓN ADICIONADA G.O. CDMX
        # 27/08/25') no es el rótulo de un encabezado aunque vaya en mayúsculas.
        if estatal and notas is not None and notas.match(s):
            return False
        return _es_nombre_suelto(s, continuacion, estatal)

    def salto_valido(numero: int, i: int, resto: str) -> bool:
        """¿Se puede saltar de `esperado` a `numero` en el renglón `i`?"""
        if not huecos or numero <= esperado or _CITA_TRAS_NUMERO_RE.match(resto):
            return False
        return all(ultima.get(k, -1) < i for k in range(esperado, numero))

    unidades: list[Unidad] = []
    actual: Unidad | None = None
    # Jerarquía vigente: 'TÍTULO IV. DE LAS PERSONAS FÍSICAS', etc. El epígrafe
    # es el nivel más bajo: un apartado o un rótulo sin palabra clave ('Del
    # Consentimiento' en el Código Civil).
    jer = dict.fromkeys(NIVELES, "")
    ultimo_nivel = ""
    # (nivel, encabezado, líneas-nombre acumuladas): un encabezado espera su
    # nombre en la(s) línea(s) siguiente(s).
    pendiente: tuple[str, str, list[str]] | None = None
    esperado = start                 # número de artículo esperado (valida la secuencia)
    # Dentro de un bloque de encabezado que desemboca en el siguiente artículo,
    # sus nombres, notas ('Capítulo adicionado DOF …') y la marca '(Se deroga)'
    # de un capítulo derogado son de la estructura, no del artículo anterior.
    en_bloque = False
    nota_previa: str | bool = False
    previa = ""                      # última línea no vacía

    abiertos: set[tuple] = set()
    # Notas previas dentro de un bloque de encabezado: son del artículo que lo cierra.
    previas_bloque: list[str] = []

    def siguiente_abre(i: int) -> bool:
        """¿El siguiente renglón no vacío tras `i` abre un artículo aceptable?"""
        j = next((j for j in range(i + 1, len(lineas)) if lineas[j].strip()), None)
        return j is not None and abre_articulo(lineas[j].strip(), j)

    def entra_bloque() -> None:
        """Empieza un bloque de encabezado: las notas previas que cerraban el
        artículo anterior anotan ese encabezado (su denominación, el capítulo
        adicionado), no a ningún artículo; como las notas 'Capítulo adicionado
        DOF …' de la Cámara, se quedan en la estructura."""
        _notas_al_final(actual, notas_previas)
        previas_bloque.clear()
        if estatal and notas is not None and actual is not None:
            # 'Capitulo Adicionado G.O. CDMX 23/08/24' justo antes del siguiente
            # encabezado anota un encabezado, no es parte del artículo.
            lineas_a = actual.cuerpo.rstrip("\n").split("\n")
            while (len(lineas_a) > 1 and _NOTA_ENCABEZADO_RE.match(lineas_a[-1].strip())
                   and notas.match(lineas_a[-1].strip())):
                lineas_a.pop()
                while len(lineas_a) > 1 and not lineas_a[-1].strip():
                    lineas_a.pop()
            actual.cuerpo = "\n".join(lineas_a) + "\n"

    def es_nota_bloque(s: str) -> bool:
        return _es_nota_de_bloque(s) or (notas is not None and bool(notas.match(s)))

    def flush(u: Unidad | None) -> None:
        if u is not None:
            u.cuerpo = u.cuerpo.strip()
            u.fechas_reforma = fechas_reforma_en(u.cuerpo)
            if notas is not None:
                u.fechas_reforma = sorted(set(u.fechas_reforma) | set(
                    fechas_en_notas(u.cuerpo, notas)))
            primer = u.cuerpo.split("\n", 1)[0]
            u.derogado = bool(DEROGADO_RE.search(primer))
            unidades.append(u)

    def fijar(nivel: str, valor: str) -> None:
        nonlocal ultimo_nivel
        ultimo_nivel = nivel
        jer[nivel] = valor
        for inferior in NIVELES[NIVELES.index(nivel) + 1:]:
            jer[inferior] = ""                  # un nivel nuevo resetea los inferiores

    def ampliar_nombre(linea: str) -> None:
        """Suma una línea al nombre del último encabezado (nombre envuelto, o
        un subencabezado sin palabra clave tras un salto de página)."""
        if ultimo_nivel:
            v = jer[ultimo_nivel]
            jer[ultimo_nivel] = f"{v}{' ' if '. ' in v or ultimo_nivel == 'epigrafe' else '. '}{linea}"

    def abre_articulo(s: str, i: int | None = None) -> bool:
        """¿`s` (renglón `i`) abre un artículo que la secuencia aceptaría ahora mismo?"""
        am = ART.match(s)
        if not am:
            return False
        numero, sufijo = int(am.group(1).replace(",", "")), bool(am.group(2) or am.group(3) or am.group(4))
        return ((numero == esperado and not sufijo)
                or (not sufijo and i is not None and salto_valido(numero, i, s[am.end():]))
                or (actual is not None and numero == actual.numero and sufijo))

    def desemboca_en_articulo(i: int, max_lineas: int = MAX_LINEAS_ENCABEZADO,
                              solo_estructura: bool = False) -> bool:
        """¿Hay un artículo aceptable en las líneas que siguen a `i`? Con
        `solo_estructura`, todas las intermedias deben ser encabezados, nombres o
        notas."""
        vistas = 0
        en_nota = False
        for j in range(i + 1, len(lineas)):
            s = lineas[j].strip()
            if not s:
                continue
            if abre_articulo(s, j):
                return True
            # El renglón que sigue a una nota sin cerrar es parte de la nota.
            sigue_nota = en_nota
            en_nota = estatal and (es_nota_bloque(s) or sigue_nota) and not s.endswith((".", ")"))
            if sigue_nota:
                continue
            if solo_estructura and not (
                    _es_encabezado(s) or es_nota_bloque(s) or nombre_suelto(s)
                    or nombre_suelto(s, continuacion=True)
                    or re.fullmatch(r"[IVXLCDM]+", s)):
                return False
            # Encabezados, notas y nombres entre corchetes no cuentan: un bloque
            # Libro/Título/Capítulo con sus notas de reforma e invalidez puede
            # pasar de MAX_LINEAS_ENCABEZADO renglones y aun así es estructura.
            if (_es_encabezado(s) or es_nota_bloque(s)
                    or (s.startswith("[") and len(s) < 150
                        and not re.match(r"\[\s*Art[ií]culo\b", s)
                        and not MARCA_FORMULA_RE.match(s))):
                continue
            vistas += 1
            if vistas >= max_lineas:
                return False
        return False

    def nota_y_articulo(i: int) -> bool:
        """¿Tras el renglón `i` van una o más notas de reforma y luego un artículo?"""
        j = next((j for j in range(i + 1, len(lineas)) if lineas[j].strip()), None)
        return (j is not None and es_nota_bloque(lineas[j].strip())
                and desemboca_en_articulo(i, max_lineas=3, solo_estructura=True))

    def nivel_de(s: str) -> str | None:
        if estatal and re.fullmatch(r"(?:T[íi]tulo|Cap[íi]tulo|Secci[óo]n|Libro)\s.*[^.]\.", s):
            s = s[:-1]                  # 'Título Séptimo Bis.' (Código Electoral de Jalisco)
        if (TITULO_RE.match(s) or LIBRO_RE.match(s) or PARTE_RE.match(s)) and (
                actual is None or len(s) < 35):
            return "titulo"
        if (CAPITULO_ESTATAL_RE if estatal else CAPITULO_RE).match(s) and (
                actual is None or len(s) < 30):
            return "capitulo"
        if SECCION_RE.match(s) and (actual is None or len(s) < 35):
            return "seccion"
        if APARTADO_RE.match(s):
            return "epigrafe"
        return None

    for i, raw in enumerate(lineas):
        line = raw.rstrip()
        stripped = line.strip()
        if (pendiente is not None or en_bloque) and MARCA_AGUA_RE.fullmatch(stripped):
            continue
        anterior, previa = previa, (stripped or previa)

        # ¿La línea anterior fue un encabezado esperando su nombre (línea siguiente)?
        if pendiente is not None:
            if not stripped:
                continue                                            # salta blancos entre número y nombre
            nivel, encabezado, partes = pendiente
            # Encabezado en MAYÚSCULAS (Cámara) → nombre en MAYÚSCULAS, una línea;
            # Title-case (normateca SAT) → nombre Title-case, hasta dos líneas
            # (los nombres largos envuelven: 'De las Facultades previstas en…').
            estricto = encabezado.isupper()
            # La nota que anota la denominación del encabezado y va entre su
            # número y su nombre ('CAPITULO CUARTO' / '(REFORMADA SU DENOMINACION,
            # P.O. …)' / 'Del Impuesto ….') es de la estructura, no del artículo.
            if (estatal and not partes and es_nota_bloque(stripped)
                    and "DENOMINACI" in stripped.upper()
                    and stripped.count("(") == stripped.count(")")
                    and desemboca_en_articulo(i, 4)):
                continue
            # Un nombre en MAYÚSCULAS bajo un encabezado en Title-case ('Sección XVI'
            # / 'MÁQUINAS Y APARATOS…') puede envolver en tres renglones.
            en_mayusculas = bool(partes) and all(
                p.isupper() for p in (*partes, stripped)) and not partes[-1].endswith((".", ";", ":"))
            acumulable = not partes or (
                not estricto and len(partes) < (MAX_LINEAS_NOMBRE if en_mayusculas else 2))
            if (acumulable and _es_nombre_encabezado(stripped, estricto=estricto, estatal=estatal)
                    and not (estatal and es_nota_bloque(stripped))):
                pendiente = (nivel, encabezado, partes + [stripped])
                continue
            # Muchas leyes de la Cámara ponen el encabezado en MAYÚSCULAS y el
            # nombre en caja normal ('CAPITULO IV' / 'Rescisión de las relaciones
            # de trabajo'), a veces envuelto en varias líneas. Sin la caja como
            # señal, la prueba es que el bloque desemboque en el siguiente
            # artículo: así no se confunde con texto del artículo anterior.
            # Un nombre entre corchetes ('[De la Integración … de las Entidades' /
            # 'Federativas, así como de los Ayuntamientos]') sigue hasta el ']'.
            corchete_abierto = bool(partes) and partes[0].startswith("[") and not any(
                "]" in p for p in partes)
            if corchete_abierto and len(partes) < MAX_LINEAS_NOMBRE and (
                    not stripped.endswith((".", ";", ":")) or stripped.endswith("]")) and (
                    "DOF" not in stripped) and not ART.match(stripped):
                pendiente = (nivel, encabezado, partes + [stripped])
                continue
            if estricto and len(partes) < MAX_LINEAS_NOMBRE and nombre_suelto(
                    stripped, continuacion=bool(partes)) and desemboca_en_articulo(i):
                pendiente = (nivel, encabezado, partes + [stripped])
                continue
            # Un rótulo de dos partes que cierra con punto ('De los contratos
            # preparatorios.- La promesa.') también es nombre si el artículo sigue
            # justo debajo; una oración ('Las personas morales deberán …') no.
            if (estatal and estricto and not partes and stripped.endswith(".") and ".- " in stripped
                    and nombre_suelto(stripped[:-1]) and siguiente_abre(i)):
                pendiente = (nivel, encabezado, [stripped])
                continue
            # Estatal: 'Capítulo IV' / 'De la financiación y del fomento.' — el
            # nombre en caja normal que cierra con punto, de un renglón y con el
            # artículo justo debajo.
            # El artículo puede ir tras una nota de reforma ('(ADICIONADO, P.O. …)'),
            # y el nombre envolver a un segundo renglón.
            if (estatal and len(partes) <= 1 and stripped.endswith(".")
                    and not stripped.endswith("..") and es_rotulo_corto(stripped)
                    and _es_nombre_encabezado(stripped[:-1], False, True)
                    and not stripped.isupper() and not es_nota_bloque(stripped)
                    and ((not estricto and siguiente_abre(i)) or nota_y_articulo(i))):
                pendiente = (nivel, encabezado, [*partes, stripped])
                continue
            pendiente = None
            nombre = " ".join(partes)
            # 'TÍTULO IV. DE LAS PERSONAS FÍSICAS'; sin nombre: solo número.
            fijar(nivel, f"{encabezado}. {nombre}" if nombre else encabezado)
            # no 'continue': esta línea puede ser un artículo u otro encabezado

        nivel = nivel_de(stripped)
        # 'Sección XVI' en Title-case dentro de una tabla (LIGIE) que no desemboca
        # en un artículo no es estructura: es texto del artículo en curso. Sacarlo
        # dejaría un hueco en medio de un párrafo.
        if (nivel and actual is not None and not en_bloque and not stripped.isupper()
                and not desemboca_en_articulo(i)):
            nivel = None
        if nivel:
            pendiente = (nivel, stripped, [])
            if en_bloque:
                previas_bloque.clear()          # anotaban la estructura de arriba
            elif actual is not None and desemboca_en_articulo(i):
                entra_bloque()
                en_bloque = True
            continue

        if actual is not None and not en_bloque and stripped and (
                # Subencabezado sin palabra clave: un numeral solo ('III' en la
                # Ley Aduanera) o un rótulo tras el final del artículo ('Del
                # Consentimiento', Código Civil), seguidos solo de estructura
                # hasta el siguiente artículo.
                (re.fullmatch(r"[IVXLCDM]+", stripped)
                 and desemboca_en_articulo(i, MAX_LINEAS_ENCABEZADO, solo_estructura=True))
                or (nombre_suelto(stripped) and not stripped.endswith(",")
                    # 'Derogado' tras la última fracción es texto del artículo.
                    and not (estatal and MARCA_DEROGADO_RE.fullmatch(stripped))
                    and (epigrafe_max is None or es_rotulo_corto(stripped, epigrafe_max))
                    and (anterior.endswith((".", ";", ":")) or es_nota_bloque(anterior))
                    # La segunda línea de una nota envuelta ('DE 2024)') no es un rótulo.
                    and not (estatal and es_nota_bloque(anterior) and _nota_abierta(anterior))
                    and desemboca_en_articulo(i, MAX_LINEAS_ENCABEZADO, solo_estructura=True))):
            fijar("epigrafe", stripped)
            entra_bloque()
            en_bloque = True
            continue

        if (estatal and en_bloque and nota_previa and stripped
                and not nota_previa.endswith((".", ")"))
                and not abre_articulo(stripped, i)):
            nota_previa = stripped      # la nota sigue: 'ARTÍCULO 14 DE LAS DISPOSICIONES …'
            continue
        if (estatal and en_bloque and previas_bloque and stripped
                and _nota_abierta(previas_bloque[-1]) and not abre_articulo(stripped, i)):
            previas_bloque[-1] += "\n" + stripped     # la nota del editor sigue
            continue
        if en_bloque and not ART.match(stripped):
            if not stripped:
                continue
            if previas_bloque and _nota_abierta(previas_bloque[-1]):
                previas_bloque[-1] += "\n" + stripped     # la nota previa sigue
                continue
            if notas_previas is not None and notas_previas.match(stripped):
                previas_bloque.append(stripped)
                continue
            if es_nota_bloque(stripped):
                nota_previa = stripped
                continue
            if nota_previa and (stripped[:1].islower()
                                or not nota_previa.endswith((".", ")"))):
                nota_previa = stripped                      # la nota sigue en otra línea
                continue
            nota_previa = False
            # Estatal: el nombre en MAYÚSCULAS que envuelve en varios renglones y
            # cierra con punto ('…O VALES DE CANJE.') sigue siendo el nombre.
            nombre_mayusculas = (
                estatal and ultimo_nivel and stripped.isupper()
                and not anterior.endswith((".", ";", ":")) and anterior.isupper()
                and _es_nombre_encabezado(stripped, True, True)
                and desemboca_en_articulo(i))
            if (nombre_suelto(stripped) or nombre_suelto(stripped, continuacion=True)
                    or nombre_mayusculas
                    or re.fullmatch(r"[IVXLCDM]+", stripped)):
                ampliar_nombre(stripped)
                previas_bloque.clear()
                continue

        if estatal and actual is not None and not en_bloque and not ART.match(stripped):
            # '20 A. El procedimiento…': el PDF omite la palabra 'Artículo' en la
            # variante con letra del artículo en curso.
            sm = re.match(r"(\d+) ([A-ZÑ])\.\s+\S", stripped)
            if (sm and int(sm.group(1)) == actual.numero and not actual.letra
                    and not actual.ordinal and not actual.guion_num
                    and (actual.numero, sm.group(2), "", "", "", "") not in abiertos):
                stripped = line = "Artículo " + stripped
        am = ART.match(stripped)
        if am:
            numero = int(am.group(1).replace(",", ""))
            letra = (am.group(2) or "").upper()
            guion_num = am.group(3) or ""         # numeral con guion: "58-1", "195-L-4"
            ordinal = (am.group(4) or "").title()
            ord_num = (am.group(5) or "").title()   # numeral tras el ordinal: "Bis 1", "Bis Uno"
            sub_letra = am.group(6) or (am.group(7) if ART.groups >= 7 else "") or ""  # letra tras el numeral: "Bis 35 A", "Bis-A"
            # 'Artículo 176-Bis. 3.' es el 176 Bis 3 si el 176 Bis ya se abrió
            # (Código Penal de Jalisco); si no, 'Artículo 459 Ter. 1.' es el 459
            # Ter y '1.' su primer párrafo numerado (Código Electoral de Jalisco).
            if (ord_num and "." in stripped[am.end(4):am.start(5)]
                    and (numero, letra, guion_num, ordinal, "", "") not in abiertos):
                ord_num = sub_letra = ""
                line = stripped[:am.end(4)] + "\n" + stripped[am.end(4):].lstrip(" .")
                am = ART.match(line)
            tiene_sufijo = bool(letra or guion_num or ordinal)
            # Aceptar solo el siguiente esperado (bare) o una variante del actual.
            # Así se descartan las citas "Artículo 89 de la Constitución".
            es_siguiente = not tiene_sufijo and (
                numero == esperado or salto_valido(numero, i, stripped[am.end():]))
            es_variante = (actual is not None and numero == actual.numero
                           and tiene_sufijo)
            # Un 'Bis' que el PDF pone ANTES de su artículo base ('ARTÍCULO 855
            # BIS.-' y luego el 855, CDMX): es otro artículo, no una cita.
            if (estatal and not es_variante and ordinal and not letra and not guion_num
                    and numero == esperado and "BIS" in stripped[:am.end()].upper()
                    and any((m2 := ART.match(ln.strip())) and not m2.group(2)
                            and not m2.group(3) and not m2.group(4)
                            and int(m2.group(1).replace(",", "")) == numero
                            for ln in lineas[i + 1:i + 120])):
                es_variante = True
            # Una cita al inicio de renglón ("Artículo 46 Bis 3 de la presente
            # Ley") repite una clave ya abierta: no es un artículo nuevo.
            clave = (numero, letra, guion_num, ordinal, ord_num, sub_letra)
            if es_variante and clave in abiertos:
                es_variante = False
            if es_siguiente or es_variante:
                abiertos.add(clave)
                en_bloque = nota_previa = False
                previas = (_notas_al_final(actual, notas_previas) if actual is not None
                           else _notas_antes(lineas[:i], notas_previas)) + previas_bloque
                previas_bloque = []
                flush(actual)
                actual = Unidad(
                    numero=numero, letra=letra, guion_num=guion_num, ordinal=ordinal,
                    ord_num=ord_num,
                    sub_letra=sub_letra, titulo=jer["titulo"], capitulo=jer["capitulo"],
                    seccion=jer["seccion"], epigrafe=jer["epigrafe"],
                )
                actual.cuerpo = line + "\n"
                # Rótulo estatal con ordinal y sin la 'o' ('ARTÍCULO 5 BIS').
                actual.sin_o = bool(
                    estatal and ordinal and numero <= 9
                    and not re.match(r"\s*(?:/[oº°]|[oº°])", line[am.end(1):]))
                if i in marginales:
                    actual.epigrafe = marginales[i]
                if previas:
                    # Encabezado, las notas (cada una su párrafo) y el texto que
                    # seguía al encabezado en su renglón: el orden del PDF.
                    actual.cuerpo = (line[:am.end()].rstrip() + "\n\n" + "\n\n".join(previas)
                                     + "\n\n" + line[am.end():] + "\n")
                    actual.n_previas = len(previas)
                if es_siguiente:
                    esperado = numero + 1
                continue

        if actual is not None:
            actual.cuerpo += line + "\n"

    flush(actual)
    return unidades
