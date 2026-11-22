"""La sesión del agente reparador (scripts/agente/reparar.sh): lo que recibe de
los intentos anteriores, los archivos que no puede escribir mientras trabaja y
la comprobación que corre antes de entregar, que es el mismo código de las
compuertas. Corre reparar.sh sobre una copia del extractor en un repo temporal,
con un `claude` simulado."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
import reparacion as rp  # noqa: E402

SHA = "a" * 64
RESULTADO = {"type": "result", "subtype": "success", "result": "veredicto escrito",
             "num_turns": 12, "duration_ms": 60000, "total_cost_usd": 3.5,
             "usage": {"input_tokens": 9, "output_tokens": 800},
             "modelUsage": {"modelo-grande": {"outputTokens": 800, "costUSD": 3.5}}}


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), "-c", "user.name=prueba",
                        "-c", "user.email=prueba@example.com", *args],
                       capture_output=True, text=True, check=True)
    return r.stdout


@pytest.fixture
def copia(tmp_path):
    """Un repo con el extractor y los scripts de este árbol y una sola prueba."""
    if shutil.which("git") is None:
        pytest.skip("sin git")
    repo = tmp_path / "extractor-copia"
    rastreados = subprocess.run(["git", "-C", str(RAIZ), "ls-files", "-z", "--", "extractor"],
                                capture_output=True, text=True).stdout.split("\0")
    if not any(rastreados):
        pytest.skip("este árbol no es un repo de git")
    for rel in filter(None, rastreados):
        if (RAIZ / rel).is_file():
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(RAIZ / rel, repo / rel)
    # Los scripts, tal como están en disco: son lo que se prueba.
    shutil.copytree(RAIZ / "scripts", repo / "scripts",
                    ignore=shutil.ignore_patterns("__pycache__"))
    (repo / "tests").mkdir()
    (repo / "tests" / "test_existente.py").write_text("def test_existente():\n    assert True\n",
                                                      encoding="utf-8")
    (repo / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "partida")

    trabajo = tmp_path / "agente"
    rep = trabajo / "reparacion"
    (rep / "pdfs").mkdir(parents=True)
    objetivo = {"corpus": "estatal", "grupo": "estructura", "intento": "2026-11-21T000000-abc123",
                "descripcion": "encabezados de estructura fuera de lugar", "otras": [],
                "leyes": [{"clave": "guanajuato/codigo-civil", "pdf_sha256": SHA, "intentos": 2,
                           "hallazgos": [{"clave": "012", "nota": "el capítulo quedó en el cuerpo",
                                          "categoria": "estructura"}],
                           "descartes": [{"intento": "i1", "fecha": "2026-11-20",
                                          "motivo": "guanajuato/codigo-civil: unidades con "
                                                    "problemas nuevos (guanajuato/codigo-civil/941)"}]}]}
    (rep / "objetivo.json").write_text(json.dumps(objetivo), encoding="utf-8")
    (rep / "registro.json").write_text('{"documentos": []}', encoding="utf-8")

    binarios = tmp_path / "bin"
    binarios.mkdir()
    for nombre in ("python", "python3"):
        (binarios / nombre).write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding="utf-8")
    (binarios / "pip").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    for p in binarios.iterdir():
        p.chmod(0o755)

    limpio = {k: v for k, v in os.environ.items()
              if not k.startswith(("GITHUB_", "REPARACION_", "AGENTE_", "SESION_", "PYTHON"))}
    env = {**limpio, "PATH": f"{binarios}{os.pathsep}{os.environ['PATH']}",
           "AGENTE_DIR": str(trabajo), "REPARACION_GATE": str(tmp_path / "gate"),
           "REPARACION_CORPUS": "estatal", "TMPDIR": str(tmp_path), "OUT": str(tmp_path / "datos")}

    def correr(fase: str, **extra):
        return subprocess.run(["bash", str(repo / "scripts" / "agente" / "reparar.sh"), fase],
                              capture_output=True, text=True, env={**env, **extra})

    def claude(cuerpo: str) -> None:
        (binarios / "claude").write_text("#!/usr/bin/env bash\n" + cuerpo, encoding="utf-8")
        (binarios / "claude").chmod(0o755)

    return repo, rep, correr, claude


def _escribible(p: Path) -> bool:
    return os.access(p, os.W_OK)


def _prueba_nueva(repo: Path) -> None:
    (repo / "tests" / "test_reparacion_nueva.py").write_text(
        "def test_reparacion_nueva():\n    assert True\n", encoding="utf-8")


# ------------------------------------------------------------------ intentos anteriores

def test_descartes_previos_del_mismo_pdf(tmp_path):
    reg = tmp_path / "reparaciones"
    reg.mkdir()

    def anotar(intento, documento, pdf, resultado, motivo=""):
        with (reg / f"{intento}.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"documento": documento, "pdf": pdf, "intento": intento,
                                 "resultado": resultado, "motivo": motivo,
                                 "fecha": f"2026-11-{intento[1:]}"}) + "\n")

    for n, motivo in enumerate(["uno", "dos\n  con   espacios", "x" * 900, "cuatro"], 11):
        anotar(f"i{n}", "q/ley", "pdf-1", "iniciado")
        anotar(f"i{n}", "q/ley", "pdf-1", "descartado", motivo)
    anotar("i15", "q/ley", "pdf-1", "iniciado")
    anotar("i15", "q/ley", "pdf-1", "publicado", "un arreglo que sí entró")
    anotar("i16", "q/ley", "pdf-2", "descartado", "de otro PDF")
    anotar("i17", "q/otra", "pdf-1", "descartado", "de otra ley")
    registros = rp.reparaciones.cargar(reg)
    previos = rp.descartes_previos("q/ley", "pdf-1", registros)
    assert [d["intento"] for d in previos] == ["i12", "i13", "i14"]
    assert previos[0] == {"intento": "i12", "fecha": "2026-11-12", "motivo": "dos con espacios"}
    assert len(previos[1]["motivo"]) == 301 and previos[1]["motivo"].endswith("…")
    assert rp.descartes_previos("q/ley", "pdf-3", registros) == []


def test_el_brief_trae_el_motivo_de_los_descartes_y_la_comprobacion(copia):
    repo, rep, correr, claude = copia
    claude(f"cat <<'JSON'\n{json.dumps(RESULTADO)}\nJSON\n")
    assert correr("agente").returncode == 0
    brief = (rep / "brief.md").read_text(encoding="utf-8")
    assert "intentos anteriores con este mismo PDF, descartados" in brief
    assert "2026-11-20: guanajuato/codigo-civil: unidades con problemas nuevos" in brief
    assert f"bash {repo}/scripts/agente/reparar.sh comprobar" in brief
    assert "__" not in brief.replace("__init__", "")


# ------------------------------------------------------------------ la sesión

@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root escribe sin permiso")
def test_pruebas_y_compuerta_de_solo_lectura_durante_la_sesion(copia):
    repo, rep, correr, claude = copia
    existente, verificar = repo / "tests" / "test_existente.py", repo / "extractor" / "verificar.py"
    antes = existente.read_bytes()
    claude(f'''cd "{repo}"
{{ echo "# cambio" >> tests/test_existente.py; }} 2>/dev/null && echo prueba >> "{rep}/escritos.txt"
{{ echo "# cambio" >> extractor/verificar.py; }} 2>/dev/null && echo verificar >> "{rep}/escritos.txt"
echo "def test_nueva(): pass" > tests/test_reparacion_nueva.py && echo nueva >> "{rep}/escritos.txt"
echo "# cambio" >> extractor/normalize.py && echo extractor >> "{rep}/escritos.txt"
echo "$REPARACION_PARTIDA" > "{rep}/partida.txt"
cat <<'JSON'
{json.dumps(RESULTADO)}
JSON
''')
    r = correr("agente")
    assert r.returncode == 0, r.stderr
    assert (rep / "escritos.txt").read_text(encoding="utf-8").split() == ["nueva", "extractor"]
    assert existente.read_bytes() == antes
    assert _escribible(existente) and _escribible(verificar)
    assert (rep / "partida.txt").read_text().strip() == _git(repo, "rev-parse", "HEAD").strip()
    # El registro de uso y el log de siempre.
    (uso,) = [json.loads(x) for x in (rep / "uso.jsonl").read_text(encoding="utf-8").splitlines()]
    assert uso["paso"] == "reparacion" and uso["grupo"] == "estructura"
    assert uso["documentos"] == ["guanajuato/codigo-civil"]
    assert (uso["tokens_salida"], uso["costo_usd"], uso["turnos"]) == (800, 3.5, 12)
    assert (rep / "agente.log").read_text(encoding="utf-8") == "veredicto escrito\n"
    assert "veredicto escrito" in r.stdout


def test_los_permisos_vuelven_aunque_la_sesion_truene(copia):
    repo, rep, correr, claude = copia
    claude('echo "sin respuesta"\nkill -TERM "$PPID"\nexit 9\n')
    correr("agente")
    assert _escribible(repo / "tests" / "test_existente.py")
    assert _escribible(repo / "extractor" / "validate.py")
    # Y si aun así quedaran sin permiso, las compuertas lo devuelven.
    (repo / "tests" / "test_existente.py").chmod(0o444)
    assert correr("compuertas").returncode == 0
    assert _escribible(repo / "tests" / "test_existente.py")


# ------------------------------------------------------------------ comprobar

def _comprobar(correr, repo, rep):
    """Corre `comprobar` y exige que no decida nada ni cambie el arreglo."""
    estado = _git(repo, "status", "--porcelain", "-uall")
    diff = _git(repo, "diff")
    r = correr("comprobar", REPARACION_PARTIDA=_git(repo, "rev-parse", "HEAD~0").strip())
    assert _git(repo, "status", "--porcelain", "-uall") == estado
    assert _git(repo, "diff") == diff
    assert not any((rep / f).exists() for f in ("estado.txt", "descarte.txt", "cambian.txt",
                                                 "arreglo-descartado.patch"))
    assert _git(repo, "worktree", "list").count("\n") == 1
    return r


def _descarte(correr, repo, rep) -> str:
    """El motivo con el que las compuertas descartan ese mismo arreglo."""
    assert correr("compuertas").returncode == 0
    assert (rep / "estado.txt").read_text().strip() == "descartado"
    # Lo de fuera de extractor/ y tests/ lo deshace el paso del workflow.
    assert _git(repo, "status", "--porcelain", "-uall", "--", "extractor", "tests") == ""
    return (rep / "descarte.txt").read_text(encoding="utf-8").strip()


@pytest.mark.parametrize("arreglo, motivo", [
    (lambda repo: None, "el agente no cambió el extractor"),
    (lambda repo: (repo / "scripts" / "nota.txt").write_text("x"),
     "tocó archivos fuera de extractor/ y tests/: scripts/nota.txt"),
    (lambda repo: (repo / "extractor" / "verificar.py").open("a").write("# x\n"),
     "cambió extractor/verificar.py o extractor/validate.py, que son la compuerta"),
    (lambda repo: (repo / "tests" / "test_existente.py").open("a").write("# x\n"),
     "cambió pruebas existentes: tests/test_existente.py"),
    (lambda repo: (repo / "extractor" / "normalize.py").open("a").write("# x\n"),
     "no agregó una prueba nueva en tests/"),
    (lambda repo: ((repo / "extractor" / "normalize.py").open("a").write("# x\n"),
                   (repo / "tests" / "test_reparacion_rota.py").write_text(
                       "def test_rota():\n    assert False\n")),
     "las pruebas no pasan"),
    (lambda repo: ((repo / "extractor" / "reparaciones.py").open("a").write("# x\n"),
                   _prueba_nueva(repo)),
     "no cambia ningún archivo de la huella del extractor"),
])
def test_comprobar_dice_lo_mismo_que_las_compuertas(copia, arreglo, motivo):
    repo, rep, correr, _ = copia
    arreglo(repo)
    r = _comprobar(correr, repo, rep)
    assert r.returncode == 1
    assert f"NO PASA: {motivo}" in r.stdout
    assert _descarte(correr, repo, rep) == motivo.strip()


def test_comprobar_detecta_commits_y_llega_a_reconstruir_las_leyes(copia):
    repo, rep, correr, _ = copia
    partida = _git(repo, "rev-parse", "HEAD").strip()
    # Un arreglo con todo lo barato en orden llega hasta la reconstrucción de
    # las leyes, que aquí no tienen PDF.
    (repo / "extractor" / "normalize.py").open("a").write("# x\n")
    _prueba_nueva(repo)
    r = _comprobar(correr, repo, rep)
    assert r.returncode == 1
    assert "NO PASA: no cambia el texto de ninguna de las leyes con hallazgos" in r.stdout
    assert (rep / "comprobacion" / "antes" / "resultado.json").exists()
    assert (rep / "comprobacion" / "antes.sello").read_text().startswith(partida)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "commit del agente")
    r = correr("comprobar", REPARACION_PARTIDA=partida)
    assert r.returncode == 1 and "NO PASA: hizo commits en el extractor" in r.stdout
    assert _git(repo, "rev-parse", "HEAD").strip() != partida      # comprobar no deshace nada
    assert correr("compuertas", REPARACION_PARTIDA=partida).returncode == 0
    assert (rep / "descarte.txt").read_text().strip() == "hizo commits en el extractor"
    assert _git(repo, "rev-parse", "HEAD").strip() == partida
