from extractor.parsers.articulado import parse_texto


def test_articulo_transcrito_entre_comillas_abre_unidad():
    t = '''"ARTICULO 1o.- Texto uno".
"ARTICULO 2o.- Texto dos.
Mas texto".
'''
    us = parse_texto(t)
    assert [u.numero for u in us] == [1, 2]
