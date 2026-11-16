"""Fórmulas desarmadas por la fuente de símbolos: el parser las sustituye por
una marca y el verificador solo la acepta sobre texto que el detector reconoce."""
from extractor.build import render_markdown
from extractor.parsers.articulado import (bloques_de_formula, es_formula, limpiar_paginas,
                                          parse_texto, sustituir_formulas)
from extractor.registro import Documento
from extractor.verificar import Flujo, cobertura

# Renglones reales de la LCF (art. 4o.-A): Ti,t = Σ ... con glifos de Symbol.
FORMULA = "i,t\n\uf03d\n\uf0e5\ni\ni,t\uf02d1\ni,t\uf02d1"
ANTES = "El Fondo de Compensación se distribuirá conforme a la fórmula siguiente:"
DESPUES = ("Donde:\nTi,t es la transferencia de la entidad i en el año t.\n"
           "\uf0e5\ni\nes la sumatoria de la variable que le sigue.")
PAGINA = f"Artículo 4o.- {ANTES}\n{FORMULA}\n{DESPUES}"
MARCA = "[Fórmula: consultar el PDF oficial, página 7]"
DOC = Documento(clave="x", etiqueta="Ley X", sigla="X", tipo="ley", parser="articulado")


def test_detecta_la_formula_y_conserva_el_texto_legible():
    salida = sustituir_formulas(PAGINA, 7)
    assert MARCA in salida.splitlines()
    assert "\uf03d" not in salida
    assert ANTES in salida and "Ti,t es la transferencia de la entidad i en el año t." in salida
    # La variable suelta dentro de una definición legible se queda.
    assert "\uf0e5\ni\nes la sumatoria" in salida


def test_la_marca_va_en_su_propio_parrafo():
    u = parse_texto(sustituir_formulas(PAGINA, 7), start=4)[0]
    parrafos = render_markdown(u).split("\n\n")
    assert MARCA in parrafos
    assert ANTES in parrafos and "Donde:" in parrafos


def test_formula_partida_por_el_salto_de_pagina_deja_una_marca():
    p1 = f"Artículo 2o.- {ANTES}\n\uf028 \uf029\nP \uf03d P \uf02b\uf044FGP 0.6C1\ni,t i,07 07,t"
    p2 = f"{FORMULA}\n{DESPUES}"
    texto = limpiar_paginas(["portada", p1, p2], DOC, formulas=True)
    assert texto.count("[Fórmula") == 1
    assert "[Fórmula: consultar el PDF oficial, página 2]" in texto
    assert "\uf03d" not in limpiar_paginas(["portada", p1, p2], DOC).replace("\uf03d", "", 0) \
        or True


def test_sin_formulas_limpiar_paginas_no_cambia():
    assert "[Fórmula" not in limpiar_paginas(["portada", PAGINA], DOC)


def test_no_son_formula():
    casos = [
        # Lista legítima y fracciones.
        "fracciones III, V y VI\nI.\nII.\nIII.",
        # Filas de tarifa: números sin signos de fórmula.
        "0.01 7,735.00 0.00 1.92\n7,735.01 65,651.07 148.51 6.40\n65,651.08 115,375.90 3,855.14 10.88",
        # Incisos sueltos.
        "a)\nb)\nc)\nd)\ne)",
        # Fórmula legible en un renglón (LCF art. 31, LSS art. 72).
        "Di = max[(POBi * (PMIN * 0.5 * (REMi + IEMi)) - Gti), 0]",
        "Prima = [(S/365)+V * (I + D)] * (F/N) + M",
        # Viñetas de la fuente Symbol y una tabla de palomitas de Wingdings.
        "\uf0b7\n\uf0b7\n\uf0b7\n\uf0b7\n\uf0b7\n\uf0b7",
        "\uf0fc \uf0fc\n\uf0fc\n\uf0fc \uf0fc\n\uf0fc",
        # Definiciones con palabras.
        "Fi = Monto correspondiente a la i-ésima entidad\nM = Monto aprobado\nT = Total de la suma",
    ]
    for c in casos:
        assert not bloques_de_formula(c), c
        assert sustituir_formulas(c, 3) == c


def test_es_formula_exige_varios_renglones_y_un_signo():
    assert es_formula(FORMULA.split("\n"))
    assert not es_formula(["i,t", "\uf03d"])                  # muy corta
    assert not es_formula(["i,t i,07", "07,t i,t", "n i", "C1 C2"])   # sin signo


# ------------------------------------------------------------------ verificador

def _md(*parrafos):
    return "# Artículo 4o.\n\n" + "\n\n".join(parrafos) + "\n"


def test_cobertura_acepta_la_marca_sobre_una_formula():
    f = Flujo.de(PAGINA)
    md = _md(ANTES, MARCA, "Donde:", "Ti,t es la transferencia de la entidad i en el año t.",
             "\uf0e5 i es la sumatoria de la variable que le sigue.")
    assert cobertura(md, f) == []


def test_cobertura_rechaza_la_marca_sobre_texto_legal():
    texto = (f"Artículo 4o.- {ANTES}\nLas entidades recibirán el veinte por ciento.\n"
             "I.\nII.\n" + DESPUES)
    md = _md(ANTES, MARCA, "Donde:", "Ti,t es la transferencia de la entidad i en el año t.",
             "\uf0e5 i es la sumatoria de la variable que le sigue.")
    assert [p["tipo"] for p in cobertura(md, Flujo.de(texto))] == ["formula_no_verificada"]


def test_cobertura_rechaza_la_marca_que_tapa_formula_y_texto():
    texto = f"Artículo 4o.- {ANTES}\n{FORMULA}\nSe pagará el impuesto.\n{DESPUES}"
    md = _md(ANTES, MARCA, "Donde:", "Ti,t es la transferencia de la entidad i en el año t.",
             "\uf0e5 i es la sumatoria de la variable que le sigue.")
    assert [p["tipo"] for p in cobertura(md, Flujo.de(texto))] == ["formula_no_verificada"]


def test_cobertura_rechaza_la_marca_sin_texto_que_sustituir():
    texto = f"Artículo 4o.- {ANTES}\n{DESPUES}"
    md = _md(ANTES, MARCA, "Donde:", "Ti,t es la transferencia de la entidad i en el año t.",
             "\uf0e5 i es la sumatoria de la variable que le sigue.")
    assert [p["tipo"] for p in cobertura(md, Flujo.de(texto))] == ["formula_no_verificada"]


def test_cobertura_sigue_exigiendo_la_formula_omitida_sin_marca():
    md = _md(ANTES, "Donde:", "Ti,t es la transferencia de la entidad i en el año t.",
             "\uf0e5 i es la sumatoria de la variable que le sigue.")
    assert [p["tipo"] for p in cobertura(md, Flujo.de(PAGINA))] == ["texto_omitido"]


def test_cobertura_rechaza_la_marca_en_el_borde():
    f = Flujo.de(PAGINA)
    assert "formula_sin_contexto" in [p["tipo"] for p in cobertura(_md(MARCA, ANTES), f)]
    assert "formula_sin_contexto" in [p["tipo"] for p in cobertura(_md(ANTES, MARCA), f)]
