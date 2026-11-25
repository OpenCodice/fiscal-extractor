from extractor.parsers.articulado import _quitar_encabezados

PAGINA = """CÓDIGO NACIONAL DE PROCEDIMIENTOS CIVILES Y FAMILIARES
CÁMARA DE DIPUTADOS DEL H. CONGRESO DE LA UNIÓN
Secretaría General
Secretaría de Servicios Parlamentarios Última Reforma DOF 16-12-2024
Secretaría General de Gobierno o cualquier otra oficina que lleve a cabo dicha función en
cada Entidad Federativa, quienes serán responsables de su custodia.
179 de 317"""


def test_una_frase_de_la_ley_bajo_el_membrete_no_se_descarta():
    texto = _quitar_encabezados(PAGINA, ())
    assert "Secretaría General de Gobierno o cualquier otra oficina" in texto
    assert "CÁMARA DE DIPUTADOS" not in texto and "Servicios Parlamentarios" not in texto
    assert texto.count("Secretaría General") == 1


LOCG = """LEY ORGÁNICA DEL CONGRESO GENERAL DE LOS ESTADOS UNIDOS MEXICANOS
CÁMARA DE DIPUTADOS DEL H. CONGRESO DE LA UNIÓN
Secretaría General
Secretaría de Servicios Parlamentarios Última Reforma DOF 15-10-2013
Secretaría General, de las Secretarías de Servicios Parlamentarios y de Servicios
Administrativos y Financieros, y demás centros y unidades.
14 de 60"""


def test_la_frase_puede_seguir_con_una_coma():
    texto = _quitar_encabezados(LOCG, ())
    assert "Secretaría General, de las Secretarías de Servicios Parlamentarios y de Servicios" in texto
    assert texto.count("Secretaría General") == 1
