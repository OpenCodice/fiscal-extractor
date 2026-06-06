"""Invariantes deterministas del repo de datos fiscal — el gate de un PR.

Atrapa regresiones del parser / corrupción mejor que cualquier LLM: o se cumplen
los invariantes o no. Corre sobre el repo de datos YA construido (no re-parsea
PDF), leyendo `metadata/` y los `.md`. Sale con código != 0 si algo falla.

Por tipo de documento:
  - articulado: secuencia de artículos continua (sin huecos), sin colisiones,
    sin fugas de encabezado, fechas de reforma ISO, ningún cuerpo truncado.
  - reglas (RMF): número de cada regla CONSISTENTE con su contexto estructural
    (Título/Capítulo/Sección) — cierra el riesgo de citas tomadas como reglas;
    continuidad por sección (informativa) y conteo de anomalías.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .parsers.reglas import DOF_HEADER_RE, _ctx_prefijo, _consistente

# Marcas de encabezado/pie que NUNCA deben aparecer en el texto.
LEAK_MARKERS = ("CÁMARA DE DIPUTADOS", "Secretaría de Servicios")
FOOTER_RE = re.compile(r"^\d{1,4} de \d{1,4}$", re.MULTILINE)
MIN_BODY_CHARS = 8


def _items(idx: dict) -> list[dict]:
    return idx.get("articulos") or idx.get("reglas") or []


def _cuerpo(md_text: str) -> str:
    return md_text.split("\n", 2)[-1].strip()


def validar(data_repo: str) -> tuple[bool, list[tuple[bool, str, str]]]:
    repo = Path(data_repo)
    checks: list[tuple[bool, str, str]] = []

    def chk(ok: bool, label: str, detail: str = "") -> None:
        checks.append((bool(ok), label, detail))

    docs = json.loads((repo / "metadata" / "documentos.json")
                      .read_text(encoding="utf-8"))["documentos"]
    chk(bool(docs), "índice maestro no vacío", f"{len(docs)} documentos")

    for d in docs:
        clave, tipo = d["clave"], d["tipo"]
        idx = json.loads((repo / "metadata" / clave / "articulos.json")
                         .read_text(encoding="utf-8"))
        items = _items(idx)
        mds = sorted((repo / clave).glob("*.md"))

        # --- comunes a todo documento --------------------------------------
        chk(len(mds) == idx["num_articulos"] == len(items),
            f"[{clave}] índice == archivos == unidades",
            f"{len(mds)} md / {idx['num_articulos']} idx / {len(items)} items "
            "(¿colisión de claves?)")

        textos = {p.name: p.read_text(encoding="utf-8") for p in mds}
        fugas = [n for n, t in textos.items()
                 if any(m in t for m in LEAK_MARKERS) or FOOTER_RE.search(t)
                 or any(DOF_HEADER_RE.match(ln.strip()) for ln in t.splitlines())]
        chk(not fugas, f"[{clave}] sin fugas de encabezado/pie", ", ".join(fugas[:4]))

        truncados = [n for n, t in textos.items() if len(_cuerpo(t)) < MIN_BODY_CHARS]
        chk(not truncados, f"[{clave}] ningún cuerpo truncado", ", ".join(truncados[:4]))

        ref = json.loads((repo / "metadata" / clave / "reformas.json")
                         .read_text(encoding="utf-8"))
        malas = [f for f in ref if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", f)]
        chk(not malas, f"[{clave}] fechas de reforma ISO", ", ".join(malas[:4]))

        # --- específicos por tipo ------------------------------------------
        if tipo == "rmf":
            _validar_reglas(clave, idx, items, repo, chk)
        else:
            _validar_articulado(clave, items, chk)

    return all(c[0] for c in checks), checks


def _validar_articulado(clave: str, items: list[dict], chk) -> None:
    nums = sorted({a["articulo"] for a in items})
    if not nums:
        return
    huecos = [n for n in range(nums[0], nums[-1] + 1) if n not in set(nums)]
    chk(not huecos, f"[{clave}] secuencia de artículos continua",
        f"huecos: {huecos[:10]}" + (" …" if len(huecos) > 10 else ""))


def _validar_reglas(clave: str, idx: dict, items: list[dict], repo: Path, chk) -> None:
    # 1) cada número CONSISTENTE con su contexto (cierra el riesgo de citas).
    inconsistentes = []
    for r in items:
        prefijo = _ctx_prefijo(r.get("seccion", ""), r.get("capitulo", ""),
                               r.get("titulo", ""))
        if not _consistente(r["numero"], prefijo):
            inconsistentes.append(f"{r['numero']}∉{prefijo}")
    chk(not inconsistentes, f"[{clave}] reglas consistentes con su contexto",
        ", ".join(inconsistentes[:6]))

    # 2) continuidad por grupo padre (informativa: en la RMF hay reglas derogadas).
    grupos: dict[str, list[int]] = {}
    for r in items:
        partes = r["numero"].split(".")
        padre, hijo = ".".join(partes[:-1]), partes[-1]
        if hijo.isdigit():
            grupos.setdefault(padre, []).append(int(hijo))
    huecos_tot = 0
    for padre, hijos in grupos.items():
        hs = sorted(set(hijos))
        huecos_tot += sum(1 for n in range(hs[0], hs[-1] + 1) if n not in set(hs))
    chk(True, f"[{clave}] continuidad por sección (informativa)",
        f"{len(grupos)} grupos, {huecos_tot} huecos (normal: reglas derogadas)")

    # 3) anomalías registradas en el build (líneas ambiguas no tomadas como regla).
    anom_path = repo / "metadata" / clave / "anomalias.json"
    if anom_path.exists():
        anom = json.loads(anom_path.read_text(encoding="utf-8"))["anomalias"]
        riesgo = [a for a in anom if a["motivo"] == "cita_otra_rama_capitalizada"]
        # Estas el contexto ya las atrapó; si aparecieran, conviene revisar.
        chk(not riesgo, f"[{clave}] sin citas de otra rama capitalizadas coladas",
            f"{len(riesgo)}")
        minus = sum(1 for a in anom if a["motivo"] == "consistente_minuscula")
        chk(True, f"[{clave}] anomalías informativas",
            f"{len(anom)} total, {minus} 'consistente_minuscula' (revisar si crecen)")


def format_report(checks: list[tuple[bool, str, str]]) -> str:
    lines = []
    for ok, label, detail in checks:
        mark = "✓" if ok else "✗ FALLA"
        lines.append(f"  [{mark}] {label}" + (f"  — {detail}" if detail else ""))
    return "\n".join(lines)
