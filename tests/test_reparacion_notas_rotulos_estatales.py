import re

from extractor.estatales import queretaro as q
from extractor.parsers.articulado import _notas_aparte, parse_texto

EN_LINEA = re.compile(q.NOTAS_EN_LINEA)


def test_nota_queretaro_sin_punto_y_fecha_partida():
    t = "Texto del párrafo; (Ref. P. O. No. 61, 1-\nIX-17)\nOtro (Adición. P. O. No. 58, 15-VII-26)\nY (Ref.\nP. O No. 87, 30-IX-21)"
    s = _notas_aparte([t], EN_LINEA)[0].split("\n")
    assert "(Ref. P. O. No. 61, 1-IX-17)" in s
    assert "(Adición. P. O. No. 58, 15-VII-26)" in s
    assert "(Ref. P. O No. 87, 30-IX-21)" in s


def test_bis_con_letra_bis_uno_y_ocr():
    t = ("ARTÍCULO 220.- Uno.\nARTÍCULO 221.- Base.\nARTÍCULO 22I BIS.- Dos.\nARTÍCULO 221 BIS-A.- Tres.\n"
         "ARTÍCULO 221 BIS UNO.- Cuatro.\nARTÍCULO 222.- Cinco.\n")
    us = parse_texto(t, start=220, estatal=True)
    assert [u.numero for u in us] == [220, 221, 221, 221, 221, 222]
    assert len({u.clave for u in us}) == 6


def test_letra_enie_distinta_de_n():
    t = "Artículo 142-N. Uno.\nArtículo 142-Ñ. Dos.\n"
    us = parse_texto("Artículo 142. Cero.\n" + t, start=142, estatal=True)
    assert len({u.clave for u in us}) == 3


def test_guion_largo_tras_el_rotulo_y_nombre_mayusculas_largo():
    t = ("ARTÍCULO 1.- Uno.\nTÍTULO SEXTO\nDELITOS CONTRA UNO Y\nDOS TRES CUATRO\n"
         "CINCO SEIS SIETE\nOCHO NUEVE DIEZ.\nCAPÍTULO I\nCORRUPCIÓN,\nDE PERSONAS.\n"
         "ARTÍCULO 2.- Dos.\n")
    us = parse_texto(t, estatal=True)
    assert [u.numero for u in us] == [1, 2]
    assert us[0].cuerpo.strip().splitlines() == ["ARTÍCULO 1.- Uno."]
    assert us[1].titulo.endswith("OCHO NUEVE DIEZ.")
