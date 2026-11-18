"""Nuevo León: cita 'Artículo 48 de este código.' al inicio de renglón, '.' suelto
tras una fracción y corte entre la nota previa y el texto del rótulo."""
import re

from extractor.normalize import normalize_body
from extractor.parsers.articulado import ARTICULO_ESTATAL_RE, _ROTULO_EPIGRAFE_RE, parse_texto


def _estatal(texto, start=1):
    return parse_texto(texto, start=start, estatal=True, epigrafe_max=80)


def test_cita_de_articulo_al_inicio_de_renglon_no_abre_unidad():
    t = """Artículo 47.- Primer texto.
levantar acta parcial al respecto, la cual deberá reunir los requisitos que establece el
Artículo 48 de este código.
Artículo 48.- La visita se desarrollará así.
"""
    us = _estatal(t, 47)
    assert [u.numero for u in us] == [47, 48]
    assert "establece el\nArtículo 48 de este código." in us[0].cuerpo
    assert us[1].cuerpo.startswith("Artículo 48.- La visita")


def test_punto_suelto_tras_fraccion_sin_cierre_se_conserva():
    t = """Artículo 55.- Se podrá determinar cuando:
III.- Se dé alguna de las siguientes irregularidades
.
A).- Omisión del registro.
Artículo 56.- Otro.
"""
    us = _estatal(t, 55)
    assert "irregularidades.\nA).- Omisión" in us[0].cuerpo


def test_punto_suelto_sin_inciso_sigue_descartandose():
    t = """Artículo 1.- Texto del artículo
.
siguiente renglón.
"""
    assert "\n.\n" not in _estatal(t)[0].cuerpo


def test_corte_con_nota_previa_usa_el_renglon_con_rotulo():
    cuerpo = ("Artículo 149.-\n(ADICIONADO P.O. 20 DE FEBRERO DE 2009)\n"
              "Los testigos serán presentados por la parte oferente;\n"
              "y únicamente cuando ésta no pueda, lo comunicará.\n")
    cortes = {("Artículo 149.- Los testigos serán presentados por la parte oferente;",
               "y únicamente cuando ésta no pueda, lo comunicará."): False}
    notas = re.compile(r"^\((?:ADICIONADO|REFORMADO)[^)]*\)$")
    out = normalize_body(cuerpo, "Artículo 149", notas=notas, rotulo=ARTICULO_ESTATAL_RE,
                         cortes=cortes)
    assert out.endswith("oferente; y únicamente cuando ésta no pueda, lo comunicará.")


def test_rotulo_epigrafe_de_una_oracion():
    assert _ROTULO_EPIGRAFE_RE.match(
        "Artículo 53. De las sanciones por faltas o infracciones administrativas.")
    assert not _ROTULO_EPIGRAFE_RE.match("Artículo 5. Se prohíbe fumar. Además, beber.")
