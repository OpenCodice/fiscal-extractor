"""Verificación de una reconstrucción del corpus contra los PDF oficiales.

Tras `actualizar`, revisa cada unidad cuyo texto cambió (según git) y decide si
la extracción es fiel al PDF. No juzga si el cambio es una reforma de fondo: el
repo debe reflejar lo que dice el PDF. Dos comprobaciones independientes:

  - `cobertura` (determinista, todas las unidades cambiadas): cada párrafo
    extraído debe estar literal en el PDF y entre párrafos consecutivos no
    puede quedar texto del PDF sin extraer.
  - LLM (hasta MAX_LLM unidades): compara los párrafos cambiados contra las
    páginas crudas y detecta lo que la cobertura no ve —encabezados o pies de
    página colados, texto de otra unidad—. Lo que el modelo base no dé por fiel
    se reevalúa con un modelo más capaz, cuyo veredicto es el definitivo.

El LLM nunca redacta texto legal: solo emite veredictos.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

from .parsers import articulado, criterios, reglas
from .registro import POR_CLAVE, Documento

MODELO_DEFAULT = "gpt-5.4-mini"
MODELO_FUERTE_DEFAULT = "gpt-5.5"
MAX_LLM = 60                 # unidades revisadas por LLM por corrida (control de costo)
MAX_PAGINAS_CONTEXTO = 6
MAX_BLOQUE_CHARS = 1500
MAX_UNIDAD_CHARS = 12000
MAX_HUECO = 0

VEREDICTOS = ("fiel", "artefacto", "incierto")

# Encabezados estructurales que los parsers consumen como contexto, no como cuerpo.
ENCABEZADO_RE = re.compile(
    r"\b(?:T[íi]tulo|Cap[íi]tulo|Secci[óo]n)\s+(?:[IVXLCDM]+\b|[úu]nic[oa]\b|"
    r"\d+(?:\.\d+)*\.?|[a-záéíóúñ]+\b)(?:\s+Bis\b)?",
    re.IGNORECASE)


MAX_ENCABEZADO_CHARS = 400


def _es_encabezado(texto: str) -> bool:
    """Hueco que es solo un encabezado estructural con su nombre descriptivo
    ('TÍTULO II DE LAS PERSONAS MORALES'), no texto de un artículo."""
    return bool(ENCABEZADO_RE.match(texto) and len(texto) <= MAX_ENCABEZADO_CHARS
                and not re.search(r"\bArt[íi]culo\s+\d", texto))


def paginas_crudas(pdf_path: str) -> list[str]:
    """Texto crudo por página. Extraerlo es lo caro de toda la verificación, así
    que se guarda junto al PDF y se reutiliza mientras el PDF no cambie."""
    pdf = Path(pdf_path)
    cache = pdf.with_suffix(".paginas.json")
    firma = [pdf.stat().st_size, pdf.stat().st_mtime_ns]
    if cache.exists():
        guardado = json.loads(cache.read_text(encoding="utf-8"))
        if guardado.get("firma") == firma:
            return guardado["paginas"]
    import pdfplumber
    with pdfplumber.open(pdf_path) as doc:
        paginas = [page.extract_text() or "" for page in doc.pages]
    cache.write_text(json.dumps({"firma": firma, "paginas": paginas}, ensure_ascii=False),
                     encoding="utf-8")
    return paginas


def texto_limpio(doc: Documento, pdf_path: str) -> str:
    """El mismo texto sin encabezados/pies que consume el parser del documento."""
    paginas = paginas_crudas(pdf_path)
    if doc.parser == "articulado":
        return articulado.limpiar_paginas(paginas, doc)
    if doc.parser == "reglas":
        return reglas.limpiar_paginas(paginas)
    return criterios.limpiar_paginas(paginas)


def _norm(s: str) -> str:
    d = unicodedata.normalize("NFD", s.lower())
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in d if unicodedata.category(c) != "Mn"))


# ------------------------------------------------------------------ cambios

@dataclass
class Cambio:
    doc: str
    clave: str
    antes: str
    despues: str

    @property
    def ref(self) -> str:
        return f"{self.doc}/{self.clave}"

    def bloques(self) -> tuple[list[str], list[str]]:
        """(eliminados, añadidos) a nivel de párrafo."""
        a = [b for b in self.antes.split("\n\n") if b.strip()]
        d = [b for b in self.despues.split("\n\n") if b.strip()]
        sa, sd = set(a), set(d)
        return [b for b in a if b not in sd], [b for b in d if b not in sa]


def _git(out: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(out), *args],
                          capture_output=True, text=True).stdout


def cambios(out: str | Path) -> list[Cambio]:
    """Unidades de texto (`<clave>/NNN.md`) que difieren de HEAD."""
    out = Path(out)
    rutas = set()
    for line in _git(out, "status", "--porcelain", "--no-renames", "-uall").splitlines():
        ruta = Path(line[3:].strip().strip('"'))
        if ruta.suffix == ".md" and len(ruta.parts) == 2 and ruta.parts[0] in POR_CLAVE:
            rutas.add(ruta)
    res = []
    for ruta in sorted(rutas):
        actual = out / ruta
        res.append(Cambio(
            doc=ruta.parts[0], clave=ruta.stem,
            antes=_git(out, "show", f"HEAD:{ruta.as_posix()}"),
            despues=actual.read_text(encoding="utf-8") if actual.exists() else "",
        ))
    return res


# ------------------------------------------------------------------ cobertura

@dataclass
class Flujo:
    """Texto limpio del PDF + su forma normalizada, con índice de vuelta."""
    texto: str
    norma: str
    idx: list[int]

    @classmethod
    def de(cls, texto: str) -> "Flujo":
        norma, idx = [], []
        for i, ch in enumerate(texto):
            n = _norm(ch)
            norma.append(n)
            idx.extend([i] * len(n))
        return cls(texto, "".join(norma), idx)

    def original(self, a: int, b: int) -> str:
        return " ".join(self.texto[self.idx[a]:self.idx[b - 1] + 1].split())


def cobertura(md: str, flujo: Flujo) -> list[dict]:
    """Comprobación determinista de una unidad extraída contra el PDF."""
    bloques = [n for b in md.split("\n\n")
               if b.strip() and not b.startswith("# ") and (n := _norm(b))]
    unicos = [(len(b), i) for i, b in enumerate(bloques) if flujo.norma.count(b) == 1]
    if not unicos:
        # Unidad sin ningún párrafo único (p. ej. "(Se deroga)."): solo literalidad.
        return [{"tipo": "no_literal", "fragmento": b[:120]}
                for b in bloques if b not in flujo.norma]
    k = max(unicos)[1]
    ini = flujo.norma.find(bloques[k])
    fin = ini + len(bloques[k])
    problemas: list[dict] = []

    def hueco(a: int, b: int) -> None:
        if b - a <= MAX_HUECO:
            return
        texto = flujo.original(a, b)
        if not _es_encabezado(texto):
            problemas.append({"tipo": "texto_omitido", "fragmento": texto[:300]})

    for b in bloques[k + 1:]:
        p = flujo.norma.find(b, fin)
        if p == -1:
            problemas.append({"tipo": "no_literal", "fragmento": b[:120]})
            continue
        hueco(fin, p)
        fin = p + len(b)
    for b in reversed(bloques[:k]):
        p = flujo.norma.rfind(b, 0, ini)
        if p == -1:
            problemas.append({"tipo": "no_literal", "fragmento": b[:120]})
            continue
        hueco(p + len(b), ini)
        ini = p
    return problemas


def encabezado_pegado(md: str) -> list[dict]:
    """Último párrafo de un artículo que tiene forma de encabezado: corto, sin
    puntuación final, sin nota de reforma y sin ser fracción. Es texto literal
    del PDF, así que `cobertura` no lo ve, pero es estructura (el nombre de un
    capítulo, un epígrafe) pegada al artículo anterior."""
    bloques = [b.strip() for b in md.split("\n\n") if b.strip() and not b.startswith("# ")]
    while bloques and bloques[-1].startswith("_"):
        bloques.pop()                       # notas de reforma en cursiva
    if len(bloques) < 2:
        return []
    b = bloques[-1]
    if (len(b) > 150 or "DOF" in b or re.search(r"[.;:)…”\"»]$", b)
            or re.match(r"^(?:[IVXLCDM]+|[a-zñ]{1,2}|[A-Z]|\d+)\s*[.)\-]", b)
            or not b[:1].isupper()
            # Una tabla que cierra el artículo ('Años de servicios … 10 80% 11
            # 85%') tampoco lleva puntuación final; un encabezado no trae cifras.
            or len(re.findall(r"\d+", b)) >= 4):
        return []
    return [{"tipo": "encabezado_pegado", "fragmento": b[:200]}]


# Señales de que una unidad absorbió lo que sigue al articulado: los
# transitorios y los decretos de reforma que la Cámara compila al final.
_FUERA_DEL_ARTICULADO = re.compile(
    r"^(?:DECRETO\s+(?:por\s+el\s+que|que)\b|Publicado\s+en\s+el\s+Diario\s+Oficial\s+de\s+la"
    r"\s+Federaci[óo]n\s+el\b|(?:ART[ÍI]CULOS?\s+)?TRANSITORIOS?:?$|T\s+r\s+a\s+n\s+s\s+i"
    # Otro artículo del decreto que expidió la ley ('ARTÍCULO SEGUNDO.- …'):
    # los artículos de una ley llevan número, los de un decreto, ordinal en palabra.
    r"|ART[ÍI]CULO\s+(?:PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO|S[ÉE]PTIMO|OCTAVO|"
    r"NOVENO|D[ÉE]CIMO|[ÚU]NICO)\b)",
    re.MULTILINE)


def fuera_del_articulado(md: str) -> list[dict]:
    """Un artículo que contiene transitorios o decretos de reforma: el corte del
    articulado no se encontró y el último artículo se tragó el resto del PDF."""
    m = _FUERA_DEL_ARTICULADO.search(md.split("\n", 2)[-1])
    if not m:
        return []
    cuerpo = md.split("\n", 2)[-1]
    return [{"tipo": "fuera_del_articulado", "fragmento": cuerpo[m.start():m.start() + 200]}]


# Párrafo hecho solo de fragmentos de 1 a 3 mayúsculas ('D IA', 'IO O F', 'L'):
# letras sueltas de una marca de agua girada ('DIARIO OFICIAL') que el PDF
# intercala con el texto.
_MARCA_DE_AGUA = re.compile(r"^(?:[A-ZÁÉÍÓÚÑ]{1,3}\s+)*[A-ZÁÉÍÓÚÑ]{1,3}$")


def marca_de_agua(md: str) -> list[dict]:
    for b in md.split("\n\n"):
        b = b.strip()
        if b and not b.startswith("#") and _MARCA_DE_AGUA.match(b) \
                and not re.fullmatch(r"[IVXLCDM]+\.?", b):
            return [{"tipo": "marca_de_agua", "fragmento": b}]
    return []


# ------------------------------------------------------------------ contexto

def _coincidencias(bloque: str, normas: list[str]) -> list[int]:
    nb = _norm(bloque)
    return [i for i, n in enumerate(normas) if nb[:50] in n] if len(nb) >= 20 else []


def paginas_de(bloques: list[str], unidad: list[str], normas: list[str]) -> list[int]:
    """Páginas donde arrancan (y si hace falta, continúan) los bloques, ancladas
    al inicio de la unidad: un mismo párrafo puede repetirse en otras."""
    unicas = [c[0] for b in unidad if len(c := _coincidencias(b, normas)) == 1]
    ancla = min(unicas, default=0)
    idx: list[int] = []
    for b in bloques:
        cands = _coincidencias(b, normas)
        if not cands:
            continue
        p = min((c for c in cands if c >= ancla), default=cands[0])
        idx.append(p)
        if _norm(b)[-40:] not in normas[p] and p + 1 < len(normas):
            idx.append(p + 1)
    return sorted(set(idx))[:MAX_PAGINAS_CONTEXTO]


# ------------------------------------------------------------------ LLM

PROMPT = """Eres verificador de un sistema que versiona la legislación fiscal mexicana \
en git. Un extractor automático convirtió el PDF oficial a texto y, respecto de la \
versión anterior, cambió la unidad {ref} de: {nombre}.

Tu única tarea: decidir si los BLOQUES AÑADIDOS reproducen fielmente lo que dice el \
PDF. No evalúes si el cambio es una reforma de fondo, editorial o de puntuación: si el \
PDF lo dice así, es fiel. La ausencia de una nota de reforma no es señal de nada.

Reglas:
- Todo bloque añadido es copia literal del PDF una vez descartadas las líneas que el \
extractor reconoce como encabezado o pie. Los encabezados y pies que veas en el texto \
crudo son normales: solo son un problema si aparecen DENTRO de los bloques añadidos.
- Solo se listan los bloques que cambiaron. Los párrafos de la unidad que no cambiaron \
NO aparecen entre los añadidos; consulta el texto completo de la unidad antes de decir \
que falta algo.
- Las páginas del PDF cubren solo la zona de los bloques cambiados.
- Diferencias de saltos de línea o de dónde se parte un párrafo no son artefacto si \
las palabras son las mismas y están en el mismo orden. Erratas del propio PDF tampoco. \
Las tablas pueden verse aplanadas en ambos lados.

Es "artefacto" si dentro de un bloque añadido hay numeración de página o encabezados \
colados, texto de otra unidad, palabras fuera de orden o duplicadas, o si el PDF \
tiene, en la zona de un bloque añadido, texto legal que no está en la unidad completa.

BLOQUES ELIMINADOS (versión anterior):
{eliminados}

BLOQUES AÑADIDOS (extracción nueva):
{anadidos}

TEXTO COMPLETO DE LA UNIDAD (extracción nueva):
{unidad}

TEXTO CRUDO DEL PDF:
{paginas}

Responde SOLO un objeto JSON:
{{
  "veredicto": "fiel" | "artefacto" | "incierto",
  "explicacion": "una o dos frases, en español",
  "problemas": [{{"tipo": "ruido_pagina" | "texto_faltante" | "duplicado" | "orden" | "otro", "fragmento": "cita literal breve"}}]
}}
"problemas" va vacío si el veredicto es "fiel". "incierto" = no puedes decidir con lo dado."""


def openai_call(modelo: str) -> Callable[[str], str]:
    from openai import OpenAI
    client = OpenAI()

    def call(prompt: str) -> str:
        resp = client.chat.completions.create(
            model=modelo,
            max_completion_tokens=8000,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content or ""

    return call


def _recorta(bloques: list[str]) -> str:
    if not bloques:
        return "(ninguno)"
    return "\n\n".join(b if len(b) <= MAX_BLOQUE_CHARS else b[:MAX_BLOQUE_CHARS] + " […]"
                       for b in bloques)


@dataclass
class Veredicto:
    ref: str
    veredicto: str
    explicacion: str = ""
    problemas: list[dict] = field(default_factory=list)


def verificar_cambio(c: Cambio, paginas: list[str], normas: list[str],
                     call: Callable[[str], str]) -> Veredicto:
    eliminados, anadidos = c.bloques()
    unidad = [b for b in (c.despues or c.antes).split("\n\n") if b.strip()]
    idx = paginas_de(anadidos or eliminados, unidad, normas)
    crudo = "\n\n".join(f"=== PÁGINA {i + 1} ===\n{paginas[i]}" for i in idx) \
        or "(no se localizó la unidad en el PDF)"
    completo = (c.despues if len(c.despues) <= MAX_UNIDAD_CHARS
                else "(omitido por extensión; no afirmes que falta texto)")
    prompt = PROMPT.format(ref=c.ref, nombre=POR_CLAVE[c.doc].etiqueta,
                           eliminados=_recorta(eliminados), anadidos=_recorta(anadidos),
                           unidad=completo or "(unidad eliminada)", paginas=crudo)
    try:
        data = json.loads(call(prompt))
    except Exception as e:
        return Veredicto(c.ref, "incierto", f"el verificador falló: {e}")
    v = data.get("veredicto")
    return Veredicto(
        ref=c.ref,
        veredicto=v if v in VEREDICTOS else "incierto",
        explicacion=str(data.get("explicacion", "")),
        problemas=[p for p in data.get("problemas", []) if isinstance(p, dict)],
    )


# ------------------------------------------------------------------ orquestación

@dataclass
class Resultado:
    total: int                       # unidades con texto cambiado
    duros: list[Veredicto]           # fallas de cobertura (deterministas)
    llm: list[Veredicto]             # veredictos del LLM
    sin_pdf: list[str]               # documentos cambiados cuyo PDF no está

    @property
    def ok(self) -> bool:
        return (not self.duros and not self.sin_pdf
                and all(v.veredicto == "fiel" for v in self.llm))


def _muestra(items: list, n: int) -> list:
    """Hasta `n` elementos repartidos de forma pareja (cubre todos los documentos)."""
    if len(items) <= n:
        return items
    paso = len(items) / n
    return [items[int(i * paso)] for i in range(n)]


def verificar(out: str | Path, pdf_por_clave: dict[str, str],
              call: Callable[[str], str] | None, *,
              call_fuerte: Callable[[str], str] | None = None) -> Resultado:
    todos = cambios(out)
    por_doc: dict[str, list[Cambio]] = {}
    for c in todos:
        por_doc.setdefault(c.doc, []).append(c)
    sin_pdf = sorted(d for d in por_doc if d not in pdf_por_clave)

    duros: list[Veredicto] = []
    contexto: dict[str, tuple[list[str], list[str]]] = {}
    for clave, cs in por_doc.items():
        if clave in sin_pdf:
            continue
        pdf = pdf_por_clave[clave]
        flujo = Flujo.de(texto_limpio(POR_CLAVE[clave], pdf))
        articulado_doc = POR_CLAVE[clave].parser == "articulado"
        for c in cs:
            if c.despues and (pr := cobertura(c.despues, flujo) + (
                    encabezado_pegado(c.despues) + fuera_del_articulado(c.despues)
                    + marca_de_agua(c.despues)
                    if articulado_doc else [])):
                duros.append(Veredicto(c.ref, "artefacto",
                                       "El texto extraído no coincide con el PDF.", pr))
        paginas = paginas_crudas(pdf)
        contexto[clave] = (paginas, [_norm(p) for p in paginas])

    llm: list[Veredicto] = []
    if call:
        con_fallas = {v.ref for v in duros}
        candidatos = [c for c in todos if c.doc in contexto and c.ref not in con_fallas]

        def evaluar(c: Cambio) -> Veredicto:
            paginas, normas = contexto[c.doc]
            v = verificar_cambio(c, paginas, normas, call)
            if v.veredicto != "fiel" and call_fuerte:
                v = verificar_cambio(c, paginas, normas, call_fuerte)
            return v

        with ThreadPoolExecutor(max_workers=6) as pool:
            llm = list(pool.map(evaluar, _muestra(candidatos, MAX_LLM)))
    return Resultado(len(todos), duros, llm, sin_pdf)


def auditar(out: str | Path, pdf_por_clave: dict[str, str]) -> dict:
    """Cobertura determinista de TODAS las unidades de los documentos con PDF.
    Sirve de línea base: un cambio al extractor no puede sumar unidades."""
    total, malos = 0, {}
    for clave, pdf in sorted(pdf_por_clave.items()):
        if clave not in POR_CLAVE:
            continue
        flujo = Flujo.de(texto_limpio(POR_CLAVE[clave], pdf))
        articulado_doc = POR_CLAVE[clave].parser == "articulado"
        for md in sorted((Path(out) / clave).glob("*.md")):
            total += 1
            texto = md.read_text(encoding="utf-8")
            if pr := cobertura(texto, flujo) + (
                    encabezado_pegado(texto) + fuera_del_articulado(texto)
                    + marca_de_agua(texto)
                    if articulado_doc else []):
                malos[f"{clave}/{md.stem}"] = pr
        if articulado_doc:
            for ref, pr in texto_entre_unidades(Path(out), clave, flujo).items():
                malos.setdefault(f"{clave}/{ref}", []).extend(pr)
    return {"total": total, "con_problemas": malos}


# Lo que puede quedar entre dos artículos es estructura: encabezados, sus nombres
# y notas. Una fracción, un inciso o un importe ahí es texto de un artículo que
# no se extrajo, y `cobertura`, que mira dentro de cada unidad, no lo ve.
_TEXTO_DE_ARTICULO = re.compile(
    r"^[ \t]*(?:[IVXL]{1,6}\s*\.-|[IVXL]{1,6}\.\s+[A-ZÁÉÍÓÚ]|[a-zñ]\)\s*\.?-?\s+[A-ZÁÉÍÓÚa-z])"
    r"|\$\s?\d", re.MULTILINE)


def texto_entre_unidades(out: Path, clave: str, flujo: Flujo) -> dict[str, list[dict]]:
    """Texto de artículo entre una unidad y la siguiente, en orden del documento."""
    idx = out / "metadata" / clave / "articulos.json"
    if not idx.exists():
        return {}
    orden = [a["clave"] for a in json.loads(idx.read_text(encoding="utf-8")).get("articulos", [])]
    problemas: dict[str, list[dict]] = {}
    fin_prev, prev = 0, None
    for unidad in orden:
        ruta = out / clave / f"{unidad}.md"
        if not ruta.exists():
            continue
        bloques = [n for b in ruta.read_text(encoding="utf-8").split("\n\n")
                   if b.strip() and not b.startswith("# ") and (n := _norm(b))]
        if not bloques:
            continue
        ini = flujo.norma.find(bloques[0], fin_prev)
        if ini == -1:
            prev = None
            continue
        if prev is not None and ini > fin_prev:
            # Con sus saltos de línea: la fracción va al inicio de renglón
            # ('Capítulo IX. En consecuencia' dentro de una nota no lo es).
            hueco = flujo.texto[flujo.idx[fin_prev]:flujo.idx[ini - 1] + 1]
            if _TEXTO_DE_ARTICULO.search(hueco):
                problemas[prev] = [{"tipo": "texto_entre_unidades",
                                    "fragmento": " ".join(hueco.split())[:300]}]
        fin = ini
        for b in bloques:
            p = flujo.norma.find(b, fin)
            if p != -1:
                fin = p + len(b)
        fin_prev, prev = fin, unidad
    return problemas


ICONO = {"fiel": "✅", "artefacto": "❌", "incierto": "❔"}


def reporte_md(r: Resultado) -> str:
    lineas = ["### 🔬 Verificación de la extracción contra los PDF", ""]
    if not r.total:
        lineas.append("Ninguna unidad de texto cambió.")
        return "\n".join(lineas) + "\n"
    if r.ok:
        lineas.append("Todos los cambios reproducen fielmente los PDF oficiales.")
    else:
        lineas.append("**Hay cambios que no coinciden con el PDF — no mergear sin revisar.**")
    lineas += ["", f"- Unidades cambiadas: **{r.total}**",
               f"- Cobertura determinista (literalidad y texto omitido): "
               f"**{r.total - len(r.duros)} de {r.total}** en verde",
               f"- Revisión con LLM: **{sum(v.veredicto == 'fiel' for v in r.llm)} de "
               f"{len(r.llm)}** fieles" + (" (muestra)" if len(r.llm) < r.total - len(r.duros) else "")]
    if r.sin_pdf:
        lineas.append(f"- Sin PDF para verificar: {', '.join(r.sin_pdf)}")
    malos = r.duros + [v for v in r.llm if v.veredicto != "fiel"]
    if malos:
        lineas.append("")
    for v in malos[:40]:
        lineas.append(f"- {ICONO[v.veredicto]} **{v.ref}** — {v.veredicto}: {v.explicacion}")
        for p in v.problemas[:4]:
            lineas.append(f"  - `{p.get('tipo', 'otro')}`: «{str(p.get('fragmento', ''))[:160]}»")
    if len(malos) > 40:
        lineas.append(f"- … y {len(malos) - 40} más")
    return "\n".join(lineas) + "\n"


def modelo_configurado() -> str:
    return os.environ.get("VERIFICADOR_MODELO") or MODELO_DEFAULT


def modelo_fuerte_configurado() -> str:
    return os.environ.get("VERIFICADOR_MODELO_FUERTE") or MODELO_FUERTE_DEFAULT
