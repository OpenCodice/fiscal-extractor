from extractor.parsers.articulado import ARTICULO_ESTATAL_RE, parse_texto


def test_terdecies_es_ordinal_del_articulo_estatal():
    for ord_ in ("Terdecies", "Quaterdecies"):
        m = ARTICULO_ESTATAL_RE.match(f"Artículo 28 {ord_}. El Centro realizará el cobro.")
        assert m and ord_ in m.group(0)


def test_terdecies_no_queda_absorbido_en_duodecies():
    t = ("Artículo 28. Primero.\n"
         "Artículo 28 duodecies. El Centro será el encargado de emitir.\n"
         "Artículo 28 terdecies. El Centro realizará el cobro de derechos.\n"
         "Artículo 29. Otro texto.\n")
    us = parse_texto(t, start=28, estatal=True)
    assert len(us) == 4
    assert "terdecies" not in us[1].cuerpo.lower()
