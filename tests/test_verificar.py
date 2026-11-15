"""Pruebas del verificador (sin LLM real ni PDF)."""
import json

from extractor.verificar import (Cambio, Flujo, Resultado, Veredicto, _es_encabezado,
                                 _muestra, _norm, cobertura, paginas_de, verificar_cambio)

PDF = """Artículo 5o.- Primer párrafo del artículo cinco, con texto propio.
Segundo párrafo, distinto del primero y también único.
(Se deroga).
TÍTULO II
DE LAS PERSONAS MORALES
Artículo 6o.- Otro artículo que no importa aquí.
(Se deroga)."""


def _md(*parrafos):
    return "# Artículo 5o.\n\n" + "\n\n".join(parrafos) + "\n"


def test_cobertura_acepta_extraccion_completa():
    f = Flujo.de(PDF)
    assert cobertura(_md("Primer párrafo del artículo cinco, con texto propio.",
                         "Segundo párrafo, distinto del primero y también único.",
                         "(Se deroga)."), f) == []


def test_cobertura_detecta_parrafo_omitido():
    f = Flujo.de(PDF)
    pr = cobertura(_md("Primer párrafo del artículo cinco, con texto propio.", "(Se deroga)."), f)
    assert [p["tipo"] for p in pr] == ["texto_omitido"]
    assert "Segundo párrafo" in pr[0]["fragmento"]


def test_cobertura_detecta_texto_que_no_esta_en_el_pdf():
    f = Flujo.de(PDF)
    pr = cobertura(_md("Primer párrafo del artículo 12 de 416 cinco, con texto propio.",
                       "Segundo párrafo, distinto del primero y también único."), f)
    assert [p["tipo"] for p in pr] == ["no_literal"]


def test_cobertura_unidad_sin_parrafo_unico_solo_exige_literalidad():
    f = Flujo.de(PDF)
    assert cobertura("# Artículo 6o.\n\n(Se deroga).\n", f) == []
    assert [p["tipo"] for p in cobertura("# Artículo 6o.\n\nNo está.\n", f)] == ["no_literal"]


def test_encabezado_con_nombre_no_es_texto_omitido():
    assert _es_encabezado("TÍTULO II DE LAS PERSONAS MORALES")
    assert _es_encabezado("Sección III De los servicios de hotelería")
    assert _es_encabezado("Capítulo 2.7. De los CFDI")
    assert not _es_encabezado("Los contribuyentes deberán presentar aviso.")
    assert not _es_encabezado("CAPÍTULO II DE LOS INGRESOS Artículo 90. Están obligadas")


def test_cobertura_ignora_encabezado_entre_parrafos():
    f = Flujo.de("Artículo 5o.- Texto único del quinto.\nTÍTULO II\nDE LAS PERSONAS MORALES\n"
                 "Cierre único del quinto.")
    assert cobertura(_md("Texto único del quinto.", "Cierre único del quinto."), f) == []


def test_bloques_solo_reporta_lo_que_cambio():
    c = Cambio("cff", "027", "A\n\nB\n\nC", "A\n\nB2\n\nC\n\nD")
    assert c.bloques() == (["B"], ["B2", "D"])
    assert c.ref == "cff/027"


def test_paginas_se_anclan_a_la_unidad_cuando_el_parrafo_se_repite():
    rep = "Quien incumpla lo dispuesto será sancionado conforme a este Código."
    normas = [_norm(t) for t in (
        f"Artículo 81. Son infracciones relacionadas con declaraciones. {rep}",
        "Artículo 82. Texto sin relación con lo anterior en absoluto.",
        f"Artículo 83. Son infracciones relacionadas con la contabilidad. {rep}",
    )]
    unidad = ["Son infracciones relacionadas con la contabilidad.", rep]
    assert paginas_de([rep], unidad, normas) == [2]


def _cambio():
    return Cambio("cff", "027", "Texto anterior del artículo.", "Texto nuevo del artículo reformado.")


def test_veredicto_del_llm():
    v = verificar_cambio(_cambio(), ["x"], ["x"], lambda _: '{"veredicto": "fiel"}')
    assert v.veredicto == "fiel"
    resp = json.dumps({"veredicto": "artefacto", "explicacion": "pie colado",
                       "problemas": [{"tipo": "ruido_pagina", "fragmento": "8 de 416"}]})
    v = verificar_cambio(_cambio(), ["x"], ["x"], lambda _: resp)
    assert (v.veredicto, v.problemas[0]["tipo"]) == ("artefacto", "ruido_pagina")


def test_respuesta_invalida_es_incierto():
    assert verificar_cambio(_cambio(), ["x"], ["x"], lambda _: "no es json").veredicto == "incierto"
    assert verificar_cambio(_cambio(), ["x"], ["x"],
                            lambda _: '{"veredicto": "quizá"}').veredicto == "incierto"


def test_resultado_ok_exige_todo_en_verde():
    fiel = Veredicto("cff/027", "fiel")
    assert Resultado(1, [], [fiel], []).ok
    assert not Resultado(1, [Veredicto("cff/027", "artefacto")], [], []).ok
    assert not Resultado(1, [], [Veredicto("cff/027", "incierto")], []).ok
    assert not Resultado(1, [], [fiel], ["lisr"]).ok


def test_muestra_reparte_parejo():
    assert _muestra(list(range(5)), 10) == [0, 1, 2, 3, 4]
    assert _muestra(list(range(100)), 4) == [0, 25, 50, 75]


def test_encabezado_pegado_al_final_del_articulo():
    from extractor.verificar import encabezado_pegado
    pegado = "# Artículo 1797.\n\nSiete.\n\nDe la Capacidad\n"
    assert encabezado_pegado(pegado)[0]["fragmento"] == "De la Capacidad"
    # Notas de reforma, fracciones y párrafos con punto final no son encabezados.
    for md in ("# Artículo 1.\n\nUno.\n\n_Artículo reformado DOF 01-01-2020_\n",
               "# Artículo 2.\n\nSon:\n\nI. Las personas físicas\n",
               "# Artículo 3.\n\nUno.\n\nDos.\n",
               "# Artículo 4.\n\n(Se deroga)\n"):
        assert encabezado_pegado(md) == []
