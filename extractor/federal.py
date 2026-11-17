"""Corpus de leyes federales: registro generado del índice de LeyesBiblio.

A diferencia del corpus fiscal, que se declara a mano en `registro.py`, el
federal es todo lo que publica la Cámara de Diputados en su índice de leyes
vigentes (~320). El repo de datos (`leyes-federales`) guarda su registro en
`fuentes.json`: por documento, su definición, la huella del PDF del que salió
su texto (sha256 + cabeceras HTTP) y la huella del extractor que lo produjo. Los
PDF no se versionan.

La vigilancia se divide en tres pasos para repartir la extracción entre varios
jobs de CI:

  planear  — compara el índice y las cabeceras de cada PDF contra fuentes.json y
             decide qué documentos se reprocesan (nuevo, PDF distinto, cambio
             del parser o reintento de uno excluido).
  extraer  — descarga y construye un subconjunto del plan, y lo audita.
  cerrar   — con los resultados de todos: incluye lo que quedó fiel, deja fuera
             (y anota) lo nuevo que no, conserva la versión anterior de lo ya
             publicado que no, y redacta el commit.
"""
from __future__ import annotations

import hashlib
import html as _html
import json
import re
import shutil
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

from .fuentes import UA, _SSL_GOB, descargar, url_vigente
from .registro import BASE_DIPUTADOS, FISCALES as _FISCALES, Documento, a_dict, de_dict

INDICE = f"{BASE_DIPUTADOS}/index.htm"

# Documentos del índice que no entran a este corpus.
FUERA_DEL_CORPUS = {
    "cpeum": "La Constitución se versiona aparte, en OpenCodice/constitucion-mexicana.",
    # Su artículo 1o. es la tarifa arancelaria: una tabla de varias columnas
    # (fracción, descripción, unidad, tasas) que en texto plano mezcla las
    # columnas a media descripción. No es un articulado que este parser
    # pueda representar fielmente.
    "ligie-2022": "La tarifa del artículo 1o. es una tabla de varias columnas; en texto "
                  "plano las columnas se mezclan a media descripción.",
    # La marca de agua girada 'DIARIO OFICIAL' del PDF deja letras sueltas a
    # media frase ('la metodología S para su evaluación') que ninguna regla
    # general separa de una letra legítima ('fracciones III, V y VI').
    "lfpccs": "La marca de agua girada del PDF deja letras sueltas dentro del texto de "
              "varios artículos.",
}

# Archivos del extractor cuyo cambio puede cambiar el texto o la metadata que se
# genera. Si su huella cambia, todo el corpus se reconstruye.
_FUENTES_EXTRACTOR = ("parsers/*.py", "build.py", "modelo.py", "normalize.py",
                      # Una compuerta más estricta también obliga a reauditar.
                      "verificar.py", "validate.py")

TIEMPO_MAX_DOC = 20 * 60          # segundos para construir un documento


# ------------------------------------------------------------------ índice

@dataclass
class Fila:
    slug: str          # 'lgs' de ref/lgs.htm: estable aunque cambie el PDF
    nombre: str        # 'LEY General de Salud'
    pdf: str           # URL absoluta del PDF vigente


_FILA_RE = re.compile(r"<tr>(.*?)</tr>", re.S | re.I)
_REF_RE = re.compile(r'<a\s[^>]*href="ref/([^"/]+)\.htm"[^>]*>(.*?)</a>', re.S | re.I)
_PDF_RE = re.compile(r'href="(pdf/[^"]+\.pdf)"', re.I)


def _texto(fragmento: str) -> str:
    return " ".join(_html.unescape(re.sub(r"<[^>]+>", " ", fragmento)).split())


def leer_indice(html: str) -> list[Fila]:
    """Filas del índice de leyes vigentes que tienen PDF."""
    filas = []
    for tr in _FILA_RE.findall(html):
        ref, pdf = _REF_RE.search(tr), _PDF_RE.search(tr)
        if ref and pdf:
            filas.append(Fila(ref.group(1).lower(), _texto(ref.group(2)),
                              urljoin(INDICE, pdf.group(1))))
    return filas


def _etiqueta(nombre: str) -> str:
    """'LEY General de Salud' → 'Ley General de Salud' (el índice pone en
    mayúsculas solo la primera palabra)."""
    primera, _, resto = nombre.partition(" ")
    if primera.isupper() and len(primera) > 1:
        primera = primera.capitalize()
    return f"{primera} {resto}".strip()


def _sigla(fila: Fila) -> str:
    """Sigla del nombre del PDF ('LGS.pdf', 'LGES_200421.pdf'); si el PDF es
    solo un número ('238.pdf'), la del slug."""
    base = re.sub(r"_\d{6}$", "", Path(fila.pdf).stem)
    return base if not base.isdigit() and not re.match(r"^\d", base) else fila.slug.upper()


def _clave(slug: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", slug).strip("-")


def documentos(html: str) -> list[Documento]:
    """Corpus federal: las leyes del índice más los reglamentos fiscales.

    Las leyes que ya están en el corpus fiscal conservan su clave, etiqueta y
    sigla (mismo namespace en los dos repos); su URL es la del índice."""
    fiscales_por_pdf = {Path(d.url).name.lower(): d for d in _FISCALES
                        if d.url and d.url.startswith(BASE_DIPUTADOS)}
    fiscales_por_clave = {d.clave: d for d in _FISCALES}
    docs: list[Documento] = []
    vistas: set[str] = set()
    for f in leer_indice(html):
        clave = _clave(f.slug)
        if clave in FUERA_DEL_CORPUS or clave in vistas:
            continue
        fiscal = fiscales_por_pdf.get(Path(f.pdf).name.lower())
        if fiscal is None and getattr(fiscales_por_clave.get(clave), "tipo", "") == "ley":
            fiscal = fiscales_por_clave[clave]
        if fiscal:
            docs.append(Documento(fiscal.clave, fiscal.etiqueta, fiscal.sigla, "ley",
                                  "articulado", url=f.pdf,
                                  titulos_encabezado=fiscal.titulos_encabezado))
            vistas.add(fiscal.clave)
        else:
            docs.append(Documento(clave, _etiqueta(f.nombre), _sigla(f), "ley",
                                  "articulado", url=f.pdf))
            vistas.add(clave)
    for d in _FISCALES:
        if d.tipo == "reglamento" and d.clave not in vistas:
            docs.append(d)
            vistas.add(d.clave)
    return docs


def leer_url(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60, context=_SSL_GOB) as r:
        crudo = r.read()
    # LeyesBiblio sirve ISO-8859-1; otras páginas, UTF-8.
    try:
        return crudo.decode("utf-8")
    except UnicodeDecodeError:
        return crudo.decode("latin-1")


# ------------------------------------------------------------------ huellas

def huella_extractor() -> str:
    raiz = Path(__file__).parent
    h = hashlib.sha256()
    for patron in _FUENTES_EXTRACTOR:
        for p in sorted(raiz.glob(patron)):
            h.update(p.relative_to(raiz).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


def sha_extractor() -> str | None:
    """Commit del extractor que corre (el que produce el texto), o None si no
    es un repo de git."""
    r = subprocess.run(["git", "-C", str(Path(__file__).parent.parent), "rev-parse", "HEAD"],
                       capture_output=True, text=True)
    return r.stdout.strip() or None if r.returncode == 0 else None


def sha256(ruta: str | Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def cabeceras(url: str) -> dict:
    """ETag, Last-Modified y tamaño del PDF sin descargarlo."""
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60, context=_SSL_GOB) as r:
        return {"etag": r.headers.get("ETag"),
                "last_modified": r.headers.get("Last-Modified"),
                "bytes": int(r.headers.get("Content-Length") or 0) or None}


def _mismas_cabeceras(antes: dict | None, ahora: dict) -> bool:
    if not antes:
        return False
    claves = [k for k in ("etag", "last_modified", "bytes") if ahora.get(k)]
    return bool(claves) and all(antes.get(k) == ahora[k] for k in claves)


# ------------------------------------------------------------------ fuentes.json

def leer_fuentes(out: str | Path) -> dict:
    ruta = Path(out) / "fuentes.json"
    if ruta.exists():
        return json.loads(ruta.read_text(encoding="utf-8"))
    return {"indice": INDICE, "documentos": []}


def escribir_fuentes(out: str | Path, fuentes: dict) -> None:
    fuentes["documentos"].sort(key=lambda d: d["clave"])
    (Path(out) / "fuentes.json").write_text(
        json.dumps(fuentes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ planear

def planear(out: str | Path, docs: list[Documento], *, solo: list[str] | None = None,
            lote: int | None = None, shards: int = 12, consultar=cabeceras) -> dict:
    """Qué documentos reprocesar y por qué, repartidos en `shards` grupos.

    `lote` limita los documentos nuevos (o reintentos) por corrida —el alta del
    corpus entra en tandas—; los cambios a documentos ya publicados no se
    limitan."""
    previos = {d["clave"]: d for d in leer_fuentes(out)["documentos"]}
    huella = huella_extractor()
    candidatos = [d for d in docs if not solo or d.clave in solo]

    def revisar(doc: Documento) -> tuple[Documento, str | None, dict | None]:
        prev = previos.get(doc.clave)
        try:
            url = url_vigente(doc)
            cab = consultar(url)
        except Exception as e:                      # noqa: BLE001 — se reporta
            return doc, "pdf", {"error": f"{type(e).__name__}: {e}"}
        if prev is None:
            return doc, "nuevo", cab
        cambio_pdf = url != prev.get("url") or not _mismas_cabeceras(prev.get("pdf"), cab)
        if solo:
            motivo = "pdf" if cambio_pdf else "extractor"
        elif prev.get("estado") == "excluida":
            motivo = "reintento" if (cambio_pdf or prev.get("extractor") != huella) else None
        elif prev.get("extractor") != huella:
            motivo = "extractor"
        else:
            motivo = "pdf" if cambio_pdf else None
        return doc, motivo, cab

    with ThreadPoolExecutor(max_workers=8) as pool:
        revisados = list(pool.map(revisar, candidatos))

    elegidos, nuevos = [], 0
    # Lo declarado fuera del corpus que sigue publicado se retira en `cerrar`;
    # entra al plan para que haya corrida aunque nada más cambie.
    for clave in FUERA_DEL_CORPUS:
        prev = previos.get(clave)
        if prev and prev.get("estado") == "incluida" and (not solo or clave in solo):
            elegidos.append({**{k: prev[k] for k in ("clave", "etiqueta", "sigla", "tipo",
                                                      "parser", "url") if k in prev},
                             "motivo": "fuera", "cabeceras": None})
    for doc, motivo, cab in revisados:
        if not motivo:
            continue
        if motivo in ("nuevo", "reintento") and lote is not None:
            if nuevos >= lote:
                continue
            nuevos += 1
        elegidos.append({**a_dict(doc), "motivo": motivo, "cabeceras": cab})

    n = max(1, min(shards, len(elegidos)))
    grupos = [[e["clave"] for e in elegidos[i::n]] for i in range(n)] if elegidos else []
    pendientes = sum(1 for _, m, _ in revisados if m in ("nuevo", "reintento")) - nuevos
    return {"huella": huella, "extractor_sha": sha_extractor(),
            "documentos": elegidos, "shards": grupos,
            "nuevos_pendientes": max(0, pendientes)}


# ------------------------------------------------------------------ extraer

def _construir(doc: dict, pdf: str, out: str, registro: str) -> str | None:
    """Construye un documento en un proceso aparte (con tiempo máximo).
    Devuelve el error, o None si salió bien."""
    cmd = [sys.executable, "-m", "extractor", "--registro", registro, "build",
           "--doc", doc["clave"], "--pdf", pdf, "--out", out, "--sin-pasajes"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIEMPO_MAX_DOC,
                           cwd=Path(__file__).parent.parent)
    except subprocess.TimeoutExpired:
        return f"la extracción excedió {TIEMPO_MAX_DOC // 60} minutos"
    if r.returncode != 0:
        ultima = (r.stderr.strip().splitlines() or ["sin detalle"])[-1]
        return f"la extracción falló: {ultima[:300]}"
    return None


def evaluar(out: str | Path, clave: str, pdf: str) -> dict:
    """Auditoría determinista e invariantes de un documento ya construido."""
    from .validate import validar
    from .verificar import auditar
    a = auditar(out, {clave: pdf})
    _, checks = validar(str(out), [clave])
    idx_path = Path(out) / "metadata" / clave / "articulos.json"
    idx = json.loads(idx_path.read_text(encoding="utf-8")) if idx_path.exists() else {}
    return {
        "unidades": idx.get("num_articulos", 0),
        "version": idx.get("version"),
        "problemas": a["con_problemas"],
        "invariantes": [f"{label}: {detalle}" if detalle else label
                        for ok, label, detalle in checks if not ok],
    }


def es_fiel(r: dict) -> bool:
    """Pasa las compuertas deterministas y, si es un alta, la revisión
    completa contra el PDF (`revision`: el motivo si no la pasó)."""
    return (not r.get("error") and not r.get("problemas") and not r.get("invariantes")
            and not r.get("revision"))


def extraer(plan_path: str, out: str, pdf_dir: str, *, claves: list[str],
            previos: dict | None = None, descargar_pdf: bool = True) -> dict:
    """Descarga (si hace falta), construye y audita `claves` del plan."""
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    por_clave = {d["clave"]: d for d in plan["documentos"]}
    previos = previos if previos is not None else {
        d["clave"]: d for d in leer_fuentes(out)["documentos"]}
    Path(pdf_dir).mkdir(parents=True, exist_ok=True)
    resultados = {}
    for clave in claves:
        d = por_clave[clave]
        pdf = str(Path(pdf_dir) / f"{clave}.pdf")
        r: dict = {"clave": clave, "motivo": d["motivo"]}
        try:
            url = url_vigente(de_dict(d))
            if descargar_pdf or not Path(pdf).exists():
                descargar(url, pdf)
            r.update(url=url, sha256=sha256(pdf), bytes=Path(pdf).stat().st_size,
                     etag=(d.get("cabeceras") or {}).get("etag"),
                     last_modified=(d.get("cabeceras") or {}).get("last_modified"))
        except Exception as e:                       # noqa: BLE001 — se reporta
            r["error_fuente"] = f"no se pudo descargar: {type(e).__name__}: {e}"
            resultados[clave] = r
            print(f"✗ {clave}: {r['error_fuente']}", flush=True)
            continue
        prev = previos.get(clave)
        if (d["motivo"] == "pdf" and prev and prev.get("pdf", {}).get("sha256") == r["sha256"]
                and prev.get("extractor") == plan["huella"]):
            r["sin_cambio"] = True                   # cambiaron las cabeceras, no el PDF
            resultados[clave] = r
            print(f"= {clave}: mismo PDF", flush=True)
            continue
        error = _construir(d, pdf, out, plan_path)
        if error:
            r["error"] = error
        else:
            r.update(evaluar(out, clave, pdf))
        resultados[clave] = r
        estado = "✓" if es_fiel(r) else "✗"
        print(f"{estado} {clave}: {r.get('unidades', 0)} unidades, "
              f"{len(r.get('problemas', {}))} con problemas, "
              f"{len(r.get('invariantes', []))} invariantes rotos"
              + (f" — {r['error']}" if r.get("error") else ""), flush=True)
    return resultados


# ------------------------------------------------------------------ cerrar

def _git(out, *args) -> str:
    return subprocess.run(["git", "-C", str(out), *args], capture_output=True,
                          text=True).stdout


def unidades_cambiadas(out: str | Path, clave: str) -> list[str]:
    """Unidades de `clave` cuyo texto difiere de HEAD (añadidas, cambiadas o
    suprimidas)."""
    salida = _git(out, "status", "--porcelain", "--no-renames", "-uall", "--", clave)
    return sorted(Path(l[3:].strip().strip('"')).stem for l in salida.splitlines()
                  if l.strip().endswith(".md"))


def _articulo(out: Path, clave: str, unidad: str) -> str:
    """'Artículo 4o.' del encabezado del .md → '4o'; si se suprimió, de HEAD."""
    ruta = out / clave / f"{unidad}.md"
    texto = ruta.read_text(encoding="utf-8") if ruta.exists() else _git(
        out, "show", f"HEAD:{clave}/{unidad}.md")
    primera = texto.split("\n", 1)[0]
    return re.sub(r"^#\s*Art[íi]culo\s+", "", primera).rstrip(".").strip() or unidad


def _restaurar(out: Path, clave: str) -> None:
    """Devuelve el documento a su versión publicada (o lo quita si es nuevo)."""
    for ruta in (clave, f"metadata/{clave}"):
        if (out / ruta).exists():
            shutil.rmtree(out / ruta)
        if _git(out, "ls-tree", "-d", "HEAD", ruta).strip():
            subprocess.run(["git", "-C", str(out), "checkout", "-q", "HEAD", "--", ruta],
                           check=True)


def motivo_exclusion(r: dict) -> str:
    if r.get("error"):
        return r["error"]
    if r.get("revision"):
        return r["revision"]
    partes = []
    if r.get("invariantes"):
        partes.append("invariantes rotos: " + "; ".join(r["invariantes"][:3]))
    if r.get("problemas"):
        ejemplos = ", ".join(list(r["problemas"])[:5])
        partes.append(f"{len(r['problemas'])} unidades no reproducen el PDF ({ejemplos})")
    return ". ".join(partes) or "sin detalle"


def _publicada_es_fiel(out: Path, clave: str, pdf: str | None) -> bool:
    """¿La versión publicada (HEAD) pasa la auditoría actual contra este PDF?"""
    if not pdf or not Path(pdf).exists():
        return False
    import tempfile
    from .verificar import auditar
    with tempfile.TemporaryDirectory() as tmp:
        destino = Path(tmp) / clave
        destino.mkdir()
        for ruta in _git(out, "ls-tree", "--name-only", "HEAD", f"{clave}/").split():
            (Path(tmp) / ruta).write_text(_git(out, "show", f"HEAD:{ruta}"), encoding="utf-8")
        return not auditar(tmp, {clave: pdf})["con_problemas"]


def cerrar(plan_path: str, out: str, resultados: dict, *, reparacion: dict | None = None,
           hoy: date | None = None, pdf_dir: str | None = None) -> dict:
    """Aplica las decisiones a `fuentes.json` y al árbol de datos; devuelve el
    resumen para el commit y el PR."""
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    out_p = Path(out)
    fuentes = leer_fuentes(out)
    fuentes["indice"] = INDICE
    entradas = {d["clave"]: d for d in fuentes["documentos"]}
    hoy = (hoy or date.today()).isoformat()
    reparados = set((reparacion or {}).get("reparados", []))
    titulo_rep = (reparacion or {}).get("titulo")
    sha_plan = plan.get("extractor_sha")
    sha_rep = (reparacion or {}).get("sha") or sha_plan
    huella_rep = huella_extractor() if reparados else plan["huella"]
    # Causa de cada cambio, para los trailers de su commit
    # (scripts/commits_por_documento.py): con qué PDF y qué extractor se produjo.
    contexto: dict[str, dict] = {}

    altas, reformas, correcciones, excluidas, retenidas, fallidas = [], [], [], [], [], []
    retiradas: list[str] = []            # publicadas que salen del corpus
    aplazadas: list[str] = []            # altas cuya revisión completa queda para otra corrida
    for clave, motivo in FUERA_DEL_CORPUS.items():
        e = entradas.get(clave)
        if e and e.get("estado") == "incluida":
            for ruta in (clave, f"metadata/{clave}"):
                if (out_p / ruta).exists():
                    shutil.rmtree(out_p / ruta)
            entradas[clave] = {**{k: v for k, v in e.items() if k not in ("alta", "unidades",
                                                                          "version")},
                               "estado": "excluida", "motivo": motivo, "fecha": hoy}
            excluidas.append((clave, motivo))
            retiradas.append(clave)
            contexto[clave] = {"motivo_retiro": "fuera del corpus", "extractor_sha": sha_plan}
    for d in plan["documentos"]:
        clave = d["clave"]
        r = resultados.get(clave)
        prev = entradas.get(clave)
        if r is None or clave in FUERA_DEL_CORPUS:
            continue
        if r.get("error_fuente"):
            fallidas.append((clave, r["error_fuente"]))
            if prev is None:
                _restaurar(out_p, clave)
            continue
        definicion = {k: v for k, v in d.items() if k not in ("motivo", "cabeceras")}
        huella_pdf = {"sha256": r["sha256"], "bytes": r["bytes"], "etag": r.get("etag"),
                      "last_modified": r.get("last_modified")}
        if r.get("sin_cambio"):
            prev["pdf"] = huella_pdf
            continue
        publicada = prev is not None and prev.get("estado") == "incluida"
        if r.get("aplazada") and not publicada:
            # Su revisión completa no cupo en esta corrida: queda como si no
            # se hubiera procesado y la siguiente la planea otra vez.
            _restaurar(out_p, clave)
            aplazadas.append(clave)
            continue
        if es_fiel(r):
            reparada = clave in reparados
            sha_doc = sha_rep if reparada else sha_plan
            cambio_pdf = ((prev or {}).get("pdf") or {}).get("sha256") != r["sha256"]
            contexto[clave] = {
                "fuente": r.get("url") or d.get("url"), "sha256": r["sha256"],
                "pdf": str(Path(pdf_dir) / f"{clave}.pdf") if pdf_dir else None,
                "pdf_cambio": cambio_pdf if publicada else None,
                "extractor_cambio": (prev or {}).get("extractor") != (
                    huella_rep if reparada else plan["huella"]),
                "extractor_sha": sha_doc,
                "extractor_anterior": (prev or {}).get("extractor_sha") if publicada else None,
            }
            entrada = {**definicion, "estado": "incluida", "version": r.get("version"),
                       "unidades": r.get("unidades"), "pdf": huella_pdf,
                       "extractor": plan["huella"],
                       **({"extractor_sha": sha_doc} if sha_doc else {})}
            entrada["alta"] = prev.get("alta") if publicada else {
                "fecha": hoy, "via": "reparada" if clave in reparados else "limpia",
                **({"reparacion": titulo_rep} if clave in reparados and titulo_rep else {})}
            entradas[clave] = entrada
            cambiadas = unidades_cambiadas(out_p, clave)
            if not publicada:
                altas.append(clave)
            elif cambiadas and cambio_pdf:
                reformas.append((clave, r.get("version"),
                                 [_articulo(out_p, clave, u) for u in cambiadas]))
            elif cambiadas:
                correcciones.append((clave, len(cambiadas)))
            continue
        motivo = motivo_exclusion(r)
        _restaurar(out_p, clave)
        pdf = str(Path(pdf_dir) / f"{clave}.pdf") if pdf_dir else None
        if publicada and d["motivo"] != "pdf" and not _publicada_es_fiel(out_p, clave, pdf):
            # Mismo PDF y la versión publicada tampoco pasa la auditoría actual
            # (se publicó con compuertas más laxas): no puede seguir publicada.
            for ruta in (clave, f"metadata/{clave}"):
                if (out_p / ruta).exists():
                    shutil.rmtree(out_p / ruta)
            motivo += ". La versión publicada tampoco pasa la auditoría actual"
            entradas[clave] = {**definicion, "estado": "excluida", "motivo": motivo,
                               "fecha": hoy, "pdf": huella_pdf, "extractor": plan["huella"]}
            excluidas.append((clave, motivo))
            retiradas.append(clave)
            contexto[clave] = {"motivo_retiro": "la extracción no reproduce el PDF",
                               "extractor_sha": sha_plan}
        elif publicada:
            # Lo publicado se conserva: mejor la versión anterior fiel que una
            # nueva que no lo es. Queda anotado para revisión.
            prev["revision_pendiente"] = {"fecha": hoy, "motivo": motivo,
                                          "pdf": huella_pdf}
            retenidas.append((clave, motivo))
        else:
            entradas[clave] = {**definicion, "estado": "excluida", "motivo": motivo,
                               "fecha": hoy, "pdf": huella_pdf, "extractor": plan["huella"]}
            excluidas.append((clave, motivo))

    for e in entradas.values():
        if e.get("estado") == "incluida" and e["clave"] not in {c for c, _ in retenidas} \
                and e["clave"] in resultados and es_fiel(resultados[e["clave"]]):
            e.pop("revision_pendiente", None)
    fuentes["documentos"] = list(entradas.values())
    escribir_fuentes(out, fuentes)
    from .build import escribir_indice_maestro
    escribir_indice_maestro(out)

    siglas = {c: e["sigla"] for c, e in entradas.items()}
    asunto = _asunto(altas, reformas, correcciones, siglas, retiradas)
    return {"asunto": asunto, "contexto": contexto,
            "altas": altas, "reformas": reformas, "retiradas": retiradas,
            "correcciones": correcciones, "excluidas": excluidas,
            "retenidas": retenidas, "fuentes_fallidas": fallidas, "aplazadas": aplazadas,
            "reparados": sorted(reparados & set(altas + [c for c, *_ in reformas]
                                                 + [c for c, _ in correcciones]))}


def _lista_corta(elems: list[str], n: int = 6) -> str:
    return ", ".join(elems[:n]) + (f" y {len(elems) - n} más" if len(elems) > n else "")


def _asunto(altas, reformas, correcciones, siglas, retiradas=()) -> str:
    partes = []
    for clave, version, arts in reformas[:3]:
        partes.append(f"Reforma {siglas.get(clave, clave)} (DOF {version or 's/f'}): "
                      f"{'art.' if len(arts) == 1 else 'arts.'} {_lista_corta(arts)}")
    if len(reformas) > 3:
        partes.append(f"reformas en {len(reformas) - 3} leyes más")
    if altas:
        partes.append(f"Alta de {len(altas)} "
                      f"{'ley federal' if len(altas) == 1 else 'leyes federales'}: "
                      f"{_lista_corta([siglas.get(c, c) for c in altas], 5)}")
    if correcciones:
        n = sum(k for _, k in correcciones)
        partes.append(f"Corrección de extracción: {n} "
                      f"{'artículo' if n == 1 else 'artículos'} en {len(correcciones)} "
                      f"{'ley' if len(correcciones) == 1 else 'leyes'}")
    if retiradas:
        partes.append(f"Retiro de {len(retiradas)} "
                      f"{'ley' if len(retiradas) == 1 else 'leyes'} que no "
                      f"{'reproduce' if len(retiradas) == 1 else 'reproducen'} el PDF: "
                      f"{_lista_corta([siglas.get(c, c) for c in retiradas], 5)}")
    return " · ".join(partes) or "Actualización de fuentes de las leyes federales"


def cuerpo_pr(res: dict, plan: dict, resultados: dict, notas_agente: str = "") -> str:
    """Descripción del PR: qué entra, qué se queda fuera y por qué."""
    l = ["### Leyes federales: resultado de la vigilancia", ""]
    rep = set(res.get("reparados", []))
    if res["altas"]:
        l.append(f"**Altas ({len(res['altas'])})**, fieles al PDF según la auditoría determinista:")
        for c in res["altas"]:
            r = resultados[c]
            l.append(f"- `{c}` — {r.get('unidades')} artículos, versión {r.get('version') or 's/f'}"
                     + (" (tras reparar el extractor)" if c in rep else ""))
        l.append("")
    if res["reformas"]:
        l.append("**Reformas**:")
        for c, v, arts in res["reformas"]:
            l.append(f"- `{c}` (DOF {v or 's/f'}): {_lista_corta(arts, 30)}")
        l.append("")
    if res["correcciones"]:
        l.append("**Correcciones de extracción** (mismo PDF, mejor lectura):")
        for c, n in res["correcciones"]:
            l.append(f"- `{c}`: {n} artículos")
        l.append("")
    if res["excluidas"]:
        l.append(f"**Fuera del corpus ({len(res['excluidas'])})**: no quedaron fieles al PDF.")
        for c, m in res["excluidas"]:
            l.append(f"- `{c}` — {m}")
        l.append("")
    if res["retenidas"]:
        l.append("**Se conserva la versión publicada** (la nueva extracción no quedó fiel; "
                 "requiere revisión):")
        for c, m in res["retenidas"]:
            l.append(f"- `{c}` — {m}")
        l.append("")
    if res["fuentes_fallidas"]:
        l.append("**Fuentes que no se pudieron descargar**:")
        for c, m in res["fuentes_fallidas"]:
            l.append(f"- `{c}` — {m}")
        l.append("")
    if notas_agente:
        l += ["### 🤖 Agente", "", notas_agente.strip(), ""]
    pendientes = plan.get("nuevos_pendientes", 0)
    if pendientes:
        l.append(f"{'Queda 1 ley nueva' if pendientes == 1 else f'Quedan {pendientes} leyes nuevas'} "
                 "por procesar en las siguientes tandas.")
    l += ["", f"<!-- asunto: {res['asunto']} -->"]
    return "\n".join(l) + "\n"
