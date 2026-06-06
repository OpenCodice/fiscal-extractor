"""Materializa el corpus fiscal en el repo de datos, en capas independientes.

Itera el registro de documentos. Para cada documento escribe DOS capas que
nunca se tocan entre sí:

  Capa 1 — TEXTO       <clave>/NNN.md          encabezado + cuerpo fiel
  Capa 3 — METADATA    metadata/<clave>/*.json índice derivado, regenerable
                       metadata/documentos.json índice maestro del corpus

`escribir_texto` y `escribir_metadata` son independientes: se puede regenerar el
índice sin tocar un solo .md.
"""
from __future__ import annotations

import json
from pathlib import Path

import re

from .modelo import Regla, Unidad
from .normalize import normalize_body
from .parsers import resolver
from .parsers.articulado import fecha_version, texto_limpio as _texto_articulado
from .parsers.reglas import fecha_publicacion, reglas_y_anomalias, texto_limpio as _texto_reglas
from .registro import Documento, POR_CLAVE, activos


def render_markdown(u: Unidad) -> str:
    """Texto de la unidad: encabezado + cuerpo en párrafos. Sin metadata."""
    body = normalize_body(u.cuerpo, u.etiqueta)
    return f"# {u.etiqueta}\n\n{body}\n"


def escribir_texto(unidades: list[Unidad], doc: Documento, data_repo: str) -> None:
    """Capa 1: escribe los archivos de texto `<clave>/NNN.md`."""
    art_dir = Path(data_repo) / doc.clave
    art_dir.mkdir(parents=True, exist_ok=True)
    for old in art_dir.glob("*.md"):       # limpiar para reflejar supresiones en git
        old.unlink()
    for u in unidades:
        (art_dir / f"{u.clave}.md").write_text(render_markdown(u), encoding="utf-8")


def escribir_metadata(unidades: list[Unidad], doc: Documento, data_repo: str,
                      version: str | None = None) -> None:
    """Capa 3: índice derivado en `metadata/<clave>/` (no toca los .md)."""
    meta_dir = Path(data_repo) / "metadata" / doc.clave
    meta_dir.mkdir(parents=True, exist_ok=True)

    indice = [
        {
            "clave": u.clave,
            "articulo": u.numero,
            "letra": u.letra,
            "ordinal": u.ordinal,
            "etiqueta": u.etiqueta,
            "cita": f"{u.etiqueta} {doc.sigla}",
            "titulo": u.titulo,
            "capitulo": u.capitulo,
            "derogado": u.derogado,
            "ultima_reforma": u.ultima_reforma.isoformat() if u.ultima_reforma else None,
            "num_reformas": len(u.fechas_reforma),
            "reformas": [d.isoformat() for d in u.fechas_reforma],
            "archivo": f"{doc.clave}/{u.clave}.md",
        }
        for u in unidades
    ]
    doc_idx = {
        "documento": doc.clave,
        "etiqueta": doc.etiqueta,
        "sigla": doc.sigla,
        "tipo": doc.tipo,
        "fuente": doc.url,
        "version": version,
        "num_articulos": len(unidades),
        "articulos": indice,
    }
    (meta_dir / "articulos.json").write_text(
        json.dumps(doc_idx, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Mapa reforma → unidades afectadas, ordenado por fecha.
    reformas: dict[str, list[str]] = {}
    for u in unidades:
        for d in u.fechas_reforma:
            reformas.setdefault(d.isoformat(), []).append(u.clave)
    reformas_sorted = {k: sorted(set(v)) for k, v in sorted(reformas.items())}
    (meta_dir / "reformas.json").write_text(
        json.dumps(reformas_sorted, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def escribir_indice_maestro(data_repo: str) -> None:
    """metadata/documentos.json: índice del corpus, DERIVADO de la metadata que
    exista en disco. Así es independiente del orden de build (construir un solo
    documento no borra a los demás del índice)."""
    meta = Path(data_repo) / "metadata"
    meta.mkdir(parents=True, exist_ok=True)
    resumen = []
    for idx_path in sorted(meta.glob("*/articulos.json")):
        d = json.loads(idx_path.read_text(encoding="utf-8"))
        resumen.append({
            "clave": d["documento"], "etiqueta": d["etiqueta"], "sigla": d["sigla"],
            "tipo": d["tipo"], "num_articulos": d["num_articulos"], "version": d["version"],
        })
    (meta / "documentos.json").write_text(
        json.dumps({"documentos": resumen}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")


# ----------------------------- reglas (RMF) -------------------------------- #
def render_regla_markdown(r: Regla) -> str:
    """Texto de la regla: encabezado (número + título) + cuerpo en párrafos."""
    body = normalize_body(r.cuerpo, r.etiqueta)
    return f"# {r.etiqueta}\n\n{body}\n"


def _vigencia_anual(clave: str) -> tuple[str | None, str | None]:
    """De 'rmf-2026' → ('2026-01-01', '2026-12-31'). La RMF rige el ejercicio."""
    m = re.search(r"(\d{4})", clave)
    if not m:
        return None, None
    y = m.group(1)
    return f"{y}-01-01", f"{y}-12-31"


def escribir_reglas_texto(reglas: list[Regla], doc: Documento, data_repo: str) -> None:
    dirp = Path(data_repo) / doc.clave
    dirp.mkdir(parents=True, exist_ok=True)
    for old in dirp.glob("*.md"):
        old.unlink()
    for r in reglas:
        (dirp / f"{r.clave}.md").write_text(render_regla_markdown(r), encoding="utf-8")


def escribir_reglas_metadata(reglas: list[Regla], doc: Documento, data_repo: str,
                             version: str | None) -> None:
    meta_dir = Path(data_repo) / "metadata" / doc.clave
    meta_dir.mkdir(parents=True, exist_ok=True)
    desde, hasta = _vigencia_anual(doc.clave)
    indice = [
        {
            "clave": r.clave,
            "numero": r.numero,
            "nivel": r.nivel,
            "etiqueta": r.etiqueta,
            "cita": f"Regla {r.numero}. {doc.sigla}",
            "titulo_regla": r.titulo_regla,
            "titulo": r.titulo,
            "capitulo": r.capitulo,
            "seccion": r.seccion,
            "referencias": r.referencias,
            "vigente_desde": desde,
            "vigente_hasta": hasta,
            "archivo": f"{doc.clave}/{r.clave}.md",
        }
        for r in reglas
    ]
    doc_idx = {
        "documento": doc.clave, "etiqueta": doc.etiqueta, "sigla": doc.sigla,
        "tipo": doc.tipo, "fuente": doc.url, "version": version,
        "vigente_desde": desde, "vigente_hasta": hasta,
        "num_articulos": len(reglas), "reglas": indice,
    }
    (meta_dir / "articulos.json").write_text(
        json.dumps(doc_idx, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # reformas.json vacío: la RMF anual no anota reforma por regla (se sustituye entera).
    (meta_dir / "reformas.json").write_text("{}\n", encoding="utf-8")


def _escribir_anomalias(anomalias: list[dict], doc: Documento, data_repo: str) -> None:
    """Líneas ambiguas que el parser de reglas NO tomó como regla (auditoría).

    No es la fuente de verdad; es el registro de lo descartado para que el
    validador / un humano confirmen que ninguna era una regla real perdida.
    """
    meta_dir = Path(data_repo) / "metadata" / doc.clave
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "anomalias.json").write_text(
        json.dumps({"documento": doc.clave, "anomalias": anomalias},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_documento(doc: Documento, pdf_path: str, data_repo: str,
                    what: str = "all") -> list:
    """Parsea un documento y materializa las capas pedidas. Devuelve sus unidades."""
    if doc.parser == "reglas":
        unidades, anomalias = reglas_y_anomalias(_texto_reglas(pdf_path))
        v = fecha_publicacion(pdf_path)
        version = v.isoformat() if v else None
        if what in ("all", "text"):
            escribir_reglas_texto(unidades, doc, data_repo)
        if what in ("all", "metadata"):
            escribir_reglas_metadata(unidades, doc, data_repo, version=version)
            _escribir_anomalias(anomalias, doc, data_repo)
        return unidades
    unidades = resolver(doc.parser)(pdf_path, doc)
    # articulado
    v = fecha_version(pdf_path)
    version = v.isoformat() if v else None
    if what in ("all", "text"):
        escribir_texto(unidades, doc, data_repo)
    if what in ("all", "metadata"):
        escribir_metadata(unidades, doc, data_repo, version=version)
    return unidades


def build(claves: list[str] | None, pdf_por_clave: dict[str, str], data_repo: str,
          what: str = "all") -> dict[str, list[Unidad]]:
    """Construye los documentos indicados (o todos los activos). pdf_por_clave mapea
    clave → ruta del PDF descargado. Actualiza también el índice maestro."""
    docs = [POR_CLAVE[c] for c in claves] if claves else activos()
    salida: dict[str, list[Unidad]] = {}
    for doc in docs:
        pdf = pdf_por_clave.get(doc.clave)
        if not pdf:
            raise FileNotFoundError(f"falta el PDF para '{doc.clave}'")
        salida[doc.clave] = build_documento(doc, pdf, data_repo, what=what)
    if what in ("all", "metadata"):
        escribir_indice_maestro(data_repo)
    return salida
