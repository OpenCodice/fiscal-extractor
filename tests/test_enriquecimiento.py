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
