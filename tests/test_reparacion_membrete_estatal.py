"""Membrete de varios renglones y pie 'Página N de M' repetidos (Guanajuato)."""
from extractor.parsers.articulado import _sin_membrete_repetido

CAB = ("Ley X\nH. CONGRESO DEL ESTADO DE GUANAJUATO Expidió: LXIV Legislatura\n"
       "Publicada: P.O. Núm. 146, 22-07-2020\nSecretaria General\n"
       "Reforma: P.O. Núm. 96, 14-05-2026\nInstituto de Investigaciones Legislativas\n")


def _paginas(n=10):
    return [CAB + f"texto {i} de la ley\nsigue el texto\nPágina {i} de {n}" for i in range(1, n + 1)]


def test_quita_membrete_y_pie():
    for t in _sin_membrete_repetido(_paginas()):
        assert t.startswith("texto ") and "Página" not in t and "Publicada" not in t
        assert t.endswith("sigue el texto")


def test_no_quita_membrete_corto_ni_renglon_suelto():
    pag = [f"Ley X\nH. CONGRESO\ntexto {i}\notro" for i in range(10)]
    assert _sin_membrete_repetido(pag) == pag
    pag = _paginas()
    pag[3] = pag[3].replace("sigue el texto", "Instituto de Investigaciones Legislativas")
    assert "Instituto de Investigaciones Legislativas" in _sin_membrete_repetido(pag)[3]
