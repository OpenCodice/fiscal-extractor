"""Chequeos de forma (extractor/forma.py): cada uno con defectos reales, tomados
de los hallazgos de la revisión completa (verificaciones/altas/), y con texto
fiel parecido que no debe señalar."""
import json

from extractor import forma
from extractor.__main__ import main
from extractor.forma import Articulo, Ley


def _ley(*arts, etiqueta="", **kw) -> Ley:
    """arts: (clave, [párrafos]) o (clave, [párrafos], meta)."""
    return Ley("estado/ley", tuple(Articulo(a[0], tuple(a[1]), a[2] if len(a) > 2 else {})
                                   for a in arts), etiqueta, **kw)


def _claves(hallazgos) -> list[str]:
    return [h.clave for h in hallazgos]


# ------------------------------------------------------------------ pie de página

def test_pie_pagina_formas_conocidas():
    ley = _ley(
        ("003", ["Los servidores públicos serán sujetos de juicio político por la vía procesal que "
                 "Decreto Núm. 473 expedido por la LXXV Legislatura 1 corresponda."]),
        ("031", ["El Estado distribuirá las participaciones.",
                 "Página 19 de 33 Secretaría General Publicada: P.O. Núm. 261; Vigésima Parte, "
                 "31-12-2025 Instituto de Investigaciones Legislativas"]),
        ("046", ["La convocante podrá LXXIII Legislatura 35, 36 adjudicar el contrato."]),
        ("132", ["Los ayuntamientos sesionarán página 45 de 119 en forma ordinaria."]),
        ("133", ["Las sesiones serán públicas."]))
    hs = forma.pie_pagina(ley)
    assert _claves(hs) == ["003", "031", "046", "132"]
    assert "Decreto Núm. 473 expedido por" in hs[0].nota


def test_pie_pagina_titulo_de_la_ley_con_folio():
    etiqueta = "Ley de Seguridad Pública para el Estado de Nuevo León"
    ley = _ley(
        ("189", ["Los integrantes de las instituciones policiales LEY DE SEGURIDAD PÚBLICA PARA EL "
                 "ESTADO DE NUEVO LEÓN 75 deberán conducirse con apego al orden jurídico."]),
        ("190", ["Se aplicará la Ley de Seguridad Pública para el Estado de Nuevo León."]),
        etiqueta=etiqueta)
    assert _claves(forma.pie_pagina(ley)) == ["189"]


def test_pie_pagina_no_marca_texto_de_ley():
    ley = _ley(("010", [
        "La LXXV Legislatura del Congreso del Estado expedirá la convocatoria en 15 días.",
        "El acta constará en la página 3 del libro de registro, de conformidad con el decreto "
        "número 12 expedido por el Ejecutivo.",
        "La Secretaría General del Congreso publicará el acuerdo."]))
    assert forma.pie_pagina(ley) == []


# ------------------------------------------------------------------ rótulo interno

def test_rotulo_interno_articulo_absorbido():
    ley = _ley(
        ("161-bis-1", ["DEROGADO. (P.O. 28 DE JULIO DE 2004.)",
                       "ARTÍCULO161 BIS 2.- SE APLICARÁ LA SANCIÓN DE TRES A OCHO AÑOS DE PRISIÓN."]),
        ("2448-d", ["Para los efectos de este capítulo la renta deberá estipularse en moneda nacional.",
                    "_(REFORMADO, G.O. 28 DE AGOSTO DE 2024)_",
                    "ARTICULO 2428 (SIC) E.- La renta debe pagarse puntualmente."]),
        ("426-quindecies", ["La Unidad tendrá las atribuciones siguientes.",
                            "Artículo 426 Sexiesdecies. El titular será designado por el Consejo."]))
    hs = forma.rotulo_interno(ley)
    assert _claves(hs) == ["161-bis-1", "2448-d", "426-quindecies"]
    assert "no existe archivo 161-bis-2" in hs[0].nota
    assert "no existe archivo 2428-e" in hs[1].nota


def test_rotulo_interno_el_mismo_articulo_dos_veces():
    # El PDF trae dos renglones «Artículo 988.-» y el segundo quedó en el cuerpo.
    ley = _ley(("988", ["El juez nombrará un tutor interino.", "Artículo 988.- Se deroga."]))
    assert _claves(forma.rotulo_interno(ley)) == ["988"]


def test_rotulo_interno_a_media_linea():
    ley = _ley(("014", ["Las notificaciones surtirán efectos al día siguiente. Artículo 15.- Los "
                        "términos empezarán a correr al día siguiente."]),
               ("016", ["Los términos son improrrogables."]))
    assert _claves(forma.rotulo_interno(ley)) == ["014"]


def test_rotulo_interno_no_marca_la_cita_de_otro_articulo():
    # Código Civil Federal, art. 1777: transcribe el art. 54 de otra ley. El 54
    # existe en este código, así que el rótulo no es de un artículo absorbido.
    ley = _ley(
        ("054", ["Las actas del Registro Civil se extenderán en formas especiales."]),
        ("1777", ["El testador puede encargar a un tercero la distribución.",
                  "Artículo 54.- Las enajenaciones de bienes inmuebles cuyo valor convencional sea "
                  "mayor de quinientos pesos se harán en escritura pública."]))
    assert forma.rotulo_interno(ley) == []


def test_rotulo_interno_no_marca_el_primer_parrafo_ni_una_referencia():
    ley = _ley(
        ("005", ["Artículo 5 de la Constitución: nadie puede ser privado del producto de su trabajo.",
                 "Artículo 123 constitucional y sus leyes reglamentarias serán supletorios."]),
        ("006", ["_Artículo 7.- reformado, P.O. 1 DE ENERO DE 2020_", "El texto sigue."]))
    assert forma.rotulo_interno(ley) == []


# ------------------------------------------------------------------ salto en la numeración

def test_salto_numeracion_con_rotulo_sin_numero():
    # Código Civil de Jalisco: el rótulo del 568 perdió su número.
    ley = _ley(
        ("567", ["Niñas, niños y adolescentes deben ser objeto de especial atención.",
                 "Artículo Niñas, niños y adolescentes gozarán de los derechos reconocidos por la "
                 "Constitución."], {"articulo": 567}),
        ("569", ["Ninguna de las disposiciones debe ser interpretada en forma restrictiva."],
         {"articulo": 569}))
    hs = forma.salto_numeracion(ley)
    assert _claves(hs) == ["567"]
    assert "del 567 se pasa al 569" in hs[0].nota and "Artículo Niñas" in hs[0].nota


def test_salto_numeracion_no_marca_el_sic_de_la_fuente():
    # Ley Orgánica de Alcaldías de la CDMX: el PDF pasa del 209 al «211. (SIC)».
    ley = _ley(
        ("209", ["Las Alcaldías deberán promover la participación ciudadana; entre otros."],
         {"articulo": 209}),
        ("211", ["(SIC) Es obligación de las Alcaldías realizar audiencias públicas."],
         {"articulo": 211}))
    assert forma.salto_numeracion(ley) == []


def test_salto_numeracion_no_marca_un_hueco_ni_un_transitorio_citado():
    ley = _ley(
        ("012", ["El recurso se interpondrá por escrito.", "Artículo Primero.- del decreto citado."],
         {"articulo": 12}),
        ("015", ["El 13 y el 14 se derogaron y el PDF los omite."], {"articulo": 15}),
        ("015-bis", ["Mismo número, otro sufijo."], {"articulo": 15}))
    assert forma.salto_numeracion(ley) == []


# ------------------------------------------------------------------ notas

def test_nota_de_encabezado_dentro_de_un_articulo():
    ley = _ley(
        ("131", ["La Junta propondrá al Pleno la integración.",
                 "(CAPITULO ADICIONADO CON LOS ARTÍCULOS Y LAS SECCIONES QUE LO INTEGRAN, P.O. 29 DE "
                 "MAYO DEL 2026)"]),
        ("148-ter", ["Se impondrán de treinta a sesenta años de prisión.",
                     "_Capitulo Adicionado G.O. CDMX 23/08/24_"]),
        ("856", ["La sentencia causará ejecutoria.",
                 "_(ADICIONADO CON LOS ARTÍCULOS QUE LO INTEGRAN, P.O. 27 DE DICIEMBRE DE 2011)_"]))
    hs = forma.nota_de_encabezado(ley)
    assert _claves(hs) == ["131", "148-ter", "856"]
    assert "CAPITULO ADICIONADO" in hs[0].nota


def test_nota_de_encabezado_no_marca_la_nota_del_articulo_ni_su_texto():
    ley = _ley(
        # Guanajuato anota así el epígrafe del propio artículo: publicado y revisado.
        ("152", ["_(REFORMADO SU ACÁPITE, P.O. 28 DE NOVIEMBRE DE 2014)_", "El Consejo sesionará."]),
        ("153", ["_(REFORMADO, P.O. 28 DE NOVIEMBRE DE 2014)_",
                 "El Capítulo Tercero de este Título fue adicionado para regular el procedimiento, "
                 "según el decreto publicado en el Periódico Oficial."]))
    assert forma.nota_de_encabezado(ley) == []


def _con_notas_previas(*extra):
    """Una ley cuyas notas de artículo van antes de él (ocho lo muestran)."""
    base = [(f"{n:03d}", ["_(REFORMADO, P.O. 10 DE FEBRERO DE 2006)_", "El texto del artículo."])
            for n in range(1, 9)]
    return _ley(*base, *extra)


def test_nota_previa_al_final_es_de_lo_que_sigue():
    # Código Penal de Nuevo León, art. 387: la nota del 387 Bis cerró el 387
    # (el PDF la escribe sin paréntesis de cierre).
    ley = _con_notas_previas(
        ("387", ["Se aplicará prisión de dos a seis años.", "_(ADICIONADO, P.O. 28 DE JULIO DE 2004_"]),
        ("043", ["La sanción será de multa.", "REFORMADO PRIMER PÁRRAFO, P.O. 10 DE FEBRERO DE 2006)"]))
    assert _claves(forma.nota_previa_al_final(ley)) == ["387", "043"]


def test_nota_previa_al_final_no_marca_derogaciones_ni_fuentes_con_la_nota_despues():
    derogada = _con_notas_previas(
        ("322", ["El recurso procede contra la sentencia.",
                 "_(DEROGADO ÚLTIMO PÁRRAFO, P.O. 29 DE ABRIL DE 2020)_"]))
    assert forma.nota_previa_al_final(derogada) == []
    # La CDMX escribe «Artículo reformado G.O. CDMX…» después del artículo.
    despues = _ley(*[(f"{n:03d}", ["El texto del artículo.", "_Artículo reformado G.O. CDMX 30/11/2022_"])
                     for n in range(1, 12)])
    assert forma.nota_previa_al_final(despues) == []
    # Y también cuando la misma ley trae notas viejas antes y nuevas después.
    mezcla = _con_notas_previas(
        ("071", ["El Consejo sesionará cada mes.", "_Párrafo reformado G.O. CDMX 23/12/24_"]))
    assert forma.nota_previa_al_final(mezcla) == []


def test_nota_en_cuerpo_pegada_donde_la_fuente_las_separa():
    arts = (
        ("008", ["VII. Realizar estudios e investigaciones;", "_(Ref. P.O. No. 19, 27-II-26)_",
                 "VIII. Establecer medidas de protección, fomentando un entorno libre de violencia, "
                 "discriminación y desigualdad; y (Adición, P.O. No. 19, 27-II-26)"]),
        ("137", ["V. Los demás que señalen las leyes fiscales. (Re. P.O. No. 101, 23-XII-25)"]))
    hs = forma.nota_en_cuerpo(_ley(*arts, marca_notas=True, separa_notas=True))
    assert _claves(hs) == ["008", "137"]
    assert "(Adición, P.O. No. 19, 27-II-26)" in hs[0].nota
    # Sin `notas_en_linea` en su definición, la nota a renglón seguido es como
    # la escribe el PDF: texto fiel.
    assert forma.nota_en_cuerpo(_ley(*arts, marca_notas=True)) == []


def test_nota_en_cuerpo_sola_sin_marcar():
    # Ley del Notariado de Nuevo León, art. 156: el PDF omite el paréntesis
    # inicial y la nota quedó como texto.
    arts = (("156", ["VIII. Autorizar definitivamente la escritura;",
                     "ADICIONADA, P.O. 17 DE ENERO DE 2025)",
                     "IX. Expedir los testimonios."]),)
    assert _claves(forma.nota_en_cuerpo(_ley(*arts, marca_notas=True))) == ["156"]
    assert forma.nota_en_cuerpo(_ley(*arts)) == []


def test_nota_en_cuerpo_no_marca_derogaciones_ni_prosa_entre_parentesis():
    ley = _ley(
        ("101", ["II. (DEROGADA, P.O. 26 DE MAYO DE 2017);", "(DEROGADO, P.O. 5 DE JULIO DE 1991)"]),
        # Código Electoral de Jalisco: la anotación va a renglón seguido en el PDF.
        ("229", ["Los partidos políticos deberán informarlo antes del inicio de las precampañas. "
                 "(Este párrafo fue reformado por Decreto 29185/LXIII/23 publicado en el Periódico "
                 "Oficial El Estado de Jalisco el día veinte de Mayo del dos mil veintitrés, el cual "
                 "fue declarado invalido)"]),
        marca_notas=True, separa_notas=True)
    assert forma.nota_en_cuerpo(ley) == []


def test_nota_con_texto_de_la_ley_dentro():
    # Ley Electoral de Nuevo León, art. 79.
    ley = _ley(("079", [
        "VIII. La determinación del responsable financiero.",
        "_((REFORMADO, P.O. 04 DE MARZO DE 2022) Para el caso de la elección de Diputaciones y "
        "Ayuntamientos, contendrá además el señalamiento del partido político._"]))
    hs = forma.nota_con_texto(ley)
    assert _claves(hs) == ["079"] and "Para el caso" in hs[0].nota


def test_nota_con_texto_no_marca_notas_enteras():
    ley = _ley(("028", [
        "_(DEROGADO, P.O. 29 DE DICIEMBRE DE 2015) (F. DE E., P.O. 29 DE ENERO DE 2016)_",
        "_(REFORMADO PRIMER PÁRRAFO, P.O. 10 DE FEBRERO DE 2006)_",
        "_(REFORMADA (SIC), P.O. 10 DE FEBRERO DE 2006)_",
        "_N. DE E. EN RELACIÓN CON LA ENTRADA EN VIGOR, VÉASE TRANSITORIO ÚNICO._",
        "(En este párrafo sin cursiva) sigue el texto de la ley."]))
    assert forma.nota_con_texto(ley) == []


def test_nota_sin_cerrar():
    ley = _ley(("043-bis", ["_(ADICIONADO, P.O. 13 DE ENERO DE 2023_", "El texto.",
                            "_(REFORMADO, P.O. 13 DE ENERO DE 2023)_"]))
    assert _claves(forma.nota_sin_cerrar(ley)) == ["043-bis"]


# ------------------------------------------------------------------ cortes de párrafo

def test_corte_a_media_oracion():
    ley = _ley(
        # Ley de Coordinación Fiscal de Guanajuato, art. 24.
        ("024", ["Es el coeficiente del Impuesto Especial sobre Producción y Servicios",
                 "por la enajenación de cerveza, bebidas refrescantes y alcohol."]),
        # Código Civil Federal, art. 474.
        ("474", ["Se observará, en su caso, lo dispuesto en el artículo", "457."]),
        ("475", ["El tutor responderá de los daños que cause por"]))
    hs = forma.corte_a_media_oracion(ley)
    assert _claves(hs) == ["024", "474", "475"]
    assert "Producción y Servicios» / «por la enajenación" in hs[0].nota


def test_corte_a_media_oracion_no_marca_enumeraciones_ni_cierres_sin_punto():
    ley = _ley(("002", [
        "Para los efectos de esta ley se entiende por",
        "I. Autoridad: la dependencia competente;",
        "II. Contribuyente: la persona obligada al pago, y",
        "Las autoridades aplicarán esta ley conforme a lo siguiente:",
        "a) En el ámbito estatal, la Secretaría",
        "El párrafo anterior cierra sin punto y este empieza con mayúscula",
        "[Fórmula: consultar el PDF oficial, página 12]",
        "donde cada variable se define en el reglamento."]))
    assert forma.corte_a_media_oracion(ley) == []


def test_epigrafe_siguiente_colado():
    con = {"epigrafe": "Objeto"}
    # Código Territorial de Guanajuato, art. 105.
    ley = _ley(
        ("104", ["El Ejecutivo expedirá las declaratorias."], con),
        ("105", ["Las áreas se administrarán conforme a su programa de manejo.",
                 "Concesiones, permisos o licencias para la realización de obras o actividades en "
                 "las áreas naturales protegidas"], con),
        ("106", ["La Secretaría podrá otorgar concesiones."], {"epigrafe": ""}),
        ("107", ["Las concesiones son intransferibles."], con))
    hs = forma.epigrafe_siguiente_colado(ley)
    assert _claves(hs) == ["105"] and "106" in hs[0].nota


def test_epigrafe_siguiente_colado_no_marca_sin_la_convencion_ni_tras_un_punto():
    cuerpo_abierto = ["El texto del artículo termina sin punto"]
    sin_epigrafes = _ley(("001", cuerpo_abierto), ("002", ["Sigue."]), ("003", ["Sigue."]))
    assert forma.epigrafe_siguiente_colado(sin_epigrafes) == []
    con = {"epigrafe": "Objeto"}
    ley = _ley(("001", ["El artículo cierra con punto."], con),
               ("002", ["Este no tiene epígrafe."], {"epigrafe": ""}),
               ("003", cuerpo_abierto, con),
               ("004", ["Se deroga."], {"epigrafe": "", "derogado": True}),
               ("005", ["Sigue."], con))
    assert forma.epigrafe_siguiente_colado(ley) == []


def test_epigrafe_final_con_punto():
    ley = _ley(
        # Código Ambiental de Querétaro, art. 165; Código Electoral de Jalisco, art. 445-N.
        ("165", ["La Secretaría promoverá la participación de los sectores social y privado.",
                 "De la financiación y del fomento."]),
        ("445-n", ["Derogado.", "De los Recursos en Materia de Participación Social."]),
        # Código Penal de la CDMX, art. 182: la última línea del encabezado del Título.
        ("182", ["Se aumentará la pena en una mitad.", "CAPACIDAD DE RESISTIR LA CONDUCTA."]))
    assert _claves(forma.epigrafe_final_con_punto(ley)) == ["165", "445-n", "182"]


def test_epigrafe_final_con_punto_no_marca_oraciones():
    ley = _ley(("010", ["El recurso se presentará por escrito.",
                        "De no hacerlo, se tendrá por no interpuesto."]),
               ("011", ["Los titulares rendirán un informe.",
                        "Del cumplimiento de esta obligación serán responsables los titulares."]),
               ("012", ["De las resoluciones conocerá el Pleno."]))
    assert forma.epigrafe_final_con_punto(ley) == []
    # En una ley escrita en mayúsculas, un cierre en mayúsculas es texto.
    mayusculas = _ley(*[(f"{n:03d}", ["EL TEXTO DEL ARTÍCULO VA EN MAYÚSCULAS.",
                                      "LA SANCIÓN SERÁ DE MULTA."]) for n in range(1, 5)])
    assert forma.epigrafe_final_con_punto(mayusculas) == []


def test_derogado_pegado():
    # Código de Instituciones y Procedimientos Electorales de la CDMX, art. 111.
    ley = _ley(
        ("111", ["En cada uno de los distritos electorales el Instituto Electoral contará con un "
                 "órgano desconcentrado permanente denominado Dirección Distrital. Derogado"]),
        ("112", ["II. Derogado.", "Se deroga."]))
    hs = forma.derogado_pegado(ley)
    assert _claves(hs) == ["111"] and "Dirección Distrital." in hs[0].nota


def test_fraccion_huerfana():
    ley = _ley(
        # Ley de Instituciones y Procedimientos Electorales de Guanajuato, art. 101: el
        # PDF dice «IV. (DEROGADA, P.O. 26 DE MAYO DE 2017):» y los dos puntos quedaron solos.
        ("101", ["III. (DEROGADA, P.O. 26 DE MAYO DE 2017);", "IV.",
                 "_(DEROGADA, P.O. 26 DE MAYO DE 2017)_", ":",
                 "V. Proveer lo necesario para la impresión;"]),
        # Código Penal de la CDMX, art. 179: la «o» que cierra la fracción II.
        ("179", ["II. Exista una relación de superioridad entre el sujeto activo y la víctima;", "o",
                 "III. Se condicione la obtención de beneficios."]),
        ("152", ["Las banquetas tendrán por lo menos", "1.", "8 metros de ancho."]))
    hs = forma.fraccion_huerfana(ley)
    assert [(h.clave, h.nota.split("«")[1].split("»")[0]) for h in hs] == [
        ("101", ":"), ("179", "o"), ("152", "1.")]


def test_fraccion_huerfana_no_marca_la_fraccion_derogada_con_su_nota():
    # «IV.» seguido de su nota es una fracción cuyo único texto es la nota de
    # derogación: así están publicadas y revisadas varias leyes de Guanajuato.
    ley = _ley(("023-bis", ["II.- Por la adopción de un menor; y", "III.-",
                            "_(DEROGADA, P.O. 9 DE MAYO DE 2014)_"]),
               ("028", ["r)", "_(DEROGADO, P.O. 29 DE DICIEMBRE DE 2015)_"]),
               ("029", ["I. La primera;", "II. La segunda.", "…", "Derogado.", "_(Nota)_"]))
    assert forma.fraccion_huerfana(ley) == []


# ------------------------------------------------------------------ el conjunto

def test_el_filtro_solo_lleva_chequeos_sin_falsos_positivos_conocidos():
    assert set(forma.FILTRO) <= set(forma.CHEQUEOS)
    # Medidos sobre lo publicado, estos dos señalan texto fiel al PDF: un
    # rótulo que la fuente escribió sin número (Código Civil de Jalisco, 567) y
    # notas que el PDF no cierra (Nuevo León). Quedan solo en el informe.
    assert set(forma.CHEQUEOS) - set(forma.FILTRO) == {"salto_numeracion", "nota_sin_cerrar"}


def test_revisar_ordena_por_articulo_y_respeta_los_chequeos_pedidos():
    ley = _ley(("001", ["El texto.", "IV."]),
               ("002", ["Los ayuntamientos sesionarán página 45 de 119 en forma ordinaria.", ":"]))
    todos = forma.revisar(ley)
    assert [(h.clave, h.chequeo) for h in todos] == [
        ("001", "fraccion_huerfana"), ("002", "pie_pagina"), ("002", "fraccion_huerfana")]
    assert todos[1].a_dict() == {"clave": "002", "chequeo": "pie_pagina", "nota": todos[1].nota}
    assert [h.chequeo for h in forma.revisar(ley, ("pie_pagina",))] == ["pie_pagina"]


def _escribir(repo, clave, arts, etiqueta="Ley de Prueba del Estado"):
    estatal = "/" in clave
    unidades = repo / (f"{clave}/articulos" if estatal else clave)
    metadata = repo / (f"{clave}/metadata" if estatal else f"metadata/{clave}")
    unidades.mkdir(parents=True)
    metadata.mkdir(parents=True)
    for c, ps in arts:
        (unidades / f"{c}.md").write_text(f"# Artículo {c}.\n\n" + "\n\n".join(ps) + "\n",
                                          encoding="utf-8")
    (metadata / "articulos.json").write_text(json.dumps({
        "etiqueta": etiqueta,
        "articulos": [{"clave": c, "articulo": int(c[:3]), "epigrafe": ""} for c, _ in arts]}),
        encoding="utf-8")


def test_cargar_e_informe_de_un_repo_estatal_y_de_uno_plano(tmp_path):
    _escribir(tmp_path, "jalisco/ley-de-prueba", [("010", ["Primer párrafo.", "_(Nota)_"]),
                                                    ("002", ["El texto.", "IV."])])
    _escribir(tmp_path, "jalisco/constitucion", [("001", ["IV."])])
    _escribir(tmp_path, "lgs", [("001", ["Texto limpio."])])
    ley = forma.cargar(tmp_path, "jalisco/ley-de-prueba")
    # El orden es el del índice, no el alfabético.
    assert [a.clave for a in ley.articulos] == ["010", "002"]
    assert ley.articulos[0].parrafos == ("Primer párrafo.", "_(Nota)_")
    assert ley.articulos[0].cuerpo == ("Primer párrafo.",)
    assert ley.etiqueta == "Ley de Prueba del Estado" and ley.articulos[1].numero == 2
    # Las constituciones son de constitucion-extractor: el informe no las mira.
    assert forma.documentos_de_repo(tmp_path) == ["jalisco/ley-de-prueba", "lgs"]
    assert {c: _claves(hs) for c, hs in forma.informe(tmp_path).items()} == {
        "jalisco/ley-de-prueba": ["002"]}


def test_comando_forma_es_un_informe_y_siempre_sale_cero(tmp_path, capsys):
    _escribir(tmp_path, "jalisco/ley-de-prueba", [("002", ["El texto.", "IV."])])
    salida = tmp_path / "forma.json"
    assert main(["forma", "--out", str(tmp_path), "--json", str(salida)]) == 0
    texto = capsys.readouterr().out
    assert "002 [fraccion_huerfana]" in texto and "* fraccion_huerfana" in texto
    assert "  salto_numeracion" in texto
    assert json.loads(salida.read_text(encoding="utf-8")) == {"jalisco/ley-de-prueba": [
        {"clave": "002", "chequeo": "fraccion_huerfana",
         "nota": "párrafo suelto «IV.», sin el texto de su fracción"}]}
