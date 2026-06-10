"""Referencias legales cruzadas — capa derivada, determinista.

Los criterios del SAT, las reglas de la RMF/RGCE y los reglamentos citan en su
cuerpo a los artículos de ley que desarrollan ("el artículo 151 de la Ley del
ISR…"). Esta capa extrae esas citas y las resuelve a ids del corpus
(`lisr/151`), para que el RAG pueda llevar la fuente primaria al contexto
cuando recupera al satélite que la parafrasea.

Disciplina:
- Solo se emite una referencia si resuelve a una unidad EXISTENTE del corpus
  (validación contra metadata/<doc>/articulos.json) — cero refs rotas.
- Sin anáforas ("dicha Ley", "del mismo Código", "el citado ordenamiento"):
  resolverlas requiere seguimiento de discurso y equivocarse contamina; las
  citas explícitas cubren la gran mayoría.
- Se excluyen citas a versiones históricas ("…de la Ley del ISR vigente hasta
  el 31 de diciembre de 2013"): el corpus solo tiene el texto vigente.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .modelo import _ascii

# ------------------------- artículo → clave de unidad ----------------------- #
# "1o.", "29-A", "2o.-A", "17-H Bis", "137 Bis 1". El marcador ordinal "o" debe
# venir pegado al número ("4o."), no confundir con la disyuntiva "27 o 28".
_TOKEN = re.compile(
    r"(?P<num>\d{1,3})(?!\d)(?!,\d{3})"
    r"(?:o\.?)?"
    r"(?:\s*-\s*(?P<letra>[A-Z])(?![A-Za-zÁ-ÚÑáéíóúñ]))?"
    r"(?:\s+(?P<ordinal>[Bb]is|[Tt]er|[Qq]u[áa]ter|[Qq]uinquies|[Ss]exies"
    r"|[Ss]epties|[Oo]cties|[Nn]onies|[Dd]ecies)\b\.?"
    r"(?:\s+(?P<ordnum>\d{1,2})\b)?)?"
)

# Un número precedido por estas palabras no es un artículo (fracciones,
# párrafos, montos) ni tampoco fechas o porcentajes.
_PRECEDIDO_NO_ART = re.compile(
    r"(?:fracci(?:ón|ones)|incisos?|p[áa]rrafos?|numerales?|apartados?|punto"
    r"|\$)\s*$", re.IGNORECASE)
_SIGUE_NO_ART = re.compile(
    r"\s*(?:%|por\s+ciento|de\s+(?:enero|febrero|marzo|abril|mayo|junio|julio"
    r"|agosto|septiembre|octubre|noviembre|diciembre))", re.IGNORECASE)

_ART_KW = re.compile(r"[Aa]rt[íi]culos?\s+")
_REGLA_KW = re.compile(r"[Rr]eglas?\s+")
_REGLA_NUM = re.compile(r"(?P<num>(?:\d+\.){1,3}\d+)")
_VIGENTE_HIST = re.compile(r"vigente\s+(?:hasta|al)\b", re.IGNORECASE)

_VENTANA = 140  # chars tras la palabra clave donde buscar números y la ley


def clave_articulo(num: str, letra: str | None, ordinal: str | None,
                   ordnum: str | None) -> str:
    """Misma acuñación que Unidad.clave: '2o.-A' → '002-a', '17-H Bis' → '017-h-bis'."""
    partes = [f"{int(num):03d}"]
    if letra:
        partes.append(_ascii(letra))
    if ordinal:
        partes.append(_ascii(ordinal))
    if ordnum:
        partes.append(ordnum)
    return "-".join(partes)


# ------------------------------ nombre de ley → doc ------------------------- #
# Alias explícitos tal como aparecen en los textos. Se prueban en orden (los
# largos primero: "reglamento de la ley del isr" debe ganarle a "ley del isr").
# Las claves anuales (lif-2026, rmf-2026…) se resuelven contra el corpus.
_ALIAS: list[tuple[str, str]] = [
    ("reglamento del código fiscal de la federación", "rcff"),
    ("reglamento de la ley del impuesto sobre la renta", "rlisr"),
    ("reglamento de la ley del isr", "rlisr"),
    ("reglamento de la ley del impuesto al valor agregado", "rliva"),
    ("reglamento de la ley del iva", "rliva"),
    ("reglamento de la ley del impuesto especial sobre producción y servicios", "rlieps"),
    ("reglamento de la ley del ieps", "rlieps"),
    ("reglamento de la ley aduanera", "rladua"),
    ("reglamento de la lfpiorpi", "rlfpiorpi"),
    ("código fiscal de la federación", "cff"),
    ("ley del impuesto sobre la renta", "lisr"),
    ("ley del impuesto al valor agregado", "liva"),
    ("ley del impuesto especial sobre producción y servicios", "lieps"),
    ("ley del impuesto sobre automóviles nuevos", "lfisan"),
    ("ley federal del impuesto sobre automóviles nuevos", "lfisan"),
    ("ley federal para la prevención e identificación de operaciones "
     "con recursos de procedencia ilícita", "lfpiorpi"),
    ("ley federal de los derechos del contribuyente", "lfdc"),
    ("ley federal de procedimiento contencioso administrativo", "lfpca"),
    ("ley del servicio de administración tributaria", "lsat"),
    ("ley de ingresos sobre hidrocarburos", "lish"),
    ("ley de ingresos de la federación", "lif-"),
    ("ley federal de derechos", "lfd"),
    ("ley de coordinación fiscal", "lcf"),
    ("ley aduanera", "ladua"),
    ("ley del isr", "lisr"),
    ("ley del iva", "liva"),
    ("ley del ieps", "lieps"),
    ("resolución miscelánea fiscal", "rmf-"),
    ("reglas generales de comercio exterior", "rgce-"),
    ("resolución de facilidades administrativas", "rfa-"),
    ("lfpiorpi", "lfpiorpi"),
    ("rlisr", "rlisr"),
    ("rliva", "rliva"),
    ("rcff", "rcff"),
    ("lisr", "lisr"),
    ("liva", "liva"),
    ("lieps", "lieps"),
    ("cff", "cff"),
    ("rgce", "rgce-"),
    ("rmf", "rmf-"),
    ("rfa", "rfa-"),
]
_ALIAS_RE = re.compile(
    r"\b(" + "|".join(re.escape(a) for a, _ in sorted(_ALIAS, key=lambda x: -len(x[0])))
    + r")\b", re.IGNORECASE)
_ALIAS_MAP = {a: c for a, c in _ALIAS}

# Documentos que pueden decir "esta Ley" refiriéndose a sí mismos.
_LEYES = {"cff", "lisr", "liva", "lieps", "lfd", "ladua", "lcf", "lfpca",
          "lfdc", "lfisan", "lish", "lfpiorpi", "lsat"}

# Referencias contextuales: dependen del documento donde aparece la cita.
# "la Ley" a secas dentro de un reglamento (o de las RGCE) es SU ley.
_LEY_DE = {"rcff": "cff", "rlisr": "lisr", "rliva": "liva", "rlieps": "lieps",
           "rladua": "ladua", "rlfpiorpi": "lfpiorpi", "rgce-": "ladua"}
_ESTA_LEY = re.compile(r"(?:esta|la\s+presente)\s+ley\b", re.IGNORECASE)
_ESTE_CODIGO = re.compile(r"(?:este|el|del)\s+c[óo]digo\b(?!\s+(?:civil|penal"
                          r"|nacional|de\s+comercio))", re.IGNORECASE)
_ESTE_REGLAMENTO = re.compile(r"(?:este|el\s+presente)\s+reglamento\b", re.IGNORECASE)
_LA_LEY = re.compile(r"\bla\s+ley\b(?!\s+(?:del?\b|de\s|federal|general|aduanera"
                     r"|citada|mencionada|referida|señalada|aludida|que\b))",
                     re.IGNORECASE)


class Resolutor:
    """Resuelve citas legales de un texto a ids `documento/unidad` del corpus."""

    def __init__(self, claves_por_doc: dict[str, set[str]]):
        self._claves = claves_por_doc
        # "lif-" → la clave anual presente en el corpus (la más reciente).
        self._anuales = {pref: max(c for c in claves_por_doc if c.startswith(pref))
                         for pref in ("lif-", "rmf-", "rgce-", "rfa-")
                         if any(c.startswith(pref) for c in claves_por_doc)}

    def _doc_real(self, clave: str) -> str | None:
        if clave.endswith("-"):
            clave = self._anuales.get(clave, "")
        return clave if clave in self._claves else None

    def _doc_en(self, ventana: str, doc_origen: str) -> tuple[str | None, int]:
        """Primer documento citado en la ventana → (clave, posición del match)."""
        candidatos: list[tuple[int, str]] = []
        m = _ALIAS_RE.search(ventana)
        if m:
            candidatos.append((m.start(), _ALIAS_MAP[m.group(1).lower()]))
        m = _ESTE_CODIGO.search(ventana)
        if m and doc_origen in ("cff", "rcff"):
            candidatos.append((m.start(), "cff"))
        m = _ESTA_LEY.search(ventana)
        if m and (doc_origen in _LEYES or doc_origen.startswith("lif-")):
            candidatos.append((m.start(), doc_origen))
        m = _ESTE_REGLAMENTO.search(ventana)
        if m and doc_origen in _LEY_DE:
            candidatos.append((m.start(), doc_origen))
        clave_ctx = next((v for k, v in _LEY_DE.items()
                          if doc_origen == k or doc_origen.startswith(k)), None)
        m = _LA_LEY.search(ventana)
        if m and clave_ctx:
            candidatos.append((m.start(), clave_ctx))
        if not candidatos:
            return None, -1
        pos, clave = min(candidatos)
        return self._doc_real(clave), pos

    def _articulos(self, texto: str, doc_origen: str) -> list[str]:
        out: list[str] = []
        for kw in _ART_KW.finditer(texto):
            ini = kw.end()
            sig = _ART_KW.search(texto, ini)
            fin = min(ini + _VENTANA, sig.start() if sig else len(texto))
            ventana = texto[ini:fin]
            doc, pos_ley = self._doc_en(ventana, doc_origen)
            if not doc:
                continue
            if _VIGENTE_HIST.search(ventana[pos_ley:pos_ley + 60]):
                continue  # cita a una versión histórica, no al texto vigente
            for t in _TOKEN.finditer(ventana, 0, pos_ley):
                if _PRECEDIDO_NO_ART.search(ventana, 0, t.start()):
                    continue
                if _SIGUE_NO_ART.match(ventana, t.end()):
                    continue
                clave = clave_articulo(t["num"], t["letra"], t["ordinal"], t["ordnum"])
                if clave in self._claves.get(doc, ()):
                    out.append(f"{doc}/{clave}")
        return out

    def _reglas(self, texto: str, doc_origen: str) -> list[str]:
        out: list[str] = []
        propio = doc_origen if any(doc_origen.startswith(p)
                                   for p in ("rmf-", "rgce-", "rfa-")) else None
        for kw in _REGLA_KW.finditer(texto):
            ini = kw.end()
            ventana = texto[ini:ini + _VENTANA]
            nums = [m["num"] for m in _REGLA_NUM.finditer(ventana[:60])]
            if not nums:
                continue
            doc, _ = self._doc_en(ventana, doc_origen)
            if doc is None or doc not in self._anuales.values():
                doc = propio  # sin documento explícito: la propia resolución
            if not doc:
                continue
            out.extend(f"{doc}/{n}" for n in nums if n in self._claves.get(doc, ()))
        return out

    def referencias(self, texto: str, doc_origen: str) -> list[str]:
        """Ids únicos citados en `texto`, en orden de aparición."""
        vistos: set[str] = set()
        out: list[str] = []
        for ref in self._articulos(texto, doc_origen) + self._reglas(texto, doc_origen):
            if ref not in vistos:
                vistos.add(ref)
                out.append(ref)
        return out


# --------------------------- aplicación sobre el repo ----------------------- #
def claves_corpus(data_repo: str | Path) -> dict[str, set[str]]:
    """Unidades existentes por documento, leídas de metadata/<doc>/articulos.json."""
    out: dict[str, set[str]] = {}
    for idx in sorted(Path(data_repo).glob("metadata/*/articulos.json")):
        d = json.loads(idx.read_text(encoding="utf-8"))
        unidades = (d.get("articulos") or d.get("reglas") or d.get("criterios")
                    or d.get("fichas") or d.get("apartados") or [])
        out[d["documento"]] = {u["clave"] for u in unidades}
    return out


def aplicar_referencias(data_repo: str | Path) -> dict[str, int]:
    """Anota cada pasaje de metadata/*/pasajes.jsonl con sus `referencias`.

    Post-proceso idempotente sobre la capa derivada: no necesita PDFs ni
    re-extracción. La auto-referencia (un pasaje citando a su propia unidad)
    se omite: no aporta contexto nuevo. Devuelve {doc: pasajes con refs}.
    """
    res = Resolutor(claves_corpus(data_repo))
    stats: dict[str, int] = {}
    for path in sorted(Path(data_repo).glob("metadata/*/pasajes.jsonl")):
        lineas = []
        con_refs = 0
        for linea in path.read_text(encoding="utf-8").splitlines():
            if not linea.strip():
                continue
            p = json.loads(linea)
            refs = [r for r in res.referencias(p["texto"], p["documento"])
                    if r != f"{p['documento']}/{p['clave_unidad']}"]
            if refs:
                p["referencias"] = refs
                con_refs += 1
            else:
                p.pop("referencias", None)
            lineas.append(json.dumps(p, ensure_ascii=False))
        path.write_text("\n".join(lineas) + "\n", encoding="utf-8")
        stats[path.parent.name] = con_refs
    return stats
