"""Normaliza el cuerpo crudo de una unidad a párrafos limpios.

Port de `constitucion-extractor/extractor/normalize.py`. El PDF entrega saltos
de línea "visuales" (no de párrafo); se re-unen y se separan en bloques lógicos
(fracciones, incisos, notas de reforma) para que un `git diff` de una reforma
muestre solo el párrafo cambiado.
"""
from __future__ import annotations

import re

from .parsers.articulado import ARTICULO_RE, _nota_abierta

# Inicio de una nota de reforma al pie ("... DOF DD-MM-YYYY"), posiblemente
# envuelta en varias líneas por el PDF.
# Una nota empieza con el elemento reformado (Párrafo/Fracción/Artículo…) o
# directamente con el verbo ("Reformado DOF…", "Derogada DOF…", "Adicionado…").
# Las formas verbales se listan completas (con género/plural) para que el \b
# cierre bien; un stem como "Derogad\b" NO casaría con "Derogado".
REFORM_NOTE_START_RE = re.compile(
    r"^(?:Párrafo|Fracción|Inciso|Apartado|Artículo|Numeral|Sección|Cap[íi]tulo|"
    r"T[íi]tulo|Reforma|Denominación|Fe de erratas|Fe de|"
    r"Reformad[oa]s?|Adicionad[oa]s?|Derogad[oa]s?|Recorrid[oa]s?|Reubicad[oa]s?|"
    r"Abrogad[oa]s?|Renumerad[oa]s?)\b.*DOF\s+\d{2}-\d{2}-\d{4}",
)
NOTE_COMPLETE_RE = re.compile(r"\d{2}-\d{2}-\d{4}[.)]?$")
MAX_NOTE_CONT_LINES = 4
# Las notas estatales cierran con su paréntesis; las del editor ('(las porciones
# normativas resaltadas fueron reformadas mediante Decreto…)') ocupan más renglones.
MAX_NOTA_ESTATAL_LINES = 8

# Nota de reforma de las compilaciones de la normateca del SAT (RISAT):
# "(DOF 21 de diciembre de 2021)" en línea propia, siempre completa.
NOTA_NORMATECA_RE = re.compile(
    r"^\(DOF\s+\d{1,2}\s+de\s+[a-zá-ú]+\s+de\s+\d{4}\)$", re.IGNORECASE)

# Marcadores de fracción / inciso / apartado: "I.", "a)", "1.", "A. ".
STRUCT_MARKER_RE = re.compile(r"^(?:[IVXLCDM]+\.|[a-z]\)|\d+\.|[A-Z]\.\s)")
SENTENCE_END_RE = re.compile(r"[.:;]$")
# Un número o un romano con punto que abre el renglón no es un marcador si el
# renglón de arriba lo deja pendiente: '…lo dispuesto en el artículo' / '457.',
# '…a partir del 1 de enero de' / '2016.'. Tras una conjunción ('…en los
# artículos 2027 y' / '2028.') solo si el número va solo o le sigue una
# minúscula: '…anterior al delito y' / 'VIII.- Los que…' sí abre una fracción.
NUMERO_AL_INICIO_RE = re.compile(r"^(?:\d+|[IVXLCDM]+)\.")
NUMERO_SUELTO_RE = re.compile(r"^(?:\d+|[IVXLCDM]+)\.(?:$|\s+[a-záéíóúüñ])")
DEJA_PENDIENTE_RE = re.compile(
    r"\b(?:art[íi]culos?|fracci[oó]n|fracciones|p[áa]rrafos?|incisos?|numeral(?:es)?|"
    r"del?|al|en|entre|los|las|el|la)$", re.IGNORECASE)
CONJUNCION_FINAL_RE = re.compile(r"(?<![,;])\s[yoeua]$")
# '…conforme a lo establecido en los artículos 31, 149 o' / '172. La impugnación…':
# la lista de artículos o fracciones que cierra en conjunción sigue en su último número.
CITA_ABIERTA_RE = re.compile(
    r"\b(?:art[íi]culos|fracciones)\s+[\dIVXLC][\dIVXLC°ºo.,\s]*\s[yoeu]$", re.IGNORECASE)
# '0.75 metros de profundidad;' abre con un decimal, no con el marcador '0.'.
DECIMAL_AL_INICIO_RE = re.compile(r"^\d+\.\d")


# Párrafo que solo dice que el texto fue derogado: 'DEROGADO. P.O. 20 DE MAYO DE 2022.'
DEROGADO_SUELTO_RE = re.compile(r"DEROGAD[OA]\.\s+P\.\s?O\.\s+\d{1,2}\s+DE\s+[A-ZÁÉÍÓÚ]+\s+DE\s+\d{4}\.?")


def _numero_pendiente(anterior: str, s: str) -> bool:
    if not NUMERO_AL_INICIO_RE.match(s):
        return False
    return bool(DEJA_PENDIENTE_RE.search(anterior) or CITA_ABIERTA_RE.search(anterior)
                or (CONJUNCION_FINAL_RE.search(anterior) and NUMERO_SUELTO_RE.match(s)))


def _is_reform_note(line: str) -> bool:
    return bool(REFORM_NOTE_START_RE.match(line.strip()))


def _is_struct_marker(line: str) -> bool:
    s = line.strip()
    return bool(STRUCT_MARKER_RE.match(s)) and not DECIMAL_AL_INICIO_RE.match(s)


def _note_is_complete(note: str) -> bool:
    return bool(NOTE_COMPLETE_RE.search(note.strip()))


IMPORTE_SUELTO_RE = re.compile(r"\$?\s?\d[\d.,]*(?:\s+(?:cuotas?|veces))?")
TARIFA_FINAL_RE = re.compile(r"[A-ZÁÉÍÓÚÑ][^.;:,]{0,60}\$\s?\d[\d.,]*$")


def blocks_texto(blocks: list[str]) -> bool:
    """¿Hay ya algún párrafo que no sea una nota (en cursiva)?"""
    return any(not b.startswith("_") for b in blocks)


def normalize_body(body: str, heading_label: str, notas: re.Pattern | None = None,
                   rotulo: re.Pattern = ARTICULO_RE,
                   cortes: dict[tuple[str, str], bool] | None = None) -> str:
    """Devuelve el cuerpo de la unidad como párrafos, sin la línea de encabezado.

    Las notas de reforma quedan en *cursiva* como anotación al pie de su bloque.
    `notas` reconoce además las notas propias de una fuente estatal
    ('(REFORMADO, G.O. 25 DE MAYO DE 2000)'), que no llevan 'DOF' y anotan el
    párrafo que les sigue: cada una es su propio párrafo, hasta el paréntesis
    que la cierra. `rotulo` reconoce el encabezado del artículo en el primer
    renglón (el de las leyes estatales admite más formas).

    `cortes` (leyes estatales) dice, para un par de renglones seguidos, si el
    PDF abre ahí un párrafo (True) o el primero sigue en el segundo (False),
    por su geometría; manda sobre el punto final. Un renglón que sigue y abre
    con marcador ('406. Para tal efecto…') solo se une si el anterior no cerró
    con puntuación: un inciso que cierra justo en el margen no se une al
    siguiente.
    """
    lines = [ln.rstrip() for ln in body.splitlines()]
    originales = [ln.strip() for ln in lines]

    # Quitar el encabezado "Artículo N ...": el texto que le sigue en el mismo
    # renglón se conserva.
    if lines:
        first = lines[0]
        m = rotulo.match(first)
        lines[0] = first[m.end():] if m else first
        if m and cortes is not None and first[:1] in "\"“" and lines[0].strip():
            # Ley estatal que cita el artículo entre comillas ('“Artículo 23. …”'):
            # la de apertura es texto del PDF, y la de cierre queda al final.
            lines[0] = first[0] + lines[0].lstrip()

    blocks: list[str] = []
    buf: list[str] = []
    anterior = ""            # renglón original (con rótulo) del último en `buf`
    # Ley estatal con notas antes del texto: el rótulo queda solo en el primer
    # renglón y el texto que compartía su renglón ('Artículo 149.- Los testigos…')
    # viene después de las notas; los cortes lo conocen con el rótulo.
    rotulo_solo = (first.strip() if lines and cortes and m and not lines[0].strip() else "")

    def flush_buf() -> None:
        if buf:
            blocks.append(" ".join(w.strip() for w in buf if w.strip()))
            buf.clear()

    i = 0
    n = len(lines)
    while i < n:
        s = lines[i].strip()
        if not s:
            flush_buf()
            i += 1
            continue
        if notas is not None and notas.match(s):
            flush_buf()
            # Sigue en el renglón siguiente si no cerró su paréntesis o, la nota
            # del editor ('N. DE E. EN RELACIÓN CON …'), si no cerró la oración.
            note, j = s, i + 1
            while (j < n and (j - i) <= MAX_NOTA_ESTATAL_LINES and lines[j].strip()
                   and _nota_abierta(note)):
                note = f"{note} {lines[j].strip()}"
                j += 1
            blocks.append(f"_{note}_")
            i = j
            continue
        if NOTA_NORMATECA_RE.match(s):
            flush_buf()
            blocks.append(f"_{s}_")
            i += 1
            continue
        if _is_reform_note(s):
            flush_buf()
            note = s
            j = i + 1
            while (
                j < n
                and (j - i) <= MAX_NOTE_CONT_LINES
                and not _note_is_complete(note)
                and lines[j].strip()
                and not _is_struct_marker(lines[j])
                and not _is_reform_note(lines[j])
            ):
                note = f"{note} {lines[j].strip()}"
                j += 1
            blocks.append(f"_{note}_")
            i = j
            continue
        if cortes and buf and re.match(r"\*N\. de E\.", s):
            flush_buf()                 # la nota del editor es su propio párrafo
        corte = cortes.get((anterior, originales[i])) if cortes and buf else None
        if (corte is None and cortes and buf and rotulo_solo and len(buf) == 1
                and not blocks_texto(blocks)):
            corte = cortes.get((f"{rotulo_solo} {anterior}", originales[i]))
        if _is_struct_marker(s):
            sigue = corte is False and not SENTENCE_END_RE.search(buf[-1])
            if not sigue and corte is None and buf and _numero_pendiente(buf[-1], s):
                sigue = True
        else:
            sigue = corte is False or (corte is None and not (buf and SENTENCE_END_RE.search(buf[-1])))
            # Ley estatal: un ';' a media oración ('…a su testamento;' / 'si no
            # supiere…') que la geometría no decide sigue en el renglón que abre
            # en minúscula sin ser inciso.
            if (not sigue and cortes and corte is None and buf and buf[-1].endswith(";")
                    and re.match(r"[a-záéíóúüñ]{2,}\s", s) and not re.match(r"[a-zñ]{1,4}[.)]\s", s)):
                sigue = True
            # La conjunción sola en su renglón ('…que se impugnó;' /
            # 'y' / 'III. Por consulta…') cierra la fracción de arriba.
            if (not sigue and corte is None and buf and buf[-1].endswith(";")
                    and re.fullmatch(r"[yoeu]", s)):
                sigue = True
            # Ley estatal: el punto de un ordinal abreviado ('…del artículo 3o.' /
            # 'de la Constitución…') no cierra la oración si sigue una minúscula.
            if (not sigue and cortes and corte is None and buf
                    and re.search(r"\b\d{1,3}\s?[oº°]\.$", buf[-1])
                    and re.match(r"[a-záéíóúüñ]{2,}\s", s)
                    and not re.match(r"[a-zñ]{1,4}[.)]\s", s)):
                sigue = True
        # Ley estatal: 'DEROGADO. P.O. 20 DE MAYO DE 2022.' es un párrafo propio
        # aunque abra una página y la geometría lo dé por continuación.
        if (sigue and cortes and buf and SENTENCE_END_RE.search(buf[-1])
                and DEROGADO_SUELTO_RE.fullmatch(s)):
            sigue = False
        # Ley estatal: el importe de una tarifa ('204.5 cuotas') que el PDF pasa al
        # renglón siguiente de los puntos guía ('…suplente………') es de esa fila.
        if (not sigue and cortes is not None and buf and IMPORTE_SUELTO_RE.fullmatch(s)
                and re.search(r"(?:…|\.{3,})\.?$", buf[-1])):
            sigue = True
        if not sigue:
            flush_buf()
        elif corte is False and re.search(r"\w-$", buf[-1]):
            # 'DIF-' / 'CDMX.': el guion de una palabra compuesta no lleva espacio.
            buf[-1] += s
            anterior = originales[i]
            i += 1
            continue
        buf.append(s)
        anterior = originales[i]
        i += 1

    flush_buf()
    # Ley estatal: un renglón de tarifa que cierra el artículo ('Unidad Fiscal
    # hasta 1000 c c $ 3.50', sin punto) tras el párrafo que lo anuncia con ':'
    # sigue en ese párrafo; suelto parecería el encabezado del artículo siguiente.
    if (cortes and len(blocks) >= 2 and blocks[-2].endswith(":")
            and not blocks[-2].startswith("_")
            and TARIFA_FINAL_RE.match(blocks[-1])):
        blocks[-2:] = [f"{blocks[-2]} {blocks[-1]}"]
    return "\n\n".join(b for b in blocks if b).strip()
