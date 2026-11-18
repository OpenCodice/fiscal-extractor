"""Leyes estatales: 'o' al fin de renglón con hueco, '(SIC) 135 QUÁTER.-' como rótulo y una nota de
Querétaro partida por el salto de página. Sin PDF."""
import re

from extractor.estatales import queretaro
from extractor.parsers.articulado import (ARTICULO_ESTATAL_RE, _notas_aparte,
                                          cortes_geometricos)

MARGEN = 527.0
PASO = 11.5


def renglon(texto, top, x1=MARGEN, palabra=30.0):
    return {"texto": texto, "top": top, "x1": x1, "margen": MARGEN, "palabra": palabra}


def relleno(top=50.0):
    salida = []
    for k in range(4):
        top += PASO
        salida.append(renglon(f"relleno {k} que llega al margen", top))
    salida[-1]["x1"] = 200.0
    return salida, top


def test_conjuncion_o_al_fin_de_renglon_con_hueco_sigue():
    p, top = relleno()
    a = renglon("No se autorizará la fusión de lotes, unidades privativas o", top + 2 * PASO, 336.0)
    b = renglon("que pertenezcan a desarrollos inmobiliarios diferentes ya autorizados.",
                top + 2 * PASO + 69.0, 527.0, palabra=22.0)
    p += [a, b]
    texto = a["texto"] + "\n" + b["texto"]
    assert cortes_geometricos([p], texto)[(a["texto"], b["texto"])] is False


def test_inciso_que_cierra_con_punto_y_coma_o_no_se_une_al_siguiente():
    p, top = relleno()
    a = renglon("ii) Individual; o", top + 2 * PASO, 300.0)
    b = renglon("iii) Grupal.", top + 2 * PASO + 69.0, 200.0)
    p += [a, b]
    assert cortes_geometricos([p], a["texto"] + "\n" + b["texto"]).get(
        (a["texto"], b["texto"])) is not False


def test_o_suelta_antes_de_un_inciso_no_se_une():
    p, top = relleno()
    a = renglon("o", top + 2 * PASO, 161.4)
    b = renglon("b) Contar con una experiencia mínima de 2 años", top + 2 * PASO + 25.0)
    p += [a, b]
    assert cortes_geometricos([p], a["texto"] + "\n" + b["texto"]).get(
        (a["texto"], b["texto"])) is not False


def test_o_al_fin_de_renglon_con_hueco_y_mayuscula_no_se_decide():
    p, top = relleno()
    a = renglon("Se impondrá prisión o", top + 2 * PASO, 336.0)
    b = renglon("Multa de cien días.", top + 2 * PASO + 69.0, 300.0)
    p += [a, b]
    texto = a["texto"] + "\n" + b["texto"]
    assert cortes_geometricos([p], texto).get((a["texto"], b["texto"])) is not False


def test_renglon_justificado_en_punto_y_mayuscula_sigue():
    # Llega al margen (a menos de un punto): un renglón justificado que sigue.
    p, top = relleno()
    a = renglon("conforme al artículo 5 de este Código.", top + 2 * PASO, 526.8)
    b = renglon("Quien lo infrinja será sancionado.", top + 3 * PASO, 400.0, palabra=40.0)
    p += [a, b]
    assert cortes_geometricos([p], a["texto"] + "\n" + b["texto"])[(a["texto"], b["texto"])] is False


def test_sic_antes_del_numero_es_rotulo_de_articulo():
    m = ARTICULO_ESTATAL_RE.match("(SIC) 135 QUÁTER.- Este delito se considerará tentativa")
    assert m and m.group(1) == "135"
    assert not ARTICULO_ESTATAL_RE.match("(SIC) lo que dice el texto")
    assert not ARTICULO_ESTATAL_RE.match("(SIC) 135 Este delito")


def test_nota_partida_por_el_salto_de_pagina_va_en_su_renglon():
    nota = re.compile(queretaro.NOTAS_EN_LINEA)
    p1 = ("VI. La autorización de la ubicación de las superficies; (Fe de erratas según oficio\n"
          "DALJ/2678/18/LVIII emitido por el Presidente de la Mesa Directiva de la LVIII Legislatura")
    p2 = ("del Estado de Querétaro, publicado en el P. O. No. 38, 11-V-18)\n"
          "VII. Plazo de iniciación de las obras;")
    a, b = _notas_aparte([p1, p2], nota)
    assert a.split("\n") == [
        "VI. La autorización de la ubicación de las superficies;",
        "(Fe de erratas según oficio DALJ/2678/18/LVIII emitido por el Presidente de la Mesa "
        "Directiva de la LVIII Legislatura del Estado de Querétaro, publicado en el P. O. No. 38, "
        "11-V-18)"]
    assert b == "VII. Plazo de iniciación de las obras;"
