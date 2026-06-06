"""Pruebas del validador: debe pasar un repo sano y FALLAR uno corrompido."""
import json

import pytest

from extractor.validate import validar


def _repo(tmp, clave, tipo, items, textos, reformas=None):
    """Arma un mini repo de datos para validar."""
    (tmp / clave).mkdir(parents=True, exist_ok=True)
    for nombre, cuerpo in textos.items():
        (tmp / clave / f"{nombre}.md").write_text(cuerpo, encoding="utf-8")
    meta = tmp / "metadata" / clave
    meta.mkdir(parents=True, exist_ok=True)
    key = "reglas" if tipo == "rmf" else "articulos"
    (meta / "articulos.json").write_text(json.dumps({
        "documento": clave, "etiqueta": clave, "sigla": clave.upper(),
        "tipo": tipo, "version": "2026-01-01", "num_articulos": len(items),
        key: items,
    }), encoding="utf-8")
    (meta / "reformas.json").write_text(json.dumps(reformas or {}), encoding="utf-8")
    (tmp / "metadata" / "documentos.json").write_text(json.dumps({
        "documentos": [{"clave": clave, "etiqueta": clave, "sigla": clave.upper(),
                        "tipo": tipo, "num_articulos": len(items),
                        "version": "2026-01-01"}]
    }), encoding="utf-8")


def _art(num):
    return {"articulo": num, "clave": f"{num:03d}", "archivo": f"x/{num:03d}.md"}


def test_articulado_sano_pasa(tmp_path):
    items = [_art(1), _art(2), _art(3)]
    textos = {f"{n:03d}": f"# Artículo {n}o.\n\nCuerpo suficiente del artículo {n}."
              for n in (1, 2, 3)}
    _repo(tmp_path, "cff", "ley", items, textos)
    ok, checks = validar(str(tmp_path))
    assert ok, [c for c in checks if not c[0]]


def test_colision_de_claves_falla(tmp_path):
    # índice dice 3 artículos pero solo hay 2 archivos (uno se sobrescribió).
    items = [_art(1), _art(2), _art(3)]
    textos = {f"{n:03d}": f"# Artículo {n}o.\n\nCuerpo del artículo {n} válido."
              for n in (1, 2)}             # falta 003.md
    _repo(tmp_path, "cff", "ley", items, textos)
    ok, checks = validar(str(tmp_path))
    assert not ok
    assert any("índice == archivos" in c[1] and not c[0] for c in checks)


def test_hueco_en_secuencia_falla(tmp_path):
    items = [_art(1), _art(2), _art(4)]    # falta el 3
    textos = {f"{n:03d}": f"# Artículo {n}o.\n\nCuerpo del artículo {n} válido."
              for n in (1, 2, 4)}
    _repo(tmp_path, "cff", "ley", items, textos)
    ok, checks = validar(str(tmp_path))
    assert not ok
    assert any("secuencia" in c[1] and not c[0] for c in checks)


def test_regla_inconsistente_con_contexto_falla(tmp_path):
    items = [
        {"numero": "2.7.1.1", "clave": "2.7.1.1", "titulo": "Título 2. CFF",
         "capitulo": "Capítulo 2.7. CFDI", "seccion": "Sección 2.7.1. Generales"},
        # número 3.1.5 bajo Sección 2.7.1 → inconsistente (cita colada).
        {"numero": "3.1.5", "clave": "3.1.5", "titulo": "Título 2. CFF",
         "capitulo": "Capítulo 2.7. CFDI", "seccion": "Sección 2.7.1. Generales"},
    ]
    textos = {"2.7.1.1": "# Regla 2.7.1.1.\n\nCuerpo de la regla válido aquí.",
              "3.1.5": "# Regla 3.1.5.\n\nCuerpo de la regla válido aquí."}
    _repo(tmp_path, "rmf-2026", "rmf", items, textos)
    ok, checks = validar(str(tmp_path))
    assert not ok
    assert any("consistentes con su contexto" in c[1] and not c[0] for c in checks)
