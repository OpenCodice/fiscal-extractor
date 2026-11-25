"""Yucatán: el PDF abre con portada, un índice que repite cada rótulo con su
epígrafe ('ARTÍCULO 1. Objeto' … y al final 'TRANSITORIOS') y el decreto de
expedición con su exposición de motivos (que cita otro 'Artículo 1o.'). La ley
empieza después. Sus notas a veces no llevan 'D.O.' ('Artículo reformado
28-08-2025') o el día ('D.O. XX-09-2021'); un epígrafe puede seguir a una
oración que cierra con comilla, o llevar un participio ('Heredero declarado…').
Y el interlineado se mide en las páginas de la ley, no en los decretos de
reforma compilados al final."""
import re

from extractor.estatales import yucatan
from extractor.parsers import articulado
from extractor.parsers.articulado import (EPIGRAFE_MAX_ESTATAL, _interlineado_de_la_ley,
                                          parse_texto)
from extractor.perfil import ESTATAL_BASE

_NOTAS = re.compile(yucatan.NOTAS)

_INDICE = """\
H. CONGRESO DEL ESTADO DE YUCATÁN
CÓDIGO DE FAMILIA PARA EL
ESTADO DE YUCATÁN
LIBRO PRIMERO
FAMILIA
CAPÍTULO ÚNICO.- DEL OBJETO Y DISPOSICIONES GENERALES
ARTÍCULO 1. Objeto
ARTÍCULO 2. Supletoriedad
ARTÍCULO 3. Irrenunciabilidad de los derechos y obligaciones
TRANSITORIOS:
DECRETO 516
Publicado en el Diario oficial del Gobierno del Estado
E X P O S I C I Ó N D E M O T I V O S:
PRIMERA.- La iniciativa que se dictamina, encuentra sustento normativo, en lo
dispuesto por el artículo:
Artículo 1o. En los Estados Unidos Mexicanos todas las personas gozarán de los
derechos humanos reconocidos en esta Constitución.
Por todo lo expuesto y fundado, sometemos a consideración del Pleno el
siguiente proyecto de:
LIBRO PRIMERO
FAMILIA
CAPÍTULO I
Del Objeto y Disposiciones Generales
Objeto
Artículo 1. Las disposiciones del Derecho de Familia contenidas en este Código son de
orden público, de interés social y tienen por objeto proteger a la familia como
elemento primordial de la sociedad.
Supletoriedad
Artículo 2. A falta de disposición expresa se aplicará el Código Civil del Estado.
Artículo reformado 28-08-2025
Irrenunciabilidad
Artículo 3. El heredero o legatario no puede enajenar la parte de los bienes que le
corresponde de la herencia sino después de verificada la partición.”
Enajenación por parte del heredero
Artículo 4. El que entre a la herencia repudiada, puede impedir que la acepten los
acreedores.
Párrafo adicionado D.O. XX-09-2021
Heredero declarado proveniente de legatario o acreedor hereditario
Artículo 5. El que a instancias de un legatario haya sido declarado heredero debe
ser considerado como tal.
TRANSITORIOS:
Artículo Primero.- El presente Decreto entrará en vigor.
"""


def _unidades(perfil=None):
    return parse_texto(_INDICE, huecos=True, perfil=perfil or yucatan.PERFIL,
                       epigrafe_max=EPIGRAFE_MAX_ESTATAL, notas=_NOTAS)


def test_la_ley_empieza_tras_el_indice_y_la_exposicion():
    us = _unidades()
    assert [u.numero for u in us] == [1, 2, 3, 4, 5]
    assert us[0].cuerpo.startswith("Artículo 1. Las disposiciones del Derecho de Familia")
    assert us[0].capitulo.startswith("CAPÍTULO I") and us[0].titulo == "LIBRO PRIMERO. FAMILIA"
    # Sin el rasgo, el 'TRANSITORIOS' del índice corta la ley.
    assert all(not u.cuerpo.split("\n", 1)[1:] for u in _unidades(ESTATAL_BASE))


def test_notas_y_epigrafes_de_yucatan():
    us = {u.numero: u for u in _unidades()}
    assert us[2].cuerpo.rstrip().endswith("Artículo reformado 28-08-2025")
    assert us[3].epigrafe == "Irrenunciabilidad"
    assert us[3].cuerpo.rstrip().endswith("verificada la partición.”")
    assert us[4].epigrafe == "Enajenación por parte del heredero"
    assert us[4].cuerpo.rstrip().endswith("Párrafo adicionado D.O. XX-09-2021")
    assert us[5].epigrafe == "Heredero declarado proveniente de legatario o acreedor hereditario"
    assert "Heredero declarado" not in us[4].cuerpo


def test_las_notas_de_yucatan():
    for s in ("Artículo reformado 28-08-2025", "Título reformado 28-08-2025",
              "Párrafo adicionado D.O. XX-09-2021", "Fracción reformada D.O. 28-06-2023"):
        assert _NOTAS.match(s), s
    assert not _NOTAS.match("Artículo 5.- El 12-05-2020 se publicó")


def _renglon(top):
    return {"texto": "x", "top": top}


def test_interlineado_de_las_paginas_de_la_ley():
    texto = ("ÍNDICE\nARTÍCULO 1. Objeto\nARTÍCULO 2. Otro\n"
             "Artículo 1. Las disposiciones de esta ley son de orden público y\n"
             "Artículo 2. Toda persona tiene derecho a que se le administre justicia.\n"
             "TRANSITORIOS:\nArtículo Primero.- El presente Decreto entrará en vigor.\n")
    paginas = ["ÍNDICE\nARTÍCULO 1. Objeto",
               "Artículo 1. Las disposiciones de esta ley son de orden público y\n"
               "Artículo 2. Toda persona tiene derecho a que se le administre justicia.",
               "TRANSITORIOS:\nArtículo Primero.- El presente Decreto entrará en vigor."]
    ley = [_renglon(100 + 20 * k) for k in range(10)]
    decretos = [_renglon(100 + 12 * k) for k in range(40)]
    geometria = [[_renglon(100), _renglon(111)], ley, decretos]
    assert articulado._interlineado(geometria) == 12
    assert _interlineado_de_la_ley(paginas, geometria, texto, yucatan.PERFIL) == 20


def test_epigrafe_partido_tras_particula():
    # 'Atribuciones …, erigido como' / 'Tribunal Constitucional' sobre un
    # artículo derogado: todo es el epígrafe del 34, nada queda en el 33.
    renglones = []
    for n in range(10, 34):
        renglones += [f"Epígrafe del artículo {n}",
                      f"Artículo {n}.- Texto del artículo {n}, que cierra con punto."]
    renglones += ["Atribuciones del Tribunal Superior de Justicia del Estado, erigido como",
                  "Tribunal Constitucional", "Artículo 34.- Se deroga.",
                  "Artículo derogado DO 28-08-2025",
                  "Substanciación de los asuntos", "Artículo 35.- Se deroga."]
    texto = "\n".join(renglones) + "\n"
    us = {u.numero: u for u in parse_texto(texto, start=10, huecos=True, perfil=yucatan.PERFIL,
                                           epigrafe_max=EPIGRAFE_MAX_ESTATAL, notas=_NOTAS)}
    assert us[33].cuerpo.rstrip().endswith("que cierra con punto.")
    assert us[34].epigrafe == ("Atribuciones del Tribunal Superior de Justicia del Estado, "
                               "erigido como Tribunal Constitucional")
    sin = {u.numero: u for u in parse_texto(texto, start=10, huecos=True, perfil=ESTATAL_BASE,
                                            epigrafe_max=EPIGRAFE_MAX_ESTATAL, notas=_NOTAS)}
    assert "erigido como" in sin[33].cuerpo
