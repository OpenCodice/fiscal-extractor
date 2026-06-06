"""Pruebas de la generación de pasajes (párrafos citables) y normalización locate."""
from extractor.locate import _norm_text
from extractor.modelo import Criterio, Regla, Unidad
from extractor.pasajes import pasajes_de
from extractor.registro import Documento

CFF = Documento("cff", "Código Fiscal de la Federación", "CFF", "ley", "articulado")
RMF = Documento("rmf-2026", "RMF 2026", "RMF 2026", "rmf", "reglas")
CRIT = Documento("criterios-normativos", "Criterios", "Criterio Normativo",
                 "criterios", "criterios")


def test_articulo_un_pasaje_por_parrafo_sin_notas():
    u = Unidad(numero=27, cuerpo=(
        "Artículo 27.- Primer párrafo del artículo.\n\n"
        "Segundo párrafo del artículo.\n\n"
        "Párrafo reformado DOF 01-01-2020"))     # nota: no es pasaje
    ps = pasajes_de(u, CFF)
    assert [p["id"] for p in ps] == ["cff/027.p1", "cff/027.p2"]
    assert ps[0]["cita"] == "Artículo 27 CFF, párrafo 1"
    assert ps[0]["texto"].startswith("Primer párrafo")
    assert all("DOF" not in p["texto"] for p in ps)        # la nota quedó fuera


def test_cita_de_regla():
    r = Regla(numero="2.7.1.21", titulo_regla="Comprobantes",
              cuerpo="Para los efectos de esta RMF, los contribuyentes podrán.")
    ps = pasajes_de(r, RMF)
    assert ps[0]["id"] == "rmf-2026/2.7.1.21.p1"
    assert ps[0]["cita"] == "Regla 2.7.1.21 RMF 2026, párrafo 1"


def test_cita_de_criterio():
    c = Criterio(numero="10/IVA/N", ley="IVA", tipo="N", rubro="Alimentos",
                 cuerpo="El artículo 2o.-A de la Ley del IVA establece la tasa del 0%.")
    ps = pasajes_de(c, CRIT)
    assert ps[0]["id"] == "criterios-normativos/10-iva-n.p1"
    assert ps[0]["cita"] == "Criterio 10/IVA/N, párrafo 1"


def test_pasaje_lleva_provenance():
    u = Unidad(numero=1, cuerpo="Artículo 1o.- Texto del primer artículo de prueba.")
    p = pasajes_de(u, CFF)[0]
    assert p["documento"] == "cff"
    assert p["archivo_texto"] == "cff/001.md"
    assert p["clave_unidad"] == "001"


def test_norm_text_quita_acentos_y_puntuacion():
    assert _norm_text("Artículo 2o.-A, fracción I") == "articulo2oafraccioni"
