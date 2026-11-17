#!/usr/bin/env python3
"""Impacto del extractor, tal como está en disco, sobre todo lo publicado.

Reconstruye cada documento publicado de fiscal-mexicano y de leyes-federales
desde el PDF exacto de su versión publicada (el sha256 que guardan
`metadata/documentos.json` y `fuentes.json`), compara unidad por unidad contra
el texto publicado (HEAD del repo de datos, no su árbol de trabajo) y deja en
`--trabajo` las correcciones que eso produciría y que el registro de
`scripts/impacto.py` aún no confirma (`pendientes.json`, para
`scripts/agente/impacto.sh`). En cada documento que cambia audita además la
cobertura antes y después: unidades nuevas con problemas son una regresión y
el cambio del extractor no puede entrar.

Los PDF no se versionan: se buscan por sha256 en `--pdf-dir` (los que ya
descargó la vigilancia) y en `--cache`, y si no, se descargan de su URL; si la
fuente ya publica otro PDF (hubo una reforma), ese documento no se puede medir
y queda anotado: su corrección la exige después la vigilancia.

Sale 0 si no queda nada por verificar ni hay regresiones, 1 si hay correcciones
por verificar, 2 si hay regresiones de cobertura, errores de extracción o
correcciones ya rechazadas.

Uso:
  impacto_corpus.py --trabajo T [--fiscal REPO] [--federal REPO] [--pdf-dir D]...
      [--cache C] [--solo DOC]...
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import impacto  # noqa: E402

EXTRACTOR = Path(__file__).resolve().parent.parent
ORG = "https://github.com/OpenCodice"


def _git(repo, *args, binario=False):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True)
    return r.stdout if binario else r.stdout.decode("utf-8")


def clonar(nombre: str, destino: Path) -> Path:
    if not (destino / ".git").exists():
        subprocess.run(["git", "clone", "-q", "--depth", "1", f"{ORG}/{nombre}.git", str(destino)],
                       check=True)
    return destino


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def documentos(fiscal: Path | None, federal: Path | None, trabajo: Path) -> list[dict]:
    """Cada documento publicado: repo, clave, URL, sha256 del PDF publicado y
    registro con el que se construye (None: el fiscal de registro.py)."""
    docs = []
    if fiscal:
        indice = json.loads(_git(fiscal, "show", "HEAD:metadata/documentos.json"))
        for e in indice["documentos"]:
            idx = json.loads(_git(fiscal, "show", f"HEAD:metadata/{e['clave']}/articulos.json"))
            docs.append({"repo": fiscal, "nombre": "fiscal-mexicano", "clave": e["clave"],
                         "url": idx.get("fuente"), "sha256": e.get("pdf_sha256"),
                         "registro": None})
    if federal:
        registro = trabajo / "fuentes.json"
        registro.write_bytes(_git(federal, "show", "HEAD:fuentes.json", binario=True))
        for e in json.loads(registro.read_text(encoding="utf-8"))["documentos"]:
            if e.get("estado") == "incluida":
                docs.append({"repo": federal, "nombre": "leyes-federales", "clave": e["clave"],
                             "url": e.get("url"), "sha256": (e.get("pdf") or {}).get("sha256"),
                             "registro": str(registro)})
    return docs


class PDFs:
    """PDF por sha256: de las carpetas dadas, de la caché o descargado."""

    def __init__(self, dirs: list[str], cache: Path):
        self.cache = cache
        cache.mkdir(parents=True, exist_ok=True)
        self.por_sha = {p.stem: str(p) for p in cache.glob("*.pdf")}
        for d in dirs:
            for p in Path(d).glob("*.pdf"):
                self.por_sha.setdefault(_sha256(p), str(p))

    def obtener(self, sha: str | None, url: str | None) -> str | None:
        if sha and sha in self.por_sha:
            return self.por_sha[sha]
        if not (sha and url):
            return None
        destino = self.cache / f"{sha}.pdf"
        tmp = self.cache / f"{sha}.descarga"
        try:
            sys.path.insert(0, str(EXTRACTOR))
            from extractor.fuentes import descargar
            descargar(url, str(tmp))
        except Exception:                            # noqa: BLE001 — sin PDF no se mide
            return None
        if _sha256(tmp) != sha:
            tmp.unlink(missing_ok=True)
            return None
        tmp.rename(destino)
        self.por_sha[sha] = str(destino)
        return str(destino)


def _exportar_publicado(repo: Path, clave: str, destino: Path) -> dict[str, bytes]:
    """Unidades y metadata publicadas (HEAD) del documento, en `destino`."""
    datos = _git(repo, "archive", "--format=tar", "HEAD", clave, f"metadata/{clave}", binario=True)
    with tarfile.open(fileobj=io.BytesIO(datos)) as tar:
        tar.extractall(destino, filter="data")
    return {p.stem: p.read_bytes() for p in (destino / clave).glob("*.md")}


def _extractor(args: list[str], registro: str | None) -> str | None:
    cmd = [sys.executable, "-m", "extractor"] + (["--registro", registro] if registro else []) + args
    r = subprocess.run(cmd, cwd=EXTRACTOR, capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": str(EXTRACTOR)})
    return None if r.returncode == 0 else (r.stderr.strip().splitlines() or ["?"])[-1][:300]


def _auditar(out: Path, pdf_dir: Path, registro: str | None) -> set[str] | None:
    salida = out / "auditoria.json"
    if _extractor(["auditar", "--out", str(out), "--pdf-dir", str(pdf_dir), "--json", str(salida)],
                  registro) is not None:
        return None
    return set(json.loads(salida.read_text(encoding="utf-8"))["con_problemas"])


def evaluar(d: dict, trabajo: Path, pdfs: PDFs) -> dict:
    nombre = f"{d['nombre']}__{d['clave']}"
    res = {"documento": d["clave"], "repo": d["nombre"], "pdf_sha256": d["sha256"], "pdf": None,
           "error": None, "sin_pdf": False, "cambios": [], "regresiones": []}
    pdf = pdfs.obtener(d["sha256"], d["url"])
    if pdf is None:
        res["sin_pdf"] = True
        return res
    res["pdf"] = pdf
    pub, nuevo = trabajo / "publicado" / nombre, trabajo / "nuevo" / nombre
    pdf_dir = trabajo / "pdf" / nombre
    for p in (pub, nuevo, pdf_dir):
        shutil.rmtree(p, ignore_errors=True)
    pdf_dir.mkdir(parents=True)
    (pdf_dir / f"{d['clave']}.pdf").symlink_to(Path(pdf).resolve())
    publicado = _exportar_publicado(d["repo"], d["clave"], pub)
    nuevo.mkdir(parents=True)
    res["error"] = _extractor(["build", "--doc", d["clave"], "--pdf", pdf, "--out", str(nuevo),
                               "--sin-pasajes"], d["registro"])
    if res["error"]:
        return res
    nuevos = {p.stem: p.read_bytes() for p in (nuevo / d["clave"]).glob("*.md")}
    for clave in sorted(set(publicado) | set(nuevos)):
        a, b = publicado.get(clave), nuevos.get(clave)
        if a != b:
            res["cambios"].append((clave, a.decode("utf-8") if a is not None else None,
                                   b.decode("utf-8") if b is not None else None))
    if res["cambios"]:
        antes = _auditar(pub, pdf_dir, d["registro"])
        despues = _auditar(nuevo, pdf_dir, d["registro"])
        if antes is None or despues is None:
            res["error"] = "no se pudo auditar"
        else:
            res["regresiones"] = sorted(despues - antes)
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--trabajo", required=True)
    ap.add_argument("--fiscal", default=None, help="clon de fiscal-mexicano (si no, se clona)")
    ap.add_argument("--federal", default=None, help="clon de leyes-federales (si no, se clona)")
    ap.add_argument("--sin-fiscal", action="store_true")
    ap.add_argument("--sin-federal", action="store_true")
    ap.add_argument("--pdf-dir", action="append", default=[])
    ap.add_argument("--cache", default=None, help="caché de PDF por sha256")
    ap.add_argument("--solo", action="append", help="limitar a estas claves")
    ap.add_argument("--registro", default=str(impacto.REGISTRO))
    ap.add_argument("--procesos", type=int, default=os.cpu_count() or 2)
    a = ap.parse_args(argv)

    t = Path(a.trabajo)
    t.mkdir(parents=True, exist_ok=True)
    fiscal = None if a.sin_fiscal else (
        Path(a.fiscal) if a.fiscal else clonar("fiscal-mexicano", t / "clones" / "fiscal"))
    federal = None if a.sin_federal else (
        Path(a.federal) if a.federal else clonar("leyes-federales", t / "clones" / "federal"))
    docs = [d for d in documentos(fiscal, federal, t) if not a.solo or d["clave"] in a.solo]
    pdfs = PDFs(a.pdf_dir, Path(a.cache) if a.cache else t / "cache")
    with ThreadPoolExecutor(max_workers=max(1, a.procesos)) as pool:
        resultados = list(pool.map(lambda d: evaluar(d, t, pdfs), docs))

    cambios = [impacto.Cambio(r["documento"], c, r["pdf_sha256"], x, y)
               for r in resultados for c, x, y in r["cambios"]]
    resumen = impacto.exportar(cambios, t, {r["pdf_sha256"]: r["pdf"] for r in resultados if r["pdf"]},
                               registro=impacto.cargar(a.registro),
                               origen="el extractor de este repo con cambios sin publicar")
    errores = [f"{r['repo']}/{r['documento']}: {r['error']}" for r in resultados if r["error"]]
    regresiones = [f"{r['repo']}/{r['documento']}: {', '.join(r['regresiones'][:10])}"
                   for r in resultados if r["regresiones"]]
    sin_pdf = [f"{r['repo']}/{r['documento']}" for r in resultados if r["sin_pdf"]]
    tocados = sorted({c.documento for c in cambios})
    informe = {"documentos": len(docs), "tocados": tocados, "errores": errores,
               "regresiones": regresiones, "sin_pdf": sin_pdf, **resumen}
    (t / "resumen.json").write_text(json.dumps(informe, ensure_ascii=False, indent=1) + "\n",
                                    encoding="utf-8")
    print(f"{len(docs) - len(sin_pdf)} de {len(docs)} documentos reconstruidos "
          f"({len(sin_pdf)} sin su PDF publicado); cambian {len(cambios)} unidades en "
          f"{len(tocados)} ({', '.join(tocados[:8])}); {resumen['ya_mejora']} ya confirmadas, "
          f"{resumen['pendientes']} por verificar en {resumen['grupos']} grupos.")
    for e in errores:
        print(f"✗ {e}")
    for r in regresiones:
        print(f"✗ regresión de cobertura en {r}")
    rechazadas = resumen["ya_empeora"] + resumen["ya_incierto"]
    if rechazadas:
        print(f"✗ reproduce correcciones ya rechazadas: {', '.join(rechazadas[:10])}")
    if errores or regresiones or rechazadas:
        return 2
    return 1 if resumen["pendientes"] or resumen["sin_revisar"] else 0


if __name__ == "__main__":
    sys.exit(main())
