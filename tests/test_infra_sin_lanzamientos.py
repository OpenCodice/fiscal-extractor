"""Ningún workflow ni script lanza corridas: el único lanzador es el supervisor.

Un paso que necesita que corra algo después lo pide: escribe `pedir=<JSON>` en
su salida y el job la expone como salida `pedir_*`. El job final `estado` sube
lo que declaró cada job (artefacto `cadena`), y el supervisor
(OpenCodice/supervisor) lo lee y lanza.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
WORKFLOWS = RAIZ / ".github" / "workflows"
ENCADENADOS = ("vigilar-fiscal.yml", "vigilar-federal.yml",
               "vigilar-leyes-estatales.yml", "expandir-estatales.yml")

LANZAMIENTO = re.compile(
    r"gh\s+workflow\s+run|gh\s+run\s+rerun|/dispatches|repository_dispatch|/rerun\b|createWorkflowDispatch")
SALIDA_DE_PASO = re.compile(r"^\$\{\{\s*steps\.([A-Za-z0-9_-]+)\.outputs\.pedir\s*\}\}$")


def _archivos():
    for carpeta in (RAIZ / ".github", RAIZ / "scripts"):
        for p in sorted(carpeta.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                yield p


def test_nada_lanza_corridas():
    hallados = []
    for p in _archivos():
        try:
            lineas = p.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        hallados += [f"{p.relative_to(RAIZ)}:{n}: {linea.strip()}"
                     for n, linea in enumerate(lineas, 1) if LANZAMIENTO.search(linea)]
    assert not hallados, "Un workflow no lanza: pide (salida `pedir_*`).\n" + "\n".join(hallados)


def test_ningun_job_puede_escribir_en_actions():
    for p in sorted(WORKFLOWS.glob("*.yml")):
        assert "actions: write" not in p.read_text(encoding="utf-8"), p.name


def _workflow(nombre):
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load((WORKFLOWS / nombre).read_text(encoding="utf-8"))


def _peticiones(nombre):
    """(job, salida, paso) de cada salida `pedir*` de un workflow."""
    for job, cuerpo in _workflow(nombre)["jobs"].items():
        pasos = {p["id"]: p for p in cuerpo.get("steps", []) if "id" in p}
        for salida, valor in (cuerpo.get("outputs") or {}).items():
            if salida.startswith("pedir"):
                m = SALIDA_DE_PASO.match(valor.strip())
                assert m, f"{nombre}: {job}.{salida} no es la salida `pedir` de un paso: {valor}"
                assert m.group(1) in pasos, f"{nombre}: {job}.{salida} nombra un paso que no existe: {m.group(1)}"
                yield job, salida, pasos[m.group(1)]


@pytest.mark.parametrize("nombre", ENCADENADOS)
def test_cada_peticion_sale_de_un_paso_que_la_escribe(nombre):
    for job, salida, paso in _peticiones(nombre):
        assert re.search(r"pedir=.*>>\s*\"\$GITHUB_OUTPUT\"", paso.get("run", "")), \
            f"{nombre}: el paso de {job}.{salida} no escribe `pedir=`"


@pytest.mark.parametrize("nombre", ENCADENADOS)
def test_cada_paso_que_pide_esta_expuesto_por_su_job(nombre):
    for job, cuerpo in _workflow(nombre)["jobs"].items():
        expuestos = {m.group(1) for v in (cuerpo.get("outputs") or {}).values()
                     if (m := SALIDA_DE_PASO.match(str(v).strip()))}
        for paso in cuerpo.get("steps", []):
            if "pedir=" in paso.get("run", ""):
                assert paso.get("id") in expuestos, \
                    f"{nombre}: el paso «{paso.get('name')}» de {job} pide y el job no lo expone"


def test_hay_peticiones_que_comprobar():
    pytest.importorskip("yaml")
    assert sum(len(list(_peticiones(n))) for n in ENCADENADOS) >= 8


@pytest.mark.parametrize("nombre", ENCADENADOS)
def test_las_peticiones_son_json_valido(nombre, tmp_path):
    """Ejecuta las líneas que escriben `pedir=` con valores difíciles."""
    if not shutil.which("jq") or not shutil.which("bash"):
        pytest.skip("sin jq o bash")
    dificil = 'nuevo-leon "x" $y \\ z'
    for job, salida, paso in _peticiones(nombre):
        lineas = [linea for linea in paso["run"].splitlines() if "pedir=" in linea]
        variables = set(re.findall(r'"\$([A-Za-z_]+)"', "\n".join(lineas))) - {"GITHUB_OUTPUT"}
        casos = [{v: dificil for v in variables}]
        if "clave" in variables:
            casos = [dict(casos[0], clave=c) for c in ("estado", "redeclarar")]
        for caso in casos:
            destino = tmp_path / f"{job}-{salida}-{caso.get('clave', '')}.txt"
            subprocess.run(["bash", "-euc", "\n".join(lineas)], check=True,
                           env={**os.environ, **caso, "GITHUB_OUTPUT": str(destino)})
            escritas = destino.read_text(encoding="utf-8").splitlines()
            assert len(escritas) == 1 and escritas[0].startswith("pedir="), escritas
            peticion = json.loads(escritas[0][len("pedir="):])
            assert set(peticion) == {"workflow", "inputs"}, peticion
            assert (WORKFLOWS / peticion["workflow"]).is_file(), peticion
            declarados = _workflow(peticion["workflow"])[True]["workflow_dispatch"]["inputs"]
            assert "origen" not in peticion["inputs"]
            for clave, valor in peticion["inputs"].items():
                assert clave in declarados, f"{nombre}: {job}.{salida} pide un input que no existe: {clave}"
                assert valor == dificil, peticion


@pytest.mark.parametrize("nombre", ENCADENADOS)
def test_estado_cierra_la_corrida_y_sube_la_cadena(nombre):
    jobs = _workflow(nombre)["jobs"]
    assert list(jobs)[-1] == "estado"
    estado = jobs["estado"]
    assert sorted(estado["needs"]) == sorted(j for j in jobs if j != "estado")
    assert "always()" in estado["if"]
    assert estado["permissions"] == {}
    assert re.fullmatch(r"estado pendiente=\[(false|\$\{\{.+&& 'true' \|\| 'false' \}\})\]", estado["name"])
    datos, subir = estado["steps"]
    assert datos["env"] == {"NEEDS": "${{ toJSON(needs) }}"}
    assert "${{" not in datos["run"] and "cadena.json" in datos["run"]
    assert subir["uses"].startswith("actions/upload-artifact@")
    assert subir["with"]["name"] == "cadena" and subir["with"]["path"] == "cadena.json"


@pytest.mark.parametrize("nombre", ("vigilar-fiscal.yml", "expandir-estatales.yml"))
def test_sin_tandas_no_hay_pendiente(nombre):
    """Cuándo lanzar la ronda lo decide el supervisor: la corrida no espera ni
    se declara pendiente."""
    assert _workflow(nombre)["jobs"]["estado"]["name"] == "estado pendiente=[false]"


@pytest.mark.parametrize("nombre", ENCADENADOS)
def test_el_titulo_lleva_todos_los_inputs_y_solo_esos(nombre):
    w = _workflow(nombre)
    declarados = list(w[True]["workflow_dispatch"]["inputs"])
    assert re.findall(r"(\w+)=\[\$\{\{ inputs\.(\w+) \}\}\]", w["run-name"]) == [(i, i) for i in declarados]
    texto = (WORKFLOWS / nombre).read_text(encoding="utf-8")
    assert set(re.findall(r"inputs\.(\w+)", texto)) <= set(declarados)
