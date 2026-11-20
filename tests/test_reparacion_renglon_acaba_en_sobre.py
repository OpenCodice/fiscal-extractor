from extractor.parsers.articulado import _ACABA_EN_PARTICULA_RE, _CIERRA_RE


def test_renglon_que_acaba_en_sobre_no_cierra_parrafo():
    r = "que recaude el Estado del Impuesto sobre"
    assert _ACABA_EN_PARTICULA_RE.search(r) and not _CIERRA_RE.search(r)
    assert not _ACABA_EN_PARTICULA_RE.search("Impuesto sobre la Renta.")
