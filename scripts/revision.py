#!/usr/bin/env python3
"""Revisión completa de un documento contra su PDF, por bloques, antes de su
alta.

Las compuertas deterministas (auditar, invariantes) comparan el texto contra
el propio PDF ya filtrado por el extractor, así que no ven un pie de página no
reconocido ni un artículo que absorbió a su vecino. Un documento nuevo, que se
publica entero de una vez, lo revisa además un agente completo: el texto se
parte en bloques de artículos consecutivos, cada uno con el texto crudo de las
páginas del PDF donde vive, y el documento solo se publica si todos los
bloques, tal como quedan al final, se revisaron sin hallazgos.

Cada bloque lleva la huella de su texto: si un arreglo del extractor cambia un
bloque ya revisado, su huella cambia y hay que revisarlo otra vez. El
resultado (fiel o con hallazgos) queda en `verificaciones/altas/*.jsonl` por
(documento, PDF, extractor), para no volver a pagar la revisión de lo mismo.

Uso:
  revision.py planear --repo R --documento D --pdf P --trabajo T
  revision.py cerrar  --repo R --documento D --pdf P --trabajo T [--extractor-dir E]
  revision.py previa  --documento D --pdf P [--extractor-dir E]

Este archivo existe idéntico en constitucion-extractor y en fiscal-extractor
(scripts/revision.py): cualquier cambio se hace en los dos.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trailers as tr  # noqa: E402

EXTRACTOR = Path(__file__).resolve().parent.parent
REGISTRO = EXTRACTOR / "verificaciones" / "altas"
CARACTERES_POR_BLOQUE = 30_000
# Tope de la revisión completa: unos 1.8 millones de caracteres de texto. Un
# documento mayor no se publica solo.
MAX_BLOQUES = 60


# ------------------------------------------------------------------ texto

def _norm(texto: str) -> str:
    """Solo letras y dígitos, en minúsculas y sin acentos: para encontrar un
    párrafo en el texto crudo de la página aunque cambien espacios y cortes."""
    t = unicodedata.normalize("NFKD", texto)
    return "".join(ch for ch in t.lower() if ch.isalnum())


def paginas(pdf: str, cache: Path | None = None) -> list[str]:
    if cache and cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    import pdfplumber
    with pdfplumber.open(pdf) as doc:
        res = [p.extract_text() or "" for p in doc.pages]
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    return res


def articulos(repo: str | Path, documento: str) -> list[tuple[str, str]]:
    """(clave, texto) de cada artículo, en el orden del índice del documento."""
    raiz = Path(repo)
    base = raiz / tr._dir_articulos(documento)
    idx = tr._json(tr.lector_fs(str(raiz)), tr._dir_metadata(documento) + "articulos.json") or {}
    orden = [a["clave"] for a in idx.get("articulos", []) if isinstance(a, dict) and a.get("clave")]
    existentes = {p.stem for p in base.glob("*.md")}
    claves = [c for c in orden if c in existentes] + sorted(existentes - set(orden))
    return [(c, (base / f"{c}.md").read_text(encoding="utf-8")) for c in claves]


def _primer_parrafo(texto: str) -> str:
    for p in texto.split("\n\n"):
        p = p.strip()
        if p and not p.startswith("#") and not re.match(r"^_.*_$", p, re.S):
            return p
    return texto.split("\n", 1)[0]


def ubicar(arts: list[tuple[str, str]], pags: list[str]) -> list[int]:
    """Página (1-base) donde empieza cada artículo: la primera, desde la del
    anterior, que contiene el principio de su primer párrafo."""
    norm = [_norm(p) for p in pags]
    res, actual = [], 0
    for _, texto in arts:
        aguja = _norm(_primer_parrafo(texto))[:60]
        encontrada = None
        if len(aguja) >= 12:
            for i in range(actual, len(norm)):
                if aguja in norm[i]:
                    encontrada = i
                    break
                # El párrafo empieza al final de esta página y sigue en la otra.
                if i + 1 < len(norm):
                    siguiente = norm[i + 1][:400]
                    if aguja in norm[i][-200:] + siguiente and aguja not in siguiente:
                        encontrada = i
                        break
        if encontrada is not None:
            actual = encontrada
        res.append(actual + 1)
    return res


# ------------------------------------------------------------------ bloques

def bloques(repo: str | Path, documento: str, pdf: str, trabajo: str | Path,
            caracteres: int | None = None) -> list[dict]:
    caracteres = caracteres or CARACTERES_POR_BLOQUE
    t = Path(trabajo)
    pags = paginas(pdf, t / "paginas.json")
    arts = articulos(repo, documento)
    inicio = ubicar(arts, pags)
    grupos: list[list[int]] = []
    tam = 0
    for i, (_, texto) in enumerate(arts):
        if not grupos or tam + len(texto) > caracteres:
            grupos.append([])
            tam = 0
        grupos[-1].append(i)
        tam += len(texto)
    res = []
    for n, g in enumerate(grupos):
        primera = inicio[g[0]]
        siguiente = inicio[grupos[n + 1][0]] if n + 1 < len(grupos) else len(pags)
        h = hashlib.sha256()
        for i in g:
            h.update(arts[i][0].encode() + b"\0" + arts[i][1].encode("utf-8") + b"\0")
        res.append({"id": f"b{n + 1:03d}", "claves": [arts[i][0] for i in g],
                    "paginas": [primera, max(primera, siguiente)], "huella": h.hexdigest()[:20]})
    return res


def escribir_bloques(repo, documento, pdf, trabajo, bls: list[dict]) -> None:
    t = Path(trabajo)
    pags = paginas(pdf, t / "paginas.json")
    textos = dict(articulos(repo, documento))
    for b in bls:
        a, z = b["paginas"]
        partes = [f"# Bloque {b['id']} de {documento} (huella {b['huella']})", "",
                  f"## Texto extraído ({len(b['claves'])} artículos)", ""]
        for c in b["claves"]:
            partes += [f"<<<< {c}.md", textos[c].rstrip("\n"), ">>>>", ""]
        partes += [f"## Texto crudo del PDF, páginas {a} a {z}", ""]
        for i in range(a, z + 1):
            partes += [f"---- página {i}", pags[i - 1], ""]
        b["archivo"] = str(t / f"bloque-{b['id']}.md")
        Path(b["archivo"]).write_text("\n".join(partes) + "\n", encoding="utf-8")


def veredictos(trabajo: str | Path) -> dict[str, dict]:
    """Bloques revisados, por huella, de todos los `veredicto*.json`."""
    res: dict[str, dict] = {}
    for p in sorted(Path(trabajo).glob("veredicto*.json")):
        try:
            v = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        for b in v.get("bloques", []):
            if isinstance(b, dict) and b.get("huella"):
                res[str(b["huella"])] = b
    return res


def planear(repo, documento, pdf, trabajo) -> dict:
    t = Path(trabajo)
    t.mkdir(parents=True, exist_ok=True)
    bls = bloques(repo, documento, pdf, t)
    hechos = veredictos(t)
    pendientes = [b for b in bls if b["huella"] not in hechos]
    escribir_bloques(repo, documento, pdf, t, pendientes)
    plan = {"documento": documento, "pdf": pdf, "pdf_sha256": tr.sha256_bytes(Path(pdf).read_bytes()),
            "bloques": bls, "pendientes": [b["id"] for b in pendientes],
            "archivos": {b["id"]: b["archivo"] for b in pendientes},
            "excede": len(bls) > MAX_BLOQUES}
    (t / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1) + "\n",
                                 encoding="utf-8")
    return plan


# ------------------------------------------------------------------ registro

def huella_extractor(extractor_dir: str | Path = EXTRACTOR) -> str:
    """El código que produce el texto (extractor/), tal como está en disco."""
    h = hashlib.sha256()
    raiz = Path(extractor_dir) / "extractor"
    for p in sorted(raiz.rglob("*.py")):
        h.update(p.relative_to(raiz).as_posix().encode() + b"\0" + p.read_bytes())
    return h.hexdigest()[:16]


def previa(documento: str, pdf_sha: str, extractor: str, registro=REGISTRO) -> dict | None:
    """Resultado de una revisión anterior del mismo documento, PDF y extractor."""
    d = Path(registro)
    res = None
    for archivo in sorted(d.glob("*.jsonl")) if d.is_dir() else []:
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            e = json.loads(linea) if linea.strip() else None
            if e and (e["documento"], e["pdf"], e["extractor"]) == (documento, pdf_sha, extractor):
                res = e
    return res


def cerrar(repo, documento, pdf, trabajo, extractor_dir=EXTRACTOR,
           registro=REGISTRO) -> tuple[bool, str]:
    """¿Todos los bloques del documento, tal como está, se revisaron sin
    hallazgos? Anota el resultado en el registro y en `trabajo/resultado.json`."""
    t = Path(trabajo)
    bls = bloques(repo, documento, pdf, t)
    hechos = veredictos(t)
    hallazgos, faltan, detalle = [], [], []
    for b in bls:
        v = hechos.get(b["huella"])
        if v is None:
            faltan.append(b["id"])
            continue
        for h in v.get("hallazgos") or []:
            hallazgos.append(f"{h.get('clave', b['id'])}: {str(h.get('nota', ''))[:200]}"
                             if isinstance(h, dict) else str(h)[:200])
            # Completos, no solo los cinco del motivo: de aquí parte el agente
            # que repara el extractor (scripts/agente/reparar.sh).
            detalle.append({"clave": str(h.get("clave", b["id"])) if isinstance(h, dict) else b["id"],
                            "nota": str(h.get("nota", "") if isinstance(h, dict) else h)[:600]})
    if not bls:
        # Sin artículos que revisar (una ruta mal mapeada, un build fallido) no
        # hay revisión, y no puede registrarse como fiel.
        motivo = "La revisión completa no encontró artículos que revisar."
    elif len(bls) > MAX_BLOQUES:
        motivo = (f"Demasiado extenso para la revisión completa automática "
                  f"({len(bls)} bloques; el tope es {MAX_BLOQUES}).")
    elif hallazgos:
        motivo = ("La revisión completa contra el PDF encontró defectos de extracción: "
                  + "; ".join(hallazgos[:5]) + (f" (y {len(hallazgos) - 5} más)" if len(hallazgos) > 5 else ""))
    elif faltan:
        motivo = f"La revisión completa contra el PDF no cubrió {len(faltan)} de {len(bls)} bloques."
    else:
        motivo = ""
    ok = not motivo
    sha = tr.sha256_bytes(Path(pdf).read_bytes())
    resultado = {"documento": documento, "pdf": sha, "extractor": huella_extractor(extractor_dir),
                 "resultado": "fiel" if ok else ("incompleta" if (faltan or not bls) and not hallazgos
                                                 else "hallazgos"),
                 "motivo": motivo, "bloques": len(bls), "fecha": date.today().isoformat(),
                 **({"hallazgos": detalle[:300]} if detalle else {})}
    (t / "resultado.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1) + "\n",
                                      encoding="utf-8")
    # Una revisión incompleta (se acabó el tiempo, el agente falló) no se
    # registra: la siguiente corrida la retoma.
    if resultado["resultado"] != "incompleta":
        d = Path(registro)
        d.mkdir(parents=True, exist_ok=True)
        nombre = documento.replace("/", "__")
        with (d / f"{resultado['fecha']}-{nombre}-{sha[:8]}.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(resultado, ensure_ascii=False, sort_keys=True) + "\n")
    return ok, motivo


# ------------------------------------------------------------------ CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for nombre in ("planear", "cerrar"):
        p = sub.add_parser(nombre)
        p.add_argument("--repo", required=True)
        p.add_argument("--documento", required=True)
        p.add_argument("--pdf", required=True)
        p.add_argument("--trabajo", required=True)
        p.add_argument("--extractor-dir", default=str(EXTRACTOR))
        p.add_argument("--registro", default=str(REGISTRO))
    pv = sub.add_parser("previa")
    pv.add_argument("--documento", required=True)
    pv.add_argument("--pdf", required=True)
    pv.add_argument("--extractor-dir", default=str(EXTRACTOR))
    pv.add_argument("--registro", default=str(REGISTRO))
    a = ap.parse_args(argv)
    if a.cmd == "previa":
        e = previa(a.documento, tr.sha256_bytes(Path(a.pdf).read_bytes()),
                   huella_extractor(a.extractor_dir), a.registro)
        print(json.dumps(e, ensure_ascii=False) if e else "")
        return 0
    if a.cmd == "planear":
        plan = planear(a.repo, a.documento, a.pdf, a.trabajo)
        print(f"{a.documento}: {len(plan['bloques'])} bloques, {len(plan['pendientes'])} por revisar"
              + (" (excede el tope)" if plan["excede"] else ""))
        return 0
    ok, motivo = cerrar(a.repo, a.documento, a.pdf, a.trabajo, a.extractor_dir, a.registro)
    print("✓ revisión completa sin hallazgos" if ok else f"✗ {motivo}")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
