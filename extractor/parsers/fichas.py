"""Parser de fichas de trámite del SAT (Anexo 2 de la RMF 2026; antes Anexo 1-A).

Cada ficha se identifica por 'N/LEY' ('1/CFF', '64/ISR', '3/DEC-5'), trae el
nombre del trámite y un cuerpo tabular (quiénes lo presentan, dónde, requisitos,
plazos). El documento abre con un índice que repite cada identificador (solo el
nombre, sin cuerpo); se deduplica quedándose con la aparición de cuerpo más
largo, igual que los criterios.

Discriminador real-vs-cita: una cita a media oración suele continuar con el
rubro entre comillas ('…la ficha de trámite\n64/ISR "Aviso…"'), así que el
rubro debe empezar en MAYÚSCULA sin comilla; además el número debe crecer
monotónicamente dentro del grupo de su ley (el índice y el contenido recorren
los grupos en el mismo orden, y las fichas derogadas dejan huecos válidos).
"""
from __future__ import annotations

import re

from ..modelo import Ficha
from ..registro import Documento
from .criterios import fecha_publicacion, texto_limpio  # noqa: F401 — mismo formato DOF

# "1/CFF Solicitud de inscripción…", "3/DEC-5 Aviso…", "1/DERECHOS Declaración…"
FICHA_RE = re.compile(r"^(\d+)/([A-Z]{2,}(?:-\d+)?)\s+([A-ZÁÉÍÓÚÑ¿(].*)$")


def parse(pdf_path: str, doc: Documento) -> list[Ficha]:
    return parse_texto(texto_limpio(pdf_path))


def parse_texto(clean_text: str) -> list[Ficha]:
    """Segmenta en fichas y deduplica índice vs contenido (cuerpo más largo)."""
    bloques: list[Ficha] = []
    actual: Ficha | None = None
    buf: list[str] = []
    cur_ley = ""
    cur_num = 0
    rubro_abierto = False            # el nombre del trámite siempre cierra con "."

    def cerrar() -> None:
        if actual is not None:
            actual.cuerpo = "\n".join(buf).strip()
            bloques.append(actual)

    for raw in clean_text.splitlines():
        s = raw.strip()
        m = FICHA_RE.match(s)
        if m:
            num, ley = int(m.group(1)), m.group(2)
            if ley != cur_ley or num > cur_num:
                cerrar()
                actual = Ficha(numero=f"{num}/{ley}", ley=ley,
                               rubro=m.group(3).strip())
                buf = []
                cur_ley, cur_num = ley, num
                rubro_abierto = not actual.rubro.endswith(".")
                continue
        if actual is not None:
            # Nombre del trámite envuelto en varias líneas: continúa hasta el
            # punto final (acotado, por si alguna ficha no lo trae).
            if rubro_abierto and s and len(actual.rubro) < 300:
                actual.rubro += f" {s}"
                rubro_abierto = not s.endswith(".")
                continue
            rubro_abierto = False
            buf.append(raw)

    cerrar()

    mejor: dict[str, Ficha] = {}
    for f in bloques:
        if f.numero not in mejor or len(f.cuerpo) > len(mejor[f.numero].cuerpo):
            mejor[f.numero] = f
    return list(mejor.values())
