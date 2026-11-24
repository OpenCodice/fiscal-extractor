"""Registro de uso de las sesiones del agente (scripts/uso.py y
scripts/agente/sesion.sh): cada sesión deja una línea en uso.jsonl, y esa
telemetría nunca cambia lo que la sesión imprime ni su código de salida."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
import uso  # noqa: E402

RESULTADO = {
    "type": "result", "subtype": "success", "is_error": False, "result": "listo",
    "num_turns": 7, "duration_ms": 120000, "duration_api_ms": 90000,
    "session_id": "s-1", "total_cost_usd": 1.25,
    "usage": {"input_tokens": 10, "output_tokens": 200, "cache_read_input_tokens": 3000,
              "cache_creation_input_tokens": 400},
    "modelUsage": {
        "modelo-chico": {"inputTokens": 5, "outputTokens": 20, "costUSD": 0.01},
        "modelo-grande": {"inputTokens": 5, "outputTokens": 180, "cacheReadInputTokens": 3000,
                          "cacheCreationInputTokens": 400, "costUSD": 1.24},
    },
}


def test_uso_del_resultado_del_cli():
    u = uso.uso_de(uso.resultado_del_cli(json.dumps(RESULTADO)))
    assert u["modelo"] == "modelo-grande"
    assert (u["tokens_entrada"], u["tokens_salida"]) == (10, 200)
    assert (u["tokens_cache_lectura"], u["tokens_cache_escritura"]) == (3000, 400)
    assert (u["costo_usd"], u["turnos"], u["duracion_ms"]) == (1.25, 7, 120000)
    assert u["resultado"] == "success" and u["sesion"] == "s-1"
    assert u["modelos"]["modelo-chico"]["tokens_salida"] == 20


def test_lee_una_lista_o_un_stream_y_tolera_lo_ilegible():
    lista = json.dumps([{"type": "system"}, RESULTADO])
    stream = "\n".join(json.dumps(x) for x in ({"type": "assistant"}, RESULTADO))
    assert uso.resultado_del_cli(lista)["num_turns"] == 7
    assert uso.resultado_del_cli(stream)["num_turns"] == 7
    for basura in ("", "Error: Reached max turns (200)", "[1, 2]", '"texto"', "null"):
        assert uso.resultado_del_cli(basura) is None
    vacio = uso.uso_de(None)
    assert set(vacio) == set(uso.uso_de(RESULTADO)) and all(v is None for v in vacio.values())
    # Tipos inesperados no pasan al registro como números.
    raro = uso.uso_de({"usage": {"input_tokens": "muchos", "output_tokens": True},
                       "modelUsage": ["x"], "total_cost_usd": None, "subtype": 3})
    assert all(v is None for v in raro.values())


def _registrar(tmp_path, crudo: str, *extra):
    (tmp_path / "crudo.json").write_text(crudo, encoding="utf-8")
    r = subprocess.run([sys.executable, "-I", str(RAIZ / "scripts" / "uso.py"), "registrar",
                        "--uso", str(tmp_path / "t" / "uso.jsonl"), "--paso", "reparacion",
                        "--documentos", "jalisco/codigo-civil lgs", "--grupo", "estructura",
                        "--crudo", str(tmp_path / "crudo.json"), "--codigo", "0",
                        "--segundos", "121", *extra], capture_output=True, text=True)
    lineas = (tmp_path / "t" / "uso.jsonl").read_text(encoding="utf-8").splitlines()
    return r, [json.loads(x) for x in lineas]


def test_registrar_anota_una_linea_e_imprime_el_texto_final(tmp_path):
    r, lineas = _registrar(tmp_path, json.dumps(RESULTADO))
    assert r.returncode == 0 and r.stdout == "listo\n"
    (e,) = lineas
    assert e["paso"] == "reparacion" and e["grupo"] == "estructura"
    assert e["documentos"] == ["jalisco/codigo-civil", "lgs"]
    assert e["tokens_salida"] == 200 and e["costo_usd"] == 1.25 and e["segundos"] == 121
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", e["fecha"])
    r, lineas = _registrar(tmp_path, json.dumps(RESULTADO), "--callado")
    assert r.stdout == "" and len(lineas) == 2


def test_registrar_sin_uso_legible_anota_null_y_no_falla(tmp_path):
    r, lineas = _registrar(tmp_path, "Error: Reached max turns (200)\n")
    assert r.returncode == 0
    # Lo que el CLI haya impreso no se pierde: va al log como antes.
    assert r.stdout == "Error: Reached max turns (200)\n"
    assert lineas[0]["paso"] == "reparacion" and lineas[0]["tokens_salida"] is None
    assert lineas[0]["modelo"] is None and lineas[0]["codigo"] == 0
    # Sin respuesta final (se acabaron los turnos): el uso sí se anota.
    sin_final = {k: v for k, v in RESULTADO.items() if k != "result"} | {"subtype": "error_max_turns"}
    r, lineas = _registrar(tmp_path, json.dumps(sin_final))
    assert "error_max_turns" in r.stdout and lineas[1]["turnos"] == 7
    # Ni un archivo ausente ni un destino imposible hacen fallar el paso.
    r = subprocess.run([sys.executable, "-I", str(RAIZ / "scripts" / "uso.py"), "registrar",
                        "--uso", str(tmp_path / "crudo.json" / "uso.jsonl"), "--paso", "x",
                        "--crudo", str(tmp_path / "no-existe")], capture_output=True, text=True)
    assert r.returncode == 0


def test_resumir_por_paso(tmp_path):
    a, b = tmp_path / "uso.jsonl", tmp_path / "impacto" / "uso.jsonl"
    b.parent.mkdir()
    base = uso.linea("reparacion", ["lgs"], "estructura", RESULTADO, 0, 120)
    a.write_text(json.dumps(base) + "\n" + "renglón roto\n"
                 + json.dumps(uso.linea("reparacion", ["lgs"], None, None, 1, 5)) + "\n",
                 encoding="utf-8")
    b.write_text(json.dumps(uso.linea("impacto", ["cff"], None, RESULTADO, 0, 60)) + "\n",
                 encoding="utf-8")
    filas = uso.resumen(uso.leer([str(a), str(b.parent), str(tmp_path / "no-existe")]))
    assert [f["paso"] for f in filas] == ["reparacion", "impacto", "Total"]
    rep, imp, total = filas
    assert (rep["sesiones"], rep["sin_uso"], rep["tokens_salida"], rep["costo_usd"]) == (2, 1, 200, 1.25)
    assert (total["sesiones"], total["tokens_salida"], total["costo_usd"]) == (3, 400, 2.5)
    r = subprocess.run([sys.executable, "-I", str(RAIZ / "scripts" / "uso.py"), "resumir",
                        str(tmp_path)], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.startswith("## Uso del agente")
    assert "| reparacion | 2 (1 sin registro de uso) | modelo-grande |" in r.stdout
    # Sin sesiones no escribe nada en el resumen del job.
    r = subprocess.run([sys.executable, "-I", str(RAIZ / "scripts" / "uso.py"), "resumir",
                        str(tmp_path / "no-existe")], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout == ""


def _claude_falso(bin_dir: Path, cuerpo: str) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    (bin_dir / "claude").write_text("#!/usr/bin/env bash\n" + cuerpo, encoding="utf-8")
    (bin_dir / "claude").chmod(0o755)
    (bin_dir / "python3").write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding="utf-8")
    (bin_dir / "python3").chmod(0o755)


def _sesion(tmp_path, cuerpo: str, entorno: dict | None = None):
    _claude_falso(tmp_path / "bin", cuerpo)
    (tmp_path / "brief.md").write_text("El encargo.\n", encoding="utf-8")
    guion = (f'source "{RAIZ}/scripts/agente/sesion.sh"\n'
             f'sesion_agente revision-alta "{tmp_path}/uso.jsonl" "{tmp_path}/brief.md" "lgs" '
             f'--max-turns 3 > "{tmp_path}/agente.log" 2> "{tmp_path}/agente.err"\n'
             'echo "rc=$?"\n')
    env = {k: v for k, v in os.environ.items() if k not in ("AGENTE_MODELO", "SESION_GRUPO", "SESION_CRUDO")}
    env |= {"PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}",
            "TMPDIR": str(tmp_path), **(entorno or {})}
    r = subprocess.run(["bash", "-c", guion], capture_output=True, text=True, env=env)
    lineas = [json.loads(x) for x in (tmp_path / "uso.jsonl").read_text(encoding="utf-8").splitlines()]
    return r, lineas


def test_sesion_pide_json_y_conserva_texto_y_codigo(tmp_path):
    cuerpo = (f'printf "%s\\n" "$@" > "{tmp_path}/args.txt"\n'
              'echo "aviso del CLI" >&2\n'
              f"cat <<'JSON'\n{json.dumps(RESULTADO)}\nJSON\n")
    r, (e,) = _sesion(tmp_path, cuerpo, {"AGENTE_MODELO": "modelo-grande",
                                           "SESION_CRUDO": str(tmp_path / "agente.json")})
    assert r.stdout == "rc=0\n"
    args = (tmp_path / "args.txt").read_text(encoding="utf-8").splitlines()
    assert args[:2] == ["-p", "El encargo."]
    assert args[2:] == ["--max-turns", "3", "--model", "modelo-grande", "--output-format", "json"]
    assert (tmp_path / "agente.log").read_text(encoding="utf-8") == "listo\n"
    assert (tmp_path / "agente.err").read_text(encoding="utf-8") == "aviso del CLI\n"
    assert e["paso"] == "revision-alta" and e["documentos"] == ["lgs"] and e["turnos"] == 7
    assert e["codigo"] == 0 and e["modelo"] == "modelo-grande"
    assert json.loads((tmp_path / "agente.json").read_text(encoding="utf-8"))["result"] == "listo"


def test_sesion_que_truena_devuelve_su_codigo_y_anota_null(tmp_path):
    r, (e,) = _sesion(tmp_path, 'echo "se cayó"\nexit 7\n')
    assert r.stdout == "rc=7\n"
    assert (tmp_path / "agente.log").read_text(encoding="utf-8") == "se cayó\n"
    assert e["codigo"] == 7 and e["tokens_salida"] is None and e["costo_usd"] is None
    assert not list(tmp_path.glob("sesion-agente.*"))


def test_todas_las_sesiones_pasan_por_la_funcion_comun():
    """Una invocación directa de `claude -p` no dejaría registro de uso."""
    directas = []
    for p in sorted((RAIZ / "scripts" / "agente").glob("*.sh")):
        texto = p.read_text(encoding="utf-8")
        if p.name != "sesion.sh" and re.search(r"^\s*[^#\n]*\bclaude\s+-p\b", texto, re.M):
            directas.append(p.name)
    assert not directas


def test_el_modelo_sale_del_paso_si_nadie_dice_otro(tmp_path):
    def modelo(paso: str) -> str:
        guion = f'source "{RAIZ}/scripts/agente/sesion.sh"\nmodelo_del_paso {paso}\n'
        return subprocess.run(["bash", "-c", guion], capture_output=True, text=True).stdout.strip()
    assert modelo("reparacion") == modelo("expansion-codigo") == "claude-opus-5-5"
    for paso in ("verificacion", "revision-alta", "auditoria-federal", "impacto", "expansion"):
        assert modelo(paso) == "claude-sonnet-5-5"
    cuerpo = (f'printf "%s\\n" "$@" > "{tmp_path}/args.txt"\n'
              f"cat <<'JSON'\n{json.dumps(RESULTADO)}\nJSON\n")
    _sesion(tmp_path, cuerpo)
    args = (tmp_path / "args.txt").read_text(encoding="utf-8").splitlines()
    assert args[args.index("--model") + 1] == "claude-sonnet-5-5"
