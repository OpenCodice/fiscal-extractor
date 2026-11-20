import re

from extractor.parsers.articulado import (CAPITULO_ESTATAL_RE, EPIGRAFE_MAX_ESTATAL,
                                          _solo_articulado, parse_texto)

NOTAS = re.compile(r"^\((?:PÁRRAFO )?(?:REFORMADO|ADICIONADO|DEROGADO)[^()]*\)$")


def _u(texto, start):
    return {u.numero: u for u in parse_texto(
        texto, start=start, estatal=True, notas=NOTAS, notas_previas=NOTAS,
        epigrafe_max=EPIGRAFE_MAX_ESTATAL)}


def test_capitulo_con_ordinal_en_minuscula_no_es_nombre_del_titulo():
    assert CAPITULO_ESTATAL_RE.match("Capitulo primero")
    us = _u("Artículo 84.- Uno.\nArticulo 85.- Las condiciones.\nTÍTULO SÉPTIMO\n"
            "Capitulo primero\nDe la huelga.\nArtículo 86.- Huelga es.\n", 84)
    assert "huelga" not in us[85].cuerpo
    assert us[86].titulo == "TÍTULO SÉPTIMO"
    assert us[86].capitulo == "Capitulo primero. De la huelga."


def test_nombre_de_titulo_en_caja_normal_con_punto_antes_del_capitulo():
    us = _u("Artículo 88.- Uno.\nTÍTULO DÉCIMO\nDel Tribunal de Conciliación y Arbitraje.\n"
            "Capitulo Primero\nDe la integración del tribunal.\nArtículo 89.- El tribunal.\n", 88)
    assert us[88].cuerpo.endswith("Uno.")
    assert us[89].titulo == "TÍTULO DÉCIMO. Del Tribunal de Conciliación y Arbitraje."


def test_rotulo_con_letra_minuscula_tras_punto_guion():
    us = {i: u for i, u in enumerate(parse_texto(
        "Artículo 149.- Uno.\n(ADICIONADO, P.O. 1 DE ABRIL DE 1997)\n"
            "Artículo 149.-a.- Los conflictos.\nArtículo 149.-b.- Para los efectos.\n"
            "Artículo 150.- Fin.\n", start=149, estatal=True, notas=NOTAS, notas_previas=NOTAS,
        epigrafe_max=EPIGRAFE_MAX_ESTATAL))}
    assert [(u.numero, u.letra) for u in us.values()] == [(149, ""), (149, "A"), (149, "B"), (150, "")]


def test_epigrafe_tras_parrafo_sin_punto_con_nota_y_articulo():
    us = _u("Artículo 79. Uno.\nAsí mismo, se promoverá los ajustes\nrazonables\n"
            "Obligaciones en materia de educación especial\n(REFORMADO, P.O. 20 DE ABRIL DEL 2023)\n"
            "Artículo 80. La Secretaría.\nArtículo 81. Tres.\n", 79)
    assert "Obligaciones" not in us[79].cuerpo
    assert us[80].epigrafe == "Obligaciones en materia de educación especial"


def test_nota_antes_de_epigrafe_con_rotulo_sin_punto():
    from extractor.parsers.articulado import _nota_tras_epigrafe_pagina
    t = "Fin.\n(REFORMADO, P.O. 20 DE ABRIL DEL 2023)\nRealización de consultas\nArtículo 89 Las autoridades consultarán."
    assert _nota_tras_epigrafe_pagina(t, NOTAS).split("\n")[1:3] == [
        "Realización de consultas", "(REFORMADO, P.O. 20 DE ABRIL DEL 2023)"]


def test_comilla_de_cierre_del_decreto_no_es_del_ultimo_articulo():
    t = ("«LEY ORGÁNICA DEL CENTRO\nCapítulo I\nArtículo 1. Uno.\nArtículo 2. Dos fin.»\n"
         "TRANSITORIOS\nArtículo Primero. Vigencia.\n")
    assert not _solo_articulado(t, True).rstrip().endswith("»")
    t2 = "Artículo 1. Uno.\nArtículo 2. Dice «esto»\nTRANSITORIOS\nArtículo Primero. V.\n"
    assert _solo_articulado(t2, True).rstrip().endswith("»")
