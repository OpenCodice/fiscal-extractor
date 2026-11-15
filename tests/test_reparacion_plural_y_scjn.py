"""Arreglos de la vigilancia federal: 'Artículos 135.-' con s de más y nombres
de capítulo entre corchetes con notas de invalidez de la SCJN sin 'DOF'."""
from extractor.parsers.articulado import parse_texto


def test_articulos_en_plural_con_guion_abre_articulo():
    texto = ("Artículo 1.- Uno.\nArtículos 2.- Dos.\nArtículo 3.- Tres.\n"
             "Artículos 4 y 5 de esta Ley.\n")
    us = parse_texto(texto)
    assert [u.clave for u in us] == ["001", "002", "003"]
    assert "Artículos 4 y 5" in us[2].cuerpo


def test_encabezado_con_nombre_entre_corchetes_y_notas_scjn():
    texto = (
        "Artículo 1.- Uno.\n"
        "Artículo declarado inválido por Resolutivos de la SCJN a Acción de\n"
        "Título II\nDe la Comunicación Social\nCapítulo I\n"
        "[De las Reglas de la Comunicación Social]\n"
        "Denominación reformada DOF 27-12-2022\n"
        "Denominación declarada inválida por Resolutivos de la SCJN el 08-05-2023\n"
        "Denominación que “recupera su vigencia con el texto” por Engrose de\n"
        "Inconstitucionalidad notificado el 31-05-2023 y publicado DOF 24-11-2023\n"
        "Artículo 2.- Dos.\n"
    )
    u1, u2 = parse_texto(texto)
    assert "Capítulo" not in u1.cuerpo and "[De las" not in u1.cuerpo
    assert "Denominación" not in u1.cuerpo
    assert u2.capitulo
