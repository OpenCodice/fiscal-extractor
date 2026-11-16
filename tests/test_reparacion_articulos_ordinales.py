from extractor.parsers.articulado import parse_texto

TEXTO = """\
"El Congreso de los Estados Unidos Mexicanos, decreta:
LEY PARA CONSERVAR LA NEUTRALIDAD DEL PAIS
ARTICULO PRIMERO.- No serán admitidos submarinos.
ARTICULO SEGUNDO.- Se deroga.
Artículo derogado DOF 21-06-2018
ARTICULO TERCERO.- No será admitido ningún aeroplano.
Miguel Moreno, D. P.- Guillermo Flores Muñoz, S. P.- Rúbricas."
En cumplimiento de lo dispuesto por la fracción I del artículo 89 expido la presente Ley.
"""


def test_articulos_en_ordinal_de_decreto():
    us = parse_texto(TEXTO)
    assert [u.numero for u in us] == [1, 2, 3]
    assert "Rúbricas" not in us[-1].cuerpo and "En cumplimiento" not in us[-1].cuerpo
    assert "No serán admitidos" in us[0].cuerpo


def test_no_toca_leyes_con_articulos_numerados():
    t = "Artículo 1o.- Uno.\nARTICULO SEGUNDO.- del decreto.\n"
    assert [u.numero for u in parse_texto(t)] == [1]
