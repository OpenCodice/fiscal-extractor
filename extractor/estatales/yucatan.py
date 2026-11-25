"""Yucatán: la Unidad de Servicios Técnico-Legislativos del Congreso del Estado.

El Congreso (`congresoyucatan.gob.mx/legislacion/{codigos,leyes}`) publica una
tabla por categoría con el PDF vigente de cada ordenamiento (y su versión en
Word). El nombre del PDF es un hash fijo por ley más la fecha de la última
actualización ('…_2026-10-22.pdf') o, en las más viejas, un nombre estable
('ley_46.pdf'): el patrón de cada ley es ese hash o nombre, sin la fecha.
Cada PDF abre con su portada y su índice y repite en cada página un
encabezado ('H. Congreso del Estado de Yucatán Última Reforma D.O. …'). Las
notas de reforma van en un renglón propio, después de lo que anotan:
'Párrafo reformado D.O. 03-01-2024', 'Artículo adicionado D.O. 07-06-2022'.
"""
import re

from . import ley

MEDIO = "Diario Oficial del Gobierno del Estado de Yucatán"
_BASE = "https://www.congresoyucatan.gob.mx/legislacion/"

# 'Fracción reformada D.O. 28-06-2023', 'Párrafo reformado DO 11-05-2026',
# 'Numeral recorrido (antes fracción VII) D.O. 09-10-2023', 'Fe de Erratas D.O.
# 12/VII/2019': un renglón corto que abre con lo que se anota y lleva 'D.O.' y
# la fecha. El PDF escribe a veces 'Artíuclo' o 'Númeral'.
_OBJETO = (r"(?:n[uú]meral(?:es)?|art[íi]u?c?u?los?|p[áa]rrafos?|fracci[óo]n(?:es)?|incisos?|"
           r"cap[íi]tulos?|secci[óo]n(?:es)?|t[íi]tulos?|libros?|apartados?|bases?|"
           r"denominaci[óo]n|ep[íi]grafe|subincisos?|disposici[óo]n|transitorios?|letras?|"
           r"se\s+(?:modifica|recorre|adiciona|reforma|deroga)|nota\s+aclaratoria|"
           r"fe\s+de\s+erratas)")
NOTAS = (r"^(?i:(?!art[íi]culo\s+\d)" + _OBJETO + r"\b[^\n]{0,100}?\bD\.?\s?O\.?\s*\d[^\n]{0,80})$")


def _yuc(nombre: str, sigla: str, carpeta: str, archivo: str, **kw) -> object:
    # El índice es la tabla de la categoría; `archivo` es el hash (o nombre) del
    # PDF, que no cambia con la fecha del final.
    return ley("yucatan", nombre, sigla, medio=MEDIO, indice=f"{_BASE}{carpeta}",
               patron=rf"/storage/legislacion/{carpeta}/{archivo}(?:_\d{{4}}-\d{{2}}-\d{{2}})?\.pdf$",
               orden="unico", notas=NOTAS, **kw)


def _cod(nombre, sigla, archivo, **kw):
    return _yuc(nombre, sigla, "codigos", archivo, **kw)


def _ley(nombre, sigla, archivo, **kw):
    return _yuc(nombre, sigla, "leyes", archivo, **kw)


LEYES = [
    _cod("Código Civil del Estado de Yucatán", "CC Yuc", "ca9da342d9e6c5faf13d9e39e9ec6591"),
    _cod("Código Penal del Estado de Yucatán", "CP Yuc", "8203bd322be5e97fcb3a51358afe2e8a"),
    _cod("Código de Familia para el Estado de Yucatán", "CF Yuc", "d474fca229d7858e2f1156c9c626a090"),
    _cod("Código Fiscal del Estado de Yucatán", "CFis Yuc", "5c6e68c9b7bea85e9384441c5a6e73ac"),
    _ley("Ley de Gobierno de los Municipios del Estado de Yucatán", "LGM Yuc",
         "255eec4eb35693e90da2e2bc4ab466f5"),
    _ley("Ley de Gobierno del Poder Legislativo del Estado de Yucatán", "LGPL Yuc",
         "5964b19d58ef965b908ef20705b1e772"),
    _ley("Ley de Instituciones y Procedimientos Electorales del Estado de Yucatán", "LIPE Yuc",
         "b09323d890b610a39ceef86569c88174"),
    _ley("Ley del Sistema de Medios de Impugnación en Materia Electoral del Estado de Yucatán",
         "LSMIME Yuc", "a6b2a1080222f1ca93ed410644e15d6e"),
    _ley("Ley de Responsabilidades Administrativas del Estado de Yucatán", "LRA Yuc",
         "7d1932a70d6d511d202eb3b093cceaa8"),
    _ley("Ley de lo Contencioso Administrativo del Estado de Yucatán", "LCA Yuc",
         "d43b55276abeebf37c1019df77f62312"),
    _ley("Ley de Educación del Estado de Yucatán", "LE Yuc", "7314a13cd808930fc4745f90ea39e404"),
    _ley("Ley de Seguridad Pública del Estado de Yucatán", "LSP Yuc", "ley_46"),
]

_INDICE_TRANSITORIOS = ("El índice del PDF termina con el rótulo «TRANSITORIOS» y el extractor "
                        "corta el texto ahí: no queda ningún artículo.")

FUERA = [
    (_cod("Código de la Administración Pública de Yucatán", "CAP Yuc",
          "16e5c95db63b190a1b8ab32a772fc24a", clave="codigo-de-la-administracion-publica"),
     _INDICE_TRANSITORIOS),
    (_ley("Ley de Asentamientos Humanos, Ordenamiento Territorial y Desarrollo Urbano del Estado de Yucatán",
          "LAHOTDU Yuc", "62e8f5b3cd953719619c0cdb71e7b094"), _INDICE_TRANSITORIOS),
    (_ley("Ley de Salud del Estado de Yucatán", "LS Yuc", "5f535c442f714fdd95623393b00a52f6"),
     _INDICE_TRANSITORIOS),
    (_ley("Ley de los Trabajadores al Servicio del Estado y Municipios de Yucatán", "LTSEM Yuc",
          "e5ab497f87b8dad56532e95c7f5cf769",
          clave="ley-de-los-trabajadores-al-servicio-del-estado-y-municipios"),
     _INDICE_TRANSITORIOS),
    (_ley("Ley Orgánica del Poder Judicial del Estado de Yucatán", "LOPJ Yuc",
          "9b61e60c8013d660df1fc8ecd6a2d5a0"),
     "Los títulos de sus capítulos y secciones ('CAPÍTULO ÚNICO.- DISPOSICIONES GENERALES') "
     "quedan pegados al final del artículo anterior."),
    (_ley("Ley de la Fiscalía General del Estado de Yucatán", "LFG Yuc",
          "fcd320973e8e24d5aae7c6e28c96761b"),
     "El último artículo absorbe el decreto de expedición y su exposición de motivos."),
    (_ley("Ley del Sistema Estatal Anticorrupción de Yucatán", "LSEA Yuc",
          "c1fc8306e64f7bcc9a8d83df15c04629", clave="ley-del-sistema-estatal-anticorrupcion"),
     "Los títulos de sus secciones quedan pegados al artículo anterior y el último artículo "
     "absorbe los decretos de reforma que siguen a la ley."),
]
