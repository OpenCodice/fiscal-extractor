"""Pruebas del parser de reglas (RMF), con casos para romperlo."""
from extractor.parsers.reglas import parse_texto, reglas_y_anomalias, DOF_HEADER_RE


def numeros(texto):
    return [r.numero for r in parse_texto(texto)]


def test_regla_simple_con_titulo_y_contexto():
    texto = (
        "Título 2. Código Fiscal de la Federación\n"
        "Capítulo 2.3. Devoluciones y compensaciones\n"
        "Devolución de saldos a favor del IVA\n"
        "2.3.4. Para los efectos del artículo 22 del CFF, los contribuyentes."
    )
    rs = parse_texto(texto)
    assert len(rs) == 1
    r = rs[0]
    assert r.numero == "2.3.4"
    assert r.titulo_regla == "Devolución de saldos a favor del IVA"
    assert r.titulo == "Título 2. Código Fiscal de la Federación"
    assert r.capitulo == "Capítulo 2.3. Devoluciones y compensaciones"
    assert r.cuerpo.startswith("Para los efectos")


def test_cita_a_regla_no_inicia_unidad():
    # Discriminador real-vs-cita: la cita arranca en minúscula y se descarta.
    texto = (
        "Algún título\n"
        "2.3.4. Para los efectos del artículo 22, conforme a la regla\n"
        "2.3.8. y la ficha de trámite 1/LISH, se procederá."
    )
    # La segunda línea ('2.3.8. y la ficha…') es una cita, no una regla nueva.
    assert numeros(texto) == ["2.3.4"]


def test_numeracion_profunda():
    texto = (
        "T\n2.7.7.1.1 base\n"  # ruido
        "Regla profunda\n"
        "2.7.7.1.1. Para los efectos de esta RMF, se establece el supuesto."
    )
    rs = parse_texto(texto)
    assert any(r.numero == "2.7.7.1.1" for r in rs)
    r = next(r for r in rs if r.numero == "2.7.7.1.1")
    assert r.nivel == 5


def test_seccion_resetea_en_nuevo_capitulo():
    texto = (
        "Capítulo 2.6. Controles\n"
        "Sección 2.6.1. Disposiciones generales\n"
        "Título de regla\n"
        "2.6.1.1. Las personas obligadas cumplirán lo siguiente.\n"
        "Capítulo 2.7. CFDI\n"
        "Otro título\n"
        "2.7.1.1. Los contribuyentes podrán expedir comprobantes."
    )
    rs = parse_texto(texto)
    r1 = next(r for r in rs if r.numero == "2.6.1.1")
    r2 = next(r for r in rs if r.numero == "2.7.1.1")
    assert r1.seccion == "Sección 2.6.1. Disposiciones generales"
    assert r2.capitulo == "Capítulo 2.7. CFDI"
    assert r2.seccion == "", "la sección debe resetearse al cambiar de capítulo"


def test_cita_otra_rama_capitalizada_se_descarta():
    # La señal robusta: aunque la cita venga CAPITALIZADA, si su número no cae
    # bajo el contexto estructural vigente, no es regla (la mayúscula sola la
    # habría aceptado por error).
    texto = (
        "Sección 2.7.1. Disposiciones generales\n"
        "Comprobantes con el público en general\n"
        "2.7.1.1. Para los efectos de esta RMF, conforme a la regla\n"
        "3.1.5. El contribuyente deberá observar lo dispuesto en la materia."
    )
    rs, anom = reglas_y_anomalias(texto)
    assert [r.numero for r in rs] == ["2.7.1.1"]
    assert any(a["numero"] == "3.1.5" and a["motivo"] == "cita_otra_rama_capitalizada"
               for a in anom), "la cita de otra rama debe registrarse como anomalía"


def test_cita_misma_rama_minuscula_se_descarta_y_registra():
    texto = (
        "Sección 2.7.6. Proveedores\n"
        "Título de regla\n"
        "2.7.6.3. Para los efectos de esta RMF, conforme a la regla\n"
        "2.7.6.4. y, en su caso, la regla siguiente."
    )
    rs, anom = reglas_y_anomalias(texto)
    assert [r.numero for r in rs] == ["2.7.6.3"]
    assert any(a["numero"] == "2.7.6.4" and a["motivo"] == "consistente_minuscula"
               for a in anom)


def test_encabezado_dof_se_reconoce():
    assert DOF_HEADER_RE.match("DIARIO OFICIAL Domingo 28 de diciembre de 2025")
    assert DOF_HEADER_RE.match("Domingo 28 de diciembre de 2025 DIARIO OFICIAL")
    assert not DOF_HEADER_RE.match("2.3.4. Para los efectos del DIARIO OFICIAL citado")


def test_capitulo_sin_punto_fija_contexto():
    # La RGCE trae encabezados sin punto tras el número: "Capítulo 1.12 Agencia
    # Aduanal". Sin tolerarlo, las reglas 1.12.x se rechazan por contexto.
    texto = (
        "Capítulo 1.12 Agencia Aduanal\n"
        "Título de regla\n"
        "1.12.1. Para los efectos del artículo 167-D de la Ley, la patente."
    )
    rs, _ = reglas_y_anomalias(texto)
    assert [r.numero for r in rs] == ["1.12.1"]
    assert rs[0].capitulo == "Capítulo 1.12. Agencia Aduanal"


def test_referencia_a_capitulo_no_envenena_contexto():
    # Pie de regla de la RGCE: "Capítulo 3.6., Anexos 7, 8, 9 y 10" es una
    # referencia, no un encabezado; no debe cambiar el contexto estructural.
    texto = (
        "Capítulo 1.3. Padrones de Importadores y Exportadores\n"
        "Título de regla\n"
        "1.3.1. Para los efectos del artículo 59 de la Ley, lo siguiente.\n"
        "Capítulo 3.6., Anexos 7, 8, 9 y 10\n"
        "Otra regla\n"
        "1.3.2. Para los efectos del artículo 59 de la Ley, lo conducente."
    )
    rs, anom = reglas_y_anomalias(texto)
    assert [r.numero for r in rs] == ["1.3.1", "1.3.2"]
    assert all(r.capitulo.startswith("Capítulo 1.3.") for r in rs)
