from types import SimpleNamespace

from extractor import tablas


def _fila(*celdas):
    return {"top": 0, "bottom": 10,
            "celdas": [None if c is None else (x, c, 1 if c else 0, False) for x, c in celdas]}


def test_la_fila_sale_celda_por_celda():
    fila = _fila((88, "81"), (122, "Del codo, con un ángulo de flexión hasta 70 grados."), (498, "10%"))
    assert tablas._renglon(fila) == "81 Del codo, con un ángulo de flexión hasta 70 grados. 10%"


def test_la_fila_partida_por_el_salto_de_pagina_vuelve_a_su_fila():
    anterior = {"bordes": [88, 122, 498],
                "filas": [_fila((88, "81"), (122, "Del codo, con un ángulo de flexión hasta"), (498, "10%"))]}
    tabla = {"bordes": [88, 122, 498],
             "filas": [_fila((88, ""), (122, "70 grados."), (498, "")), _fila((88, "82"), (122, "Otro."), (498, "5%"))]}
    assert tablas._sigue(anterior, tabla)
    tablas._unir(tabla["filas"][0], anterior["filas"][-1])
    assert tablas._renglon(anterior["filas"][-1]) == "81 Del codo, con un ángulo de flexión hasta 70 grados. 10%"


def test_una_fila_nueva_no_es_el_resto_de_la_anterior():
    anterior = {"bordes": [88, 122, 498], "filas": [_fila((88, "81"), (122, "Del codo."), (498, "10%"))]}
    nueva = {"bordes": [88, 122, 498], "filas": [_fila((88, "82"), (122, "Otro."), (498, "5%"))]}
    otra = {"bordes": [88, 300], "filas": [_fila((88, ""), (300, "70 grados."))]}
    assert not tablas._sigue(anterior, nueva)
    assert not tablas._sigue(anterior, otra)


def _chars(texto, x0, paso, top=700.0):
    return [{"text": c, "x0": x0 + k * paso, "x1": x0 + k * paso + paso * 0.9, "top": top, "bottom": top + 10}
            for k, c in enumerate(texto)]


def test_dos_textos_sobreimpresos_se_leen_uno_tras_otro():
    a, b = _chars("Zona exportadora", 93, 12), _chars("Zona importadora", 251, 6)
    pagina = SimpleNamespace(chars=a + b)
    renglon = {"text": "Zona eZxopnoar timapdoortraadora", "x0": 93, "x1": 400, "top": 700, "bottom": 710,
               "chars": [c for c in a + b if c["text"] != " "]}
    assert tablas._sin_sobreimpresion(pagina, renglon) == "Zona exportadora Zona importadora"


def test_un_renglon_normal_queda_igual():
    a = _chars("la McAllen", 93, 6)
    renglon = {"text": "la McAllen", "x0": 93, "x1": 160, "top": 700, "bottom": 710,
               "chars": [c for c in a if c["text"] != " "]}
    assert tablas._sin_sobreimpresion(SimpleNamespace(chars=a), renglon) == "la McAllen"


def test_el_resto_de_una_fila_puede_traer_su_primera_celda():
    anterior = {"bordes": [123, 300, 360, 420],
                "filas": [_fila((123, "Descargas de comercio; transporte por ducto;"), (300, "$2.96"), (360, "$4.38"), (420, "$6.54"))]}
    resto = {"bordes": [123, 300, 360, 420],
             "filas": [_fila((123, "servicios financieros y de seguros."), (300, ""), (360, ""), (420, ""))]}
    escalonada = {"bordes": [123, 300, 360, 420],
                  "filas": [_fila((123, "2"), (300, "$2.35"), (360, "$1.97"), (420, ""))]}
    assert tablas._sigue(anterior, resto)
    assert not tablas._sigue(anterior, escalonada)


def test_las_columnas_coinciden_aunque_el_borde_baile_un_punto():
    anterior = {"bordes": [67, 121, 465], "filas": [_fila((67, "377"), (121, "Diplopía que limita los movimientos de ambos"), (465, "60%"))]}
    resto = {"bordes": [67, 121, 464], "filas": [_fila((67, ""), (121, "ojos y reduce el campo visual."), (464, ""))]}
    assert tablas._sigue(anterior, resto)
