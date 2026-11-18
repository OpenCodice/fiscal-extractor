"""Lo que la ronda de expansión resuelve sin una persona (scripts/expansion.py):
los estados agotados que vuelven a la cola, el veredicto `codigo`, los
dominios que se agregan solos a egress-mx y la compuerta de declaraciones de
un arreglo de código."""
import datetime
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import expansion  # noqa: E402

HOY = datetime.date(2026, 11, 18)


def _lista(*estados, tope=3):
    return {"tope_intentos": tope, "estados": [
        {"estado": e, "situacion": s, "intentos": n, **extra} for e, s, n, extra in estados]}


def _semanas_antes(n):
    return (HOY - datetime.timedelta(weeks=n)).isoformat()


def _elegir(lista, huella="h2", estado=None):
    return expansion.elegir(lista, estado, set(), lambda s: False, huella, HOY)


# ------------------------------------------------------------ agotados

def test_un_agotado_vuelve_si_cambio_el_extractor_y_paso_el_plazo():
    lista = _lista(("a", "agotado", 3, {"agotado": {"fecha": _semanas_antes(5), "huella": "h1"}}))
    e = _elegir(lista)
    assert e["estado"] == "a" and e["situacion"] == "pendiente"
    # Vuelve con un solo intento más y sus intentos de código de nuevo.
    assert e["intentos"] == 2 and e["intentos_codigo"] == 0 and e["revivido"] == 1
    assert "cambió el extractor" in e["motivo"] and "agotado" not in e


def test_un_agotado_no_vuelve_cada_semana():
    # La misma huella, o muy pronto: sigue agotado.
    for agotado in ({"fecha": _semanas_antes(5), "huella": "h2"},
                    {"fecha": _semanas_antes(1), "huella": "h1"}):
        lista = _lista(("a", "agotado", 3, {"agotado": agotado}))
        assert _elegir(lista) is None
        assert lista["estados"][0]["situacion"] == "agotado"
    # Sin cambios en el extractor, vuelve tras SEMANAS_MAX.
    lista = _lista(("a", "agotado", 3, {"agotado": {"fecha": _semanas_antes(expansion.SEMANAS_MAX),
                                                    "huella": "h2"}}))
    assert _elegir(lista)["estado"] == "a"


def test_un_agotado_sin_registro_usa_su_ultimo_intento():
    lista = _lista(("a", "agotado", 3, {"ultimo_intento": _semanas_antes(6)}))
    assert _elegir(lista)["estado"] == "a"


def test_primero_los_que_nunca_se_agotaron():
    lista = _lista(("a", "agotado", 3, {"agotado": {"fecha": _semanas_antes(5), "huella": "h1"}}),
                   ("b", "pendiente", 0, {}))
    assert _elegir(lista)["estado"] == "b"
    assert lista["estados"][0]["situacion"] == "pendiente"


def test_llegar_al_tope_guarda_la_huella(tmp_path, monkeypatch):
    ruta = tmp_path / "pendientes.json"
    ruta.write_text(json.dumps(_lista(("a", "pendiente", 3, {}))))
    monkeypatch.setattr(expansion, "LISTA", ruta)
    expansion.main(["anotar", "--estado", "a", "--resultado", "fallido", "--motivo", "x"])
    e = json.loads(ruta.read_text())["estados"][0]
    assert e["situacion"] == "agotado"
    assert e["agotado"]["huella"] == expansion.huella_expansion() and e["agotado"]["fecha"]


def test_la_huella_no_incluye_los_modulos_de_los_estados(tmp_path):
    raiz = tmp_path
    (raiz / "extractor" / "estatales").mkdir(parents=True)
    (raiz / "extractor" / "fuentes.py").write_text("a = 1\n")
    (raiz / "extractor" / "estatales" / "__init__.py").write_text("")
    h = expansion.huella_expansion(raiz)
    (raiz / "extractor" / "estatales" / "yucatan.py").write_text("LEYES = []\n")
    assert expansion.huella_expansion(raiz) == h
    (raiz / "extractor" / "fuentes.py").write_text("a = 2\n")
    assert expansion.huella_expansion(raiz) != h


# ------------------------------------------------------------ codigo y egress

def _anotar(ruta, *args):
    expansion.main(["anotar", "--estado", "a", *args])
    return json.loads(ruta.read_text())["estados"][0]


def test_codigo_cuenta_sus_propios_intentos(tmp_path, monkeypatch):
    ruta = tmp_path / "pendientes.json"
    ruta.write_text(json.dumps({**_lista(("a", "pendiente", 1, {})), "tope_codigo": 2}))
    monkeypatch.setattr(expansion, "LISTA", ruta)
    salida = tmp_path / "salida"
    monkeypatch.setenv("GITHUB_OUTPUT", str(salida))
    e = _anotar(ruta, "--resultado", "codigo", "--motivo", "href con comillas simples")
    assert e["intentos_codigo"] == 1 and e["situacion"] == "pendiente"
    assert e["falta"] == "href con comillas simples" and "necesita código" in e["motivo"]
    assert salida.read_text().splitlines()[-1] == "codigo=true"
    # Descartado: el intento de la ronda sí cuenta.
    e = _anotar(ruta, "--resultado", "codigo-descartado", "--motivo", "las pruebas no pasan")
    assert e["intentos"] == 1 and "descartado: las pruebas no pasan" in e["motivo"]
    _anotar(ruta, "--resultado", "codigo", "--motivo", "otra vez")
    e = _anotar(ruta, "--resultado", "codigo", "--motivo", "y otra")
    assert e["intentos_codigo"] == 2 and "se agotaron" in e["motivo"]
    assert salida.read_text().splitlines()[-1] == "codigo=false"


def test_un_arreglo_publicado_devuelve_el_intento(tmp_path, monkeypatch):
    ruta = tmp_path / "pendientes.json"
    ruta.write_text(json.dumps(_lista(("a", "pendiente", 3, {}))))
    monkeypatch.setattr(expansion, "LISTA", ruta)
    e = _anotar(ruta, "--resultado", "codigo", "--motivo", "falta x")
    assert e["situacion"] == "agotado"
    e = _anotar(ruta, "--resultado", "codigo-publicado", "--motivo", "opción x")
    assert e["situacion"] == "pendiente" and e["intentos"] == 2 and "agotado" not in e
    assert e["intentos_codigo"] == 1
    assert expansion.elegir(json.loads(ruta.read_text()), "a", set(), lambda s: False)["estado"] == "a"


def test_egress_agregado_vuelve_a_la_cola_sin_gastar_el_intento(tmp_path, monkeypatch):
    ruta = tmp_path / "pendientes.json"
    ruta.write_text(json.dumps(_lista(("a", "pendiente", 3, {}))))
    monkeypatch.setattr(expansion, "LISTA", ruta)
    e = _anotar(ruta, "--resultado", "egress", "--agregado", "--dominio", "x.gob.mx")
    assert e["situacion"] == "pendiente" and e["intentos"] == 2
    assert e["motivo"].startswith("x.gob.mx agregado a egress-mx")
    e = _anotar(ruta, "--resultado", "egress", "--dominio", "x.gob.mx")
    assert e["situacion"] == "egress" and e["intentos"] == 1


def test_un_egress_ya_en_la_lista_vuelve_bajo_el_tope():
    lista = _lista(("a", "egress", 3, {"dominio": "x.gob.mx"}))
    e = expansion.elegir(lista, None, {"x.gob.mx"}, lambda s: False)
    assert e["estado"] == "a" and e["intentos"] == 2


@pytest.mark.parametrize("dominio,confiables,oficial", [
    ("www.congresoyucatan.gob.mx", set(), True),
    ("legislacion.edomex.gob.mx", set(), True),
    ("leyes.congresoqroo.mx", {"www.congresoqroo.mx"}, True),
    ("congresoqroo.mx", {"documentos.congresoqroo.mx"}, True),
    ("leyes.congreso.com.mx", {"www.congreso.com.mx"}, True),
    ("otro.com.mx", {"www.congreso.com.mx"}, False),
    ("congreso.mx", set(), False),
    ("congreso-gto.s3.amazonaws.com", {"congreso-gto.s3.amazonaws.com"}, False),
    ("congresomich.site", set(), False),
    ("gob.mx.evil.com", set(), False),
    ("10.0.0.1", set(), False),
    ("a..gob.mx", set(), False),
])
def test_dominio_oficial(dominio, confiables, oficial):
    assert bool(expansion.dominio_oficial(dominio, confiables)) is oficial


def test_egress_agregar(tmp_path):
    lista = tmp_path / "permitidos.json"
    lista.write_text(json.dumps({"_nota": "n", "dominios": ["www.congresoqroo.mx"]}))
    correr = lambda *a: expansion.main(["egress-agregar", "--json", str(lista), "--estado", "x", *a])
    assert correr("--dominio", "WWW.Congresoyuc.gob.mx.") == 0
    assert correr("--dominio", "leyes.congresoqroo.mx") == 0
    assert correr("--dominio", "leyes.ejemplo.mx", "--pista", "La constitución sale de https://www.ejemplo.mx/c.pdf.") == 0
    assert correr("--dominio", "www.congresoyuc.gob.mx") == 0
    assert correr("--dominio", "evil.com") == 3
    assert correr("--dominio", "otro.mx") == 3
    datos = json.loads(lista.read_text())
    assert datos["_nota"] == "n"
    assert datos["dominios"] == ["www.congresoqroo.mx", "www.congresoyuc.gob.mx",
                                 "leyes.congresoqroo.mx", "leyes.ejemplo.mx"]


# ------------------------------------------------------------ declaraciones

def test_declaraciones_sin_red_y_su_comparacion(tmp_path, monkeypatch):
    """La compuerta de un arreglo de código: el extractor de partida resuelve
    cada URL contra las páginas índice que descarga y las guarda; el arreglo
    las resuelve leyéndolas de ahí. Un cambio que no es opcional (otra URL u
    otra declaración) no pasa."""
    from extractor import fuentes
    from extractor.registro import Documento
    paginas = {"https://e.gob.mx/leyes": '<a href="cc-010126.pdf">x</a> <a href="cc-010226.pdf">y</a>'}
    docs = [Documento(clave="yucatan/codigo-civil", etiqueta="CC", sigla="CC", tipo="ley",
                      parser="articulado", indice="https://e.gob.mx/leyes", patron=r"cc-",
                      orden="ddmmaa", medio="DO"),
            Documento(clave="yucatan/sin-indice", etiqueta="SI", sigla="SI", tipo="ley",
                      parser="articulado", indice="https://caida.gob.mx/", patron="x", medio="DO")]
    monkeypatch.setattr(expansion, "_todas", lambda: docs)

    def leer_indice(url, via=None):
        if url not in paginas:
            raise OSError("sin red")
        return paginas[url]
    monkeypatch.setattr(fuentes, "_leer_indice", leer_indice)
    antes, idx = tmp_path / "antes.json", tmp_path / "idx.json"
    assert expansion.main(["declaraciones", "--salida", str(antes), "--indices", str(idx)]) == 0
    a = json.loads(antes.read_text())
    assert a["yucatan/codigo-civil"]["url"] == "https://e.gob.mx/cc-010226.pdf"
    assert a["yucatan/sin-indice"]["url"] == "error"
    # Con el arreglo, sin red: lee las páginas guardadas.
    monkeypatch.setattr(fuentes, "_leer_indice", lambda *a: (_ for _ in ()).throw(AssertionError("red")))
    despues = tmp_path / "despues.json"
    assert expansion.main(["declaraciones", "--salida", str(despues), "--leer-de", str(idx)]) == 0
    assert expansion.main(["declaraciones-iguales", str(antes), str(despues)]) == 0
    # Un arreglo que cambia qué PDF gana para lo ya declarado no pasa.
    monkeypatch.setattr(fuentes, "_elegir", lambda doc, c: sorted(c)[0])
    assert expansion.main(["declaraciones", "--salida", str(despues), "--leer-de", str(idx)]) == 0
    assert expansion.main(["declaraciones-iguales", str(antes), str(despues)]) == 1


def test_declaraciones_iguales_ignora_campos_vacios_nuevos(tmp_path):
    a = {"x": {"declaracion": {"clave": "x", "url": "u"}, "url": "u"}}
    (tmp_path / "a.json").write_text(json.dumps(a))
    (tmp_path / "b.json").write_text(json.dumps(a))
    assert expansion.main(["declaraciones-iguales", str(tmp_path / "a.json"), str(tmp_path / "b.json")]) == 0


def test_las_declaraciones_corren_sin_site_packages(tmp_path):
    """El extractor de partida corre `declaraciones` con python -I -S (con el
    token de egress-mx): no puede depender de nada instalado."""
    r = subprocess.run([sys.executable, "-I", "-S", "-c",
                        "import sys; sys.argv=['x']; sys.path.insert(0, sys.argv[0]);"
                        f"sys.path.insert(0, {str(expansion.RAIZ)!r});"
                        "from extractor import registro, fuentes; from extractor.estatales import documentos, fuera;"
                        "print(len(registro.DOCUMENTOS) + len(documentos()))"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert int(r.stdout) > 0
