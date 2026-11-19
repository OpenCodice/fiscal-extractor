"""Estatal (Guanajuato): la nota de reforma que el PDF pone antes del epígrafe
del artículo es la primera línea del artículo (y no se pierde ni se pega al
anterior); la nota '(PÁRRAFO SEGUNDO, DEROGADO, …)' sigue siendo del anterior."""
import re

from extractor.estatales.guanajuato import NOTAS
from extractor.parsers import articulado as a
from extractor.registro import Documento


def _doc():
    return Documento("guanajuato/x", "X", "X", "ley", "articulado", "u", medio="Periódico Oficial",
                     notas=NOTAS, notas_previas=NOTAS)


def _parse(t):
    limpio = a.limpiar_paginas([t], _doc())
    return a.parse_texto(limpio, estatal=True, epigrafe_max=a.EPIGRAFE_MAX_ESTATAL,
                         notas=re.compile(NOTAS), notas_previas=re.compile(NOTAS))


def test_nota_antes_del_epigrafe_es_del_articulo():
    us = _parse("Artículo 1. Uno.\n(REFORMADO, P.O. 08 DE ENERO DE 2024)\nActas circunstanciadas\n"
                "Artículo 2. Dos.")
    assert "(REFORMADO" in us[1].cuerpo and "(REFORMADO" not in us[0].cuerpo
    assert us[1].epigrafe == "Actas circunstanciadas"
    assert "Actas" not in us[0].cuerpo


def test_nota_tras_capitulo_y_antes_de_epigrafe():
    us = _parse("Artículo 1. Uno.\nCapítulo II\nOtro nombre\n"
                "(ADICIONADO, P.O. 28 DE NOVIEMBRE DE 2014)\n"
                "Interposición de la queja\nArtículo 2. Dos.")
    assert "(ADICIONADO, P.O. 28 DE NOVIEMBRE DE 2014)" in us[1].cuerpo


def test_nota_de_parrafo_derogado_sigue_siendo_del_anterior():
    us = _parse("Artículo 1. Uno.\n(PÁRRAFO SEGUNDO, DEROGADO, P.O. 08 DE ENERO DE 2024)\n"
                "Extinción de facultades\nArtículo 2. Dos.")
    assert us[0].cuerpo.rstrip().endswith("2024)")
    assert "Extinción" not in us[0].cuerpo and "PÁRRAFO" not in us[1].cuerpo


def test_nota_denominacion_no_se_mueve():
    t = "Capítulo II\n(REFORMADA SU DENOMINACION, P.O. 08 DE ENERO DE 2024)\nDel Impuesto\nArtículo 2. Dos."
    assert a._nota_tras_epigrafe_pagina(t, re.compile(NOTAS)) == t


def test_epigrafe_con_comas_antes_de_nota_y_articulo():
    relleno = "".join(f"Epígrafe {c}\nArtículo {n}. X.\n" for n, c in
                      zip(range(4, 30), "ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
    us = _parse("Artículo 1. Uno.\nRequisitos de las solicitudes, opiniones y quejas\n"
                "(REFORMADO ACÁPITE, P.O. 12 DE OCTUBRE DE 2020)\nArtículo 2. Dos.\n"
                "Artículo 3. Tres.\n" + relleno)
    assert "Requisitos" not in us[0].cuerpo
    assert us[1].epigrafe == "Requisitos de las solicitudes, opiniones y quejas"


def test_fraccion_y_cita_no_se_reordenan():
    t = ("Procederá:\n(REFORMADA, P.O. 31 DE DICIEMBRE DE 2007)\n"
         "I.- A partir del día siguiente a aquél en que se hubiese fijado la base en los términos del\n"
         "Artículo 169 de este Código.")
    assert a._nota_tras_epigrafe_pagina(t, re.compile(NOTAS)) == t
