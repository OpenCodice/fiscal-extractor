from extractor.parsers.articulado import parse_texto


def _con_epigrafes(n=22):
    return "".join(f"Epígrafe número {k}\nArtículo {k}. Texto {k}.\n" for k in range(1, n))


def test_epigrafe_tras_texto_sin_punto_final_no_se_pega_al_articulo_anterior():
    t = (_con_epigrafes() +
         "Artículo 22. Los bienes son inalienables y sólo podrán enajenarse con autorización del Ayuntamiento\n"
         "Clasificación de los bienes del dominio público\n"
         "Artículo 23. Los bienes se clasifican en:\n")
    us = parse_texto(t, estatal=True, epigrafe_max=80)
    assert "Clasificación" not in us[-2].cuerpo
    assert us[-1].epigrafe == "Clasificación de los bienes del dominio público"


def test_undiecies_abre_articulo_y_su_seccion_no_queda_en_el_anterior():
    t = "".join(f"Artículo {k}. Texto {k}.\n" for k in range(1, 7))
    t += ("Artículo 6 Decies. Uno.\nSección Segunda\nComité de Evaluación\n"
          "Artículo 6 Undiecies. El Congreso contará con un Comité.\n"
          "Artículo 6 Duodecies. Tres.\n")
    us = parse_texto(t, estatal=True, epigrafe_max=80)
    assert [u.ordinal.lower() for u in us][6:] == ["decies", "undiecies", "duodecies"]
    assert "Comité de Evaluación" not in us[6].cuerpo
    assert us[7].seccion.endswith("Comité de Evaluación")
