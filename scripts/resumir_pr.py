#!/usr/bin/env python3
"""Comentario asistido por LLM para un PR de reforma fiscal: resume y MARCA anomalías.

NO es un gate (de eso se encarga `extractor validar`). Es un asistente de
revisión: lee el diff de las unidades (artículos/reglas/criterios) que
cambiaron y produce un resumen en lenguaje llano, señalando con ⚠️ lo que
parezca corrupción/error de extracción en vez de una reforma coherente.
Imprime Markdown a stdout (el workflow lo publica como comentario del PR).

Uso:  OPENAI_API_KEY=... python resumir_pr.py <repo-datos> <base-ref> [modelo]
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

MAX_CHARS = 4000          # por unidad, para acotar tokens del diff
MAX_UNIDADES = 40         # una RMF nueva cambia cientos de reglas; el resumen
                          # detallado solo cubre las primeras N


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True).stdout


def _siglas(repo: Path) -> dict[str, str]:
    try:
        docs = json.loads((repo / "metadata" / "documentos.json")
                          .read_text(encoding="utf-8"))["documentos"]
        return {d["clave"]: d.get("sigla", d["clave"].upper()) for d in docs}
    except Exception:
        return {}


def diff_unidades(repo: Path, base: str) -> list[tuple[str, str]]:
    """[(etiqueta, diff_unificado)] de las unidades que cambiaron.

    Las unidades viven en `<documento>/<unidad>.md` en la raíz del repo de
    datos (metadata/ trae los derivados, no texto fuente). Usa el diff de git
    (líneas '-' quitadas, '+' agregadas): enfocado en EL cambio y mucho más
    eficiente en tokens que mandar la unidad completa.
    """
    siglas = _siglas(repo)
    out = []
    for path in _git(repo, "diff", "--name-only", base, "--", "*.md").splitlines():
        p = Path(path)
        if len(p.parts) != 2 or p.parts[0] == "metadata":
            continue
        etiqueta = f"{siglas.get(p.parts[0], p.parts[0].upper())} {p.stem}"
        diff = _git(repo, "diff", base, "--", path)
        # quitar el encabezado de git (diff --git, index, +++/---); dejar los hunks
        cuerpo = "\n".join(l for l in diff.splitlines()
                           if not l.startswith(("diff --git", "index ", "--- ", "+++ ")))
        out.append((etiqueta, cuerpo[:MAX_CHARS]))
    return out


def build_prompt(diffs: list[tuple[str, str]]) -> str:
    bloques = [f"[{etiqueta}]\n{diff}" for etiqueta, diff in diffs]
    cambios = "\n\n".join(bloques)
    return (
        "Eres un asistente que ayuda a revisar cambios al corpus fiscal mexicano "
        "(leyes, reglamentos, la Resolución Miscelánea Fiscal y criterios del SAT) "
        "en un Pull Request. Abajo está el DIFF (formato git: líneas que empiezan "
        "con '-' se quitaron, con '+' se agregaron) de cada unidad que cambió; la "
        "etiqueta indica el documento (sigla) y el artículo/regla/criterio.\n\n"
        "Tu tarea:\n"
        "1. Resume en lenguaje llano y breve QUÉ cambió en cada unidad (1-2 líneas).\n"
        "2. ⚠️ IMPORTANTE: si algún cambio parece un ERROR DE EXTRACCIÓN o corrupción "
        "(texto cortado, caracteres raros, pérdida de contenido, encabezados mezclados) "
        "en vez de una reforma/actualización coherente, márcalo con '⚠️ REVISAR' y "
        "explica por qué.\n\n"
        "Formato de salida (Markdown, consistente):\n"
        "- NO agregues un título de primer nivel ni de segundo (el comentario ya "
        "lleva encabezado).\n"
        "- Por cada unidad: una línea `**SIGLA unidad**` en negritas y, debajo, "
        "1-2 oraciones. Sin corchetes. Separa las unidades con una línea en blanco.\n\n"
        "Sé conciso. No inventes; básate solo en el diff dado.\n\n"
        f"DIFFS:\n{cambios}"
    )


def summarize(prompt: str, model: str) -> str:
    from openai import OpenAI
    client = OpenAI()
    resp = client.chat.completions.create(
        model=model, max_tokens=900,
        messages=[{"role": "user", "content": prompt}])
    return resp.choices[0].message.content or ""


def main(repo_arg: str, base: str, model: str = "gpt-4o-mini") -> int:
    repo = Path(repo_arg)
    diffs = diff_unidades(repo, base)
    if not diffs:
        print("_No hubo cambios de texto en artículos/reglas/criterios._")
        return 0
    recorte = len(diffs) - MAX_UNIDADES
    cuerpo = summarize(build_prompt(diffs[:MAX_UNIDADES]), model)
    print("## 🤖 Resumen asistido del cambio\n")
    print(cuerpo)
    if recorte > 0:
        print(f"\n_…y {recorte} unidades más sin resumen detallado "
              "(cambio masivo; revisa la tabla del PR)._")
    print("\n---\n> Generado por IA como **apoyo de revisión** (no es un gate ni "
          "fuente de cita). El gate real es el check `validar`. Revisa el diff.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("uso: resumir_pr.py <repo-datos> <base-ref> [modelo]", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(*sys.argv[1:4]))
