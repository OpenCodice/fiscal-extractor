"""Pruebas del parser de reglas (RMF), con casos para romperlo."""
from extractor.parsers.reglas import parse_texto, DOF_HEADER_RE


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


def test_encabezado_dof_se_reconoce():
    assert DOF_HEADER_RE.match("DIARIO OFICIAL Domingo 28 de diciembre de 2025")
    assert DOF_HEADER_RE.match("Domingo 28 de diciembre de 2025 DIARIO OFICIAL")
    assert not DOF_HEADER_RE.match("2.3.4. Para los efectos del DIARIO OFICIAL citado")
