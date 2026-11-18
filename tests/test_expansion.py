"""La parte determinista de la ronda de expansión (scripts/expansion.py)."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import expansion  # noqa: E402

from extractor.estatales import ENTIDADES, ley  # noqa: E402


def _lista(*estados, tope=3):
    return {"tope_intentos": tope, "estados": [
        {"estado": e, "situacion": s, "intentos": n, **extra} for e, s, n, extra in estados]}


def test_la_lista_cubre_los_estados_sin_modulo():
    lista = json.loads(expansion.LISTA.read_text(encoding="utf-8"))
    nombres = [e["estado"] for e in lista["estados"]]
    assert len(nombres) == len(set(nombres))
    assert set(nombres) <= set(ENTIDADES)
    # Durante la ronda, el módulo del estado que se está sumando ya existe
    # aunque su situación aún no sea «publicado».
    en_curso = os.environ.get("EXPANSION_ESTADO")
    for e in lista["estados"]:
        if e["situacion"] != "publicado" and e["estado"] != en_curso:
            assert not expansion.modulo_de(e["estado"]).exists(), e["estado"]
    con_modulo = {s for s in ENTIDADES if expansion.modulo_de(s).exists()}
    assert set(ENTIDADES) == set(nombres) | con_modulo


def test_elegir_el_siguiente_pendiente_bajo_el_tope():
    lista = _lista(("a", "egress", 0, {"dominio": "x.gob.mx"}), ("b", "pendiente", 3, {}),
                   ("c", "pendiente", 1, {}), ("d", "pendiente", 0, {}))
    assert expansion.elegir(lista, None, set(), lambda s: False)["estado"] == "c"
    # Un dominio que ya está en egress-mx vuelve a la cola, en su lugar.
    assert expansion.elegir(lista, None, {"x.gob.mx"}, lambda s: False)["estado"] == "a"
    assert lista["estados"][0]["situacion"] == "pendiente"


def test_elegir_un_estado_pedido():
    lista = _lista(("a", "pendiente", 0, {}), ("b", "egress", 1, {"dominio": "y"}),
                   ("c", "pendiente", 3, {}))
    assert expansion.elegir(lista, "b", set(), lambda s: False)["estado"] == "b"
    for estado in ("c", "zz"):
        try:
            expansion.elegir(lista, estado, set(), lambda s: False)
        except SystemExit:
            continue
        raise AssertionError(estado)
    # Con módulo ya está publicado: no se elige.
    lista = _lista(("a", "pendiente", 0, {}))
    assert expansion.elegir(lista, None, set(), lambda s: True) is None
    assert lista["estados"][0]["situacion"] == "publicado"


def test_permitidos_de_la_lista_de_egress(tmp_path):
    w = tmp_path / "permitidos.json"
    w.write_text(json.dumps({"_nota": "x", "dominios": ["a.gob.mx", "b.gob.mx", "no es dominio", 3]}))
    assert expansion.permitidos(str(w)) == {"a.gob.mx", "b.gob.mx"}
    assert expansion.permitidos(str(tmp_path / "no")) == set()
    (tmp_path / "roto.json").write_text("{")
    assert expansion.permitidos(str(tmp_path / "roto.json")) == set()


def test_motivo_fuera():
    assert expansion.motivo_fuera({"unidades": 10, "problemas": []}) is None
    assert "3 de 10" in expansion.motivo_fuera({"unidades": 10, "problemas": ["001", "002", "003"]})
    assert expansion.motivo_fuera({"unidades": 0, "problemas": []})
    assert expansion.motivo_fuera({"error": "build: ValueError"}).startswith("El extractor no pudo")


def test_el_bloque_fuera_mueve_las_leyes():
    medio = "Periódico Oficial"
    ns = {"ley": ley, "MEDIO": medio}
    exec("LEYES = [ley('yucatan', 'Código Civil del Estado de Yucatán', 'CC Yuc', medio=MEDIO, url='https://x/a.pdf'),"
         " ley('yucatan', 'Código Penal del Estado de Yucatán', 'CP Yuc', medio=MEDIO, url='https://x/b.pdf')]\n"
         "FUERA = []" + expansion.bloque_fuera({"yucatan/codigo-penal": 'Motivo "con comillas".'}), ns)
    assert [d.clave for d in ns["LEYES"]] == ["yucatan/codigo-civil"]
    assert [(d.clave, m) for d, m in ns["FUERA"]] == [("yucatan/codigo-penal", 'Motivo "con comillas".')]


def test_anotar(tmp_path, monkeypatch):
    lista = tmp_path / "pendientes.json"
    lista.write_text(json.dumps(_lista(("a", "pendiente", 3, {}), ("b", "pendiente", 1, {}))))
    monkeypatch.setattr(expansion, "LISTA", lista)
    expansion.main(["anotar", "--estado", "b", "--resultado", "egress", "--dominio", "b.gob.mx"])
    expansion.main(["anotar", "--estado", "a", "--resultado", "fallido", "--motivo", "no pasó"])
    d = {e["estado"]: e for e in json.loads(lista.read_text())["estados"]}
    assert d["b"]["situacion"] == "egress" and d["b"]["motivo"].startswith("necesita egress-mx: b.gob.mx")
    assert d["a"]["situacion"] == "agotado"
    expansion.main(["anotar", "--estado", "b", "--resultado", "publicado", "--leyes", "12"])
    d = {e["estado"]: e for e in json.loads(lista.read_text())["estados"]}
    assert d["b"]["situacion"] == "publicado" and d["b"]["leyes"] == 12 and "dominio" not in d["b"]
