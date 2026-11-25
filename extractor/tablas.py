"""Tablas con bordes, leídas por celdas.

`extract_text` arma renglones por altura. En una fila cuya descripción ocupa
varios renglones, el número y el porcentaje van centrados a su lado y caen en
un renglón u otro según dónde corte la página (el artículo 513 de la Ley
Federal del Trabajo cambiaba de un PDF al siguiente sin reforma); y un rótulo
de columna girado sale letra por letra entre las cifras (las cuotas del 223-Bis
de la Ley Federal de Derechos). Las celdas no tienen ese problema: el PDF las
dibuja, y cada una se lee entera.

Solo se releen las tablas que lo necesitan (una celda de varios renglones junto
a otra, texto girado o una fila que sigue de la página anterior); las demás
quedan como las da `extract_text`. Cada fila sale en un renglón, sus celdas de
izquierda a derecha.
"""
from __future__ import annotations

import re
from collections import Counter

# Cambiar la lectura invalida el texto por página que `verificar` guarda junto
# al PDF.
VERSION = 2
MIN_BORDES = 4
MIN_SOBREIMPRESO = 4
MIN_ANCHO_CELDA = 6
# Dos textos impresos uno sobre el otro salen con las letras intercaladas
# ('isponZoinab dei dlispiondibilaidadd'): una mayúscula a media palabra los
# delata, y la geometría lo confirma.
_MAYUSCULA_A_MEDIA_PALABRA_RE = re.compile(r"[a-záéíóúñ]{2}[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2}")


def _girado(c: dict) -> bool:
    m = c.get("matrix")
    return bool(m) and abs(m[0]) < 0.01 and abs(m[1]) > 0.01


def _palabras(lineas: list[dict]) -> list[tuple[int, float, float, str]] | None:
    """Cada palabra de la página con el renglón en que `extract_text` la puso
    y su centro. Las celdas se arman con estos renglones, no volviendo a
    agrupar sus letras: dos renglones apretados de una celda se intercalarían."""
    palabras = []
    for n, ln in enumerate(lineas):
        chars = iter(ln["chars"])
        for palabra in ln["text"].split():
            propias = [c for c in (next(chars, None) for _ in palabra) if c]
            if "".join(c["text"] for c in propias) != palabra:
                return None
            palabras.append((n, (propias[0]["x0"] + propias[-1]["x1"]) / 2,
                             sum(c["top"] + c["bottom"] for c in propias) / (2 * len(propias)), palabra))
    return palabras


class _Mezclada(Exception):
    """Una celda con texto girado y derecho a la vez: no se sabe en qué orden
    se lee, y su tabla queda como la da `extract_text`."""


def _texto_celda(pagina, palabras, caja, recortar: bool) -> tuple[str, int, bool]:
    """Texto de la celda, sus renglones y si trae texto girado. El girado se
    lee por columnas, de abajo hacia arriba. En una tabla con texto girado los
    renglones de la página salen desarmados, y con `recortar` cada celda se
    lee sola."""
    x0, top, x1, bottom = caja
    chars = [c for c in pagina.chars if not c["text"].isspace()
             and x0 <= (c["x0"] + c["x1"]) / 2 < x1 and top <= (c["top"] + c["bottom"]) / 2 < bottom]
    if not chars:
        return "", 0, False
    girados = [c for c in chars if _girado(c)]
    if girados and len(girados) < len(chars):
        raise _Mezclada
    if girados:
        columnas: dict[int, list[dict]] = {}
        for c in pagina.chars:
            if _girado(c) and x0 <= (c["x0"] + c["x1"]) / 2 < x1 and top <= (c["top"] + c["bottom"]) / 2 < bottom:
                columnas.setdefault(round(c["x0"] / 4), []).append(c)
        partes = ["".join(c["text"] for c in sorted(col, key=lambda c: -c["top"])).strip()
                  for _, col in sorted(columnas.items())]
        return " ".join(" ".join(p.split()) for p in partes if p), len(partes), True
    if recortar:
        texto = pagina.crop((x0, top, x1, bottom), strict=False).extract_text() or ""
        renglones = [r.strip() for r in texto.split("\n") if r.strip()]
        return " ".join(renglones), len(renglones), False
    dentro = [(n, s) for n, x, y, s in palabras if x0 <= x < x1 and top <= y < bottom]
    return " ".join(s for _, s in dentro), len({n for n, _ in dentro}), False


def _leer(pagina, lineas: list[dict]) -> list[dict]:
    """Las tablas de la página con al menos dos columnas."""
    palabras = _palabras(lineas)
    if palabras is None:
        return []
    tablas = []
    halladas = pagina.find_tables()
    girados = [c for c in pagina.chars if _girado(c) and not c["text"].isspace()]
    for t in halladas:
        # Una cuadrícula con columnas de un par de puntos o con otra tabla
        # encima no es la de la tabla (renglones sombreados uno por uno): esa
        # se queda como la da `extract_text`.
        if any(o is not t and _se_enciman(o.bbox, t.bbox) for o in halladas) or any(
                c and c[2] - c[0] < MIN_ANCHO_CELDA for fila in t.rows for c in fila.cells):
            tablas.append({"bbox": t.bbox, "filas": [], "necesita": False, "omitida": True, "bordes": []})
            continue
        recortar = any(t.bbox[0] <= c["x0"] <= t.bbox[2] and t.bbox[1] <= c["top"] <= t.bbox[3]
                       for c in girados)
        # Si alguna letra de la tabla no cae en exactamente una celda (falta
        # un borde), leerla por celdas la perdería o la repetiría.
        cajas = [c for fila in t.rows for c in fila.cells if c]
        if any(sum(_en(c, caja) for caja in cajas) != 1 for c in pagina.chars
               if not c["text"].isspace() and _en(c, t.bbox)):
            tablas.append({"bbox": t.bbox, "filas": [], "necesita": False, "omitida": True, "bordes": []})
            continue
        filas, necesita, ambigua = [], False, False
        for fila in t.rows:
            try:
                celdas = [(c[0], *_texto_celda(pagina, palabras, c, recortar)) if c else None
                          for c in fila.cells]
            except _Mezclada:
                ambigua = True
                break
            # Una celda que abarca varias filas (y no es un rótulo girado) no
            # tiene un lugar único en la lectura por filas.
            bajo = min((c[3] for c in fila.cells if c), default=0)
            if any(c and c[3] > bajo + 2 and not celda[3] and celda[1]
                   for c, celda in zip(fila.cells, celdas) if c):
                ambigua = True
            llenas = [c for c in celdas if c and c[1]]
            if len(llenas) >= 2 and any(c[2] > 1 for c in llenas):
                necesita = True
            if any(c[3] for c in llenas):
                necesita = True
            filas.append({"top": fila.bbox[1], "bottom": fila.bbox[3], "celdas": celdas})
        columnas = max((len(f["celdas"]) for f in filas), default=0)
        # Lo leído tiene que ser, letra por letra, lo que hay en la tabla.
        leido = Counter("".join(_renglon(f) for f in filas).replace(" ", ""))
        escrito = Counter("".join(c["text"] for c in pagina.chars
                                  if not c["text"].isspace() and _en(c, t.bbox)))
        omitida = columnas < 2 or ambigua or leido != escrito
        tablas.append({"bbox": t.bbox, "filas": [] if omitida else filas,
                       "necesita": necesita and not omitida, "omitida": omitida,
                       "bordes": sorted({round(c[0]) for f in filas for c in f["celdas"] if c})})
    return tablas


def _en(c: dict, caja) -> bool:
    return (caja[0] <= (c["x0"] + c["x1"]) / 2 < caja[2]
            and caja[1] <= (c["top"] + c["bottom"]) / 2 < caja[3])


def _se_enciman(a, b) -> bool:
    return a[0] < b[2] - 1 and b[0] < a[2] - 1 and a[1] < b[3] - 1 and b[1] < a[3] - 1


def _renglon(fila: dict) -> str:
    return " ".join(c[1] for c in fila["celdas"] if c and c[1])


def _sigue(anterior: dict, tabla: dict) -> bool:
    """¿La primera fila de `tabla` es el resto de la última de `anterior`,
    partida por el salto de página? Mismas columnas, le faltan celdas que la
    fila anterior sí tiene, y o bien viene vacía la que identifica la fila (la
    primera) o su texto sigue en minúscula."""
    if anterior["bordes"] != tabla["bordes"] or not anterior["filas"]:
        return False
    primera, ultima = tabla["filas"][0]["celdas"], anterior["filas"][-1]["celdas"]
    if len(primera) != len(ultima) or not primera or primera[0] is None:
        return False
    llenas = [k for k, c in enumerate(primera) if c and c[1]]
    vacias = [k for k, c in enumerate(primera) if c and not c[1]]
    if not llenas or not vacias or any(not (ultima[k] and ultima[k][1]) for k in llenas):
        return False
    return 0 in vacias or primera[llenas[0]][1][:1].islower()


def _unir(resto: dict, fila: dict) -> None:
    """Agrega a cada celda de `fila` el texto de la misma columna de `resto`."""
    for k, c in enumerate(resto["celdas"]):
        if c and c[1] and k < len(fila["celdas"]) and fila["celdas"][k]:
            x, texto, n, g = fila["celdas"][k]
            fila["celdas"][k] = (x, f"{texto} {c[1]}".strip(), n + c[2], g)


def _dentro(renglon: dict, tabla: dict) -> bool:
    centro = (renglon["top"] + renglon["bottom"]) / 2
    return tabla["bbox"][1] <= centro <= tabla["bbox"][3]


def textos(pdf) -> list[str]:
    """El texto de cada página, como `extract_text`, con las tablas que lo
    necesitan leídas por celdas."""
    paginas = [page.extract_text() or "" for page in pdf.pages]
    tablas: list[list[dict]] = [[] for _ in paginas]
    renglones = {}
    for n, page in enumerate(pdf.pages):
        if len(page.rects) + len(page.lines) < MIN_BORDES:
            continue
        lineas = page.extract_text_lines()
        if [ln["text"] for ln in lineas] == paginas[n].split("\n"):
            tablas[n] = _leer(page, lineas)
            renglones[n] = lineas
    # La fila que sigue en la página siguiente vuelve a su fila: así no depende
    # de dónde cortó la página.
    for n in range(1, len(paginas)):
        if not tablas[n] or not tablas[n - 1]:
            continue
        anterior, tabla = tablas[n - 1][-1], tablas[n][0]
        ultimo = [r for r in renglones[n - 1] if not _dentro(r, anterior)]
        if any(r["top"] > anterior["bbox"][3] and not _pie(r["text"]) for r in ultimo):
            continue
        # El resto de una tabla que no se releyó tampoco se relee: sus dos
        # mitades se leen igual.
        if anterior["omitida"]:
            primera = tabla["filas"][0]["celdas"] if tabla["filas"] else []
            if any(c and not c[1] for c in primera):
                tabla.update(omitida=True, necesita=False, filas=[])
        elif not tabla["omitida"] and _sigue(anterior, tabla):
            resto = tabla["filas"].pop(0)
            _unir(resto, anterior["filas"][-1])
            anterior["necesita"] = tabla["necesita"] = True
            tabla["resto"] = (resto["top"], resto["bottom"])
    for n, page in enumerate(pdf.pages):
        if _MAYUSCULA_A_MEDIA_PALABRA_RE.search(paginas[n]):
            lineas = renglones.get(n) or page.extract_text_lines()
            if [ln["text"] for ln in lineas] == paginas[n].split("\n"):
                for ln in lineas:
                    if _MAYUSCULA_A_MEDIA_PALABRA_RE.search(ln["text"]):
                        ln["text"] = _sin_sobreimpresion(page, ln)
                renglones[n] = lineas
                paginas[n] = "\n".join(ln["text"] for ln in lineas)
    for n, lista in enumerate(tablas):
        if not any(t["necesita"] for t in lista):
            continue
        salida, puestas = [], set()
        for r in renglones[n]:
            k = next((k for k, t in enumerate(lista) if t["necesita"] and _dentro(r, t)), None)
            if k is None:
                salida.append(r["text"])
            elif k not in puestas:
                puestas.add(k)
                salida += [s for s in map(_renglon, lista[k]["filas"]) if s]
        paginas[n] = "\n".join(salida)
    return paginas


def _sin_sobreimpresion(pagina, renglon: dict) -> str:
    """El renglón con sus textos sobreimpresos uno tras otro. El PDF escribe
    cada texto de corrido: en el orden en que vienen sus caracteres, cada vez
    que la posición retrocede empieza otro texto. Si ninguno se encima con el
    anterior, el renglón no está sobreimpreso y queda igual."""
    propios = {id(c) for c in renglon["chars"]}
    tramos: list[list[dict]] = []
    for c in pagina.chars:
        espacio = (c["text"] == " " and renglon["x0"] <= c["x0"] <= renglon["x1"]
                   and renglon["top"] - 1 <= c["top"] and c["bottom"] <= renglon["bottom"] + 1)
        if id(c) not in propios and not espacio:
            continue
        if tramos and c["x0"] >= tramos[-1][-1]["x0"] - 1:
            tramos[-1].append(c)
        else:
            tramos.append([c])
    encimados = any(b[0]["x0"] < a[-1]["x1"] and a[0]["x0"] < b[-1]["x1"]
                    and len(a) >= MIN_SOBREIMPRESO and len(b) >= MIN_SOBREIMPRESO
                    for a, b in zip(tramos, tramos[1:]))
    if not encimados:
        return renglon["text"]
    return " ".join(" ".join("".join(c["text"] for c in tramo).split()) for tramo in tramos)


def _pie(texto: str) -> bool:
    """El pie de página ('231 de 565'): lo único que puede haber bajo una
    tabla que sigue en la página siguiente."""
    partes = texto.split()
    return len(partes) == 3 and partes[1] == "de" and partes[0].isdigit() and partes[2].isdigit()
