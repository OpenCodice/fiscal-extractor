#!/usr/bin/env python3
"""Reparación autónoma del extractor a partir de los hallazgos de la revisión
completa (y, en las leyes estatales, de la auditoría determinista).

Una ley con defectos de extracción queda fuera (o conserva su versión anterior,
con `revision_pendiente`) y nadie la repara a mano. Este script es la parte
determinista del agente que lo hace (`scripts/agente/reparar.sh`):

  objetivo  — junta los hallazgos de las leyes con defectos (las de esta
              corrida y las que fuentes.json tiene fuera o con
              `revision_pendiente`), los agrupa por tipo de defecto y elige un
              grupo: el que más leyes comparte, hasta `--max-leyes`, para que un
              solo arreglo atienda varias. Una ley con TOPE intentos con el mismo
              PDF ya no entra (extractor/reparaciones.py).
  preparar  — descarga el PDF de cada ley elegida y comprueba que sea el mismo
              que se revisó (si cambió, la ley sale del grupo: la vigilancia la
              reprocesa entera).
  registrar — anota el intento en verificaciones/reparaciones/ (iniciado, y
              luego publicado o descartado).
  construir — reconstruye y audita las leyes elegidas con un extractor dado.
  comparar  — el arreglo frente al extractor de partida en esas leyes: ninguna
              unidad con problemas nueva y algún texto distinto.
  fuera     — (leyes estatales) descarga, construye y audita las leyes que un
              módulo deja en FUERA sin ser por diseño (`FUERA_POR_DISENO`): las
              que fallan entran en `objetivo` (`--fuera`), con el mismo tope
              por ley y PDF; las que ya quedan limpias, en `promover`.
  promover  — pasa de FUERA a LEYES, en su módulo, las leyes que quedaron con
              build y auditar limpios (con el extractor de main, o con el
              arreglo que se acaba de publicar): un bloque al final del módulo,
              sin tocar lo demás. Después las da de alta la vigilancia, con su
              revisión completa, como a cualquier ley nueva.

Uso:
  reparacion.py objetivo  --corpus estatal|federal --out REPO --trabajo T [--max-leyes N] [--con-auditoria]
  reparacion.py preparar  --trabajo T --pdfs DIR [--pdfs DIR2]
  reparacion.py registrar --trabajo T --resultado iniciado|publicado|descartado [--motivo M] [--extractor S]
  reparacion.py construir --trabajo T --extractor-dir E --pdfs DIR --out DIR
  reparacion.py comparar  --trabajo T --antes DIR --despues DIR
  reparacion.py fuera     --trabajo T --pdfs DIR --salida J [--cache DIR] [--max N] [--estado E] [--solo-fuente]
  reparacion.py promover  --resultado J [--resultado J2 …] [--raiz EXTRACTOR]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

EXTRACTOR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EXTRACTOR))
from extractor import reparaciones  # noqa: E402

ALTAS = EXTRACTOR / "verificaciones" / "altas"
DEFECTOS = "encontró defectos de extracción: "

# Tipos de defecto, en orden: el primero que casa con la nota decide.
CATEGORIAS = [
    ("absorcion", "un artículo absorbió a otro, o falta el archivo de un artículo",
     r"absorbi|qued[óo] dentro|dentro del archivo|falta (?:su |el )?archivo|sin archivo"
     r"|no tiene archivo|dos renglones «?art"),
    ("nota_reforma", "notas de reforma o fe de erratas mal separadas del texto",
     r"\bnotas?\b|fe de erratas|\(ref\.|p\.\s*o\.|g\.\s*o\."),
    ("corte_parrafo", "párrafos partidos a media oración o unidos de más",
     r"partid|media oraci[óo]n|p[áa]rrafo suelto|en dos p[áa]rrafos|un solo p[áa]rrafo"
     r"|unid[oa]s?\b|separad|rengl[óo]n aparte|qued[óo] como p[áa]rrafo"),
    ("pagina", "pies, encabezados o números de página colados",
     r"pie\b|pie de p[áa]gina|encabezado de p[áa]gina|n[úu]mero de p[áa]gina"),
    ("estructura", "encabezados de estructura (títulos, capítulos, epígrafes) fuera de lugar",
     r"ep[íi]grafe|cap[íi]tulo|t[íi]tulo|secci[óo]n|r[óo]tulo"),
    ("auditoria", "la auditoría determinista: texto que no reproduce el PDF",
     r"^auditor[íi]a:"),
]


def categoria(nota: str) -> str:
    n = nota.lower()
    for nombre, _, patron in CATEGORIAS:
        if re.search(patron, n):
            return nombre
    return "otro"


def _leer(ruta, defecto=None):
    p = Path(ruta)
    if not p.exists():
        return defecto
    return json.loads(p.read_text(encoding="utf-8"))


def _escribir(ruta, datos) -> None:
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    Path(ruta).write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _salida_gh(**pares) -> None:
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
            for k, v in pares.items():
                fh.write(f"{k}={v}\n")


# ------------------------------------------------------------------ hallazgos

def de_motivo(motivo: str) -> list[dict]:
    """Los hallazgos que el motivo de una exclusión resume ('…: 150-bis: el
    artículo absorbió…; 155: la conjunción…  (y 3 más)')."""
    if DEFECTOS not in motivo:
        return []
    resto = motivo.split(DEFECTOS, 1)[1]
    resto = re.sub(r"\s*\(y \d+ más\)\s*$", "", resto)
    resto = re.split(r"\s+Sin arreglo automático", resto)[0]
    res = []
    for parte in re.split(r";\s+(?=[0-9a-z][\w-]*:\s)", resto):
        clave, _, nota = parte.partition(": ")
        if nota:
            res.append({"clave": clave.strip(), "nota": nota.strip()})
    return res


def de_revision(rev: Path, sha: str) -> list[dict] | None:
    """Hallazgos de la revisión de esta corrida (o de la caché): los de los
    bloques del documento tal como quedó, no los de bloques ya cambiados."""
    resultado, plan = _leer(rev / "resultado.json"), _leer(rev / "plan.json")
    if not resultado or not plan or resultado.get("pdf") != sha \
            or resultado.get("resultado") != "hallazgos":
        return None
    vigentes = {b["huella"] for b in plan.get("bloques", [])}
    res = []
    for p in sorted(rev.glob("veredicto*.json")):
        try:
            v = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        for b in v.get("bloques", []) if isinstance(v, dict) else []:
            if isinstance(b, dict) and b.get("huella") in vigentes:
                for h in b.get("hallazgos") or []:
                    if isinstance(h, dict):
                        res.append({"clave": str(h.get("clave", b.get("id"))),
                                    "nota": str(h.get("nota", ""))[:600]})
    return res or None


def de_registro(documento: str, sha: str, registro: Path = ALTAS) -> list[dict] | None:
    ultimo = None
    for archivo in sorted(registro.glob("*.jsonl")) if registro.is_dir() else []:
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(linea) if linea.strip() else None
            except ValueError:
                continue
            if e and e.get("documento") == documento and e.get("pdf") == sha:
                ultimo = e
    if not ultimo or ultimo.get("resultado") != "hallazgos":
        return None
    return ultimo.get("hallazgos") or de_motivo(ultimo.get("motivo", "")) or None


def de_auditoria(r: dict) -> list[dict]:
    res = []
    for ref, problemas in (r.get("problemas") or {}).items():
        p = (problemas or [{}])[0]
        res.append({"clave": ref.rsplit("/", 1)[-1],
                    "nota": f"auditoría: {p.get('tipo', '?')}: «{str(p.get('fragmento', ''))[:300]}»"})
    for inv in r.get("invariantes") or []:
        res.append({"clave": "-", "nota": f"auditoría: invariante roto: {inv[:300]}"})
    if r.get("error"):
        res.append({"clave": "-", "nota": f"auditoría: {r['error'][:300]}"})
    return res


# ------------------------------------------------------------------ objetivo

def descartes_previos(documento: str, pdf_sha: str, registros: list[dict],
                      maximo: int = 3, largo: int = 300) -> list[dict]:
    """Por qué se descartaron los intentos anteriores de reparar `documento`
    con ese PDF, del más antiguo al más reciente (los últimos `maximo`). El
    agente los recibe con sus hallazgos para no entregar otra vez lo mismo."""
    res = []
    for e in registros:
        if e["documento"] == documento and e.get("pdf") == pdf_sha \
                and e.get("resultado") == "descartado":
            motivo = " ".join(str(e.get("motivo") or "").split())
            if len(motivo) > largo:
                motivo = motivo[:largo].rstrip() + "…"
            res.append({"intento": e["intento"], "fecha": e.get("fecha"), "motivo": motivo})
    return res[-maximo:]


def _corpus_docs(corpus: str, fuentes: dict) -> set[str]:
    if corpus == "estatal":
        from extractor.estatales import documentos, fuera
        return {d.clave for d in documentos()} - set(fuera())
    from extractor.federal import FUERA_DEL_CORPUS
    return {d["clave"] for d in fuentes.get("documentos", [])} - set(FUERA_DEL_CORPUS)


def candidatos(corpus: str, out: Path, trabajo: Path, con_auditoria: bool,
               registros: list[dict], altas: Path = ALTAS,
               fuera: dict | None = None) -> list[dict]:
    fuentes = _leer(out / "fuentes.json", {"documentos": []})
    declarados = _corpus_docs(corpus, fuentes)
    resultados = _leer(trabajo / "resultados.json", {}) or {}
    por_clave: dict[str, dict] = {}

    def hallazgos(clave: str, sha: str, motivo: str) -> list[dict]:
        return (de_revision(trabajo / "revision" / clave, sha)
                or de_registro(clave, sha, altas) or de_motivo(motivo))

    for e in fuentes.get("documentos", []):
        clave = e.get("clave")
        if clave not in declarados:
            continue
        if e.get("estado") == "excluida" and not (e.get("reparacion") or {}).get("agotada"):
            sha, motivo = (e.get("pdf") or {}).get("sha256"), e.get("motivo", "")
        elif e.get("estado") == "incluida" and (e.get("revision_pendiente") or {}).get("revisada") \
                and not e["revision_pendiente"].get("agotada"):
            rp = e["revision_pendiente"]
            sha, motivo = (rp.get("pdf") or {}).get("sha256"), rp.get("motivo", "")
        else:
            continue
        if not sha:
            continue
        hs = hallazgos(clave, sha, motivo)
        if not hs and con_auditoria and "no reproducen el PDF" in motivo:
            hs = [{"clave": "-", "nota": f"auditoría: {motivo[:400]}"}]
        if hs:
            por_clave[clave] = {"clave": clave, "pdf_sha256": sha, "url": e.get("url"),
                                "hallazgos": hs, "origen": "registro"}
    # Lo de esta corrida manda sobre lo registrado.
    for clave, r in resultados.items():
        if clave not in declarados or r.get("error_fuente") or r.get("sin_cambio") or not r.get("sha256"):
            continue
        hs = []
        if r.get("revision") and DEFECTOS in r["revision"]:
            hs = hallazgos(clave, r["sha256"], r["revision"])
        elif con_auditoria and (r.get("problemas") or r.get("invariantes") or r.get("error")):
            hs = de_auditoria(r)
        if hs:
            por_clave[clave] = {"clave": clave, "pdf_sha256": r["sha256"], "url": r.get("url"),
                                "hallazgos": hs, "origen": "corrida"}
    # Las que un módulo deja en FUERA y fallan la auditoría (`cmd_fuera`): la
    # vigilancia nunca las intenta, así que solo aquí se reparan.
    for clave, r in (fuera or {}).items():
        if clave in por_clave or not r.get("sha256") or es_limpia(r):
            continue
        hs = de_auditoria(r)
        if hs:
            por_clave[clave] = {"clave": clave, "pdf_sha256": r["sha256"], "url": r.get("url"),
                                "hallazgos": hs, "origen": "fuera"}
    res = []
    for c in sorted(por_clave):
        e = por_clave[c]
        e["intentos"] = reparaciones.intentos(c, e["pdf_sha256"], registros)
        if e["intentos"] >= reparaciones.TOPE:
            continue
        e["descartes"] = descartes_previos(c, e["pdf_sha256"], registros)
        for h in e["hallazgos"]:
            h["categoria"] = categoria(h["nota"])
        res.append(e)
    return res


def elegir(cands: list[dict], max_leyes: int) -> tuple[str | None, list[dict]]:
    """El tipo de defecto que más leyes comparten (a igualdad, más hallazgos) y
    esas leyes, primero las de menos intentos."""
    leyes, total = Counter(), Counter()
    for e in cands:
        cats = Counter(h["categoria"] for h in e["hallazgos"])
        for c, n in cats.items():
            leyes[c] += 1
            total[c] += n
    if not leyes:
        return None, []
    grupo = max(leyes, key=lambda c: (c != "otro", leyes[c], total[c], c))
    elegidas = [e for e in cands if any(h["categoria"] == grupo for h in e["hallazgos"])]
    elegidas.sort(key=lambda e: (e["intentos"],
                                 -sum(h["categoria"] == grupo for h in e["hallazgos"]), e["clave"]))
    return grupo, elegidas[:max_leyes]


def cmd_objetivo(a) -> int:
    out, t = Path(a.out), Path(a.trabajo)
    registros = reparaciones.cargar(a.registro)
    fuera = (_leer(a.fuera) or {}) if a.fuera else {}
    cands = candidatos(a.corpus, out, t, a.con_auditoria, registros, fuera=fuera)
    grupo, elegidas = elegir(cands, a.max_leyes)
    rep = t / "reparacion"
    rep.mkdir(parents=True, exist_ok=True)
    print(f"{len(cands)} leyes con defectos y menos de {reparaciones.TOPE} intentos de reparación.")
    if not elegidas:
        (rep / "objetivo.json").unlink(missing_ok=True)
        _salida_gh(hay="false")
        return 0
    # Definiciones para construir: fuentes.json y el plan de esta corrida.
    fuentes = _leer(out / "fuentes.json", {"documentos": []})
    defs = {d["clave"]: d for d in fuentes.get("documentos", [])}
    for d in (_leer(a.plan) or {}).get("documentos", []) if a.plan else []:
        defs[d["clave"]] = d
    for c, r in fuera.items():
        if r.get("definicion"):
            defs.setdefault(c, r["definicion"])
    _escribir(rep / "registro.json", {"documentos": list(defs.values())})
    hora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
    descripcion = dict((n, d) for n, d, _ in CATEGORIAS).get(grupo, "otros defectos")
    objetivo = {"corpus": a.corpus, "grupo": grupo, "descripcion": descripcion,
                "intento": f"{hora}-{uuid.uuid4().hex[:6]}",
                "leyes": elegidas, "otras": sorted(e["clave"] for e in cands if e not in elegidas)}
    _escribir(rep / "objetivo.json", objetivo)
    print(f"Grupo «{grupo}» ({descripcion}): " + ", ".join(
        f"{e['clave']} ({sum(h['categoria'] == grupo for h in e['hallazgos'])} hallazgos, "
        f"{e['intentos']} intentos)" for e in elegidas))
    _salida_gh(hay="true")
    return 0


# ------------------------------------------------------------------ preparar

def cmd_preparar(a) -> int:
    from extractor import federal, registro
    from extractor.fuentes import descargar, url_vigente
    rep = Path(a.trabajo) / "reparacion"
    obj = _leer(rep / "objetivo.json")
    registro.cargar(rep / "registro.json")
    quedan = []
    for e in obj["leyes"]:
        doc = registro.POR_CLAVE.get(e["clave"])
        destinos = [Path(d) / f"{e['clave']}.pdf" for d in a.pdfs]
        try:
            url = e.get("url") or url_vigente(doc)
            destinos[0].parent.mkdir(parents=True, exist_ok=True)
            descargar(url, str(destinos[0]), via=getattr(doc, "via", None))
        except Exception as ex:                       # noqa: BLE001 — sin PDF no se repara
            print(f"✗ {e['clave']}: no se pudo descargar su PDF ({type(ex).__name__}: {ex})")
            continue
        sha = federal.sha256(destinos[0])
        if sha != e["pdf_sha256"]:
            print(f"✗ {e['clave']}: su PDF ya no es el revisado; la vigilancia lo reprocesa")
            destinos[0].unlink()
            continue
        for d in destinos[1:]:
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(destinos[0], d)
        quedan.append(e)
    obj["leyes"] = quedan
    _escribir(rep / "objetivo.json", obj)
    print(f"{len(quedan)} leyes listas para reparar.")
    _salida_gh(hay="true" if quedan else "false")
    return 0


# ------------------------------------------------------------------ registrar

def cmd_registrar(a) -> int:
    obj = _leer(Path(a.trabajo) / "reparacion" / "objetivo.json")
    if not obj or not obj.get("leyes"):
        return 0
    d = Path(a.registro)
    d.mkdir(parents=True, exist_ok=True)
    hoy = date.today().isoformat()
    with (d / f"{obj['intento']}.jsonl").open("a", encoding="utf-8") as fh:
        for e in obj["leyes"]:
            fh.write(json.dumps({"documento": e["clave"], "pdf": e["pdf_sha256"],
                                 "intento": obj["intento"], "grupo": obj["grupo"],
                                 "resultado": a.resultado, "motivo": (a.motivo or "")[:600],
                                 "extractor": a.extractor, "fecha": hoy},
                                ensure_ascii=False, sort_keys=True) + "\n")
    return 0


# ------------------------------------------------------------------ construir / comparar

def cmd_construir(a) -> int:
    """Construye y audita cada ley elegida con el extractor de `--extractor-dir`.
    Escribe `<out>/resultado.json`: por ley, error, unidades y las que tienen
    problemas. Sale 0 aunque una ley falle: lo decide `comparar`."""
    rep = Path(a.trabajo) / "reparacion"
    obj = _leer(rep / "objetivo.json")
    registro = str((rep / "registro.json").resolve())
    out = Path(a.out)
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    env = {**os.environ, "PYTHONPATH": str(Path(a.extractor_dir).resolve())}
    res = {}
    for e in obj["leyes"]:
        c = e["clave"]
        pdf = str((Path(a.pdfs) / f"{c}.pdf").resolve())
        datos = out / "datos"
        r = subprocess.run([sys.executable, "-m", "extractor", "--registro", registro, "build",
                            "--doc", c, "--pdf", pdf, "--out", str(datos), "--sin-pasajes"],
                           cwd=a.extractor_dir, env=env, capture_output=True, text=True, timeout=1800)
        if r.returncode != 0:
            res[c] = {"error": (r.stderr.strip().splitlines() or ["?"])[-1][:300]}
            continue
        sola = out / "pdf" / c.replace("/", "__")
        (sola / f"{c}.pdf").parent.mkdir(parents=True, exist_ok=True)
        (sola / f"{c}.pdf").symlink_to(pdf)
        j = out / f"auditoria-{c.replace('/', '__')}.json"
        r = subprocess.run([sys.executable, "-m", "extractor", "--registro", registro, "auditar",
                            "--out", str(datos), "--pdf-dir", str(sola), "--json", str(j)],
                           cwd=a.extractor_dir, env=env, capture_output=True, text=True, timeout=1800)
        if r.returncode != 0 or not j.exists():
            res[c] = {"error": "no se pudo auditar: " + (r.stderr.strip().splitlines() or ["?"])[-1][:300]}
            continue
        aud = json.loads(j.read_text(encoding="utf-8"))
        res[c] = {"unidades": aud.get("total", 0), "problemas": sorted(aud.get("con_problemas", {}))}
    _escribir(out / "resultado.json", res)
    return 0


def _textos(raiz: Path, clave: str) -> dict[str, bytes]:
    from extractor.disposicion import dir_unidades
    return {p.stem: p.read_bytes() for p in dir_unidades(raiz / "datos", clave).glob("*.md")}


def comparar(obj: dict, antes: Path, despues: Path) -> tuple[bool, str, list[str]]:
    """¿El arreglo no empeora la auditoría de ninguna ley elegida y cambia el
    texto de alguna? Devuelve (aceptable, motivo, leyes que cambian)."""
    ra, rd = _leer(antes / "resultado.json"), _leer(despues / "resultado.json")
    if not ra or not rd:
        return False, "no se pudieron reconstruir las leyes elegidas", []
    cambian = []
    for e in obj["leyes"]:
        c = e["clave"]
        a, d = ra.get(c), rd.get(c)
        if a is None or d is None:
            return False, f"{c}: no se reconstruyó", []
        if d.get("error") and not a.get("error"):
            return False, f"{c}: el arreglo rompe su extracción ({d['error']})", []
        if d.get("error"):
            continue
        if not d.get("unidades"):
            return False, f"{c}: la auditoría no revisó ninguna unidad", []
        if not a.get("error"):
            nuevas = sorted(set(d["problemas"]) - set(a["problemas"]))
            if nuevas:
                return False, f"{c}: unidades con problemas nuevos ({', '.join(nuevas[:5])})", []
        if a.get("error") or _textos(antes, c) != _textos(despues, c):
            cambian.append(c)
    if not cambian:
        return False, "no cambia el texto de ninguna de las leyes con hallazgos", []
    return True, "", cambian


def cmd_comparar(a) -> int:
    obj = _leer(Path(a.trabajo) / "reparacion" / "objetivo.json")
    ok, motivo, cambian = comparar(obj, Path(a.antes), Path(a.despues))
    if ok:
        print("OK " + " ".join(cambian))
        return 0
    print(f"NO {motivo}")
    return 2


# ------------------------------------------------------------------ fuera / promover

def es_limpia(r: dict) -> bool:
    from extractor.federal import es_fiel
    return bool(r.get("unidades")) and es_fiel(r)


def reparables() -> dict:
    """Clave → definición de las leyes en FUERA que no lo están por diseño."""
    from extractor.estatales import fuera, fuera_por_diseno
    diseno = fuera_por_diseno()
    return {c: d for c, (d, _) in fuera().items() if c not in diseno}


class NoEsPdf(ValueError):
    pass


def causa_fuente(e: Exception) -> str:
    """Por qué no se pudo obtener el PDF: `codigo` si el extractor no sabe
    resolver o pedir lo que el sitio publica (un href con un espacio que
    http.client rechaza, ningún enlace que case, una URL que el servidor no
    entiende), `red` si es del sitio o de la conexión (caído, lento, un 404,
    una página de error en vez del PDF). Solo lo de `codigo` lo puede
    arreglar un agente (expandir-estatales.yml con `redeclarar`); una caída
    de red no gasta sus intentos."""
    import http.client
    import urllib.error
    if isinstance(e, urllib.error.HTTPError):
        return "codigo" if e.code in (400, 414) else "red"
    if isinstance(e, (http.client.InvalidURL, LookupError, UnicodeError)):
        return "codigo"
    if isinstance(e, ValueError) and not isinstance(e, NoEsPdf):
        return "codigo"                      # 'unknown url type' de urllib
    return "red"


def cmd_fuera(a) -> int:
    """Construye y audita, con el extractor en disco, las leyes de FUERA que no
    lo están por diseño. Una que no se puede descargar se anota (con su
    `causa_fuente`) y no cuenta como intento. La caché (`--cache`) guarda el
    resultado por PDF y huella del extractor: una ley sin cambios no se
    reconstruye cada semana. `--solo-fuente` solo descarga (la ronda de
    redeclaración: qué leyes de un estado no se pueden descargar y por qué)."""
    from extractor import federal
    from extractor.estatal import ESTATAL
    from extractor.fuentes import descargar, url_vigente
    from extractor.registro import a_dict
    t = Path(a.trabajo)
    registros = reparaciones.cargar(a.registro)
    huella = federal.huella_extractor(ESTATAL.fuentes_extractor)
    cache = Path(a.cache) if a.cache else None
    defs = {c: d for c, d in reparables().items()
            if not a.estado or c.split("/")[0] == a.estado}
    reg = t / "fuera" / "registro.json"
    _escribir(reg, {"documentos": [a_dict(d) for d in defs.values()]})
    res, construidas = {}, 0
    for c, d in sorted(defs.items()):
        base = {"definicion": a_dict(d)}
        pdf = Path(a.pdfs) / f"{c}.pdf"
        try:
            url = url_vigente(d)
            descargar(url, str(pdf), via=d.via)
            if not pdf.read_bytes()[:4] == b"%PDF":
                raise NoEsPdf("lo descargado no es un PDF")
        except Exception as e:                       # noqa: BLE001 — se reporta
            res[c] = {**base, "error_fuente": f"{type(e).__name__}: {e}"[:300],
                      "causa_fuente": causa_fuente(e)}
            print(f"· {c}: sin PDF ({res[c]['causa_fuente']}: {res[c]['error_fuente']})")
            continue
        sha = federal.sha256(pdf)
        base.update(sha256=sha, url=url, intentos=reparaciones.intentos(c, sha, registros))
        if a.solo_fuente:
            res[c] = base
            print(f"· {c}: PDF descargado ({url})")
            continue
        guardado = cache / f"{c.replace('/', '__')}.json" if cache else None
        previo = _leer(guardado) if guardado else None
        if previo and previo.get("sha256") == sha and previo.get("huella") == huella:
            res[c] = {**previo, **base}
        elif construidas >= a.max:
            print(f"· {c}: queda para otra corrida (tope de {a.max} por corrida)")
            continue
        else:
            construidas += 1
            datos = t / "fuera" / "datos"
            error = federal._construir({"clave": c}, str(pdf), str(datos), str(reg))
            r = {"error": error} if error else federal.evaluar(datos, c, str(pdf))
            res[c] = {**base, **r, "huella": huella}
            if guardado:
                _escribir(guardado, {**res[c], "intentos": None})
        r = res[c]
        estado = ("limpia" if es_limpia(r) else
                  f"{len(r.get('problemas') or {})} unidades con problemas" if not r.get("error")
                  else r["error"][:120])
        print(f"{'✓' if es_limpia(r) else '✗'} {c}: {estado} ({r['intentos']} intentos con este PDF)")
    _escribir(Path(a.salida), res)
    limpias = sorted(c for c, r in res.items() if es_limpia(r))
    _salida_gh(limpias=" ".join(limpias))
    return 0


BLOQUE_LEYES = """

# Reparación autónoma (scripts/reparacion.py promover, {fecha}): estas leyes
# de FUERA ya quedan con build y auditar limpios sobre su PDF; la vigilancia
# las da de alta tras su revisión completa.
_A_LEYES = {{
{filas}
}}
LEYES = list(LEYES) + [d for d, _ in FUERA if d.clave in _A_LEYES]
FUERA = [(d, m) for d, m in FUERA if d.clave not in _A_LEYES]
"""


def bloque_leyes(claves: list[str]) -> str:
    filas = "\n".join(f"    {json.dumps(c, ensure_ascii=False)}," for c in sorted(claves))
    return BLOQUE_LEYES.format(fecha=date.today().isoformat(), filas=filas)


def cmd_promover(a) -> int:
    """Lee resultados de build + auditar (de `fuera` o de las compuertas de un
    arreglo, `construir`) y pasa a LEYES las de FUERA (no por diseño) que
    quedaron limpias. Solo agrega un bloque al final de cada módulo."""
    raiz = Path(a.raiz).resolve()
    candidatas = set(reparables())
    limpias = set()
    for ruta in a.resultado:
        for c, r in (_leer(ruta) or {}).items():
            if c in candidatas and es_limpia(r):
                limpias.add(c)
    por_estado: dict[str, list[str]] = {}
    for c in sorted(limpias):
        por_estado.setdefault(c.split("/")[0], []).append(c)
    for estado, claves in por_estado.items():
        ruta = raiz / "extractor" / "estatales" / f"{estado.replace('-', '_')}.py"
        ruta.write_text(ruta.read_text(encoding="utf-8").rstrip("\n") + bloque_leyes(claves),
                        encoding="utf-8")
        print(f"→ LEYES {', '.join(claves)}")
    _salida_gh(promovidas=" ".join(sorted(limpias)),
               estados=" ".join(sorted(por_estado)))
    if not limpias:
        print("Ninguna ley de FUERA quedó limpia.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("objetivo")
    p.add_argument("--corpus", choices=("estatal", "federal"), required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--trabajo", required=True)
    p.add_argument("--plan", default=None, help="plan de esta corrida (definiciones de sus altas)")
    p.add_argument("--max-leyes", type=int, default=4)
    p.add_argument("--con-auditoria", action="store_true",
                   help="también las leyes con fallas de la auditoría determinista")
    p.add_argument("--fuera", default=None, help="resultado de `fuera`: las leyes de FUERA que fallan")
    p.add_argument("--registro", default=str(reparaciones.REGISTRO))
    p = sub.add_parser("preparar")
    p.add_argument("--trabajo", required=True)
    p.add_argument("--pdfs", action="append", required=True)
    p = sub.add_parser("registrar")
    p.add_argument("--trabajo", required=True)
    p.add_argument("--resultado", choices=("iniciado", "publicado", "descartado"), required=True)
    p.add_argument("--motivo", default="")
    p.add_argument("--extractor", default="")
    p.add_argument("--registro", default=str(reparaciones.REGISTRO))
    p = sub.add_parser("construir")
    p.add_argument("--trabajo", required=True)
    p.add_argument("--extractor-dir", required=True)
    p.add_argument("--pdfs", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("comparar")
    p.add_argument("--trabajo", required=True)
    p.add_argument("--antes", required=True)
    p.add_argument("--despues", required=True)
    p = sub.add_parser("fuera")
    p.add_argument("--trabajo", required=True)
    p.add_argument("--pdfs", required=True)
    p.add_argument("--salida", required=True)
    p.add_argument("--cache", default=None)
    p.add_argument("--max", type=int, default=8, help="leyes que se construyen por corrida")
    p.add_argument("--estado", default=None, help="solo las de este estado")
    p.add_argument("--solo-fuente", action="store_true", help="solo descargar, sin construir")
    p.add_argument("--registro", default=str(reparaciones.REGISTRO))
    p = sub.add_parser("promover")
    p.add_argument("--resultado", action="append", required=True)
    p.add_argument("--raiz", default=str(EXTRACTOR))
    a = ap.parse_args(argv)
    return {"objetivo": cmd_objetivo, "preparar": cmd_preparar, "registrar": cmd_registrar,
            "construir": cmd_construir, "comparar": cmd_comparar, "fuera": cmd_fuera,
            "promover": cmd_promover}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
