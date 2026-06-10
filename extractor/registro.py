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
# Página índice de la normatividad RMF del SAT. Los PDF del SAT llevan la fecha
# en el nombre (RMF_2026-DOF-28122025.pdf), así que la URL directa muere con
# cada nueva versión: la vigente se resuelve contra esta página (ver fuentes.py).
INDICE_SAT_RMF = ("https://www.sat.gob.mx/minisitio/NormatividadRMFyRGCE/"
                  "normatividad_rmf_rgce2026.html")


@dataclass(frozen=True)
class Documento:
    clave: str                       # namespace estable: "cff", "lisr", "rmf-2026"
    etiqueta: str                    # nombre legible: "Código Fiscal de la Federación"
    sigla: str                       # cita corta: "CFF", "LISR"
    tipo: str                        # "ley" | "reglamento" | "rmf" | "criterios"
    parser: str                      # "articulado" | "reglas" | "criterios"
    url: str | None = None           # fuente oficial (PDF) para descargar/vigilar
    # Resolución dinámica (fuentes del SAT): página índice + regex sobre los
    # href; gana el PDF de fecha más reciente. `url` queda como última conocida.
    indice: str | None = None
    patron: str | None = None
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
    _ley("lfdc",  "Ley Federal de los Derechos del Contribuyente", "LFDC", "LFDC.pdf"),
    _ley("lfisan", "Ley Federal del Impuesto sobre Automóviles Nuevos", "LFISAN",
         "LFISAN.pdf"),
    _ley("lish",  "Ley de Ingresos sobre Hidrocarburos", "LISH", "LIH.pdf"),
    _ley("lfpiorpi",
         "Ley Federal para la Prevención e Identificación de Operaciones con "
         "Recursos de Procedencia Ilícita", "LFPIORPI", "LFPIORPI.pdf"),
    # La Ley del SAT usa el esquema viejo de LeyesBiblio: número de ley + fecha de
    # la última reforma en el nombre (93_041218.pdf), así que la URL muere con
    # cada reforma y se resuelve contra el índice, igual que las fuentes del SAT.
    Documento("lsat", "Ley del Servicio de Administración Tributaria", "LSAT",
              tipo="ley", parser="articulado",
              url=f"{BASE_DIPUTADOS}/pdf/93_041218.pdf",
              indice=f"{BASE_DIPUTADOS}/index.htm",
              patron=r"pdf/93_\d{6}\.pdf$"),
    # --- Reglamentos (mismo parser articulado) ------------------------------
    _ley("rcff",  "Reglamento del Código Fiscal de la Federación", "RCFF",
         "Reg_CFF.pdf", tipo="reglamento"),
    _ley("rlisr", "Reglamento de la Ley del Impuesto sobre la Renta", "RLISR",
         "Reg_LISR_060516.pdf", tipo="reglamento"),
    _ley("rliva", "Reglamento de la Ley del Impuesto al Valor Agregado", "RLIVA",
         "Reg_LIVA_250914.pdf", tipo="reglamento"),
    _ley("rlieps", "Reglamento de la Ley del IEPS", "RLIEPS",
         "Reg_LIEPS.pdf", tipo="reglamento"),
    _ley("rladua", "Reglamento de la Ley Aduanera", "RLA",
         "Reg_LAdua.pdf", tipo="reglamento"),
    _ley("rlfpiorpi", "Reglamento de la LFPIORPI", "RLFPIORPI",
         "Reg_LFPIORPI.pdf", tipo="reglamento"),
    # --- RMF (reglas) -------------------------------------------------------
    Documento("rmf-2026", "Resolución Miscelánea Fiscal para 2026", "RMF 2026",
              tipo="rmf", parser="reglas",
              url="https://www.sat.gob.mx/minisitio/NormatividadRMFyRGCE/"
                  "documentos2026/rmf/rmf/RMF_2026-DOF-28122025.pdf",
              indice=INDICE_SAT_RMF,
              patron=r"documentos2026/rmf/rmf/RMF_2026.*\.pdf$"),
    # --- RGCE y RFA (mismas 'reglas' numeradas que la RMF; anuales) ---------
    Documento("rgce-2026", "Reglas Generales de Comercio Exterior para 2026",
              "RGCE 2026", tipo="rgce", parser="reglas",
              url="https://www.sat.gob.mx/minisitio/NormatividadRMFyRGCE/"
                  "documentos2026/rgce/rgce/ReglasGeneralesComercioExteriorpara2026.pdf",
              indice=INDICE_SAT_RMF,
              patron=r"documentos2026/rgce/rgce/ReglasGenerales.*\.pdf$"),
    Documento("rfa-2026", "Resolución de Facilidades Administrativas para 2026",
              "RFA 2026", tipo="rfa", parser="reglas",
              url="https://www.sat.gob.mx/minisitio/NormatividadRMFyRGCE/"
                  "documentos2026/rfa/rfa/RFA2026_17022026.pdf",
              indice=INDICE_SAT_RMF,
              patron=r"documentos2026/rfa/rfa/RFA2026.*\.pdf$"),
    # --- Criterios del SAT (anexos de la RMF) -------------------------------
    Documento("criterios-normativos",
              "Compilación de criterios normativos fiscales (Anexo 7 RMF 2026)",
              "Criterio Normativo", tipo="criterios", parser="criterios",
              url="https://www.sat.gob.mx/minisitio/NormatividadRMFyRGCE/"
                  "documentos2026/rmf/anexos/Anexo_7_RMF2026-09012026.pdf",
              indice=INDICE_SAT_RMF,
              patron=r"documentos2026/rmf/anexos/Anexo_7_RMF2026.*\.pdf$"),
    Documento("criterios-no-vinculativos",
              "Compilación de criterios sobre prácticas fiscales indebidas (Anexo 3 RMF 2026)",
              "Criterio No Vinculativo", tipo="criterios", parser="criterios",
              url="https://www.sat.gob.mx/minisitio/NormatividadRMFyRGCE/"
                  "documentos2026/rmf/anexos/Anexo_3_RMF2026-09012026.pdf",
              indice=INDICE_SAT_RMF,
              patron=r"documentos2026/rmf/anexos/Anexo_3_RMF2026.*\.pdf$"),
]

POR_CLAVE = {d.clave: d for d in DOCUMENTOS}


def activos() -> list[Documento]:
    """Documentos listos para extraer hoy (parser implementado)."""
    return [d for d in DOCUMENTOS if d.activo]
