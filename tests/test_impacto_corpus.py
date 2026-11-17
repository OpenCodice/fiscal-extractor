"""Modos de scripts/impacto_corpus.py que usa el job `reparar`: la medición de
solo lectura del agente reparador (`--medir`, `--muestra`, `--objetivo`), la
descarga previa (`--solo-pdfs`) y la caché de PDF compartida con las
compuertas. Sin red ni PDF: la reconstrucción se sustituye."""
import hashlib
import importlib
import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))

ic = importlib.import_module("impacto_corpus")
im = importlib.import_module("impacto")

PDF = "b" * 64


def _doc(nombre, clave):
    return {"repo": None, "nombre": nombre, "clave": clave, "url": None, "sha256": PDF,
            "registro": None}


def _res(doc, cambios, repo="leyes-estatales", **extra):
    return {"documento": doc, "repo": repo, "pdf_sha256": PDF, "pdf": "/x.pdf", "error": None,
            "sin_pdf": False, "cambios": cambios, "regresiones": [], **extra}


ANTES, DESPUES = "# Artículo 1\n\nUno dos.\n", "# Artículo 1\n\nUno.\n\ndos.\n"


def test_muestra_espaciada_por_repo_y_con_el_objetivo():
    docs = [_doc("leyes-federales", f"l{i:02d}") for i in range(20)] + \
           [_doc("fiscal-mexicano", "cff"), _doc("leyes-federales", "cff")]
    elegidos = ic.muestrear(docs, 4, {"l07"})
    fed = sorted(d["clave"] for d in elegidos if d["nombre"] == "leyes-federales")
    assert fed == ["cff", "l04", "l07", "l09", "l14"]
    # La misma clave en otro repo cuenta aparte: el fiscal tiene un solo documento.
    assert [d["clave"] for d in elegidos if d["nombre"] == "fiscal-mexicano"] == ["cff"]
    assert ic.muestrear(docs, 0) == docs


def test_informe_separa_objetivo_de_lo_demas_y_usa_el_registro(tmp_path):
    ya = im.Cambio("jalisco/codigo-civil", "002", PDF, ANTES, DESPUES)
    im.escribir([{"documento": ya.documento, "clave": ya.clave, "pdf": PDF,
                  "antes": im.huella(ANTES), "despues": im.huella(DESPUES),
                  "veredicto": "mejora"}], tmp_path / "reg", "x")
    resultados = [_res("cdmx/codigo-civil", [("001", ANTES, DESPUES)]),
                  _res("jalisco/codigo-civil", [("001", ANTES, DESPUES), ("002", ANTES, DESPUES)])]
    datos, md = ic.informe_medicion(resultados, {"cdmx/codigo-civil"}, im.cargar(tmp_path / "reg"))
    assert (datos["cambian"], datos["en_objetivo"], datos["fuera"], datos["fuera_sin_confirmar"]) \
        == (3, 1, 2, 1)
    assert "jalisco/codigo-civil:001 — FUERA DEL OBJETIVO, sin juzgar" in md
    assert "jalisco/codigo-civil:002 — FUERA DEL OBJETIVO, ya confirmada como mejora" in md
    assert "+Uno." in md and "-Uno dos." in md


def _main(tmp_path, monkeypatch, resultados, *extra):
    docs = [_doc("leyes-estatales", r["documento"]) for r in resultados]
    por_clave = {r["documento"]: r for r in resultados}
    monkeypatch.setattr(ic, "documentos", lambda *a, **k: docs)
    monkeypatch.setattr(ic, "evaluar", lambda d, t, pdfs: por_clave[d["clave"]])
    t = tmp_path / "t"
    rc = ic.main(["--trabajo", str(t), "--sin-fiscal", "--sin-federal", "--estatal", str(tmp_path),
                  "--cache", str(tmp_path / "cache"), "--registro", str(tmp_path / "reg"),
                  "--medir", *extra])
    return rc, t


def test_medir_no_exporta_pendientes_y_sale_segun_lo_de_fuera(tmp_path, monkeypatch):
    solo_objetivo = [_res("cdmx/codigo-civil", [("001", ANTES, DESPUES)]),
                     _res("jalisco/codigo-civil", [])]
    rc, t = _main(tmp_path, monkeypatch, solo_objetivo, "--objetivo", "cdmx/codigo-civil")
    assert rc == 0
    assert not (t / "pendientes.json").exists()
    datos = json.loads((t / "medicion.json").read_text(encoding="utf-8"))
    assert datos["por_documento"] == {"cdmx/codigo-civil": 1}

    con_fuera = [_res("cdmx/codigo-civil", []), _res("jalisco/codigo-civil", [("001", ANTES, DESPUES)])]
    rc, t = _main(tmp_path, monkeypatch, con_fuera, "--objetivo", "cdmx/codigo-civil")
    assert rc == 1
    assert "FUERA DEL OBJETIVO" in (t / "medicion.md").read_text(encoding="utf-8")

    regresion = [_res("jalisco/codigo-civil", [("001", ANTES, DESPUES)], regresiones=["001"])]
    rc, _ = _main(tmp_path, monkeypatch, regresion, "--objetivo", "jalisco/codigo-civil")
    assert rc == 2


def test_solo_pdfs_no_construye(tmp_path, monkeypatch):
    monkeypatch.setattr(ic, "documentos", lambda *a, **k: [_doc("leyes-estatales", "cdmx/x")])
    monkeypatch.setattr(ic, "evaluar", lambda *a: (_ for _ in ()).throw(AssertionError("construyó")))
    pedidos = []
    monkeypatch.setattr(ic.PDFs, "obtener", lambda self, sha, url, clave: pedidos.append(clave))
    rc = ic.main(["--trabajo", str(tmp_path / "t"), "--sin-fiscal", "--sin-federal",
                  "--estatal", str(tmp_path), "--cache", str(tmp_path / "cache"), "--solo-pdfs"])
    assert rc == 0 and pedidos == ["cdmx/x"]


def test_un_pdf_alterado_en_la_cache_no_se_usa(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    bueno = b"%PDF-1.4 bueno"
    sha = hashlib.sha256(bueno).hexdigest()
    (cache / f"{sha}.pdf").write_bytes(bueno)
    assert ic.PDFs([], cache).obtener(sha, None, "x") == str(cache / f"{sha}.pdf")
    (cache / f"{sha}.pdf").write_bytes(b"%PDF-1.4 otro")
    # Sin URL no se puede volver a descargar: no hay PDF, en vez de uno falso.
    assert ic.PDFs([], cache).obtener(sha, None, "x") is None
    assert not (cache / f"{sha}.pdf").exists()
