"""Un commit por documento, con trailers calculados de la causa del cambio, y
validación de esos commits (scripts/commits_por_documento.py,
scripts/validar_commits.py)."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _cargar(nombre):
    spec = importlib.util.spec_from_file_location(nombre, _SCRIPTS / f"{nombre}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cpd = _cargar("commits_por_documento")
vc = _cargar("validar_commits")
tr = _cargar("trailers")


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True,
                          text=True).stdout


def _init(repo):
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")


# Extractor de juguete: el "PDF" es texto `clave|cuerpo` por línea más una línea
# `version|fecha`; la versión 2 del extractor corrige una errata de lectura.
_EXTRACTOR = '''
import json, sys
from pathlib import Path
a = sys.argv[1:]
if a[0] == "--registro":
    a = a[2:]
doc, pdf, out = a[a.index("--doc") + 1], a[a.index("--pdf") + 1], Path(a[a.index("--out") + 1])
lineas = [l.split("|", 1) for l in Path(pdf).read_text().splitlines() if l]
version = dict(lineas).pop("version")
d = out / doc
d.mkdir(parents=True, exist_ok=True)
for f in d.glob("*.md"):
    f.unlink()
reformas = {}
for clave, cuerpo in lineas:
    if clave == "version":
        continue
    CORREGIR
    (d / f"{clave}.md").write_text(f"# Artículo {int(clave)}\\n\\n{cuerpo}\\n")
    if "reformado" in cuerpo:
        reformas.setdefault(version, []).append(clave)
m = out / "metadata" / doc
m.mkdir(parents=True, exist_ok=True)
(m / "articulos.json").write_text(json.dumps({"documento": doc, "sigla": doc.upper(),
                                             "version": version, "articulos": []}))
(m / "reformas.json").write_text(json.dumps(reformas))
'''


@pytest.fixture
def entorno(tmp_path):
    ext = tmp_path / "extractor"
    _init(ext)
    (ext / "extractor").mkdir()
    (ext / "extractor" / "__init__.py").write_text("")
    (ext / "extractor" / "__main__.py").write_text(_EXTRACTOR.replace("CORREGIR", "pass"))
    _git(ext, "add", "-A")
    _git(ext, "commit", "-qm", "v1")
    v1 = _git(ext, "rev-parse", "HEAD").strip()
    (ext / "extractor" / "__main__.py").write_text(
        _EXTRACTOR.replace("CORREGIR", 'cuerpo = cuerpo.replace("lectrua", "lectura")'))
    _git(ext, "commit", "-qam", "v2")
    v2 = _git(ext, "rev-parse", "HEAD").strip()

    datos = tmp_path / "datos"
    _init(datos)
    pdfs = tmp_path / "pdfs"
    pdfs.mkdir()
    return {"ext": ext, "v1": v1, "v2": v2, "datos": datos, "pdfs": pdfs, "tmp": tmp_path}


def _construir(e, sha, doc, pdf_texto):
    pdf = e["pdfs"] / f"{doc}.pdf"
    pdf.write_text(pdf_texto)
    _git(e["ext"], "checkout", "-q", sha)
    subprocess.run([sys.executable, "-m", "extractor", "build", "--doc", doc, "--pdf", str(pdf),
                    "--out", str(e["datos"])], cwd=e["ext"], check=True,
                   env={"PYTHONPATH": str(e["ext"])})
    _git(e["ext"], "checkout", "-q", "main")
    return cpd.sha256(pdf)


def _publicar(e, docs: dict[str, tuple[str, str]]):
    """Estado publicado: cada documento construido con (extractor, PDF)."""
    entradas = []
    for doc, (sha, texto) in docs.items():
        pdf_sha = _construir(e, sha, doc, texto)
        entradas.append({"clave": doc, "version": "x", "pdf_sha256": pdf_sha,
                         "extractor_sha": sha})
    (e["datos"] / "metadata" / "documentos.json").write_text(
        json.dumps({"documentos": entradas}, indent=2) + "\n")
    _git(e["datos"], "add", "-A")
    _git(e["datos"], "commit", "-qm", "publicado")


def _correr(e):
    (e["pdfs"] / "descargas.json").write_text(json.dumps(
        {p.stem: f"https://x/{p.stem}.pdf" for p in e["pdfs"].glob("*.pdf")}))
    base = _git(e["datos"], "rev-parse", "HEAD").strip()
    cpd.main([str(e["datos"]), "--titulo-indice", "Índice del corpus fiscal y README al día",
              "--extractor-dir", str(e["ext"]), "--pdf-dir", str(e["pdfs"])])
    assert not _git(e["datos"], "status", "--porcelain")
    log = _git(e["datos"], "log", "--reverse", "--format=%H", f"{base}..HEAD").split()
    commits = [tr.parsear(_git(e["datos"], "log", "-1", "--format=%B", c)) for c in log]
    assert vc.main(str(e["datos"]), base) == 0
    return commits


def test_reforma_correccion_separacion_y_alta(entorno):
    e = entorno
    _publicar(e, {
        "cor": (e["v1"], "version|2026-01-01\n001|Una lectrua.\n"),
        "ref": (e["v2"], "version|2026-01-01\n001|Uno.\n002|Dos.\n"),
        "sep": (e["v1"], "version|2026-01-01\n001|Una lectrua.\n002|Dos.\n"),
    })
    # Nuevo estado: `cor` mismo PDF, extractor v2; `ref` otro PDF, mismo
    # extractor; `sep` otro PDF y otro extractor; `alt` es nuevo.
    _construir(e, e["v2"], "cor", "version|2026-01-01\n001|Una lectrua.\n")
    _construir(e, e["v2"], "ref", "version|2026-02-01\n001|Uno reformado.\n003|Tres.\n")
    _construir(e, e["v2"], "sep", "version|2026-03-01\n001|Una lectrua.\n002|Dos reformado.\n")
    _construir(e, e["v2"], "alt", "version|2026-04-01\n001|Nuevo.\n")
    commits = _correr(e)
    titulos = [t for t, _ in commits]
    v1, v2 = e["v1"][:7], e["v2"][:7]
    assert titulos == [
        "Alta de ALT",
        "Corrección de extracción COR: art. 1",
        "Reforma REF (DOF 2026-02-01): arts. 1, 2, 3",
        "Reforma SEP (DOF 2026-03-01): art. 2",
        "Corrección de extracción SEP: art. 1",
        "Índice del corpus fiscal y README al día",
    ]
    t = dict(commits[2][1])
    assert t["Articulos-Modificados"] == "001" and t["Articulos-Adicionados"] == "003"
    assert t["Articulos-Derogados"] == "002"                    # el archivo desapareció
    assert t["Publicacion-Origen"] == "notas" and t["Extractor"].endswith(v2)
    assert dict(commits[3][1])["Extractor"].endswith(v1)        # reforma con el extractor viejo
    assert dict(commits[4][1])["Extractor"].endswith(v2)
    assert dict(commits[5][1]) == {"Tipo": "indice", "Extractor": f"OpenCodice/fiscal-extractor@{v2}"}
    docs = {d["clave"]: d for d in json.loads(
        (e["datos"] / "metadata" / "documentos.json").read_text())["documentos"]}
    assert docs["sep"]["extractor_sha"] == e["v2"] and docs["cor"]["extractor_sha"] == e["v2"]
    assert docs["ref"]["pdf_sha256"] == cpd.sha256(e["pdfs"] / "ref.pdf")


def test_sin_extractor_anterior_no_se_separa(entorno):
    e = entorno
    _construir(e, e["v1"], "sep", "version|2026-01-01\n001|Una lectrua.\n")
    (e["datos"] / "metadata" / "documentos.json").write_text(
        json.dumps({"documentos": [{"clave": "sep", "version": "x"}]}))
    _git(e["datos"], "add", "-A")
    _git(e["datos"], "commit", "-qm", "publicado")
    _construir(e, e["v2"], "sep", "version|2026-03-01\n001|Una lectrua reformado.\n")
    (titulo, t), _ = _correr(e)
    assert titulo == "Reforma SEP (DOF 2026-03-01): art. 1"
    assert tr.valor(t, "Separacion") == "no-disponible"


def test_validar_commits_rechaza_un_commit_sin_trailers(entorno):
    e = entorno
    _publicar(e, {"ref": (e["v1"], "version|2026-01-01\n001|Uno.\n")})
    base = _git(e["datos"], "rev-parse", "HEAD").strip()
    _construir(e, e["v1"], "ref", "version|2026-02-01\n001|Uno reformado.\n")
    _git(e["datos"], "commit", "-qam", "Reforma REF (DOF 2026-02-01): art. 1")
    assert vc.main(str(e["datos"]), base) == 1


def test_agrupar():
    por_doc, resto = cpd.agrupar(
        ["lgs/001.md", "metadata/lgs/articulos.json", "lft/002.md", "fuentes.json", "README.md",
         "metadata/documentos.json"])
    assert por_doc == {"lgs": ["lgs/001.md", "metadata/lgs/articulos.json"], "lft": ["lft/002.md"]}
    assert resto == ["fuentes.json", "README.md", "metadata/documentos.json"]


def test_contexto_federal_reforma_y_retiro(entorno):
    e = entorno
    _publicar(e, {"lgs": (e["v2"], "version|2026-01-01\n001|Uno.\n"),
                  "lft": (e["v2"], "version|2026-01-01\n001|Uno.\n")})
    _construir(e, e["v2"], "lgs", "version|2026-02-01\n001|Uno reformado.\n")
    for ruta in ("lft", "metadata/lft"):
        subprocess.run(["rm", "-r", str(e["datos"] / ruta)], check=True)
    (e["datos"] / "fuentes.json").write_text("{}")
    ctx = e["tmp"] / "contexto.json"
    ctx.write_text(json.dumps({"build": {}, "documentos": {
        "lgs": {"fuente": "https://x/LGS.pdf", "sha256": "a" * 64, "pdf_cambio": True,
                "extractor_cambio": False, "extractor_sha": e["v2"]},
        "lft": {"motivo_retiro": "fuera del corpus", "extractor_sha": e["v2"]}}}))
    base = _git(e["datos"], "rev-parse", "HEAD").strip()
    cpd.main([str(e["datos"]), "--titulo-indice", "Registro de fuentes al día",
              "--extractor-dir", str(e["ext"]), "--contexto", str(ctx)])
    assert vc.main(str(e["datos"]), base) == 0
    titulos = _git(e["datos"], "log", "--reverse", "--format=%s", f"{base}..HEAD").splitlines()
    assert titulos == ["Retiro de LFT: fuera del corpus",
                       "Reforma LGS (DOF 2026-02-01): art. 1",
                       "Registro de fuentes al día"]
