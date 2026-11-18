"""Código Civil de Nuevo León: rótulos 'Art. 54.-' / 'Art. 134.' tras la nota
previa, 'Bis IV'…'Bis X' y el 'CAPITILO' del Código Fiscal."""
import re

from extractor.estatales.nuevo_leon import NOTAS
from extractor.parsers import articulado
from extractor.parsers.articulado import _rotulo_abreviado_completo, parse_texto


def test_rotulo_abreviado_se_lee_como_articulo():
    t = ("Art. 54.- Para la inscripción\nArt. 134. La cancelación\n"
         "Art. 393 BIS. Las personas\nArt. 410 Bis V.- Si alguno\nArt. 53.-\n"
         "texto Art. 5.- no empieza renglón\nArt. 5 de la Ley")
    r = _rotulo_abreviado_completo(t).split("\n")
    assert r[0] == "Artículo 54.- Para la inscripción"
    assert r[1] == "Artículo 134. La cancelación"
    assert r[2] == "Artículo 393 BIS. Las personas"
    assert r[3] == "Artículo 410 Bis V.- Si alguno"
    assert r[4] == "Artículo 53.-"
    assert r[5].startswith("texto Art. 5.-")
    assert r[6] == "Art. 5 de la Ley"


def test_nota_previa_y_bis_romano_hasta_x():
    n = re.compile(NOTAS)
    t = ("Artículo 52.- Primero.\n(REFORMADO, P.O. 01 DE ENERO DE 1982)\n"
         "Artículo 53.- Segundo.\n(ADICIONADO, P.O. 28 DE ABRIL DE 2004)\n"
         "Artículo 53 Bis IV.- Tercero.\nArtículo 53 Bis V.- Cuarto.\n")
    us = parse_texto(t, start=52, notas=n, notas_previas=n, estatal=True)
    assert [(u.numero, u.ordinal, u.ord_num) for u in us] == [
        (52, "", ""), (53, "", ""), (53, "Bis", "Iv"), (53, "Bis", "V")]


def test_capitilo_es_capitulo():
    assert articulado.CAPITULO_RE.match("CAPITILO IV")
    assert articulado.CAPITULO_RE.match("CAPITULO IV")
