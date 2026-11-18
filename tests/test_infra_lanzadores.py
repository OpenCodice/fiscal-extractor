"""Los lanzadores de corridas (scripts/lanzar_*.sh) frente a la cola de GitHub.

Se ejecutan con un `gh` falso en el PATH que registra cada llamada: `run list`
responde con el número de corridas en espera que diga la prueba (o falla) y
`workflow run` solo se anota.
"""
import os
import pathlib
import stat
import subprocess

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
VIGILANCIA = RAIZ / "scripts" / "lanzar_vigilancia_estatal.sh"
RONDA = RAIZ / "scripts" / "lanzar_ronda_expansion.sh"

GH_FALSO = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$GH_LLAMADAS"
if [ "$1 $2" = "run list" ]; then
  [ "$GH_COLA" = falla ] && { echo "error de red" >&2; exit 1; }
  echo "$GH_COLA"
  exit 0
fi
[ "$1 $2" = "workflow run" ] && [ "${GH_LANZAR:-}" = falla ] && exit 1
exit 0
"""


@pytest.fixture
def correr(tmp_path):
    binarios = tmp_path / "bin"
    binarios.mkdir()
    gh = binarios / "gh"
    gh.write_text(GH_FALSO, encoding="utf-8")
    gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
    llamadas = tmp_path / "llamadas.txt"

    def _correr(script, *args, cola="0", lanzar=""):
        llamadas.write_text("", encoding="utf-8")
        entorno = {**os.environ, "PATH": f"{binarios}{os.pathsep}{os.environ['PATH']}",
                   "GH_LLAMADAS": str(llamadas), "GH_COLA": cola, "GH_LANZAR": lanzar,
                   "GITHUB_REPOSITORY": "OpenCodice/fiscal-extractor", "LANZAR_ESPERA": "0"}
        r = subprocess.run(["bash", str(script), *args], env=entorno, capture_output=True, text=True)
        lineas = llamadas.read_text(encoding="utf-8").splitlines()
        return r, [l for l in lineas if l.startswith("workflow run")], [l for l in lineas if l.startswith("run list")]

    return _correr


def test_vigilancia_cola_vacia_lanza_solo_los_estados(correr):
    r, lanzadas, _ = correr(VIGILANCIA, "jalisco colima", "-f", "origen=reparar")
    assert r.returncode == 0, r.stderr
    assert lanzadas == ["workflow run vigilar-leyes-estatales.yml -R OpenCodice/fiscal-extractor "
                        "--ref main -f estados=jalisco colima -f origen=reparar"]


def test_vigilancia_con_una_en_espera_lanza_la_completa(correr):
    r, lanzadas, _ = correr(VIGILANCIA, "jalisco", "-f", "origen=ronda", cola="1")
    assert r.returncode == 0, r.stderr
    assert lanzadas == ["workflow run vigilar-leyes-estatales.yml -R OpenCodice/fiscal-extractor "
                        "--ref main -f origen=ronda"]


def test_vigilancia_si_no_puede_mirar_la_cola_lanza_la_completa(correr):
    r, lanzadas, _ = correr(VIGILANCIA, "jalisco", "-f", "origen=reparar", cola="falla")
    assert r.returncode == 0, r.stderr
    assert lanzadas == ["workflow run vigilar-leyes-estatales.yml -R OpenCodice/fiscal-extractor "
                        "--ref main -f origen=reparar"]
    assert "::warning::" in r.stdout


def test_vigilancia_completa_no_depende_de_la_cola(correr):
    for cola in ("0", "1", "falla"):
        r, lanzadas, _ = correr(VIGILANCIA, "", "-f", "reintento=true", "-f", "origen=salud", cola=cola)
        assert r.returncode == 0, r.stderr
        assert lanzadas == ["workflow run vigilar-leyes-estatales.yml -R OpenCodice/fiscal-extractor "
                            "--ref main -f reintento=true -f origen=salud"]


def test_vigilancia_falla_si_no_logra_lanzar(correr):
    r, _, _ = correr(VIGILANCIA, "jalisco", lanzar="falla")
    assert r.returncode != 0


def test_ronda_cola_vacia_lanza(correr):
    r, lanzadas, _ = correr(RONDA, "-f", "estado=colima", "-f", "origen=codigo")
    assert r.returncode == 0, r.stderr
    assert lanzadas == ["workflow run expandir-estatales.yml -R OpenCodice/fiscal-extractor "
                        "--ref main -f estado=colima -f origen=codigo"]


def test_ronda_con_una_en_espera_no_lanza(correr):
    r, lanzadas, _ = correr(RONDA, "-f", "redeclarar=colima", "-f", "origen=codigo", cola="1")
    assert r.returncode == 0, r.stderr
    assert lanzadas == []
    assert "no se lanza" in r.stdout


def test_ronda_si_no_puede_mirar_la_cola_reintenta_y_lanza(correr):
    r, lanzadas, miradas = correr(RONDA, "-f", "estado=colima", "-f", "origen=ronda", cola="falla")
    assert r.returncode == 0, r.stderr
    assert len(miradas) == 3
    assert lanzadas == ["workflow run expandir-estatales.yml -R OpenCodice/fiscal-extractor "
                        "--ref main -f estado=colima -f origen=ronda"]
    assert "::warning::" in r.stdout


def test_ronda_falla_si_no_logra_lanzar(correr):
    r, _, _ = correr(RONDA, "-f", "estado=colima", lanzar="falla")
    assert r.returncode != 0
