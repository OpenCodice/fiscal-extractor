"""Pruebas del parser de apartados (Anexos 5 y 8 de la RMF)."""
from extractor.parsers.apartados import parse_texto


def test_apartados_basicos():
    texto = (
        "A. Tarifa aplicable a pagos provisionales\n"
        "Cuerpo del apartado A con su tarifa.\n"
        "B. Tarifas aplicables a retenciones\n"
        "Cuerpo del apartado B."
    )
    aps = parse_texto(texto)
    assert [a.letra for a in aps] == ["A", "B"]
    assert aps[0].clave == "a"
    assert aps[0].etiqueta == "Apartado A. Tarifa aplicable a pagos provisionales"


def test_fraccion_romana_no_abre_apartado():
    # 'I.', 'V.' y 'X.' son fracciones dentro del cuerpo, no apartados.
    texto = (
        "A. Cantidades actualizadas establecidas en el CFF.\n"
        "I. De $5,070.00 a $15,200.00, a las comprendidas en las fracciones I y II.\n"
        "V. De $5,030.00 a $15,160.00, a la comprendida en la fracción VII.\n"
        "X. De $14,100.00 a $26,430.00, para la establecida en la fracción X.\n"
        "B. Compilación de cantidades establecidas en el CFF.\n"
        "Cuerpo del apartado B."
    )
    aps = parse_texto(texto)
    assert [a.letra for a in aps] == ["A", "B"]
    assert "fracción VII" in aps[0].cuerpo


def test_dedup_contenido_vs_cuerpo():
    texto = (
        "Contenido\n"
        "A. Cantidades actualizadas establecidas en el CFF.\n"
        "B. Compilación de cantidades establecidas en el CFF.\n"
        "A. Cantidades actualizadas establecidas en el CFF.\n"
        "Artículo 82. De $2,050.00 a $25,360.00, tratándose de declaraciones.\n"
        "B. Compilación de cantidades establecidas en el CFF.\n"
        "Artículo 20. Cuerpo largo del apartado B con sus cantidades."
    )
    aps = parse_texto(texto)
    assert [a.letra for a in aps] == ["A", "B"]
    assert all("Artículo" in a.cuerpo for a in aps)
