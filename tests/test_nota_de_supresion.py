from extractor.normalize import normalize_body

NOTA = "Reforma DOF 11-12-2013: Derogó de la fracción el entonces párrafo cuarto"


def test_el_texto_que_sigue_a_la_nota_no_es_nota():
    cuerpo = normalize_body(
        "Artículo 43.- Las Entidades Federativas podrán establecer impuestos cedulares.\n"
        "ingresos.\n"
        f"{NOTA}\n"
        "Las Entidades Federativas podrán establecer distintas tasas dentro de los límites que establece el\n"
        "presente artículo por cada uno de los impuestos cedulares a que se refiere este artículo.\n",
        "Artículo 43")
    assert f"_{NOTA}_" in cuerpo.split("\n\n")
    assert cuerpo.rstrip().endswith("a que se refiere este artículo.")


def test_la_nota_que_envuelve_sigue_siendo_una_nota():
    cuerpo = normalize_body(
        "Artículo 2.- Texto del artículo.\n"
        "Reforma DOF 09-12-2013: Derogó del artículo el entonces párrafo cuarto (antes adicionado DOF\n"
        "26-12-1990, reformado DOF 15-12-1995)\n"
        "Reforma DOF 01-05-2019: Derogó del artículo los entonces párrafos tercero,\n"
        "cuarto y quinto\n",
        "Artículo 2")
    assert "_Reforma DOF 09-12-2013: Derogó del artículo el entonces párrafo cuarto (antes adicionado DOF " \
           "26-12-1990, reformado DOF 15-12-1995)_" in cuerpo
    assert "_Reforma DOF 01-05-2019: Derogó del artículo los entonces párrafos tercero, cuarto y quinto_" in cuerpo
