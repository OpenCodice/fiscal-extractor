"""Registro de correcciones confirmadas y su exigencia (scripts/impacto.py) y
revisión completa por bloques de un alta (scripts/revision.py). Idénticos en
constitucion-extractor y fiscal-extractor; esta prueba también."""
import importlib
import json
import subprocess
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))


im = importlib.import_module("impacto")
rv = importlib.import_module("revision")
tr = importlib.import_module("trailers")

EXT = "OpenCodice/fiscal-extractor@b897ca4"
PDF = "a" * 64


def _cambio(clave, pie="Página 3 de 90", doc="lgs"):
    return im.Cambio(doc, clave, PDF, f"# Artículo {clave}\n\nTexto {clave}. {pie}\n",
                     f"# Artículo {clave}\n\nTexto {clave}.\n")


def test_firma_agrupa_el_mismo_cambio_salvo_numeros():
    a, b = _cambio("004", "Página 3 de 90"), _cambio("022", "Página 17 de 90", doc="lft")
    c = im.Cambio("lgs", "030", PDF, "# Artículo 30\n\nUno.\n", "# Artículo 30\n\nDos.\n")
    grupos = im.agrupar([a, b, c])
    assert [len(g.miembros) for g in grupos] == [2, 1]
    assert {m.documento for m in grupos[0].muestra()} == {"lgs", "lft"}


def test_exportar_cerrar_y_no_verificar_dos_veces(tmp_path):
    reg, t = tmp_path / "registro", tmp_path / "t"
    cambios = [_cambio("004"), _cambio("022"),
               im.Cambio("lgs", "030", PDF, "# Artículo 30\n\nUno.\n", "# Artículo 30\n\nDos.\n")]
    r = im.exportar(cambios, t, {PDF: "/x.pdf"}, registro=im.cargar(reg))
    assert (r["pendientes"], r["grupos"]) == (3, 2)
    pend = json.loads((t / "pendientes.json").read_text())
    ids = [g["id"] for g in pend["grupos"]]
    (t / "veredicto-01.json").write_text(json.dumps({"grupos": [
        {"id": ids[0], "veredicto": "mejora", "nota": "pie de página"},
        {"id": ids[1], "veredicto": "incierto", "nota": "no se ve"}]}))
    ok, res = im.cerrar(t, EXT, reg, "2026-01-01-lote")
    assert not ok and res["mejora"] == 2 and len(res["rechazados"]) == 1
    registro = im.cargar(reg)
    assert im.faltantes(registro, "lgs", PDF, {c.clave: (c.antes, c.despues) for c in cambios}) == ["030"]
    # Lo ya juzgado no se vuelve a exportar.
    r2 = im.exportar(cambios, tmp_path / "t2", {}, registro=registro)
    assert (r2["pendientes"], r2["ya_mejora"], r2["ya_incierto"]) == (0, 2, ["lgs:030"])
    # Otro arreglo que llega al mismo texto se juzga de nuevo; el último vale.
    t3 = tmp_path / "t3"
    r3 = im.exportar(cambios, t3, {}, registro=registro, rejuzgar=True)
    assert (r3["pendientes"], r3["ya_incierto"]) == (1, [])
    g = json.loads((t3 / "pendientes.json").read_text())["grupos"][0]["id"]
    (t3 / "veredicto-01.json").write_text(json.dumps({"grupos": [
        {"id": g, "veredicto": "mejora", "nota": "se ve"}]}))
    assert im.cerrar(t3, EXT, reg)[0]
    assert im.faltantes(im.cargar(reg), "lgs", PDF,
                        {c.clave: (c.antes, c.despues) for c in cambios}) == []


def test_cerrar_sin_veredicto_no_aprueba(tmp_path):
    im.exportar([_cambio("004")], tmp_path, {}, registro={})
    ok, res = im.cerrar(tmp_path, EXT, tmp_path / "reg", "x")
    assert not ok and res["sin_veredicto"] == ["lgs:004"]
    assert im.cargar(tmp_path / "reg") == {}


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True,
                          text=True).stdout


def test_pendientes_y_exigir_sobre_commits(tmp_path):
    repo = tmp_path / "datos"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "lgs").mkdir()
    (repo / "metadata" / "lgs").mkdir(parents=True)
    (repo / "metadata" / "lgs" / "articulos.json").write_text(json.dumps({"sigla": "LGS"}))
    c = _cambio("004")
    (repo / "lgs" / "004.md").write_text(c.antes)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "publicado")
    base = _git(repo, "rev-parse", "HEAD").strip()
    (repo / "lgs" / "004.md").write_text(c.despues)
    rutas = ["lgs/004.md"]
    msg = tr.mensaje("lgs", "correccion", rutas, tr.lector_git(str(repo), "HEAD"),
                     tr.lector_fs(str(repo)), fuente="https://x", fuente_sha256=PDF, extractor=EXT)
    _git(repo, "commit", "-qam", msg)
    reg, t = tmp_path / "reg", tmp_path / "t"
    assert im.main(["exigir", str(repo), "--base", base, "--registro", str(reg)]) == 1
    veredicto = tmp_path / "veredicto.json"
    veredicto.write_text(json.dumps({"fiel": True, "unidades": [
        {"clave": "lgs/004", "veredicto": "fiel", "nota": "contra la pág. 3"}]}))
    pdfs = tmp_path / "pdfs"
    pdfs.mkdir()
    # El agente de la vigilancia revisó contra otro PDF: no cuenta.
    (pdfs / "otro.pdf").write_bytes(b"%PDF otro")
    im.main(["pendientes-commits", str(repo), "--base", base, "--trabajo", str(t),
             "--pdf-dir", str(pdfs), "--registro", str(reg), "--veredicto-agente", str(veredicto),
             "--extractor", EXT])
    assert json.loads((t / "pendientes.json").read_text())["resumen"]["pendientes"] == 1
    assert im.main(["exigir", str(repo), "--base", base, "--registro", str(reg)]) == 1
    entrada = {"documento": "lgs", "clave": "004", "pdf": PDF, "antes": im.huella(c.antes),
               "despues": im.huella(c.despues), "veredicto": "mejora"}
    im.escribir([entrada], reg, "manual")
    assert im.main(["exigir", str(repo), "--base", base, "--registro", str(reg)]) == 0


# ------------------------------------------------------------------ revisión

def test_bloques_ubicar_y_cerrar(tmp_path, monkeypatch):
    repo = tmp_path / "datos"
    (repo / "lgs").mkdir(parents=True)
    (repo / "metadata" / "lgs").mkdir(parents=True)
    claves = [f"{i:03d}" for i in range(1, 7)]
    (repo / "metadata" / "lgs" / "articulos.json").write_text(
        json.dumps({"articulos": [{"clave": c} for c in claves]}))
    for c in claves:
        (repo / "lgs" / f"{c}.md").write_text(
            f"# Artículo {int(c)}\n\nEl artículo número {int(c)} dispone lo siguiente " + "x" * 40 + "\n")
    pags = [f"Artículo {i}. El artículo número {i} dispone lo siguiente " + "x" * 40
            for i in range(1, 7)]
    monkeypatch.setattr(rv, "paginas", lambda pdf, cache=None: pags)
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF")
    assert rv.ubicar(rv.articulos(repo, "lgs"), pags) == [1, 2, 3, 4, 5, 6]
    bls = rv.bloques(repo, "lgs", str(pdf), tmp_path / "rev", caracteres=200)
    assert [b["claves"] for b in bls] == [claves[:2], claves[2:4], claves[4:]]
    assert [b["paginas"] for b in bls] == [[1, 3], [3, 5], [5, 6]]
    t = tmp_path / "rev"
    t.mkdir(exist_ok=True)
    reg = tmp_path / "reg"
    (t / "veredicto-01.json").write_text(json.dumps({"bloques": [
        {"id": b["id"], "huella": b["huella"], "hallazgos": []} for b in bls[:2]]}))
    monkeypatch.setattr(rv, "CARACTERES_POR_BLOQUE", 200)
    ok, motivo = rv.cerrar(repo, "lgs", str(pdf), t, registro=reg)
    assert not ok and "no cubrió 1 de 3" in motivo and not reg.exists()
    (t / "veredicto-02.json").write_text(json.dumps({"bloques": [
        {"id": bls[2]["id"], "huella": bls[2]["huella"],
         "hallazgos": [{"clave": "006", "nota": "pie colado"}]}]}))
    ok, motivo = rv.cerrar(repo, "lgs", str(pdf), t, registro=reg)
    assert not ok and "006: pie colado" in motivo
    sha = tr.sha256_bytes(b"%PDF")
    assert rv.previa("lgs", sha, rv.huella_extractor(), reg)["resultado"] == "hallazgos"
    # Un arreglo que cambia el texto invalida la revisión de ese bloque.
    (repo / "lgs" / "006.md").write_text("# Artículo 6\n\nEl artículo número 6 dispone lo siguiente.\n")
    ok, motivo = rv.cerrar(repo, "lgs", str(pdf), t, registro=reg)
    assert not ok and "no cubrió 1 de 3" in motivo


def test_ya_confirmadas_en_el_arbol_de_trabajo(tmp_path):
    repo = tmp_path / "datos"
    (repo / "lgs").mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    c = _cambio("004")
    (repo / "lgs" / "004.md").write_text(c.antes)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "publicado")
    (repo / "lgs" / "004.md").write_text(c.despues)
    pdf = tmp_path / "lgs.pdf"
    pdf.write_bytes(b"%PDF lgs")
    reg = tmp_path / "reg"
    args = ["ya-confirmadas", str(repo), "--documento", "lgs", "--pdf", str(pdf), "--registro", str(reg)]
    assert im.main(args) == 1
    im.escribir([{"documento": "lgs", "clave": "004", "pdf": tr.sha256_bytes(b"%PDF lgs"),
                  "antes": im.huella(c.antes), "despues": im.huella(c.despues),
                  "veredicto": "mejora"}], reg, "x")
    assert im.main(args) == 0
