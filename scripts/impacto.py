#!/usr/bin/env python3
"""Correcciones de extracción verificadas: el impacto de un cambio del
extractor sobre el texto publicado y el registro de lo ya confirmado.

Una corrección (mismo PDF, otro extractor) cambia texto legal ya publicado sin
que la ley haya cambiado, así que solo se publica si cada artículo que cambia
está confirmado contra el PDF como una mejora. La confirmación la da un agente
(scripts/agente/brief-impacto.md) y queda en `verificaciones/impacto/*.jsonl`
de este repo: una línea por artículo, con la huella de su texto antes y
después y la del PDF. Así nada se verifica dos veces y la vigilancia puede
exigir, por código, que cada corrección que publica esté en el registro:

- al aceptar un arreglo del agente, `impacto_corpus.py` reconstruye todo lo
  que produce el extractor y el arreglo solo entra si cada cambio es mejora;
- un commit hecho a mano al extractor lo verifica `impacto.yml` al llegar a
  main;
- la vigilancia, antes de abrir el PR, revisa sus propios commits
  (`pendientes-commits`), verifica lo que falte y rehace los commits sin las
  correcciones que no quedaron confirmadas (los generadores con
  `--verificadas`).

Los artículos que cambian igual (el mismo texto quitado y puesto, salvo
números) se agrupan: el agente revisa unos pocos de cada grupo y su veredicto
vale para todo el grupo. Eso acota el costo cuando un arreglo general toca
cientos de artículos.

Uso:
  impacto.py pendientes-commits <repo> --base REV --trabajo T [--pdf-dir D]...
      [--veredicto-agente V --extractor OpenCodice/x@sha]
  impacto.py cerrar --trabajo T --extractor OpenCodice/x@sha [--registro DIR]
  impacto.py exigir <repo> --base REV [--registro DIR]
  impacto.py ya-confirmadas <repo> --documento D --pdf P [--documento D2 --pdf P2]...

Este archivo existe idéntico en constitucion-extractor y en fiscal-extractor
(scripts/impacto.py): cualquier cambio se hace en los dos.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trailers as tr  # noqa: E402

REGISTRO = Path(__file__).resolve().parent.parent / "verificaciones" / "impacto"
VEREDICTOS = ("mejora", "empeora", "incierto")
# Grupos que un agente revisa en una corrida y miembros que mira de cada uno.
MAX_GRUPOS = 150
MUESTRA_POR_GRUPO = 3

Clave = tuple[str, str, str, str, str]


def huella(texto: "str | bytes | None") -> str:
    if texto is None:
        return "-"
    if isinstance(texto, str):
        texto = texto.encode("utf-8")
    return hashlib.sha256(texto).hexdigest()


@dataclass
class Cambio:
    documento: str
    clave: str
    pdf: str                   # sha256 del PDF contra el que se juzga
    antes: str | None
    despues: str | None

    @property
    def llave(self) -> Clave:
        return (self.documento, self.clave, self.pdf, huella(self.antes), huella(self.despues))


# ------------------------------------------------------------------ registro

def cargar(registro: str | Path = REGISTRO) -> dict[Clave, dict]:
    """Veredicto vigente de cada (documento, artículo, PDF, antes, después).
    Si un mismo cambio se juzgó dos veces, vale el último archivo en orden."""
    res: dict[Clave, dict] = {}
    d = Path(registro)
    if not d.is_dir():
        return res
    for archivo in sorted(d.glob("*.jsonl")):
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            if not linea.strip():
                continue
            e = json.loads(linea)
            res[(e["documento"], e["clave"], e["pdf"], e["antes"], e["despues"])] = e
    return res


def escribir(entradas: list[dict], registro: str | Path, nombre: str) -> Path | None:
    """Un archivo nuevo por lote: corridas paralelas nunca editan el mismo."""
    if not entradas:
        return None
    d = Path(registro)
    d.mkdir(parents=True, exist_ok=True)
    ruta = d / f"{nombre}.jsonl"
    with ruta.open("a", encoding="utf-8") as fh:
        for e in entradas:
            fh.write(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n")
    return ruta


def veredicto(registro: dict[Clave, dict], cambio: Cambio) -> str | None:
    e = registro.get(cambio.llave)
    return e["veredicto"] if e else None


def faltantes(registro: dict[Clave, dict], documento: str, pdf: str,
              cambios: dict[str, tuple[str | None, str | None]]) -> list[str]:
    """Artículos de una corrección que no están confirmados como mejora."""
    return sorted(c for c, (a, d) in cambios.items()
                  if veredicto(registro, Cambio(documento, c, pdf, a, d)) != "mejora")


# ------------------------------------------------------------------ grupos

_PALABRA = re.compile(r"\S+")
_DIGITOS = re.compile(r"\d+")


def firma(antes: str | None, despues: str | None) -> str:
    """Lo que el cambio quita y pone, palabra por palabra y con los números
    normalizados: dos artículos con la misma firma cambiaron de la misma
    manera (p. ej. el mismo pie de página que deja de colarse)."""
    if antes is None or despues is None:
        return "alta" if antes is None else "baja"
    a, d = _PALABRA.findall(antes), _PALABRA.findall(despues)
    partes = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, d, autojunk=False).get_opcodes():
        if op != "equal":
            partes.append(f"-{' '.join(a[i1:i2])}|+{' '.join(d[j1:j2])}")
    return _DIGITOS.sub("0", "\n".join(partes))[:2000]


@dataclass
class Grupo:
    id: str
    firma: str
    miembros: list[Cambio] = field(default_factory=list)

    def muestra(self) -> list[Cambio]:
        """Los que el agente revisa: el primero y, de preferencia, de otros
        documentos."""
        elegidos = [self.miembros[0]]
        docs = {self.miembros[0].documento}
        for m in self.miembros[1:]:
            if len(elegidos) >= MUESTRA_POR_GRUPO:
                break
            if m.documento not in docs:
                elegidos.append(m)
                docs.add(m.documento)
        for m in self.miembros[1:]:
            if len(elegidos) >= MUESTRA_POR_GRUPO:
                break
            if m not in elegidos:
                elegidos.append(m)
        return elegidos


def agrupar(cambios: list[Cambio]) -> list[Grupo]:
    por_firma: dict[str, Grupo] = {}
    for c in sorted(cambios, key=lambda c: (c.documento, c.clave)):
        f = firma(c.antes, c.despues)
        g = por_firma.get(f)
        if g is None:
            g = por_firma[f] = Grupo(f"g{len(por_firma) + 1:03d}", f)
        g.miembros.append(c)
    # Primero los grupos grandes: con el tope, se cubre más corpus.
    return sorted(por_firma.values(), key=lambda g: -len(g.miembros))


def diff_parrafos(antes: str | None, despues: str | None) -> str:
    a = (antes or "").split("\n\n")
    d = (despues or "").split("\n\n")
    return "\n".join(difflib.unified_diff(a, d, "publicado", "propuesto", lineterm="", n=1))


# ------------------------------------------------------------------ exportar

def exportar(cambios: list[Cambio], trabajo: str | Path, pdfs: dict[str, str], *,
             registro: dict[Clave, dict] | None = None, origen: str = "") -> dict:
    """Deja en `trabajo` lo que falta verificar: `pendientes.json` (grupos con
    sus miembros) y, por miembro, el texto antes/después y su diff. Lo ya
    juzgado en el registro no se exporta. Devuelve el resumen."""
    registro = registro if registro is not None else cargar()
    t = Path(trabajo)
    t.mkdir(parents=True, exist_ok=True)
    nuevos, juzgados = [], {"mejora": 0, "empeora": [], "incierto": []}
    for c in cambios:
        v = veredicto(registro, c)
        if v is None:
            nuevos.append(c)
        elif v == "mejora":
            juzgados["mejora"] += 1
        else:
            juzgados[v].append(f"{c.documento}:{c.clave}")
    grupos = agrupar(nuevos)
    revisar, sin_revisar = grupos[:MAX_GRUPOS], grupos[MAX_GRUPOS:]
    salida = []
    for g in revisar:
        miembros = []
        muestra = g.muestra()
        for c in g.miembros:
            base = t / "textos" / c.documento.replace("/", "__") / c.clave
            base.parent.mkdir(parents=True, exist_ok=True)
            for sufijo, texto in ((".antes.md", c.antes), (".despues.md", c.despues)):
                if texto is not None:
                    (base.parent / (base.name + sufijo)).write_text(texto, encoding="utf-8")
            (base.parent / (base.name + ".diff")).write_text(
                diff_parrafos(c.antes, c.despues) + "\n", encoding="utf-8")
            miembros.append({
                "documento": c.documento, "clave": c.clave, "pdf_sha256": c.pdf,
                "pdf": pdfs.get(c.pdf), "revisar": c in muestra,
                "antes": str(base) + ".antes.md" if c.antes is not None else None,
                "despues": str(base) + ".despues.md" if c.despues is not None else None,
                "diff": str(base) + ".diff",
                "huella_antes": huella(c.antes), "huella_despues": huella(c.despues)})
        salida.append({"id": g.id, "firma": g.firma, "miembros": miembros})
    resumen = {"origen": origen, "cambios": len(cambios), "ya_mejora": juzgados["mejora"],
               "ya_empeora": juzgados["empeora"], "ya_incierto": juzgados["incierto"],
               "pendientes": sum(len(g.miembros) for g in revisar),
               "grupos": len(revisar),
               "sin_revisar": [f"{c.documento}:{c.clave}" for g in sin_revisar for c in g.miembros]}
    (t / "pendientes.json").write_text(json.dumps({"resumen": resumen, "grupos": salida},
                                                  ensure_ascii=False, indent=1) + "\n",
                                       encoding="utf-8")
    return resumen


# ------------------------------------------------------------------ cerrar

def veredictos(trabajo: str | Path) -> dict[str, dict]:
    """Veredicto por grupo de todos los `veredicto*.json` (uno por sesión del
    agente)."""
    res: dict[str, dict] = {}
    for p in sorted(Path(trabajo).glob("veredicto*.json")):
        try:
            v = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        for g in v.get("grupos", []) if isinstance(v, dict) else []:
            if isinstance(g, dict) and g.get("id"):
                res[str(g["id"])] = g
    return res


def cerrar(trabajo: str | Path, extractor: str, registro_dir: str | Path = REGISTRO,
           nombre: str | None = None) -> tuple[bool, dict]:
    """Pasa al registro el veredicto del agente (`veredicto.json`) de cada
    grupo exportado (`veredicto*.json`). Verdadero si todo lo exportado quedó como mejora y no hay
    nada juzgado antes como peor o incierto ni sin revisar."""
    t = Path(trabajo)
    p = t / "pendientes.json"
    if not p.exists():
        return True, {"mejora": 0, "rechazados": [], "sin_veredicto": []}
    pend = json.loads(p.read_text(encoding="utf-8"))
    por_grupo = veredictos(t)
    hoy = date.today().isoformat()
    entradas, rechazados, sin_veredicto, mejora = [], [], [], 0
    for g in pend["grupos"]:
        dado = por_grupo.get(g["id"]) or {}
        ver = dado.get("veredicto")
        if ver not in VEREDICTOS:
            sin_veredicto += [f"{m['documento']}:{m['clave']}" for m in g["miembros"]]
            continue
        for m in g["miembros"]:
            entradas.append({"documento": m["documento"], "clave": m["clave"],
                             "pdf": m["pdf_sha256"], "antes": m["huella_antes"],
                             "despues": m["huella_despues"], "veredicto": ver,
                             "grupo": g["id"], "nota": str(dado.get("nota", ""))[:500],
                             "extractor": extractor, "fecha": hoy})
            if ver == "mejora":
                mejora += 1
            else:
                rechazados.append(f"{m['documento']}:{m['clave']} ({ver})")
    if not nombre:
        import uuid
        nombre = f"{hoy}-{extractor.rsplit('@', 1)[-1][:7]}-{uuid.uuid4().hex[:6]}"
    escribir(entradas, registro_dir, nombre)
    r = pend["resumen"]
    rechazados += [f"{x} (empeora)" for x in r.get("ya_empeora", [])]
    rechazados += [f"{x} (incierto)" for x in r.get("ya_incierto", [])]
    sin_veredicto += r.get("sin_revisar", [])
    res = {"mejora": mejora + r.get("ya_mejora", 0), "rechazados": rechazados,
           "sin_veredicto": sin_veredicto}
    return not rechazados and not sin_veredicto, res


def reporte(res: dict) -> str:
    l = [f"Correcciones confirmadas como mejora: {res['mejora']}."]
    if res["rechazados"]:
        l.append(f"Rechazadas ({len(res['rechazados'])}): " + ", ".join(res["rechazados"][:30]))
    if res["sin_veredicto"]:
        l.append(f"Sin verificar ({len(res['sin_veredicto'])}): "
                 + ", ".join(res["sin_veredicto"][:30]))
    return "\n".join(l)


# ------------------------------------------------------------------ commits

def _git(repo: str, *args: str, binario: bool = False):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, check=True)
    return r.stdout if binario else r.stdout.decode("utf-8")


def _indice_pdfs(dirs: list[str]) -> dict[str, str]:
    res = {}
    for d in dirs:
        for p in sorted(Path(d).rglob("*.pdf")):        # leyes estatales: en subcarpetas
            res[tr.sha256_bytes(p.read_bytes())] = str(p)
    return res


def correcciones_de_commits(repo: str, base: str, head: str = "HEAD"
                            ) -> list[tuple[str, str, str, dict]]:
    """(commit, documento, sha256 del PDF, cambios) de cada commit
    `Tipo: correccion` entre base y head."""
    res = []
    for c in _git(repo, "rev-list", "--reverse", f"{base}..{head}").split():
        _, t = tr.parsear(_git(repo, "log", "-1", "--format=%B", c))
        if tr.valor(t, "Tipo") != "correccion":
            continue
        doc, pdf = tr.valor(t, "Documento"), tr.valor(t, "Fuente-Sha256") or "-"
        rutas = [r for r in _git(repo, "diff-tree", "-r", "--no-commit-id", "--name-only",
                                 "--no-renames", "-z", f"{c}^", c).split("\0") if r]
        cambios = tr.cambios_de_articulos(doc, rutas, tr.lector_git(repo, f"{c}^"),
                                          tr.lector_git(repo, c))
        res.append((c, doc, pdf, cambios))
    return res


def _pdfs_de_fuente(repo: str, commits: list[tuple[str, str]], destino: Path) -> dict[str, str]:
    """Las constituciones guardan su PDF en `fuente/`: el de antes y el de
    después de cada commit (commit, documento) quedan disponibles para el
    agente."""
    res = {}
    destino.mkdir(parents=True, exist_ok=True)
    for c, doc in commits:
        for rev in (f"{c}^", c):
            leer = tr.lector_git(repo, rev)
            for r in tr.rutas_fuente(doc):
                datos = leer(r) if r.endswith(".pdf") else None
                if datos is None:
                    continue
                sha = tr.sha256_bytes(datos)
                if sha not in res:
                    p = destino / f"{sha[:16]}.pdf"
                    p.write_bytes(datos)
                    res[sha] = str(p)
    return res


def aprobados_por_agente(veredicto: str | Path, cambios: list[Cambio], pdfs: set[str],
                         extractor: str) -> list[dict]:
    """Entradas de registro para las correcciones que el agente de la
    vigilancia ya verificó: unidades que su veredicto declara `fiel` contra el
    mismo PDF del que sale el commit, con fidelidad global. Así no se paga dos
    veces la misma revisión."""
    try:
        v = json.loads(Path(veredicto).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if v.get("fiel") is not True:
        return []
    fieles = {str(u.get("clave")): str(u.get("nota", ""))[:500] for u in v.get("unidades", [])
              if isinstance(u, dict) and u.get("veredicto") == "fiel"}
    hoy = date.today().isoformat()
    res = []
    for c in cambios:
        nota = fieles.get(f"{c.documento}/{c.clave}", fieles.get(c.clave))
        if nota is None or c.pdf not in pdfs or c.despues is None:
            continue
        llave = c.llave
        res.append({"documento": c.documento, "clave": c.clave, "pdf": c.pdf,
                    "antes": llave[3], "despues": llave[4], "veredicto": "mejora",
                    "grupo": "vigilancia", "nota": f"verificado por el agente de la vigilancia: {nota}",
                    "extractor": extractor, "fecha": hoy})
    return res


def _descargar(repo: str, commits: list[str], faltan: set[str], destino: Path) -> dict[str, str]:
    """Los PDF que no se versionan (fiscal, federal) se vuelven a descargar de
    la Fuente del commit; solo valen si su sha256 es el declarado."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from extractor.fuentes import descargar
    except ImportError:
        return {}
    res = {}
    destino.mkdir(parents=True, exist_ok=True)
    for c in commits:
        _, t = tr.parsear(_git(repo, "log", "-1", "--format=%B", c))
        sha, url = tr.valor(t, "Fuente-Sha256"), tr.valor(t, "Fuente")
        if sha not in faltan or sha in res or not url:
            continue
        p = destino / f"{sha[:16]}.pdf"
        try:
            descargar(url, str(p))
        except Exception:                            # noqa: BLE001 — queda sin PDF
            continue
        if tr.sha256_bytes(p.read_bytes()) == sha:
            res[sha] = str(p)
    return res


def cmd_pendientes_commits(a) -> int:
    corr = correcciones_de_commits(a.repo, a.base)
    cambios = [Cambio(doc, clave, pdf, x, y) for _, doc, pdf, cs in corr
               for clave, (x, y) in cs.items()]
    pdfs = _indice_pdfs(a.pdf_dir or [])
    if a.veredicto_agente and a.extractor:
        import uuid
        previos = cargar(a.registro)
        nuevos = [e for e in aprobados_por_agente(a.veredicto_agente, cambios, set(pdfs), a.extractor)
                  if (e["documento"], e["clave"], e["pdf"], e["antes"], e["despues"]) not in previos]
        escribir(nuevos, a.registro, f"{date.today().isoformat()}-vigilancia-{uuid.uuid4().hex[:6]}")
        if nuevos:
            print(f"{len(nuevos)} correcciones ya verificadas por el agente de la vigilancia.")
    faltan = {c.pdf for c in cambios} - set(pdfs)
    if faltan:
        pdfs.update(_pdfs_de_fuente(a.repo, [(c, doc) for c, doc, *_ in corr],
                                    Path(a.trabajo) / "pdfs"))
    faltan = {c.pdf for c in cambios} - set(pdfs)
    if faltan:
        pdfs.update(_descargar(a.repo, [c for c, *_ in corr], faltan, Path(a.trabajo) / "pdfs"))
    r = exportar(cambios, a.trabajo, pdfs, registro=cargar(a.registro),
                 origen=f"commits {a.base[:9]}..HEAD de {Path(a.repo).name}")
    print(f"{len(corr)} commits de corrección, {r['cambios']} artículos: "
          f"{r['ya_mejora']} ya confirmados, {r['pendientes']} por verificar en "
          f"{r['grupos']} grupos, {len(r['ya_empeora']) + len(r['ya_incierto'])} rechazados antes.")
    _salida_gh(pendientes="true" if r["pendientes"] else "false")
    return 0


def cmd_cerrar(a) -> int:
    ok, res = cerrar(a.trabajo, a.extractor, a.registro, a.nombre)
    print(reporte(res))
    if a.reporte:
        Path(a.reporte).write_text(reporte(res) + "\n", encoding="utf-8")
    return 0 if ok else 2


def cmd_exigir(a) -> int:
    """Sale 1 si alguna corrección entre base y HEAD no está confirmada."""
    registro = cargar(a.registro)
    malos = []
    for c, doc, pdf, cambios in correcciones_de_commits(a.repo, a.base):
        f = faltantes(registro, doc, pdf, cambios)
        if f:
            malos.append(f"{doc} ({c[:9]}): {', '.join(f[:10])}")
    for m in malos:
        print(f"✗ corrección sin confirmar: {m}")
    if not malos:
        print("✓ toda corrección está confirmada como mejora.")
    _salida_gh(rehacer="true" if malos else "false")
    return 1 if malos else 0


def cmd_ya_confirmadas(a) -> int:
    """Sale 0 si todo lo que cambió en el árbol de trabajo de estos documentos
    son correcciones ya confirmadas contra el mismo PDF: entonces el agente de
    la vigilancia no tiene nada nuevo que revisar."""
    if len(a.documento) != len(a.pdf):
        raise SystemExit("cada --documento lleva su --pdf")
    registro = cargar(a.registro)
    antes, despues = tr.lector_git(a.repo, "HEAD"), tr.lector_fs(a.repo)
    total = 0
    for doc, pdf in zip(a.documento, a.pdf):
        rutas = [r for r in _git(a.repo, "status", "--porcelain", "-z", "--no-renames", "-uall")
                 .split("\0") if r]
        rutas = [r[3:] for r in rutas]
        cambios = tr.cambios_de_articulos(doc, rutas, antes, despues)
        sha = tr.sha256_bytes(Path(pdf).read_bytes()) if Path(pdf).exists() else "-"
        f = faltantes(registro, doc, sha, cambios)
        if f:
            print(f"{doc}: {len(f)} de {len(cambios)} artículos sin confirmar")
            return 1
        total += len(cambios)
    print(f"Los {total} artículos cambiados son correcciones ya confirmadas contra el PDF.")
    return 0 if total else 1


def _salida_gh(**pares) -> None:
    import os
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
            for k, v in pares.items():
                fh.write(f"{k}={v}\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pendientes-commits")
    p.add_argument("repo")
    p.add_argument("--base", required=True)
    p.add_argument("--trabajo", required=True)
    p.add_argument("--pdf-dir", action="append")
    p.add_argument("--registro", default=str(REGISTRO))
    p.add_argument("--veredicto-agente", default=None,
                   help="veredicto.json del agente de la vigilancia (sus unidades fieles cuentan)")
    p.add_argument("--extractor", default=None)
    c = sub.add_parser("cerrar")
    c.add_argument("--trabajo", required=True)
    c.add_argument("--extractor", required=True)
    c.add_argument("--registro", default=str(REGISTRO))
    c.add_argument("--nombre", default=None)
    c.add_argument("--reporte", default=None)
    e = sub.add_parser("exigir")
    e.add_argument("repo")
    e.add_argument("--base", required=True)
    e.add_argument("--registro", default=str(REGISTRO))
    y = sub.add_parser("ya-confirmadas")
    y.add_argument("repo")
    y.add_argument("--documento", action="append", default=[])
    y.add_argument("--pdf", action="append", default=[])
    y.add_argument("--registro", default=str(REGISTRO))
    a = ap.parse_args(argv)
    return {"pendientes-commits": cmd_pendientes_commits, "cerrar": cmd_cerrar,
            "exigir": cmd_exigir, "ya-confirmadas": cmd_ya_confirmadas}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
