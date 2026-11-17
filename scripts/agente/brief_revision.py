#!/usr/bin/env python3
"""Brief de una sesión de la revisión completa de un alta: los bloques
pendientes del plan de `scripts/revision.py` (hasta POR_SESION), sobre
`brief-revision.md`. No escribe nada si no queda bloque por revisar o el
documento excede el tope (entonces la revisión no se completa y el documento no
se publica).

Uso: brief_revision.py REV N POR_SESION __CLAVE__=valor...
(`__BRIEF__=archivo.md` usa otro brief de scripts/agente/.)

Este archivo existe idéntico en constitucion-extractor y en fiscal-extractor.
"""
import json
import pathlib
import sys

rev, n, por = pathlib.Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
valores = dict(a.split("=", 1) for a in sys.argv[4:])
plan = json.loads((rev / "plan.json").read_text(encoding="utf-8"))
brief_p = rev / "brief.md"
brief_p.unlink(missing_ok=True)
if plan["excede"] or not plan["pendientes"]:
    sys.exit(0)
por_id = {b["id"]: b for b in plan["bloques"]}
lote = plan["pendientes"][:por]
lineas = [f"{len(plan['bloques'])} bloques en total; {len(plan['pendientes'])} por revisar; "
          f"en esta sesión, {len(lote)}:"]
for i in lote:
    b = por_id[i]
    lineas.append(f"{i} (huella {b['huella']}): {plan['archivos'][i]} — unidades {b['claves'][0]} "
                  f"a {b['claves'][-1]}, págs. {b['paginas'][0]} a {b['paginas'][1]}")
nombre = valores.pop("__BRIEF__", "brief-revision.md")
brief = (pathlib.Path(__file__).resolve().parent / nombre).read_text(encoding="utf-8")
valores.update({"__TRABAJO__": str(rev), "__VEREDICTO__": str(rev / f"veredicto-{n:02d}.json"),
                "__BLOQUES__": "\n".join(lineas)})
for k, v in valores.items():
    brief = brief.replace(k, v)
brief_p.write_text(brief, encoding="utf-8")
