"""Estatal (Guanajuato): nota previa con rótulo 'Artículo 6 bis.' en minúscula,
epígrafe envuelto en dos renglones, y corte de fracción tras '; y' en el margen."""
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


_RELLENO = "".join(f"\nEpígrafe {c}\nArtículo {n}. Texto del artículo." for n, c in
                   zip(range(7, 30), "ABCDEFGHIJKLMNOPQRSTUVW"))


_PREVIO = "".join(f"Artículo {n}. Texto del artículo.\n" for n in range(1, 6))


def test_rotulo_bis_en_minuscula():
    us = _parse(_PREVIO + "Artículo 6. Seis.\n(ADICIONADO, P.O. 08 DE ENERO DE 2024)\nSupletoriedad\n"
                "Artículo 6 bis. En lo no previsto." + _RELLENO)
    assert "(ADICIONADO, P.O. 08 DE ENERO DE 2024)" in us[6].cuerpo
    assert "(ADICIONADO" not in us[5].cuerpo and us[6].epigrafe == "Supletoriedad"


def test_cita_en_minuscula_no_se_mueve():
    t = ("Procederá:\n(REFORMADA, P.O. 31 DE DICIEMBRE DE 2007)\nI.- Algo\n"
         "Artículo 169 de este Código.")
    assert a._nota_tras_epigrafe_pagina(t, re.compile(NOTAS)) == t


def test_epigrafe_de_dos_renglones():
    us = _parse(_PREVIO + "Artículo 6. Uno.\nVIII. Acta.\n"
                "(REFORMADO SU ACÁPITE, P.O. 28 DE NOVIEMBRE DE 2014)\n"
                "Prueba práctica para jueces de partido, jefes de unidad de causa y\n"
                "gestión, y encargados de sala del sistema penal acusatorio y oral\n"
                "Artículo 7. Dos." + _RELLENO.replace("Artículo 7.", "Artículo 8.", 1))
    assert "Prueba" not in us[5].cuerpo and "(REFORMADO" not in us[5].cuerpo
    assert "(REFORMADO SU ACÁPITE" in us[6].cuerpo
    assert us[6].epigrafe.endswith("sistema penal acusatorio y oral")


def test_fin_de_fraccion_y_numeral_siguiente():
    assert a._FIN_DE_FRACCION_RE.search("la comprendida en la fracción VII; y")
    assert a._FRACCION_ROMANA_RE.match("VI. De 150 a 250 Unidades")
    assert not a._FIN_DE_FRACCION_RE.search("la comprendida en la fracción VII")
