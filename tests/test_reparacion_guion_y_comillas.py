from extractor.modelo import Unidad
from extractor.parsers.articulado import ARTICULO_RE, _quitar_marca_girada, parse_texto


def test_numeral_con_guion_es_unidad_propia():
    texto = (
        "ARTÍCULO 58.- Uno.\n"
        "ARTÍCULO 58-1. Dos.\n"
        "ARTÍCULO 58-28.- Tres.\n"
        "ARTÍCULO 59.- Cuatro.\n"
    )
    us = parse_texto(texto, start=58)
    assert [u.clave for u in us] == ["058", "058-1", "058-28", "059"]
    assert us[1].etiqueta == "Artículo 58-1"
    assert us[2].cuerpo.endswith("Tres.")


def test_numeral_con_guion_tras_letra_y_ordinal():
    texto = (
        "Artículo 195.- Cero.\n"
        "Artículo 195-L.- Uno.\n"
        "Artículo 195-L-4. Dos.\n"
        "Artículo 195-Z-11 Bis.- Tres.\n"
        "Artículo 196.- Cuatro.\n"
    )
    us = parse_texto(texto, start=195)
    assert [u.clave for u in us] == ["195", "195-l", "195-l-4", "195-z-11-bis", "196"]
    assert [u.guion_num for u in us] == ["", "", "4", "11", ""]
    assert us[3].etiqueta == "Artículo 195-Z-11 Bis"


def test_numeral_con_guion_no_casa_en_cita_ni_en_anio():
    assert ARTICULO_RE.match("Artículo 19-1. (Se deroga).").group(3) == "1"
    assert ARTICULO_RE.match("Artículo 30-2019 de la Ley") is None
    assert Unidad(numero=19, guion_num="1").clave == "019-1"


def test_parrafo_final_con_comilla_de_cierre_no_es_epigrafe():
    texto = (
        "Artículo 13.- Primer párrafo que termina\n"
        "mediante reglas de carácter general.\n"
        "El valor del vehículo enajenado deberá estar expresado en el comprobante correspondiente en\n"
        "moneda nacional.”\n"
        "Artículo reformado DOF 29-12-1997\n"
        "Artículo 14. Siguiente.\n"
    )
    us = parse_texto(texto, start=13)
    assert "moneda nacional.”" in us[0].cuerpo
    assert "Artículo reformado DOF 29-12-1997" in us[0].cuerpo
    assert us[1].epigrafe == ""


def test_letra_del_simbolo_de_variable_no_es_marca_de_agua():
    formula = ["t", "1", "t", "i", "j", "* * t", "t", "i", "j", "t", "i"]
    pagina = "\n".join(
        ["que se determine de acuerdo con la siguiente fórmula:"] + formula
        + ["Donde:", "t *", ": Cuota aplicable al trasvase de aguas nacionales.",
           "t", "i : Cuota prevista en el artículo 223 de esta Ley.",
           "t", "j: Cuota prevista en el artículo 223 de esta Ley."])
    salida = _quitar_marca_girada(pagina).splitlines()
    i = salida.index("i : Cuota prevista en el artículo 223 de esta Ley.")
    assert salida[i - 1] == "t"
    j = salida.index("j: Cuota prevista en el artículo 223 de esta Ley.")
    assert salida[j - 1] == "t"
