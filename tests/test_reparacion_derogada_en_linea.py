"""Una fracción o inciso derogado con su nota en el mismo renglón del PDF
('XII. (DEROGADA, P.O. …);') es un solo párrafo, no rótulo + nota + ';'."""
import re

from extractor.parsers.articulado import _notas_aparte
from extractor.estatales.guanajuato import NOTAS_EN_LINEA


def _aparte(texto):
    return _notas_aparte([texto], re.compile(NOTAS_EN_LINEA))[0]


def test_fraccion_derogada_queda_en_un_renglon():
    out = _aparte("XI. Proponer al Consejo;\nXII. (DEROGADA, P.O. 26 DE MAYO DE 2017);\nXIII. Notificar.")
    assert "XII. (DEROGADA, P.O. 26 DE MAYO DE 2017);\n" in out
    assert "\n;" not in out


def test_inciso_derogado_sin_punto_y_coma():
    out = _aparte("a) Algo;\nb) (DEROGADO, P.O. 21 DE NOVIEMBRE DE 2003)\nc) Otro;")
    assert "b) (DEROGADO, P.O. 21 DE NOVIEMBRE DE 2003)\n" in out


def test_nota_previa_normal_sigue_aparte():
    out = _aparte("(REFORMADO, P.O. 3 DE JUNIO DE 2011)\nXII. Texto;")
    assert out.startswith("(REFORMADO, P.O. 3 DE JUNIO DE 2011)\nXII.")
