"""Parser de anexos de la RMF organizados en apartados (Anexos 5 y 8).

Estos anexos no traen reglas ni artículos: son apartados 'A. / B. / C.' con
cantidades actualizadas (Anexo 5) o tarifas del ISR (Anexo 8). La unidad es el
apartado; la granularidad citable fina la dan los pasajes (párrafo + página).

El 'Contenido' inicial repite cada encabezado de apartado, así que se deduplica
por letra quedándose con el cuerpo más largo (el real). Las fracciones romanas
de una sola letra dentro del cuerpo ('I. De $5,070.00…', 'V. …', 'X. …') casan
con el patrón de apartado y se excluyen explícitamente.
"""
from __future__ import annotations

import re

from ..modelo import Apartado
from ..registro import Documento
from .criterios import fecha_publicacion, texto_limpio  # noqa: F401 — mismo formato DOF

APARTADO_RE = re.compile(r"^([A-Z])\.\s+(\S.*)$")
# Letras que en el cuerpo son números romanos de fracción, no apartados.
ROMANOS = set("IVXLM")


def parse(pdf_path: str, doc: Documento) -> list[Apartado]:
    return parse_texto(texto_limpio(pdf_path))


def parse_texto(clean_text: str) -> list[Apartado]:
    """Segmenta en apartados y deduplica índice vs contenido (cuerpo más largo)."""
    bloques: list[Apartado] = []
    actual: Apartado | None = None
    buf: list[str] = []

    def cerrar() -> None:
        if actual is not None:
            actual.cuerpo = "\n".join(buf).strip()
            bloques.append(actual)

    for raw in clean_text.splitlines():
        m = APARTADO_RE.match(raw.strip())
        if m and m.group(1) not in ROMANOS:
            cerrar()
            actual = Apartado(letra=m.group(1), rubro=m.group(2).strip().rstrip("."))
            buf = []
            continue
        if actual is not None:
            buf.append(raw)

    cerrar()

    mejor: dict[str, Apartado] = {}
    for a in bloques:
        if a.letra not in mejor or len(a.cuerpo) > len(mejor[a.letra].cuerpo):
            mejor[a.letra] = a
    return list(mejor.values())
