"""Chequeos de forma: defectos de extracción que se ven en el texto solo.

La auditoría (`verificar.py`) compara cada párrafo con el PDF ya filtrado por
el extractor, así que no ve lo que el extractor no supo quitar o separar: un
pie de página dentro de un párrafo, el rótulo de un artículo absorbido por su
vecino, una nota de reforma pegada al texto. Eso lo encuentra la revisión
completa de un alta (`scripts/revision.py`), que se paga en tokens. Varios de
esos defectos tienen una forma reconocible sin mirar el PDF; este módulo los
busca en el texto publicado.

No es una compuerta de lo publicado y no forma parte de `auditar`: medido
sobre el corpus, varios chequeos señalan leyes ya publicadas, y volverlas a
juzgar de golpe no es el propósito. Tiene dos usos:

- `FILTRO`, los chequeos sin falsos positivos conocidos en lo publicado: se
  corren antes de la revisión completa de un alta de ley estatal
  (`scripts/forma_alta.py`). Lo que encuentran deja la ley fuera como lo
  haría esa revisión, sin gastar la sesión del agente. Si no encuentran nada,
  la revisión corre igual: el filtro ahorra revisiones, no las sustituye.
- `python -m extractor forma --out <repo de datos>`: el informe de todos los
  chequeos, para una persona. Ningún workflow lo llama.

Cada chequeo recibe una `Ley` y devuelve `Hallazgo`s con la forma de los de la
revisión (`clave`, `nota`), y la nota cita el texto que lo delata.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .disposicion import dir_metadata, dir_unidades


# ------------------------------------------------------------------ modelo

@dataclass(frozen=True)
class Articulo:
    clave: str
    parrafos: tuple[str, ...]          # sin el encabezado '# Artículo…'
    meta: dict = field(default_factory=dict)

    @property
    def cuerpo(self) -> tuple[str, ...]:
        """Los párrafos que no son nota (las notas van en cursiva)."""
        return tuple(p for p in self.parrafos if not es_nota(p))

    @property
    def numero(self) -> int | None:
        n = self.meta.get("articulo")
        if isinstance(n, int):
            return n
        m = re.match(r"\d+", self.clave)
        return int(m.group()) if m else None


@dataclass(frozen=True)
class Ley:
    clave: str
    articulos: tuple[Articulo, ...]
    etiqueta: str = ""
    # Lo que su definición dice que el extractor hace con las notas de reforma
    # (`notas`, `notas_en_linea` de `Documento`): marcarlas en cursiva y pasar a
    # su propio párrafo las que el PDF escribe a renglón seguido. Sin eso, una
    # nota dentro de un párrafo es texto fiel al PDF, no un defecto.
    marca_notas: bool = False
    separa_notas: bool = False


@dataclass(frozen=True)
class Hallazgo:
    chequeo: str
    clave: str
    nota: str

    def a_dict(self) -> dict:
        return {"clave": self.clave, "nota": self.nota, "chequeo": self.chequeo}


def es_nota(parrafo: str) -> bool:
    return len(parrafo) > 2 and parrafo.startswith("_") and parrafo.endswith("_")


def parrafos(texto: str) -> tuple[str, ...]:
    """Los párrafos del .md de un artículo, sin su encabezado."""
    return tuple(b.strip() for b in texto.split("\n\n")
                 if b.strip() and not b.startswith("# "))


def cargar(repo: str | Path, clave: str, definicion=None) -> Ley:
    """La ley `clave` tal como está en el repo de datos, en el orden de su
    índice (`articulos.json`). `definicion`: su `Documento`, si se conoce."""
    unidades = dir_unidades(repo, clave)
    indice = dir_metadata(repo, clave) / "articulos.json"
    idx = json.loads(indice.read_text(encoding="utf-8")) if indice.exists() else {}
    metas = {a["clave"]: a for a in idx.get("articulos", [])
             if isinstance(a, dict) and a.get("clave")}
    archivos = {p.stem: p for p in unidades.glob("*.md")}
    orden = [c for c in metas if c in archivos] + sorted(set(archivos) - set(metas))
    arts = tuple(Articulo(c, parrafos(archivos[c].read_text(encoding="utf-8")), metas.get(c, {}))
                 for c in orden)
    return Ley(clave, arts, idx.get("etiqueta", ""),
               marca_notas=bool(getattr(definicion, "notas", None)),
               separa_notas=bool(getattr(definicion, "notas_en_linea", None)))


# ------------------------------------------------------------------ patrones

_VERBO = r"(?:REFORMAD|ADICIONAD|DEROGAD|RECORRID|REUBICAD|REFORMDA|ADICIOND)"
_MEDIO = r"(?:P\.\s?O\.|G\.\s?O\.|D\.\s?O\.\s?F\.|DOF\b|GODF|Peri[óo]dico Oficial)"
# Una nota de reforma compacta, como las escriben los congresos estatales:
# '(REFORMADO, P.O. 4 DE MARZO DE 2022)', '(Adición, P.O. No. 19, 27-II-26)',
# '(F. DE E., P.O. 29 DE ENERO DE 2016)'. La prosa entre paréntesis ('(Esta
# porción normativa fue reformada por Decreto…)') no cuenta: Jalisco la
# escribe a renglón seguido y ahí es texto fiel.
_NOTA = (rf"(?:(?:P[ÁA]RRAFO|FRACCI[ÓO]N|INCISO|ART[ÍI]CULO|NUMERAL|CAP[ÍI]TULO|T[ÍI]TULO|SECCI[ÓO]N)\s+)?"
         rf"{_VERBO}[OA]S?\b"
         rf"[^()\n]{{0,140}}?{_MEDIO}[^()\n]{{0,80}}"
         rf"|(?:Ref|Re|Adici[óo]n|Fe de erratas)\b[^()\n]{{0,80}}P\.\s?O\.[^()\n]{{0,60}}"
         rf"|(?:F\.\s?DE\s?E\.|N\.\s?DE\s?E\.)[^()\n]{{0,160}}")
NOTA_ENTRE_PARENTESIS = re.compile(rf"\(\s*(?:{_NOTA})\)", re.IGNORECASE)
# La misma nota como párrafo entero; el PDF a veces omite uno de los paréntesis.
NOTA_SOLA = re.compile(rf"\(?\s*(?:{_NOTA})\)?\.?", re.IGNORECASE)
# Una nota que anota un encabezado (un capítulo adicionado, una denominación
# reformada): nunca es de un artículo.
NOTA_DE_ENCABEZADO = re.compile(
    rf"\b(?:CAP[ÍI]TULO|T[ÍI]TULO|SECCI[ÓO]N|LIBRO|DENOMINACI[ÓO]N)\b[^()\n.]{{0,70}}?{_VERBO}[OA]S?\b"
    rf"|{_VERBO}[OA]S?\s+(?:CON\s+(?:EL|LOS|LA|LAS)\s+(?:ART[ÍI]CULOS?|CAP[ÍI]TULOS?|SECCI[ÓO]N|SECCIONES|T[ÍI]TULOS?)"
    rf"|SU\s+DENOMINACI[ÓO]N)", re.IGNORECASE)
_NOTA_DE_ARTICULO = re.compile(rf"_?\(?\s*{_VERBO}[OA]S?\s*,", re.IGNORECASE)
# '(REFORMADO PRIMER PÁRRAFO, P.O. …)': el verbo primero, como las escriben las
# fuentes que anotan antes. 'Párrafo reformado G.O. CDMX…' va después.
_NOTA_VERBO_PRIMERO = re.compile(rf"\(?\s*{_VERBO}[OA]S?\b", re.IGNORECASE)

FRACCION = re.compile(r"(?:[IVXLCDM]+|[a-zñ]{1,3}|[A-Z]|\d{1,3})\s*[.)\-]")
FIN_DE_ORACION = re.compile(r"[.;:)…”\"»!?\]]$|[.;:,]\s*[yoeu]$|\.[”\"»]?\s*_?$")

_SUFIJO = (r"(?:BIS|TER|QU[ÁA]TER|QUINTUS|QUINQUIES|SEXIES|SEPTIES|OCTIES|NONIES|NOVIES"
           r"|[A-Z]*DECIES|[A-Z]|\d{1,2})")
_ROTULO = (rf"(?:ART[ÍI]CULO|Art[íi]culo|ART\.|Art\.)\s*(?P<n>\d+)[°ºo]?\.?\s*(?:\(SIC\)\s*)?"
           rf"(?P<suf>(?:[\s\-]{{0,2}}(?i:{_SUFIJO})\b){{0,3}})\s*\.?\s*[\-–—.]")
ROTULO_AL_INICIO = re.compile(_ROTULO)
ROTULO_EN_LINEA = re.compile(rf"[.;:]\s+{_ROTULO}\s?[\-–—]\s")
# 'Artículo Niñas, niños…': un rótulo cuyo número se perdió. Los ordinales son
# de un artículo transitorio o de un decreto citado.
_ROTULO_SIN_NUMERO = re.compile(
    r"(?:ART[ÍI]CULO|Art[íi]culo)\s+(?!(?:[ÚU]nico|Primero|Segundo|Tercero|Cuarto|Quinto|Sexto"
    r"|S[ée]ptimo|Octavo|Noveno|D[ée]cimo|Transitorio)\b)[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+", re.IGNORECASE)

PIE = re.compile(
    r"\bP[áa]g(?:ina|\.)?\s*\d+(?:\s*,\s*\d+)*\s+de\s+\d+\b"
    r"|Decreto\s+N[úu]m\.?\s*\d+\s+expedido\s+por"
    r"|\b[LXVI]{3,}\s+Legislatura\s+\d{1,3}(?:\s*,\s*\d{1,3})*(?:\s|$)"
    r"|Secretar[íi]a\s+General\s+Publicada"
    r"|H\.\s+CONGRESO\s+DEL\s+ESTADO\s+DE\s+[A-ZÁÉÍÓÚÑ ]+\s+(?:Expidi|Secretar)"
    r"|[ÚU]ltima\s+[Rr]eforma\s+(?:DOF|P\.\s?O\.|publicada)[^.\n]{0,40}\d{4}\s+\d+\s+de\s+\d+",
    re.IGNORECASE)


def _sin_acentos(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t)
                   if unicodedata.category(c) != "Mn")


def _cita(texto: str, inicio: int = 0, fin: int | None = None, margen: int = 40) -> str:
    """El fragmento `texto[inicio:fin]` con algo de contexto, para la nota."""
    fin = len(texto) if fin is None else fin
    a, z = max(0, inicio - margen), min(len(texto), fin + margen)
    return ("…" if a else "") + texto[a:z].replace("\n", " ") + ("…" if z < len(texto) else "")


# ------------------------------------------------------------------ chequeos

def pie_pagina(ley: Ley) -> list[Hallazgo]:
    """Pie o membrete de página dentro del texto: una forma conocida («Página
    N de M», «Decreto Núm. N expedido por…», «LXXIII Legislatura N») o el
    título de la propia ley en mayúsculas seguido del folio."""
    titulo = None
    if len(ley.etiqueta) > 15:
        titulo = re.compile(r"\s+".join(map(re.escape, _sin_acentos(ley.etiqueta).upper().split()))
                            + r"\s+\d{1,3}(?:\s|$)")
    res = []
    for a in ley.articulos:
        for p in a.parrafos:
            m = PIE.search(p) or (titulo.search(_sin_acentos(p)) if titulo else None)
            if m:
                cita = _cita(p, m.start(), m.end())
                res.append(Hallazgo("pie_pagina", a.clave,
                                    f"pie de página colado en el texto: «{cita}»"))
    return res


def _clave_de_rotulo(m: re.Match) -> str:
    """'161 BIS 2' → '161-bis-2': la clave de archivo que tendría ese artículo."""
    sufijos = re.findall(r"[^\W_]+", _sin_acentos(m.group("suf")).lower())
    return "-".join([f"{int(m.group('n')):03d}", *sufijos])


def rotulo_interno(ley: Ley) -> list[Hallazgo]:
    """Rótulo «Artículo N.-» dentro del cuerpo de otro artículo, cuando ese N
    no tiene archivo propio (o es el del mismo artículo, repetido): un artículo
    absorbido por el anterior. Un rótulo cuyo artículo sí existe en la ley es
    la cita literal de un artículo (de esta ley o de otra) y no se señala."""
    claves = {a.clave for a in ley.articulos}
    res = []
    for a in ley.articulos:
        for i, p in enumerate(a.parrafos):
            if es_nota(p):
                continue
            m = (ROTULO_AL_INICIO.match(p) if i else None) or ROTULO_EN_LINEA.search(p)
            if not m:
                continue
            absorbido = _clave_de_rotulo(m)
            if absorbido == a.clave or absorbido not in claves:
                cita = _cita(p, m.start(), m.end(), 30)
                res.append(Hallazgo(
                    "rotulo_interno", a.clave,
                    f"el artículo absorbió a otro: su cuerpo contiene el rótulo «{cita}»"
                    + ("" if absorbido in claves else f" y no existe archivo {absorbido}")))
    return res


def salto_numeracion(ley: Ley) -> list[Hallazgo]:
    """Salto en la numeración con un rótulo sin número en el artículo anterior
    («Artículo Niñas, niños…»): el artículo que falta quedó dentro de él. Un
    salto sin ese indicio no se señala: los PDF estatales omiten artículos
    derogados (`huecos`) y alguno numera mal y lo dice («(SIC)»)."""
    res = []
    con_numero = [a for a in ley.articulos if a.numero is not None]
    for anterior, a in zip(con_numero, con_numero[1:]):
        if a.numero <= anterior.numero + 1:
            continue
        for p in anterior.parrafos[1:]:
            if not es_nota(p) and (m := _ROTULO_SIN_NUMERO.match(p)):
                res.append(Hallazgo(
                    "salto_numeracion", anterior.clave,
                    f"falta el archivo de un artículo: del {anterior.clave} se pasa al {a.clave} y "
                    f"dentro del {anterior.clave} quedó un rótulo sin número: «{_cita(p, 0, m.end())}»"))
                break
    return res


def nota_de_encabezado(ley: Ley) -> list[Hallazgo]:
    """Nota que anota un encabezado («CAPÍTULO ADICIONADO…», «ADICIONADO CON
    LOS ARTÍCULOS QUE LO INTEGRAN…») dentro de un artículo: es de la
    estructura que sigue, no del artículo."""
    res = []
    for a in ley.articulos:
        for p in a.parrafos:
            t = p.strip("_")
            if len(t) <= 300 and NOTA_DE_ENCABEZADO.search(t) \
                    and (es_nota(p) or NOTA_SOLA.fullmatch(t)):
                res.append(Hallazgo("nota_de_encabezado", a.clave,
                                    f"la nota «{t[:200]}» anota un encabezado de la estructura, "
                                    f"no al artículo, y está entre sus párrafos"))
    return res


def nota_previa_al_final(ley: Ley) -> list[Hallazgo]:
    """En una fuente que pone la nota ANTES de lo que anota, una nota de
    reforma o adición como último párrafo anota lo que sigue (el artículo o el
    encabezado siguiente), no a este artículo. La convención se infiere del
    propio texto (casi todas las notas de artículo entero lo abren), no de
    `notas_previas`: la CDMX las declara y aun así escribe después sus
    «Artículo reformado G.O. CDMX…», que por eso no cuentan (solo las que
    empiezan por el verbo). Las de derogación tampoco: «(DEROGADO ÚLTIMO
    PÁRRAFO…)» ocupa el lugar del párrafo que ya no está."""
    abren, candidatas = 0, []
    for a in ley.articulos:
        if len(a.parrafos) < 2:
            continue
        abren += bool(_NOTA_DE_ARTICULO.match(a.parrafos[0]))
        t = a.parrafos[-1].strip("_")
        if NOTA_SOLA.fullmatch(t) and _NOTA_VERBO_PRIMERO.match(t) \
                and not re.search(r"DEROGAD", t, re.IGNORECASE):
            candidatas.append(Hallazgo(
                "nota_previa_al_final", a.clave,
                f"la nota «{t[:200]}» quedó como último párrafo; esta fuente pone las notas "
                f"antes de lo que anotan, así que es de lo que sigue"))
    return candidatas if abren >= 8 and abren >= 4 * len(candidatas) else []


def nota_en_cuerpo(ley: Ley) -> list[Hallazgo]:
    """Nota de reforma dentro de un párrafo que no es nota, en una ley cuya
    definición las aparta: sola pero sin marcar (si `marca_notas`), o pegada
    al texto que anota (si `separa_notas`)."""
    res = []
    for a in ley.articulos:
        for p in a.cuerpo:
            if NOTA_SOLA.fullmatch(p):
                # 'DEROGADO, P.O. …' solo es el cuerpo de un artículo derogado.
                if ley.marca_notas and not re.search(r"DEROGAD", p, re.IGNORECASE):
                    res.append(Hallazgo("nota_en_cuerpo", a.clave,
                                        f"la nota de reforma «{p[:200]}» quedó como texto del "
                                        f"artículo, sin marcar como nota"))
                continue
            m = NOTA_ENTRE_PARENTESIS.search(p) if ley.separa_notas else None
            if not m:
                continue
            antes, despues = p[:m.start()].strip(), p[m.end():].strip(" .;")
            # 'XVIII. (DEROGADA, P.O. …)' es el cuerpo de una fracción derogada.
            if re.search(r"DEROGAD", m.group(), re.IGNORECASE) and not despues and (
                    not antes or FRACCION.fullmatch(antes) or len(antes) < 25):
                continue
            res.append(Hallazgo("nota_en_cuerpo", a.clave,
                                f"la nota de reforma «{m.group()[:200]}» quedó pegada al texto del "
                                f"párrafo («{_cita(p, m.start(), m.start(), 50)}»), no en su propio párrafo"))
    return res


_NOTA_Y_COLA = re.compile(r"\([^()]*(?:\([^()]*\)[^()]*)*\)\s*(?P<cola>[^\s(].*)", re.S)


def nota_con_texto(ley: Ley) -> list[Hallazgo]:
    """Párrafo marcado como nota que, tras el paréntesis de cierre de la nota,
    sigue con texto: el texto de la ley quedó dentro de la nota."""
    res = []
    for a in ley.articulos:
        for p in a.parrafos:
            t = p.strip("_").strip()
            # '((REFORMADO, …) Para el caso…': un paréntesis de más no esconde la cola.
            m = _NOTA_Y_COLA.fullmatch(re.sub(r"^\(\((?=[^()]*\)[^)])", "(", t)) \
                if es_nota(p) and t.startswith("(") else None
            if m and len(m.group("cola")) > 3 and not NOTA_SOLA.match(m.group("cola")):
                res.append(Hallazgo("nota_con_texto", a.clave,
                                    f"el párrafo marcado como nota lleva texto después de la nota: "
                                    f"«{t[:200]}»"))
    return res


def nota_sin_cerrar(ley: Ley) -> list[Hallazgo]:
    """Nota con los paréntesis sin cerrar: suele estar cortada, pero algún PDF
    la escribe así."""
    res = []
    for a in ley.articulos:
        for p in a.parrafos:
            t = p.strip("_").strip()
            if es_nota(p) and t.startswith("(") and t.count("(") != t.count(")"):
                res.append(Hallazgo("nota_sin_cerrar", a.clave,
                                    f"la nota «{t[:200]}» no cierra sus paréntesis"))
    return res


# Palabras que no pueden cerrar una oración.
_FUNCION = frozenset(
    "de del la el los las en que y o a al por para con sin sobre su sus se un una ante bajo "
    "entre hacia hasta según tras e u ni lo le les cuyo cuya como artículo artículos fracción "
    "fracciones".split())


def corte_a_media_oracion(ley: Ley) -> list[Hallazgo]:
    """Párrafo que acaba en una palabra que no puede cerrar una oración («…lo
    dispuesto en el») o sin puntuación y seguido de otro que empieza en
    minúscula sin ser inciso: un párrafo partido."""
    res = []
    for a in ley.articulos:
        c = a.cuerpo
        for i, p in enumerate(c):
            q = c[i + 1] if i + 1 < len(c) else ""
            if p.startswith("[") or len(p) < 15 or FIN_DE_ORACION.search(p) or p.endswith(","):
                continue
            ultima = re.findall(r"[^\W\d_]+$", p)
            if not ultima:
                continue
            sigue_inciso = bool(q) and bool(FRACCION.match(q))
            abierta = ultima[0] in _FUNCION and not (sigue_inciso and not q[0].isdigit())
            minuscula = bool(q) and q.lstrip("“\"«(")[:1].islower() and not sigue_inciso
            if abierta or minuscula:
                res.append(Hallazgo("corte_a_media_oracion", a.clave,
                                    f"párrafo partido a media oración: «…{p[-60:]}» / "
                                    f"«{q[:60] or '(fin del artículo)'}»"))
    return res


def epigrafe_siguiente_colado(ley: Ley) -> list[Hallazgo]:
    """En una ley cuyos artículos llevan epígrafe (al menos la mitad lo tiene
    en su metadata), un artículo SIN epígrafe precedido por uno cuyo último
    párrafo no cierra con puntuación: su epígrafe se quedó en el anterior."""
    arts = ley.articulos
    if not arts or sum(1 for a in arts if a.meta.get("epigrafe")) < 0.5 * len(arts):
        return []
    res = []
    for a, sig in zip(arts, arts[1:]):
        if not a.cuerpo or sig.meta.get("epigrafe") or sig.meta.get("derogado"):
            continue
        b = a.cuerpo[-1]
        if not FIN_DE_ORACION.search(b) and re.search(r"[^\W\d_]$", b) and not b.startswith("["):
            res.append(Hallazgo("epigrafe_siguiente_colado", a.clave,
                                f"el epígrafe del artículo siguiente ({sig.clave}, que no tiene) "
                                f"quedó al final de este: «…{b[-140:]}»"))
    return res


_EPIGRAFE = re.compile(r"(?:De|Del|Disposiciones|Reglas|Generalidades|Prevenciones|Objeto|Atribuciones"
                       r"|Facultades|Integraci[óo]n|Requisitos|Obligaciones|Definici[óo]n|Naturaleza)\b")
_VERBO_CONJUGADO = re.compile(
    r"\b(?:se|ser[áa]n?|deber[áa]n?|podr[áa]n?|es|son|tendr[áa]n?|est[áa]n?|har[áa]n?|queda|rige"
    r"|aplica\w*|observar[áa]n?|conocer[áa]n?)\b", re.IGNORECASE)


def epigrafe_final_con_punto(ley: Ley) -> list[Hallazgo]:
    """Último párrafo corto con forma de rótulo aunque lleve punto final («De
    la participación social.»), o todo en mayúsculas en una ley que no lo
    está: el encabezado de lo que sigue, colado al final del artículo."""
    en_mayusculas = sum(1 for a in ley.articulos for p in a.cuerpo[:1] if p.isupper())
    ley_en_mayusculas = en_mayusculas > len(ley.articulos) * 0.3
    res = []
    for a in ley.articulos:
        c = a.cuerpo
        if len(c) < 2:
            continue
        b = c[-1]
        if len(b) > 110 or FRACCION.match(b) or re.search(r"\d", b) or "," in b \
                or re.search(r"derog", b, re.IGNORECASE):
            continue
        sin_punto = b.rstrip(".")
        rotulo = _EPIGRAFE.match(b) and len(b.split()) <= 12 and not _VERBO_CONJUGADO.search(sin_punto)
        mayusculas = not ley_en_mayusculas and sin_punto.isupper() and len(sin_punto) > 12
        if rotulo or mayusculas:
            res.append(Hallazgo("epigrafe_final_con_punto", a.clave,
                                f"el último párrafo «{b}» tiene forma de epígrafe o encabezado de "
                                f"lo que sigue, no de texto del artículo"))
    return res


def derogado_pegado(ley: Ley) -> list[Hallazgo]:
    """«Derogado» pegado al final de un párrafo con texto: la anotación de un
    párrafo derogado, que el PDF pone en su propio renglón."""
    res = []
    for a in ley.articulos:
        for p in a.cuerpo:
            m = re.search(r"[.;]\s+\(?(?:Derogad[oa]|Se deroga|DEROGAD[OA]|SE DEROGA)\)?\.?$", p)
            if m and m.start() > 60:
                res.append(Hallazgo("derogado_pegado", a.clave,
                                    f"«{p[m.start() + 1:].strip()}» quedó pegado al final del párrafo "
                                    f"«…{p[max(0, m.start() - 60):m.start() + 1]}»"))
    return res


_NUMERAL = re.compile(r"(?:[IVXLCDM]{1,7}|[a-zñ]{1,2}|\d{1,3})\s*[.)]\s*[.\-]?")
_SUELTO = re.compile(r"[IVXLCDM]{1,7}|[a-zñ]{1,2}|\d{1,3}|[;,.:()\-–]+")


def fraccion_huerfana(ley: Ley) -> list[Hallazgo]:
    """Párrafo que es solo un numeral, una letra de inciso, una conjunción o un
    signo: su texto quedó en otro párrafo. Un numeral seguido de una nota no
    cuenta: es una fracción derogada («IV. (DEROGADA, P.O. …)») cuyo único
    texto es la nota, que va en su propio párrafo."""
    res = []
    for a in ley.articulos:
        for i, p in enumerate(a.parrafos):
            if es_nota(p):
                continue
            sigue_nota = i + 1 < len(a.parrafos) and es_nota(a.parrafos[i + 1])
            if _SUELTO.fullmatch(p) or (_NUMERAL.fullmatch(p) and not sigue_nota):
                res.append(Hallazgo("fraccion_huerfana", a.clave,
                                    f"párrafo suelto «{p}», sin el texto de su fracción"))
    return res


Chequeo = Callable[[Ley], list[Hallazgo]]

CHEQUEOS: dict[str, Chequeo] = {f.__name__: f for f in (
    pie_pagina, rotulo_interno, salto_numeracion, nota_de_encabezado, nota_previa_al_final,
    nota_en_cuerpo, nota_con_texto, nota_sin_cerrar, corte_a_media_oracion,
    epigrafe_siguiente_colado, epigrafe_final_con_punto, derogado_pegado, fraccion_huerfana)}

# Los que filtran un alta antes de su revisión completa. Entra un chequeo solo
# sin falsos positivos conocidos en lo publicado (la medición está en
# AGENTS.md, «Filtro de forma»): uno que marca texto fiel dejaría fuera una
# ley sin defecto. Los demás quedan para el informe.
FILTRO: tuple[str, ...] = (
    "pie_pagina", "rotulo_interno", "nota_de_encabezado", "nota_previa_al_final",
    "nota_en_cuerpo", "nota_con_texto", "corte_a_media_oracion", "epigrafe_siguiente_colado",
    "epigrafe_final_con_punto", "derogado_pegado", "fraccion_huerfana")


def revisar(ley: Ley, chequeos: tuple[str, ...] | None = None) -> list[Hallazgo]:
    """Hallazgos de `chequeos` (todos, si no se dicen) en el orden de la ley."""
    orden = {a.clave: i for i, a in enumerate(ley.articulos)}
    nombres = CHEQUEOS if chequeos is None else chequeos
    res = [h for n in nombres for h in CHEQUEOS[n](ley)]
    return sorted(res, key=lambda h: (orden.get(h.clave, len(orden)), list(CHEQUEOS).index(h.chequeo)))


# ------------------------------------------------------------------ informe

def documentos_de_repo(repo: str | Path) -> list[str]:
    """Las leyes que este extractor produce en `repo`: las de un repo plano
    (`metadata/<doc>/`) y las estatales, sin las constituciones."""
    repo = Path(repo)
    planos = [p.parent.name for p in repo.glob("metadata/*/articulos.json")]
    estatales = [f"{p.parts[-4]}/{p.parts[-3]}" for p in repo.glob("*/*/metadata/articulos.json")
                 if p.parts[-3] != "constitucion"]
    return sorted(planos + estatales)


def definiciones() -> dict:
    """El `Documento` de cada ley estatal declarada (las de FUERA incluidas)."""
    from .estatales import documentos, fuera
    return {**{c: d for c, (d, _) in fuera().items()}, **{d.clave: d for d in documentos()}}


def informe(repo: str | Path, claves: list[str] | None = None,
            chequeos: tuple[str, ...] | None = None) -> dict[str, list[Hallazgo]]:
    """Hallazgos por ley (solo las que tienen alguno)."""
    defs = definiciones()
    res = {}
    for clave in claves or documentos_de_repo(repo):
        hs = revisar(cargar(repo, clave, defs.get(clave)), chequeos)
        if hs:
            res[clave] = hs
    return res
