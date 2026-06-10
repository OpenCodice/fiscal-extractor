"""Parsers por tipo de documento.

Cada documento del registro declara su `parser`; aquí se resuelve a la función
que segmenta su fuente en unidades: `articulado` (leyes/códigos/reglamentos),
`reglas` (RMF/RGCE/RFA), `criterios` (Anexos 3 y 7), `fichas` (Anexo 2) y
`apartados` (Anexos 5 y 8).
"""
from __future__ import annotations

from . import apartados, articulado, criterios, fichas, reglas

PARSERS = {
    "articulado": articulado.parse,
    "reglas": reglas.parse,
    "criterios": criterios.parse,
    "fichas": fichas.parse,
    "apartados": apartados.parse,
}


def resolver(nombre: str):
    if nombre not in PARSERS:
        raise NotImplementedError(f"parser '{nombre}' aún no implementado")
    return PARSERS[nombre]
