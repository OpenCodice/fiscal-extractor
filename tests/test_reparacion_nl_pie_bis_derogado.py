from extractor.estatales import nuevo_leon
from extractor.normalize import normalize_body
from extractor.parsers.articulado import parse_texto


def test_justicia_civica_declara_su_pie_de_pagina():
    d = next(d for d in nuevo_leon.LEYES if d.clave.endswith("ley-de-justicia-civica"))
    assert "Decreto Núm. 267 expedido por la LXXVI Legislatura 1" in d.titulos_encabezado
    assert "Decreto Núm. 267 expedido por la LXXVI Legislatura 51" in d.titulos_encabezado


def test_rotulo_bis_con_ele_minuscula_se_lee_como_bis():
    from extractor.parsers.articulado import _rotulo_abreviado_completo
    assert _rotulo_abreviado_completo("ARTÍCULO 79 BlS. - El Centro.") == "ARTÍCULO 79 BIS. - El Centro."
    texto = _rotulo_abreviado_completo("ARTÍCULO 1.- Uno.\nARTÍCULO 1 BlS. - Centro.\nARTÍCULO 2.- Texto.\n")
    unidades = parse_texto(texto, estatal=True)
    assert [(u.numero, u.ordinal) for u in unidades] == [(1, ""), (1, "Bis"), (2, "")]


def test_derogado_al_abrir_pagina_es_parrafo_propio():
    cuerpo = "Si no se da el nombramiento, cesarán en sus funciones.\nDEROGADO. P.O. 20 DE MAYO DE 2022.\nEl Pleno harán la designación."
    cortes = {("Si no se da el nombramiento, cesarán en sus funciones.",
               "DEROGADO. P.O. 20 DE MAYO DE 2022."): False}
    out = normalize_body(cuerpo, "Artículo 129", cortes=cortes)
    assert "funciones.\n\nDEROGADO. P.O. 20 DE MAYO DE 2022." in out
