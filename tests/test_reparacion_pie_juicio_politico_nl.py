from extractor.estatales import nuevo_leon


def test_juicio_politico_quita_pie_decreto_473():
    docs = {d.clave: d for d in nuevo_leon.LEYES}
    d = docs["nuevo-leon/ley-de-juicio-politico"]
    pie = set(d.titulos_encabezado)
    assert "Decreto Núm. 473 expedido por la LXXV Legislatura 1" in pie
    assert "Decreto Núm. 473 expedido por la LXXV Legislatura 6" in pie
