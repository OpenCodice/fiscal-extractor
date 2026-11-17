#!/usr/bin/env python3
"""La parte determinista de la ronda de expansión (expandir-estatales.yml):
qué estado sigue, si la cadena anterior terminó, y las compuertas del módulo
que escribe el agente (scripts/agente/expandir.sh). Ver «Ronda de expansión»
en AGENTS.md.

La lista ordenada de estados por sumar y lo que pasó con cada uno vive en
`extractor/estatales/pendientes.json` (no entra en la huella del extractor: no
es un `*.py`). Situaciones: `pendiente`, `publicado`, `egress` (el sitio
rechaza IP extranjeras y su dominio no está en el Worker egress-mx) y
`agotado` (llegó al tope de intentos).

Subcomandos:

  listo     --out LEYES-ESTATALES   leyes declaradas sin alta todavía (y alcanzables)
  elegir    [--estado E] [--permitidos worker.js]   el estado de esta ronda; cuenta el intento
  registro  --estado E --salida R   valida el módulo nuevo y escribe su registro (datos)
  descargar --registro R --pdfs D --resultado J   descarga sus PDF (sin importar código del agente)
  construir --registro R --pdfs D --descargas J --out O   build + auditar de cada ley
  fuera     --estado E --construccion C   pasa a FUERA las leyes que no quedaron limpias
  anotar    --estado E --resultado publicado|egress|fallido [--motivo M] [--dominio H] …
  impacto-igual A B   el impacto en lo publicado es el mismo con y sin el módulo
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

LISTA = RAIZ / "extractor" / "estatales" / "pendientes.json"
MAX_LEYES = 30


def _salida_gh(**pares) -> None:
    ruta = os.environ.get("GITHUB_OUTPUT")
    if ruta:
        with open(ruta, "a", encoding="utf-8") as f:
            for k, v in pares.items():
                f.write(f"{k}={v}\n")


def _leer(ruta: Path):
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


def _escribir(ruta: Path, datos) -> None:
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    Path(ruta).write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def modulo_de(estado: str) -> Path:
    return RAIZ / "extractor" / "estatales" / f"{estado.replace('-', '_')}.py"


def _hoy() -> str:
    return datetime.date.today().isoformat()


# ------------------------------------------------------------------ listo

def cmd_listo(a) -> int:
    """Leyes declaradas que aún no tienen entrada en fuentes.json (su alta no
    ha terminado) y cuyo PDF responde: la cadena de vigilancias las sigue
    dando de alta. Una que no responde tampoco la puede dar de alta la
    vigilancia (su `planear` la cuenta como falla de fuente), así que no
    detiene la ronda."""
    import urllib.request
    from extractor.estatales import documentos
    from extractor.fuentes import _SSL_GOB, _peticion, url_vigente
    previas = {d["clave"] for d in _leer(Path(a.out) / "fuentes.json")["documentos"]}
    pendientes, sin_fuente = [], []
    for doc in documentos():
        if doc.clave in previas:
            continue
        try:
            url = url_vigente(doc)
            with urllib.request.urlopen(_peticion(url, doc.via), timeout=60, context=_SSL_GOB) as r:
                r.read(1)
            pendientes.append(doc.clave)
        except Exception as e:                       # noqa: BLE001 — se reporta
            sin_fuente.append(f"{doc.clave} ({type(e).__name__}: {e})")
    for c in pendientes:
        print(f"alta pendiente: {c}")
    for c in sin_fuente:
        print(f"::warning::sin alta y sin PDF alcanzable: {c}")
    estados = sorted({c.split("/")[0] for c in pendientes})
    _salida_gh(pendientes=len(pendientes), estados=" ".join(estados))
    return 0


# ------------------------------------------------------------------ elegir

def permitidos(ruta: str | None) -> set[str]:
    """Dominios del Worker egress-mx (`PERMITIDOS` en su worker.js)."""
    if not ruta or not Path(ruta).exists():
        return set()
    m = re.search(r"PERMITIDOS\s*=\s*new Set\(\[(.*?)\]\)", Path(ruta).read_text(encoding="utf-8"), re.S)
    return set(re.findall(r'"([a-z0-9.-]+)"', m.group(1))) if m else set()


def elegir(lista: dict, estado: str | None, dominios: set[str], hay_modulo) -> dict | None:
    """El estado de esta ronda (o None). Un `egress` cuyo dominio ya está en el
    Worker vuelve a `pendiente`; un estado con módulo ya está `publicado`."""
    tope = lista.get("tope_intentos", 3)
    for e in lista["estados"]:
        if hay_modulo(e["estado"]) and e["situacion"] != "publicado":
            e["situacion"] = "publicado"
        if e["situacion"] == "egress" and e.get("dominio") in dominios:
            e["situacion"] = "pendiente"
            e["motivo"] = f"{e['dominio']} ya está en egress-mx: se reintenta"
    if estado:
        e = next((x for x in lista["estados"] if x["estado"] == estado), None)
        if e is None:
            raise SystemExit(f"{estado} no está en la lista de pendientes")
        if e["situacion"] == "publicado":
            raise SystemExit(f"{estado} ya tiene módulo")
        if e["intentos"] >= tope:
            raise SystemExit(f"{estado} llegó al tope de {tope} intentos")
        return e
    return next((x for x in lista["estados"]
                 if x["situacion"] == "pendiente" and x["intentos"] < tope), None)


def cmd_elegir(a) -> int:
    lista = _leer(LISTA)
    dominios = permitidos(a.permitidos)
    e = elegir(lista, a.estado or None, dominios, lambda s: modulo_de(s).exists())
    if e is None:
        _escribir(LISTA, lista)
        print("No queda ningún estado por intentar.")
        _salida_gh(hay="false")
        return 0
    e["intentos"] += 1
    e["ultimo_intento"] = _hoy()
    _escribir(LISTA, lista)
    from extractor.estatales import ENTIDADES
    print(f"Ronda: {ENTIDADES[e['estado']]} (intento {e['intentos']} de {lista.get('tope_intentos', 3)})")
    _salida_gh(hay="true", estado=e["estado"], nombre=ENTIDADES[e["estado"]],
               modulo=modulo_de(e["estado"]).stem, pista=" ".join((e.get("pista") or "").split()),
               permitidos=" ".join(sorted(dominios)))
    return 0


# ------------------------------------------------------------------ registro

def cmd_registro(a) -> int:
    """Importa el módulo nuevo (sin secretos en el entorno: es código del
    agente), comprueba su forma y escribe su registro como datos."""
    import importlib
    from extractor.registro import Documento, a_dict
    mod = importlib.import_module(f"extractor.estatales.{modulo_de(a.estado).stem}")
    errores = []
    if not isinstance(getattr(mod, "MEDIO", None), str) or not mod.MEDIO.strip():
        errores.append("falta MEDIO")
    leyes, fuera = getattr(mod, "LEYES", None), getattr(mod, "FUERA", None)
    if not isinstance(leyes, list) or not leyes or not all(isinstance(d, Documento) for d in leyes):
        errores.append("LEYES debe ser una lista no vacía de ley(...)")
        leyes = []
    if not isinstance(fuera, list) or not all(
            isinstance(x, tuple) and len(x) == 2 and isinstance(x[0], Documento)
            and isinstance(x[1], str) and x[1].strip() for x in fuera):
        errores.append("FUERA debe ser una lista (quizá vacía) de (ley(...), motivo)")
        fuera = []
    todas = [d for d in leyes] + [d for d, _ in fuera]
    claves = [d.clave for d in todas]
    if len(set(claves)) != len(claves):
        errores.append("claves repetidas")
    for d in todas:
        if not d.clave.startswith(f"{a.estado}/") or d.parser != "articulado" or not d.medio:
            errores.append(f"{d.clave}: no es una ley(...) de {a.estado}")
        if d.via not in (None, "mx"):
            errores.append(f"{d.clave}: via desconocida {d.via!r}")
        if not (d.url or (d.indice and d.patron)):
            errores.append(f"{d.clave}: sin url ni indice + patron")
        for u in (d.url, d.indice):
            if u and not re.match(r"https?://[^/@\s]+/", u):
                errores.append(f"{d.clave}: URL inválida {u!r}")
    if len(leyes) > MAX_LEYES:
        errores.append(f"más de {MAX_LEYES} leyes")
    if errores:
        for e in errores:
            print(f"✗ {e}")
        return 1
    _escribir(Path(a.salida), {"documentos": [a_dict(d) for d in leyes],
                               "fuera": {d.clave: m for d, m in fuera}})
    print(f"{len(leyes)} leyes y {len(fuera)} fuera.")
    return 0


# ------------------------------------------------------------------ descargar

def cmd_descargar(a) -> int:
    """Descarga el PDF vigente de cada ley del registro. Corre desde un clon
    limpio del extractor (con EGRESS_MX_TOKEN): no importa el módulo del
    agente, solo lee su registro como datos."""
    from extractor.fuentes import descargar, url_vigente
    from extractor.registro import de_dict
    reg = _leer(Path(a.registro))
    res = {}
    for d in reg["documentos"]:
        doc = de_dict(d)
        dest = Path(a.pdfs) / f"{doc.clave}.pdf"
        try:
            url = url_vigente(doc)
            descargar(url, str(dest), via=doc.via)
            datos = dest.read_bytes()
            if not datos.startswith(b"%PDF"):
                raise ValueError("lo descargado no es un PDF")
            res[doc.clave] = {"url": url, "sha256": hashlib.sha256(datos).hexdigest()}
            print(f"✓ {doc.clave}: {url}")
        except Exception as e:                       # noqa: BLE001 — se reporta
            res[doc.clave] = {"error": f"{type(e).__name__}: {e}"[:300]}
            print(f"✗ {doc.clave}: {res[doc.clave]['error']}")
    _escribir(Path(a.resultado), res)
    fallidas = sum(1 for r in res.values() if "error" in r)
    _salida_gh(fallidas=fallidas)
    return 0


# ------------------------------------------------------------------ construir

def cmd_construir(a) -> int:
    """build + auditar de cada ley descargada con el extractor en disco (el
    del agente; sin secretos). `<out>/resultado.json`: por ley, unidades y
    las que tienen problemas, o el error."""
    reg = str(Path(a.registro).resolve())
    descargas = _leer(Path(a.descargas))
    out = Path(a.out)
    datos = out / "datos"
    res = {}
    for d in _leer(Path(a.registro))["documentos"]:
        c = d["clave"]
        if "error" in descargas.get(c, {"error": "sin descarga"}):
            res[c] = {"error": "sin PDF: " + descargas.get(c, {}).get("error", "sin descarga")}
            continue
        pdf = str((Path(a.pdfs) / f"{c}.pdf").resolve())
        r = subprocess.run([sys.executable, "-m", "extractor", "--registro", reg, "build",
                            "--doc", c, "--pdf", pdf, "--out", str(datos), "--sin-pasajes"],
                           cwd=RAIZ, capture_output=True, text=True, timeout=1800)
        if r.returncode != 0:
            res[c] = {"error": "build: " + (r.stderr.strip().splitlines() or ["?"])[-1][:300]}
            print(f"✗ {c}: {res[c]['error']}")
            continue
        sola = out / "pdf" / c.replace("/", "__")
        (sola / f"{c}.pdf").parent.mkdir(parents=True, exist_ok=True)
        if not (sola / f"{c}.pdf").exists():
            (sola / f"{c}.pdf").symlink_to(pdf)
        j = out / f"auditoria-{c.replace('/', '__')}.json"
        r = subprocess.run([sys.executable, "-m", "extractor", "--registro", reg, "auditar",
                            "--out", str(datos), "--pdf-dir", str(sola), "--json", str(j)],
                           cwd=RAIZ, capture_output=True, text=True, timeout=1800)
        if not j.exists():
            res[c] = {"error": "auditar: " + (r.stderr.strip().splitlines() or ["?"])[-1][:300]}
            print(f"✗ {c}: {res[c]['error']}")
            continue
        aud = _leer(j)
        res[c] = {"unidades": aud.get("total", 0), "problemas": sorted(aud.get("con_problemas", {}))}
        print(f"{'✓' if not res[c]['problemas'] and res[c]['unidades'] else '✗'} {c}: "
              f"{res[c]['unidades']} unidades, {len(res[c]['problemas'])} con problemas")
    _escribir(out / "resultado.json", res)
    return 0


# ------------------------------------------------------------------ fuera

def motivo_fuera(r: dict) -> str | None:
    """Motivo en lenguaje llano de una ley que no quedó limpia (o None)."""
    if "error" in r:
        return f"El extractor no pudo leer su PDF ({r['error'][:160]})."
    if not r.get("unidades"):
        return "El extractor no encontró ningún artículo en su PDF."
    if r.get("problemas"):
        p = r["problemas"]
        return (f"La extracción no reproduce fielmente el PDF: {len(p)} de {r['unidades']} "
                f"artículos con problemas en la auditoría (p. ej. {', '.join(p[:3])}).")
    return None


BLOQUE = '''

# Compuertas de la ronda de expansión (scripts/expansion.py, {fecha}): estas
# leyes no quedaron con build y auditar limpios sobre su PDF.
_FUERA_RONDA = {{
{filas}
}}
FUERA = list(FUERA) + [(d, _FUERA_RONDA[d.clave]) for d in LEYES if d.clave in _FUERA_RONDA]
LEYES = [d for d in LEYES if d.clave not in _FUERA_RONDA]
'''


def bloque_fuera(motivos: dict[str, str]) -> str:
    filas = "\n".join(f"    {json.dumps(c, ensure_ascii=False)}: {json.dumps(m, ensure_ascii=False)},"
                      for c, m in sorted(motivos.items()))
    return BLOQUE.format(fecha=_hoy(), filas=filas)


def cmd_fuera(a) -> int:
    res = _leer(Path(a.construccion))
    motivos = {c: m for c, r in res.items() if (m := motivo_fuera(r))}
    limpias = len(res) - len(motivos)
    if motivos:
        ruta = modulo_de(a.estado)
        ruta.write_text(ruta.read_text(encoding="utf-8").rstrip("\n") + bloque_fuera(motivos),
                        encoding="utf-8")
        for c, m in sorted(motivos.items()):
            print(f"→ FUERA {c}: {m}")
    print(f"{limpias} leyes limpias de {len(res)}.")
    _salida_gh(limpias=limpias, fuera=len(motivos))
    return 0


# ------------------------------------------------------------------ anotar

def cmd_anotar(a) -> int:
    lista = _leer(LISTA)
    e = next(x for x in lista["estados"] if x["estado"] == a.estado)
    for k in ("motivo", "dominio", "leyes", "fuera_por_compuertas"):
        e.pop(k, None)
    if a.resultado == "publicado":
        e.update(situacion="publicado", fecha=_hoy(), leyes=a.leyes,
                 **({"fuera_por_compuertas": a.fuera} if a.fuera else {}))
    elif a.resultado == "egress":
        e.update(situacion="egress", dominio=a.dominio,
                 motivo=f"necesita egress-mx: {a.dominio}" + (f" ({a.motivo})" if a.motivo else ""))
    else:
        agotado = e["intentos"] >= lista.get("tope_intentos", 3)
        e.update(situacion="agotado" if agotado else "pendiente",
                 motivo=(a.motivo or "la ronda falló")[:400])
    if a.corrida:
        e["corrida"] = a.corrida
    _escribir(LISTA, lista)
    print(f"{a.estado}: {e['situacion']}" + (f" — {e.get('motivo')}" if e.get("motivo") else ""))
    return 0


# ------------------------------------------------------------------ impacto-igual

def cmd_impacto_igual(a) -> int:
    """Sale 0 si las dos mediciones de impacto_corpus.py (sin y con el módulo
    nuevo) cambian exactamente las mismas unidades del mismo modo."""
    def firma(t):
        r = _leer(Path(t) / "resumen.json")
        return {"cambios": _leer(Path(t) / "cambios.json"), "errores": sorted(r["errores"]),
                "regresiones": sorted(r["regresiones"]), "sin_pdf": sorted(r["sin_pdf"])}
    try:
        iguales = firma(a.antes) == firma(a.despues)
    except (OSError, KeyError, ValueError) as e:
        print(f"✗ no se pudieron comparar las mediciones: {e}")
        return 1
    print("El módulo no cambia nada de lo publicado." if iguales
          else "✗ El módulo cambia lo publicado.")
    return 0 if iguales else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("listo"); s.add_argument("--out", required=True)
    s = sub.add_parser("elegir"); s.add_argument("--estado", default=""); s.add_argument("--permitidos")
    s = sub.add_parser("registro"); s.add_argument("--estado", required=True); s.add_argument("--salida", required=True)
    s = sub.add_parser("descargar")
    for k in ("--registro", "--pdfs", "--resultado"):
        s.add_argument(k, required=True)
    s = sub.add_parser("construir")
    for k in ("--registro", "--pdfs", "--descargas", "--out"):
        s.add_argument(k, required=True)
    s = sub.add_parser("fuera"); s.add_argument("--estado", required=True); s.add_argument("--construccion", required=True)
    s = sub.add_parser("anotar")
    s.add_argument("--estado", required=True)
    s.add_argument("--resultado", required=True, choices=["publicado", "egress", "fallido"])
    s.add_argument("--motivo", default="")
    s.add_argument("--dominio", default="")
    s.add_argument("--leyes", type=int, default=0)
    s.add_argument("--fuera", type=int, default=0)
    s.add_argument("--corrida", default="")
    s = sub.add_parser("impacto-igual"); s.add_argument("antes"); s.add_argument("despues")
    a = p.parse_args(argv)
    return {"listo": cmd_listo, "elegir": cmd_elegir, "registro": cmd_registro,
            "descargar": cmd_descargar, "construir": cmd_construir, "fuera": cmd_fuera,
            "anotar": cmd_anotar, "impacto-igual": cmd_impacto_igual}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
