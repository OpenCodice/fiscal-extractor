import re

from extractor.estatales import nuevo_leon
from extractor.parsers.articulado import ARTICULO_ESTATAL_RE, ARTICULO_RE, parse_texto

NOTAS = re.compile(nuevo_leon.NOTAS, re.M)


def test_bis_con_numeral_romano_es_su_propio_articulo():
    m = ARTICULO_ESTATAL_RE.match("ARTÍCULO 33 BIS I. La Fiscalía tendrá")
    assert (m.group(4).title(), m.group(5)) == ("Bis", "I")
    m = ARTICULO_ESTATAL_RE.match("ARTÍCULO 80 BIS I.- La Contraloría")
    assert m.group(5) == "I"
    # La regla federal no cambia.
    assert ARTICULO_RE.match("ARTÍCULO 33 BIS I. La Fiscalía").group(5) is None


def test_bis_romano_abre_unidad_aparte():
    t = ("ARTÍCULO 33. Uno.\n"
         "ARTÍCULO 33 BIS. Dos.\n"
         "ARTÍCULO 33 BIS I. Tres:\n"
         "I. Algo;\n"
         "ARTÍCULO 34. Cuatro.\n")
    us = parse_texto(t, start=33, notas=NOTAS, notas_previas=NOTAS, estatal=True)
    assert [(u.numero, u.ordinal, u.ord_num) for u in us] == [
        (33, "", ""), (33, "Bis", ""), (33, "Bis", "I"), (34, "", "")]
    assert "Tres" not in us[1].cuerpo


def test_segunda_linea_de_nota_envuelta_no_es_epigrafe():
    t = ("ARTÍCULO 32. Uno.\n"
         "(ADICIONADO CON LOS ARTÍCULOS QUE LO INTEGRAN, P.O. 12 DE FEBRERO\n"
         "DE 2024)\n"
         "CAPÍTULO VIII BIS\n"
         "DE LA FISCALÍA ESPECIALIZADA\n"
         "ARTÍCULO 33. Dos.\n")
    us = parse_texto(t, start=32, notas=NOTAS, notas_previas=NOTAS, estatal=True)
    assert us[1].epigrafe == ""
    assert "DE 2024)" not in us[1].cuerpo
    assert "FEBRERO" not in us[0].cuerpo


def test_pie_de_la_ley_de_seguridad_publica_esta_declarado():
    d = next(x for x in nuevo_leon.LEYES if x.clave.endswith("ley-de-seguridad-publica"))
    assert "LEY DE SEGURIDAD PÚBLICA DEL ESTADO DE NUEVO LEÓN 1" in d.titulos_encabezado
    assert "LEY DE SEGURIDAD PÚBLICA DEL ESTADO DE NUEVO LEÓN 108" in d.titulos_encabezado
