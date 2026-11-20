"""Guanajuato: nombres de encabezado partidos o con comas, párrafos sin punto
final que parecían epígrafe, nota de párrafo derogado y rótulos con letra."""
import re

from extractor.estatales import guanajuato as G
from extractor.parsers.articulado import parse_texto


def _parse(t, start=1):
    return parse_texto(t, start=start, huecos=True, estatal=True, epigrafe_max=80,
                       notas=re.compile(G.NOTAS), notas_previas=re.compile(G.NOTAS_PREVIAS))


def _cuerpo(us, numero, **k):
    return next(u for u in us if u.numero == numero
                and all(getattr(u, a) == v for a, v in k.items())).cuerpo


def test_nombre_de_capitulo_partido_sin_punto():
    us = _parse('''Artículo 228. Texto uno
que se refiere este Capítulo.
(REFORMADA SU DENOMINACIÓN, P.O. 5 DE DICIEMBRE DE 2017)
Capítulo II
Patrimonio natural, cultural urbano y arquitectónico, y áreas y centros de
población declarados Patrimonio Cultural
(REFORMADA SU DENOMINACIÓN, P.O. 5 DE DICIEMBRE DE 2017)
Sección Primera
Conservación del patrimonio natural
(REFORMADO, P.O. 5 DE DICIEMBRE DE 2017)
Artículo 229. Otro.
''')
    assert "población" not in _cuerpo(us, 228)
    assert us[1].capitulo.endswith("Patrimonio Cultural")


def test_nombre_de_seccion_con_comas():
    us = _parse('''Artículo 398. Uno.
Dos.
(ADICIONADO CON SU SECCIÓN Y LOS ARTÍCULOS QUE LA INTEGRAN, P.O. 29 DE MAYO DE 2026)
Capítulo V Bis
Del Juicio Electoral
Sección Única
Reglas particulares, procedencia y competencia.
Artículo 398 Bis. El juicio.
''')
    assert "Reglas" not in _cuerpo(us, 398, ordinal="")
    assert "Reglas particulares" in us[1].seccion


def test_parrafo_sin_punto_final_no_es_epigrafe():
    us = _parse('''Artículo 35.- Uno.
Los organismos descentralizados podrán ser creados por el Poder Legislativo
escuchando la opinión de la persona Titular del Poder Ejecutivo durante el proceso
legislativo. Asimismo, el Congreso del Estado sólo podrá extinguir los organismos
descentralizados creados por Ley
Artículo 36.- Otro.
''')
    assert "creados por Ley" in _cuerpo(us, 35)


def test_nota_de_parrafo_derogado_queda_en_su_articulo():
    us = _parse('''Artículo 6o.- Uno.
(REFORMADO, P.O. 14 DE ABRIL DE 2023)
Dos.
(DEROGADO PÁRRAFO TERCERO, P.O. 14 DE ABRIL DE 2023)
CAPÍTULO IV
OTRAS LEYES
Artículo 7o.- Tres.
''')
    assert "(DEROGADO PÁRRAFO TERCERO" in _cuerpo(us, 6)


def test_rotulos_con_letra_minuscula_y_sic():
    us = _parse('''Artículo 99.- Cero.
Artículo 99-w.- Uno.
(ADICIONADO, P.O. 3 DE JUNIO DE 2011)
Artículo 99-y (sic).- Dos.
Artículo 99-z.- Tres.
''', start=99)
    assert [(u.numero, u.letra) for u in us] == [(99, ""), (99, "W"), (99, "Y"), (99, "Z")]
    us = _parse('''Artículo 155.- Uno.
Artículo 155-a. Habrá homicidio.
Artículo 156.- Dos.
''', start=155)
    assert [(u.numero, u.letra) for u in us] == [(155, ""), (155, "A"), (156, "")]
    us = _parse('''Artículo 235.- Uno.
Artículo 235 ter.- Dos.
Artículo 235 ter-a.- Tres.
Artículo 239.- Cuatro.
Artículo 239-a.- Cinco.
Artículo 239 b. A quien imparta.
''', start=235)
    assert [(u.numero, u.letra, u.ordinal, u.sub_letra) for u in us][2:3] == [(235, "", "Ter", "a")]
    assert [(u.numero, u.letra) for u in us][-1] == (239, "B")
