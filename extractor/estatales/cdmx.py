"""Ciudad de México: la Consejería Jurídica y de Servicios Legales.

Publica el texto vigente de cada ley (el del Congreso se queda atrás, como en
la Constitución). El nombre del PDF lleva un número de edición que cambia con
cada reforma ('CODIGO_CIVIL_PARA_EL_DF_15.4.pdf') y su página de códigos o de
leyes enlaza solo el vigente. Muchas notas de reforma van ANTES de lo que
anotan ('(REFORMADO, G.O. 25 DE MAYO DE 2000)' sobre el artículo o el párrafo).
Al pie de cada página se repite el nombre de la Consejería.
"""
from . import ley

MEDIO = "Gaceta Oficial de la Ciudad de México"
_BASE = "https://data.consejeria.cdmx.gob.mx/index.php/leyes/"
# Dos estilos de nota de reforma, a veces en el mismo código:
# - antes de lo que anotan, entre paréntesis y en MAYÚSCULAS: '(REFORMADO, G.O.
#   25 DE MAYO DE 2000)', '(F. DE E., D.O.F. …)', '(DEROGADO POR ARTICULO …)';
# - después (las reformas recientes), sin paréntesis o con el verbo en
#   minúsculas: 'Párrafo reformado G.O. CDMX 08/12/23', 'Fracción reformada,
#   G.O.CDMX 29 de noviembre de 2024', '(artículo reformado, G.O.CDMX …)'.
# Las demás llevan el medio (G.O., D.O.F., GODF) y lo que se hizo.
_MEDIO = r"(?:G\.\s?O\.|D\.\s?O\.\s?F\.|GODF)"
_VERBO = r"(?:REFORMAD|ADICIONAD|DEROGAD|REUBICAD|RECORRID|ACLARAD)"
# Las previas, en mayúsculas, a veces envuelven y el medio queda en el renglón
# siguiente: '(DEROGADO POR ARTICULO SEGUNDO TRANSITORIO DE LA LEY FEDERAL'.
NOTAS_PREVIAS = rf"^\((?:[A-ZÁÉÍÓÚÑ ]+\s)?(?:{_VERBO}[OA]S?\b|F\.\s?DE\s?E\.|FE DE ERRATAS)|^N\.\s?DE\s?E\."
NOTAS = (NOTAS_PREVIAS + rf"|^\((?=[^)]*{_MEDIO})[^)]*?(?i:{_VERBO}|F\.\s?DE\s?E\.|FE DE ERRATAS)"
         r"|^(?i:P[áa]rrafos?|Fracci[óo]n(?:es)?|Art[íi]culos?|Incisos?|"
         r"Cap[íi]tulos?|Denominaci[óo]n|Transitorios?|T[íi]tulos?|Secci[óo]n(?:es)?|"
         rf"Numeral(?:es)?|Apartados?)\s+(?i:{_VERBO}[oa]s?)\b[^\n]*?{_MEDIO}"
         # Fe de erratas y erratas señaladas, sin verbo: 'Fe de Erratas G.O. CDMX
         # 13/11/2023', 'Sic. G.O. CDMX 07/06/2017'.
         rf"|^(?i:Fe\s+de\s+erratas)\b(?:[^\n]*?{_MEDIO}|\s+\d{{1,2}}/\d{{1,2}}/\d{{4}}$)"
         rf"|^Sic\.\s*{_MEDIO}"
         # Notas del editor: 'N. DE E. EN RELACIÓN CON LA ENTRADA EN VIGOR …'.
         r"|^N\.\s?DE\s?E\.")


def _cdmx(nombre: str, sigla: str, pagina: str, archivo: str, **kw) -> object:
    return ley("cdmx", nombre, sigla, medio=MEDIO, indice=_BASE + pagina, orden="unico",
               patron=rf"/{archivo}_[\d.]+\.pdf$", notas=NOTAS, notas_previas=NOTAS_PREVIAS,
               titulos_encabezado=("CONSEJERÍA JURÍDICA Y DE SERVICIOS LEGALES",), **kw)


LEYES = [
    _cdmx("Código Civil para el Distrito Federal", "CC CDMX", "codigos",
          "CODIGO_CIVIL_PARA_EL_DF"),
    _cdmx("Código Penal para el Distrito Federal", "CP CDMX", "codigos",
          "CODIGO_PENAL_PARA_EL_DF"),
    _cdmx("Código de Instituciones y Procedimientos Electorales de la Ciudad de México",
          "CIPE CDMX", "codigos", "CODIGO_DE_INSTITUCIONES_Y_PROC_ELECTORALES_CDMX"),
    _cdmx("Ley Orgánica del Congreso de la Ciudad de México", "LOC CDMX", "leyes",
          "LEY_ORGANICA_DEL_CONGRESO_DE_LA_CDMX"),
    _cdmx("Ley Orgánica de Alcaldías de la Ciudad de México", "LOA CDMX", "leyes",
          "LEY_ORGANICA_DE_ALCALDIAS_DE_LA_CDMX"),
    _cdmx("Ley de Acceso de las Mujeres a una Vida Libre de Violencia de la Ciudad de México",
          "LAMVLV CDMX", "leyes",
          "LEY_DE_ACCESO_DE_LAS_MUJERES_A_UNA_VIDA_LIBRE_DE_VIOLENCIA_DE_LA_CDMX"),
    _cdmx("Ley de los Derechos de Niñas, Niños y Adolescentes de la Ciudad de México",
          "LDNNA CDMX", "leyes", "LEY_DERECHOS_NINAS_NINOS_ADOLESCENTES_CDMX"),
]

FUERA = [
    (_cdmx("Código de Procedimientos Civiles para el Distrito Federal", "CPC CDMX", "codigos",
           "Codigo_Procedimientos_Civiles_DF"),
     "Su Título Especial de la Justicia de Paz vuelve a numerar sus artículos desde el 1, "
     "y un archivo por número de artículo no puede guardar dos artículos con el mismo "
     "número."),
]
