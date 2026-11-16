from extractor.parsers.articulado import ARTICULO_RE, _quitar_marca_girada, parse_texto, _solo_articulado


def test_articulo_con_coma_de_millares():
    texto = "Artículo 999.- Uno.\nArtículo 1,000.- Dos.\nArtículo 1,001.- Tres.\n"
    assert [u.numero for u in parse_texto(texto, start=999)] == [999, 1000, 1001]


def test_bis_con_guion_y_numeral():
    texto = "Artículo 45.- Uno.\nArtículo 45 Bis-1.- Dos.\nArtículo 45 Bis-2.- Tres.\nArtículo 46.- Cuatro.\n"
    us = parse_texto(texto, start=45)
    assert [(u.numero, u.ordinal, u.ord_num) for u in us] == [
        (45, "", ""), (45, "Bis", "1"), (45, "Bis", "2"), (46, "", "")]


def test_rotulo_disposiciones_transitorias_en_minusculas():
    texto = "Artículo 1.- Uno.\nDisposiciones transitorias\nARTÍCULO CUARTO. Algo.\n"
    assert "transitorias" not in _solo_articulado(texto)


def test_marca_de_agua_girada():
    frag = ["D", "IA", "R", "IO", "O", "F", "IC", "IA", "L"]
    pagina = "Texto del artículo que sigue con peso que corresponde 1 5\n" + "\n".join(frag) + "\n0\n7\nfin."
    limpio = _quitar_marca_girada(pagina)
    assert limpio == "Texto del artículo que sigue con peso que corresponde\nfin."
    assert _quitar_marca_girada("I\nII\nIII\ntexto") == "I\nII\nIII\ntexto"
