"""Querétaro: la Dirección de Investigación y Estadística Legislativa del
Poder Legislativo (Biblioteca «Manuel Septién y Septién»).

Publica el texto vigente de cada ley en una ruta fija que no cambia con las
reformas (`CloudPLQ/InvEst/Codigos/COD-ID-02.pdf`, `…/Ley-Org/ORG-ID-08.pdf`).
Cada PDF abre con su «Ficha Genealógica» (versión primigenia e historial de
cambios, de donde sale la versión: ver `articulado.fecha_version`). Las notas
de reforma van a renglón seguido, al final del párrafo que anotan y a veces
partidas entre renglones: '(Ref. P. O. No. 75, 31-X-22)', '(Adición P. O.
No. 102, 27-XII-23)'.
"""
import re

from . import ley

MEDIO = "Periódico Oficial del Gobierno del Estado de Querétaro «La Sombra de Arteaga»"
_BASE = "https://site.legislaturaqueretaro.gob.mx/CloudPLQ/InvEst/"
_FECHA_PO = (r"P\.\s*O\.?\s*(?:[NM]\s?o\.\s*)+\d+\s*[,.]\s*\d{1,2}\s*-\s*[IVX]+\s*-\s*\d{2,4}")
# El PDF escribe a veces 'p.o.' en minúsculas, 'Mo.' por 'No.' o un punto por la
# coma; la nota puede seguir con '(esta reforma entra en vigor …)', que es suya.
_NOTA = (r"\((?i:(?:Ref\.|Reforma|Adici[óo]n\.?|Derogad[oa]|Derogaci[óo]n|Fe\s+de\s+erratas)?\s*"
         + _FECHA_PO + r")\)(?:\s*\((?i:esta\s+(?:adici[óo]n|reforma))\s+entra[^()]*\))?"
         r"|\(Fe\s+de\s+erratas\s+seg[úu]n\s+oficio\s+[\w/.-]+[^()]*?publicado\s+en\s+el\s+"
         + _FECHA_PO + r"\)"
         r"|\(Modificaci[óo]n\s+seg[úu]n\s+oficio\s+[\w/.-]+\s+publicado\s+en\s+el\s+"
         + _FECHA_PO + r"\)")
NOTAS_EN_LINEA = _NOTA
NOTAS = r"^(?:" + _NOTA + r")$"


def _qro(nombre: str, sigla: str, ruta: str, **kw) -> object:
    # El índice es el listado del directorio: el PDF tiene que seguir en él.
    carpeta, archivo = ruta.split("/")
    return ley("queretaro", nombre, sigla, medio=MEDIO, indice=f"{_BASE}{carpeta}/",
               patron=rf"(?:^|/){re.escape(archivo)}$", orden="unico", notas=NOTAS,
               notas_en_linea=NOTAS_EN_LINEA, **kw)


LEYES = [
    _qro("Código Civil del Estado de Querétaro", "CC Qro", "Codigos/COD-ID-02.pdf"),
    # 'Capítulo Quinto / I. De la administración': el subtítulo con numeral romano
    # sería, entre dos artículos, indistinguible de una fracción sin extraer.
    _qro("Código de Procedimientos Civiles del Estado de Querétaro", "CPC Qro",
         "Codigos/COD-ID-04.pdf", titulos_encabezado=("I. De la administración",)),
    _qro("Código Fiscal del Estado de Querétaro", "CF Qro", "Codigos/COD-ID-05.pdf"),
    _qro("Código Urbano del Estado de Querétaro", "CU Qro", "Codigos/COD-ID-06.pdf"),
    _qro("Código Penal para el Estado de Querétaro", "CP Qro", "Codigos/COD-ID-07.pdf"),
    _qro("Código Ambiental del Estado de Querétaro", "CA Qro", "Codigos/COD-ID-01.pdf"),
    _qro("Ley Orgánica del Poder Ejecutivo del Estado de Querétaro", "LOPE Qro",
         "Ley-Org/ORG-ID-08.pdf"),
    _qro("Ley Orgánica del Poder Judicial del Estado de Querétaro", "LOPJ Qro",
         "Ley-Org/ORG-ID-09.pdf"),
    _qro("Ley Orgánica del Poder Legislativo del Estado de Querétaro", "LOPL Qro",
         "Ley-Org/ORG-ID-10.pdf"),
    _qro("Ley Orgánica Municipal del Estado de Querétaro", "LOM Qro", "Ley-Org/ORG-ID-13.pdf"),
    _qro("Ley Orgánica de la Fiscalía General del Estado de Querétaro", "LOFG Qro",
         "Ley-Org/ORG-ID-03.pdf"),
    _qro("Ley Orgánica del Tribunal de Justicia Administrativa del Estado de Querétaro",
         "LOTJA Qro", "Ley-Org/ORG-ID-11.pdf"),
    _qro("Ley Orgánica del Tribunal Electoral del Estado de Querétaro", "LOTE Qro",
         "Ley-Org/ORG-ID-12.pdf"),
    _qro("Código de Ética del Poder Legislativo del Estado de Querétaro", "CEPL Qro",
         "Codigos/COD-ID-03.pdf"),
    _qro("Ley Orgánica de la Agencia de Energía del Estado de Querétaro", "LOAE Qro",
         "Ley-Org/ORG-ID-01.pdf"),
    _qro("Ley Orgánica de la Escuela Normal del Estado de Querétaro", "LOEN Qro",
         "Ley-Org/ORG-ID-02.pdf"),
    _qro("Ley Orgánica de la Universidad Autónoma de Querétaro", "LOUAQ",
         "Ley-Org/ORG-ID-04.pdf", clave="ley-organica-de-la-universidad-autonoma-de-queretaro"),
    _qro("Ley Orgánica de la Universidad Tecnológica de Querétaro", "LOUTEQ",
         "Ley-Org/ORG-ID-05.pdf", clave="ley-organica-de-la-universidad-tecnologica-de-queretaro"),
    _qro("Ley Orgánica del Centro de Conciliación Laboral del Estado de Querétaro", "LOCCL Qro",
         "Ley-Org/ORG-ID-06.pdf"),
    _qro("Ley Orgánica del Colegio de Bachilleres del Estado de Querétaro", "LOCB Qro",
         "Ley-Org/ORG-ID-07.pdf"),
]
