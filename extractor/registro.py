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
    # Resolución por texto de ancla (normateca legacy del SAT): los href son
    # blobs opacos del CMS y lo estable es el texto del enlace ("RISAT").
    texto_enlace: str | None = None
    # Líneas de encabezado que se repiten en cada página del PDF y deben quitarse
    # (además de las genéricas de la Cámara). Suele ser el título del documento.
    titulos_encabezado: tuple[str, ...] = field(default_factory=tuple)
    activo: bool = True              # False = declarado pero su parser aún no existe
    # --- leyes estatales (ver estatal.py) ---------------------------------
    # Periódico oficial donde se publican sus reformas ('Periódico Oficial del
    # Estado de Jalisco'): el trailer Medio de sus commits.
    medio: str | None = None
    # Cómo elegir entre los PDF del índice que casan con `patron`: 'ddmmaaaa'
    # (la fecha más reciente en el nombre, SAT), 'ddmmaa' (Jalisco) o 'unico'
    # (el índice enlaza solo el vigente; dos rutas distintas son un error).
    orden: str = "ddmmaaaa"
    # La numeración del PDF tiene huecos: los estados suelen omitir el artículo
    # derogado en vez de dejar "Se deroga". Ver `articulado.parse_texto`.
    huecos: bool = False
    # Regex de las notas de reforma de la fuente ('Párrafo reformado G.O. CDMX
    # 08/12/23'): cada una es un párrafo en cursiva y de ellas salen las fechas
    # de reforma, como de las 'DOF DD-MM-AAAA' de la Cámara.
    notas: str | None = None
    # Las que el PDF pone ANTES de lo que anotan ('(REFORMADO, G.O. 25 DE MAYO
    # DE 2000)' sobre el artículo, en la CDMX): las que quedan justo antes de
    # un artículo son de ese artículo.
    notas_previas: str | None = None
    # 'mx': el sitio rechaza IP extranjeras; se descarga por el Worker egress-mx.
    via: str | None = None
    # Notas que el PDF escribe a renglón seguido, al final del párrafo que
    # anotan y a veces partidas entre dos renglones ('…de la vida; (Ref. P. O.
    # No. 75, 31-X-22)', Querétaro): cada una pasa a su propio renglón, donde
    # `notas` la reconoce.
    notas_en_linea: str | None = None
    # Los href del índice llevan consulta tras '.pdf' ('….pdf?fecha=…', Nuevo
    # León): también cuentan como PDF. Opcional para no cambiar qué enlaces ve
    # el resto del corpus.
    consulta: bool = False
    # Además de `consulta`: la consulta del href es solo un cache-buster y a
    # veces trae un espacio ('….pdf?2026-03- 9') que la descarga rechaza; se
    # descarta y queda la URL del PDF sin ella.
    sin_consulta: bool = False


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
    # El RISAT viene de la normateca del SAT, no de la Cámara: la Cámara solo
    # tiene la publicación original 2015 en PDF y el SAT publica la compilación
    # vigente (reforma DOF 21-12-2021, que movió aduanas a la ANAM). El href es
    # un blob del CMS que cambia con cada versión; se resuelve por el texto del
    # ancla. La leyenda al pie se repite en cada página y no es auto-detectable.
    Documento("risat", "Reglamento Interior del Servicio de Administración Tributaria",
              "RISAT", tipo="reglamento", parser="articulado",
              url="https://wwwmat.sat.gob.mx/cs/Satellite?blobcol=urldata&blobkey=id"
                  "&blobtable=MungoBlobs&blobwhere=1461176458878&ssbinary=true",
              indice="https://wwwmat.sat.gob.mx/normatividad/43026/reglamentos",
              texto_enlace=r"RISAT",
              titulos_encabezado=(
                  "Este documento es una compilación del reglamento y sus reformas "
                  "publicadas en el Diario Oficial de la Federación, de conformidad "
                  "con el artículo 5 de la Ley",
                  "Federal de los Derechos del Contribuyente. Para sustentar "
                  "legalmente actos o resoluciones se deberá consultar el Diario "
                  "Oficial de la Federación.",
              )),
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
    # --- Anexos de la RMF: fichas de trámite, cantidades y tarifas ----------
    Documento("anexo2-2026", "Fichas de trámite fiscales (Anexo 2 RMF 2026)",
              "Anexo 2 RMF 2026", tipo="anexo-rmf", parser="fichas",
              url="https://www.sat.gob.mx/minisitio/NormatividadRMFyRGCE/"
                  "documentos2026/rmf/anexos/Anexo-2-RMF-2026_DOF-28122025.pdf",
              indice=INDICE_SAT_RMF,
              patron=r"documentos2026/rmf/anexos/Anexo-2-RMF.*\.pdf$"),
    Documento("anexo5-2026", "Cantidades actualizadas del CFF (Anexo 5 RMF 2026)",
              "Anexo 5 RMF 2026", tipo="anexo-rmf", parser="apartados",
              url="https://www.sat.gob.mx/minisitio/NormatividadRMFyRGCE/"
                  "documentos2026/rmf/anexos/Anexo-5-RMF-2026_DOF-28122025.pdf",
              indice=INDICE_SAT_RMF,
              patron=r"documentos2026/rmf/anexos/Anexo-5-RMF.*\.pdf$"),
    Documento("anexo8-2026", "Tarifas del ISR (Anexo 8 RMF 2026)",
              "Anexo 8 RMF 2026", tipo="anexo-rmf", parser="apartados",
              url="https://www.sat.gob.mx/minisitio/NormatividadRMFyRGCE/"
                  "documentos2026/rmf/anexos/Anexo-8-RMF-2026_DOF-28122025.pdf",
              indice=INDICE_SAT_RMF,
              patron=r"documentos2026/rmf/anexos/Anexo-8-RMF.*\.pdf$"),
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
# El corpus fiscal tal cual, aunque `usar` sustituya el activo.
FISCALES: tuple[Documento, ...] = tuple(DOCUMENTOS)


def activos() -> list[Documento]:
    """Documentos listos para extraer hoy (parser implementado)."""
    return [d for d in DOCUMENTOS if d.activo]


# --- Registros declarados en un repo de datos -------------------------------
# Un repo de datos puede traer su propio registro (`fuentes.json`) en vez del
# corpus fiscal de arriba: es el caso de leyes-federales, cuyo registro se
# genera del índice de LeyesBiblio (ver federal.py).

def a_dict(doc: Documento) -> dict:
    d = {"clave": doc.clave, "etiqueta": doc.etiqueta, "sigla": doc.sigla,
         "tipo": doc.tipo, "parser": doc.parser, "url": doc.url}
    for campo in ("indice", "patron", "texto_enlace"):
        if getattr(doc, campo):
            d[campo] = getattr(doc, campo)
    if doc.titulos_encabezado:
        d["titulos_encabezado"] = list(doc.titulos_encabezado)
    for campo in ("medio", "notas", "notas_previas", "via", "notas_en_linea"):
        if getattr(doc, campo):
            d[campo] = getattr(doc, campo)
    if doc.orden != "ddmmaaaa":
        d["orden"] = doc.orden
    if doc.huecos:
        d["huecos"] = True
    if doc.consulta:
        d["consulta"] = True
    if doc.sin_consulta:
        d["sin_consulta"] = True
    return d


def de_dict(d: dict) -> Documento:
    return Documento(
        clave=d["clave"], etiqueta=d["etiqueta"], sigla=d["sigla"], tipo=d["tipo"],
        parser=d.get("parser", "articulado"), url=d.get("url"),
        indice=d.get("indice"), patron=d.get("patron"),
        texto_enlace=d.get("texto_enlace"),
        titulos_encabezado=tuple(d.get("titulos_encabezado", ())),
        medio=d.get("medio"), orden=d.get("orden", "ddmmaaaa"),
        huecos=bool(d.get("huecos")), notas=d.get("notas"),
        notas_previas=d.get("notas_previas"),
        via=d.get("via"), notas_en_linea=d.get("notas_en_linea"),
        consulta=bool(d.get("consulta")), sin_consulta=bool(d.get("sin_consulta")),
    )


def usar(documentos: list[Documento]) -> None:
    """Sustituye el corpus activo. Se modifican las estructuras en sitio porque
    los demás módulos las importan por nombre."""
    DOCUMENTOS[:] = documentos
    POR_CLAVE.clear()
    POR_CLAVE.update({d.clave: d for d in documentos})


def cargar(ruta) -> None:
    """Usa como corpus los documentos de un `fuentes.json` (o de un plan). Una
    ley estatal se define en `extractor/estatales/` (cómo leer su PDF):
    fuentes.json solo la identifica, así que gana la definición del código."""
    import json
    from pathlib import Path
    from .estatales import documentos as estatales, fuera
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    codigo = {d.clave: d for d in estatales()} | {c: d for c, (d, _) in fuera().items()}
    usar([codigo.get(d["clave"]) or de_dict(d) for d in datos["documentos"]])
