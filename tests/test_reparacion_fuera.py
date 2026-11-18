"""Las leyes estatales que un módulo deja en FUERA también se reparan
(scripts/reparacion.py fuera, objetivo --fuera y promover)."""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import reparacion  # noqa: E402

from extractor.estatales import fuera, fuera_por_diseno, ley  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent


def test_lo_que_queda_fuera_por_diseno_no_se_repara():
    assert "cdmx/codigo-de-procedimientos-civiles" in fuera_por_diseno()
    assert fuera_por_diseno() <= set(fuera())
    assert "cdmx/codigo-de-procedimientos-civiles" not in reparacion.reparables()
    assert set(reparacion.reparables()) == set(fuera()) - fuera_por_diseno()


def _r(**kw):
    return {"sha256": "s1", "url": "https://x/a.pdf", "unidades": 10, "problemas": {},
            "invariantes": [], **kw}


def test_las_de_fuera_que_fallan_entran_al_objetivo(tmp_path):
    out = tmp_path / "datos"
    out.mkdir()
    (out / "fuentes.json").write_text(json.dumps({"documentos": []}))
    medidas = {
        "nuevo-leon/codigo-civil": _r(problemas={"nuevo-leon/codigo-civil/022": [
            {"tipo": "omitido", "fragmento": "Art. 22.- Las personas"}]}),
        "nuevo-leon/ley-de-hacienda": _r(),                    # limpia: se promueve, no se repara
        "nuevo-leon/codigo-penal": _r(error="la extracción falló: X"),
    }
    registros = [{"documento": "nuevo-leon/codigo-penal", "pdf": "s1", "intento": str(i)}
                 for i in range(3)]
    cands = reparacion.candidatos("estatal", out, tmp_path, True, registros, fuera=medidas)
    assert [c["clave"] for c in cands] == ["nuevo-leon/codigo-civil"]
    c = cands[0]
    assert c["origen"] == "fuera" and c["pdf_sha256"] == "s1" and c["intentos"] == 0
    assert c["hallazgos"][0]["categoria"] == "auditoria"
    # Con 3 intentos con ese PDF ya no entra (el penal); con otro PDF, sí.
    medidas["nuevo-leon/codigo-penal"]["sha256"] = "s2"
    cands = reparacion.candidatos("estatal", out, tmp_path, True, registros, fuera=medidas)
    assert "nuevo-leon/codigo-penal" in [c["clave"] for c in cands]


def test_el_bloque_pasa_las_leyes_de_fuera_a_leyes():
    ns = {"ley": ley}
    codigo = (
        "MEDIO = 'PO'\n"
        "LEYES = [ley('yucatan', 'Ley A del Estado de Yucatán', 'A', medio=MEDIO, url='https://x/a.pdf')]\n"
        "FUERA = [(ley('yucatan', 'Código Civil del Estado de Yucatán', 'CC', medio=MEDIO, url='https://x/b.pdf'), 'm'),\n"
        "         (ley('yucatan', 'Código Penal del Estado de Yucatán', 'CP', medio=MEDIO, url='https://x/c.pdf'), 'n')]\n")
    exec(codigo + reparacion.bloque_leyes(["yucatan/codigo-civil"]), ns)
    assert [d.clave for d in ns["LEYES"]] == ["yucatan/ley-a", "yucatan/codigo-civil"]
    assert [(d.clave, m) for d, m in ns["FUERA"]] == [("yucatan/codigo-penal", "n")]


def test_promover_solo_agrega_un_bloque_al_modulo(tmp_path, monkeypatch):
    raiz = tmp_path / "ext"
    (raiz / "extractor" / "estatales").mkdir(parents=True)
    original = (RAIZ / "extractor" / "estatales" / "nuevo_leon.py").read_text(encoding="utf-8")
    (raiz / "extractor" / "estatales" / "nuevo_leon.py").write_text(original, encoding="utf-8")
    shutil.copy(RAIZ / "extractor" / "estatales" / "cdmx.py", raiz / "extractor" / "estatales")
    res = tmp_path / "fuera.json"
    res.write_text(json.dumps({
        "nuevo-leon/codigo-civil": _r(),
        "nuevo-leon/codigo-penal": _r(problemas={"x": [{}]}),
        "cdmx/codigo-de-procedimientos-civiles": _r(),           # por diseño: nunca
        "nuevo-leon/no-declarada": _r(),
    }))
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    assert reparacion.main(["promover", "--resultado", str(res), "--raiz", str(raiz)]) == 0
    nuevo = (raiz / "extractor" / "estatales" / "nuevo_leon.py").read_text(encoding="utf-8")
    assert nuevo.startswith(original.rstrip("\n"))
    bloque = nuevo[len(original.rstrip("\n")):]
    assert '"nuevo-leon/codigo-civil"' in bloque and "codigo-penal" not in bloque
    assert (raiz / "extractor" / "estatales" / "cdmx.py").read_text() == \
        (RAIZ / "extractor" / "estatales" / "cdmx.py").read_text()


def test_fuera_mide_y_reusa_la_cache(tmp_path, monkeypatch):
    from extractor import federal, fuentes
    defs = {"yucatan/codigo-civil": ley("yucatan", "Código Civil del Estado de Yucatán", "CC",
                                        medio="PO", url="https://x/b.pdf"),
            "yucatan/codigo-penal": ley("yucatan", "Código Penal del Estado de Yucatán", "CP",
                                        medio="PO", url="https://caida/c.pdf")}
    monkeypatch.setattr(reparacion, "reparables", lambda: defs)

    def descargar(url, dest, via=None):
        if "caida" in url:
            raise OSError("sin respuesta")
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(b"%PDF-1.4 x")
    monkeypatch.setattr(fuentes, "descargar", descargar)
    construidas = []
    monkeypatch.setattr(federal, "_construir", lambda doc, pdf, out, reg: construidas.append(doc["clave"]))
    monkeypatch.setattr(federal, "evaluar", lambda out, c, pdf: {"unidades": 5, "problemas": {},
                                                                 "invariantes": []})
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    args = ["fuera", "--trabajo", str(tmp_path / "t"), "--pdfs", str(tmp_path / "p"),
            "--salida", str(tmp_path / "f.json"), "--cache", str(tmp_path / "c"),
            "--registro", str(tmp_path / "sin-registro")]
    assert reparacion.main(args) == 0
    r = json.loads((tmp_path / "f.json").read_text())
    assert reparacion.es_limpia(r["yucatan/codigo-civil"])
    assert r["yucatan/codigo-civil"]["intentos"] == 0 and r["yucatan/codigo-civil"]["definicion"]
    assert "error_fuente" in r["yucatan/codigo-penal"] and "sha256" not in r["yucatan/codigo-penal"]
    assert construidas == ["yucatan/codigo-civil"]
    # Mismo PDF y misma huella: no se reconstruye.
    assert reparacion.main(args) == 0
    assert construidas == ["yucatan/codigo-civil"]
