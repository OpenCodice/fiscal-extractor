"""Registro declarativo del corpus fiscal — qué se extrae y cómo.

La diferencia central con `constitucion-extractor` (un solo documento) es esta
lista: cada entrada describe un documento del corpus, su fuente, su tipo y qué
parser lo procesa. La `clave` es el namespace de TODO lo que produce el
documento: archivos `cff/027.md`, ids de pasaje `cff/027.p1`, citas "Art. 27 CFF".

Los PDF de leyes y reglamentos vienen de la H. Cámara de Diputados (misma fuente
que la CPEUM, estructura de articulado casi idéntica). La RMF y los criterios se
publican en el DOF / portal del SAT y usan otra estructura ('reglas',
'criterios'); sus parsers llegan en fases posteriores.
"""
from __future__ import annotations

from dataclasses import dataclass, field

BASE_DIPUTADOS = "https://www.diputados.gob.mx/LeyesBiblio"


@dataclass(frozen=True)
class Documento:
    clave: str                       # namespace estable: "cff", "lisr", "rmf-2026"
    etiqueta: str                    # nombre legible: "Código Fiscal de la Federación"
    sigla: str                       # cita corta: "CFF", "LISR"
    tipo: str                        # "ley" | "reglamento" | "rmf" | "criterios"
    parser: str                      # "articulado" | "reglas" | "criterios"
    url: str | None = None           # fuente oficial (PDF) para descargar/vigilar
    # Líneas de encabezado que se repiten en cada página del PDF y deben quitarse
    # (además de las genéricas de la Cámara). Suele ser el título del documento.
    titulos_encabezado: tuple[str, ...] = field(default_factory=tuple)
    activo: bool = True              # False = declarado pero su parser aún no existe


def _ley(clave, etiqueta, sigla, archivo, encabezado="", *, parser="articulado",
         tipo="ley", activo=True):
    # El encabezado corrido se auto-detecta del PDF (ver _titulo_corrido); pasar
    # `encabezado` es opcional, como refuerzo.
    carpeta = "pdf" if tipo == "ley" else "regley"
    return Documento(
        clave=clave, etiqueta=etiqueta, sigla=sigla, tipo=tipo, parser=parser,
        url=f"{BASE_DIPUTADOS}/{carpeta}/{archivo}",
        titulos_encabezado=(encabezado,) if encabezado else (), activo=activo,
    )


# Corpus completo (objetivo). Solo los `activo=True` con parser implementado se
# extraen hoy; el resto queda declarado para las siguientes fases.
DOCUMENTOS: list[Documento] = [
    # --- Leyes y códigos (parser articulado, fuente Cámara de Diputados) ----
    _ley("cff",   "Código Fiscal de la Federación", "CFF",
         "CFF.pdf",   "CÓDIGO FISCAL DE LA FEDERACIÓN"),
    _ley("lisr",  "Ley del Impuesto sobre la Renta", "LISR",
         "LISR.pdf",  "LEY DEL IMPUESTO SOBRE LA RENTA"),
    _ley("liva",  "Ley del Impuesto al Valor Agregado", "LIVA",
         "LIVA.pdf",  "LEY DEL IMPUESTO AL VALOR AGREGADO"),
    _ley("lieps", "Ley del Impuesto Especial sobre Producción y Servicios", "LIEPS",
         "LIEPS.pdf", "LEY DEL IMPUESTO ESPECIAL SOBRE PRODUCCIÓN Y SERVICIOS"),
    _ley("lfd",   "Ley Federal de Derechos", "LFD", "LFD.pdf"),
    _ley("ladua", "Ley Aduanera", "L. Aduanera", "LAdua.pdf"),
    _ley("lcf",   "Ley de Coordinación Fiscal", "LCF", "LCF.pdf"),
    _ley("lfpca", "Ley Federal de Procedimiento Contencioso Administrativo", "LFPCA",
         "LFPCA.pdf"),
    _ley("lif-2026", "Ley de Ingresos de la Federación 2026", "LIF 2026",
         "LIF_2026.pdf"),   # anual: se renueva cada ejercicio (clave con año)
    # --- Reglamentos (mismo parser articulado) ------------------------------
    _ley("rcff",  "Reglamento del Código Fiscal de la Federación", "RCFF",
         "Reg_CFF.pdf", tipo="reglamento"),
    _ley("rlisr", "Reglamento de la Ley del Impuesto sobre la Renta", "RLISR",
         "Reg_LISR_060516.pdf", tipo="reglamento"),
    _ley("rliva", "Reglamento de la Ley del Impuesto al Valor Agregado", "RLIVA",
         "Reg_LIVA_250914.pdf", tipo="reglamento"),
    _ley("rlieps", "Reglamento de la Ley del IEPS", "RLIEPS",
         "Reg_LIEPS.pdf", tipo="reglamento"),
    # --- RMF (reglas) -------------------------------------------------------
    Documento("rmf-2026", "Resolución Miscelánea Fiscal para 2026", "RMF 2026",
              tipo="rmf", parser="reglas",
              url="https://www.sat.gob.mx/minisitio/NormatividadRMFyRGCE/"
                  "documentos2026/rmf/rmf/RMF_2026-DOF-28122025.pdf"),
    # --- Criterios (parser de fase posterior) -------------------------------
    Documento("criterios-normativos", "Criterios Normativos del SAT", "Criterio Normativo",
              tipo="criterios", parser="criterios", activo=False),
]

POR_CLAVE = {d.clave: d for d in DOCUMENTOS}


def activos() -> list[Documento]:
    """Documentos listos para extraer hoy (parser implementado)."""
    return [d for d in DOCUMENTOS if d.activo]
