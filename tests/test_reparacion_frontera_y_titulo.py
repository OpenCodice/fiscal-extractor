"""Arreglos del agente de la vigilancia federal (run 43753067563): decretos de
reforma compilados al final, título corrido en PDF cortos, separadores raros y
citas que repiten un sufijo ya abierto."""
from extractor.parsers.articulado import _titulo_corrido, parse_texto


def claves(texto, start=1):
    return [u.clave for u in parse_texto(texto, start=start)]


def test_corta_en_decretos_de_reforma_compilados():
    texto = (
        "Artículo 1o.- Uno.\nArtículo 2o.- Dos.\n"
        "ARTÍCULOS TRANSITORIOS DE DECRETOS DE REFORMA\n"
        "DECRETO que adiciona la fracción III.\nARTICULO UNICO.- Se adiciona."
    )
    assert claves(texto) == ["001", "002"]


def test_titulo_corrido_en_pdf_de_tres_paginas():
    paginas = ["Portada", "LEY X\nArtículo 1.- Uno.", "LEY X\nArtículo 2.- Dos."]
    assert _titulo_corrido(paginas) == ("LEY X",)


def test_separador_pegado_al_texto_y_punto_extra():
    texto = "Artículo 1o.- Uno.\nARTICULO 2.-Dos.\nArtículo 3.-. Tres.\nArtículo 4. Cuatro."
    assert claves(texto) == ["001", "002", "003", "004"]


def test_cita_con_sufijo_repetido_no_duplica_la_unidad():
    texto = (
        "Artículo 36.- Uno.\nArtículo 37.- Dos.\nARTÍCULO 37 BIS. “La Comisión” fondo,\ncon los volúmenes.\n"
        "Artículo 37 BIS de esta Ley, la Autoridad privilegiará.\n"
        "Artículo 38.- Tres."
    )
    assert claves(texto, start=36) == ["036", "037", "037-bis", "038"]
