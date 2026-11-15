"""Subcomandos `federal …`: la vigilancia del corpus de leyes federales.

    federal planear   --out REPO --plan plan.json [--doc X] [--lote N] [--shards N]
    federal extraer   --plan plan.json --out REPO --pdf-dir D --shard I --staging S
    federal integrar  --plan plan.json --staging S --out REPO --pdf-dir D --trabajo T
    federal reevaluar --plan plan.json --out REPO --pdf-dir D --trabajo T
    federal cerrar    --plan plan.json --out REPO --trabajo T

Ver federal.py para el porqué de cada paso.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from . import federal, registro


def _salida_gh(**pares) -> None:
    """Escribe outputs del paso de GitHub Actions, si se corre ahí."""
    ruta = os.environ.get("GITHUB_OUTPUT")
    if not ruta:
        return
    with open(ruta, "a", encoding="utf-8") as fh:
        for k, v in pares.items():
            fh.write(f"{k}={v}\n")


def _leer_json(ruta, defecto=None):
    p = Path(ruta)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else defecto


def _escribir_json(ruta, datos) -> None:
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    Path(ruta).write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")


def _cmd_planear(a) -> int:
    html = (Path(a.indice_html).read_text(encoding="latin-1") if a.indice_html
            else federal.leer_url(federal.INDICE))
    docs = federal.documentos(html)
    if len(docs) < 100:
        # Un índice casi vacío es una página rota, no 200 leyes abrogadas.
        print(f"✗ El índice trae solo {len(docs)} documentos: no se planea nada.")
        return 1
    plan = federal.planear(a.out, docs, solo=a.doc, lote=a.lote, shards=a.shards)
    _escribir_json(a.plan, plan)
    motivos: dict[str, int] = {}
    for d in plan["documentos"]:
        motivos[d["motivo"]] = motivos.get(d["motivo"], 0) + 1
    print(f"Índice: {len(docs)} documentos. A procesar: {len(plan['documentos'])} "
          f"{motivos or ''} en {len(plan['shards'])} grupos; "
          f"nuevos pendientes para otra tanda: {plan['nuevos_pendientes']}")
    _salida_gh(hay="true" if plan["documentos"] else "false",
               shards=json.dumps(list(range(len(plan["shards"])))),
               pendientes=plan["nuevos_pendientes"])
    return 0


def _copiar_doc(origen: Path, destino: Path, clave: str) -> None:
    for rel in (clave, f"metadata/{clave}"):
        if (destino / rel).exists():
            shutil.rmtree(destino / rel)
        if (origen / rel).exists():
            shutil.copytree(origen / rel, destino / rel)


def _cmd_extraer(a) -> int:
    registro.cargar(a.plan)
    plan = _leer_json(a.plan)
    claves = a.doc or plan["shards"][a.shard]
    res = federal.extraer(a.plan, a.out, a.pdf_dir, claves=claves)
    staging = Path(a.staging)
    for clave, r in res.items():
        if r.get("error_fuente") or r.get("sin_cambio"):
            continue
        _copiar_doc(Path(a.out), staging / "datos", clave)
        if not federal.es_fiel(r):
            # El agente necesitará el PDF (y su texto por página, que es lo caro).
            (staging / "pdfs").mkdir(parents=True, exist_ok=True)
            for ext in (".pdf", ".paginas.json"):
                f = Path(a.pdf_dir) / f"{clave}{ext}"
                if f.exists():
                    shutil.copy2(f, staging / "pdfs" / f.name)
    _escribir_json(staging / "resultados" / f"{a.shard}.json", res)
    return 0


def _cmd_integrar(a) -> int:
    staging, out, trabajo = Path(a.staging), Path(a.out), Path(a.trabajo)
    resultados: dict = {}
    for f in sorted((staging / "resultados").glob("*.json")):
        resultados.update(_leer_json(f))
    for clave, r in resultados.items():
        if not (r.get("error_fuente") or r.get("sin_cambio")):
            _copiar_doc(staging / "datos", out, clave)
    Path(a.pdf_dir).mkdir(parents=True, exist_ok=True)
    for f in (staging / "pdfs").glob("*") if (staging / "pdfs").exists() else []:
        shutil.copy2(f, Path(a.pdf_dir) / f.name)
    _escribir_json(trabajo / "resultados.json", resultados)
    fallas = {c: r for c, r in resultados.items()
              if not r.get("error_fuente") and not r.get("sin_cambio") and not federal.es_fiel(r)}
    _escribir_json(trabajo / "fallas.json", fallas)
    _escribir_json(trabajo / "base.json", {"con_problemas": {
        ref: p for r in fallas.values() for ref, p in (r.get("problemas") or {}).items()}})
    fieles = sum(1 for r in resultados.values() if federal.es_fiel(r))
    print(f"{len(resultados)} documentos procesados: {fieles} fieles, {len(fallas)} con "
          f"fallas{': ' + ', '.join(fallas) if fallas else ''}")
    _salida_gh(fallas="true" if fallas else "false")
    return 0


def _cmd_reevaluar(a) -> int:
    """Reconstruye y audita los documentos con fallas usando los PDF ya
    descargados (tras un arreglo del extractor)."""
    registro.cargar(a.plan)
    trabajo = Path(a.trabajo)
    resultados = _leer_json(trabajo / "resultados.json", {})
    claves = a.doc or list(_leer_json(trabajo / "fallas.json", {}))
    previos = {c: {} for c in claves}       # sin atajo de 'mismo PDF'
    nuevos = federal.extraer(a.plan, a.out, a.pdf_dir, claves=claves,
                             previos=previos, descargar_pdf=False)
    resultados.update(nuevos)
    _escribir_json(trabajo / "resultados.json", resultados)
    if a.json:
        _escribir_json(a.json, {"con_problemas": {
            ref: p for r in nuevos.values() for ref, p in (r.get("problemas") or {}).items()},
            "resultados": nuevos})
    return 0


def _cmd_cerrar(a) -> int:
    trabajo = Path(a.trabajo)
    resultados = _leer_json(trabajo / "resultados.json", {})
    reparacion = _leer_json(trabajo / "reparacion.json")
    res = federal.cerrar(a.plan, a.out, resultados, reparacion=reparacion)
    plan = _leer_json(a.plan)
    notas = (trabajo / "notas-agente.md").read_text(encoding="utf-8") \
        if (trabajo / "notas-agente.md").exists() else ""
    (trabajo / "pr.md").write_text(federal.cuerpo_pr(res, plan, resultados, notas),
                                   encoding="utf-8")
    _escribir_json(trabajo / "cierre.json", res)
    print(f"Asunto: {res['asunto']}")
    for k in ("altas", "excluidas", "retenidas", "fuentes_fallidas"):
        if res[k]:
            print(f"  {k}: {len(res[k])}")
    _salida_gh(asunto=res["asunto"].replace("\n", " "),
               fuentes_fallidas="true" if res["fuentes_fallidas"] else "false",
               retenidas="true" if res["retenidas"] else "false")
    return 0


def registrar(sub) -> None:
    fp = sub.add_parser("federal", help="vigilancia del corpus de leyes federales")
    fsub = fp.add_subparsers(dest="federal_cmd", required=True)

    sp = fsub.add_parser("planear", help="decide qué documentos reprocesar")
    sp.add_argument("--out", required=True, help="repo de datos (lee su fuentes.json)")
    sp.add_argument("--plan", required=True, help="dónde escribir el plan")
    sp.add_argument("--doc", action="append", help="solo estas claves")
    sp.add_argument("--lote", type=int, default=None,
                    help="máximo de documentos nuevos por corrida")
    sp.add_argument("--shards", type=int, default=12)
    sp.add_argument("--indice-html", default=None, help="índice ya descargado (pruebas)")
    sp.set_defaults(fn=_cmd_planear)

    sp = fsub.add_parser("extraer", help="descarga, construye y audita un grupo del plan")
    sp.add_argument("--plan", required=True)
    sp.add_argument("--out", required=True)
    sp.add_argument("--pdf-dir", required=True)
    sp.add_argument("--shard", type=int, default=0)
    sp.add_argument("--doc", action="append", help="en vez del grupo, estas claves")
    sp.add_argument("--staging", required=True, help="carpeta a subir como artefacto")
    sp.set_defaults(fn=_cmd_extraer)

    sp = fsub.add_parser("integrar", help="junta los grupos en el repo de datos")
    sp.add_argument("--plan", required=True)
    sp.add_argument("--staging", required=True)
    sp.add_argument("--out", required=True)
    sp.add_argument("--pdf-dir", required=True)
    sp.add_argument("--trabajo", required=True)
    sp.set_defaults(fn=_cmd_integrar)

    sp = fsub.add_parser("reevaluar", help="reconstruye y audita los documentos con fallas")
    sp.add_argument("--plan", required=True)
    sp.add_argument("--out", required=True)
    sp.add_argument("--pdf-dir", required=True)
    sp.add_argument("--trabajo", required=True)
    sp.add_argument("--doc", action="append")
    sp.add_argument("--json", default=None, help="auditoría resultante (formato de auditar)")
    sp.set_defaults(fn=_cmd_reevaluar)

    sp = fsub.add_parser("cerrar", help="decide altas, exclusiones y el commit")
    sp.add_argument("--plan", required=True)
    sp.add_argument("--out", required=True)
    sp.add_argument("--trabajo", required=True)
    sp.set_defaults(fn=_cmd_cerrar)
