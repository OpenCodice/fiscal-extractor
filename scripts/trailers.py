"""Trailers de git de los commits de los repos de datos.

Cada commit de un documento lleva, además del título, trailers que la bitácora
lee sin interpretar texto libre:

    Reforma LGS (DOF 2026-01-15): arts. 4o, 22, 222 Bis

    Documento: lgs
    Tipo: reforma
    Publicacion: 2026-01-15
    Publicacion-Origen: notas
    Medio: DOF
    Articulos-Modificados: 004, 022
    Articulos-Adicionados: 222-bis
    Fuente: https://www.diputados.gob.mx/LeyesBiblio/pdf/LGS.pdf
    Fuente-Sha256: 9f2c…
    Extractor: OpenCodice/fiscal-extractor@b897ca4

Todo sale de código determinista: del árbol antes y después del commit (que se
lee con un "lector": ruta → bytes o None) y de la causa del cambio, que decide
el pipeline (cambió el PDF, el extractor o ambos). Un cambio del extractor que
no toca el texto de ningún artículo (solo metadata: el nombre del periódico
oficial, los pasajes, el índice) es `metadatos`, no `correccion`: la bitácora
lo muestra aparte, como cambio menor. El mismo cálculo sirve para
los commits nuevos, para validar los de un PR y para reconstruir los trailers
del historial.

Este archivo existe idéntico en constitucion-extractor y en fiscal-extractor
(scripts/trailers.py): cualquier cambio se hace en los dos.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Callable, Iterable

Lector = Callable[[str], "bytes | None"]

TIPOS_DOCUMENTO = ("reforma", "correccion", "metadatos", "alta", "retiro")
TIPOS = TIPOS_DOCUMENTO + ("indice",)

# Orden canónico de los trailers en el mensaje.
ORDEN = ("Documento", "Tipo", "Publicacion", "Publicacion-Origen", "Medio",
         "Articulos-Adicionados", "Articulos-Modificados", "Articulos-Derogados",
         "Articulos-Corregidos", "Fuente", "Fuente-Sha256", "Extractor", "Separacion")
LISTAS = {"reforma": ("Articulos-Adicionados", "Articulos-Modificados", "Articulos-Derogados"),
          "correccion": ("Articulos-Corregidos",)}

MAX_EN_TITULO = 12
MAX_ARCHIVOS_EN_TITULO = 4

_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_EXTRACTOR = re.compile(r"^OpenCodice/[A-Za-z0-9._-]+@[0-9a-f]{7,40}$")
_TRAILER = re.compile(r"^([A-Z][A-Za-z0-9-]*): (.+)$")


# ------------------------------------------------------------------ mensaje

def formatear(titulo: str, trailers: Iterable[tuple[str, str]]) -> str:
    """Título, línea en blanco y un trailer por línea, en el orden canónico."""
    pares = sorted(trailers, key=lambda kv: ORDEN.index(kv[0]) if kv[0] in ORDEN else len(ORDEN))
    return titulo + "\n\n" + "\n".join(f"{k}: {v}" for k, v in pares) + "\n"


def parsear(mensaje: str) -> tuple[str, list[tuple[str, str]]]:
    """(título, trailers). Los trailers son el último párrafo del mensaje si
    todas sus líneas tienen la forma `Clave: valor`; si no, no hay trailers."""
    lineas = mensaje.strip("\n").split("\n")
    titulo = lineas[0].strip() if lineas else ""
    parrafos = "\n".join(lineas[1:]).strip("\n").split("\n\n")
    ultimo = parrafos[-1].strip("\n") if parrafos and parrafos[-1].strip() else ""
    if not ultimo:
        return titulo, []
    pares = []
    for l in ultimo.split("\n"):
        m = _TRAILER.match(l.rstrip())
        if not m:
            return titulo, []
        pares.append((m.group(1), m.group(2).strip()))
    return titulo, pares


def valor(trailers: list[tuple[str, str]], clave: str) -> str | None:
    for k, v in trailers:
        if k == clave:
            return v
    return None


def valores(trailers: list[tuple[str, str]], clave: str) -> list[str]:
    return [v for k, v in trailers if k == clave]


def lista(texto: str | None) -> list[str]:
    return [x.strip() for x in (texto or "").split(",") if x.strip()]


# ------------------------------------------------------------------ disposición

def esquema_de(documento: str) -> str:
    """'cpeum' (constitucion-mexicana), 'estatal' (leyes-estatales: la
    constitución o una ley de un estado, `<estado>/<clave>`) o 'corpus'
    (fiscal-mexicano, leyes-federales)."""
    if documento == "cpeum":
        return "cpeum"
    if "/" in documento:
        return "estatal"
    return "corpus"


def es_constitucion_estatal(documento: str) -> bool:
    return documento.endswith("/constitucion")


def documento_de_ruta(ruta: str, esquema: str) -> str | None:
    """Documento al que pertenece una ruta del repo; None si es compartida
    (índices, README, documentación)."""
    partes = ruta.split("/")
    if esquema == "cpeum":
        return "cpeum" if partes[0] in ("articulos", "metadata", "fuente") and len(partes) > 1 else None
    if esquema == "estatal":
        # `<estado>/<clave>/…`: su constitución (constitucion-extractor) o una de
        # sus leyes (fiscal-extractor), cada una en su carpeta.
        return f"{partes[0]}/{partes[1]}" if len(partes) > 2 and not partes[0].startswith(".") else None
    if partes[0] == "metadata":
        return partes[1] if len(partes) > 2 else None
    if partes[0].startswith(".") or len(partes) < 2:
        return None
    return partes[0]


def _dir_articulos(documento: str) -> str:
    e = esquema_de(documento)
    return "articulos/" if e == "cpeum" else (
        f"{documento}/articulos/" if e == "estatal" else f"{documento}/")


def _dir_metadata(documento: str) -> str:
    e = esquema_de(documento)
    return "metadata/" if e == "cpeum" else (
        f"{documento}/metadata/" if e == "estatal" else f"metadata/{documento}/")


def carpetas(documento: str) -> list[str]:
    """Las carpetas del repo que son del documento (para `git status/add --`)."""
    e = esquema_de(documento)
    if e == "cpeum":
        return ["articulos", "metadata", "fuente"]
    if e == "estatal":
        return [documento]
    return [documento, f"metadata/{documento}"]


def esquema_repo(raiz_dirs: Iterable[str], tiene_constitucion: Callable[[str], bool]) -> str:
    """Esquema de un repo de datos por su raíz: 'cpeum' si tiene `articulos/`,
    'estatal' si alguna carpeta tiene `constitucion/`, si no 'corpus'."""
    dirs = list(raiz_dirs)
    if "articulos" in dirs:
        return "cpeum"
    if any(tiene_constitucion(d) for d in dirs):
        return "estatal"
    return "corpus"


def clave_articulo(ruta: str, documento: str) -> str | None:
    """'004' de `lgs/004.md`; None si la ruta no es un artículo del documento."""
    base = _dir_articulos(documento)
    resto = ruta[len(base):] if ruta.startswith(base) else None
    if not resto or "/" in resto or not resto.endswith(".md"):
        return None
    return resto[:-3]


def rutas_fuente(documento: str) -> tuple[str, ...]:
    """Archivo oficial guardado en el repo (solo constituciones; de las leyes se
    guarda su sha256). El .doc va primero: cuando existe es el original
    descargado y el PDF su conversión."""
    e = esquema_de(documento)
    if e == "cpeum":
        return ("fuente/CPEUM.pdf",)
    if e == "estatal" and es_constitucion_estatal(documento):
        return (f"{documento}/fuente/constitucion.doc", f"{documento}/fuente/constitucion.pdf")
    return ()


# ------------------------------------------------------------------ lectura

def _json(leer: Lector, ruta: str):
    crudo = leer(ruta)
    if crudo is None:
        return None
    try:
        return json.loads(crudo.decode("utf-8"))
    except ValueError:
        return None


def info(documento: str, leer: Lector) -> dict:
    """Lo que el árbol dice del documento: versión, fechas de reforma, sigla,
    medio. `existe` es falso si el árbol no tiene su índice."""
    meta = _dir_metadata(documento)
    idx = _json(leer, meta + "articulos.json")
    if not isinstance(idx, dict):
        idx = None
    reformas = _json(leer, meta + "reformas.json")
    if isinstance(reformas, dict):
        fechas = set(reformas)
    else:
        fechas = {f for a in (idx or {}).get("articulos", []) for f in (a.get("reformas") or [])}
    e = esquema_de(documento)
    if e == "cpeum":
        sigla, medio = "CPEUM", "DOF"
    elif e == "estatal" and es_constitucion_estatal(documento):
        sigla = documento.split("/")[0]
        medio = ((idx or {}).get("fuente") or "").split(" — ")[0].strip() or None
    elif e == "estatal":
        # Una ley estatal: su sigla ('CC Jalisco') y su periódico oficial.
        sigla = (idx or {}).get("sigla") or documento
        medio = (idx or {}).get("medio")
    else:
        sigla, medio = (idx or {}).get("sigla") or documento.upper(), "DOF"
    return {"existe": idx is not None, "version": (idx or {}).get("version"),
            "reformas": {f for f in fechas if _FECHA.match(str(f))},
            "sigla": sigla, "medio": medio}


def medio_corto(medio: str | None) -> str:
    """'DOF', o las iniciales del nombre del periódico oficial: 'Periódico
    Oficial del Estado de Jalisco' → 'P.O.' (como lo abrevian las propias notas
    de reforma estatales)."""
    if not medio:
        return "s/m"
    if medio == "DOF":
        return "DOF"
    iniciales = []
    for palabra in medio.split():
        if not palabra[:1].isupper():
            break
        iniciales.append(palabra[0])
    return ".".join(iniciales) + "." if iniciales else medio


# ------------------------------------------------------------------ artículos

_DEROGA = re.compile(r"^\(?\s*(se\s+deroga|derogad[oa]s?)\b", re.I)
_NOTA = re.compile(r"^_.*_$")
_PARENTESIS = re.compile(r"^\(.*\)\.?$")


def es_derogado(texto: str | None) -> bool:
    """El cuerpo del artículo es solo una marca de derogación ("Se deroga.",
    "Derogado", "(DEROGADO, P.O. …)"), con sus notas de reforma."""
    if texto is None:
        return False
    parrafos = [p.strip() for p in texto.split("\n\n") if p.strip()]
    if parrafos and parrafos[0].startswith("#"):
        parrafos = parrafos[1:]
    cuerpo = [p for p in parrafos if not _NOTA.match(p)]
    if not cuerpo or not any(_DEROGA.match(p) for p in cuerpo):
        return False
    return all(_DEROGA.match(p) or _PARENTESIS.match(p) for p in cuerpo)


def etiqueta(texto: str | None, clave: str) -> str:
    """'4o' de '# Artículo 4o.'; si no hay encabezado, la clave sin ceros."""
    primera = (texto or "").split("\n", 1)[0]
    if primera.startswith("#"):
        e = re.sub(r"^#+\s*", "", primera)
        e = re.sub(r"^(art[íi]culo|regla|criterio|ficha|apartado)\s+", "", e, flags=re.I)
        e = e.rstrip(".").strip()
        if e:
            return e
    return clave.lstrip("0") or "0"


def clasificar(tipo: str, cambios: dict[str, tuple[str | None, str | None]]) -> dict[str, list[str]]:
    """Listas de artículos por trailer. `cambios`: clave → (texto antes, texto
    después), None si el archivo no existe de ese lado."""
    if tipo == "correccion":
        return {"Articulos-Corregidos": sorted(cambios)}
    if tipo != "reforma":
        return {}
    ad, mod, der = [], [], []
    for clave, (antes, despues) in sorted(cambios.items()):
        if antes is None:
            ad.append(clave)
        elif despues is None or (es_derogado(despues) and not es_derogado(antes)):
            der.append(clave)
        else:
            mod.append(clave)
    return {"Articulos-Adicionados": ad, "Articulos-Modificados": mod, "Articulos-Derogados": der}


def publicaciones(tipo: str, reformas_antes: set[str], reformas_despues: set[str],
                  version: str | None) -> tuple[list[str], str | None]:
    """(fechas, origen). Las fechas de reforma que aparecen nuevas en la
    metadata del documento ('notas'); si no hay, la versión del PDF ('portada')."""
    if tipo not in ("reforma", "alta"):
        return [], None
    nuevas = sorted(reformas_despues - reformas_antes) if tipo == "reforma" else []
    if nuevas:
        return nuevas, "notas"
    return ([version], "portada") if version else ([], None)


# ------------------------------------------------------------------ cálculo

def cambios_de_articulos(documento: str, rutas: Iterable[str], leer_antes: Lector,
                         leer_despues: Lector) -> dict[str, tuple[str | None, str | None]]:
    cambios = {}
    for r in rutas:
        clave = clave_articulo(r, documento)
        if clave is None:
            continue
        a, d = leer_antes(r), leer_despues(r)
        if a == d:
            continue
        cambios[clave] = (a.decode("utf-8") if a is not None else None,
                          d.decode("utf-8") if d is not None else None)
    return cambios


def tipo_por_existencia(documento: str, leer_antes: Lector, leer_despues: Lector) -> str | None:
    """'alta' o 'retiro' si el documento aparece o desaparece; si no, None."""
    antes, despues = info(documento, leer_antes)["existe"], info(documento, leer_despues)["existe"]
    if despues and not antes:
        return "alta"
    if antes and not despues:
        return "retiro"
    return None


def tipo_historico(documento: str, leer_antes: Lector, leer_despues: Lector) -> str:
    """Tipo de un commit del pasado, cuando no se conoce el PDF ni el extractor:
    alta/retiro por existencia; reforma si cambió la versión del documento o
    aparecieron fechas de reforma nuevas; si no, corrección."""
    t = tipo_por_existencia(documento, leer_antes, leer_despues)
    if t:
        return t
    a, d = info(documento, leer_antes), info(documento, leer_despues)
    if a["version"] != d["version"] or d["reformas"] - a["reformas"]:
        return "reforma"
    return "correccion"


def decidir_tipo(pdf_cambio: bool | None, extractor_cambio: bool | None) -> str:
    """Causa → tipo de commit en la vigilancia:
    'correccion' (mismo PDF), 'reforma' (otro PDF, mismo extractor),
    'separar' (cambiaron ambos: dos commits) o 'sin-separacion' (otro PDF y no
    se sabe con qué extractor se publicó lo anterior: todo es reforma)."""
    if not pdf_cambio:
        return "correccion"
    if extractor_cambio is None:
        return "sin-separacion"
    return "separar" if extractor_cambio else "reforma"


def texto_articulos(etiquetas: list[str]) -> str:
    if not etiquetas:
        return "solo metadata"
    if len(etiquetas) > MAX_EN_TITULO:
        return f"{len(etiquetas)} artículos"
    return ("art. " if len(etiquetas) == 1 else "arts. ") + ", ".join(etiquetas)


def texto_archivos(archivos: list[str]) -> str:
    if not archivos:
        return "sin archivos"
    if len(archivos) > MAX_ARCHIVOS_EN_TITULO:
        return f"{len(archivos)} archivos"
    return ", ".join(archivos)


def archivos_metadata(documento: str, rutas: Iterable[str]) -> list[str]:
    """Archivos del documento que no son artículos, relativos a su carpeta de
    metadata ('articulos.json') o, fuera de ella, a la del documento
    ('fuente/ruido.json')."""
    meta = _dir_metadata(documento)
    raiz = {"cpeum": "", "estatal": f"{documento}/"}.get(esquema_de(documento), f"{documento}/")
    nombres = set()
    for r in rutas:
        if clave_articulo(r, documento) is not None:
            continue
        if r.startswith(meta):
            nombres.add(r[len(meta):])
        elif r.startswith(raiz):
            nombres.add(r[len(raiz):])
    return sorted(nombres)


def tipo_sin_reforma(documento: str, rutas: Iterable[str], leer_antes: Lector,
                     leer_despues: Lector) -> str:
    """Mismo PDF, otro extractor: 'correccion' si cambia el texto de algún
    artículo; si solo cambia metadata, 'metadatos'."""
    return "correccion" if cambios_de_articulos(documento, rutas, leer_antes, leer_despues) \
        else "metadatos"


def titulo(tipo: str, sigla: str, *, medio: str | None = None, fecha: str | None = None,
           etiquetas: list[str] | None = None, motivo: str | None = None,
           archivos: list[str] | None = None) -> str:
    if tipo == "metadatos":
        return f"Metadatos de {sigla}: {texto_archivos(archivos or [])}"
    if tipo == "reforma":
        return (f"Reforma {sigla} ({medio_corto(medio)} {fecha or 's/f'}): "
                f"{texto_articulos(etiquetas or [])}")
    if tipo == "correccion":
        return f"Corrección de extracción {sigla}: {texto_articulos(etiquetas or [])}"
    if tipo == "alta":
        return f"Alta de {sigla}"
    if tipo == "retiro":
        return f"Retiro de {sigla}" + (f": {motivo}" if motivo else "")
    raise ValueError(f"tipo de documento desconocido: {tipo}")


def calcular(documento: str, tipo: str, rutas: Iterable[str], leer_antes: Lector,
             leer_despues: Lector, *, fuente: str | None = None,
             fuente_sha256: str | None = None, extractor: str | None = None,
             separacion: str | None = None, motivo: str | None = None
             ) -> tuple[str, list[tuple[str, str]]]:
    """(título, trailers) del commit de un documento.

    `rutas`: rutas que toca el commit; `leer_antes` / `leer_despues`: el árbol
    del repo antes y después (ruta → bytes, o None si no existe). Fuente,
    Fuente-Sha256 y Extractor se omiten si no se pasan (commits históricos)."""
    if tipo not in TIPOS_DOCUMENTO:
        raise ValueError(f"tipo de documento desconocido: {tipo}")
    rutas = list(rutas)
    a = info(documento, leer_antes)
    d = info(documento, leer_despues) if tipo != "retiro" else a
    cambios = cambios_de_articulos(documento, rutas, leer_antes, leer_despues) \
        if tipo in LISTAS or tipo == "metadatos" else {}
    listas = clasificar(tipo, cambios)
    fechas, origen = publicaciones(tipo, a["reformas"], d["reformas"], d["version"])
    t: list[tuple[str, str]] = [("Documento", documento), ("Tipo", tipo)]
    t += [("Publicacion", f) for f in fechas]
    if origen:
        t.append(("Publicacion-Origen", origen))
    if d["medio"]:
        t.append(("Medio", d["medio"]))
    for k in LISTAS.get(tipo, ()):
        if listas.get(k):
            t.append((k, ", ".join(listas[k])))
    if fuente:
        t.append(("Fuente", fuente))
    if fuente_sha256:
        t.append(("Fuente-Sha256", fuente_sha256))
    if extractor:
        t.append(("Extractor", extractor))
    if separacion and tipo == "reforma":
        t.append(("Separacion", separacion))
    if tipo == "metadatos" and cambios:
        raise ValueError(f"Tipo metadatos pero cambia el texto de: {', '.join(sorted(cambios)[:5])}")
    claves = sorted(cambios)
    etiquetas = [etiqueta(cambios[c][1] if cambios[c][1] is not None else cambios[c][0], c)
                 for c in claves]
    tit = titulo(tipo, d["sigla"], medio=d["medio"], fecha=fechas[0] if fechas else None,
                 etiquetas=etiquetas, motivo=motivo,
                 archivos=archivos_metadata(documento, rutas) if tipo == "metadatos" else None)
    return tit, t


def mensaje(documento: str, tipo: str, rutas: Iterable[str], leer_antes: Lector,
            leer_despues: Lector, **kw) -> str:
    """El mensaje completo (título + trailers) de `calcular`."""
    return formatear(*calcular(documento, tipo, rutas, leer_antes, leer_despues, **kw))


def trailers_indice(extractor: str | None = None) -> list[tuple[str, str]]:
    t = [("Tipo", "indice")]
    if extractor:
        t.append(("Extractor", extractor))
    return t


def extractor_id(repo: str, sha: str) -> str:
    return f"OpenCodice/{repo}@{sha[:7]}"


def sha256_bytes(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


# ------------------------------------------------------------------ validación

def validar(titulo_commit: str, trailers: list[tuple[str, str]], rutas: list[str],
            leer_antes: Lector, leer_despues: Lector, esquema: str, *,
            estricto: bool = True) -> list[str]:
    """Errores del commit (vacío si es válido). `estricto` exige Fuente,
    Fuente-Sha256 y Extractor, que todo commit nuevo lleva."""
    errores: list[str] = []
    if not trailers:
        return ["sin trailers"]
    vistos: dict[str, int] = {}
    for k, v in trailers:
        if k not in ORDEN:
            errores.append(f"trailer desconocido: {k}")
        vistos[k] = vistos.get(k, 0) + 1
    for k, n in vistos.items():
        if n > 1 and k != "Publicacion":
            errores.append(f"trailer repetido: {k}")
    tipo = valor(trailers, "Tipo")
    if tipo not in TIPOS:
        return errores + [f"Tipo inválido: {tipo!r}"]
    ext = valor(trailers, "Extractor")
    if ext is not None and not _EXTRACTOR.match(ext):
        errores.append(f"Extractor mal formado: {ext!r}")
    if estricto and ext is None and tipo != "indice":
        errores.append("falta Extractor")
    docs_tocados = {documento_de_ruta(r, esquema) for r in rutas}

    if tipo == "indice":
        if valor(trailers, "Documento") is not None:
            errores.append("un commit de índice no lleva Documento")
        tocados = sorted(r for r in rutas if documento_de_ruta(r, esquema) is not None)
        if tocados:
            errores.append(f"un commit de índice toca documentos: {', '.join(tocados[:5])}")
        sobran = set(vistos) - {"Tipo", "Extractor"}
        if sobran:
            errores.append(f"trailers de documento en un commit de índice: {', '.join(sorted(sobran))}")
        return errores

    doc = valor(trailers, "Documento")
    if not doc:
        return errores + ["falta Documento"]
    if esquema_de(doc) != esquema:
        errores.append(f"Documento {doc!r} no corresponde a este repositorio")
    if docs_tocados != {doc}:
        ajenas = sorted(r for r in rutas if documento_de_ruta(r, esquema) != doc)
        errores.append(f"el commit toca rutas fuera de {doc}: {', '.join(ajenas[:5])}")

    por_existencia = tipo_por_existencia(doc, leer_antes, leer_despues)
    if tipo in ("alta", "retiro") and por_existencia != tipo:
        errores.append(f"Tipo {tipo} pero el documento {'ya existía' if tipo == 'alta' else 'sigue existiendo'}")
    if tipo in ("reforma", "correccion", "metadatos") and por_existencia:
        errores.append(f"Tipo {tipo} pero el commit es un{'a' if por_existencia == 'alta' else ''} {por_existencia}")

    fuente, sha = valor(trailers, "Fuente"), valor(trailers, "Fuente-Sha256")
    if sha is not None and not _SHA256.match(sha):
        errores.append(f"Fuente-Sha256 mal formado: {sha!r}")
    if estricto and tipo != "retiro":
        if not fuente:
            errores.append("falta Fuente")
        if not sha:
            errores.append("falta Fuente-Sha256")
    if sha and tipo != "retiro" and rutas_fuente(doc):
        guardado = next((leer_despues(r) for r in rutas_fuente(doc) if leer_despues(r) is not None), None)
        if guardado is not None and sha256_bytes(guardado) != sha:
            errores.append("Fuente-Sha256 no coincide con el archivo de fuente/ del commit")
    sep = valor(trailers, "Separacion")
    if sep is not None and (sep != "no-disponible" or tipo != "reforma"):
        errores.append(f"Separacion inválida: {sep!r}")
    for f in valores(trailers, "Publicacion"):
        if not _FECHA.match(f):
            errores.append(f"Publicacion mal formada: {f!r}")

    if tipo in ("correccion", "metadatos"):
        corregidos = cambios_de_articulos(doc, rutas, leer_antes, leer_despues)
        if tipo == "metadatos" and corregidos:
            return errores + [f"Tipo metadatos pero cambia el texto de: "
                              f"{', '.join(sorted(corregidos)[:5])}"]
        # Los commits publicados antes de que existiera `metadatos` dicen
        # `correccion` aunque no corrijan ningún artículo; solo se validan así
        # en modo no estricto.
        if tipo == "correccion" and not corregidos and estricto:
            errores.append("corrección sin artículos corregidos: es Tipo metadatos")

    # Lo demás se recalcula del árbol y debe coincidir exactamente.
    try:
        esperado_t, esperados = calcular(doc, tipo, rutas, leer_antes, leer_despues,
                                         fuente=fuente, fuente_sha256=sha, extractor=ext,
                                         separacion=sep)
    except Exception as e:                       # noqa: BLE001 — se reporta
        return errores + [f"no se pudieron recalcular los trailers: {e}"]
    for k in ("Publicacion", "Publicacion-Origen", "Medio", "Articulos-Adicionados",
              "Articulos-Modificados", "Articulos-Derogados", "Articulos-Corregidos"):
        dado, calc = valores(trailers, k), valores(esperados, k)
        if dado != calc:
            errores.append(f"{k}: dice {', '.join(dado) or '(nada)'}; el diff dice "
                           f"{', '.join(calc) or '(nada)'}")
    if tipo == "retiro":
        if not titulo_commit.startswith(esperado_t):
            errores.append(f"título incoherente: se esperaba que empezara con {esperado_t!r}")
    elif titulo_commit != esperado_t:
        errores.append(f"título incoherente: se esperaba {esperado_t!r}")
    return errores


# ------------------------------------------------------------------ lectores

def lector_dict(archivos: dict[str, "str | bytes"]) -> Lector:
    """Lector sobre un dict ruta → contenido (pruebas, reescritura de historial)."""
    def leer(ruta: str) -> bytes | None:
        v = archivos.get(ruta)
        return v.encode("utf-8") if isinstance(v, str) else v
    return leer


def lector_git(repo: str, rev: str | None) -> Lector:
    """Lector del árbol de `rev` en `repo` (None: árbol vacío, para el primer
    commit). Cachea lo leído."""
    import subprocess
    cache: dict[str, bytes | None] = {}

    def leer(ruta: str) -> bytes | None:
        if rev is None:
            return None
        if ruta not in cache:
            r = subprocess.run(["git", "-C", repo, "cat-file", "blob", f"{rev}:{ruta}"],
                               capture_output=True)
            cache[ruta] = r.stdout if r.returncode == 0 else None
        return cache[ruta]
    return leer


def lector_fs(raiz: str) -> Lector:
    """Lector del árbol de trabajo."""
    from pathlib import Path

    def leer(ruta: str) -> bytes | None:
        p = Path(raiz) / ruta
        return p.read_bytes() if p.is_file() else None
    return leer
