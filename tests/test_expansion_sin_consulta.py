from extractor.estatales import ley
from extractor.fuentes import url_vigente
from extractor.registro import a_dict, de_dict

HTML = ('<a href="/leyes/pdf/LEY%20DE%20GOBIERNO%20MUNICIPAL.pdf?2025-11- 7">LGM</a>'
        '<a href="/leyes/pdf/OTRA.pdf?2026-01-01">otra</a>')
KW = dict(medio="P.O.", indice="https://www.hcnl.gob.mx/leyes/", patron=r"GOBIERNO%20MUNICIPAL")


def test_sin_consulta_descarta_la_consulta_con_espacio():
    doc = ley("nuevo-leon", "Ley de Gobierno Municipal del Estado de Nuevo León", "LGM",
              sin_consulta=True, **KW)
    assert url_vigente(doc, leer=lambda _u: HTML) == \
        "https://www.hcnl.gob.mx/leyes/pdf/LEY%20DE%20GOBIERNO%20MUNICIPAL.pdf"


def test_sin_la_opcion_nada_cambia():
    doc = ley("nuevo-leon", "Ley de Gobierno Municipal del Estado de Nuevo León", "LGM",
              consulta=True, **KW)
    assert not doc.sin_consulta
    assert "sin_consulta" not in a_dict(doc)
    assert url_vigente(doc, leer=lambda _u: HTML).endswith(".pdf?2025-11- 7")


def test_ida_y_vuelta():
    doc = ley("nuevo-leon", "Ley de Gobierno Municipal del Estado de Nuevo León", "LGM",
              sin_consulta=True, **KW)
    assert a_dict(doc)["sin_consulta"] is True
    assert de_dict(a_dict(doc)).sin_consulta
