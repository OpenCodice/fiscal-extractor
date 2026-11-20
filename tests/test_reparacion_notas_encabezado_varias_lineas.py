import re

from extractor.estatales import guanajuato as g
from extractor.parsers.articulado import parse_texto

NOTAS = re.compile(g.NOTAS)
PREVIAS = re.compile(g.NOTAS_PREVIAS)


def _parse(t):
    return {u.numero: u for u in parse_texto(
        t, estatal=True, notas=NOTAS, notas_previas=PREVIAS)}


def test_nota_de_encabezado_en_dos_renglones_no_es_del_articulo():
    t = """(ADICIONADO, P.O. 27 DE DICIEMBRE DE 2011)
Artículo 1.- Texto uno.
(ADICIONADO CON LOS ARTÍCULOS QUE LO INTEGRAN,
P.O. 27 DE DICIEMBRE DE 2011)
CAPÍTULO II
De las Audiencias
(ADICIONADO, P.O. 27 DE DICIEMBRE DE 2011)
Artículo 2.- Texto dos.
"""
    us = _parse(t)
    assert "INTEGRAN" not in us[1].cuerpo
    assert "INTEGRAN" not in us[2].cuerpo


def test_nota_del_editor_en_dos_renglones_es_del_siguiente():
    t = """(ADICIONADO, P.O. 27 DE DICIEMBRE DE 2011)
Artículo 1.- Texto uno.
N. DE E. EN RELACIÓN CON LA ENTRADA EN VIGOR DEL PRESENTE ARTÍCULO, VÉASE
ARTÍCULO TERCERO TRANSITORIO DEL DECRETO QUE MODIFICA ESTE ORDENAMIENTO.
(ADICIONADO, P.O. 27 DE DICIEMBRE DE 2011)
Artículo 2.- Texto dos.
"""
    us = _parse(t)
    assert "N. DE E." not in us[1].cuerpo
    assert "N. DE E." in us[2].cuerpo


def test_nota_y_encabezado_con_punto_al_final_no_son_del_articulo():
    t = """(ADICIONADO, P.O. 13 DE AGOSTO DE 2004)
Artículo 1.- Texto uno.
(REFORMADA SU NUMERACIÓN, P.O. 13 DE AGOSTO DE 2004)
TITULO QUINTO.
CAPITULO UNICO.
Declaración de estado de interdicción.
Artículo 2.- Texto dos.
"""
    us = _parse(t)
    assert us[1].cuerpo.rstrip().endswith("Texto uno.")
    assert "Declaración" not in us[1].cuerpo
