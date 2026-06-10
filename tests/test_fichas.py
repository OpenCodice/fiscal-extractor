"""Pruebas del parser de fichas de trámite (Anexo 2 de la RMF)."""
from extractor.parsers.fichas import parse_texto


def test_ficha_basica_y_clave():
    texto = (
        "Código Fiscal de la Federación\n"
        "1/CFF Solicitud de inscripción en el RFC de personas físicas.\n"
        "Trámite Descripción del trámite o servicio Monto\n"
        "Servicio Solicita la inscripción en el RFC. Gratuito"
    )
    fs = parse_texto(texto)
    assert len(fs) == 1
    f = fs[0]
    assert f.numero == "1/CFF" and f.ley == "CFF"
    assert f.clave == "1-cff"
    assert f.rubro.startswith("Solicitud de inscripción")
    assert "Gratuito" in f.cuerpo


def test_dedup_indice_vs_contenido_gana_cuerpo_largo():
    # El índice recorre los grupos (CFF…ISR) y el contenido real los repite
    # desde el principio: la reapertura de cada grupo reinicia la numeración.
    texto = (
        "Contenido\n"
        "1/CFF Solicitud de inscripción en el RFC de personas físicas.\n"
        "2/CFF Solicitud de inscripción en el RFC de personas morales.\n"
        "1/ISR Declaración informativa por contraprestaciones recibidas.\n"
        "II. Trámites\n"
        "1/CFF Solicitud de inscripción en el RFC de personas físicas.\n"
        "Trámite Descripción del trámite o servicio Monto\n"
        "Servicio Solicita la inscripción con todos sus requisitos. Gratuito\n"
        "2/CFF Solicitud de inscripción en el RFC de personas morales.\n"
        "Trámite Descripción del trámite o servicio Monto\n"
        "Servicio Solicita la inscripción de la persona moral. Gratuito\n"
        "1/ISR Declaración informativa por contraprestaciones recibidas.\n"
        "Trámite Descripción del trámite o servicio Monto\n"
        "Servicio Presenta la declaración informativa. Gratuito"
    )
    fs = parse_texto(texto)
    assert [f.numero for f in fs] == ["1/CFF", "2/CFF", "1/ISR"]
    assert all("Gratuito" in f.cuerpo for f in fs)


def test_rubro_envuelto_en_varias_lineas_se_completa():
    texto = (
        "64/ISR Aviso que presentan los contribuyentes dedicados a las actividades\n"
        "agrícolas que ejercen la opción de enterar el 4 por ciento.\n"
        "Trámite Descripción del trámite o servicio Monto"
    )
    fs = parse_texto(texto)
    assert fs[0].rubro.endswith("el 4 por ciento.")
    assert fs[0].cuerpo.startswith("Trámite")


def test_cita_con_comillas_no_abre_ficha():
    # "…la ficha de trámite\n64/ISR \"Aviso…\"" es una cita, no un encabezado.
    texto = (
        "1/ISR Declaración informativa por contraprestaciones recibidas.\n"
        "Cuerpo de la ficha conforme a la ficha de trámite\n"
        '64/ISR "Aviso que presentan los contribuyentes dedicados…"\n'
        "más cuerpo de la misma ficha."
    )
    fs = parse_texto(texto)
    assert [f.numero for f in fs] == ["1/ISR"]
    assert "64/ISR" in fs[0].cuerpo


def test_grupos_por_decreto_y_numeracion_no_consecutiva():
    # Fichas derogadas dejan huecos válidos (monotonía, no consecutividad).
    texto = (
        "1/DEC-5 Aviso para aplicar el estímulo fiscal en región fronteriza.\n"
        "Cuerpo uno.\n"
        "4/DEC-5 Solicitud de renovación al padrón de beneficiarios.\n"
        "Cuerpo cuatro."
    )
    fs = parse_texto(texto)
    assert [f.numero for f in fs] == ["1/DEC-5", "4/DEC-5"]
    assert fs[0].ley == "DEC-5"
