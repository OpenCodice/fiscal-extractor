"""Nuevo León: el H. Congreso del Estado (hcnl.gob.mx, «Trabajo legislativo»).

Publica el texto vigente de cada ley en una ruta fija bajo
`trabajo_legislativo/leyes/pdf/` y lo enlaza desde dos páginas índice: `leyes/`
(las leyes) y `leyes/codigos.php` (los códigos). Todos los href llevan tras
`.pdf` la fecha de la última reforma como consulta ('….pdf?2026-06-26'), por lo
que cada ley usa `consulta=True`; junto a cada PDF hay una versión Word (que no
se usa). Las notas de reforma van ANTES de lo que anotan, entre paréntesis y en
mayúsculas ('(REFORMADO, P.O. 08 DE DICIEMBRE DE 2004)'). Algunos PDF repiten al
pie 'Decreto Núm. N expedido por la … Legislatura' (con el número de página o
sin él) y uno repite el nombre de la ley: van en `titulos_encabezado`. Los href
con un espacio en la consulta ('….pdf?2026-03- 9') no se pueden descargar, y esas
leyes están en `FUERA`.
"""
import re

from . import ley

MEDIO = "Periódico Oficial del Estado de Nuevo León"
_BASE = "https://www.hcnl.gob.mx/trabajo_legislativo/leyes/"
_LEYES = _BASE
_CODIGOS = _BASE + "codigos.php"

# Notas de reforma: se ajustan a lo que cite el PDF (ver pruebas).
# Todas van ANTES de lo que anotan, entre paréntesis y en MAYÚSCULAS: '(REFORMADO,
# P.O. 08 DE DICIEMBRE DE 2004)', '(ADICIONADA, P.O. …)', '(REFORMADA SU
# DENOMINACIÓN, P.O. …)', '(F. DE E., P.O. …)'. A veces envuelven a otro renglón.
NOTAS = (r"^\((?:REFORMAD|REFORMDA|ADICIONAD|ADICIOND|DEROGAD|RECORRID|REUBICAD|SE\s+DEROGA"
         r"|F\.\s?DE\s?E\.|N\.\s?DE\s?E\.|FE\s+DE\s+ERRATAS|ADCIONAD|SE\s+SUSPENDE"
         r"|\(REFORMAD|P\.\s?O\.\s?\d|P[ÁA]RRAFO\s+\w+\s+(?:REFORMAD|ADICIONAD|DEROGAD))")
NOTAS_PREVIAS = NOTAS


def _pie(decreto: int, legislatura: str, numerado: bool = True) -> tuple[str, ...]:
    """Pie de página de las leyes que lo llevan: 'Decreto Núm. 314 expedido por
    la LXXIV Legislatura 42' (o sin el número de página, que va en otro renglón).
    `titulos_encabezado` quita renglones exactos, así que se listan todos."""
    base = f"Decreto Núm. {decreto} expedido por la {legislatura} Legislatura"
    return (base, *(f"{base} {n}" for n in range(1, 600))) if numerado else (base,)


def _nl(nombre: str, sigla: str, archivo: str, indice: str = _LEYES, **kw) -> object:
    return ley("nuevo-leon", nombre, sigla, medio=MEDIO, indice=indice,
               patron=rf"/leyes/pdf/{re.escape(archivo)}\.pdf", orden="unico",
               consulta=True, notas=NOTAS, notas_previas=NOTAS_PREVIAS, **kw)


LEYES = [
    _nl("Código de Ética para el Congreso del Estado de Nuevo León", "CE Congreso NL",
        "CODIGO%20DE%20ETICA%20PARA%20EL%20CONGRESO%20DEL%20ESTADO%20DE%20NUEVO%20LEON", _CODIGOS,
        titulos_encabezado=_pie(479, "LXXVI")),
    _nl("Código Fiscal del Estado de Nuevo León", "CF NL",
        "CODIGO%20FISCAL%20DEL%20ESTADO%20DE%20NUEVO%20LEON", _CODIGOS),
    _nl("Ley Orgánica del Poder Legislativo del Estado de Nuevo León", "LOPL NL",
        "LEY%20ORGANICA%20DEL%20PODER%20LEGISLATIVO"),
    _nl("Ley Orgánica de la Fiscalía General de Justicia del Estado de Nuevo León", "LOFGJ NL",
        "LEY%20ORGANICA%20DE%20LA%20FISCALIA%20GENERAL%20DE%20JUSTICIA%20DEL%20ESTADO%20DE%20NUEVO%20LEON",
        titulos_encabezado=_pie(314, "LXXIV")),
    _nl("Ley Electoral para el Estado de Nuevo León", "LE NL",
        "LEY%20ELECTORAL%20PARA%20EL%20ESTADO%20DE%20NUEVO%20LEON"),
    _nl("Ley de Seguridad Pública para el Estado de Nuevo León", "LSP NL",
        "LEY%20DE%20SEGURIDAD%20PUBLICA%20PARA%20EL%20ESTADO%20DE%20NUEVO%20LEON"),
    _nl("Ley de Juicio Político del Estado de Nuevo León", "LJP NL",
        "LEY%20DE%20JUICIO%20POLITICO%20DEL%20ESTADO%20DE%20NUEVO%20LEON"),
    _nl("Ley de Fiscalización Superior del Estado de Nuevo León", "LFS NL",
        "LEY%20DE%20FISCALIZACION%20SUPERIOR%20DEL%20ESTADO%20DE%20NUEVO%20LEON"),
    _nl("Ley de Responsabilidad Patrimonial del Estado y Municipios de Nuevo León", "LRP NL",
        "LEY%20DE%20RESPONSABILIDAD%20PATRIMONIAL%20DEL%20ESTADO%20Y%20MUNICIPIOS",
        clave="ley-de-responsabilidad-patrimonial"),
    _nl("Ley de Adquisiciones, Arrendamientos y Contratación de Servicios del Estado de Nuevo León", "LAACS NL",
        "LEY%20DE%20ADQUISICIONES%2C%20ARRENDAMIENTOS%20Y%20CONTRATACION%20DE%20SERVICIOS%20DEL%20ESTADO%20DE%20NUEVO%20LEON"),
    _nl("Ley del Notariado del Estado de Nuevo León", "LN NL",
        "LEY%20DEL%20NOTARIADO%20DEL%20ESTADO%20DE%20NUEVO%20LEON"),
    _nl("Ley de Protección Civil para el Estado de Nuevo León", "LPC NL",
        "LEY%20DE%20PROTECCION%20CIVIL%20PARA%20EL%20ESTADO%20DE%20NUEVO%20LEON"),
    _nl("Ley del Registro Civil para el Estado de Nuevo León", "LRC NL",
        "LEY%20DEL%20REGISTRO%20CIVIL%20PARA%20EL%20ESTADO%20DE%20NUEVO%20LEON",
        titulos_encabezado=("Ley del Registro Civil para el Estado de Nuevo León",)),
    _nl("Ley de Justicia Cívica para el Estado de Nuevo León", "LJC NL",
        "LEY%20DE%20JUSTICIA%20CIVICA%20PARA%20EL%20ESTADO%20DE%20NUEVO%20LEON"),
]

# Lo que se consideró y no queda fiel con las opciones de `ley()` (el parser no se toca).
FUERA = [
    (
    _nl("Ley Orgánica de la Administración Pública para el Estado de Nuevo León", "LOAP NL",
            "LEY%20ORGANICA%20DE%20LA%20ADMINISTRACION%20PUBLICA%20PARA%20EL%20ESTADO%20DE%20NUEVO%20LEON",
            sin_consulta=True),
     "su PDF ya se descarga (se ignora la consulta inválida del enlace); falta construirlo y auditarlo"),
    (
    _nl("Ley de Responsabilidades Administrativas del Estado de Nuevo León", "LRA NL",
            "LEY%20DE%20RESPONSABILIDADES%20ADMINISTRATIVAS%20DEL%20ESTADO%20DE%20NUEVO%20LEON",
            titulos_encabezado=_pie(144, "LXXV"),
            sin_consulta=True),
     "su PDF ya se descarga (se ignora la consulta inválida del enlace); falta construirlo y auditarlo"),
    (
    _nl("Ley de Asentamientos Humanos, Ordenamiento Territorial y Desarrollo Urbano para el Estado de Nuevo León", "LAHOTDU NL",
            "LEY%20DE%20ASENTAMIENTOS%20HUMANOS%20ORDENAMIENTO%20TERRITORIAL%20Y%20DESARROLLO%20URBANO%20PARA%20EL%20ESTADO%20DE%20NUEVO%20LEON",
            titulos_encabezado=_pie(312, "LXXIV", numerado=False),
            sin_consulta=True),
     "su PDF ya se descarga (se ignora la consulta inválida del enlace); falta construirlo y auditarlo"),
    (
    _nl("Código Penal para el Estado de Nuevo León", "CP NL",
            "CODIGO%20PENAL%20PARA%20EL%20ESTADO%20DE%20%20NUEVO%20LEON", _CODIGOS),
     'un capítulo de delitos electorales (artículos 208 Bis a 208 Bis II, todos derogados) queda sin artículo y su encabezado se pierde, así que el texto no queda completo'),
    (
    _nl("Código de Procedimientos Civiles del Estado de Nuevo León", "CPC NL",
            "CODIGO%20DE%20PROCEDIMIENTOS%20CIVILES%20DEL%20ESTADO%20DE%20NUEVO%20LEON", _CODIGOS),
     "los artículos 'Bis I', 'Bis II'… (por ejemplo 180 Bis I a X) se leen como un solo artículo 'Bis' y no quedan separados fielmente"),
    (
    _nl("Ley Orgánica del Poder Judicial del Estado de Nuevo León", "LOPJ NL",
            "LEY%20ORGANICA%20DEL%20PODER%20JUDICIAL%20DEL%20ESTADO%20DE%20NUEVO%20LEON"),
     "el artículo 5 Bis no puede verificarse contra el PDF porque su rótulo ('5o Bis') no coincide con el del PDF"),
    (
    _nl("Ley de Gobierno Municipal del Estado de Nuevo León", "LGM NL",
            "LEY%20DE%20GOBIERNO%20MUNICIPAL%20DEL%20ESTADO%20DE%20NUEVO%20LEON",
            sin_consulta=True),
     "el PDF escribe 'ARTíCULO 110 Bis' con una í minúscula y el artículo 110 Bis se confunde con el 110 y sus 'Bis I' a 'Bis IV'"),
    (
    _nl("Ley de Hacienda del Estado de Nuevo León", "LH NL",
            "LEY%20DE%20HACIENDA%20DEL%20ESTADO%20DE%20NUEVO%20LEON"),
     'varios encabezados de capítulo con nota de reforma, un título en minúsculas y una tabla al final de un artículo no quedan en su sitio'),
    (
    _nl("Ley de Justicia Administrativa para el Estado y Municipios de Nuevo León", "LJA NL",
            "LEY%20DE%20JUSTICIA%20ADMINISTRATIVA%20PARA%20EL%20ESTADO%20Y%20MUNICIPIOS",
            clave="ley-de-justicia-administrativa-para-el-estado-y-municipios",
            sin_consulta=True),
     "el artículo 6 Bis no puede verificarse contra el PDF porque su rótulo ('6o Bis') no coincide con el del PDF"),
    (
    _nl("Ley de Transparencia y Acceso a la Información Pública del Estado de Nuevo León", "LTAIP NL",
            "LEY%20DE%20TRANSPARENCIA%20Y%20ACCESO%20A%20LA%20INFORMACION%20PUBLICA%20DEL%20ESTADO%20DE%20NUEVO%20LEON"),
     "un encabezado ('Capítulo ll Bis', con letras ele en vez de números romanos) no se reconoce y queda pegado al final del artículo 76"),
    (
    _nl("Código Civil para el Estado de Nuevo León", "CC NL",
            "CODIGO%20CIVIL%20PARA%20EL%20ESTADO%20DE%20NUEVO%20LEON%20", _CODIGOS),
     "el PDF numera sus artículos como 'Art. 22.-' y el extractor solo reconoce 'Artículo'"),
]

# Reparación autónoma (scripts/reparacion.py promover, 2026-11-18): estas leyes
# de FUERA ya quedan con build y auditar limpios sobre su PDF; la vigilancia
# las da de alta tras su revisión completa.
_A_LEYES = {
    "nuevo-leon/codigo-penal",
    "nuevo-leon/ley-de-hacienda",
    "nuevo-leon/ley-de-transparencia-y-acceso-a-la-informacion-publica",
    "nuevo-leon/ley-organica-del-poder-judicial",
}
LEYES = list(LEYES) + [d for d, _ in FUERA if d.clave in _A_LEYES]
FUERA = [(d, m) for d, m in FUERA if d.clave not in _A_LEYES]
