import re

from extractor.estatales import nuevo_leon as nl
from extractor.estatales import clave_de
from extractor.fuentes import url_vigente

NOTAS = re.compile(nl.NOTAS)
PREVIAS = re.compile(nl.NOTAS_PREVIAS)


def test_claves_del_estado():
    docs = [d for d, _ in nl.FUERA] + list(nl.LEYES)
    assert docs
    for d in docs:
        assert d.clave.startswith("nuevo-leon/"), d.clave
    claves = [d.clave for d in docs]
    assert len(claves) == len(set(claves))
    assert nl.MEDIO


def test_claves_sin_ambito():
    assert clave_de("Código Penal para el Estado de Nuevo León") == "codigo-penal"
    assert {d.clave for d in nl.LEYES} >= {"nuevo-leon/codigo-fiscal",
                                           "nuevo-leon/ley-organica-del-poder-legislativo"}


def test_notas_reales_del_pdf():
    for n in ["(REFORMADO, P.O. 08 DE DICIEMBRE DE 2004)", "(REFORMADA, P.O. 3 DE JULIO DE 1991)",
              "(ADICIONADO, P.O. 20 DE MAYO DE 2022)", "(ADICIONADO P.O. 20 DE MAYO DE 2022)",
              "(REFORMADA SU DENOMINACIÓN, P.O. 13 DE OCTUBRE DE 2000)",
              "(REFORMADO PRIMER PARRAFO, P.O. 29 DE ENERO DE 1997)",
              "(ADICIONADO CON LOS ARTICULOS QUE LO INTEGRAN, P.O. 3 DE JULIO DE 1991)",
              "(F. DE E., P.O. 18 DE ABRIL DE 2007)", "(DEROGADO, P.O. 24 DE ENERO DE 1997)",
              "(RECORRIDA, [REFORMADA], P.O. 5 DE DICIEMBRE DE 2014)",
              "(ADICIONDO, P.O. 15 DE JUNIO DE 2023)", "(P.O. 21 DE OCTUBRE DE 2016)",
              "((REFORMADO, P.O. 04 DE MARZO DE 2022)"]:
        assert NOTAS.match(n), n
        assert PREVIAS.match(n), n


def test_texto_normal_no_es_nota():
    for t in ["Artículo 5.- La Ley (P.O. de", "(a) el Estado", "(artículo 5)",
              "El Estado (REFORMADO", "Reforma publicada en el Periódico Oficial",
              "I.- Las personas físicas;", "(Reforma publicada)"]:
        assert not NOTAS.match(t), t


def test_pie_de_pagina_por_ley():
    pies = {d.clave: set(d.titulos_encabezado) for d in nl.LEYES}
    fg = pies["nuevo-leon/ley-organica-de-la-fiscalia-general-de-justicia"]
    assert "Decreto Núm. 314 expedido por la LXXIV Legislatura 42" in fg
    assert "Decreto Núm. 314 expedido por la LXXV Legislatura 42" not in fg


def test_resolucion_de_la_url_sin_red():
    indice = ('<a href="https://www.hcnl.gob.mx/trabajo_legislativo/leyes/pdf/'
              'CODIGO%20FISCAL%20DEL%20ESTADO%20DE%20NUEVO%20LEON.pdf?2023-01-13">x</a>'
              '<a href="https://www.hcnl.gob.mx/trabajo_legislativo/leyes/pdf/'
              'CODIGO%20FISCAL%20DEL%20ESTADO%20DE%20NUEVO%20LEON.doc">x</a>')
    d = next(x for x in nl.LEYES if x.clave == "nuevo-leon/codigo-fiscal")
    assert d.consulta
    assert url_vigente(d, leer=lambda *_: indice).endswith("NUEVO%20LEON.pdf?2023-01-13")


def test_todas_se_resuelven_por_indice():
    for d in nl.LEYES:
        assert d.indice and d.patron and d.consulta


def test_pie_con_numero_de_pagina_y_sin_el():
    assert "Decreto Núm. 5 expedido por la X Legislatura 3" in nl._pie(5, "X")
    assert nl._pie(5, "X", numerado=False) == ("Decreto Núm. 5 expedido por la X Legislatura",)


def test_fuera_declara_motivo():
    for d, motivo in nl.FUERA:
        assert d.clave.startswith("nuevo-leon/") and len(motivo) > 20
