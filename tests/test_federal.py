"""Registro y vigilancia del corpus federal, sin red ni PDF."""
import json
import subprocess

import pytest

from extractor import federal
from extractor.registro import Documento

FILA = """<tr><td>{n}</td><td><p><a href="ref/{slug}.htm"><b>
<font>{nombre}</font></b></a></p><p>DOF 07/02/1984</p></td>
<td>DOF 15/01/2026</td><td><a target="_blank" href="pdf/{pdf}">
<img src="imagenes/principal/pdf.png"></a><a href="doc/X.doc"></a></td></tr>"""


def indice(*filas):
    return "<table>" + "".join(FILA.format(n=i, slug=s, nombre=n, pdf=p)
                               for i, (s, n, p) in enumerate(filas)) + "</table>"


HTML = indice(
    ("cpeum", "CONSTITUCIÓN Política de los Estados Unidos Mexicanos", "CPEUM.pdf"),
    ("lgs", "LEY General de Salud", "LGS.pdf"),
    ("cff", "CÓDIGO Fiscal de la Federación", "CFF.pdf"),
    ("lsat", "LEY del Servicio de Administración Tributaria", "93_041218.pdf"),
    ("lcpro", "LEY de Capitalización del Procampo", "238.pdf"),
    ("lges", "LEY General de Educación Superior", "LGES_200421.pdf"),
)


def test_leer_indice():
    filas = federal.leer_indice(HTML)
    assert [f.slug for f in filas] == ["cpeum", "lgs", "cff", "lsat", "lcpro", "lges"]
    assert filas[1].pdf == "https://www.diputados.gob.mx/LeyesBiblio/pdf/LGS.pdf"
    assert filas[1].nombre == "LEY General de Salud"


def test_documentos_del_indice():
    docs = {d.clave: d for d in federal.documentos(HTML)}
    assert "cpeum" not in docs                       # vive en constitucion-mexicana
    assert docs["lgs"].etiqueta == "Ley General de Salud" and docs["lgs"].sigla == "LGS"
    assert docs["lcpro"].sigla == "LCPRO"            # PDF numérico: sigla del slug
    assert docs["lges"].sigla == "LGES"              # sin la fecha del nombre
    # Las leyes fiscales conservan clave y etiqueta del corpus fiscal.
    assert docs["cff"].etiqueta == "Código Fiscal de la Federación"
    assert docs["lsat"].url.endswith("pdf/93_041218.pdf")
    # Y se suman los reglamentos fiscales, que no están en el índice de leyes.
    assert {"rcff", "rlisr", "risat"} <= set(docs)


def _docs():
    return [Documento("lgs", "Ley General de Salud", "LGS", "ley", "articulado",
                      url="https://x/pdf/LGS.pdf"),
            Documento("lft", "Ley Federal del Trabajo", "LFT", "ley", "articulado",
                      url="https://x/pdf/LFT.pdf"),
            Documento("cpf", "Código Penal Federal", "CPF", "ley", "articulado",
                      url="https://x/pdf/CPF.pdf")]


CAB = {"etag": '"1"', "last_modified": "Thu, 19 Feb 2026 21:41:07 GMT", "bytes": 10}


def _fuentes(tmp_path, docs):
    (tmp_path / "fuentes.json").write_text(json.dumps({"documentos": docs}))


def test_planear_solo_lo_que_cambio(tmp_path):
    huella = federal.huella_extractor()
    _fuentes(tmp_path, [
        {"clave": "lgs", "url": "https://x/pdf/LGS.pdf", "estado": "incluida",
         "pdf": CAB, "extractor": huella},
        {"clave": "lft", "url": "https://x/pdf/LFT.pdf", "estado": "incluida",
         "pdf": {**CAB, "etag": '"viejo"'}, "extractor": huella},
    ])
    plan = federal.planear(tmp_path, _docs(), consultar=lambda _u: CAB, shards=2)
    assert {d["clave"]: d["motivo"] for d in plan["documentos"]} == {
        "lft": "pdf", "cpf": "nuevo"}
    assert sorted(sum(plan["shards"], [])) == ["cpf", "lft"]


def test_planear_cambio_de_extractor_reprocesa_todo(tmp_path):
    _fuentes(tmp_path, [{"clave": c, "url": f"https://x/pdf/{c.upper()}.pdf",
                         "estado": "incluida", "pdf": CAB, "extractor": "otra"}
                        for c in ("lgs", "lft", "cpf")])
    plan = federal.planear(tmp_path, _docs(), consultar=lambda _u: CAB)
    assert [d["motivo"] for d in plan["documentos"]] == ["extractor"] * 3


def test_planear_lote_limita_solo_las_altas(tmp_path):
    _fuentes(tmp_path, [{"clave": "lgs", "url": "https://x/pdf/LGS.pdf",
                         "estado": "incluida", "pdf": CAB, "extractor": "otra"}])
    plan = federal.planear(tmp_path, _docs(), lote=1, consultar=lambda _u: CAB)
    assert {d["clave"]: d["motivo"] for d in plan["documentos"]} == {
        "lgs": "extractor", "lft": "nuevo"}
    assert plan["nuevos_pendientes"] == 1


def test_excluida_no_se_reintenta_sin_motivo(tmp_path):
    huella = federal.huella_extractor()
    _fuentes(tmp_path, [{"clave": "lgs", "url": "https://x/pdf/LGS.pdf",
                         "estado": "excluida", "pdf": CAB, "extractor": huella}])
    plan = federal.planear(tmp_path, _docs()[:1], consultar=lambda _u: CAB)
    assert plan["documentos"] == []
    _fuentes(tmp_path, [{"clave": "lgs", "url": "https://x/pdf/LGS.pdf",
                         "estado": "excluida", "pdf": CAB, "extractor": "otra"}])
    plan = federal.planear(tmp_path, _docs()[:1], consultar=lambda _u: CAB)
    assert plan["documentos"][0]["motivo"] == "reintento"


# ------------------------------------------------------------------ cerrar

def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "lgs").mkdir()
    (tmp_path / "lgs" / "004.md").write_text("# Artículo 4o.\n\nTexto viejo.\n")
    (tmp_path / "metadata" / "lgs").mkdir(parents=True)
    (tmp_path / "metadata" / "lgs" / "articulos.json").write_text(json.dumps(
        {"documento": "lgs", "etiqueta": "Ley General de Salud", "sigla": "LGS",
         "tipo": "ley", "version": "2025-01-01", "num_articulos": 1, "articulos": []}))
    _fuentes(tmp_path, [{"clave": "lgs", "etiqueta": "Ley General de Salud",
                         "sigla": "LGS", "tipo": "ley", "url": "https://x/pdf/LGS.pdf",
                         "estado": "incluida", "pdf": CAB, "extractor": "h",
                         "alta": {"fecha": "2026-11-16", "via": "limpia"}}])
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "inicio")
    return tmp_path


def _plan(repo, docs):
    ruta = repo.parent / "plan.json"
    ruta.write_text(json.dumps({"huella": "h2", "documentos": docs, "shards": []}))
    return str(ruta)


def _d(clave, motivo):
    return {"clave": clave, "etiqueta": clave.upper(), "sigla": clave.upper(),
            "tipo": "ley", "parser": "articulado", "url": f"https://x/pdf/{clave}.pdf",
            "motivo": motivo}


R_OK = {"sha256": "s", "bytes": 1, "problemas": {}, "invariantes": [], "unidades": 3,
        "version": "2026-01-15"}


def test_cerrar_reforma_alta_y_exclusion(repo):
    (repo / "lgs" / "004.md").write_text("# Artículo 4o.\n\nTexto reformado.\n")
    (repo / "lft").mkdir()
    (repo / "lft" / "001.md").write_text("# Artículo 1o.\n\nUno.\n")
    (repo / "cpf").mkdir()
    (repo / "cpf" / "001.md").write_text("# Artículo 1o.\n\nMal.\n")
    plan = _plan(repo, [_d("lgs", "pdf"), _d("lft", "nuevo"), _d("cpf", "nuevo")])
    res = federal.cerrar(plan, str(repo), {
        "lgs": R_OK, "lft": R_OK,
        "cpf": {**R_OK, "problemas": {"cpf/001": [{"tipo": "no_literal"}]}}},
        reparacion={"reparados": ["lft"], "titulo": "arreglo"})
    assert res["reformas"] == [("lgs", "2026-01-15", ["4o"])]
    assert res["altas"] == ["lft"]
    assert [c for c, _ in res["excluidas"]] == ["cpf"]
    assert not (repo / "cpf").exists()               # lo excluido no se publica
    fuentes = {d["clave"]: d for d in json.loads((repo / "fuentes.json").read_text())["documentos"]}
    assert fuentes["cpf"]["estado"] == "excluida" and "cpf/001" in fuentes["cpf"]["motivo"]
    assert fuentes["lft"]["alta"]["via"] == "reparada"
    assert fuentes["lgs"]["alta"]["via"] == "limpia"     # se conserva el alta original
    assert res["asunto"].startswith("Reforma LGS (DOF 2026-01-15): art. 4o")
    assert "Alta de 1 ley federal: LFT" in res["asunto"]


def test_cerrar_conserva_lo_publicado_si_la_nueva_version_no_es_fiel(repo):
    (repo / "lgs" / "004.md").write_text("# Artículo 4o.\n\nTexto roto.\n")
    plan = _plan(repo, [_d("lgs", "pdf")])
    res = federal.cerrar(plan, str(repo), {"lgs": {**R_OK, "error": "la extracción falló"}})
    assert (repo / "lgs" / "004.md").read_text().endswith("Texto viejo.\n")
    assert [c for c, _ in res["retenidas"]] == ["lgs"]
    fuentes = json.loads((repo / "fuentes.json").read_text())["documentos"]
    assert fuentes[0]["estado"] == "incluida" and fuentes[0]["revision_pendiente"]
