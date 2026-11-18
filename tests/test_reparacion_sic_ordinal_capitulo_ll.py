"""Nuevo León: '(sic)' en el rótulo, '6° Bis' con nota previa y 'Capítulo ll Bis'."""
import re

from extractor.parsers.articulado import CAPITULO_RE, parse_texto

SIC = """Artículo 235.- Igualmente podrán admitirse los documentos.
Artículo 326 (sic).- Todas las pruebas podrán recibirse con asistencia de las partes.
Artículo 237.- Las pruebas que cada parte rindiere constarán en cuaderno separado.
"""


def test_articulo_con_sic_es_el_esperado():
    us = parse_texto(SIC, 235, estatal=True)
    assert [u.numero for u in us] == [235, 236, 237]
    assert "326" not in us[0].cuerpo
    assert us[1].cuerpo.startswith("Artículo 236.-")


def test_cita_numerada_no_es_sic():
    t = "Artículo 1.- Uno.\nArtículo 326 (sic).- Suelto.\nArtículo 7.- Siete.\n"
    assert [u.numero for u in parse_texto(t, estatal=True)] == [1]


def test_capitulo_con_ele_minuscula():
    assert CAPITULO_RE.match("Capítulo ll Bis")
    assert CAPITULO_RE.match("Capítulo II Bis")


def test_ordinal_con_nota_previa_rotula_sin_o():
    t = ("Artículo 5.- Cinco.\n(ADICIONADO, P.O. 19 DE ENERO DE 2018)\n"
         "Artículo 5° Bis.- Texto.\nArtículo 6.- Seis.\n")
    us = parse_texto(t, 5, estatal=True, notas_previas=re.compile(r"\(ADICIONADO"))
    bis = next(u for u in us if u.ordinal)
    assert bis.etiqueta == "Artículo 5 Bis"
