"""Notas de reforma de Nuevo León mal separadas del texto (reparación autónoma):
sin paréntesis de apertura o de cierre, 'DEROGADO … PÁRRAFO' que cierra al artículo
anterior, nota del editor sin punto final y rótulos escritos de otra forma."""
import re

from extractor.estatales import nuevo_leon as nl
from extractor.normalize import normalize_body
from extractor.parsers.articulado import _rotulo_abreviado_completo, parse_texto

N = re.compile(nl.NOTAS)


def _parse(texto: str, start: int):
    return {u.etiqueta: u for u in parse_texto(
        _rotulo_abreviado_completo(texto), start, estatal=True, notas=N, notas_previas=N)}


def test_derogado_parrafo_cierra_el_articulo_anterior():
    u = _parse("""Artículo 87.- Los folios son las hojas.
(REFORMADO, P.O. 17 DE ENERO DE 2025)
La entrega de folios no podrá exceder de tres mil.
(DEROGADO ÚLTIMO PÁRRAFO, P.O. 17 DE ENERO DE 2025)
(REFORMADO, P.O. 13 DE OCTUBRE DE 2000)
Artículo 88.- La formación del libro.
(REFORMADO, P.O. 13 DE OCTUBRE DE 2000)
Artículo 89.- Los folios tendrán dimensiones.
""", 87)
    cuerpos = [x.cuerpo for x in u.values()]
    assert "DEROGADO ÚLTIMO PÁRRAFO" in cuerpos[0]
    assert "DEROGADO ÚLTIMO" not in cuerpos[1]
    assert "REFORMADO, P.O. 13 DE OCTUBRE DE 2000" in cuerpos[1]


def test_notas_sin_parentesis_de_apertura_son_del_articulo_siguiente():
    u = _parse("""ARTÍCULO 233.- EL QUE ASÍ OBRE.
REFORMADO, P.O. 09 DE JUNIO DE 2010)
ARTÍCULO 234.- LOS DEFENSORES PÚBLICOS.
ADICIONADO, P.O. 13 DE MARZO DE 2007) (FE DE ERRATAS, P.O. 18 DE ABRIL DE
2007)
ARTÍCULO 235.- OTRO TEXTO.
(ADICIONADO, P.O. 28 DE JULIO DE 2004
ARTÍCULO 236.- MÁS TEXTO.
""", 233)
    c = [x.cuerpo for x in u.values()]
    assert "REFORMADO" not in c[0] and "REFORMADO, P.O. 09 DE JUNIO DE 2010)" in c[1]
    assert "ADICIONADO" not in c[1]
    assert "FE DE ERRATAS, P.O. 18 DE ABRIL DE\n2007)" in c[2]
    assert "ADICIONADO, P.O. 28 DE JULIO DE 2004" not in c[2]
    assert "ADICIONADO, P.O. 28 DE JULIO DE 2004" in c[3]


def test_nota_sin_apertura_va_en_cursiva():
    cuerpo = normalize_body("Artículo 108.-\nDEROGADO, P.O. 17 DE ENERO DE 2025)\n", "Artículo 108", N)
    assert "_DEROGADO, P.O. 17 DE ENERO DE 2025)_" in cuerpo


def test_nota_del_editor_sin_punto_antes_de_un_capitulo():
    u = _parse("""ARTICULO 31.- (DEROGADO, P.O. 30 DE DICIEMBRE DE 1983)
N. DE E., LOS ARTICULOS 32 A 103, QUE INTEGRAN EL CAPITULO SEGUNDO,
TITULO SEGUNDO, FUERON SUSPENDIDOS
SECRETARIA DE HACIENDA Y CREDITO PUBLICO, P.O. 3 DE DICIEMBRE DE 1979
CAPITULO SEGUNDO
Del impuesto sobre Ingresos Mercantiles
ARTICULO 32.- El impuesto grava los ingresos.
""", 31)
    a, b = u.values()
    assert "N. DE E." not in a.cuerpo
    assert b.capitulo.startswith("CAPITULO SEGUNDO")


def test_rotulos_escritos_de_otra_forma():
    u = _parse("""ARTÍCULO 161.- BASE.
ARTÍCULO 161 BIS 1.- DEROGADO. (P.O. 28 DE JULIO DE 2004.)
(ADICIONADO, P.O. 28 DE JULIO DE 2004)
ARTÍCULO161 BIS 2.- SE APLICARÁ LA SANCIÓN.
ART. 162.- OTRO.
ARTÌCULO 163.- UNO MÁS.
""", 161)
    assert [x.numero for x in u.values()] == [161, 161, 161, 162, 163]
    assert len(u) == 5


def test_titulo_sin_rotulo_tras_la_nota_que_lo_anota():
    u = _parse("""ARTÍCULO 299.- X.
ARTÍCULO 299 BIS.- CUANDO EL DELITO SE COMETA.
(ADICIONADO CON EL ARTÍCULO QUE LO INTEGRA, P.O. 16 DE ABRIL DE 2025)
DELITOS CONTRA LA PAZ Y SEGURIDAD DE LAS PERSONAS.
CAPÍTULO IV
ACECHO
(ADICIONADO, P.O. 16 DE ABRIL DE 2025)
ARTÍCULO 299 TER.- COMETE EL DELITO
""", 299)
    bis = list(u.values())[1]
    assert "DELITOS CONTRA" not in bis.cuerpo and "ADICIONADO" not in bis.cuerpo


def test_importe_tras_puntos_guia_sigue_en_su_fila():
    from extractor.parsers.articulado import ARTICULO_ESTATAL_RE
    b = ("Artículo 269.-\nI.- Por el examen para la patente, ya sea titular o\n"
         "suplente……………………………………………….\n204.5 cuotas\n"
         "(REFORMADA, P.O. 27 DE DICIEMBRE DE 1996)\nII.- Por servicios, anualmente………\n82 cuotas\n")
    cuerpo = normalize_body(b, "Artículo 269", N, ARTICULO_ESTATAL_RE, cortes={})
    assert "suplente………………………………………………. 204.5 cuotas" in cuerpo
    assert "anualmente……… 82 cuotas" in cuerpo
