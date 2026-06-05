"""Modelo de una 'unidad' del articulado (artículo, con sus variantes).

Generaliza el `Article` de la constitución para el sistema de sufijos —mucho
más rico— de los códigos fiscales:

  - letra:   "Artículo 14-A", "Artículo 32-B"        → letra = "A" / "B"
  - ordinal: "Artículo 111 Bis", "Artículo 20-Ter"   → ordinal = "Bis" / "Ter"
  - combinado: "Artículo 17-H Bis", "Artículo 32-B Quáter"
  - derogado: "Artículo 64.- (Se deroga)."           → se conserva, derogado=True

La `clave` es el identificador estable (nombre de archivo): "014-a", "017-h-bis".
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import date


def _ascii(s: str) -> str:
    """'Quáter' → 'quater' (para claves de archivo sin acentos)."""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


@dataclass
class Unidad:
    numero: int
    letra: str = ""                  # "", "A".."Z"
    ordinal: str = ""                # "", "Bis", "Ter", "Quáter", "Quinquies", ...
    ord_num: str = ""                # numeral tras el ordinal: "137 Bis 1" → "1"
    titulo: str = ""                 # Título al que pertenece
    capitulo: str = ""               # Capítulo al que pertenece
    cuerpo: str = ""                 # texto completo de la unidad
    fechas_reforma: list[date] = field(default_factory=list)
    derogado: bool = False

    @property
    def clave(self) -> str:
        """Identificador estable: '004', '014-a', '017-h-bis', '137-bis-1'."""
        partes = [f"{self.numero:03d}"]
        if self.letra:
            partes.append(_ascii(self.letra))
        if self.ordinal:
            partes.append(_ascii(self.ordinal))
        if self.ord_num:
            partes.append(self.ord_num)
        return "-".join(partes)

    @property
    def etiqueta(self) -> str:
        """Cita oficial: 'Artículo 4o.-A', 'Artículo 17-H Bis', 'Artículo 137 Bis 1'."""
        if self.numero <= 9:
            core = f"{self.numero}o"
        else:
            core = f"{self.numero}"
        if self.letra:
            core += f"-{self.letra}"
        if self.ordinal:
            core += f" {self.ordinal}"
        if self.ord_num:
            core += f" {self.ord_num}"
        if not self.letra and not self.ordinal:
            core += "."                       # "Artículo 4o." / "Artículo 14."
        return f"Artículo {core}"

    @property
    def ultima_reforma(self) -> date | None:
        return max(self.fechas_reforma) if self.fechas_reforma else None
