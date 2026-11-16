"""Arreglos del agente de la vigilancia federal (run 43774603629): artículos
del decreto tras el último artículo de la ley, ordinal '2/o', notas de invalidez
y marcas de artículos suprimidos; más el rótulo del decreto antes del corte."""
from extractor.parsers.articulado import parse_texto


def claves(texto, start=1):
    return [u.clave for u in parse_texto(texto, start=start)]


def test_corta_en_el_articulo_siguiente_del_decreto():
    texto = ("Artículo 228.- Uno.\nArtículo 229.- El incumplimiento será causa de responsabilidad.\n"
             "ARTÍCULO TERCERO. ..........\nTransitorios\nPrimero. Vigor.")
    us = parse_texto(texto, start=228)
    assert us[-1].cuerpo.strip() == "Artículo 229.- El incumplimiento será causa de responsabilidad."


def test_rotulo_del_decreto_antes_del_corte_no_queda_en_el_articulo():
    texto = ("Artículo 215. Las personas morales aplicarán lo dispuesto cuando entren en liquidación.\n"
             "Artículo adicionado DOF 12-11-2021\n"
             "DISPOSICIONES DE VIGENCIA TEMPORAL DE LA LEY DEL IMPUESTO SOBRE LA\n"
             "RENTA\n"
             "ARTÍCULO NOVENO. En relación con la Ley del Impuesto sobre la Renta …")
    us = parse_texto(texto, start=215)
    assert us[0].cuerpo.strip().endswith("Artículo adicionado DOF 12-11-2021")


def test_ordinal_con_diagonal():
    assert claves("ARTICULO 1/o.- Uno.\nARTICULO 2/o.- Dos.\nARTICULO 3.- Tres.") == ["001", "002", "003"]
