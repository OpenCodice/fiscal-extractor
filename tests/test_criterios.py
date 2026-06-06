"""Pruebas del parser de criterios (Anexos 7 y 3 de la RMF)."""
from extractor.parsers.criterios import parse_texto


def test_criterio_basico_ley_tipo_clave():
    texto = (
        "I. Criterios del CFF\n"
        "A. Vigentes\n"
        "1/CFF/N Crédito fiscal. Es firme.\n"
        "El artículo 65 del CFF establece el supuesto correspondiente al caso."
    )
    cs = parse_texto(texto)
    assert len(cs) == 1
    c = cs[0]
    assert c.numero == "1/CFF/N"
    assert c.ley == "CFF" and c.tipo == "N"
    assert c.clave == "1-cff-n"               # apto para nombre de archivo
    assert c.estado == "vigente"
    assert c.rubro.startswith("Crédito fiscal")


def test_dedup_toc_vs_contenido_gana_cuerpo_largo():
    # El mismo identificador aparece en el índice (sin cuerpo) y en el contenido
    # real (con cuerpo). Debe quedar el del cuerpo largo.
    texto = (
        "Contenido\n"
        "I. Criterios del CFF\n"
        "1/CFF/N Crédito fiscal. Es firme.\n"      # índice: sin cuerpo
        "II. Criterios de la Ley del ISR\n"
        "1/CFF/N Crédito fiscal. Es firme.\n"      # contenido: con cuerpo
        "El artículo 65 del CFF prevé el supuesto y desarrolla la regla aplicable."
    )
    cs = parse_texto(texto)
    assert len(cs) == 1
    assert "artículo 65" in cs[0].cuerpo


def test_estado_derogado_desde_encabezado():
    texto = (
        "I. Criterios del CFF\n"
        "B. Derogados\n"
        "5/ISR/NV Práctica indebida histórica.\n"
        "Este criterio quedó sin efectos por la reforma correspondiente."
    )
    cs = parse_texto(texto)
    assert cs[0].estado == "derogado"
    assert cs[0].tipo == "NV"


def test_no_vinculativo_pi():
    texto = (
        "I. Criterios del CFF\n"
        "1/CFF/PI Entrega del CFDI. No se cumple con remitir a una página.\n"
        "El artículo 29 del CFF obliga a expedir y entregar el comprobante."
    )
    cs = parse_texto(texto)
    assert cs[0].numero == "1/CFF/PI" and cs[0].tipo == "PI"
    assert cs[0].clave == "1-cff-pi"
