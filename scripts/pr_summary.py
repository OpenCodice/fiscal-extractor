#!/usr/bin/env python3
"""Genera el cuerpo (markdown) del PR de actualización del corpus fiscal.

Lo usa el workflow de vigilancia: tras reconstruir el repo de datos, agrupa por
documento las unidades (artículos/reglas/criterios) cuyo texto cambió según git,
y arma un resumen legible para revisar.

Uso:  python pr_summary.py /ruta/al/repo-de-datos > cuerpo.md
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True).stdout


def cambios_por_documento(repo: Path) -> dict[str, list[str]]:
    """clave_documento → claves de unidad con cambios (modificadas/nuevas/borradas)."""
    status = _git(repo, "status", "--porcelain")
    por_doc: dict[str, list[str]] = defaultdict(list)
    for line in status.splitlines():
        path = line[3:].strip()
        if "->" in path:                       # renombrado: tomar el destino
            path = path.split("->")[-1].strip()
        if not path.endswith(".md"):
            continue
        p = Path(path)
        if len(p.parts) >= 2:                  # <documento>/<unidad>.md
            por_doc[p.parts[0]].append(p.stem)
    return {d: sorted(set(v)) for d, v in sorted(por_doc.items())}


def main(repo_arg: str) -> int:
    repo = Path(repo_arg)
    cambios = cambios_por_documento(repo)
    docs_idx = {d["clave"]: d for d in json.loads(
        (repo / "metadata" / "documentos.json").read_text(encoding="utf-8"))["documentos"]}

    total = sum(len(v) for v in cambios.values())
    print("## 🧾 Posible cambio en el corpus fiscal (detección automática)\n")
    print("Alguna fuente oficial (Cámara de Diputados / SAT) cambió respecto a la "
          "versión en este repositorio. Este PR se abrió automáticamente para revisión.\n")
    print(f"- **Documentos afectados:** {len(cambios)}")
    print(f"- **Unidades con cambios:** {total}\n")

    if cambios:
        print("| Documento | Unidades cambiadas | Versión |")
        print("|---|---|---|")
        for clave, unidades in cambios.items():
            d = docs_idx.get(clave, {})
            sigla = d.get("sigla", clave)
            ver = d.get("version", "—")
            muestra = ", ".join(unidades[:8]) + (" …" if len(unidades) > 8 else "")
            print(f"| {sigla} (`{clave}`) | {len(unidades)} — {muestra} | {ver} |")

    print("\n---\n")
    print("### Antes de aprobar")
    print("- Revisa el diff: debe corresponder a una reforma/actualización real "
          "(DOF / portal del SAT), no a un cambio del parser.")
    print("- Corre el validador:")
    print("```bash")
    print("python -m extractor validar --out .")
    print("```")
    print("\n_PR generado por el workflow `vigilar-fiscal`._")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("uso: pr_summary.py <repo-de-datos>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
