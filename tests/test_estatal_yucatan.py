"""Leyes estatales de Yucatán: claves y expresiones de notas, sin red ni PDF."""
import re

from extractor.estatales import yucatan


def _todas():
    return list(yucatan.LEYES) + [d for d, _ in yucatan.FUERA]


def test_claves_de_yucatan():
    claves = [d.clave for d in _todas()]
    assert claves and all(c.startswith("yucatan/") for c in claves)
    assert len(set(claves)) == len(claves)


def test_fuera_con_motivo():
    assert all(isinstance(m, str) and m for _, m in yucatan.FUERA)
    assert all(c in {d.clave for d, _ in yucatan.FUERA} for c in getattr(yucatan, "FUERA_POR_DISENO", ()))


def test_medio_y_patrones():
    assert yucatan.MEDIO
    for d in _todas():
        assert d.medio == yucatan.MEDIO and d.indice and d.patron and d.notas
        re.compile(d.patron)


def test_patron_ignora_la_fecha_del_nombre():
    d = yucatan.LEYES[0]
    p = re.compile(d.patron, re.IGNORECASE)
    assert p.search("/storage/legislacion/codigos/ca9da342d9e6c5faf13d9e39e9ec6591_2022-06-10.pdf")
    assert p.search("/storage/legislacion/codigos/ca9da342d9e6c5faf13d9e39e9ec6591_2027-01-02.pdf")
    assert not p.search("/storage/legislacion/codigos/8203bd322be5e97fcb3a51358afe2e8a_2026-10-22.pdf")
    assert not p.search("/storage/legislacion/leyes/ca9da342d9e6c5faf13d9e39e9ec6591_2022-06-10.pdf")


def test_patron_de_nombre_estable():
    d = next(x for x in yucatan.LEYES if x.clave.endswith("seguridad-publica"))
    p = re.compile(d.patron, re.IGNORECASE)
    assert p.search("/storage/legislacion/leyes/ley_46.pdf")
    assert not p.search("/storage/legislacion/leyes/ley_460.pdf")


def test_notas_reales():
    n = re.compile(yucatan.NOTAS)
    for t in ("Párrafo reformado D.O. 03-01-2024", "Artículo adicionado D.O. 07-06-2022",
              "Fracción reformada D.O. 28-06-2023", "Párrafo reformado DO 11-05-2026",
              "Numeral recorrido (antes fracción VII) D.O. 09-10-2023",
              "Se recorre párrafo (antes párrafo segundo)D.O. 23-07-2020",
              "Artículo derogado D.O. 26-04-2024", "Artíuclo reformado D.O. 05-08-2024",
              "Fe de Erratas D.O. 12/VII/2019",
              "Fracción recorrida (antes fracción IV) DO 28-06-2023/ reformada DO 03-01-2024"):
        assert n.match(t), t


def test_notas_no_son_texto_normal():
    n = re.compile(yucatan.NOTAS)
    for t in ("Artículo 5.- Los municipios publicarán en el D.O. 3 días antes.",
              "H. Congreso del Estado de Yucatán Última Reforma D.O.07 junio 2022",
              "Secretaría General del Poder Legislativo",
              "Los actos se publicarán en el Diario Oficial del Gobierno del Estado.",
              "I.- Cumplir con las leyes, el Bando de Policía y Gobierno;"):
        assert not n.match(t), t
