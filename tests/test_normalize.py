"""Pruebas de normalización del cuerpo a párrafos + notas de reforma."""
from extractor.normalize import normalize_body


def test_quita_encabezado_y_conserva_texto():
    body = "Artículo 1o.- Esta Ley regula el comercio exterior."
    out = normalize_body(body, "Artículo 1o.")
    assert out == "Esta Ley regula el comercio exterior."


def test_quita_encabezado_en_mayusculas():
    # LAdua/LFPCA: encabezado en mayúsculas.
    out = normalize_body("ARTICULO 1o. Esta Ley regula el comercio.", "Artículo 1o.")
    assert out == "Esta Ley regula el comercio."


def test_nota_de_reforma_en_cursiva():
    body = "Artículo 1o.- Texto vigente.\nPárrafo reformado DOF 12-11-2021"
    out = normalize_body(body, "Artículo 1o.")
    assert "_Párrafo reformado DOF 12-11-2021_" in out


def test_nota_verbo_inicial_en_cursiva():
    # Bug real (LIEPS): notas que empiezan con el verbo ('Derogado DOF…').
    body = "Artículo 2o.- Texto.\nDerogado DOF 09-12-2019"
    out = normalize_body(body, "Artículo 2o.")
    assert "_Derogado DOF 09-12-2019_" in out


def test_fracciones_quedan_en_bloques_separados():
    body = (
        "Artículo 9o.- Se consideran residentes:\n"
        "I. Las personas físicas.\n"
        "II. Las personas morales."
    )
    out = normalize_body(body, "Artículo 9o.")
    bloques = out.split("\n\n")
    assert "I. Las personas físicas." in bloques
    assert "II. Las personas morales." in bloques


def test_reune_saltos_visuales_en_un_parrafo():
    # El PDF parte un párrafo en varias líneas; deben reunirse.
    body = (
        "Artículo 1o.- Esta Ley regula la entrada al territorio nacional y la\n"
        "salida del mismo de mercancías."
    )
    out = normalize_body(body, "Artículo 1o.")
    assert out.count("\n") == 0
    assert "nacional y la salida" in out
