"""Leyes estatales: cortes de párrafo por la geometría del PDF y los rótulos y
notas que sus PDF escriben. Sin PDF: las páginas se describen renglón por
renglón."""
import re

from extractor.estatales import cdmx, jalisco
from extractor.normalize import normalize_body as _normalize_body
from extractor.parsers.articulado import (ARTICULO_ESTATAL_RE, ARTICULO_RE,
                                          cortes_geometricos)
from extractor.parsers.articulado import parse_texto as _parse_texto

MARGEN = 527.0
PASO = 11.5
# Ancho de una palabra corta al principio de un renglón, con su espacio.
PALABRA = 30.0


def renglon(texto, top, x1=MARGEN, palabra=PALABRA):
    return {"texto": texto, "top": top, "x1": x1, "margen": MARGEN, "palabra": palabra}


def pagina(*renglones):
    """Renglones (texto, x1, salto antes) desde arriba de la página, tras unos
    renglones de relleno a interlineado normal (el que se mide)."""
    top, salida = 50.0, []
    for k in range(4):
        top += PASO
        salida.append(renglon(f"relleno {k} que llega al margen", top))
    salida[-1]["x1"] = 200.0
    top += 2 * PASO
    for texto, x1, salto in renglones:
        top += salto
        salida.append(renglon(texto, top, x1))
    return salida


def normalize_body(cuerpo, cortes=None):
    return _normalize_body(cuerpo, "", rotulo=ARTICULO_ESTATAL_RE, cortes=cortes)


def test_renglon_justificado_que_termina_en_punto_sigue():
    p = pagina(("aumentada a juicio de la autoridad judicial;", MARGEN, 0),
               ("si la reincidencia fuere por delitos del mismo género.", 315.0, PASO),
               ("La sanción a los delincuentes habituales.", 366.0, 2 * PASO))
    texto = "\n".join(r["texto"] for r in p[4:])
    cortes = cortes_geometricos([p], texto)
    assert cortes[(p[4]["texto"], p[5]["texto"])] is False
    assert cortes[(p[5]["texto"], p[6]["texto"])] is True
    assert normalize_body(texto, cortes).split("\n\n") == [
        "aumentada a juicio de la autoridad judicial; si la reincidencia fuere por delitos "
        "del mismo género.", "La sanción a los delincuentes habituales."]
    # Sin geometría, como siempre: el punto y coma cierra el párrafo.
    assert len(normalize_body(texto).split("\n\n")) == 3


def test_parrafo_sin_punto_cierra_con_el_espacio_entre_parrafos():
    p = pagina(("cubierta en los términos que señale la normatividad correspondiente", 372.8, 0),
               ("El o la titular de la Alcaldía garantizará al Concejo un espacio.", 341.2,
                2 * PASO))
    texto = "\n".join(r["texto"] for r in p[4:])
    assert len(normalize_body(texto, cortes_geometricos([p], texto)).split("\n\n")) == 2
    assert len(normalize_body(texto).split("\n\n")) == 1


def test_renglon_sin_justificar_sigue_si_no_cabia_la_palabra():
    # El renglón acaba 38 pt antes del margen, pero 'Gobierno' no cabía.
    p = pagina(("las Alcaldías actuarán en coordinación con el", 489.3, 0),
               ("Gobierno de la Ciudad y con las instancias competentes.", MARGEN, PASO))
    p[-1]["palabra"] = 42.0
    texto = "\n".join(r["texto"] for r in p[4:])
    assert cortes_geometricos([p], texto)[(p[4]["texto"], p[5]["texto"])] is False


def test_salto_forzado_a_media_oracion_no_se_decide():
    # Con sitio de sobra y sin cerrar la oración: lo decide el texto.
    p = pagina(("tomar el curso prenupcial impartido a través de la Dirección", 329.7, 0),
               ("General del Registro Civil.", 191.6, PASO))
    texto = "\n".join(r["texto"] for r in p[4:])
    assert cortes_geometricos([p], texto) == {}
    assert normalize_body(texto, {}) == (
        "tomar el curso prenupcial impartido a través de la Dirección General del Registro Civil.")


def test_inciso_que_cierra_con_y_corta_aunque_no_haya_espacio():
    p = pagina(("c. Ordenar vigilancia, por el tiempo que determine el juez; y", 400.0, 0),
               ("d. Ordenar la custodia de la víctima.", 300.0, PASO))
    texto = "\n".join(r["texto"] for r in p[4:])
    assert normalize_body(texto, cortes_geometricos([p], texto)).split("\n\n") == [
        "c. Ordenar vigilancia, por el tiempo que determine el juez; y",
        "d. Ordenar la custodia de la víctima."]


def test_marcador_tras_renglon_lleno_sin_puntuacion_sigue():
    p = pagina(("se estará a lo dispuesto por el artículo", MARGEN, 0),
               ("406. Para tal efecto, el juez resolverá.", 300.0, PASO),
               ("I. Uno de los incisos que cierra justo en el margen;", MARGEN, 2 * PASO),
               ("II. El siguiente inciso.", 200.0, PASO))
    texto = "\n".join(r["texto"] for r in p[4:])
    assert normalize_body(texto, cortes_geometricos([p], texto)).split("\n\n") == [
        "se estará a lo dispuesto por el artículo 406. Para tal efecto, el juez resolverá.",
        "I. Uno de los incisos que cierra justo en el margen;", "II. El siguiente inciso."]


def test_salto_de_pagina_y_renglones_quitados():
    a = pagina(("deberá contar con la autorización y registro del DIF-", MARGEN, 0),
               ("CONSEJERÍA JURÍDICA Y DE SERVICIOS LEGALES", 400.0, 3 * PASO))
    b = pagina(("CDMX.", 80.0, 0))
    texto = "deberá contar con la autorización y registro del DIF-\nCDMX."
    cortes = cortes_geometricos([a, b], texto)
    assert cortes == {(a[4]["texto"], "CDMX."): False}
    # El guion de una palabra compuesta no lleva espacio.
    assert normalize_body(texto, cortes) == (
        "deberá contar con la autorización y registro del DIF-CDMX.")


def test_par_con_decisiones_distintas_se_descarta():
    p = pagina(("Uno;", MARGEN, 0), ("dos.", 100.0, PASO),
               ("Uno;", 100.0, 2 * PASO), ("dos.", 100.0, 2 * PASO))
    texto = "\n".join(r["texto"] for r in p[4:])
    assert ("Uno;", "dos.") not in cortes_geometricos([p], texto)


def test_rotulos_estatales_nuevos():
    casos = {"Artículo 609. Sexties.": ("609", "Sexties"),
             "Art. 229. Son excluyentes": ("229", None),
             "Artículo 132G.": ("132", None), "Artículo 137-. Se aplicará": ("137", None),
             "Artículo 176-Ter2. En los casos": ("176", "Ter"),
             "ARTICULO 323 Sextus.- Los": ("323", "Sextus"),
             "ARTICULO 135 Quitus.": ("135", "Quitus"),
             "ARTÍCULO 356 CUARTER.- Lo": ("356", "CUARTER")}
    for s, (numero, ordinal) in casos.items():
        m = ARTICULO_ESTATAL_RE.match(s)
        assert m and m.group(1) == numero and m.group(4) == ordinal, s
    assert ARTICULO_ESTATAL_RE.match("Artículo 132G.").group(2) == "G"
    # El paréntesis que sigue al rótulo es del texto.
    us = _parse_texto("Artículo 58 (Derogado)\nArtículo 59 (Derogado)\n", start=58, estatal=True)
    assert [normalize_body(u.cuerpo) for u in us] == ["(Derogado)", "(Derogado)"]
    # La lectura federal no cambia.
    assert not ARTICULO_RE.match("Art. 229. Son excluyentes")


def test_notas_del_editor_y_fe_de_erratas():
    notas = re.compile(jalisco.NOTAS)
    cuerpo = ("Artículo 154-J. El servidor público que conozca de un hecho.\n"
              "(las porciones normativas resaltadas fueron reformadas mediante Decreto\n"
              "Número 27295/LXII/19, publicado en el Periódico Oficial el Estado de Jalisco\n"
              "el once de Julio del 2019, y declaradas inválidas en resolutivo segundo de\n"
              "la sentencia derivada de la Acción de Inconstitucionalidad 86/2019,\n"
              "pronunciada por el Pleno de la Suprema Corte de Justicia de la Nación).\n")
    partes = _normalize_body(cuerpo, "", notas, rotulo=ARTICULO_ESTATAL_RE).split("\n\n")
    assert len(partes) == 2 and partes[1].startswith("_(las porciones") and partes[1].endswith(")._")
    notas = re.compile(cdmx.NOTAS)
    for s in ("Fe de Erratas G.O. CDMX 13/11/2023", "Sic. G.O. CDMX 07/06/2017"):
        assert notas.match(s)
    assert not notas.match("Fe de lo anterior dará cuenta el Secretario.")
