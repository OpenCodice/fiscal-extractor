from extractor.parsers.articulado import es_prosa, parse_texto

LFD = """Artículo 221. Aeropuertos y Servicios Auxiliares efectuará pagos provisionales bimestrales.
El derecho del ejercicio se pagará dentro de los tres meses siguientes al cierre del ejercicio fiscal.
Cuando resulte saldo a favor para Aeropuertos y Servicios Auxiliares, dicho saldo podrá acreditarlo
contra los pagos provisionales del derecho que resulte a su cargo, por los ejercicios subsecuentes al que
se declara, hasta agotarse
Artículo 221-A.- (Se deroga).
Artículo 222. Están obligadas al pago del derecho sobre agua las personas físicas y morales.
"""

CODIGO = """Artículo 1. Primer artículo.
Del Consentimiento
Artículo 2. Segundo artículo.
De la Unidad de Administración de la Suprema Corte de Justicia de la Nación
Artículo 3. Tercer artículo.
"""


def test_un_parrafo_final_sin_punto_se_queda_en_su_articulo():
    unidades = parse_texto(LFD, start=221)
    assert unidades[0].cuerpo.rstrip().endswith("hasta agotarse")
    assert all("saldo a favor" not in u.epigrafe for u in unidades)


def test_un_rotulo_sigue_siendo_epigrafe():
    unidades = {u.numero: u for u in parse_texto(CODIGO)}
    assert unidades[2].epigrafe == "Del Consentimiento"
    assert "Suprema Corte" in unidades[3].epigrafe
    assert "Consentimiento" not in unidades[1].cuerpo


def test_prosa_y_rotulos():
    assert es_prosa("En las permutas y pagos en especie, el impuesto se deberá pagar por cada bien")
    assert not es_prosa("Del Centro Público de Mecanismos Alternativos de Solución de Controversias "
                        "del Poder Judicial de la Federación")
