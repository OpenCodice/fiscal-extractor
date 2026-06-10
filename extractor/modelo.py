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


def _nombre_jerarquia(encabezado: str) -> str:
    """Nombre descriptivo de un encabezado 'NÚMERO. Nombre' (sin el número).

    'TÍTULO IV. DE LAS PERSONAS FÍSICAS' → 'DE LAS PERSONAS FÍSICAS'
    'Título 2. Código Fiscal de la Federación' → 'Código Fiscal de la Federación'
    Un encabezado solo-número ('TÍTULO IV') no aporta nombre → ''.
    """
    if not encabezado:
        return ""
    partes = encabezado.split(". ", 1)
    return partes[1].strip() if len(partes) == 2 else ""


def _contexto(*encabezados: str) -> str:
    """Nombres de la jerarquía unidos para búsqueda (el número es ruido).

    Ej.: 'DE LAS PERSONAS FÍSICAS · DEL RÉGIMEN SIMPLIFICADO DE CONFIANZA'.
    Es texto de RECALL, no de cita: ubica la unidad por el tema de su sección.
    """
    nombres = [_nombre_jerarquia(h) for h in encabezados]
    return " · ".join(n for n in nombres if n)


@dataclass
class Unidad:
    numero: int
    letra: str = ""                  # "", "A".."Z"
    ordinal: str = ""                # "", "Bis", "Ter", "Quáter", "Quinquies", ...
    ord_num: str = ""                # numeral tras el ordinal: "137 Bis 1" → "1"
    titulo: str = ""                 # "TÍTULO IV. DE LAS PERSONAS FÍSICAS" (núm. + nombre)
    capitulo: str = ""               # "CAPÍTULO II. DE LOS INGRESOS..."
    seccion: str = ""                # "SECCIÓN IV. DEL RÉGIMEN SIMPLIFICADO DE CONFIANZA"
    cuerpo: str = ""                 # texto completo de la unidad
    fechas_reforma: list[date] = field(default_factory=list)
    derogado: bool = False

    @property
    def contexto(self) -> str:
        """Nombres de la jerarquía (Título/Capítulo/Sección) para búsqueda.

        El nombre del régimen/tema suele vivir SOLO en el encabezado de su
        sección (p. ej. 'Régimen Simplificado de Confianza' no aparece en el
        cuerpo del Art. 113-E), así que sin esto la unidad es irrecuperable por
        ese término. No es fuente de cita.
        """
        return _contexto(self.titulo, self.capitulo, self.seccion)

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


@dataclass
class Regla:
    """Una regla de la RMF (Resolución Miscelánea Fiscal).

    A diferencia de un artículo, la regla se identifica por una numeración
    jerárquica con puntos ('2.7.1.21') y trae un título descriptivo propio
    ('Devolución de saldos a favor del IVA'). Su contexto estructural es
    Título → Capítulo → Sección.
    """
    numero: str                      # "2.7.1.21"
    titulo_regla: str = ""           # descripción de la regla
    titulo: str = ""                 # "Título 2. Código Fiscal de la Federación"
    capitulo: str = ""               # "Capítulo 2.7. De los CFDI..."
    seccion: str = ""                # "Sección 2.7.1. Disposiciones generales"
    cuerpo: str = ""
    referencias: list[str] = field(default_factory=list)  # fundamentos: "CFF 69"

    @property
    def clave(self) -> str:
        """Identificador estable = el número de la regla: '2.7.1.21'."""
        return self.numero

    @property
    def contexto(self) -> str:
        """Nombres de Título/Capítulo/Sección de la regla, para búsqueda."""
        return _contexto(self.titulo, self.capitulo, self.seccion)

    @property
    def nivel(self) -> int:
        return self.numero.count(".") + 1

    @property
    def etiqueta(self) -> str:
        base = f"Regla {self.numero}."
        return f"{base} {self.titulo_regla}" if self.titulo_regla else base


@dataclass
class Ficha:
    """Una ficha de trámite del SAT (Anexo 2 de la RMF 2026; antes Anexo 1-A).

    Se identifica por 'N/LEY' (p. ej. '1/CFF', '64/ISR', '3/DEC-5') y trae el
    nombre del trámite (rubro) más el contenido de la ficha: quiénes lo
    presentan, dónde, requisitos, plazos y condiciones.
    """
    numero: str                      # "1/CFF"
    ley: str                         # "CFF", "ISR", "DEC-5", ...
    rubro: str = ""                  # nombre del trámite
    cuerpo: str = ""

    @property
    def contexto(self) -> str:
        return ""

    @property
    def clave(self) -> str:
        """Identificador estable apto para archivo: '1/CFF' → '1-cff'."""
        return self.numero.replace("/", "-").lower()

    @property
    def etiqueta(self) -> str:
        base = f"Ficha de trámite {self.numero}"
        return f"{base} — {self.rubro}" if self.rubro else base


@dataclass
class Apartado:
    """Un apartado (A, B, C…) de un anexo de la RMF (cantidades, tarifas).

    Los anexos 5 y 8 no se dividen en reglas ni artículos: son apartados con
    cantidades actualizadas o tarifas; la granularidad citable fina la dan los
    pasajes (párrafo + página del PDF).
    """
    letra: str                       # "A"
    rubro: str = ""                  # "Tarifa aplicable a pagos provisionales"
    cuerpo: str = ""

    @property
    def numero(self) -> str:
        return self.letra

    @property
    def contexto(self) -> str:
        return ""

    @property
    def clave(self) -> str:
        return self.letra.lower()

    @property
    def etiqueta(self) -> str:
        base = f"Apartado {self.letra}"
        return f"{base}. {self.rubro}" if self.rubro else base


@dataclass
class Criterio:
    """Un criterio del SAT (normativo, Anexo 7; o no vinculativo, Anexo 3).

    Se identifica por 'N/LEY/TIPO' (p. ej. '10/IVA/N', '25/ISR/NV', '1/CFF/PI')
    y trae un rubro (título) + el texto del criterio. Su contexto es la sección
    por ley ('I. Criterios del CFF') y el estado (vigente/derogado).
    """
    numero: str                      # "10/IVA/N"
    ley: str                         # "IVA"
    tipo: str                        # "N" (normativo) | "NV" (no vinculativo) | "PI"
    rubro: str = ""                  # título del criterio
    cuerpo: str = ""
    seccion: str = ""                # "III. Criterios de la Ley del IVA"
    estado: str = "vigente"          # "vigente" | "derogado"

    @property
    def contexto(self) -> str:
        """Nombre de la sección por ley del criterio, para búsqueda."""
        return _contexto(self.seccion)

    @property
    def clave(self) -> str:
        """Identificador estable apto para archivo: '10/IVA/N' → '10-iva-n'."""
        return self.numero.replace("/", "-").lower()

    @property
    def etiqueta(self) -> str:
        base = f"Criterio {self.numero}"
        return f"{base} — {self.rubro}" if self.rubro else base
