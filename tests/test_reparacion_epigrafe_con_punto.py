from extractor.parsers.articulado import parse_texto

TEXTO = """Artículo 1. Primer artículo.
Capítulo IV
De la financiación y del fomento.
Artículo 2. Segundo artículo.
Capítulo V
De la participación social.
Artículo 3. Tercer artículo.
"""


def test_nombre_de_capitulo_con_punto_no_queda_en_el_articulo_anterior():
    unidades = parse_texto(TEXTO, estatal=True)
    por_numero = {u.numero: u for u in unidades}
    assert "financiación" not in por_numero[1].cuerpo
    assert "participación" not in por_numero[2].cuerpo
    assert "financiación" in por_numero[2].capitulo
    assert "participación" in por_numero[3].capitulo
