"""Reparación autónoma del extractor: tope de intentos por ley y PDF, reintento
de las leyes tras un arreglo y la elección de lo que se repara."""
import json
import sys
from pathlib import Path

from extractor import federal, reparaciones

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import reparacion as rp  # noqa: E402

from test_federal import CAB, R_OK, _d, _docs, _fuentes, _plan, repo  # noqa: E402,F401


def _intento(reg: Path, n: int, documento="lgs", pdf="s", resultado="descartado"):
    reg.mkdir(parents=True, exist_ok=True)
    with (reg / f"i{n}.jsonl").open("a") as fh:
        for r in ("iniciado", resultado):
            fh.write(json.dumps({"documento": documento, "pdf": pdf, "intento": f"i{n}",
                                 "resultado": r}) + "\n")


def test_intentos_cuentan_por_ley_y_pdf(tmp_path):
    reg = tmp_path / "reg"
    _intento(reg, 1)
    _intento(reg, 2)
    _intento(reg, 3, pdf="otro")
    (reg / "roto.jsonl").write_text("{no es json\n")
    registros = reparaciones.cargar(reg)
    assert reparaciones.intentos("lgs", "s", registros) == 2
    assert not reparaciones.agotada("lgs", "s", registros)
    _intento(reg, 4)
    assert reparaciones.agotada("lgs", "s", reparaciones.cargar(reg))


def test_agotada_no_se_reintenta_por_otro_extractor_solo_por_otro_pdf(tmp_path):
    entrada = {"clave": "lgs", "url": "https://x/pdf/LGS.pdf", "estado": "excluida",
               "pdf": CAB, "extractor": "otra", "reparacion": {"intentos": 3, "agotada": True}}
    _fuentes(tmp_path, [entrada])
    assert federal.planear(tmp_path, _docs()[:1], consultar=lambda _u: CAB)["documentos"] == []
    plan = federal.planear(tmp_path, _docs()[:1], consultar=lambda _u: {**CAB, "etag": '"2"'})
    assert plan["documentos"][0]["motivo"] == "reintento"


def test_lo_publicado_con_hallazgos_vuelve_a_revisarse_tras_otro_extractor(tmp_path):
    rp_ = {"fecha": "2026-11-17", "motivo": "…", "pdf": CAB, "revisada": True}
    _fuentes(tmp_path, [
        {"clave": "lgs", "url": "https://x/pdf/LGS.pdf", "estado": "incluida", "pdf": CAB,
         "extractor": "otra", "revision_pendiente": rp_},
        {"clave": "lft", "url": "https://x/pdf/LFT.pdf", "estado": "incluida", "pdf": CAB,
         "extractor": "otra", "revision_pendiente": {**rp_, "agotada": True}},
        {"clave": "cpf", "url": "https://x/pdf/CPF.pdf", "estado": "incluida", "pdf": CAB,
         "extractor": "otra"}])
    plan = federal.planear(tmp_path, _docs(), consultar=lambda _u: CAB)
    assert plan["revisar"] == ["lgs"]


def test_cerrar_marca_la_ley_agotada(repo, tmp_path, monkeypatch):
    reg = tmp_path / "reg"
    for n in (1, 2, 3):
        _intento(reg, n, documento="lft")
    monkeypatch.setattr(reparaciones, "REGISTRO", reg)
    (repo / "lft").mkdir()
    (repo / "lft" / "001.md").write_text("# Artículo 1o.\n\nUno.\n")
    motivo = "La revisión completa contra el PDF encontró defectos de extracción: 001: pie colado"
    federal.cerrar(_plan(repo, [_d("lft", "reintento")]), str(repo), {"lft": {**R_OK, "revision": motivo}})
    e = {d["clave"]: d for d in json.loads((repo / "fuentes.json").read_text())["documentos"]}["lft"]
    assert e["estado"] == "excluida" and e["reparacion"] == {"intentos": 3, "agotada": True}
    assert "tras 3 intentos" in e["motivo"]
    # Con otro PDF, los intentos vuelven a empezar.
    federal.cerrar(_plan(repo, [_d("lft", "reintento")]), str(repo),
                   {"lft": {**R_OK, "sha256": "nuevo", "revision": motivo}})
    e = {d["clave"]: d for d in json.loads((repo / "fuentes.json").read_text())["documentos"]}["lft"]
    assert "reparacion" not in e and e["motivo"] == motivo


def test_hallazgos_del_motivo_y_su_tipo():
    motivo = ("La revisión completa contra el PDF encontró defectos de extracción: 150-bis: el "
              "artículo absorbió a su vecino; 155: la «o» final quedó como párrafo suelto; "
              "137: la nota de reforma «(Ref. P. O. No. 29, 8-VI-12)» quedó partida (y 3 más) "
              "Sin arreglo automático tras 3 intentos: se reintenta cuando cambie su PDF.")
    hs = rp.de_motivo(motivo)
    assert [h["clave"] for h in hs] == ["150-bis", "155", "137"]
    assert [rp.categoria(h["nota"]) for h in hs] == ["absorcion", "corte_parrafo", "nota_reforma"]
    assert rp.de_motivo("1 unidades no reproducen el PDF (x/872)") == []


def test_elegir_el_defecto_que_mas_leyes_comparten():
    def ley(clave, *cats, intentos=0):
        return {"clave": clave, "intentos": intentos,
                "hallazgos": [{"clave": "1", "nota": "", "categoria": c} for c in cats]}
    cands = [ley("a", "nota_reforma", "nota_reforma"), ley("b", "corte_parrafo", "nota_reforma"),
             ley("c", "corte_parrafo"), ley("d", "nota_reforma", intentos=2), ley("e", "otro")]
    grupo, elegidas = rp.elegir(cands, 2)
    assert grupo == "nota_reforma" and [e["clave"] for e in elegidas] == ["a", "b"]


def _construida(raiz: Path, textos: dict, problemas=(), error=None):
    d = raiz / "datos" / "q" / "ley" / "articulos"
    d.mkdir(parents=True, exist_ok=True)
    for k, v in textos.items():
        (d / f"{k}.md").write_text(v)
    r = {"error": error} if error else {"unidades": len(textos), "problemas": list(problemas)}
    (raiz / "resultado.json").write_text(json.dumps({"q/ley": r}))


def test_comparar_exige_algun_cambio_y_ninguna_regresion(tmp_path):
    obj = {"leyes": [{"clave": "q/ley"}]}
    a, d = tmp_path / "a", tmp_path / "d"
    _construida(a, {"001": "uno"})
    _construida(d, {"001": "uno"})
    assert not rp.comparar(obj, a, d)[0]                         # nada cambia
    _construida(d, {"001": "uno bien"}, problemas=["q/ley/002"])
    ok, motivo, _ = rp.comparar(obj, a, d)
    assert not ok and "problemas nuevos" in motivo
    _construida(d, {"001": "uno bien"}, error="la extracción falló")
    assert not rp.comparar(obj, a, d)[0]
    _construida(d, {"001": "uno bien"})
    assert rp.comparar(obj, a, d) == (True, "", ["q/ley"])
    (d / "resultado.json").unlink()
    assert not rp.comparar(obj, a, d)[0]                         # sin resultado no hay arreglo
