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

# Marcadores de fracción / inciso / apartado: "I.", "a)", "1.", "A. ".
STRUCT_MARKER_RE = re.compile(r"^(?:[IVXLCDM]+\.|[a-z]\)|\d+\.|[A-Z]\.\s)")
SENTENCE_END_RE = re.compile(r"[.:;]$")


def _is_reform_note(line: str) -> bool:
    return bool(REFORM_NOTE_START_RE.match(line.strip()))


def _is_struct_marker(line: str) -> bool:
    return bool(STRUCT_MARKER_RE.match(line.strip()))


def _note_is_complete(note: str) -> bool:
    return bool(NOTE_COMPLETE_RE.search(note.strip()))


def normalize_body(body: str, heading_label: str) -> str:
    """Devuelve el cuerpo de la unidad como párrafos, sin la línea de encabezado.

    Las notas de reforma quedan en *cursiva* como anotación al pie de su bloque.
    """
    lines = [ln.rstrip() for ln in body.splitlines()]

    # Quitar el encabezado "Artículo N ...": el texto que le sigue en el mismo
    # renglón se conserva.
    if lines:
        first = lines[0]
        m = ARTICULO_RE.match(first)
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
