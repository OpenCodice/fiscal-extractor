#!/usr/bin/env python3
"""La parte determinista de la ronda de expansión (expandir-estatales.yml):
qué estado sigue, si la cadena anterior terminó, y las compuertas del módulo
que escribe el agente (scripts/agente/expandir.sh). Ver «Ronda de expansión»
en AGENTS.md.

La lista ordenada de estados por sumar y lo que pasó con cada uno vive en
`extractor/estatales/pendientes.json` (no entra en la huella del extractor: no
es un `*.py`). Situaciones: `pendiente`, `publicado`, `egress` (el sitio
rechaza IP extranjeras y su dominio no está en el Worker egress-mx) y
`agotado` (llegó al tope de intentos; vuelve a la cola cuando cambia lo que
el agente puede usar del extractor, o con el tiempo: ver `revive`).

Subcomandos:

  listo     --out LEYES-ESTATALES   leyes declaradas sin alta todavía (y alcanzables)
  elegir    [--estado E] [--permitidos permitidos.json]   el estado de esta ronda; cuenta el intento
  registro  --estado E --salida R   valida el módulo nuevo y escribe su registro (datos)
  descargar --registro R --pdfs D --resultado J   descarga sus PDF (sin importar código del agente)
  construir --registro R --pdfs D --descargas J --out O   build + auditar de cada ley
  fuera     --estado E --construccion C   pasa a FUERA las leyes que no quedaron limpias
  anotar    --estado E --resultado publicado|egress|fallido|codigo|codigo-publicado|codigo-descartado …
  impacto-igual A B   el impacto en lo publicado es el mismo con y sin el módulo
  egress-agregar --json permitidos.json --dominio H --estado E [--pista P]
            agrega a la lista de egress-mx un dominio oficial (regla en `dominio_oficial`)
  declaraciones --salida J [--indices H] [--fuentes F …] [--leer-de H]
            la declaración y la URL vigente de todo el registro (compuerta de un
            arreglo de código: con el extractor de partida, que descarga las
            páginas índice, y con el arreglo, que las lee de H sin red)
  declaraciones-iguales A B   el arreglo no cambia ninguna declaración ni URL

Redeclaración (un estado ya publicado con leyes en FUERA que no se pueden
descargar por algo del extractor, `reparacion.py fuera` con causa `codigo`):

  redeclarar-pendiente --fuera J   el estado que toca redeclarar (lo lanza `reparar`)
  elegir --redeclarar E --fuera J --objetivo O   cuenta su intento y deja sus leyes
  redeclaracion-cerco --antes R --despues R --objetivo O --salida R2
            el agente solo agregó opciones a esas leyes de FUERA
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
TOPE_CODIGO = 2           # arreglos de código por estado (y por vuelta a la cola)
TOPE_REDECLARACION = 2    # rondas de redeclaración por estado y firma de sus fallas
SEMANAS_HUELLA = 4        # un agotado vuelve si cambió la huella y pasó esto…
SEMANAS_MAX = 12          # …o, sin cambios, tras esto
# Lo que el agente de la ronda puede usar del extractor: si cambia, un estado
# agotado puede tener otra salida. Los módulos de otros estados no cuentan
# (cambian cada semana con la ronda misma).
HUELLA_EXPANSION = ("parsers/*.py", "build.py", "modelo.py", "normalize.py", "verificar.py",
                    "validate.py", "fuentes.py", "registro.py", "estatales/__init__.py",
                    "estatal.py", "disposicion.py")


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


_HOST = re.compile(r"(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")


def _hoy() -> str:
    return datetime.date.today().isoformat()


def huella_expansion(raiz: Path = RAIZ) -> str:
    h = hashlib.sha256()
    for patron in HUELLA_EXPANSION:
        for p in sorted((raiz / "extractor").glob(patron)):
            h.update(p.relative_to(raiz).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


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
    """Dominios del Worker egress-mx: `dominios` de egress-mx/permitidos.json
    (de main de constitucion-extractor, la lista que lee el Worker)."""
    if not ruta or not Path(ruta).exists():
        return set()
    try:
        datos = _leer(Path(ruta))
    except ValueError:
        return set()
    return {d for d in datos.get("dominios", []) if isinstance(d, str) and _HOST.fullmatch(d)}


def _semanas(desde: str | None, hoy: datetime.date) -> float:
    try:
        return (hoy - datetime.date.fromisoformat(desde or "")).days / 7
    except ValueError:
        return float("inf")


def revive(e: dict, tope: int, huella: str | None, hoy: datetime.date) -> str | None:
    """Si un estado `agotado` vuelve a la cola, por qué. Vuelve con un solo
    intento más (y sus intentos de código de nuevo), así que uno sin salida
    cuesta a lo más una sesión cada SEMANAS_HUELLA semanas si el extractor
    cambia, o cada SEMANAS_MAX si no."""
    a = e.get("agotado") or {}
    semanas = _semanas(a.get("fecha") or e.get("ultimo_intento"), hoy)
    if huella and a.get("huella") != huella and semanas >= SEMANAS_HUELLA:
        return "cambió el extractor desde que se agotó"
    if semanas >= SEMANAS_MAX:
        return f"pasaron {SEMANAS_MAX} semanas desde que se agotó"
    return None


def elegir(lista: dict, estado: str | None, dominios: set[str], hay_modulo,
           huella: str | None = None, hoy: datetime.date | None = None) -> dict | None:
    """El estado de esta ronda (o None). Un `egress` cuyo dominio ya está en el
    Worker vuelve a `pendiente`; un estado con módulo ya está `publicado`; un
    `agotado` puede volver (ver `revive`). Primero los que nunca se agotaron."""
    tope = lista.get("tope_intentos", 3)
    hoy = hoy or datetime.date.today()
    for e in lista["estados"]:
        if hay_modulo(e["estado"]) and e["situacion"] != "publicado":
            e["situacion"] = "publicado"
        if e["situacion"] == "egress" and e.get("dominio") in dominios:
            e["situacion"] = "pendiente"
            e["intentos"] = min(e["intentos"], tope - 1)
            e["motivo"] = f"{e['dominio']} ya está en egress-mx: se reintenta"
        if e["situacion"] == "agotado" and (por := revive(e, tope, huella, hoy)):
            e.update(situacion="pendiente", intentos=tope - 1, intentos_codigo=0,
                     revivido=e.get("revivido", 0) + 1, motivo=f"vuelve a la cola: {por}")
            e.pop("agotado", None)
    if estado:
        e = next((x for x in lista["estados"] if x["estado"] == estado), None)
        if e is None:
            raise SystemExit(f"{estado} no está en la lista de pendientes")
        if e["situacion"] == "publicado":
            raise SystemExit(f"{estado} ya tiene módulo")
        if e["intentos"] >= tope:
            raise SystemExit(f"{estado} llegó al tope de {tope} intentos")
        return e
    listos = [x for x in lista["estados"] if x["situacion"] == "pendiente" and x["intentos"] < tope]
    return min(listos, key=lambda x: bool(x.get("revivido")), default=None)


def cmd_elegir(a) -> int:
    lista = _leer(LISTA)
    dominios = permitidos(a.permitidos)
    if a.redeclarar:
        o = elegir_redeclaracion(lista, a.redeclarar, _leer(Path(a.fuera)))
        if o is None:
            print(f"{a.redeclarar}: ninguna ley de FUERA por redeclarar (o se agotaron sus intentos).")
            _salida_gh(hay="false")
            return 0
        _escribir(LISTA, lista)
        _escribir(Path(a.objetivo), o)
        from extractor.estatales import ENTIDADES
        e = next(x for x in lista["estados"] if x["estado"] == a.redeclarar)
        print(f"Redeclaración de {ENTIDADES[a.redeclarar]}: {', '.join(o['leyes'])} "
              f"(intento {o['intentos'] + 1} de {lista.get('tope_redeclaracion', TOPE_REDECLARACION)})")
        _salida_gh(hay="true", estado=a.redeclarar, nombre=ENTIDADES[a.redeclarar],
                   modulo=modulo_de(a.redeclarar).stem, pista=" ".join((e.get("pista") or "").split()),
                   permitidos=" ".join(sorted(dominios)))
        return 0
    e = elegir(lista, a.estado or None, dominios, lambda s: modulo_de(s).exists(),
               huella_expansion())
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


# ------------------------------------------------------------------ redeclaración

def objetivo_redeclaracion(e: dict, fuera_res: dict, lista: dict) -> dict | None:
    """Las leyes de FUERA del estado de `e` (ya publicado) que no se pudieron
    descargar por algo del extractor, y si quedan intentos para ellas. La
    firma (qué leyes y qué excepción) separa una falla nueva de la misma: los
    intentos de redeclaración y de código se cuentan por firma, así que la
    misma falla cuesta a lo más TOPE_REDECLARACION rondas, y una distinta
    empieza de cero."""
    if e.get("situacion") != "publicado":
        return None
    leyes = {c: r["error_fuente"] for c, r in sorted(fuera_res.items())
             if c.split("/")[0] == e["estado"] and r.get("causa_fuente") == "codigo"}
    if not leyes:
        return None
    firma = hashlib.sha256("\n".join(f"{c}|{m.split(':')[0]}" for c, m in leyes.items())
                           .encode()).hexdigest()[:16]
    r = e.get("redeclaracion") or {}
    intentos = r.get("intentos", 0) if r.get("firma") == firma else 0
    if intentos >= lista.get("tope_redeclaracion", TOPE_REDECLARACION):
        return None
    return {"estado": e["estado"], "firma": firma, "intentos": intentos, "leyes": leyes}


def cmd_redeclarar_pendiente(a) -> int:
    """El primer estado publicado con leyes de FUERA por redeclarar (bajo su
    tope), para que `reparar` lance su ronda."""
    lista, res = _leer(LISTA), _leer(Path(a.fuera))
    for e in lista["estados"]:
        if (o := objetivo_redeclaracion(e, res, lista)):
            print(f"Redeclarar {o['estado']}: {', '.join(o['leyes'])} "
                  f"(intento {o['intentos'] + 1} con esta falla)")
            _salida_gh(estado=o["estado"])
            return 0
    print("Ninguna ley de FUERA espera un arreglo de su declaración.")
    _salida_gh(estado="")
    return 0


def elegir_redeclaracion(lista: dict, estado: str, fuera_res: dict) -> dict | None:
    e = next((x for x in lista["estados"] if x["estado"] == estado), None)
    if e is None or not modulo_de(estado).exists():
        raise SystemExit(f"{estado} no es un estado publicado")
    e["situacion"] = "publicado"
    o = objetivo_redeclaracion(e, fuera_res, lista)
    if o is None:
        return None
    r = e.get("redeclaracion") or {}
    if r.get("firma") != o["firma"]:
        r = {"firma": o["firma"], "intentos": 0, "intentos_codigo": 0}
    r.update(intentos=r.get("intentos", 0) + 1, ultimo_intento=_hoy(), leyes=sorted(o["leyes"]))
    r.pop("motivo", None)
    e["redeclaracion"] = r
    return o


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
    diseno = getattr(mod, "FUERA_POR_DISENO", set())
    if not isinstance(diseno, (set, frozenset, tuple, list)) or \
            not set(diseno) <= {d.clave for d, _ in fuera}:
        errores.append("FUERA_POR_DISENO debe ser un conjunto de claves de FUERA")
    if len(leyes) > MAX_LEYES:
        errores.append(f"más de {MAX_LEYES} leyes")
    if errores:
        for e in errores:
            print(f"✗ {e}")
        return 1
    _escribir(Path(a.salida), {"documentos": [a_dict(d) for d in leyes],
                               "fuera": {d.clave: m for d, m in fuera},
                               "medio": mod.MEDIO,
                               "fuera_documentos": [a_dict(d) for d, _ in fuera],
                               "por_diseno": sorted(diseno)})
    print(f"{len(leyes)} leyes y {len(fuera)} fuera.")
    return 0


# ------------------------------------------------------------------ redeclaracion-cerco

# Un campo con su valor por omisión es una opción que no se usa: darle valor es agregarla.
_VACIOS = (None, False, "", [], ())


def cerco_redeclaracion(antes: dict, despues: dict, leyes: set[str]) -> tuple[list[str], list[dict]]:
    """Lo que el agente de una redeclaración no puede cambiar del módulo (por
    `a_dict`, como datos): MEDIO, cada entrada de LEYES (y su orden), qué
    claves hay en FUERA y en FUERA_POR_DISENO, y las entradas de FUERA que no
    son de sus `leyes`. En las suyas solo puede agregar opciones: cada campo
    que ya tenían queda igual. Devuelve (errores, entradas cambiadas)."""
    errores = []
    if despues.get("medio") != antes.get("medio"):
        errores.append("cambió MEDIO")
    if despues["documentos"] != antes["documentos"]:
        errores.append("cambió LEYES (la promoción a LEYES es de reparar.sh promover)")
    if despues.get("por_diseno") != antes.get("por_diseno"):
        errores.append("cambió FUERA_POR_DISENO")
    a = {d["clave"]: d for d in antes["fuera_documentos"]}
    d = {x["clave"]: x for x in despues["fuera_documentos"]}
    if set(a) != set(d):
        errores.append("cambió qué leyes hay en FUERA")
    cambiadas = []
    for c in sorted(set(a) & set(d)):
        if a[c] == d[c]:
            continue
        if c not in leyes or c in (antes.get("por_diseno") or []):
            errores.append(f"{c}: no es una de las leyes por redeclarar")
            continue
        tocados = [k for k, v in a[c].items() if v not in _VACIOS and d[c].get(k) != v]
        if tocados:
            errores.append(f"{c}: cambió {', '.join(tocados)} (solo se pueden agregar opciones)")
            continue
        cambiadas.append(d[c])
    if not cambiadas and not errores:
        errores.append("no agregó ninguna opción a las leyes por redeclarar")
    return errores, cambiadas


def cmd_redeclaracion_cerco(a) -> int:
    o = _leer(Path(a.objetivo))
    errores, cambiadas = cerco_redeclaracion(_leer(Path(a.antes)), _leer(Path(a.despues)),
                                             set(o["leyes"]))
    for e in errores:
        print(f"✗ {e}")
    if errores:
        return 1
    _escribir(Path(a.salida), {"documentos": cambiadas})
    antes = {d["clave"]: d for d in _leer(Path(a.antes))["fuera_documentos"]}
    for x in cambiadas:
        nuevas = [k for k, v in x.items() if antes[x["clave"]].get(k) in _VACIOS and v not in _VACIOS]
        print(f"✓ {x['clave']}: agrega {', '.join(nuevas)}")
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

def _agotar_o_seguir(e: dict, lista: dict, motivo: str) -> None:
    if e["intentos"] >= lista.get("tope_intentos", 3):
        e.update(situacion="agotado", agotado={"fecha": _hoy(), "huella": huella_expansion()})
    else:
        e["situacion"] = "pendiente"
    e["motivo"] = motivo[:400]


def anotar_redeclaracion(e: dict, lista: dict, a) -> None:
    """Como la ronda de un estado nuevo, pero en el registro `redeclaracion`
    del estado ya publicado: el estado sigue `publicado` pase lo que pase."""
    r = e.setdefault("redeclaracion", {})
    tope_codigo = lista.get("tope_codigo", TOPE_CODIGO)
    if a.resultado == "publicado":
        r.update(situacion="redeclarado", fecha=_hoy(), motivo="leyes redeclaradas: las retoma `reparar`")
    elif a.resultado == "codigo":
        hay = r.get("intentos_codigo", 0) < tope_codigo
        if hay:
            r["intentos_codigo"] = r.get("intentos_codigo", 0) + 1
            r["falta"] = " ".join(a.motivo.split())[:600]
        r["motivo"] = (f"necesita código en el extractor: {a.motivo}" if hay else
                       f"necesita código y se agotaron sus {tope_codigo} intentos de código: {a.motivo}")[:400]
        _salida_gh(codigo="true" if hay else "false")
    elif a.resultado == "codigo-publicado":
        r["intentos"] = max(0, r.get("intentos", 0) - 1)
        r["motivo"] = f"el extractor ya tiene lo que faltaba ({a.motivo}): se reintenta"[:400]
    elif a.resultado == "codigo-descartado":
        r["motivo"] = f"{r.get('motivo', '')}; arreglo de código descartado: {a.motivo}"[:400]
    else:
        r["motivo"] = (a.motivo or "la redeclaración falló")[:400]
    if a.corrida:
        r["corrida"] = a.corrida
    print(f"{a.estado} (redeclaración): {r.get('motivo', '')}")


def cmd_anotar(a) -> int:
    lista = _leer(LISTA)
    e = next(x for x in lista["estados"] if x["estado"] == a.estado)
    if a.redeclaracion:
        anotar_redeclaracion(e, lista, a)
        _escribir(LISTA, lista)
        return 0
    if not a.resultado.startswith("codigo-"):
        for k in ("motivo", "dominio", "leyes", "fuera_por_compuertas", "falta", "agotado"):
            e.pop(k, None)
    tope_codigo = lista.get("tope_codigo", TOPE_CODIGO)
    if a.resultado == "publicado":
        e.update(situacion="publicado", fecha=_hoy(), leyes=a.leyes,
                 **({"fuera_por_compuertas": a.fuera} if a.fuera else {}))
    elif a.resultado == "egress":
        # No fue una falla del agente: el intento no cuenta. Con el dominio ya
        # en la lista de egress-mx (`--agregado`), el estado vuelve a la cola.
        e["intentos"] = max(0, e["intentos"] - 1)
        e.update(situacion="pendiente" if a.agregado else "egress", dominio=a.dominio,
                 motivo=(f"{a.dominio} agregado a egress-mx: se reintenta" if a.agregado
                         else f"necesita egress-mx: {a.dominio}")
                 + (f" ({a.motivo})" if a.motivo else ""))
    elif a.resultado == "codigo":
        # Le falta algo al extractor (no al parser): lo intenta el job `codigo`
        # mientras queden intentos de código. El intento se cuenta aquí, antes
        # de ese agente.
        hay = e.get("intentos_codigo", 0) < tope_codigo
        if hay:
            e["intentos_codigo"] = e.get("intentos_codigo", 0) + 1
            e["falta"] = " ".join(a.motivo.split())[:600]
        _agotar_o_seguir(e, lista, f"necesita código en el extractor: {a.motivo}" if hay else
                         f"necesita código en el extractor y se agotaron sus {tope_codigo} "
                         f"intentos de código: {a.motivo}")
        _salida_gh(codigo="true" if hay else "false")
    elif a.resultado == "codigo-publicado":
        # El extractor ya tiene lo que faltaba: el intento que lo pidió no
        # cuenta y el estado se reintenta enseguida.
        e["intentos"] = max(0, min(e["intentos"], lista.get("tope_intentos", 3)) - 1)
        e.pop("agotado", None)
        e.update(situacion="pendiente", motivo=f"el extractor ya tiene lo que faltaba ({a.motivo}): se reintenta"[:400])
    elif a.resultado == "codigo-descartado":
        e["motivo"] = (f"{e.get('motivo', '')}; arreglo de código descartado: {a.motivo}")[:400]
    else:
        _agotar_o_seguir(e, lista, a.motivo or "la ronda falló")
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


# ------------------------------------------------------------------ egress-agregar

# Segundos niveles de .mx que reparten dominios a cualquiera: ahí el dominio
# registrable tiene tres etiquetas (congreso.com.mx), no dos.
_SLD_MX = {"com", "org", "net", "edu", "gob"}


def registrable(host: str) -> str:
    partes = host.split(".")
    n = 3 if len(partes) >= 3 and partes[-1] == "mx" and partes[-2] in _SLD_MX else 2
    return ".".join(partes[-n:])


def dominio_oficial(dominio: str, confiables: set[str]) -> str | None:
    """Por qué `dominio` es plausiblemente oficial (o None). Regla estricta:
    - termina en `.gob.mx`, que NIC México solo asigna a dependencias de
      gobierno; o
    - termina en `.mx` y su dominio registrable es el de un host que ya se
      tiene por oficial: el de la constitución publicada del estado (su
      pista) o uno de la lista de egress-mx.
    Cualquier otro (un `.com`, un bucket, un `.mx` sin relación) no se agrega
    solo: el intento cuenta como fallido."""
    if not _HOST.fullmatch(dominio) or not dominio.endswith(".mx"):
        return None
    if dominio.endswith(".gob.mx"):
        return "dominio .gob.mx"
    base = registrable(dominio)
    if base in {registrable(h) for h in confiables if h.endswith(".mx")}:
        return f"mismo dominio que {base}, ya oficial"
    return None


def cmd_egress_agregar(a) -> int:
    """Agrega `--dominio` a la lista de egress-mx si es oficial. Sale 0 si lo
    agregó (o ya estaba), 3 si no es un dominio oficial reconocible."""
    ruta = Path(a.json)
    datos = _leer(ruta)
    actuales = list(datos.get("dominios", []))
    dominio = a.dominio.strip().lower().rstrip(".")
    pista = {h.lower() for h in re.findall(r"https?://([^/\s:]+)", a.pista or "")}
    por = dominio_oficial(dominio, set(actuales) | pista)
    if por is None:
        print(f"✗ {dominio}: no es un dominio oficial reconocible (.gob.mx, o .mx del mismo "
              "dominio que la constitución del estado o que la lista de egress-mx)")
        return 3
    if dominio in actuales:
        print(f"{dominio} ya está en egress-mx.")
        return 0
    datos["dominios"] = actuales + [dominio]
    _escribir(ruta, datos)
    print(f"✓ {dominio} agregado a egress-mx ({por}; {a.estado}).")
    return 0


# ------------------------------------------------------------------ declaraciones

def _todas() -> list:
    """Todo lo declarado en el código: el corpus fiscal, las leyes estatales y
    sus FUERA."""
    from extractor import registro
    from extractor.estatales import documentos, fuera
    return list(registro.DOCUMENTOS) + documentos() + [d for d, _ in fuera().values()]


def cmd_declaraciones(a) -> int:
    """La declaración (a_dict, sin campos vacíos) y la URL vigente de cada
    documento del código y de los `--fuentes` (un fuentes.json: su registro
    pasa por de_dict). Con `--indices` descarga cada página índice (el
    extractor de partida, con la red y el token) y las guarda; con
    `--leer-de` las lee de ese archivo, sin red (el arreglo, sin secretos).
    Así un arreglo opcional se comprueba contra lo que ya está declarado: ni
    una declaración ni una URL vigente pueden cambiar."""
    from extractor.fuentes import _leer_indice, url_vigente
    from extractor.registro import a_dict, de_dict
    docs = {}
    for d in _todas():
        docs.setdefault(d.clave, d)
    for f in a.fuentes or []:
        for d in _leer(Path(f))["documentos"]:
            docs.setdefault(d["clave"], de_dict(d))
    paginas = _leer(Path(a.leer_de)) if a.leer_de else {}
    nuevas, fallidas = {}, {}

    def leer(url, via=None):
        k = f"{via or ''} {url}"
        if a.leer_de:
            if k not in paginas:
                raise LookupError(f"página índice no guardada: {url}")
            return paginas[k]
        if k in fallidas:
            raise fallidas[k]
        if k not in nuevas:
            for intento in range(2):
                try:
                    nuevas[k] = _leer_indice(url, via) if via else _leer_indice(url)
                    break
                except Exception as e:               # noqa: BLE001 — se reporta
                    if intento:
                        fallidas[k] = e
                        raise
        return nuevas[k]

    res = {}
    for c, d in sorted(docs.items()):
        decl = {k: v for k, v in a_dict(d).items() if v not in (None, False, "", [], ())}
        try:
            url = url_vigente(d, leer=leer)
        except Exception:                            # noqa: BLE001 — se compara
            # Sin la página índice no hay URL que comparar, con ninguno de los
            # dos extractores: cuenta igual en ambos.
            url = "error"
        res[c] = {"declaracion": decl, "url": url}
    _escribir(Path(a.salida), res)
    if a.indices:
        _escribir(Path(a.indices), nuevas)
    errores = sum(1 for r in res.values() if r["url"] == "error")
    print(f"{len(res)} documentos; {len(nuevas) or len(paginas)} páginas índice; "
          f"{errores} sin URL resuelta.")
    return 0


def cmd_declaraciones_iguales(a) -> int:
    antes, despues = _leer(Path(a.antes)), _leer(Path(a.despues))
    difs = [c for c in sorted(set(antes) | set(despues)) if antes.get(c) != despues.get(c)]
    for c in difs[:20]:
        print(f"✗ {c}: {antes.get(c)} → {despues.get(c)}")
    if difs:
        print(f"✗ El arreglo cambia {len(difs)} declaraciones o URL vigentes.")
        return 1
    print(f"Ninguna de las {len(antes)} declaraciones ni URL vigentes cambia.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("listo"); s.add_argument("--out", required=True)
    s = sub.add_parser("elegir"); s.add_argument("--estado", default=""); s.add_argument("--permitidos")
    s.add_argument("--redeclarar", default=""); s.add_argument("--fuera"); s.add_argument("--objetivo")
    s = sub.add_parser("redeclarar-pendiente"); s.add_argument("--fuera", required=True)
    s = sub.add_parser("redeclaracion-cerco")
    for k in ("--antes", "--despues", "--objetivo", "--salida"):
        s.add_argument(k, required=True)
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
    s.add_argument("--resultado", required=True,
                   choices=["publicado", "egress", "fallido", "codigo", "codigo-publicado",
                            "codigo-descartado"])
    s.add_argument("--agregado", action="store_true")
    s.add_argument("--motivo", default="")
    s.add_argument("--dominio", default="")
    s.add_argument("--leyes", type=int, default=0)
    s.add_argument("--fuera", type=int, default=0)
    s.add_argument("--corrida", default="")
    s.add_argument("--redeclaracion", action="store_true",
                   help="el resultado es de la redeclaración de un estado ya publicado")
    s = sub.add_parser("impacto-igual"); s.add_argument("antes"); s.add_argument("despues")
    s = sub.add_parser("egress-agregar")
    for k in ("--json", "--dominio", "--estado"):
        s.add_argument(k, required=True)
    s.add_argument("--pista", default="")
    s = sub.add_parser("declaraciones")
    s.add_argument("--salida", required=True)
    s.add_argument("--indices")
    s.add_argument("--leer-de")
    s.add_argument("--fuentes", action="append")
    s = sub.add_parser("declaraciones-iguales"); s.add_argument("antes"); s.add_argument("despues")
    a = p.parse_args(argv)
    return {"listo": cmd_listo, "elegir": cmd_elegir, "registro": cmd_registro,
            "descargar": cmd_descargar, "construir": cmd_construir, "fuera": cmd_fuera,
            "anotar": cmd_anotar, "impacto-igual": cmd_impacto_igual,
            "egress-agregar": cmd_egress_agregar, "declaraciones": cmd_declaraciones,
            "declaraciones-iguales": cmd_declaraciones_iguales,
            "redeclarar-pendiente": cmd_redeclarar_pendiente,
            "redeclaracion-cerco": cmd_redeclaracion_cerco}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
