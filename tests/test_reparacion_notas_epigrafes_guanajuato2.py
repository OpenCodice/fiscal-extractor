"""Guanajuato: epígrafe envuelto a dos renglones con coma, nota '(REFORMADO SU
ACÁPITE …)', fracción '(REFORMADA …)' sin texto, nota sin paréntesis de apertura,
nota del editor entre corchetes y ordinales Cuater/Cuaterdecies/Sexiesdecies."""
import re

from extractor.estatales.guanajuato import NOTAS, NOTAS_EN_LINEA, NOTAS_PREVIAS
from extractor.parsers import articulado as a
from extractor.registro import Documento


def _doc():
    return Documento("guanajuato/x", "X", "X", "ley", "articulado", "u", medio="Periódico Oficial",
                     notas=NOTAS, notas_previas=NOTAS_PREVIAS, notas_en_linea=NOTAS_EN_LINEA)


def _parse(t):
    limpio = a.limpiar_paginas([t], _doc())
    return a.parse_texto(limpio, estatal=True, epigrafe_max=a.EPIGRAFE_MAX_ESTATAL,
                         notas=re.compile(NOTAS), notas_previas=re.compile(NOTAS_PREVIAS))


def _con_epigrafes(n=22):
    return "".join(f"Epígrafe número {k}\nArtículo {k}. Texto {k}.\n" for k in range(1, n))


def test_epigrafe_de_dos_renglones_con_coma():
    t = (_con_epigrafes() +
         "Artículo 22. Uno.\nProcedimiento para la revisión, modificación\n"
         "y actualización de los programas municipales\nArtículo 23. Dos.\n"
         "Pago por el servicio público de drenaje,\ntratamiento y disposición de aguas\n"
         "Artículo 24. Tres.\n")
    us = _parse(t)
    assert us[21].cuerpo.rstrip().endswith("Uno.")
    assert us[22].epigrafe == "Procedimiento para la revisión, modificación y actualización de los programas municipales"
    assert us[22].cuerpo.rstrip().endswith("Dos.")


def test_nota_de_acapite_no_es_del_articulo():
    t = ("Artículo 1. Uno.\n(REFORMADO SU ACÁPITE, P.O. 5 DE DICIEMBRE DE 2017)\n"
         "Atribuciones del Instituto\nArtículo 2. Dos.\n")
    us = _parse(t)
    assert "ACÁPITE" not in us[1].cuerpo and "ACÁPITE" not in us[0].cuerpo


def test_fraccion_reformada_sin_texto_en_un_renglon():
    t = ("Artículo 1. Uno:\nVII. (DEROGADA, P.O. 23 DE NOVIEMBRE DE 2021)\n"
         "VIII. (REFORMADA, P.O. 23 DE NOVIEMBRE DE 2021)\nIX. Otra.\n")
    c = _parse(t)[0].cuerpo
    assert "VIII. (REFORMADA, P.O. 23 DE NOVIEMBRE DE 2021)" in c
    assert not re.search(r"(?m)^VIII\.$", c)


def test_nota_sin_parentesis_de_apertura():
    t = ("Artículo 1. Uno.\nREFORMADO [N. DE E. ESTE PÁRRAFO], P.O. 5 DE DICIEMBRE DE 2017)\n"
         "Artículo 2. Dos.\n")
    us = _parse(t)
    assert "REFORMADO [N. DE E." in us[1].cuerpo and "REFORMADO" not in us[0].cuerpo


def test_nota_del_editor_entre_corchetes_es_del_articulo_anterior():
    t = ("Artículo 1. Uno:\nI. Algo.\n[N. DE E. VÉASE LITERALIDAD DEL DECRETO PUBLICADO\n"
         "EN EL P.O. DE 29 DE MAYO DE 2020, PÁGINA 50.]\nArtículo 2. Dos.\n")
    us = _parse(t)
    assert "PÁGINA 50.]" in us[0].cuerpo and us[1].epigrafe in ("", None)


def test_ordinales_cuater_y_cuaterdecies():
    t = ("Artículo 1. Uno.\nArtículo 1 Ter. Dos.\nArtículo 1 Cuater. Tres.\n"
         "Artículo 1 Cuaterdecies. Cuatro.\nArtículo 1 Sexiesdecies. Cinco.\n"
         "Artículo 1 Septedecies. Seis.\nArtículo 1 Octodecies. Siete.\n")
    assert [u.ordinal.lower() for u in _parse(t)][1:] == [
        "ter", "cuater", "cuaterdecies", "sexiesdecies", "septedecies", "octodecies"]
