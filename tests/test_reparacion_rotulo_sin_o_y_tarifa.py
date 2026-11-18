from extractor.normalize import normalize_body
from extractor.parsers.articulado import parse_texto


_BASE = "".join(f"ARTÍCULO {n}o.- Texto {n}.\n" for n in range(1, 5))


def _unidades(texto):
    return parse_texto(texto, estatal=True)


def test_estatal_rotulo_bis_sin_o_conserva_el_rotulo_del_pdf():
    t = (_BASE + "ARTÍCULO 5o.- Texto cinco.\n"
         "ARTÍCULO 5 BIS.- Texto del bis.\nARTÍCULO 6o.- Texto seis.\n")
    us = {u.clave: u for u in _unidades(t)}
    assert us["005-bis"].etiqueta == "Artículo 5 Bis"
    assert us["005"].etiqueta == "Artículo 5o."


def test_estatal_rotulo_bis_con_o_no_cambia():
    t = (_BASE + "ARTÍCULO 5o.- Texto cinco.\nARTÍCULO 5o Bis.- Texto del bis.\n"
         "ARTÍCULO 6o.- Texto seis.\n")
    us = {u.clave: u for u in _unidades(t)}
    assert us["005-bis"].etiqueta == "Artículo 5o Bis"


def test_renglon_de_tarifa_final_sigue_en_el_parrafo_que_lo_anuncia():
    body = ("ARTICULO 215.- Intro.\n"
            "SEGUNDA CATEGORIA: Comprende las bebidas\nsea mayor de $30.00 el litro:\n"
            "Unidad Fiscal hasta 1000 c c $ 3.50\n")
    cortes = {("ARTICULO 215.- Intro.", "SEGUNDA CATEGORIA: Comprende las bebidas"): True,
              ("SEGUNDA CATEGORIA: Comprende las bebidas", "sea mayor de $30.00 el litro:"): False,
              ("sea mayor de $30.00 el litro:", "Unidad Fiscal hasta 1000 c c $ 3.50"): True}
    out = normalize_body(body, "Artículo 215.", cortes=cortes)
    assert out.split("\n\n")[-1].endswith("el litro: Unidad Fiscal hasta 1000 c c $ 3.50")
