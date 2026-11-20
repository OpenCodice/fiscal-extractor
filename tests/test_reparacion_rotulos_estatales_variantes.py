import re
from extractor.parsers.articulado import ARTICULO_ESTATAL_RE, _rotulo_abreviado_completo, parse_texto


def test_letra_minuscula_con_guion_o_espacio():
    for s, letra in (("Artículo 133-a.- Cumplido el", "a"), ("Artículo 150 b.- (DEROGADO", "b")):
        m = ARTICULO_ESTATAL_RE.match(s)
        assert m and m.group(2) == letra


def test_rotulo_abreviado_variantes():
    t = ("Art.146. (DEROGADO, P.O. 1)\nArt. 136-A. Texto\nART. 1418. (DEROGADO POR X)\n"
         "Art. 10014 (sic). (DEROGADO)\nARTíCULO 110 Bis.- Texto\n")
    r = _rotulo_abreviado_completo(t).splitlines()
    assert r[0].startswith("Artículo 146. ")
    assert r[1].startswith("Artículo 136-A. ")
    assert r[2].startswith("ARTÍCULO 1418. ")
    assert r[3].startswith("Artículo 10014 (sic).")
    assert r[4].startswith("ARTÍCULO 110 Bis")


def test_rotulo_3o_bis_conserva_o():
    t = ("Artículo 3o.- Uno.\n(ADICIONADO, P.O. 04 DE JULIO DE 2023)\n"
         "Artículo 3o Bis.- Dos.\nArtículo 4o.- Tres.\n")
    p = re.compile(r"^\(ADICIONADO, P\.O\. [^)]*\)$")
    us = parse_texto(t, start=3, estatal=True, notas=p, notas_previas=p)
    bis = [u for u in us if u.ordinal == "Bis"][0]
    assert bis.etiqueta.startswith("Artículo 3o Bis")
