from extractor.parsers.articulado import ARTICULO_ESTATAL_RE, parse_texto


def test_letra_enie():
    m = ARTICULO_ESTATAL_RE.match("Artículo 100 Ñ. (Derogado)")
    assert m and m.group(2) == "Ñ"


TEXTO = """Artículo 19.- Texto uno.
Artículo 20.- Primer párrafo del veinte.
20 A. El procedimiento para la elección se sujetará a la Constitución.
Artículo 21.- Texto veintiuno.
Artículo 22.- Fracción
I. Uno;
X. Juez Menor.
Derogado
Artículo 23.- Texto.
"""


def test_variante_sin_palabra_articulo_y_derogado_final():
    us = {u.clave: u for u in parse_texto(TEXTO, start=19, estatal=True)}
    assert "020-a" in us
    assert "020-a" in us and "20 A." not in us["020"].cuerpo
    assert us["022"].cuerpo.rstrip().endswith("Derogado")
