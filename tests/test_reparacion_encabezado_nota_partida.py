"""Guanajuato (Código de Procedimientos Civiles): la nota de un encabezado partida
en dos renglones dentro del bloque, y el nombre de capítulo que envuelve en un
segundo renglón en minúscula, son estructura y no texto del artículo anterior."""
from extractor.parsers.articulado import parse_texto

NOTAS = r"^\((?:REFORMAD|ADICIONAD)[^()]*\)$"
import re

NP = re.compile(NOTAS)


def _parse(t):
    return parse_texto(t, huecos=True, estatal=True, notas=NP, notas_previas=NP)


def test_nota_de_encabezado_partida_en_dos_renglones():
    t = """\
Artículo 1.- Texto uno.
(ADICIONADO CON LAS SECCIONES Y ARTÍCULOS QUE LO INTEGRAN,
P.O. 27 DE DICIEMBRE DE 2011)
CAPÍTULO V
Disposiciones Especiales
(ADICIONADA CON LOS ARTÍCULOS QUE LA INTEGRAN,
P.O. 27 DE DICIEMBRE DE 2011)
SECCIÓN PRIMERA
Guarda y Custodia
(ADICIONADO, P.O. 27 DE DICIEMBRE DE 2011)
Artículo 2.- Texto dos.
"""
    u1, u2 = _parse(t)
    assert "QUE LA INTEGRAN" not in u1.cuerpo
    assert "P.O. 27" not in u2.capitulo
    assert u2.capitulo.endswith("Disposiciones Especiales")


def test_nombre_de_capitulo_envuelto_en_minuscula():
    t = """\
Artículo 1.- Texto uno.
(REFORMADA SU DENOMINACIÓN, P.O. 5 DE FEBRERO DE 1981)
CAPITULO IX.
Disposiciones sobre testamentarias e intestados cuyo caudal aparente no
exceda de la cuantía fijada en el Artículo 23 de este Código.
Artículo 2.- Texto dos.
"""
    u1, u2 = _parse(t)
    assert "exceda" not in u1.cuerpo
    assert "exceda de la cuantía" in u2.capitulo
