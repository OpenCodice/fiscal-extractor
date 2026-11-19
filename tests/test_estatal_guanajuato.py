import re

from extractor.estatales import guanajuato as g
from extractor.fuentes import url_vigente

_BASE = "https://congreso-gto.s3.amazonaws.com/uploads/reforma/"
_HTML = (
    f'<a href="{_BASE}periodico_pdf/3737/PO_LOPEEG_REF_03Nov2026.pdf" target="blank">x</a>'
    f'<a href="{_BASE}pdf/3737/LOPEEG_REF_03Nov2026.pdf" target="blank">x</a>'
    f'<a href="{_BASE}pdf/3706/LOFEG_REF_21Abril2026.pdf" target="blank">x</a>'
    f'<a href="{_BASE}pdf/3721/c860c0f7-f2c5-493f-b436-24704e7b5a01.pdf">x</a>'
)


def _todas():
    return g.LEYES + [d for d, _ in g.FUERA]


def test_claves_del_estado():
    assert g.MEDIO
    for d in _todas():
        assert d.clave.startswith("guanajuato/")
    claves = [d.clave for d in _todas()]
    assert len(claves) == len(set(claves))
    assert all(isinstance(m, str) and m for _, m in g.FUERA)


def test_el_indice_se_lee_por_mx_y_el_pdf_directo():
    for d in _todas():
        assert d.via_indice == "mx"
        assert d.via is None
        assert d.indice in (g._LEYES, g._CODIGOS)


def test_patron_toma_el_pdf_vigente_y_no_el_periodico():
    ley = next(d for d in g.LEYES if d.clave.endswith("ley-organica-del-poder-ejecutivo")) \
        if any(d.clave.endswith("ley-organica-del-poder-ejecutivo") for d in g.LEYES) else \
        next(d for d, _ in g.FUERA if d.clave.endswith("ley-organica-del-poder-ejecutivo"))
    assert url_vigente(ley, lambda url, via=None: _HTML) == _BASE + "pdf/3737/LOPEEG_REF_03Nov2026.pdf"
    fiscalia = next(d for d in g.LEYES if d.clave.endswith("fiscalia-general"))
    assert url_vigente(fiscalia, lambda url, via=None: _HTML).endswith("/3706/LOFEG_REF_21Abril2026.pdf")


def test_las_siglas_no_se_confunden():
    # LOPEEG_REF_ no casa con otra ley cuyo nombre empieza igual.
    patron = re.compile(r"/reforma/pdf/\d+/LOPJEG_REF_")
    assert not patron.search(_BASE + "pdf/3737/LOPEEG_REF_03Nov2026.pdf")


_NOTAS = [
    "(REFORMADO, P.O. 3 DE JUNIO DE 2011)",
    "(ADICIONADA, P.O. 21 DE ABRIL DEL 2026)",
    "(RECORRIDA EN SU ORDEN, P.O. 21 DE ABRIL DEL 2026)",
    "(PÁRRAFO ADICIONADO, P.O. 10 DE ABRIL DE 2026)",
    "(DEROGADO PÁRRAFO TERCERO, P.O. 14 DE ABRIL DE 2023)",
    "(REFORMADO, P.O. 14 DE ABRIL DE 2023) (F. DE E., P.O. 24 DE ABRIL DE 2023)",
    "(REFORMADA SU DENOMINACIÓN, P.O. 24 DE OCTUBRE DE 2023)",
    "(PARRAFO REFORMADO, 30 DICIEMBRE 2022)",
    "(REUBICADO, ANTES CAPÍTULO IV, P.O. 3 DE JUNIO DE 2011)",
    "(ADICIONADO CON SU SECCIÓN Y LOS ARTÍCULOS QUE LA INTEGRAN,\nP.O. 29 DE MAYO DE 2026)",
    "N. DE E. EN RELACIÓN CON LA ENTRADA EN VIGOR DEL\nPRESENTE PÁRRAFO, VÉASE ARTÍCULO PRIMERO TRANSITORIO\nDEL DECRETO QUE MODIFICA EL ORDENAMIENTO.",
]
_TEXTO = [
    "Artículo 3. La presente Ley tiene por objeto regular la estructura.",
    "Objeto",
    "Capítulo XI",
    "Página 26 de 167",
    "(Se entenderá por Ley, la Ley Orgánica del Poder Judicial)",
    "I. Los servidores públicos adscritos a la Fiscalía General;",
    "Reforma: P.O. Núm. 79, Tercera Parte, 21-04-2026",
    "(REFORMADO por el Pleno, según el artículo 4 de la Ley)",
]


def test_notas_reconocen_renglones_reales():
    en_linea = re.compile(g.NOTAS_EN_LINEA)
    previas = re.compile(g.NOTAS_PREVIAS)
    for n in _NOTAS:
        assert en_linea.fullmatch(n), n
        una = re.sub(r"\s*\n\s*", " ", n)
        assert previas.match(una), n


def test_notas_no_reconocen_texto_normal():
    en_linea = re.compile(g.NOTAS_EN_LINEA)
    previas = re.compile(g.NOTAS_PREVIAS)
    for t in _TEXTO:
        assert not en_linea.search(t), t
        assert not previas.match(t), t


def test_dos_notas_seguidas_son_una_sola_coincidencia():
    t = "(REFORMADO, P.O. 14 DE ABRIL DE 2023) (F. DE E., P.O. 24 DE ABRIL DE 2023)\nTexto"
    m = re.search(g.NOTAS_EN_LINEA, t)
    assert m.group(0) == t.split("\n")[0]
