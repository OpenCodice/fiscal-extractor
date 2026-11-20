from extractor.parsers.articulado import _sin_membrete_repetido


def test_pie_pagina_en_minuscula():
    paginas = [f"Artículo {i}. Texto.\npágina {i} de 119" for i in range(1, 8)]
    assert all("página" not in t for t in _sin_membrete_repetido(paginas))


def test_epigrafe_tras_articulo_derogado_en_una_linea():
    from extractor.parsers.articulado import parse_texto
    texto = ("Artículo 27. Texto uno.\nArtículo 28. (DEROGADO, P.O. 29 DE MAYO DEL 2026)\n"
             "Atribuciones de las regidurías\nArtículo 29. Texto tres.\n")
    unidades = parse_texto(texto, start=27, estatal=True)
    u28 = next(u for u in unidades if u.numero == 28)
    assert "Atribuciones" not in u28.cuerpo
    assert next(u for u in unidades if u.numero == 29).epigrafe == "Atribuciones de las regidurías"
