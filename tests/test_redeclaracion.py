"""Leyes de FUERA de un estado ya publicado que no se pueden descargar por algo
del extractor: `reparacion.py fuera` dice la causa, `reparar` lanza la ronda
de redeclaración (expansion.py redeclarar-pendiente / elegir --redeclarar) y
su cerco solo deja agregar opciones a esas entradas."""
import copy
import json
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import expansion  # noqa: E402
import reparacion  # noqa: E402

from extractor.fuentes import descargar  # noqa: E402


def _excepcion(f):
    try:
        f()
    except Exception as e:                           # noqa: BLE001
        return e
    raise AssertionError("no falló")


def test_un_href_con_espacio_es_causa_del_extractor():
    # http.client lo rechaza antes de conectarse: no hace falta red.
    e = _excepcion(lambda: descargar("https://no-existe.invalid/a.pdf?2026-03- 9", "/dev/null"))
    assert reparacion.causa_fuente(e) == "codigo"


@pytest.mark.parametrize("e, causa", [
    (urllib.error.URLError("timed out"), "red"),
    (TimeoutError(), "red"),
    (ConnectionResetError(), "red"),
    (urllib.error.HTTPError("u", 404, "Not Found", {}, None), "red"),
    (urllib.error.HTTPError("u", 503, "x", {}, None), "red"),
    (urllib.error.HTTPError("u", 400, "Bad Request", {}, None), "codigo"),
    (LookupError("ningún PDF coincide"), "codigo"),
    (ValueError("unknown url type: 'x'"), "codigo"),
    (reparacion.NoEsPdf("lo descargado no es un PDF"), "red"),
])
def test_causa_fuente(e, causa):
    assert reparacion.causa_fuente(e) == causa


def _fuera_res():
    return {
        "nuevo-leon/ley-a": {"error_fuente": "InvalidURL: URL can't contain control characters",
                             "causa_fuente": "codigo"},
        "nuevo-leon/ley-b": {"error_fuente": "URLError: timed out", "causa_fuente": "red"},
        "nuevo-leon/ley-c": {"sha256": "s", "unidades": 3},
        "jalisco/ley-d": {"error_fuente": "LookupError: x", "causa_fuente": "codigo"},
    }


def _lista():
    return {"tope_intentos": 3, "estados": [
        {"estado": "nuevo-leon", "situacion": "publicado", "intentos": 2},
        {"estado": "yucatan", "situacion": "pendiente", "intentos": 0}]}


def test_objetivo_solo_las_de_causa_codigo_del_estado():
    o = expansion.objetivo_redeclaracion(_lista()["estados"][0], _fuera_res(), _lista())
    assert list(o["leyes"]) == ["nuevo-leon/ley-a"] and o["intentos"] == 0
    # Un estado sin publicar no se redeclara (lo hace su ronda normal).
    assert expansion.objetivo_redeclaracion(_lista()["estados"][1], _fuera_res(), _lista()) is None


def test_tope_por_firma_de_la_falla():
    lista = _lista()
    for _ in range(expansion.TOPE_REDECLARACION):
        assert expansion.elegir_redeclaracion(lista, "nuevo-leon", _fuera_res())
    r = lista["estados"][0]["redeclaracion"]
    assert r["intentos"] == expansion.TOPE_REDECLARACION and r["leyes"] == ["nuevo-leon/ley-a"]
    assert expansion.elegir_redeclaracion(lista, "nuevo-leon", _fuera_res()) is None
    # El estado no deja de estar publicado ni gasta sus intentos de ronda.
    assert lista["estados"][0]["situacion"] == "publicado" and lista["estados"][0]["intentos"] == 2
    # Una falla distinta empieza de cero.
    res = _fuera_res()
    res["nuevo-leon/ley-b"].update(causa_fuente="codigo", error_fuente="LookupError: y")
    assert expansion.elegir_redeclaracion(lista, "nuevo-leon", res)["intentos"] == 0
    assert lista["estados"][0]["redeclaracion"]["intentos"] == 1


def test_redeclarar_pendiente(tmp_path, monkeypatch):
    lista = tmp_path / "pendientes.json"
    lista.write_text(json.dumps(_lista()))
    fuera = tmp_path / "fuera.json"
    fuera.write_text(json.dumps(_fuera_res()))
    salida = tmp_path / "out"
    monkeypatch.setattr(expansion, "LISTA", lista)
    monkeypatch.setenv("GITHUB_OUTPUT", str(salida))
    assert expansion.main(["redeclarar-pendiente", "--fuera", str(fuera)]) == 0
    # jalisco no está en la lista (no lo publicó la ronda): no se redeclara.
    assert salida.read_text() == "estado=nuevo-leon\n"


def _anotar(lista, *args):
    return expansion.main(["anotar", "--estado", "nuevo-leon", "--redeclaracion", *args])


def test_anotar_redeclaracion(tmp_path, monkeypatch):
    lista = tmp_path / "pendientes.json"
    datos = _lista()
    expansion.elegir_redeclaracion(datos, "nuevo-leon", _fuera_res())
    lista.write_text(json.dumps(datos))
    monkeypatch.setattr(expansion, "LISTA", lista)
    salida = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(salida))
    for _ in range(expansion.TOPE_CODIGO):
        _anotar(lista, "--resultado", "codigo", "--motivo", "falta codificar la consulta")
    _anotar(lista, "--resultado", "codigo", "--motivo", "otra vez")
    assert salida.read_text().splitlines() == ["codigo=true"] * expansion.TOPE_CODIGO + ["codigo=false"]
    _anotar(lista, "--resultado", "codigo-publicado", "--motivo", "codificar_consulta")
    e = json.loads(lista.read_text())["estados"][0]
    assert e["situacion"] == "publicado" and e["intentos"] == 2
    assert e["redeclaracion"]["intentos"] == 0     # el que pidió el código no cuenta
    _anotar(lista, "--resultado", "publicado")
    assert json.loads(lista.read_text())["estados"][0]["redeclaracion"]["situacion"] == "redeclarado"


# ------------------------------------------------------------------ cerco

def _registro():
    def d(clave, **kw):
        return {"clave": clave, "etiqueta": clave, "sigla": "X", "tipo": "ley", "parser": "articulado",
                "url": None, "indice": "https://x/", "patron": "a", "medio": "PO", "consulta": True, **kw}
    return {"documentos": [d("nuevo-leon/ley-l")], "medio": "PO", "por_diseno": ["nuevo-leon/ley-z"],
            "fuera": {}, "fuera_documentos": [d("nuevo-leon/ley-a"), d("nuevo-leon/ley-b"),
                                              d("nuevo-leon/ley-z")]}


OBJ = {"nuevo-leon/ley-a", "nuevo-leon/ley-z"}


def _con(f):
    r = copy.deepcopy(_registro())
    f(r)
    return expansion.cerco_redeclaracion(_registro(), r, OBJ)


def _fuera(r, clave):
    return next(d for d in r["fuera_documentos"] if d["clave"] == clave)


def test_cerco_agregar_una_opcion_a_una_ley_del_objetivo():
    errores, cambiadas = _con(lambda r: _fuera(r, "nuevo-leon/ley-a").update(codificar_consulta=True))
    assert errores == [] and [d["clave"] for d in cambiadas] == ["nuevo-leon/ley-a"]
    # Dar valor a un campo que estaba vacío también es agregar una opción.
    errores, _ = _con(lambda r: _fuera(r, "nuevo-leon/ley-a").update(url=None, via="mx"))
    assert errores == []


@pytest.mark.parametrize("cambio, error", [
    (lambda r: r["documentos"][0].update(codificar_consulta=True), "cambió LEYES"),
    (lambda r: r["documentos"].append(r["fuera_documentos"].pop(0)), "cambió LEYES"),
    (lambda r: _fuera(r, "nuevo-leon/ley-a").update(patron="b"), "cambió patron"),
    (lambda r: _fuera(r, "nuevo-leon/ley-b").update(codificar_consulta=True), "no es una de las leyes"),
    (lambda r: _fuera(r, "nuevo-leon/ley-z").update(codificar_consulta=True), "no es una de las leyes"),
    (lambda r: r.update(por_diseno=[]), "FUERA_POR_DISENO"),
    (lambda r: r.update(medio="otro"), "MEDIO"),
    (lambda r: r["fuera_documentos"].pop(1), "qué leyes hay en FUERA"),
    (lambda r: None, "no agregó ninguna opción"),
])
def test_cerco_lo_demas_no_se_toca(cambio, error):
    errores, _ = _con(cambio)
    assert any(error in e for e in errores), errores


def test_registro_trae_lo_que_compara_el_cerco(tmp_path):
    salida = tmp_path / "r.json"
    assert expansion.main(["registro", "--estado", "cdmx", "--salida", str(salida)]) == 0
    r = json.loads(salida.read_text())
    assert r["medio"] and r["fuera_documentos"]
    assert "cdmx/codigo-de-procedimientos-civiles" in r["por_diseno"]
    assert expansion.cerco_redeclaracion(r, r, set())[0] == ["no agregó ninguna opción a las leyes por redeclarar"]


def test_fuera_solo_fuente_anota_la_causa(tmp_path, monkeypatch):
    import extractor.fuentes as fuentes
    monkeypatch.setattr(fuentes, "url_vigente", lambda d: "https://no-existe.invalid/a.pdf?2026-03- 9")
    salida = tmp_path / "fuera.json"
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    assert reparacion.main(["fuera", "--trabajo", str(tmp_path), "--pdfs", str(tmp_path / "pdfs"),
                            "--salida", str(salida), "--estado", "nuevo-leon", "--solo-fuente",
                            "--registro", str(tmp_path / "reg")]) == 0
    res = json.loads(salida.read_text())
    assert res and all(c.startswith("nuevo-leon/") for c in res)
    assert {r["causa_fuente"] for r in res.values()} == {"codigo"}
