import re

from extractor.estatales import queretaro as q
from extractor.normalize import normalize_body
from extractor.parsers.articulado import _notas_aparte, parse_texto

EN_LINEA = re.compile(q.NOTAS_EN_LINEA)


def test_no_duplicado_y_fe_de_erratas_y_digito_pegado():
    t = ("I. El Gobernador; (Ref. P.O. No. No. 87, 30-IX-21)\nII. Otro;\n"
         "Los sentidos: (Fe de erratas según oficio SSP/2398/20/LIX emitido por el Presidente\n"
         "de la Mesa Directiva, publicado en el P. O. No. 57, 3-VII-20)\nIII. Algo.\n"
         "Texto final. (Adición P. O. No. 80, 19-VIII-24)9\nCapítulo V")
    s = _notas_aparte([t], EN_LINEA)[0].split("\n")
    assert s[1] == "(Ref. P.O. No. No. 87, 30-IX-21)"
    assert any(x.startswith("(Fe de erratas según oficio") and x.endswith("3-VII-20)") for x in s)
    assert "(Adición P. O. No. 80, 19-VIII-24)" in s
    assert "9" not in s


def test_punto_y_coma_a_media_oracion_sigue():
    cuerpo = ("Artículo 1.\nEl sordo deberá dar lectura a su testamento;\n"
              "si no supiere, designará a otra persona.\nI. Fracción;\nII. Otra.")
    cortes = {("x", "y"): True}
    r = normalize_body(cuerpo, "Artículo 1.", cortes=cortes)
    assert "testamento; si no supiere" in r
    assert "\n\nI. Fracción;" in r
