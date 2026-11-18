"""Código Penal, Ley de Hacienda y Código Civil de Nuevo León (reparación)."""
import re

from extractor.estatales import nuevo_leon as nl
from extractor.parsers.articulado import ARTICULO_ESTATAL_RE, parse_texto


def _parse(texto, start=1):
    return parse_texto(texto, start=start, estatal=True, notas=re.compile(nl.NOTAS),
                       notas_previas=re.compile(nl.NOTAS))


def test_texto_en_mayusculas_no_se_toma_por_epigrafe_marginal():
    # Texto todo en mayúsculas: el primer renglón sin puntuación es texto del artículo.
    t = "".join(f"ARTICULO {n}.- LAS CONSECUENCIAS JURÍDICAS DE LOS DELITOS, SE\n"
                f"DETERMINARÁN CONFORME A LA LEY VIGENTE.\n" for n in range(1, 13))
    us = _parse(t)
    assert len(us) == 12
    assert all("LAS CONSECUENCIAS JURÍDICAS DE LOS DELITOS, SE" in u.cuerpo for u in us)
    assert all(not u.epigrafe for u in us)


def test_articulos_derogados_con_coma_y_numeral_romano():
    for rotulo in ("ARTICULO 208 BIS, (DEROGADO, P.O. 24 DE ENERO DE 1997)",
                   "ARTICULO 208 BIS I, (DEROGADO, P.O. 24 DE ENERO DE 1997)",
                   "Art. 37 (DEROGADO, P.O. 28 DE NOVIEMBRE DE 2008)",
                   "Art. 388.-( DEROGADO P.O. 12 DE SEPTIEMBRE DE 2003.)"):
        assert ARTICULO_ESTATAL_RE.match(rotulo), rotulo
    t = ("ARTICULO 208.- TEXTO.\n"
         "ARTICULO 208 BIS, (DEROGADO, P.O. 24 DE ENERO DE 1997)\n"
         "ARTICULO 208 BIS I, (DEROGADO, P.O. 24 DE ENERO DE 1997)\n"
         "ARTICULO 209.- OTRO.\n")
    assert len(_parse(t, 208)) == 4


def test_capitulo_con_nombre_con_punto_y_nota_antes_del_articulo():
    t = ("ARTICULO 112.- X.\n"
         "CAPITULO CUARTO\n"
         "(REFORMADA SU DENOMINACION, P.O. 27 DE DICIEMBRE DE 1996)\n"
         "Del Impuesto por obtención de premios.\n"
         "(REFORMADO, P.O. 25 DE ABRIL DE 1997)\n"
         "ARTICULO 113.- Es objeto.\n"
         "(ADICIONADO CON LOS ARTÍCULOS QUE LO INTEGRAN, P.O. 30 DE DICIEMBRE DE\n"
         "2019)\n"
         "CAPITULO QUINTO BIS\n"
         "Del Impuesto a las Tarifas Efectivamente Cobradas por las Empresas de Redes de\n"
         "Transporte.\n"
         "(ADICIONADO, P.O. 30 DE DICIEMBRE DE 2019)\n"
         "ARTICULO 114.- Es objeto.\n")
    u112, u113, u114 = _parse(t, 112)
    assert "Del Impuesto" not in u112.cuerpo
    assert u113.capitulo == "CAPITULO CUARTO. Del Impuesto por obtención de premios."
    assert "DENOMINACION" not in u113.cuerpo
    assert "Transporte" not in u113.cuerpo
    assert u114.capitulo.endswith("Empresas de Redes de Transporte.")
