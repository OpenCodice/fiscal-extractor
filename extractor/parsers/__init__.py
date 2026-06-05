"""Parsers por tipo de documento.

Cada documento del registro declara su `parser`; aquí se resuelve a la función
que segmenta su fuente en unidades. Hoy existe `articulado` (leyes/códigos/
reglamentos); `reglas` (RMF) y `criterios` llegan en fases posteriores.
"""
from __future__ import annotations

from . import articulado

PARSERS = {
    "articulado": articulado.parse,
}


def resolver(nombre: str):
    if nombre not in PARSERS:
        raise NotImplementedError(f"parser '{nombre}' aún no implementado")
    return PARSERS[nombre]
