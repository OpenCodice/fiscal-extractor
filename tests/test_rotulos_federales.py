"""Rótulos de artículo de las leyes federales que el parser no reconocía y que
dejaban un artículo dentro del anterior, sin archivo propio, y números que el
renglón de arriba deja pendientes y se leían como marcador de inciso."""
import pytest

from extractor.normalize import normalize_body
from extractor.parsers.articulado import ARTICULO_RE


@pytest.mark.parametrize("renglon, grupos", [
    # LGTOC: la letra en minúscula, con espacio.
    ("Artículo 228 a.- Los certificados de participación", ("228", "a", None, None)),
    ("Artículo 228 a bis.- Los “certificados de vivienda”", ("228", "a", None, "bis")),
    # La «o» separada de un número de varias cifras es la letra, no el ordinal.
    ("Artículo 228 o.- Los términos y condiciones", ("228", "o", None, None)),
    # LGOAAC: el guion separado de la letra.
    ("Artículo 81- B.- Para operar como centro cambiario", ("81", "B", None, None)),
    # LFPA: letra y ordinal separados por espacios.
    ("Artículo 69 C Bis.- Asimismo, a efecto de facilitar", ("69", "C", None, "Bis")),
    # Ley de Aviación Civil, Ley de Aeropuertos, LGAMVLV: ordinales tras Decies.
    ("Artículo 78 Undecies. La Agencia Federal de Aviación", ("78", None, None, "Undecies")),
    ("ARTICULO 73 QUINQUIESDECIES. Las personas concesionarias", ("73", None, None, "QUINQUIESDECIES")),
    ("ARTÍCULO 34 Quaterdecies.- En caso de que la persona", ("34", None, None, "Quaterdecies")),
    ("Artículo 78 Novodecies. La persona concesionaria", ("78", None, None, "Novodecies")),
    # Código de Justicia Militar.
    ("Artículo 30 Séptimus.- Para ser titular de un Juzgado", ("30", None, None, "Séptimus")),
    ("Artículo 30 Sextus.- Los Juzgados Militares", ("30", None, None, "Sextus")),
])
def test_rotulos_que_abren_articulo(renglon, grupos):
    m = ARTICULO_RE.match(renglon)
    assert m and m.groups()[:4] == grupos


@pytest.mark.parametrize("renglon, grupos", [
    ("Artículo 14-A.- Texto", ("14", "A", None, None)),
    ("Artículo 17-H Bis. Texto", ("17", "H", None, "Bis")),
    ("Artículo 118 A. Texto", ("118", "A", None, None)),
    ("Artículo 12 Quáter.- Texto", ("12", None, None, "Quáter")),
    ("Artículo 2 o.- Texto", ("2", None, None, None)),
    ("Artículo 10o.- Texto", ("10", None, None, None)),
    # La preposición tras el número no es la letra del artículo.
    ("Artículo 5 a que se refiere", ("5", None, None, None)),
    ("Artículo 3 A falta de disposición", ("3", None, None, None)),
])
def test_rotulos_que_no_cambian(renglon, grupos):
    assert ARTICULO_RE.match(renglon).groups()[:4] == grupos


def test_numero_que_el_renglon_anterior_deja_pendiente():
    cuerpo = ("Artículo 474.- Se aplicará, observándose, en su caso, lo dispuesto en el artículo\n"
              "457.\nEl juez resolverá.")
    assert normalize_body(cuerpo, "x") == (
        "Se aplicará, observándose, en su caso, lo dispuesto en el artículo 457.\n\nEl juez resolverá.")
    cuerpo = "Artículo 1983.- Se regirá por lo dispuesto en los artículos 2027 y\n2028."
    assert normalize_body(cuerpo, "x") == "Se regirá por lo dispuesto en los artículos 2027 y 2028."
    cuerpo = "Artículo 82.- La multa de la fracción\nXXXIV. se aplicará así."
    assert normalize_body(cuerpo, "x") == "La multa de la fracción XXXIV. se aplicará así."


def test_la_fraccion_tras_una_conjuncion_sigue_abriendo_parrafo():
    cuerpo = ("Artículo 13.- Son autores:\nVII.- Los que auxilien al delincuente, en cumplimiento de una promesa anterior al delito y\n"
              "VIII.- Los que sin acuerdo previo, intervengan con otros.")
    assert normalize_body(cuerpo, "x").split("\n\n")[-1].startswith("VIII.- Los que")


def test_un_inciso_numerado_sigue_abriendo_parrafo():
    cuerpo = "Artículo 1.- Son entidades:\n1. Aguascalientes, y\n2. Baja California\n3. Colima;\nI. Otra cosa"
    assert normalize_body(cuerpo, "x") == (
        "Son entidades:\n\n1. Aguascalientes, y\n\n2. Baja California\n\n3. Colima;\n\nI. Otra cosa")


def test_nombre_de_capitulo_con_punto_no_es_texto_del_articulo_anterior():
    from extractor.parsers.articulado import parse_texto
    texto = ("Artículo 391.- Salvo pacto en contrario, el cedente responderá de la legitimidad del crédito.\n"
             "CAPITULO IV\nDe la Consignación Mercantil.\nCapítulo adicionado DOF 05-06-2000\n"
             "Artículo 392.- La consignación mercantil es el contrato.")
    us = parse_texto(texto, start=391)
    assert [u.clave for u in us] == ["391", "392"]
    assert "Consignación" not in us[0].cuerpo
    assert "Consignación Mercantil" in us[1].capitulo


def test_cita_con_mayuscula_del_articulo_siguiente_no_lo_abre():
    from extractor.parsers.articulado import parse_texto
    texto = ("Artículo 73.- El Comité clasificará a las Sociedades en las categorías a que se refiere el\n"
             "Artículo 74 de esta Ley, según su adecuación a los Niveles de Capitalización.\n"
             "Artículo 74.- De manera enunciativa y no limitativa, deberán cumplir con las medidas.")
    us = parse_texto(texto, start=73)
    assert [u.clave for u in us] == ["073", "074"]
    assert "según su adecuación" in us[0].cuerpo
    assert us[1].cuerpo.startswith("Artículo 74.- De manera enunciativa")


def test_conjuncion_sola_cierra_la_fraccion_de_arriba():
    cuerpo = "Artículo 242.- Se impondrá:\nVII.- Al que haga uso indebido de ellos;\ny\nVIII.- Al que a sabiendas hiciere uso."
    assert normalize_body(cuerpo, "x") == (
        "Se impondrá:\n\nVII.- Al que haga uso indebido de ellos; y\n\nVIII.- Al que a sabiendas hiciere uso.")


def test_decimal_y_lista_de_articulos_no_abren_parrafo():
    cuerpo = "Artículo 3.- El recipiente deberá ser de cuando menos de 2.0 metros de ancho por\n0.75 metros de profundidad;"
    assert normalize_body(cuerpo, "x").count("\n\n") == 0
    cuerpo = "Artículo 56.- Conforme a lo establecido en los artículos 31, 149 o\n172. La impugnación sólo se admitirá."
    assert normalize_body(cuerpo, "x") == "Conforme a lo establecido en los artículos 31, 149 o 172. La impugnación sólo se admitirá."


def test_cita_del_articulo_siguiente_tras_un_parrafo_sin_punto():
    from extractor.parsers.articulado import parse_texto
    texto = ("Artículo 10.- Las Sociedades que tengan registrados un monto.\n"
             "Las Sociedades deberán cumplir con lo dispuesto en el\nArtículo 11 de la presente Ley.\n"
             "Las Sociedades, una vez autorizadas, podrán solicitar el cambio.\n"
             "Artículo 11.- La solicitud de autorización deberá acompañarse de lo siguiente:\nI. Las bases.")
    us = parse_texto(texto, start=10)
    assert [u.clave for u in us] == ["010", "011"]
    assert "lo dispuesto en el\nArtículo 11 de la presente Ley." in us[0].cuerpo
    assert us[1].cuerpo.startswith("Artículo 11.- La solicitud")


def test_encabezados_con_marca_o_punto_de_mas():
    from extractor.parsers.articulado import parse_texto
    texto = ("Artículo 42.- Las relaciones de trabajo se regirán por la Ley Federal del Trabajo.\n"
             "CAPÍTULO V (sic DOF 20-03-2014)\nDEL PROCEDIMIENTO DE QUEJA\n"
             "Capítulo recorrido y denominación reformada DOF 20-03-2014\n"
             "Sección Primera\nDisposiciones Generales.\n"
             "Artículo 43.- El Consejo conocerá de las quejas.\n"
             "Sección Segunda.\nDe su Integración y Funcionamiento.\n"
             "Artículo 44.- El Consejo se integrará así.")
    us = parse_texto(texto, start=42)
    assert [u.clave for u in us] == ["042", "043", "044"]
    assert us[0].cuerpo.strip() == "Artículo 42.- Las relaciones de trabajo se regirán por la Ley Federal del Trabajo."
    assert "PROCEDIMIENTO DE QUEJA" in us[1].capitulo and "Disposiciones Generales" in us[1].seccion
    assert "Integración y Funcionamiento" not in us[1].cuerpo
    assert "Integración y Funcionamiento" in us[2].seccion


def test_la_cita_de_un_libro_con_punto_no_es_encabezado():
    from extractor.parsers.articulado import parse_texto
    texto = ("Artículo 65.- La sanción no excederá del máximo señalado en el Título Segundo del\n"
             "Título Primero.\nArtículo 66.- Otro.")
    us = parse_texto(texto, start=65)
    assert "Título Primero." in us[0].cuerpo


def test_nombre_en_mayusculas_envuelto_que_cierra_con_punto():
    from extractor.parsers.articulado import parse_texto
    texto = ("Artículo 6.- Son sujetos de esta Ley los Abastecedores de Caña.\n"
             "TITULO SEGUNDO\nDE LAS AUTORIDADES Y DE LOS ORGANOS EN MATERIA DE LA AGROINDUSTRIA DE\n"
             "LA CAÑA DE AZÚCAR.\nCAPITULO I\nDe la Secretaría\n"
             "Artículo 7. La Secretaría realizará lo siguiente.")
    us = parse_texto(texto, start=6)
    assert us[0].cuerpo.strip() == "Artículo 6.- Son sujetos de esta Ley los Abastecedores de Caña."
    assert "LA CAÑA DE AZÚCAR" in us[1].titulo


def test_nombre_de_capitulo_con_abreviatura():
    from extractor.parsers.articulado import parse_texto
    texto = ("ARTÍCULO 9. Las autoridades universitarias serán electas por la Comunidad.\n"
             "Capítulo V\nDel H. Consejo Universitario y sus Comisiones.\n"
             "ARTÍCULO 10. El Consejo es la máxima autoridad.")
    us = parse_texto(texto, start=9)
    assert "Consejo Universitario y sus Comisiones" not in us[0].cuerpo
    assert "Consejo Universitario y sus Comisiones" in us[1].capitulo


def test_inciso_y_numero_solos_tras_un_renglon_sin_puntuacion():
    cuerpo = "Artículo 191.- Podrá optar por el beneficio señalado en el inciso\na).\nEl derecho sólo podrán ejercerlo."
    assert normalize_body(cuerpo, "x") == "Podrá optar por el beneficio señalado en el inciso a).\n\nEl derecho sólo podrán ejercerlo."
    cuerpo = "Artículo 40.- Sólo podrá realizarse por las uniones que se ubiquen en el nivel de operaciones\nIII."
    assert normalize_body(cuerpo, "x") == "Sólo podrá realizarse por las uniones que se ubiquen en el nivel de operaciones III."
    cuerpo = "Artículo 5.- Son requisitos:\nI. Ser mexicano;\nII.\nTener treinta años."
    assert normalize_body(cuerpo, "x").split("\n\n")[2].startswith("II.")


TABLA_GIRADA = """Apartado A, del artículo 223 de esta Ley, fuente de extracción aguas superficiales
e d a
d
o r a ZD 1
Zona de dispon
2
ib ilidad importador
3
a
4
n a
d
ni
bili
rt a
d 1
2
$
$
4
2
.
.
3 $1.9 759
ooo
Z s p x p 3 $1.5829 $0.9174 $0.6475
die
4 $1.5102 $0.8306 $0.5062 $0.4954
Apartado B, fracción I del artículo 223 de esta Ley, fuente de extracción aguas subterráneas"""


def test_tabla_con_rotulos_girados_lleva_su_marca():
    from extractor.parsers.articulado import bloques_ilegibles, sustituir_formulas
    assert [(a, b) for a, b, _ in bloques_ilegibles(TABLA_GIRADA)] == [(1, 28)]
    limpio = sustituir_formulas(TABLA_GIRADA, 201).split("\n")
    assert [x for x in limpio if x] == [
        "Apartado A, del artículo 223 de esta Ley, fuente de extracción aguas superficiales",
        "[Tabla: consultar el PDF oficial, página 201]",
        "Apartado B, fracción I del artículo 223 de esta Ley, fuente de extracción aguas subterráneas"]


def test_una_tabla_legible_o_una_lista_no_llevan_marca():
    from extractor.parsers.articulado import bloques_ilegibles
    tarifa = "\n".join(["Zona de disponibilidad", "ZD 1 2 3 4"] + [f"{n} $1.{n}599 $0.9174" for n in range(1, 15)])
    assert bloques_ilegibles(tarifa) == []
    lista = "Son entidades:\n" + "\n".join(f"{n}. Estado número {n};" for n in range(1, 20))
    assert bloques_ilegibles(lista) == []
    cifras = "\n".join(str(n % 10) for n in range(30))
    assert bloques_ilegibles(cifras) == []


def test_una_formula_sigue_siendo_formula():
    from extractor.parsers.articulado import MARCA_FORMULA, bloques_ilegibles
    formula = "Donde:\n" + "\n".join(["C", "i,t", "\uf03d", "x1", "b", "c", "d", "x2", "f", "g", "h", "i", "j", "k"])
    assert [m for _, _, m in bloques_ilegibles(formula)] == [MARCA_FORMULA]
