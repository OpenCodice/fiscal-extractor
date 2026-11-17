"""Notas de reforma de la CDMX que el parser perdía o dejaba en el artículo
equivocado (hallazgos de la revisión completa del Código Civil y del de
Instituciones y Procedimientos Electorales)."""
import re

from extractor.estatales import cdmx
from extractor.parsers.articulado import parse_texto

NOTAS = re.compile(cdmx.NOTAS)
PREVIAS = re.compile(cdmx.NOTAS_PREVIAS)


def _parse(texto, start, **kw):
    return parse_texto(texto, start=start, notas=NOTAS, notas_previas=PREVIAS,
                       estatal=True, **kw)


def test_variantes_de_nota():
    for n in ["Numeral reformado G.O. CDMX 09/04/2026", "Fe de Erratas 13/11/2023",
              "Fe de Erratas G.O. CDMX 13/11/2023",
              "N. DE E. SE RECOMIENDA CONSULTAR EL DECRETO"]:
        assert NOTAS.match(n), n


def test_nota_en_mayusculas_tras_fraccion_no_es_epigrafe():
    t = ("ARTICULO 134.- Procede:\nIV. En caso de homonimia.\n"
         "FRACCIÓN ADICIONADA G.O. CDMX 27/08/25\n"
         "ARTICULO 135.- Otro texto.\n")
    u = _parse(t, 134)
    assert u[0].cuerpo.rstrip().endswith("FRACCIÓN ADICIONADA G.O. CDMX 27/08/25")
    assert u[0].epigrafe == "" and u[1].epigrafe == ""


def test_nota_del_editor_larga_es_del_articulo_siguiente():
    t = ("ARTICULO 119.- Texto.\nVI. La hora de muerte.\n"
         "N. DE E. SE RECOMIENDA CONSULTAR EL DECRETO POR EL QUE SE CREA UNA\n"
         "NUEVA UNIDAD DEL SISTEMA MONETARIO, PUBLICADO EN EL D.O.F. DE FECHA\n"
         "EL 15 DE NOVIEMBRE DE 1995.\n"
         "(REFORMADO, D.O.F. 3 DE ENERO DE 1979)\n"
         "ARTICULO 120.- Multa de cinco mil pesos.\n")
    a, b = _parse(t, 119)
    assert "N. DE E." not in a.cuerpo
    assert b.cuerpo.index("N. DE E.") < b.cuerpo.index("(REFORMADO") < b.cuerpo.index("Multa")
    assert "1995.\n\n(REFORMADO" in b.cuerpo


def test_nota_del_editor_tras_encabezado_de_capitulo():
    t = ("ARTICULO 145.- (DEROGADO, G.O. 25 DE MAYO DE 2000)\n"
         "CAPITULO II\nDe los requisitos\n"
         "N. DE E. SE MODIFICA EL TEXTO DEL PRESENTE ARTÍCULO\n"
         "ARTÍCULO 14 DE LAS DISPOSICIONES TRANSITORIAS DE LA LEY.\n"
         "(REFORMADO, G.O. 29 DE DICIEMBRE DE 2009)\n"
         "ARTICULO 146.- Matrimonio es la unión libre.\n")
    a, b = _parse(t, 145)
    assert "ARTÍCULO 14 DE LAS" not in a.cuerpo
    assert b.cuerpo.index("N. DE E.") < b.cuerpo.index("ARTÍCULO 14 DE LAS") \
        < b.cuerpo.index("(REFORMADO") < b.cuerpo.index("Matrimonio")


def test_articulo_de_solo_notas_suelta_las_del_siguiente():
    t = ("ARTICULO 2448.- Base.\nARTICULO 2448 F.- Texto.\n(REFORMADA, G.O. 28 DE AGOSTO DE 2024)\n"
         "ARTICULO 2448 G.- (DEROGADO, G.O. 14 DE MAYO DE 2010)\n"
         "(ADICIONADO, D.O.F. 7 DE FEBRERO DE 1985)\n"
         "ARTICULO 2448 H.- El arrendamiento.\n")
    us = _parse(t, 2448)
    g, h = us[2], us[3]
    assert "DEROGADO" in g.cuerpo and "ADICIONADO" not in g.cuerpo
    assert "ADICIONADO" in h.cuerpo


def test_bis_antes_de_su_articulo_base():
    t = ("ARTICULO 854.- Texto.\nARTÍCULO 855 BIS.- Se reconoce a los animales.\n"
         "ARTICULO 855.- Los animales sin marca.\nARTICULO 856.- Otro.\n")
    us = _parse(t, 854)
    assert [(u.numero, u.ordinal) for u in us] == [(854, ""), (855, "Bis"), (855, ""), (856, "")]
