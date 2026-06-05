"""Pruebas del parser articulado, con casos diseñados para romperlo.

Cada caso aquí salió de un bug real encontrado al extraer el corpus fiscal:
sufijos en mayúsculas que colisionaban claves, encabezados ARTÍCULO en
mayúsculas (LAdua/LFPCA), el guion terminador confundido con letra, etc.
Se usa `parse_texto` (texto sintético, sin PDF) para aislar la lógica.
"""
import re
from datetime import date

import pytest

from extractor.parsers.articulado import (
    ARTICULO_RE,
    fechas_reforma_en,
    parse_texto,
    NUEVO_RE,
    VERSION_RE,
)


def claves(texto, start=1):
    return [u.clave for u in parse_texto(texto, start=start)]


# --------------------------------------------------------------------------- #
# Secuencia y filtrado de citas
# --------------------------------------------------------------------------- #
def test_secuencia_basica():
    texto = "Artículo 1o.- Uno.\nArtículo 2o.- Dos.\nArtículo 3o.- Tres."
    assert claves(texto) == ["001", "002", "003"]


def test_cita_a_otro_articulo_no_inicia_unidad():
    # "artículo 89" en minúscula (cita) y "Artículo 89" fuera de secuencia: ninguno
    # debe iniciar una unidad nueva.
    texto = (
        "Artículo 1o.- En términos del artículo 89 de la Constitución y del "
        "Artículo 105 de esta Ley, se dispone lo siguiente.\n"
        "Artículo 2o.- Dos."
    )
    assert claves(texto) == ["001", "002"]


def test_articulo_derogado_conserva_secuencia():
    texto = (
        "Artículo 1o.- Uno.\n"
        "Artículo 2o.- (Se deroga).\n"
        "Artículo 3o.- Tres."
    )
    us = parse_texto(texto)
    assert [u.clave for u in us] == ["001", "002", "003"]
    assert us[1].derogado is True
    assert us[0].derogado is False


# --------------------------------------------------------------------------- #
# Sufijos: letra, ordinal, combinados, mayúsculas
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("encabezado,clave_esp", [
    ("Artículo 4o.-A.- Texto.", "004-a"),
    ("Artículo 14-A.- Texto.", "014-a"),
    ("Artículo 15-A. Texto.", "015-a"),
    ("Artículo 111 Bis.- Texto.", "111-bis"),
    ("Artículo 156-Bis. Texto.", "156-bis"),
    ("Artículo 20-Ter. Texto.", "020-ter"),
    ("Artículo 17-H Bis. Texto.", "017-h-bis"),
    ("Artículo 32-B Quáter. Texto.", "032-b-quater"),
    ("Artículo 32-B Quinquies. Texto.", "032-b-quinquies"),
])
def test_clave_de_sufijo(encabezado, clave_esp):
    # Se antepone el artículo base (bare) para que la variante sea aceptada, y se
    # parsea desde ese número (el articulado real arranca en 1, no en el base).
    base_num = int(re.match(r"\D+(\d+)", encabezado).group(1))
    texto = f"Artículo {base_num}.- Base.\n{encabezado}"
    cs = claves(texto, start=base_num)
    assert clave_esp in cs, f"{encabezado!r} → {cs}"


def test_ordinal_en_mayusculas_no_colisiona():
    # Bug real (LIVA/LIEPS): 'BIS/TER/QUÁTER' en mayúsculas colapsaban a una clave.
    texto = (
        "Artículo 18.- Base.\n"
        "Artículo 18-H.- H.\n"
        "Artículo 18-H BIS. Uno.\n"
        "Artículo 18-H TER. Dos.\n"
        "Artículo 18-H QUÁTER. Tres.\n"
        "Artículo 18-H QUINTUS. Cuatro."
    )
    cs = claves(texto, start=18)
    assert cs == ["018", "018-h", "018-h-bis", "018-h-ter", "018-h-quater", "018-h-quintus"]
    assert len(cs) == len(set(cs)), "claves duplicadas → colisión de archivos"


def test_ordinal_con_numeral_no_colisiona():
    # Bug real (LAdua): 'ARTICULO 137 bis 1..9' (ordinal + numeral) colapsaban a
    # una sola clave '137-bis'.
    texto = (
        "Artículo 137.- Base.\n"
        "ARTICULO 137 bis 1.- Uno.\n"
        "ARTICULO 137 bis 2.- Dos.\n"
        "ARTICULO 137 bis 9.- Nueve."
    )
    cs = claves(texto, start=137)
    assert cs == ["137", "137-bis-1", "137-bis-2", "137-bis-9"]
    assert len(cs) == len(set(cs))


def test_encabezado_en_mayusculas():
    # Bug real (LAdua 'ARTICULO', LFPCA 'ARTÍCULO'): encabezados en mayúsculas.
    texto = "ARTICULO 1o. Uno.\nARTÍCULO 2o.- Dos.\nARTICULO 3o. Tres."
    assert claves(texto) == ["001", "002", "003"]


def test_minuscula_no_es_encabezado():
    # 'artículo' en minúscula es cita, nunca encabezado.
    assert ARTICULO_RE.match("artículo 1o. de esta Ley") is None
    assert ARTICULO_RE.match("Artículo 1o.- Texto") is not None
    assert ARTICULO_RE.match("ARTÍCULO 1o.- Texto") is not None


def test_guion_terminador_no_es_letra():
    # Bug real: 'Artículo 80.- A quien...' tomaba la 'A' del cuerpo como letra.
    us = parse_texto("Artículo 79.- Uno.\nArtículo 80.- A quien cometa algo.", start=79)
    assert [u.clave for u in us] == ["079", "080"]
    assert us[1].letra == "", "el guion terminador se confundió con letra-sufijo"


# --------------------------------------------------------------------------- #
# Fechas de reforma
# --------------------------------------------------------------------------- #
def test_fechas_reforma_simple_y_encadenada():
    assert fechas_reforma_en("Reformado DOF 12-11-2021") == [date(2021, 11, 12)]
    # Encadenadas con coma en una sola cláusula DOF.
    fechas = fechas_reforma_en("Reformado DOF 04-12-2006, 10-06-2011")
    assert fechas == [date(2006, 12, 4), date(2011, 6, 10)]


def test_fechas_reforma_unicas_y_ordenadas():
    texto = "x DOF 10-06-2011 y DOF 05-02-2017 y otra vez DOF 10-06-2011"
    assert fechas_reforma_en(texto) == [date(2011, 6, 10), date(2017, 2, 5)]


def test_unidad_acumula_fechas_de_su_cuerpo():
    texto = (
        "Artículo 1o.- Uno.\n_Párrafo reformado DOF 12-11-2021_\n"
        "_Artículo reformado DOF 09-12-2019_"
    )
    u = parse_texto(texto)[0]
    assert u.fechas_reforma == [date(2019, 12, 9), date(2021, 11, 12)]
    assert u.ultima_reforma == date(2021, 11, 12)


# --------------------------------------------------------------------------- #
# Frontera de Transitorios
# --------------------------------------------------------------------------- #
def test_corta_en_transitorios():
    texto = (
        "Artículo 1o.- Uno.\nArtículo 2o.- Dos.\n"
        "TRANSITORIOS\nArtículo Primero.- Esto no es articulado."
    )
    assert claves(texto) == ["001", "002"]


# --------------------------------------------------------------------------- #
# Detección de versión (regex de portada)
# --------------------------------------------------------------------------- #
def test_version_ultima_reforma():
    m = VERSION_RE.search("... UNIÓN Última Reforma DOF 09-04-2026")
    assert m and (m.group(3), m.group(2), m.group(1)) == ("2026", "04", "09")


def test_version_nuevo_reglamento_fallback():
    assert VERSION_RE.search("... Nuevo Reglamento DOF 02-04-2014") is None
    m = NUEVO_RE.search("... UNIÓN Nuevo Reglamento DOF 02-04-2014")
    assert m and m.group(3) == "2014"
