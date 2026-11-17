import re

from extractor.estatales import queretaro as q
from extractor.parsers.articulado import _notas_aparte

EN_LINEA = re.compile(q.NOTAS_EN_LINEA)
NOTAS = re.compile(q.NOTAS)


def test_variantes_de_nota():
    for n in ["(Ref. P.O. Mo. 87, 30-IX-21)", "(Ref. p.o. No.31, 4-IV-25)",
              "(Ref. P.O. No. 31. 4-IV-25)", "(Fe de Erratas P. O. No. 54, 7-VII-25)",
              "(Modificación según oficio DALJ/601/15 publicado en el P. O. No. 79, 15-X-15)",
              "(Adición P. O. No. 89, 22-XII-22) (esta adición entra en vigor 6 meses después "
              "de la fecha indicada, reformado a su vez, el 27 de enero de 2023 periódico número 5)"]:
        assert NOTAS.match(n), n


def test_nota_partida_y_pegada():
    t = ("XIV. La Secretaría de la Juventud; (Modificación según oficio DALJ/601/15 publicado en el P.\n"
         "O. No. 79, 15-X-15)\nXV. Otra; (Ref. P.O. Mo. 87, 30-IX-21)")
    s = _notas_aparte([t], EN_LINEA)[0].split("\n")
    assert s[0] == "XIV. La Secretaría de la Juventud;"
    assert s[1].endswith("P. O. No. 79, 15-X-15)")
    assert s[3] == "(Ref. P.O. Mo. 87, 30-IX-21)"


def test_conjuncion_antes_de_la_nota():
    t = "autoridad, o de particulares;\ny (Ref. P. O. No. 93, 27-IX-24)\nXXXII. Las demás."
    s = _notas_aparte([t], EN_LINEA)[0].split("\n")
    assert s[0] == "autoridad, o de particulares; y"
    assert s[1] == "(Ref. P. O. No. 93, 27-IX-24)"
