"""Guanajuato: resincronía de los cortes geométricos tras renglones que el texto
limpio no conserva, fórmula en imagen que agranda un renglón, 'Art. 1°.-', nota
del editor tras el nombre de una sección y 'TITULO QUINTO.' con punto."""
import re

from extractor.parsers import articulado as A


def renglon(texto, top, x1, margen=524.0, palabra=15.0, justificada=True):
    return {"texto": texto, "top": top, "x1": x1, "palabra": palabra, "margen": margen,
            "justificada": justificada}


def _pagina(renglones):
    return [renglones] + [[renglon(f"x{k}", 12.0 * k, 524) for k in range(40)]]


def test_renglon_agrandado_por_formula_no_corta_la_oracion():
    a = renglon(": Es el coeficiente del incremento del Fondo General de Participaciones",
                296.0, 524.0)
    b = renglon("que se distribuye en función de la recaudación de Predial y Agua del municipio",
                317.0, 524.0)
    c = renglon("el año validada por el SNCF.", 332.0, 241.0)
    texto = "\n".join(r["texto"] for r in (a, b, c))
    cortes = A.cortes_geometricos(_pagina([a, b, c]), texto)
    assert cortes[(a["texto"], b["texto"])] is False


def test_renglon_corto_con_espacio_de_parrafo_si_corta():
    a = renglon("del actuario y de quien recibe, o la causa por la cual este último no firma", 494.0, 524)
    b = renglon("firmar", 506.0, 101)
    c = renglon("Las notificaciones personales podrán practicarse en el local del tribunal", 530.9, 524)
    texto = "\n".join(r["texto"] for r in (a, b, c))
    cortes = A.cortes_geometricos(_pagina([a, b, c]), texto)
    assert cortes[(b["texto"], c["texto"])] is True


def test_resincroniza_tras_una_racha_de_renglones_ausentes_del_texto():
    derogados = [renglon(f"Art. {n}.- (DEROGADO, P.O. 13 DE AGOSTO DE 2004)", 12.0 * k, 524)
                 for k, n in enumerate(range(195, 215))]
    a = renglon("de treinta días contados del siguiente al de la última publicación en el Periódico Oficial.",
                400.0, 523.9)
    b = renglon("Se fijará, además, en la puerta del tribunal una copia íntegra de la resolución por todo el",
                412.0, 523.9)
    texto = "\n".join([a["texto"], b["texto"]])    # los derogados no están en el texto limpio
    cortes = A.cortes_geometricos(_pagina(derogados + [a, b]), texto)
    assert cortes[(a["texto"], b["texto"])] is False


def test_rotulo_abreviado_con_grado():
    texto = A._rotulo_abreviado_completo("Art. 1°.- Solamente puede iniciarse\nArt. 2°.- Puede")
    assert texto.startswith("Artículo 1°.-")
    assert "\nArtículo 2°.-" in texto


NOTAS = re.compile(r"^(?:\((?:REFORMADO|ADICIONADO)[^()]*\)|N\.\s?DE\s?E\.[A-ZÁÉÍÓÚÑ0-9 ,.\n]*?\.(?=\n|$))$")


def _parse(texto):
    return A.parse_texto(texto, huecos=True, estatal=True, epigrafe_max=A.EPIGRAFE_MAX_ESTATAL,
                         notas=NOTAS, notas_previas=NOTAS)


def test_nota_del_editor_tras_la_seccion_es_del_articulo():
    us = _parse("""Artículo 61.- Texto del artículo anterior que termina aquí.
SECCION SEGUNDA
Secretario
N. DE E. EN RELACIÓN CON LA ENTRADA EN VIGOR DEL PRESENTE ARTÍCULO, VÉASE
ARTÍCULO SEGUNDO TRANSITORIO DEL DECRETO QUE MODIFICA ESTE
ORDENAMIENTO.
(REFORMADO, P.O. 27 DE DICIEMBRE DE 2011)
Artículo 62.- En todo acto de que deba dejarse constancia en autos, intervendrá
el secretario y lo autorizará con su firma.
Artículo 63.- Otro.
""")
    assert "N. DE E. EN RELACIÓN" in us[1].cuerpo and "ORDENAMIENTO." in us[1].cuerpo
    assert us[1].contexto.endswith("Secretario") or "N. DE E." not in us[1].contexto


def test_titulo_en_mayusculas_con_punto_no_queda_en_el_articulo():
    us = _parse("""Artículo 1.- Texto de uno.
Artículo 2.- A una presunción general puede oponérsele una presunción
especial, pero la prueba que destruye los efectos de la general.
TITULO QUINTO.
CAPITULO UNICO.
Resoluciones Judiciales.
Artículo 3.- En los casos en que no haya prevención especial de la ley.
""")
    f = us[1]
    assert "TITULO" not in f.cuerpo


def test_renglon_con_sangria_tras_oracion_a_ancho_completo_no_se_une():
    derogados = [renglon(f"Art. {n}.- (DEROGADO, P.O. 13 DE AGOSTO DE 2004)", 12.0 * k, 524)
                 for k, n in enumerate(range(195, 215))]
    x = renglon("Para obtener la autorización o reconocimiento de validez oficial de estudios",
                500.0, 541.0, margen=541.0)
    a = renglon("I. Presentar la validación del proyecto pedagógico por la instancia competente.",
                519.0, 541.0, margen=541.0)
    b = renglon("Tratándose de instituciones que requieran autorización, éstas deberán sujetarse",
                531.0, 541.0, margen=541.0)
    for r, x0 in ((x, 71.0), (a, 71.0), (b, 106.0)):
        r["x0"] = x0
    texto = "\n".join(r["texto"] for r in (x, a, b))
    cortes = A.cortes_geometricos(_pagina(derogados + [x, a, b]), texto)
    assert (a["texto"], b["texto"]) not in cortes     # lo decide el texto: cierra con punto
