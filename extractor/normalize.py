"""Normaliza el cuerpo crudo de una unidad a párrafos limpios.

Port de `constitucion-extractor/extractor/normalize.py`. El PDF entrega saltos
de línea "visuales" (no de párrafo); se re-unen y se separan en bloques lógicos
(fracciones, incisos, notas de reforma) para que un `git diff` de una reforma
muestre solo el párrafo cambiado.
"""
from __future__ import annotations

import re

from .parsers.articulado import ARTICULO_RE

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

# Nota de reforma de las compilaciones de la normateca del SAT (RISAT):
# "(DOF 21 de diciembre de 2021)" en línea propia, siempre completa.
NOTA_NORMATECA_RE = re.compile(
    r"^\(DOF\s+\d{1,2}\s+de\s+[a-zá-ú]+\s+de\s+\d{4}\)$", re.IGNORECASE)

# Marcadores de fracción / inciso / apartado: "I.", "a)", "1.", "A. ".
STRUCT_MARKER_RE = re.compile(r"^(?:[IVXLCDM]+\.|[a-z]\)|\d+\.|[A-Z]\.\s)")
SENTENCE_END_RE = re.compile(r"[.:;]$")


def _is_reform_note(line: str) -> bool:
    return bool(REFORM_NOTE_START_RE.match(line.strip()))


def _is_struct_marker(line: str) -> bool:
    return bool(STRUCT_MARKER_RE.match(line.strip()))


def _note_is_complete(note: str) -> bool:
    return bool(NOTE_COMPLETE_RE.search(note.strip()))


def normalize_body(body: str, heading_label: str, notas: re.Pattern | None = None,
                   rotulo: re.Pattern = ARTICULO_RE) -> str:
    """Devuelve el cuerpo de la unidad como párrafos, sin la línea de encabezado.

    Las notas de reforma quedan en *cursiva* como anotación al pie de su bloque.
    `notas` reconoce además las notas propias de una fuente estatal
    ('(REFORMADO, G.O. 25 DE MAYO DE 2000)'), que no llevan 'DOF' y anotan el
    párrafo que les sigue: cada una es su propio párrafo, hasta el paréntesis
    que la cierra. `rotulo` reconoce el encabezado del artículo en el primer
    renglón (el de las leyes estatales admite más formas).
    """
    lines = [ln.rstrip() for ln in body.splitlines()]

    # Quitar el encabezado "Artículo N ...": el texto que le sigue en el mismo
    # renglón se conserva.
    if lines:
        first = lines[0]
        m = rotulo.match(first)
        lines[0] = first[m.end():] if m else first

    blocks: list[str] = []
    buf: list[str] = []

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
            while (j < n and (j - i) <= MAX_NOTE_CONT_LINES and lines[j].strip()
                   and (note.count("(") > note.count(")")
                        or (note.startswith("N. DE E.") and not note.endswith(".")))):
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
        if _is_struct_marker(s):
            flush_buf()
            buf.append(s)
            i += 1
            continue
        if buf and SENTENCE_END_RE.search(buf[-1]):
            flush_buf()
        buf.append(s)
        i += 1

    flush_buf()
    return "\n\n".join(b for b in blocks if b).strip()
