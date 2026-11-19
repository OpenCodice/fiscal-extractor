from extractor.estatales import ley
from extractor.fuentes import url_vigente
from extractor.registro import a_dict, de_dict

_HTML = ('<a href="https://congreso-gto.s3.amazonaws.com/uploads/reforma/pdf/3737/'
         'LOPEEG_REF_03Nov2026.pdf">Ley</a>')


def _ley(**kw):
    return ley("guanajuato", "Ley Orgánica del Poder Ejecutivo del Estado de Guanajuato",
               "LOPEEG", medio="P.O.", indice="https://www.congresogto.gob.mx/leyes",
               patron=r"LOPEEG_REF", **kw)


def test_via_indice_solo_lee_el_indice_por_mx():
    llamadas = []

    def leer(url, via=None):
        llamadas.append(via)
        return _HTML
    d = _ley(via_indice="mx")
    assert url_vigente(d, leer).endswith("LOPEEG_REF_03Nov2026.pdf")
    assert llamadas == ["mx"]
    assert d.via is None  # la descarga del PDF va directa


def test_sin_la_opcion_nada_cambia():
    llamadas = []

    def leer(url, via=None):
        llamadas.append(via)
        return _HTML
    d = _ley()
    url_vigente(d, leer)
    assert llamadas == [None]
    assert "via_indice" not in a_dict(d)
    assert de_dict(a_dict(d)).via_indice is None


def test_via_indice_ida_y_vuelta():
    d = _ley(via_indice="mx")
    assert a_dict(d)["via_indice"] == "mx"
    assert de_dict(a_dict(d)).via_indice == "mx"
