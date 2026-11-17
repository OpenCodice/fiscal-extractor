#!/usr/bin/env python3
"""Convierte los cambios sin commit de un repo de datos en un commit por documento.

El historial de cada documento debe contar solo su propia historia: `git log --
lgs/` no puede mostrar la reforma de otra ley. Un documento es una carpeta de
primer nivel (`lgs/`) más su `metadata/lgs/`. Lo que no pertenece a ningún
documento (índices compartidos, README) va en un último commit aparte, con
`Tipo: indice`.

Cada commit lleva los trailers de scripts/trailers.py. El tipo sale de la
causa, nunca del agente: otro PDF con el mismo extractor es una reforma; el
mismo PDF con otro extractor, una corrección. Si cambiaron ambos, el documento
se separa en dos commits reconstruyendo el PDF nuevo con el extractor que
produjo la versión publicada: primero la reforma (lo que ese extractor ve
cambiar en el PDF) y luego la corrección (lo que cambia el extractor nuevo).
El PDF anterior no se guarda, así que el orden inverso no es reconstruible.

Una corrección que no toca el texto de ningún artículo es `metadatos`. Con
`--verificadas`, una corrección solo se publica si cada artículo que cambia
está confirmado como mejora en el registro de `scripts/impacto.py`. Si no: un
documento que solo tenía la corrección se queda como está publicado; uno que
además tenía reforma publica solo la reforma, construida con el extractor de
su versión publicada. En los dos casos su registro (`fuentes.json`,
`metadata/documentos.json`) conserva el extractor anterior, para que la
siguiente vigilancia lo vuelva a intentar, y `fuentes.json` lo anota en
`revision_pendiente`.

Uso:
  commits_por_documento.py <repo> --extractor-dir D --titulo-indice "…" \\
      (--pdf-dir P | --contexto contexto.json) [--verificadas verificaciones/impacto]

`--pdf-dir` (fiscal-mexicano): los PDF que dejó `actualizar` y su
`descargas.json`; la causa se deduce de `metadata/documentos.json`, que guarda
por documento el sha256 del PDF y el commit del extractor de su versión
publicada. `--contexto` (leyes-federales): lo escribe `federal cerrar`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import impacto  # noqa: E402
import trailers as tr  # noqa: E402


def _git(repo: str, *args: str, check: bool = True) -> str:
    return subprocess.run(["git", "-C", repo, *args], check=check,
                          capture_output=True, text=True).stdout


def cambios(repo: str, *rutas: str) -> list[str]:
    """Rutas cambiadas (incluidas nuevas y borradas), relativas al repo."""
    salida = _git(repo, "status", "--porcelain", "-z", "--no-renames", "-uall",
                  *(["--", *rutas] if rutas else []))
    return [e[3:] for e in salida.split("\0") if e]


def esquema(repo: str) -> str:
    """'estatal' en leyes-estatales (cada ley en `<estado>/<clave>/`), si no
    'corpus'."""
    raiz = Path(repo)
    return tr.esquema_repo((p.name for p in raiz.iterdir() if p.is_dir()),
                           lambda d: (raiz / d / "constitucion").is_dir())


def agrupar(rutas: list[str], esq: str = "corpus") -> tuple[dict[str, list[str]], list[str]]:
    por_doc: dict[str, list[str]] = {}
    resto: list[str] = []
    for r in rutas:
        doc = tr.documento_de_ruta(r, esq)
        if doc:
            por_doc.setdefault(doc, []).append(r)
        else:
            resto.append(r)
    return por_doc, resto


def sha256(ruta: str | Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def commit(repo: str, rutas: list[str], mensaje: str) -> None:
    _git(repo, "add", "-A", "--", *rutas)
    _git(repo, "commit", "-q", "-m", mensaje)


def mensaje_doc(repo: str, doc: str, tipo: str, rutas: list[str], ctx: dict,
                extractor: str | None, separacion: str | None = None) -> str:
    return tr.mensaje(doc, tipo, rutas, tr.lector_git(repo, "HEAD"), tr.lector_fs(repo),
                      fuente=ctx.get("fuente"), fuente_sha256=ctx.get("sha256"),
                      extractor=extractor, separacion=separacion,
                      motivo=ctx.get("motivo_retiro"))


def _articulos(raiz: Path, doc: str) -> dict[str, bytes]:
    d = raiz / tr._dir_articulos(doc)
    return {p.name: p.read_bytes() for p in sorted(d.glob("*.md"))} if d.is_dir() else {}


def _copiar_doc(origen: Path, destino: Path, doc: str) -> None:
    for rel in tr.carpetas(doc):
        if (destino / rel).exists():
            shutil.rmtree(destino / rel)
        if (origen / rel).exists():
            shutil.copytree(origen / rel, destino / rel)


def obtener_pdf(ctx: dict, extractor_dir: str, destino: Path) -> str | None:
    """El PDF del que salió el texto nuevo: el descargado, o se vuelve a
    descargar (la vigilancia federal extrae en otros jobs) y debe ser el mismo."""
    if ctx.get("pdf") and Path(ctx["pdf"]).exists():
        return ctx["pdf"]
    if not (ctx.get("fuente") and ctx.get("sha256")):
        return None
    try:
        sys.path.insert(0, extractor_dir)
        from extractor.fuentes import descargar
        descargar(ctx["fuente"], str(destino))
    except Exception as e:                       # noqa: BLE001 — sin PDF no se separa
        print(f"  · no se pudo volver a descargar {ctx['fuente']}: {e}")
        return None
    finally:
        sys.path.remove(extractor_dir)
    if sha256(destino) != ctx["sha256"]:
        print(f"  · {ctx['fuente']} cambió desde la extracción; no se separa")
        return None
    return str(destino)


def construir_con(extractor_dir: str, sha: str, repo: str, doc: str, pdf: str,
                  build: dict, trabajo: Path) -> Path | None:
    """Construye `doc` desde `pdf` con el extractor en el commit `sha`, sobre
    una copia del repo de datos en HEAD. Devuelve la copia, o None si no se
    pudo (commit desconocido, error del extractor)."""
    ext = trabajo / f"extractor-{sha[:12]}"
    if not ext.exists():
        r = subprocess.run(["git", "-C", extractor_dir, "worktree", "add", "-q", "--detach",
                            str(ext), sha], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  · no se pudo obtener el extractor {sha[:7]}: {r.stderr.strip()[:200]}")
            return None
    datos = trabajo / f"datos-{doc}"
    _git(repo, "worktree", "add", "-q", "--detach", str(datos), "HEAD")
    cmd = [sys.executable, "-m", "extractor"]
    if build.get("registro"):
        cmd += ["--registro", build["registro"]]
    cmd += ["build", "--doc", doc, "--pdf", pdf, "--out", str(datos), *build.get("args", [])]
    r = subprocess.run(cmd, cwd=ext, capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": str(ext)})
    if r.returncode != 0:
        print(f"  · el extractor {sha[:7]} no pudo construir {doc}: "
              f"{(r.stderr.strip().splitlines() or [''])[-1][:200]}")
        return None
    return datos


def sin_confirmar(repo: str, doc: str, ctx: dict, registro: dict | None) -> list[str]:
    """Artículos de la corrección que hay ahora en el árbol que el registro no
    confirma como mejora (vacío si no se exige)."""
    if registro is None:
        return []
    corregidos = tr.cambios_de_articulos(doc, cambios(repo, *tr.carpetas(doc)),
                                         tr.lector_git(repo, "HEAD"), tr.lector_fs(repo))
    return impacto.faltantes(registro, doc, ctx.get("sha256") or "-", corregidos)


def _restaurar_doc(repo: str, doc: str) -> None:
    for rel in tr.carpetas(doc):
        _git(repo, "checkout", "-q", "HEAD", "--", rel, check=False)
        _git(repo, "clean", "-fdq", "--", rel)


def _entrada_indice(repo: str, doc: str) -> dict | None:
    """La entrada de metadata/documentos.json que `build` deriva del índice
    del documento en disco (escribir_indice_maestro)."""
    d = tr._json(tr.lector_fs(repo), tr._dir_metadata(doc) + "articulos.json")
    if not isinstance(d, dict):
        return None
    return {"clave": d.get("documento", doc), "etiqueta": d.get("etiqueta"), "sigla": d.get("sigla"),
            "tipo": d.get("tipo"), "num_articulos": d.get("num_articulos"), "version": d.get("version")}


def retener_en_indices(repo: str, doc: str, motivo: str, *, extractor_sha: str | None) -> None:
    """Deja el registro del documento como corresponde a lo que sí se publica:
    sus cifras según el índice que quedó en disco y el extractor de su versión
    publicada."""
    previo = _git(repo, "show", "HEAD:fuentes.json", check=False)
    ruta = Path(repo) / "fuentes.json"
    if ruta.exists() and previo:
        anterior = {e["clave"]: e for e in json.loads(previo)["documentos"]}.get(doc)
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        for e in datos["documentos"]:
            if e["clave"] == doc and anterior:
                for campo in ("extractor", "extractor_sha"):
                    if campo in anterior:
                        e[campo] = anterior[campo]
                if extractor_sha is None:
                    for campo in ("version", "unidades", "pdf"):
                        if campo in anterior:
                            e[campo] = anterior[campo]
                e["revision_pendiente"] = {"fecha": date.today().isoformat(),
                                           "motivo": motivo}
        ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ruta = Path(repo) / "metadata" / "documentos.json"
    entrada = _entrada_indice(repo, doc)
    if ruta.exists() and entrada:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        for e in datos["documentos"]:
            if e["clave"] == doc:
                e.update(entrada)
        ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _motivo(faltan: list[str]) -> str:
    return ("La corrección de extracción no quedó confirmada contra el PDF "
            f"(arts. {', '.join(faltan[:8])}{' y más' if len(faltan) > 8 else ''}); "
            "se conserva el texto publicado.")


def commits_documento(repo: str, doc: str, ctx: dict, *, extractor_repo: str,
                      extractor_dir: str | None, build: dict, trabajo: Path,
                      registro: dict | None = None) -> list[str]:
    """Hace el commit (o los dos) de un documento; devuelve sus tipos (vacío
    si no se publica)."""
    antes, despues = tr.lector_git(repo, "HEAD"), tr.lector_fs(repo)
    actual = tr.extractor_id(extractor_repo, ctx["extractor_sha"]) if ctx.get("extractor_sha") else None
    rutas = cambios(repo, *tr.carpetas(doc))
    tipo = tr.tipo_por_existencia(doc, antes, despues)
    if tipo:
        commit(repo, rutas, mensaje_doc(repo, doc, tipo, rutas, ctx, actual))
        return [tipo]

    pdf_cambio = ctx.get("pdf_cambio")
    if pdf_cambio is None:
        # Sin huella del PDF anterior: cambió si cambió su versión o aparecieron
        # fechas de reforma nuevas.
        a, d = tr.info(doc, antes), tr.info(doc, despues)
        pdf_cambio = a["version"] != d["version"] or bool(d["reformas"] - a["reformas"])
    decision = tr.decidir_tipo(pdf_cambio, ctx.get("extractor_cambio"))

    if decision == "separar":
        anterior = ctx.get("extractor_anterior")
        datos = None
        pdf = obtener_pdf(ctx, extractor_dir, trabajo / f"{doc}.pdf") if extractor_dir else None
        if anterior and pdf:
            datos = construir_con(extractor_dir, anterior, repo, doc, pdf, build, trabajo)
        if datos is None:
            decision = "sin-separacion"
        else:
            final, inter = _articulos(Path(repo), doc), _articulos(datos, doc)
            publicado = {Path(r).name: antes(r)
                         for r in _git(repo, "ls-tree", "-z", "--name-only", "HEAD",
                                       tr._dir_articulos(doc)).split("\0")
                         if r.endswith(".md")}
            if inter == final:
                decision = "reforma"            # el extractor nuevo no cambia nada aquí
            elif inter == publicado:
                decision = "correccion"         # el PDF nuevo no cambia el texto
            else:
                guardado = trabajo / f"final-{doc}"
                _copiar_doc(Path(repo), guardado, doc)
                _copiar_doc(datos, Path(repo), doc)
                r1 = cambios(repo, *tr.carpetas(doc))
                commit(repo, r1, mensaje_doc(repo, doc, "reforma", r1, ctx,
                                             tr.extractor_id(extractor_repo, anterior)))
                _copiar_doc(guardado, Path(repo), doc)
                r2 = cambios(repo, *tr.carpetas(doc))
                if not r2:
                    return ["reforma"]
                faltan = sin_confirmar(repo, doc, ctx, registro)
                if faltan:
                    _restaurar_doc(repo, doc)
                    ctx["extractor_sha"] = anterior
                    retener_en_indices(repo, doc, _motivo(faltan), extractor_sha=anterior)
                    print(f"  · {doc}: solo la reforma; {_motivo(faltan)}")
                    return ["reforma"]
                tipo2 = tr.tipo_sin_reforma(doc, r2, tr.lector_git(repo, "HEAD"), tr.lector_fs(repo))
                commit(repo, r2, mensaje_doc(repo, doc, tipo2, r2, ctx, actual))
                return ["reforma", tipo2]

    tipo = "correccion" if decision == "correccion" else "reforma"
    if tipo == "correccion":
        faltan = sin_confirmar(repo, doc, ctx, registro)
        if faltan:
            _restaurar_doc(repo, doc)
            retener_en_indices(repo, doc, _motivo(faltan), extractor_sha=None)
            print(f"  · {doc}: no se publica; {_motivo(faltan)}")
            return []
        tipo = tr.tipo_sin_reforma(doc, rutas, antes, despues)
    sep = "no-disponible" if decision == "sin-separacion" else None
    commit(repo, rutas, mensaje_doc(repo, doc, tipo, rutas, ctx, actual, sep))
    return [tipo]


# ------------------------------------------------------------------ fiscal

def _documentos_json(texto: str | None) -> dict:
    if not texto:
        return {}
    d = json.loads(texto)
    return {e["clave"]: e for e in (d["documentos"] if isinstance(d, dict) else d)}


def extractor_cambio(extractor_dir: str, anterior: str | None, actual: str) -> bool | None:
    """¿Cambió el código del extractor (extractor/) entre dos commits? None si
    no se sabe con qué commit se publicó lo anterior."""
    if not anterior:
        return None
    r = subprocess.run(["git", "-C", extractor_dir, "diff", "--quiet", anterior, actual,
                        "--", "extractor/"], capture_output=True)
    return {0: False, 1: True}.get(r.returncode)


def contexto_fiscal(repo: str, pdf_dir: str, extractor_dir: str, docs: list[str]) -> dict:
    """La causa de cada documento de fiscal-mexicano: el PDF descargado contra
    el sha256 y el commit del extractor de su versión publicada
    (metadata/documentos.json en HEAD)."""
    previos = _documentos_json(_git(repo, "show", "HEAD:metadata/documentos.json", check=False))
    descargas_p = Path(pdf_dir) / "descargas.json"
    descargas = json.loads(descargas_p.read_text(encoding="utf-8")) if descargas_p.exists() else {}
    actual = _git(extractor_dir, "rev-parse", "HEAD").strip()
    ctx = {}
    for doc in docs:
        pdf = Path(pdf_dir) / f"{doc}.pdf"
        prev = previos.get(doc, {})
        sha = sha256(pdf) if pdf.exists() else None
        idx = tr._json(tr.lector_fs(repo), f"metadata/{doc}/articulos.json") or {}
        ctx[doc] = {
            "fuente": descargas.get(doc) or idx.get("fuente"),
            "sha256": sha, "pdf": str(pdf) if pdf.exists() else None,
            "pdf_cambio": None if not (prev.get("pdf_sha256") and sha) else prev["pdf_sha256"] != sha,
            "extractor_sha": actual,
            "extractor_anterior": prev.get("extractor_sha"),
            "extractor_cambio": extractor_cambio(extractor_dir, prev.get("extractor_sha"), actual),
        }
    return ctx


def anotar_documentos_json(repo: str, publicados: dict[str, dict]) -> None:
    """Conserva en metadata/documentos.json, por documento, el sha256 del PDF y
    el commit del extractor de su versión publicada (`build` lo regenera sin
    ellos): los de este PR se actualizan, los demás se traen de HEAD."""
    ruta = Path(repo) / "metadata" / "documentos.json"
    if not ruta.exists():
        return
    previos = _documentos_json(_git(repo, "show", "HEAD:metadata/documentos.json", check=False))
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    for e in datos["documentos"]:
        fuente = publicados.get(e["clave"]) or previos.get(e["clave"], {})
        for campo_dato, campo_ctx in (("pdf_sha256", "sha256"), ("extractor_sha", "extractor_sha")):
            v = fuente.get(campo_ctx) if e["clave"] in publicados else fuente.get(campo_dato)
            if v:
                e[campo_dato] = v
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--conservar-indice", action="store_true",
                    help="solo devuelve a metadata/documentos.json los campos de HEAD que "
                         "`build` no escribe, para que reconstruir no lo cambie")
    ap.add_argument("--titulo-indice")
    ap.add_argument("--extractor-dir")
    ap.add_argument("--extractor-repo", default="fiscal-extractor")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--pdf-dir")
    g.add_argument("--contexto")
    ap.add_argument("--salida", default=None, help="JSON con los commits hechos")
    ap.add_argument("--verificadas", default=None,
                    help="registro de correcciones confirmadas (scripts/impacto.py)")
    a = ap.parse_args(argv)
    registro = impacto.cargar(a.verificadas) if a.verificadas else None

    repo = a.repo
    if a.conservar_indice:
        anotar_documentos_json(repo, {})
        return 0
    if not (a.titulo_indice and a.extractor_dir and (a.pdf_dir or a.contexto)):
        ap.error("faltan --titulo-indice, --extractor-dir y --pdf-dir o --contexto")
    por_doc, _ = agrupar(cambios(repo), esquema(repo))
    if a.contexto:
        c = json.loads(Path(a.contexto).read_text(encoding="utf-8"))
        ctx, build = c.get("documentos", {}), c.get("build", {})
    else:
        ctx, build = contexto_fiscal(repo, a.pdf_dir, a.extractor_dir, sorted(por_doc)), {}
    actual_sha = _git(a.extractor_dir, "rev-parse", "HEAD").strip()

    hechos: dict[str, list[str]] = {}
    with tempfile.TemporaryDirectory() as tmp:
        for doc in sorted(por_doc):
            d = ctx.get(doc) or {"extractor_sha": actual_sha}
            hechos[doc] = commits_documento(
                repo, doc, d, extractor_repo=a.extractor_repo,
                extractor_dir=a.extractor_dir, build=build, trabajo=Path(tmp), registro=registro)
            if hechos[doc]:
                print(f"{doc}: {' + '.join(hechos[doc])} — "
                      f"{_git(repo, 'log', '-1', '--format=%s').strip()}")
            else:
                del hechos[doc]
    for r in (repo, a.extractor_dir):
        _git(r, "worktree", "prune", check=False)
    if a.pdf_dir:
        anotar_documentos_json(repo, {doc: ctx[doc] for doc in hechos
                                      if doc in ctx and hechos[doc] != ["retiro"]})
    resto = cambios(repo)
    if resto:
        commit(repo, resto, tr.formatear(a.titulo_indice, tr.trailers_indice(
            tr.extractor_id(a.extractor_repo, actual_sha))))
        print(f"índice ({len(resto)} archivos): {a.titulo_indice}")
    tipos = {t for ts in hechos.values() for t in ts}
    if a.salida:
        Path(a.salida).write_text(json.dumps(hechos, ensure_ascii=False, indent=1), encoding="utf-8")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
            fh.write(f"tipo={'reforma' if tipos & {'reforma', 'alta'} else 'correccion'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
