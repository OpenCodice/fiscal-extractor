import importlib.util
import json
import subprocess
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "scripts" / "commits_por_documento.py"
_spec = importlib.util.spec_from_file_location("commits_por_documento", _MOD)
cpd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cpd)


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, text=True).stdout


def test_agrupar():
    por_doc, resto = cpd.agrupar(
        ["lgs/001.md", "metadata/lgs/articulos.json", "lft/002.md", "fuentes.json", "README.md"],
        {"lgs", "lft"})
    assert por_doc == {"lgs": ["lgs/001.md", "metadata/lgs/articulos.json"], "lft": ["lft/002.md"]}
    assert resto == ["fuentes.json", "README.md"]


def test_un_commit_por_documento(tmp_path):
    r = tmp_path / "datos"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@t")
    _git(r, "config", "user.name", "t")
    (r / "README.md").write_text("x")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "base")
    for f, t in {"lgs/001.md": "a", "metadata/lgs/i.json": "{}", "lft/002.md": "b",
                 "fuentes.json": "{}"}.items():
        (r / f).parent.mkdir(parents=True, exist_ok=True)
        (r / f).write_text(t)
    asuntos = tmp_path / "a.json"
    asuntos.write_text(json.dumps({"lgs": "Reforma LGS (DOF 2026-01-01): art. 1"}))
    cpd.main(str(r), str(asuntos), "Registro de fuentes al día")
    log = _git(r, "log", "--format=%s|", "--name-only").split("\n")
    assert _git(r, "log", "-1", "--format=%s", "--", "lgs").strip() == "Reforma LGS (DOF 2026-01-01): art. 1"
    assert _git(r, "log", "-1", "--format=%s", "--", "lft").strip() == "Actualización de lft"
    assert _git(r, "log", "-1", "--format=%s", "--", "fuentes.json").strip() == "Registro de fuentes al día"
    assert _git(r, "show", "--name-only", "--format=", "HEAD~2").split() == ["lft/002.md"]
    assert not _git(r, "status", "--porcelain")
