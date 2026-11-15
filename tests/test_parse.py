"""Pruebas del parser articulado, con casos diseñados para romperlo.

Cada caso aquí salió de un bug real encontrado al extraer el corpus fiscal:
sufijos en mayúsculas que colisionaban claves, encabezados ARTÍCULO en
mayúsculas (LAdua/LFPCA), el guion terminador confundido con letra, etc.
Se usa `parse_texto` (texto sintético, sin PDF) para aislar la lógica.
"""
import re
from datetime import date

import pytest

from extractor.parsers.articulado import (
    ARTICULO_RE,
    MESES,
    PAGE_FOOTER_RE,
    fechas_reforma_en,
    parse_texto,
    NUEVO_RE,
    VERSION_LARGA_RE,
    VERSION_RE,
)


def claves(texto, start=1):
    return [u.clave for u in parse_texto(texto, start=start)]


# --------------------------------------------------------------------------- #
# Secuencia y filtrado de citas
# --------------------------------------------------------------------------- #
def test_secuencia_basica():
    texto = "Artículo 1o.- Uno.\nArtículo 2o.- Dos.\nArtículo 3o.- Tres."
    assert claves(texto) == ["001", "002", "003"]


def test_cita_a_otro_articulo_no_inicia_unidad():
    # "artículo 89" en minúscula (cita) y "Artículo 89" fuera de secuencia: ninguno
    # debe iniciar una unidad nueva.
    texto = (
        "Artículo 1o.- En términos del artículo 89 de la Constitución y del "
        "Artículo 105 de esta Ley, se dispone lo siguiente.\n"
        "Artículo 2o.- Dos."
    )
    assert claves(texto) == ["001", "002"]


def test_jerarquia_captura_nombre_de_seccion():
    # Estructura real de la Cámara: NÚMERO y NOMBRE del encabezado en líneas
    # separadas; entre el nombre y el artículo puede ir una nota de reforma. El
    # nombre del régimen vive SOLO aquí (no en el cuerpo del Art. 1).
    texto = (
        "TÍTULO IV\n"
        "DE LAS PERSONAS FÍSICAS\n"
        "CAPÍTULO II\n"
        "DE LOS INGRESOS POR ACTIVIDADES EMPRESARIALES\n"
        "SECCIÓN IV\n"
        "DEL RÉGIMEN SIMPLIFICADO DE CONFIANZA\n"
        "Sección adicionada DOF 12-11-2021\n"
        "Artículo 1o.- Los contribuyentes personas físicas podrán optar."
    )
    us = parse_texto(texto)
    assert [u.clave for u in us] == ["001"]
    u = us[0]
    assert u.titulo == "TÍTULO IV. DE LAS PERSONAS FÍSICAS"
    assert u.seccion == "SECCIÓN IV. DEL RÉGIMEN SIMPLIFICADO DE CONFIANZA"
    # el contexto (para búsqueda) trae los NOMBRES, sin los números:
    assert "DEL RÉGIMEN SIMPLIFICADO DE CONFIANZA" in u.contexto
    assert "TÍTULO" not in u.contexto
    # y la nota de reforma NO se cuela en el cuerpo del artículo:
    assert "adicionada" not in u.cuerpo


def test_encabezado_sin_nombre_no_se_traga_el_articulo():
    # Si un encabezado no trae línea-nombre, el siguiente artículo debe iniciar
    # normalmente (no confundir el cuerpo con un nombre).
    texto = "TÍTULO I\nArtículo 1o.- Uno.\nArtículo 2o.- Dos."
    us = parse_texto(texto)
    assert [u.clave for u in us] == ["001", "002"]
    assert us[0].titulo == "TÍTULO I"          # solo número, sin nombre
    assert us[0].contexto == ""                # sin nombre → no aporta contexto


def test_articulo_derogado_conserva_secuencia():
    texto = (
        "Artículo 1o.- Uno.\n"
        "Artículo 2o.- (Se deroga).\n"
        "Artículo 3o.- Tres."
    )
    us = parse_texto(texto)
    assert [u.clave for u in us] == ["001", "002", "003"]
    assert us[1].derogado is True
    assert us[0].derogado is False


# --------------------------------------------------------------------------- #
# Sufijos: letra, ordinal, combinados, mayúsculas
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("encabezado,clave_esp", [
    ("Artículo 4o.-A.- Texto.", "004-a"),
    ("Artículo 14-A.- Texto.", "014-a"),
    ("Artículo 15-A. Texto.", "015-a"),
    ("Artículo 111 Bis.- Texto.", "111-bis"),
    ("Artículo 156-Bis. Texto.", "156-bis"),
    ("Artículo 20-Ter. Texto.", "020-ter"),
    ("Artículo 17-H Bis. Texto.", "017-h-bis"),
    ("Artículo 32-B Quáter. Texto.", "032-b-quater"),
    ("Artículo 32-B Quinquies. Texto.", "032-b-quinquies"),
])
def test_clave_de_sufijo(encabezado, clave_esp):
    # Se antepone el artículo base (bare) para que la variante sea aceptada, y se
    # parsea desde ese número (el articulado real arranca en 1, no en el base).
    base_num = int(re.match(r"\D+(\d+)", encabezado).group(1))
    texto = f"Artículo {base_num}.- Base.\n{encabezado}"
    cs = claves(texto, start=base_num)
    assert clave_esp in cs, f"{encabezado!r} → {cs}"


def test_ordinal_en_mayusculas_no_colisiona():
    # Bug real (LIVA/LIEPS): 'BIS/TER/QUÁTER' en mayúsculas colapsaban a una clave.
    texto = (
        "Artículo 18.- Base.\n"
        "Artículo 18-H.- H.\n"
        "Artículo 18-H BIS. Uno.\n"
        "Artículo 18-H TER. Dos.\n"
        "Artículo 18-H QUÁTER. Tres.\n"
        "Artículo 18-H QUINTUS. Cuatro."
    )
    cs = claves(texto, start=18)
    assert cs == ["018", "018-h", "018-h-bis", "018-h-ter", "018-h-quater", "018-h-quintus"]
    assert len(cs) == len(set(cs)), "claves duplicadas → colisión de archivos"


def test_ordinal_con_numeral_no_colisiona():
    # Bug real (LAdua): 'ARTICULO 137 bis 1..9' (ordinal + numeral) colapsaban a
    # una sola clave '137-bis'.
    texto = (
        "Artículo 137.- Base.\n"
        "ARTICULO 137 bis 1.- Uno.\n"
        "ARTICULO 137 bis 2.- Dos.\n"
        "ARTICULO 137 bis 9.- Nueve."
    )
    cs = claves(texto, start=137)
    assert cs == ["137", "137-bis-1", "137-bis-2", "137-bis-9"]
    assert len(cs) == len(set(cs))


def test_encabezado_en_mayusculas():
    # Bug real (LAdua 'ARTICULO', LFPCA 'ARTÍCULO'): encabezados en mayúsculas.
    texto = "ARTICULO 1o. Uno.\nARTÍCULO 2o.- Dos.\nARTICULO 3o. Tres."
    assert claves(texto) == ["001", "002", "003"]


def test_minuscula_no_es_encabezado():
    # 'artículo' en minúscula es cita, nunca encabezado.
    assert ARTICULO_RE.match("artículo 1o. de esta Ley") is None
    assert ARTICULO_RE.match("Artículo 1o.- Texto") is not None
    assert ARTICULO_RE.match("ARTÍCULO 1o.- Texto") is not None


def test_guion_terminador_no_es_letra():
    # Bug real: 'Artículo 80.- A quien...' tomaba la 'A' del cuerpo como letra.
    us = parse_texto("Artículo 79.- Uno.\nArtículo 80.- A quien cometa algo.", start=79)
    assert [u.clave for u in us] == ["079", "080"]
    assert us[1].letra == "", "el guion terminador se confundió con letra-sufijo"


# --------------------------------------------------------------------------- #
# Fechas de reforma
# --------------------------------------------------------------------------- #
def test_fechas_reforma_simple_y_encadenada():
    assert fechas_reforma_en("Reformado DOF 12-11-2021") == [date(2021, 11, 12)]
    # Encadenadas con coma en una sola cláusula DOF.
    fechas = fechas_reforma_en("Reformado DOF 04-12-2006, 10-06-2011")
    assert fechas == [date(2006, 12, 4), date(2011, 6, 10)]


def test_fechas_reforma_unicas_y_ordenadas():
    texto = "x DOF 10-06-2011 y DOF 05-02-2017 y otra vez DOF 10-06-2011"
    assert fechas_reforma_en(texto) == [date(2011, 6, 10), date(2017, 2, 5)]


def test_unidad_acumula_fechas_de_su_cuerpo():
    texto = (
        "Artículo 1o.- Uno.\n_Párrafo reformado DOF 12-11-2021_\n"
        "_Artículo reformado DOF 09-12-2019_"
    )
    u = parse_texto(texto)[0]
    assert u.fechas_reforma == [date(2019, 12, 9), date(2021, 11, 12)]
    assert u.ultima_reforma == date(2021, 11, 12)


# --------------------------------------------------------------------------- #
# Frontera de Transitorios
# --------------------------------------------------------------------------- #
def test_corta_en_transitorios():
    texto = (
        "Artículo 1o.- Uno.\nArtículo 2o.- Dos.\n"
        "TRANSITORIOS\nArtículo Primero.- Esto no es articulado."
    )
    assert claves(texto) == ["001", "002"]


# --------------------------------------------------------------------------- #
# Detección de versión (regex de portada)
# --------------------------------------------------------------------------- #
def test_version_ultima_reforma():
    m = VERSION_RE.search("... UNIÓN Última Reforma DOF 09-04-2026")
    assert m and (m.group(3), m.group(2), m.group(1)) == ("2026", "04", "09")


def test_version_nuevo_reglamento_fallback():
    assert VERSION_RE.search("... Nuevo Reglamento DOF 02-04-2014") is None
    m = NUEVO_RE.search("... UNIÓN Nuevo Reglamento DOF 02-04-2014")
    assert m and m.group(3) == "2014"


# --------------------------------------------------------------------------- #
# Formato de la normateca del SAT (compilaciones tipo RISAT)
# --------------------------------------------------------------------------- #
def test_fechas_reforma_en_letras():
    # Las compilaciones de la normateca anotan "(DOF 21 de diciembre de 2021)".
    assert fechas_reforma_en("(DOF 21 de diciembre de 2021)") == [date(2021, 12, 21)]
    fechas = fechas_reforma_en("x DOF 24 de agosto de 2015 y DOF 09-12-2019")
    assert fechas == [date(2015, 8, 24), date(2019, 12, 9)]


def test_version_en_letras():
    m = VERSION_LARGA_RE.search("Última reforma DOF 21 de diciembre de 2021")
    assert m and (m.group(1), MESES[m.group(2).lower()], m.group(3)) == ("21", 12, "2021")


def test_pie_de_pagina_normateca():
    # Cámara: "1 de 377"; normateca SAT: "51 / 131". Nunca texto normal.
    assert PAGE_FOOTER_RE.match("1 de 377")
    assert PAGE_FOOTER_RE.match("51 / 131")
    assert not PAGE_FOOTER_RE.match("división de poderes y 131")


def test_jerarquia_title_case_con_nombre_envuelto():
    # Estructura real del RISAT consolidado: encabezados Title-case, nombre del
    # Título III envuelto en dos líneas y nota de reforma con fecha en letras.
    texto = (
        "Título III\n"
        "De las Facultades previstas en la Ley Federal para la Prevención e "
        "Identificación de Operaciones con\n"
        "Recursos de Procedencia Ilícita\n"
        "Capítulo I\n"
        "De la Organización\n"
        "(DOF 21 de diciembre de 2021)\n"
        "Artículo 1.- Uno."
    )
    us = parse_texto(texto)
    assert [u.clave for u in us] == ["001"]
    u = us[0]
    assert u.titulo.startswith("Título III. De las Facultades previstas")
    assert u.titulo.endswith("Recursos de Procedencia Ilícita")
    assert u.capitulo == "Capítulo I. De la Organización"
    # ni el nombre envuelto ni la nota DOF se cuelan al cuerpo:
    assert "Procedencia" not in u.cuerpo and "diciembre" not in u.cuerpo


def test_jerarquia_title_case_con_ordinal_en_palabra():
    # Ley Aduanera / LSAT: 'Título Segundo' y 'Sección Primera' en Title-case.
    # Una cita con texto tras el numeral ('Título Segundo de esta Ley') no casa.
    texto = (
        "Título Segundo\n"
        "Control de aduana en el despacho\n"
        "Sección Primera\n"
        "Disposiciones generales\n"
        "Artículo 1o.- Uno conforme al\n"
        "Título Segundo de esta Ley.\n"
        "Artículo 2o.- Dos."
    )
    us = parse_texto(texto)
    assert [u.clave for u in us] == ["001", "002"]
    assert us[0].titulo == "Título Segundo. Control de aduana en el despacho"
    assert us[0].seccion == "Sección Primera. Disposiciones generales"
    assert "Título Segundo de esta Ley" in us[0].cuerpo


def test_encabezado_mayusculas_no_acepta_nombre_title_case():
    # En formato Cámara (encabezado en MAYÚSCULAS) un nombre Title-case sería
    # una línea de cuerpo: la heurística laxa solo aplica a encabezados Title-case.
    texto = (
        "Artículo 1o.- Uno.\n"
        "CAPÍTULO II\n"
        "Las personas morales deberán calcular el impuesto.\n"
        "Artículo 2o.- Dos."
    )
    us = parse_texto(texto)
    assert [u.clave for u in us] == ["001", "002"]
    assert us[1].capitulo == "CAPÍTULO II"
    assert "personas morales" in us[0].cuerpo


# --------------------------------------------------------------------------- #
# Bloques de encabezado entre artículos (leyes federales de la Cámara)
# --------------------------------------------------------------------------- #
def test_nombre_en_caja_normal_tras_encabezado_en_mayusculas():
    # Ley General de Salud: 'TÍTULO SEGUNDO' / 'Sistema Nacional de Salud' /
    # 'CAPÍTULO I' / 'Disposiciones Comunes'. Los nombres se pegaban al final
    # del artículo anterior.
    texto = (
        "Artículo 4o.- Son autoridades sanitarias:\n"
        "I. El Presidente de la República;\n"
        "TÍTULO SEGUNDO\n"
        "Sistema Nacional de Salud\n"
        "CAPÍTULO I\n"
        "Disposiciones Comunes\n"
        "Artículo 5o.- El Sistema Nacional de Salud está constituido por…"
    )
    us = parse_texto(texto, start=4)
    assert [u.clave for u in us] == ["004", "005"]
    assert "Sistema Nacional" not in us[0].cuerpo
    assert "Disposiciones" not in us[0].cuerpo
    assert us[1].titulo == "TÍTULO SEGUNDO. Sistema Nacional de Salud"
    assert us[1].capitulo == "CAPÍTULO I. Disposiciones Comunes"


def test_nombre_envuelto_en_varias_lineas():
    texto = (
        "Artículo 1o.- Uno.\n"
        "CAPITULO II\n"
        "De los derechos y obligaciones de los trabajadores y de los\n"
        "patrones en el trabajo a domicilio\n"
        "Artículo 2o.- Dos."
    )
    us = parse_texto(texto)
    assert us[0].cuerpo.strip().endswith("Uno.")
    assert us[1].capitulo.endswith("patrones en el trabajo a domicilio")


def test_encabezado_que_no_desemboca_en_articulo_no_se_come_texto():
    # Sin un artículo cerca, la línea en caja normal tras 'CAPÍTULO II' no es
    # un nombre: sigue siendo cuerpo del artículo.
    texto = (
        "Artículo 1o.- Lo previsto en el\n"
        "CAPÍTULO II\n"
        "Disposiciones de esta Ley aplica\n"
        "a todos los casos\n" + "".join(f"línea {i} del artículo\n" for i in range(20))
        + "Artículo 2o.- Dos."
    )
    us = parse_texto(texto)
    assert "Disposiciones de esta Ley aplica" in us[0].cuerpo


def test_notas_del_encabezado_no_van_al_articulo_anterior():
    # Ley Federal del Trabajo: la nota de reforma del Título y el '(Se deroga)'
    # de un capítulo derogado son de la estructura.
    texto = (
        "Artículo 172.- En los establecimientos en que trabajen mujeres…\n"
        "TITULO QUINTO BIS\n"
        "Trabajo de los Menores\n"
        "Título adicionado DOF 31-12-1974\n"
        "Artículo 173.- El trabajo de los menores…\n"
        "Artículo reformado DOF 30-11-2012\n"
        "CAPITULO IV\n"
        "Adulterio\n"
        "(Se deroga)\n"
        "Capítulo derogado DOF 08-06-2011\n"
        "Artículo 174.- (Se deroga)."
    )
    us = parse_texto(texto, start=172)
    assert [u.clave for u in us] == ["172", "173", "174"]
    assert "DOF" not in us[0].cuerpo
    # La nota del artículo (antes del encabezado) sí es suya.
    assert "Artículo reformado DOF 30-11-2012" in us[1].cuerpo
    assert "Se deroga" not in us[1].cuerpo and "Capítulo derogado" not in us[1].cuerpo


def test_libro_es_encabezado():
    texto = (
        "Artículo 122.- (Se deroga).\n"
        "LIBRO SEGUNDO\n"
        "TITULO PRIMERO\n"
        "Delitos contra la seguridad de la Nación\n"
        "Título con denominación reformado DOF 29-07-1970\n"
        "Artículo 123.- Se impondrá…"
    )
    us = parse_texto(texto, start=122)
    assert us[0].cuerpo.strip() == "Artículo 122.- (Se deroga)."
    assert us[1].titulo == "TITULO PRIMERO. Delitos contra la seguridad de la Nación"


def test_letra_tras_el_numeral_del_ordinal():
    # Ley General de Salud: 'Artículo 77 bis 35 A' … 'J' son artículos propios.
    texto = (
        "Artículo 77.- Uno.\n"
        "Artículo 77 bis 35.- El organismo…\n"
        "Artículo 77 bis 35 A.- Se deroga.\n"
        "Artículo 77 bis 35 B.- Se deroga.\n"
        "Artículo 78.- Otro."
    )
    us = parse_texto(texto, start=77)
    assert [u.clave for u in us] == ["077", "077-bis-35", "077-bis-35-a", "077-bis-35-b", "078"]
    assert us[2].etiqueta == "Artículo 77 Bis 35 A"


def test_nombre_de_encabezado_entre_comillas():
    # Ley del SAT: 'Título Quinto' / '"De la Información, … y de' / 'Fiscalización"'.
    texto = (
        "Artículo 20.- Uno.\n"
        "Artículo 20-A.- Texto.\n"
        "Artículo adicionado DOF 12-06-2003\n"
        "Título Quinto\n"
        "\"De la Información, la Transparencia y la Evaluación de la Eficiencia Recaudatoria y de\n"
        "Fiscalización\"\n"
        "Título adicionado DOF 12-06-2003\n"
        "Capítulo I\n"
        "\"De la Información y la Transparencia\"\n"
        "Capítulo adicionado DOF 12-06-2003\n"
        "Artículo 21.- Anualmente…"
    )
    us = parse_texto(texto, start=20)
    assert us[1].cuerpo.strip().endswith("Artículo adicionado DOF 12-06-2003")
    assert us[2].capitulo == "Capítulo I. \"De la Información y la Transparencia\""


def test_nombre_envuelto_con_mayuscula_y_subencabezado_sin_palabra_clave():
    # Reglamento de la LISR: tras el salto de página queda 'Disposiciones
    # Generales', un subencabezado sin 'CAPÍTULO'; LFD: nombre de Sección
    # envuelto cuya segunda línea empieza con mayúscula.
    texto = (
        "Artículo 12.- Doce.\n"
        "Artículo reformado DOF 06-05-2016\n"
        "TÍTULO II\n"
        "De las Personas Morales\n"
        "Disposiciones Generales\n"
        "Artículo 13.- Trece.\n"
        "SECCIÓN QUINTA\n"
        "Servicios que presta la Comisión Intersecretarial para el Control del Proceso y Uso de\n"
        "Plaguicidas, Fertilizantes y Sustancias Tóxicas\n"
        "Sección adicionada DOF 31-12-1999\n"
        "Artículo 14.- Catorce."
    )
    us = parse_texto(texto, start=12)
    assert us[0].cuerpo.strip().endswith("Artículo reformado DOF 06-05-2016")
    assert us[1].titulo == "TÍTULO II. De las Personas Morales Disposiciones Generales"
    assert us[1].cuerpo.strip() == "Artículo 13.- Trece."
    assert us[2].seccion.endswith("Plaguicidas, Fertilizantes y Sustancias Tóxicas")


def test_nota_del_encabezado_envuelta_en_varias_lineas():
    # LFD, Capítulo XII derogado con nota editorial de dos líneas.
    texto = (
        "Artículo 253-A.- Texto.\n"
        "CAPÍTULO XII\n"
        "Hidrocarburos\n"
        "(Se deroga)\n"
        "Capítulo reformado DOF 21-12-2005. Derogado DOF 11-08-2014\n"
        "Nota: Por Decreto DOF 21-12-2005, se reformó íntegro el Capítulo XII. En consecuencia, se\n"
        "suprimieron las referencias a las Secciones Primera y Segunda.\n"
        "Artículo 253-B.- (Se deroga)."
    )
    us = parse_texto("Artículo 253.- Base.\n" + texto, start=253)
    assert [u.clave for u in us] == ["253", "253-a", "253-b"]
    assert us[1].cuerpo.strip() == "Artículo 253-A.- Texto."


def test_numeral_solo_y_marca_derogada_dentro_del_bloque():
    # Ley Aduanera: 'Sección Primera' / 'Importaciones temporales' / 'I' /
    # 'Disposiciones generales'. Reglamento de la LIVA: sección derogada con
    # 'Derogada.' en vez de '(Se deroga)'.
    texto = (
        "Artículo 103.- Texto.\n"
        "Párrafo adicionado DOF 30-12-2002\n"
        "Capítulo III\n"
        "Temporales de importación y de exportación\n"
        "Sección Primera\n"
        "Importaciones temporales\n"
        "I\n"
        "Disposiciones generales\n"
        "ARTICULO 104. Las importaciones temporales…\n"
        "Sección III\n"
        "De los servicios de hotelería y conexos para congresos, convenciones, exposiciones o\n"
        "ferias\n"
        "Derogada.\n"
        "Sección derogada DOF 25-09-2014\n"
        "Artículo 105. Derogado."
    )
    us = parse_texto(texto, start=103)
    assert us[0].cuerpo.strip().endswith("Párrafo adicionado DOF 30-12-2002")
    assert us[1].cuerpo.strip() == "ARTICULO 104. Las importaciones temporales…"


def test_nota_envuelta_con_continuacion_en_mayuscula():
    texto = (
        "Artículo 253.- Texto.\n"
        "CAPÍTULO XII\n"
        "Hidrocarburos\n"
        "Nota: Por Decreto DOF 21-12-2005, se reformó íntegro el Capítulo XII. En consecuencia, se\n"
        "suprimieron las referencias a las Secciones Primera “Del Derecho sobre Hidrocarburos” y Segunda “Del Derecho\n"
        "Adicional sobre Hidrocarburos” del anterior Capítulo XII.\n"
        "Artículo 254.- Otro."
    )
    us = parse_texto(texto, start=253)
    assert us[0].cuerpo.strip() == "Artículo 253.- Texto."


def test_titulo_corrido_en_dos_lineas():
    from extractor.parsers.articulado import _titulo_corrido
    cab = ("REGLAMENTO DE LA LEY FEDERAL PARA LA PREVENCIÓN E IDENTIFICACIÓN DE "
           "OPERACIONES CON RECURSOS\nDE PROCEDENCIA ILÍCITA\n")
    paginas = ["Portada"] + [cab + f"Texto de la página {i}\n" for i in range(6)]
    assert _titulo_corrido(paginas) == (cab.splitlines()[0], "DE PROCEDENCIA ILÍCITA")


# --------------------------------------------------------------------------- #
# Epígrafes, apartados y partes (Código Civil, Ley del Mercado de Valores, CNPP)
# --------------------------------------------------------------------------- #
def test_epigrafe_sin_palabra_clave():
    # Código Civil Federal: rótulos sueltos entre artículos.
    texto = (
        "Artículo 1796.- Los contratos se perfeccionan por el mero consentimiento.\n"
        "Artículo 1797.- Siete.\n"
        "De la Capacidad\n"
        "Artículo 1798.- Son hábiles para contratar todas las personas no exceptuadas por la ley."
    )
    us = parse_texto(texto, start=1796)
    assert [u.clave for u in us] == ["1796", "1797", "1798"]
    assert us[1].cuerpo.strip() == "Artículo 1797.- Siete."
    assert us[2].epigrafe == "De la Capacidad"
    assert "De la Capacidad" in us[2].contexto


def test_epigrafe_con_nota_de_reforma():
    texto = (
        "Artículo 3042.- Texto final.\n"
        "DE LOS EFECTOS DE LAS ANOTACIONES\n"
        "Epígrafe adicionado DOF 18-01-1952. Reformado DOF 03-01-1979\n"
        "Artículo 3043.- Otro."
    )
    us = parse_texto(texto, start=3042)
    assert us[0].cuerpo.strip() == "Artículo 3042.- Texto final."


def test_linea_sin_punto_a_media_frase_no_es_epigrafe():
    # Sin un final de oración antes, una línea corta en mayúscula es la
    # continuación del párrafo, no un rótulo.
    texto = (
        "Artículo 1o.- Las disposiciones de la presente Ley Federal\n"
        "Del Trabajo\n"
        "Artículo 2o.- Dos."
    )
    us = parse_texto(texto)
    assert "Del Trabajo" in us[0].cuerpo


def test_apartado_y_parte():
    texto = (
        "Artículo 28.- Uno.\n"
        "Apartado A\n"
        "Del deber de diligencia\n"
        "Artículo 29.- Dos.\n"
        "TERCERA PARTE\n"
        "De las obligaciones\n"
        "Artículo 30.- Tres.\n"
        "Segunda Parte\n"
        "En Materia Penal\n"
        "Artículo 31.- Cuatro."
    )
    us = parse_texto(texto, start=28)
    assert [u.cuerpo.strip() for u in us] == [
        "Artículo 28.- Uno.", "Artículo 29.- Dos.", "Artículo 30.- Tres.", "Artículo 31.- Cuatro."]
    assert us[1].epigrafe == "Apartado A. Del deber de diligencia"
    assert us[2].titulo == "TERCERA PARTE. De las obligaciones" and us[2].epigrafe == ""


def test_capitulo_bis_y_nombre_envuelto_con_coma():
    texto = (
        "Artículo 33.- Uno.\n"
        "Capítulo IV Bis\n"
        "Del Beneficiario Controlador\n"
        "Artículo 34.- Dos.\n"
        "CAPITULO IV\n"
        "Aplicación de sanciones en caso de concurso, delito continuado, complicidad,\n"
        "reincidencia y error vencible\n"
        "Denominación del Capítulo reformada DOF 13-01-1984, 10-01-1994\n"
        "Artículo 35.- Tres."
    )
    us = parse_texto(texto, start=33)
    assert [u.cuerpo.strip() for u in us] == [
        "Artículo 33.- Uno.", "Artículo 34.- Dos.", "Artículo 35.- Tres."]
    assert us[2].capitulo.endswith("reincidencia y error vencible")


def test_bloque_largo_titulo_y_capitulo_con_nombres_de_tres_lineas():
    # LISR, Título VI: el bloque completo supera las 8 líneas.
    texto = (
        "Artículo 175.- Texto.\n"
        "TÍTULO VI\n"
        "DE LAS ENTIDADES EXTRANJERAS CONTROLADAS SUJETAS A REGÍMENES\n"
        "FISCALES PREFERENTES, DE LAS EMPRESAS MULTINACIONALES Y DE LAS\n"
        "OPERACIONES CELEBRADAS ENTRE PARTES RELACIONADAS\n"
        "Denominación del Título reformada DOF 09-12-2019, 12-11-2021\n"
        "CAPÍTULO I\n"
        "DE LAS ENTIDADES EXTRANJERAS CONTROLADAS SUJETAS A REGÍMENES\n"
        "FISCALES PREFERENTES\n"
        "Denominación del Capítulo reformada DOF 09-12-2019\n"
        "Artículo 176.- Otro."
    )
    us = parse_texto(texto, start=175)
    assert us[0].cuerpo.strip() == "Artículo 175.- Texto."
    assert us[1].titulo.endswith("ENTRE PARTES RELACIONADAS")


def test_numeral_solo_como_subencabezado_sin_palabra_clave():
    texto = (
        "Artículo 107.- Texto.\n"
        "III\n"
        "Para elaboración, transformación o reparación en programas de maquila o de exportación\n"
        "ARTICULO 108. Otro."
    )
    us = parse_texto(texto, start=107)
    assert us[0].cuerpo.strip() == "Artículo 107.- Texto."


def test_numeral_y_nombre_con_nota_y_capitulo_antes_del_articulo():
    texto = (
        "Artículo 2687.- Texto.\n"
        "II\n"
        "De las sociedades\n"
        "Fe de erratas al epígrafe DOF 21-12-1928\n"
        "CAPITULO I\n"
        "Disposiciones generales\n"
        "Fe de erratas a la denominación del Capítulo DOF 21-12-1928\n"
        "Artículo 2688.- Otro."
    )
    us = parse_texto(texto, start=2687)
    assert us[0].cuerpo.strip() == "Artículo 2687.- Texto."
    assert us[1].capitulo.endswith("Disposiciones generales")


def test_articulo_con_letra_separada_por_espacio():
    texto = (
        "Artículo 118.- Texto.\n"
        "Artículo 118 A. Se deroga\n"
        "Artículo 118-B.- (Se deroga).\n"
        "Artículo 119.- Otro."
    )
    us = parse_texto(texto, start=118)
    assert [(u.numero, u.letra) for u in us] == [(118, ""), (118, "A"), (118, "B"), (119, "")]
    assert us[0].cuerpo.strip() == "Artículo 118.- Texto."
