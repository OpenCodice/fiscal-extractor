"""Guanajuato: el Congreso del Estado (Instituto de Investigaciones Legislativas).

Publica el texto vigente de cada ley en https://www.congresogto.gob.mx/leyes y
/codigos (una tabla con una fila por ley). Esas páginas no responden desde
fuera de México, así que el índice se lee por egress-mx (`via_indice="mx"`); los
PDF están en un bucket S3 público y se descargan directo. El nombre del PDF
lleva la sigla de la ley y la fecha de su última reforma ('LOPEEG_REF_03Nov2026.pdf',
dentro de `…/reforma/pdf/<id>/`), de modo que el patrón se ata a la sigla; el
mismo índice enlaza también el Periódico Oficial (`reforma/periodico_pdf/`), que
el patrón no admite. Algunas leyes se publican con un nombre opaco (un uuid) que
cambia con cada reforma: solo se pueden fijar en el índice de códigos, donde es
el único así; las de /leyes van a `FUERA`.

Cada página repite arriba el membrete del Instituto con la fecha de la última
reforma. Las notas de reforma van en su propio renglón, ANTES de lo que anotan,
entre paréntesis y en MAYÚSCULAS: '(REFORMADO, P.O. 3 DE JUNIO DE 2011)',
'(PÁRRAFO ADICIONADO, P.O. 10 DE ABRIL DE 2026)', a veces dos juntas '(REFORMADO,
P.O. 14 DE ABRIL DE 2023) (F. DE E., P.O. 24 DE ABRIL DE 2023)'.
"""
from . import ley

MEDIO = "Periódico Oficial del Gobierno del Estado de Guanajuato"
_LEYES = "https://www.congresogto.gob.mx/leyes"
_CODIGOS = "https://www.congresogto.gob.mx/codigos"

# '(REFORMADA, P.O. 3 DE JUNIO DE 2011)', '(RECORRIDA EN SU ORDEN, P.O. …)',
# '(DEROGADO PÁRRAFO TERCERO, P.O. …)', '(ADICIONADO CON SU SECCIÓN Y LOS
# ARTÍCULOS QUE LA INTEGRAN, P.O. …)' (a veces partida en dos renglones),
# '(PARRAFO REFORMADO, 30 DICIEMBRE 2022)', una o varias seguidas, y las notas
# del editor 'N. DE E. EN RELACIÓN CON …' (sin paréntesis, en mayúsculas).
_VERBO = (r"(?:REFORMAD|ADICIONAD|DEROGAD|REUBICAD|RECORRID|CAMBIAD|ACLARAD|"
          r"F\.\s?DE\s?E\b|FE\s+DE\s+ERRATAS)")
_UNA = rf"\((?:[A-ZÁÉÍÓÚÑ.,\s]*?){_VERBO}[^()]*?(?:P\.\s?O\.|\b\d{{4}}\b)[^()]*\)"
NOTAS_EN_LINEA = (rf"{_UNA}(?:[ \t]*{_UNA})*"
                  r"|N\.\s?DE\s?E\.[A-ZÁÉÍÓÚÑ0-9 ,.\n]*?\.(?=\n|$)")
# A veces el PDF omite el paréntesis de apertura de la nota, que va sola en su
# renglón: 'REFORMADO [N. DE E. ESTE PÁRRAFO], P.O. 5 DE DICIEMBRE DE 2017)'.
_SIN_ABRIR = (rf"(?:REFORMAD|ADICIONAD|DEROGAD)[OA]S?\b[^()\n]*?"
              r"(?:P\.\s?O\.|\b\d{4}\b)[^()\n]*\)")
# La nota del editor entre corchetes, que el PDF pone tras el último texto de un
# artículo y antes del rótulo del siguiente y que comenta lo anterior: '[N. DE E.
# VÉASE LITERALIDAD DEL DECRETO … PÁGINA 50.]', a veces en dos renglones.
_EDITOR_CORCHETES = r"(?m:^)\[N\.\s?DE\s?E\.[^\[\]]*\.\](?=[ \t]*(?:\n|$))"
NOTAS_PREVIAS = rf"^(?:{NOTAS_EN_LINEA}|{_SIN_ABRIR})$"
NOTAS_EN_LINEA = rf"{NOTAS_EN_LINEA}|{_EDITOR_CORCHETES}"
NOTAS = rf"^(?:{NOTAS_EN_LINEA}|{_SIN_ABRIR})$"


def _gto(nombre: str, sigla: str, indice: str, archivo: str, **kw) -> object:
    # `archivo`: la sigla del PDF ('LOPEEG_REF'); `reforma/pdf/` excluye el
    # Periódico Oficial, que el índice enlaza en la misma fila.
    return ley("guanajuato", nombre, sigla, medio=MEDIO, indice=indice, via_indice="mx",
               patron=rf"/reforma/pdf/\d+/{archivo}", orden="unico",
               notas=NOTAS, notas_previas=NOTAS_PREVIAS, notas_en_linea=NOTAS_EN_LINEA, **kw)


LEYES = [
    _gto("Código Fiscal para el Estado de Guanajuato", "CF Gto", _CODIGOS, "CFEG_REF_",
         titulos_encabezado=("Intereses por devoluciones fuera de plazo",
                             "Compensación declarada por el SATEG",
                             "Extinción de créditos fiscales a cargo de entidades paraestatales")),
    _gto("Código de Procedimiento y Justicia Administrativa para el Estado y los Municipios de Guanajuato",
         "CPJA Gto", _CODIGOS, "CPJAEG_",
         clave="codigo-de-procedimiento-y-justicia-administrativa"),
    _gto("Ley Orgánica del Poder Judicial del Estado de Guanajuato", "LOPJ Gto",
         _LEYES, "LOPJEG_REF_"),
    _gto("Ley Orgánica de la Fiscalía General del Estado de Guanajuato", "LOFG Gto",
         _LEYES, "LOFEG_REF_"),
    _gto("Ley Orgánica del Tribunal de Justicia Administrativa del Estado de Guanajuato",
         "LOTJA Gto", _LEYES, "LOTJA_REF_"),
    _gto("Ley de Educación para el Estado de Guanajuato", "LE Gto", _LEYES, "LEEG_REF_"),
    _gto("Ley de Transparencia y Acceso a la Información Pública para el Estado de Guanajuato",
         "LTAIP Gto", _LEYES, "LTAIPEG_REF"),
    _gto("Ley de Coordinación Fiscal del Estado de Guanajuato", "LCF Gto", _LEYES, "LCFEG_REF_"),
    _gto("Ley de Fiscalización Superior del Estado de Guanajuato", "LFS Gto", _LEYES, "LFSEG_",
         titulos_encabezado=("Información de seguimiento",)),
    _gto("Ley del Trabajo de los Servidores Públicos al Servicio del Estado y de los Municipios",
         "LTSP Gto", _LEYES, "LTSPSEYM_REF_"),
    _gto("Ley Orgánica del Centro de Conciliación Laboral del Estado de Guanajuato",
         "LOCCL Gto", _LEYES, "LOCCLEG_"),
]

# Las que no quedaron fieles, y las de /leyes con nombre opaco (uuid), que no se
# pueden atar a un href estable con las opciones de `ley()` (el uuid cambia con
# cada reforma): se declaran para que la reparación las retome.
_UUID = ("Su PDF vigente tiene un nombre opaco (un uuid) que cambia con cada reforma y el "
         "índice enlaza muchos así: no hay manera de distinguirla de las demás.")
FUERA = [
    (_gto("Código Civil para el Estado de Guanajuato", "CC Gto", _CODIGOS, "CCG_REF_"),
     "Tras un capítulo con nota de reforma de su denominación, el artículo con letra («Art. 136-A») no se separa del anterior y queda texto fuera: la extracción no queda fiel."),
    (_gto("Código Penal del Estado de Guanajuato", "CP Gto", _CODIGOS, "CPEG_REF_"),
     "Artículos con sufijo en minúscula («153-a-1», «150 b») y notas de reforma entre un capítulo y su artículo dejan texto fuera: la extracción no queda fiel."),
    (_gto("Código Territorial para el Estado y los Municipios de Guanajuato", "CT Gto",
         _CODIGOS, "CTEG_REF", clave="codigo-territorial", titulos_encabezado=("Fomento de programas",)),
     "Una nota de reforma de denominación antes de un capítulo deja texto fuera del artículo 228: la extracción no queda fiel."),
    (_gto("Ley Orgánica del Poder Ejecutivo para el Estado de Guanajuato", "LOPE Gto",
         _LEYES, "LOPEEG_REF_"),
     "El artículo «3o Bis» (con la o ordinal) no se reconoce como rótulo y queda texto fuera: la extracción no queda fiel."),
    (_gto("Ley de Instituciones y Procedimientos Electorales para el Estado de Guanajuato",
         "LIPE Gto", _LEYES, "LIPEEG_REF"),
     "Un bloque de nota, capítulo y sección adicionados juntos (artículos 398 Bis a 398 Septies) deja texto fuera del artículo 398: la extracción no queda fiel."),
    (ley("guanajuato", "Ley para el Gobierno y Administración de los Municipios del Estado de Guanajuato",
         "LGAM Gto",
         medio=MEDIO, indice=_LEYES, via_indice="mx", patron=r"/reforma/pdf/\d+/c860c0f7",
         orden="unico", notas=NOTAS, notas_previas=NOTAS_PREVIAS),
     _UUID),
    (ley("guanajuato", "Ley Orgánica del Poder Legislativo del Estado de Guanajuato",
         "LOPL Gto", medio=MEDIO, indice=_LEYES, via_indice="mx",
         patron=r"/reforma/pdf/\d+/23084a0d", orden="unico", notas=NOTAS,
         notas_previas=NOTAS_PREVIAS),
     _UUID),
    (ley("guanajuato", "Código de Procedimientos Civiles para el Estado de Guanajuato",
         "CPC Gto", medio=MEDIO, indice=_CODIGOS, via_indice="mx",
         patron=r"/reforma/pdf/\d+/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.pdf$",
         orden="unico", notas=NOTAS, notas_previas=NOTAS_PREVIAS),
     "Su PDF vigente tiene un nombre opaco (un uuid) y su extracción deja texto fuera en tres artículos (675, 704, 843): no queda fiel."),
]

# Reparación autónoma (scripts/reparacion.py promover, 2026-11-19): estas leyes
# de FUERA ya quedan con build y auditar limpios sobre su PDF; la vigilancia
# las da de alta tras su revisión completa.
_A_LEYES = {
    "guanajuato/codigo-de-procedimientos-civiles",
    "guanajuato/codigo-penal",
    "guanajuato/codigo-territorial",
    "guanajuato/ley-de-instituciones-y-procedimientos-electorales",
    "guanajuato/ley-organica-del-poder-ejecutivo",
    "guanajuato/ley-organica-del-poder-legislativo",
    "guanajuato/ley-para-el-gobierno-y-administracion-de-los-municipios",
}
LEYES = list(LEYES) + [d for d, _ in FUERA if d.clave in _A_LEYES]
FUERA = [(d, m) for d, m in FUERA if d.clave not in _A_LEYES]

# Reparación autónoma (scripts/reparacion.py promover, 2026-11-20): estas leyes
# de FUERA ya quedan con build y auditar limpios sobre su PDF; la vigilancia
# las da de alta tras su revisión completa.
_A_LEYES = {
    "guanajuato/codigo-civil",
}
LEYES = list(LEYES) + [d for d, _ in FUERA if d.clave in _A_LEYES]
FUERA = [(d, m) for d, m in FUERA if d.clave not in _A_LEYES]
