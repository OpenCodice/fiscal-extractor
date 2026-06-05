"""Invariantes sobre el repo de datos ya construido (integración).

No parsea PDF: lee `../fiscal-mexicano` y valida las propiedades que un PR de
reforma debe conservar. Si el repo de datos no está construido, se omite.
Es el gate de regresión barato: o se cumplen o no.
"""
import json
import re
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[2] / "fiscal-mexicano"
LEAK = ("CÁMARA DE DIPUTADOS", "Secretaría de Servicios")
FOOTER_RE = re.compile(r"^\d{1,4} de \d{1,4}$", re.MULTILINE)

pytestmark = pytest.mark.skipif(
    not (DATA / "metadata" / "documentos.json").exists(),
    reason="repo de datos fiscal-mexicano no construido",
)


def _docs():
    idx = json.loads((DATA / "metadata" / "documentos.json").read_text(encoding="utf-8"))
    return [d["clave"] for d in idx["documentos"]]


def test_indice_maestro_coincide_con_carpetas():
    for clave in _docs():
        assert (DATA / clave).is_dir(), f"falta carpeta de texto de {clave}"
        idx = json.loads((DATA / "metadata" / clave / "articulos.json")
                         .read_text(encoding="utf-8"))
        n_files = len(list((DATA / clave).glob("*.md")))
        assert idx["num_articulos"] == n_files, (
            f"{clave}: índice dice {idx['num_articulos']} pero hay {n_files} .md "
            f"(¿colisión de claves?)")


def test_sin_fugas_de_encabezado_ni_pie():
    for clave in _docs():
        for md in (DATA / clave).glob("*.md"):
            txt = md.read_text(encoding="utf-8")
            assert not any(m in txt for m in LEAK), f"fuga de encabezado en {md}"
            assert not FOOTER_RE.search(txt), f"fuga de pie de página en {md}"


def test_cada_articulo_tiene_cuerpo():
    for clave in _docs():
        for md in (DATA / clave).glob("*.md"):
            cuerpo = md.read_text(encoding="utf-8").split("\n", 2)[-1].strip()
            assert len(cuerpo) >= 8, f"{md} parece vacío/truncado"


def test_claves_unicas_por_documento():
    for clave in _docs():
        nombres = [p.stem for p in (DATA / clave).glob("*.md")]
        assert len(nombres) == len(set(nombres)), f"{clave}: claves duplicadas"


def test_metadata_reformas_son_fechas_iso():
    for clave in _docs():
        ref = json.loads((DATA / "metadata" / clave / "reformas.json")
                         .read_text(encoding="utf-8"))
        for fecha in ref:
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", fecha), f"{clave}: fecha {fecha!r}"
