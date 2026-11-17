#!/usr/bin/env python3
"""Impacto del extractor, tal como está en disco, sobre todo lo publicado.

Reconstruye cada documento publicado de fiscal-mexicano, de leyes-federales y
de las leyes de leyes-estatales (no sus constituciones, que son de
constitucion-extractor) desde el PDF exacto de su versión publicada (el sha256 que guardan
`metadata/documentos.json` y `fuentes.json` o, si no, el `Fuente-Sha256` del
último commit del documento), compara unidad por unidad contra
el texto publicado (HEAD del repo de datos, no su árbol de trabajo) y deja en
`--trabajo` las correcciones que eso produciría y que el registro de
`scripts/impacto.py` aún no confirma (`pendientes.json`, para
`scripts/agente/impacto.sh`). En cada documento que cambia audita además la
cobertura antes y después: unidades nuevas con problemas son una regresión y
el cambio del extractor no puede entrar.

Los PDF no se versionan: se buscan por sha256 en `--pdf-dir` (los que ya
descargó la vigilancia) y en `--cache`, y si no, se descargan de su URL; si la
fuente ya publica otro PDF (hubo una reforma), ese documento no se puede medir
y queda anotado: su corrección la exige después la vigilancia. Si no se sabe el
sha256 publicado (versiones anteriores a que se guardara), vale el PDF de hoy
cuando su versión es la publicada.

Sale 0 si no queda nada por verificar ni hay regresiones, 1 si hay correcciones
por verificar, 2 si hay regresiones de cobertura, errores de extracción o
correcciones ya rechazadas.

Dos modos más, para el job `reparar` (scripts/agente/reparar.sh):

- `--solo-pdfs` deja en `--cache` (y los clones en `--trabajo`) todo lo que la
  medición necesita, sin construir nada: lo corre el workflow antes del agente,
  que no tiene red hacia las fuentes que piden `EGRESS_MX_TOKEN`.
- `--medir` es la misma medición, de solo lectura, para el agente reparador:
  no exporta pendientes; deja en `--trabajo` `medicion.md` (cada unidad que
  cambia, si es de las leyes `--objetivo` o no, su veredicto previo en el
  registro y su diff) y `medicion.json`. Sale 0 si fuera del objetivo no cambia
  nada sin confirmar, 1 si sí, 2 con regresiones o errores. `--muestra N` mide
  solo N documentos de cada repo, espaciados por clave (más los del objetivo):
  un paso rápido, no la medición que decide.

Uso:
  impacto_corpus.py --trabajo T [--fiscal REPO] [--federal REPO] [--estatal REPO] [--pdf-dir D]...
      [--cache C] [--solo DOC]... [--solo-pdfs | --medir [--objetivo DOC]... [--muestra N]]
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
import trailers as tr  # noqa: E402

EXTRACTOR = Path(__file__).resolve().parent.parent
ORG = "https://github.com/OpenCodice"


def _git(repo, *args, binario=False):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True)
    return r.stdout if binario else r.stdout.decode("utf-8")


def clonar(nombre: str, destino: Path) -> Path:
    # Con historia: el sha256 del PDF publicado puede estar solo en los
    # trailers del último commit del documento.
    if not (destino / ".git").exists():
        subprocess.run(["git", "clone", "-q", f"{ORG}/{nombre}.git", str(destino)], check=True)
    return destino


def sha_publicado(repo: Path, clave: str) -> str | None:
    """Fuente-Sha256 del último commit del documento: el PDF de su versión
    publicada, cuando el índice no lo guarda."""
    for rev in _git(repo, "log", "--format=%H", "-n", "20", "HEAD", "--",
                    *tr.carpetas(clave)).split():
        _, t = tr.parsear(_git(repo, "log", "-1", "--format=%B", rev))
        if tr.valor(t, "Documento") == clave and tr.valor(t, "Fuente-Sha256"):
            return tr.valor(t, "Fuente-Sha256")
    return None


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def documentos(fiscal: Path | None, federal: Path | None, trabajo: Path,
               estatal: Path | None = None) -> list[dict]:
    """Cada documento publicado: repo, clave, URL, sha256 del PDF publicado y
    registro con el que se construye (None: el fiscal de registro.py). De
    leyes-estatales, solo las leyes de su fuentes.json: las constituciones son
    de constitucion-extractor."""
    docs = []
    if fiscal:
        indice = json.loads(_git(fiscal, "show", "HEAD:metadata/documentos.json"))
        for e in indice["documentos"]:
            idx = json.loads(_git(fiscal, "show", f"HEAD:metadata/{e['clave']}/articulos.json"))
            docs.append({"repo": fiscal, "nombre": "fiscal-mexicano", "clave": e["clave"],
                         "url": idx.get("fuente"),
                         "sha256": e.get("pdf_sha256") or sha_publicado(fiscal, e["clave"]),
                         "registro": None})
    if federal:
        registro = trabajo / "fuentes.json"
        registro.write_bytes(_git(federal, "show", "HEAD:fuentes.json", binario=True))
        for e in json.loads(registro.read_text(encoding="utf-8"))["documentos"]:
            if e.get("estado") == "incluida":
                docs.append({"repo": federal, "nombre": "leyes-federales", "clave": e["clave"],
                             "url": e.get("url"),
                             "sha256": (e.get("pdf") or {}).get("sha256") or sha_publicado(federal, e["clave"]),
                             "registro": str(registro)})
    if estatal and _git(estatal, "ls-tree", "--name-only", "HEAD", "fuentes.json").strip():
        registro = trabajo / "fuentes-estatal.json"
        registro.write_bytes(_git(estatal, "show", "HEAD:fuentes.json", binario=True))
        for e in json.loads(registro.read_text(encoding="utf-8"))["documentos"]:
            if e.get("estado") == "incluida":
                docs.append({"repo": estatal, "nombre": "leyes-estatales", "clave": e["clave"],
                             "url": e.get("url"),
                             "sha256": (e.get("pdf") or {}).get("sha256") or sha_publicado(estatal, e["clave"]),
                             "registro": str(registro)})
    return docs


class PDFs:
    """PDF por sha256: de las carpetas dadas, de la caché o descargado."""

    def __init__(self, dirs: list[str], cache: Path):
        self.cache = cache
        cache.mkdir(parents=True, exist_ok=True)
        self.por_sha = {p.stem: str(p) for p in cache.glob("*.pdf")}
        self.verificados: set[str] = set()
        self.por_clave: dict[str, str] = {}
        for d in dirs:
            # Las leyes estatales ('jalisco/codigo-civil.pdf') van en subcarpetas.
            for p in Path(d).rglob("*.pdf"):
                self.por_sha.setdefault(_sha256(p), str(p))
                self.por_clave.setdefault(p.relative_to(d).with_suffix("").as_posix().lower(), str(p))

    def _integro(self, sha: str) -> bool:
        """La caché la comparten el agente reparador y las compuertas: un PDF
        de la caché vale solo si su contenido sigue siendo el de su nombre."""
        ruta = Path(self.por_sha[sha])
        if sha in self.verificados or ruta.parent != self.cache:
            return True
        try:
            ok = _sha256(ruta) == sha
        except OSError:
            ok = False
        if ok:
            self.verificados.add(sha)
            return True
        ruta.unlink(missing_ok=True)
        del self.por_sha[sha]
        return False

    def obtener(self, sha: str | None, url: str | None, clave: str) -> str | None:
        """El PDF con ese sha256; sin sha (versiones publicadas antes de que se
        guardara), el de hoy: el ya descargado o el que publica la URL."""
        if sha and sha in self.por_sha and self._integro(sha):
            return self.por_sha[sha]
        if not sha and clave in self.por_clave:
            return self.por_clave[clave]
        if not url:
            return None
        nombre = sha or "url-" + hashlib.sha256(url.encode()).hexdigest()[:16]
        destino = self.cache / f"{nombre}.pdf"
        if destino.exists():
            return str(destino)
        tmp = self.cache / f"{nombre}.descarga"
        try:
            sys.path.insert(0, str(EXTRACTOR))
            from extractor.fuentes import descargar
            descargar(url, str(tmp))
        except Exception:                            # noqa: BLE001 — sin PDF no se mide
            return None
        real = _sha256(tmp)
        if sha and real != sha:
            tmp.unlink(missing_ok=True)
            return None
        tmp.rename(destino)
        self.por_sha[real] = str(destino)
        self.verificados.add(real)
        return str(destino)


def _exportar_publicado(repo: Path, clave: str, destino: Path) -> dict[str, bytes]:
    """Unidades y metadata publicadas (HEAD) del documento, en `destino`."""
    datos = _git(repo, "archive", "--format=tar", "HEAD", *tr.carpetas(clave), binario=True)
    with tarfile.open(fileobj=io.BytesIO(datos)) as tar:
        tar.extractall(destino, filter="data")
    return {p.stem: p.read_bytes() for p in (destino / tr._dir_articulos(clave)).glob("*.md")}


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
    nombre = f"{d['nombre']}__{d['clave'].replace('/', '__')}"
    res = {"documento": d["clave"], "repo": d["nombre"], "pdf_sha256": d["sha256"], "pdf": None,
           "error": None, "sin_pdf": False, "cambios": [], "regresiones": []}
    pdf = pdfs.obtener(d["sha256"], d["url"], d["clave"])
    if pdf is None:
        res["sin_pdf"] = True
        return res
    res["pdf"] = pdf
    pub, nuevo = trabajo / "publicado" / nombre, trabajo / "nuevo" / nombre
    pdf_dir = trabajo / "pdf" / nombre
    for p in (pub, nuevo, pdf_dir):
        shutil.rmtree(p, ignore_errors=True)
    (pdf_dir / f"{d['clave']}.pdf").parent.mkdir(parents=True, exist_ok=True)
    (pdf_dir / f"{d['clave']}.pdf").symlink_to(Path(pdf).resolve())
    publicado = _exportar_publicado(d["repo"], d["clave"], pub)
    nuevo.mkdir(parents=True)
    res["error"] = _extractor(["build", "--doc", d["clave"], "--pdf", pdf, "--out", str(nuevo),
                               "--sin-pasajes"], d["registro"])
    if res["error"]:
        return res
    if not d["sha256"]:
        # Sin el sha256 publicado, el PDF de hoy solo vale si es la misma
        # versión (la fecha de su portada) que la publicada.
        leer = lambda raiz: json.loads((raiz / tr._dir_metadata(d["clave"]) / "articulos.json")
                                       .read_text(encoding="utf-8")).get("version")
        try:
            misma = leer(pub) == leer(nuevo)
        except (OSError, ValueError):
            misma = False
        if not misma:
            res["sin_pdf"] = True
            return res
        res["pdf_sha256"] = _sha256(Path(pdf))
    nuevos = {p.stem: p.read_bytes() for p in (nuevo / tr._dir_articulos(d["clave"])).glob("*.md")}
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


def muestrear(docs: list[dict], n: int, fijos: set[str] = frozenset()) -> list[dict]:
    """N documentos de cada repo, espaciados en orden de clave, más los `fijos`."""
    if n <= 0:
        return docs
    llave = lambda d: (d["nombre"], d["clave"])
    por_repo: dict[str, list[dict]] = {}
    for d in docs:
        por_repo.setdefault(d["nombre"], []).append(d)
    elegidos = {llave(d) for d in docs if d["clave"] in fijos}
    for lista in por_repo.values():
        lista = sorted(lista, key=lambda d: d["clave"])
        paso = max(1.0, len(lista) / n)
        elegidos |= {llave(lista[int(i * paso)]) for i in range(min(n, len(lista)))}
    return [d for d in docs if llave(d) in elegidos]


def informe_medicion(resultados: list[dict], objetivo: set[str], registro: dict) -> tuple[dict, str]:
    """Para el agente reparador: qué cambia, dentro y fuera de sus leyes, con
    el veredicto que el registro ya tenga de ese mismo cambio."""
    filas = []
    for r in resultados:
        for clave, antes, despues in r["cambios"]:
            c = impacto.Cambio(r["documento"], clave, r["pdf_sha256"], antes, despues)
            filas.append({"documento": r["documento"], "repo": r["repo"], "clave": clave,
                          "objetivo": r["documento"] in objetivo,
                          "veredicto_previo": impacto.veredicto(registro, c),
                          "diff": impacto.diff_parrafos(antes, despues)})
    fuera = [f for f in filas if not f["objetivo"]]
    fuera_sin_confirmar = [f for f in fuera if f["veredicto_previo"] != "mejora"]
    datos = {
        "documentos": len(resultados),
        "sin_pdf": [f"{r['repo']}/{r['documento']}" for r in resultados if r["sin_pdf"]],
        "errores": [f"{r['repo']}/{r['documento']}: {r['error']}" for r in resultados if r["error"]],
        "regresiones": [f"{r['repo']}/{r['documento']}: {', '.join(r['regresiones'][:10])}"
                        for r in resultados if r["regresiones"]],
        "cambian": len(filas), "en_objetivo": len(filas) - len(fuera), "fuera": len(fuera),
        "fuera_sin_confirmar": len(fuera_sin_confirmar),
        "por_documento": {},
        "unidades": [{k: v for k, v in f.items() if k != "diff"} for f in filas],
    }
    for f in filas:
        datos["por_documento"][f["documento"]] = datos["por_documento"].get(f["documento"], 0) + 1
    etiqueta = {None: "sin juzgar", "mejora": "ya confirmada como mejora",
                "empeora": "ya rechazada: empeora", "incierto": "ya rechazada: incierto"}
    md = [f"# Medición del extractor en disco contra lo publicado",
          "",
          f"{len(resultados) - len(datos['sin_pdf'])} de {len(resultados)} documentos medidos; cambian {len(filas)} unidades: "
          f"{len(filas) - len(fuera)} en las leyes objetivo y {len(fuera)} fuera "
          f"({len(fuera_sin_confirmar)} sin confirmar como mejora).", ""]
    for titulo, lista in (("Errores", datos["errores"]), ("Regresiones de cobertura", datos["regresiones"]),
                          ("Sin su PDF publicado (no medidos)", datos["sin_pdf"])):
        if lista:
            md += [f"## {titulo}", ""] + [f"- {x}" for x in lista] + [""]
    if datos["por_documento"]:
        md += ["## Unidades que cambian por documento", ""]
        md += [f"- {doc}: {n}{'' if doc in objetivo else ' (fuera del objetivo)'}"
               for doc, n in sorted(datos["por_documento"].items())] + [""]
    for f in sorted(filas, key=lambda f: (f["objetivo"], f["documento"], f["clave"])):
        lugar = "objetivo" if f["objetivo"] else "FUERA DEL OBJETIVO"
        md += [f"## {f['documento']}:{f['clave']} — {lugar}, {etiqueta.get(f['veredicto_previo'], f['veredicto_previo'])}",
               "", "```diff", f["diff"], "```", ""]
    return datos, "\n".join(md)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--trabajo", required=True)
    ap.add_argument("--fiscal", default=None, help="clon de fiscal-mexicano (si no, se clona)")
    ap.add_argument("--federal", default=None, help="clon de leyes-federales (si no, se clona)")
    ap.add_argument("--estatal", default=None, help="clon de leyes-estatales (si no, se clona)")
    ap.add_argument("--sin-fiscal", action="store_true")
    ap.add_argument("--sin-federal", action="store_true")
    ap.add_argument("--sin-estatal", action="store_true")
    ap.add_argument("--pdf-dir", action="append", default=[])
    ap.add_argument("--cache", default=None, help="caché de PDF por sha256")
    ap.add_argument("--solo", action="append", help="limitar a estas claves")
    ap.add_argument("--registro", default=str(impacto.REGISTRO))
    ap.add_argument("--procesos", type=int, default=os.cpu_count() or 2)
    modo = ap.add_mutually_exclusive_group()
    modo.add_argument("--solo-pdfs", action="store_true",
                      help="solo clonar y dejar en la caché los PDF publicados")
    modo.add_argument("--medir", action="store_true",
                      help="solo lectura: informe para el agente reparador, sin pendientes")
    ap.add_argument("--objetivo", action="append", default=[],
                    help="con --medir: claves de las leyes que se están reparando")
    ap.add_argument("--muestra", type=int, default=0,
                    help="con --medir: solo N documentos por repo (más los del objetivo)")
    a = ap.parse_args(argv)

    t = Path(a.trabajo)
    t.mkdir(parents=True, exist_ok=True)
    fiscal = None if a.sin_fiscal else (
        Path(a.fiscal) if a.fiscal else clonar("fiscal-mexicano", t / "clones" / "fiscal"))
    federal = None if a.sin_federal else (
        Path(a.federal) if a.federal else clonar("leyes-federales", t / "clones" / "federal"))
    estatal = None if a.sin_estatal else (
        Path(a.estatal) if a.estatal else clonar("leyes-estatales", t / "clones" / "estatal"))
    docs = [d for d in documentos(fiscal, federal, t, estatal) if not a.solo or d["clave"] in a.solo]
    pdfs = PDFs(a.pdf_dir, Path(a.cache) if a.cache else t / "cache")
    if a.solo_pdfs:
        with ThreadPoolExecutor(max_workers=4) as pool:
            faltan = [d["clave"] for d, p in zip(docs, pool.map(
                lambda d: pdfs.obtener(d["sha256"], d["url"], d["clave"]), docs)) if p is None]
        print(f"{len(docs) - len(faltan)} de {len(docs)} PDF publicados en la caché"
              + (f"; faltan: {', '.join(faltan[:20])}" if faltan else "."))
        return 0
    if a.medir:
        docs = muestrear(docs, a.muestra, set(a.objetivo))
    with ThreadPoolExecutor(max_workers=max(1, a.procesos)) as pool:
        resultados = list(pool.map(lambda d: evaluar(d, t, pdfs), docs))

    if a.medir:
        datos, md = informe_medicion(resultados, set(a.objetivo), impacto.cargar(a.registro))
        (t / "medicion.json").write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n",
                                         encoding="utf-8")
        (t / "medicion.md").write_text(md + "\n", encoding="utf-8")
        print(md.split("\n")[2])
        for doc, n in sorted(datos["por_documento"].items()):
            print(f"  {doc}: {n}{'' if doc in a.objetivo else ' (fuera del objetivo)'}")
        for x in datos["errores"]:
            print(f"✗ {x}")
        for x in datos["regresiones"]:
            print(f"✗ regresión de cobertura en {x}")
        print(f"Detalle y diffs: {t / 'medicion.md'}")
        if datos["errores"] or datos["regresiones"]:
            return 2
        return 1 if datos["fuera_sin_confirmar"] else 0

    cambios = [impacto.Cambio(r["documento"], c, r["pdf_sha256"], x, y)
               for r in resultados for c, x, y in r["cambios"]]
    resumen = impacto.exportar(cambios, t, {r["pdf_sha256"]: r["pdf"] for r in resultados if r["pdf"]},
                               registro=impacto.cargar(a.registro),
                               origen="el extractor de este repo con cambios sin publicar",
                               rejuzgar=True)
    errores = [f"{r['repo']}/{r['documento']}: {r['error']}" for r in resultados if r["error"]]
    regresiones = [f"{r['repo']}/{r['documento']}: {', '.join(r['regresiones'][:10])}"
                   for r in resultados if r["regresiones"]]
    sin_pdf = [f"{r['repo']}/{r['documento']}" for r in resultados if r["sin_pdf"]]
    tocados = sorted({c.documento for c in cambios})
    informe = {"documentos": len(docs), "tocados": tocados, "errores": errores,
               "regresiones": regresiones, "sin_pdf": sin_pdf, **resumen}
    (t / "resumen.json").write_text(json.dumps(informe, ensure_ascii=False, indent=1) + "\n",
                                    encoding="utf-8")
    # Cada unidad que cambia y cómo (huella del texto antes y después): la ronda
    # de expansión compara dos mediciones con esto (scripts/expansion.py).
    (t / "cambios.json").write_text(json.dumps(sorted(list(c.llave) for c in cambios),
                                               ensure_ascii=False) + "\n", encoding="utf-8")
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
    # Una excepción saldría con 1, que aquí significa "hay correcciones por
    # verificar": se confundiría con un resultado. Sale 3, que nadie acepta.
    try:
        sys.exit(main())
    except Exception:                                # noqa: BLE001
        import traceback
        traceback.print_exc()
        print("✗ impacto_corpus.py falló: no se pudo medir el impacto")
        sys.exit(3)
