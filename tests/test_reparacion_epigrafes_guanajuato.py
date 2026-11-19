import re

from extractor.normalize import normalize_body
from extractor.parsers.articulado import parse_texto

NOTAS = re.compile(r"^\((?:ART[IÍ]CULO )?(?:REFORMAD|ADICIONAD)[^()]*\)$")


def _u(texto, **kw):
    return {u.clave if hasattr(u, "clave") else (u.numero, u.ordinal): u
            for u in parse_texto(texto, estatal=True, epigrafe_max=80,
                                 notas=NOTAS, notas_previas=NOTAS, **kw)}


def _con_epigrafes(n=22):
    """Un PDF donde casi todo artículo trae su epígrafe encima (sin comas)."""
    return "".join(f"Epígrafe número {k}\nArtículo {k}. Texto {k}.\n" for k in range(1, n))


def test_epigrafe_con_comas_antes_del_articulo_no_es_texto_del_anterior():
    t = (_con_epigrafes() +
         "Asimismo, se entenderán como sinónimos los conceptos.\n"
         "Universalidad, laicidad y gratuidad en la educación pública\n"
         "Artículo 22. La educación que imparta el Estado será:\n")
    us = parse_texto(t, estatal=True, epigrafe_max=80)
    assert "Universalidad" not in us[-2].cuerpo
    assert us[-1].epigrafe == "Universalidad, laicidad y gratuidad en la educación pública"


def test_parrafo_sin_punto_con_comas_sigue_siendo_texto_sin_convencion_de_epigrafes():
    t = ("Artículo 1. Uno.\n"
         "Asimismo, se entenderán como sinónimos los conceptos.\n"
         "Universalidad, laicidad y gratuidad en la educación pública\n"
         "Artículo 2. Dos.\n")
    us = parse_texto(t, estatal=True, epigrafe_max=80)
    assert "Universalidad" in us[0].cuerpo


def test_ordinales_quindecies_sexdecies_abren_articulo():
    t = ("Artículo 1. Cero.\n"
         "Artículo 1 quaterdecies. Uno.\n"
         "Delitos cometidos por servidores públicos\n"
         "Artículo 1 quindecies. Dos.\n"
         "Artículo 1 sexdecies. Tres.\n")
    us = parse_texto(t, estatal=True, epigrafe_max=80)
    assert [u.ordinal.lower() for u in us][1:] == ["quaterdecies", "quindecies", "sexdecies"]


def test_conjuncion_sola_cierra_la_fraccion():
    cortes = {("que se impugnó;", "y"): None}
    cuerpo = ("Artículo 238. Los plazos:\nII. El recurso, en lo que se impugnó;\ny\n"
              "III. Por consulta.\n")
    s = normalize_body(cuerpo, "Artículo 238", cortes={("x", "y"): True})
    assert "impugnó; y" in s
    assert "\n\ny\n" not in s


def test_ordinal_abreviado_no_corta_el_parrafo():
    cuerpo = ("Artículo 149. Ley Reglamentaria del artículo 3o.\n"
              "de la Constitución Política, en materia de Mejora.\n")
    s = normalize_body(cuerpo, "Artículo 149", cortes={("x", "y"): True})
    assert "3o. de la Constitución" in s
