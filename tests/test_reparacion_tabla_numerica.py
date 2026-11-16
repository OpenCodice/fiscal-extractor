from extractor.parsers.articulado import _quitar_marca_girada


def test_filas_numericas_de_tabla_no_son_marca_de_agua():
    filas = ["20 10", "22 9", "24 8", "26 7", "28 6", "30 5", "35 4", "40 o más 3"]
    marca = ["d", "e", "ie", "rn", "ju", "io", "c c", "IA"]
    pagina = "\n".join(["Artículo 27. Tabla:"] + filas + marca)
    salida = _quitar_marca_girada(pagina).splitlines()
    for f in filas:
        assert f in salida
    assert "ie" not in salida
