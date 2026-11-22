#!/usr/bin/env python3
"""Uso de las sesiones del agente (`claude -p`): una línea JSON por sesión.

`scripts/agente/sesion.sh` lanza cada sesión con `--output-format json` y pasa
aquí lo que el CLI devolvió. De ahí salen el modelo, los tokens, el costo, los
turnos y la duración, que se agregan a un `uso.jsonl` junto con el paso y los
documentos de la sesión.

Es telemetría y nada más: ninguna compuerta la lee, y nada de lo que pase aquí
cambia el resultado de un paso. Si la salida del CLI no se puede leer, la línea
se anota igual con sus campos en null; los dos comandos salen 0 siempre.

Uso:
  uso.py registrar --uso ARCHIVO --paso P --crudo SALIDA [--documentos "a b"]
                   [--grupo G] [--codigo N] [--segundos S] [--callado]
  uso.py resumir RUTA [RUTA …]     (archivos uso.jsonl o carpetas que los contengan)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

TOKENS = {"tokens_entrada": "input_tokens", "tokens_salida": "output_tokens",
          "tokens_cache_lectura": "cache_read_input_tokens",
          "tokens_cache_escritura": "cache_creation_input_tokens"}
POR_MODELO = {"tokens_entrada": "inputTokens", "tokens_salida": "outputTokens",
              "tokens_cache_lectura": "cacheReadInputTokens",
              "tokens_cache_escritura": "cacheCreationInputTokens", "costo_usd": "costUSD"}


def _numero(x, tipo=int):
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return tipo(x)


def resultado_del_cli(texto: str) -> dict | None:
    """El objeto `result` de la salida del CLI: el objeto único de
    `--output-format json`, el último de una lista o la última línea de un
    `stream-json`."""
    try:
        datos = json.loads(texto)
    except ValueError:
        datos = []
        for linea in texto.splitlines():
            try:
                datos.append(json.loads(linea))
            except ValueError:
                continue
    if isinstance(datos, dict):
        datos = [datos]
    if not isinstance(datos, list):
        return None
    for d in reversed(datos):
        if isinstance(d, dict) and (d.get("type") == "result" or "usage" in d):
            return d
    return None


def uso_de(r: dict | None) -> dict:
    """Los campos de uso de un resultado del CLI; null lo que no traiga."""
    r = r if isinstance(r, dict) else {}
    usage = r.get("usage") if isinstance(r.get("usage"), dict) else {}
    por_modelo = r.get("modelUsage") if isinstance(r.get("modelUsage"), dict) else {}
    modelos = {}
    for nombre, m in por_modelo.items():
        if isinstance(m, dict):
            modelos[str(nombre)] = {k: _numero(m.get(v), float if k == "costo_usd" else int)
                                    for k, v in POR_MODELO.items()}
    # El modelo de la sesión es el que más escribió; los demás son auxiliares.
    principal = max(modelos, key=lambda n: modelos[n]["tokens_salida"] or 0) if modelos else None
    subtipo = r.get("subtype")
    return {
        "modelo": principal,
        **{k: _numero(usage.get(v)) for k, v in TOKENS.items()},
        "costo_usd": _numero(r.get("total_cost_usd"), float),
        "turnos": _numero(r.get("num_turns")),
        "duracion_ms": _numero(r.get("duration_ms")),
        "duracion_api_ms": _numero(r.get("duration_api_ms")),
        "resultado": subtipo if isinstance(subtipo, str) else None,
        "sesion": r.get("session_id") if isinstance(r.get("session_id"), str) else None,
        "modelos": modelos or None,
    }


def linea(paso: str, documentos: list[str], grupo: str | None, r: dict | None,
          codigo: int | None, segundos: int | None) -> dict:
    return {
        "fecha": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "paso": paso, "documentos": documentos, "grupo": grupo or None,
        **uso_de(r),
        "codigo": codigo, "segundos": segundos,
        "corrida": os.environ.get("GITHUB_RUN_ID") or None,
        "job": os.environ.get("GITHUB_JOB") or None,
    }


def cmd_registrar(a) -> int:
    try:
        texto = Path(a.crudo).read_text(encoding="utf-8", errors="replace")
    except OSError:
        texto = ""
    r = None
    try:
        r = resultado_del_cli(texto)
    except Exception:                                 # noqa: BLE001 — telemetría
        pass
    if not a.callado:
        # Lo que la sesión imprimía sin `--output-format json`: su texto final.
        if r is not None and isinstance(r.get("result"), str):
            print(r["result"])
        elif r is not None:
            print(f"[sesión sin respuesta final: {r.get('subtype')}]")
        else:
            sys.stdout.write(texto)
    try:
        registro = linea(a.paso, a.documentos.split(), a.grupo, r, a.codigo, a.segundos)
    except Exception:                                 # noqa: BLE001 — telemetría
        registro = linea(a.paso, a.documentos.split(), a.grupo, None, a.codigo, a.segundos)
    try:
        destino = Path(a.uso)
        destino.parent.mkdir(parents=True, exist_ok=True)
        # Una sola escritura por línea: las revisiones corren varias a la vez.
        with destino.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(registro, ensure_ascii=False) + "\n")
    except OSError as e:
        print(f"· uso: no se pudo anotar la sesión ({e})", file=sys.stderr)
    return 0


def leer(rutas: list[str]) -> list[dict]:
    archivos: list[Path] = []
    for ruta in rutas:
        p = Path(ruta)
        if p.is_dir():
            archivos += sorted(p.rglob("uso.jsonl"))
        elif p.is_file():
            archivos.append(p)
    sesiones = []
    for archivo in archivos:
        for renglon in archivo.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                e = json.loads(renglon)
            except ValueError:
                continue
            if isinstance(e, dict):
                sesiones.append(e)
    return sesiones


CAMPOS = ("tokens_entrada", "tokens_salida", "tokens_cache_lectura", "tokens_cache_escritura",
          "costo_usd", "turnos", "duracion_ms")


def resumen(sesiones: list[dict]) -> list[dict]:
    """Una fila por paso, en orden de aparición, y la del total al final."""
    filas: dict[str, dict] = {}
    for e in sesiones:
        f = filas.setdefault(str(e.get("paso") or "?"),
                             {"sesiones": 0, "sin_uso": 0, "modelos": set(),
                              **{c: 0 for c in CAMPOS}})
        f["sesiones"] += 1
        if _numero(e.get("tokens_salida")) is None:
            f["sin_uso"] += 1
        if isinstance(e.get("modelo"), str):
            f["modelos"].add(e["modelo"])
        for c in CAMPOS:
            f[c] += _numero(e.get(c), float) or 0
    res = [{"paso": paso, **f} for paso, f in filas.items()]
    if len(res) > 1:
        total = {"paso": "Total", "sesiones": 0, "sin_uso": 0, "modelos": set(),
                 **{c: 0 for c in CAMPOS}}
        for f in res:
            total["modelos"] |= f["modelos"]
            for c in ("sesiones", "sin_uso", *CAMPOS):
                total[c] += f[c]
        res.append(total)
    return res


def _miles(n: float) -> str:
    return f"{int(n):,}".replace(",", " ")


def markdown(filas: list[dict]) -> str:
    if not filas:
        return ""
    lineas = ["## Uso del agente", "",
              "| Paso | Sesiones | Modelo | Entrada | Salida | Caché leída | Caché escrita "
              "| Turnos | Minutos | Costo equivalente (USD) |",
              "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|"]
    for f in filas:
        sesiones = str(f["sesiones"]) + (f" ({f['sin_uso']} sin registro de uso)" if f["sin_uso"] else "")
        lineas.append(
            f"| {f['paso']} | {sesiones} | {', '.join(sorted(f['modelos'])) or '—'} "
            f"| {_miles(f['tokens_entrada'])} | {_miles(f['tokens_salida'])} "
            f"| {_miles(f['tokens_cache_lectura'])} | {_miles(f['tokens_cache_escritura'])} "
            f"| {_miles(f['turnos'])} | {f['duracion_ms'] / 60000:.0f} | {f['costo_usd']:.2f} |")
    return "\n".join(lineas) + "\n"


def cmd_resumir(a) -> int:
    try:
        sys.stdout.write(markdown(resumen(leer(a.rutas))))
    except Exception as e:                            # noqa: BLE001 — telemetría
        print(f"· uso: no se pudo resumir ({type(e).__name__}: {e})", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("registrar")
    p.add_argument("--uso", required=True)
    p.add_argument("--paso", required=True)
    p.add_argument("--crudo", required=True)
    p.add_argument("--documentos", default="")
    p.add_argument("--grupo", default=None)
    p.add_argument("--codigo", type=int, default=None)
    p.add_argument("--segundos", type=int, default=None)
    p.add_argument("--callado", action="store_true",
                   help="no imprime el texto final de la sesión")
    p = sub.add_parser("resumir")
    p.add_argument("rutas", nargs="+")
    a = ap.parse_args(argv)
    return {"registrar": cmd_registrar, "resumir": cmd_resumir}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
