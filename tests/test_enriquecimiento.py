"""Pruebas del enriquecimiento con un doble determinista del LLM (sin API)."""
import json

import pytest

from extractor import enrich
from extractor.modelo import Unidad
from extractor.registro import Documento

CFF = Documento("cff", "Código Fiscal de la Federación", "CFF", "ley", "articulado")

RESPUESTA = json.dumps({
    "denominacion_comun": "Residencia fiscal",
    "temas": ["residencia", "domicilio fiscal", "personas físicas"],
    "terminos_coloquiales": ["soy residente", "dónde pago impuestos"],
    "resumen": "Define quién se considera residente en México para efectos fiscales.",
    "preguntas_ejemplo": ["¿Soy residente fiscal?", "¿Dónde tributo si vivo fuera?"],
})


def _call(_prompt):                       # doble determinista
    return RESPUESTA


def _unidad():
    return Unidad(numero=9, cuerpo="Artículo 9o.- Se consideran residentes en territorio nacional las personas.")


def test_enrich_unit_arma_registro_valido():
    rec = enrich.enrich_unit(_unidad(), CFF, _call, "modelo-test")
    assert rec["clave"] == "009" and rec["documento"] == "cff"
    assert rec["denominacion_comun"] == "Residencia fiscal"
    assert rec["_generado"]["modelo"] == "modelo-test"
    assert rec["_generado"]["hash_texto"].startswith("sha256:")
    assert "advertencia" in rec["_generado"]


def test_call_que_no_devuelve_json_falla():
    with pytest.raises(ValueError):
        enrich.enrich_unit(_unidad(), CFF, lambda _p: "no hay json aquí", "m")


def test_validate_rechaza_campos_faltantes():
    with pytest.raises(ValueError):
        enrich.validate({"denominacion_comun": "x"})       # faltan listas


def test_clean_list_normaliza_salida_sucia():
    assert enrich._clean_list("residencia") == ["residencia"]   # string suelto
    assert enrich._clean_list(["  a ", "", None, "b", 3]) == ["a", "b", "3"]
    assert enrich._clean_list(None) == []
    assert enrich._clean_list({"x": 1}) == []                   # no-lista → vacío
    assert enrich._clean_list([True, "ok"]) == ["ok"]           # bool no es número


def test_validate_tolera_una_lista_vacia():
    # temas vacío pero las otras listas tienen contenido → válido (aporta recall).
    data = {
        "denominacion_comun": "Artículo derogado",
        "resumen": "El artículo fue derogado.",
        "temas": [],
        "terminos_coloquiales": ["artículo 70 bis derogado"],
        "preguntas_ejemplo": ["¿sigue vigente el 70 bis?"],
    }
    enrich.validate(data)                                       # no lanza


def test_validate_rechaza_todas_las_listas_vacias():
    data = {
        "denominacion_comun": "x", "resumen": "y",
        "temas": [], "terminos_coloquiales": [], "preguntas_ejemplo": [],
    }
    with pytest.raises(ValueError):
        enrich.validate(data)


def test_assemble_normaliza_temas_no_lista():
    # Reproduce el fallo real: el LLM devuelve `temas` como string + entradas
    # sucias. assemble normaliza y NO descarta la unidad.
    data = {
        "denominacion_comun": "  Residencia fiscal ",
        "temas": "residencia",                                 # string, no lista
        "terminos_coloquiales": ["  dónde pago ", ""],
        "resumen": " Define la residencia. ",
        "preguntas_ejemplo": ["¿soy residente?"],
    }
    rec = enrich.assemble(_unidad(), CFF, "texto", data, "m")
    assert rec["temas"] == ["residencia"]
    assert rec["terminos_coloquiales"] == ["dónde pago"]
    assert rec["denominacion_comun"] == "Residencia fiscal"


def test_prompt_pide_sinonimos_coloquiales():
    # Falla real del RAG: "factura" no recuperaba el Art. 27 LISR porque la ley
    # dice "comprobante fiscal" y el enriquecimiento nunca generó la palabra
    # cotidiana. El prompt debe exigir el puente coloquial→legal con ejemplos.
    prompt = enrich.build_prompt("Artículo 27 LISR", "texto")
    assert "factura" in prompt and "comprobante fiscal" in prompt
    assert "aguinaldo" in prompt and "gratificaciones" in prompt
    assert "gasolina" in prompt and "combustibles" in prompt


def test_needs_refresh_por_hash():
    u = _unidad()
    rec = enrich.enrich_unit(u, CFF, _call, "m")
    assert enrich.needs_refresh(u, None) is True            # no existe
    assert enrich.needs_refresh(u, rec) is False            # mismo texto
    u2 = Unidad(numero=9, cuerpo="Artículo 9o.- Texto distinto y más largo del artículo nueve.")
    assert enrich.needs_refresh(u2, rec) is True            # texto cambió


def test_run_enrichment_escribe_y_cachea(tmp_path):
    u = _unidad()
    s1 = enrich.run_enrichment([u], CFF, str(tmp_path), _call, "m")
    assert s1["generados"] == 1
    archivo = tmp_path / "metadata" / "cff" / "generado" / "009.json"
    assert archivo.exists()
    assert (tmp_path / "metadata" / "cff" / "generado" / "README.md").exists()
    # segunda corrida: el hash no cambió → se omite (caché)
    s2 = enrich.run_enrichment([u], CFF, str(tmp_path), _call, "m")
    assert s2["omitidos"] == 1 and s2["generados"] == 0


def test_run_enrichment_best_effort_salta_fallos(tmp_path):
    s = enrich.run_enrichment([_unidad()], CFF, str(tmp_path),
                              lambda _p: "inválido", "m", reintentos=1)
    assert s["fallidos"] == 1 and s["generados"] == 0       # no aborta


def test_cli_pdf_con_multidoc_es_error(tmp_path):
    """--pdf solo vale con un único --doc; el guard corre ANTES de construir el
    caller (no exige API key) y devuelve código 1."""
    from extractor.__main__ import main
    # Sin --doc el default son todos los activos (>1) → --pdf es inválido.
    rc = main(["enriquecer", "--pdf", "CFF.pdf", "--out", str(tmp_path),
               "--proveedor", "openai"])
    assert rc == 1
    assert not (tmp_path / "metadata").exists()             # no escribió nada
