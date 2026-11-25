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

# Cambiar la lectura invalida el texto por página que `verificar` guarda junto
# al PDF.
VERSION = 1
MIN_BORDES = 4
MIN_SOBREIMPRESO = 4
# Dos textos impresos uno sobre el otro salen con las letras intercaladas
# ('isponZoinab dei dlispiondibilaidadd'): una mayúscula a media palabra los
# delata, y la geometría lo confirma.
_MAYUSCULA_A_MEDIA_PALABRA_RE = re.compile(r"[a-záéíóúñ]{2}[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2}")


def _girado(c: dict) -> bool:
    m = c.get("matrix")
    return bool(m) and abs(m[0]) < 0.01 and abs(m[1]) > 0.01


def _texto_celda(pagina, caja) -> tuple[str, int, bool]:
    """Texto de la celda, sus renglones y si trae texto girado. El girado se
    lee por columnas, de abajo hacia arriba."""
    x0, top, x1, bottom = caja
    chars = [c for c in pagina.chars
             if x0 <= (c["x0"] + c["x1"]) / 2 < x1 and top <= (c["top"] + c["bottom"]) / 2 < bottom]
    if not chars:
        return "", 0, False
    girados = [c for c in chars if _girado(c)]
    if girados and len(girados) >= len(chars) / 2:
        columnas: dict[int, list[dict]] = {}
        for c in girados:
            columnas.setdefault(round(c["x0"] / 4), []).append(c)
        partes = ["".join(c["text"] for c in sorted(col, key=lambda c: -c["top"])).strip()
                  for _, col in sorted(columnas.items())]
        return " ".join(" ".join(p.split()) for p in partes if p), len(partes), True
    texto = pagina.crop((x0, top, x1, bottom), strict=False).extract_text() or ""
    renglones = [r.strip() for r in texto.split("\n") if r.strip()]
    return " ".join(renglones), len(renglones), False


def _leer(pagina) -> list[dict]:
    """Las tablas de la página con al menos dos columnas y dos filas."""
    if len(pagina.rects) + len(pagina.lines) < MIN_BORDES:
        return []
    tablas = []
    for t in pagina.find_tables():
        filas, necesita = [], False
        for fila in t.rows:
            celdas = [(c[0], *_texto_celda(pagina, c)) if c else None for c in fila.cells]
            llenas = [c for c in celdas if c and c[1]]
            if len(llenas) >= 2 and any(c[2] > 1 for c in llenas):
                necesita = True
            if any(c[3] for c in llenas):
                necesita = True
            filas.append({"top": fila.bbox[1], "bottom": fila.bbox[3], "celdas": celdas})
        columnas = max((len(f["celdas"]) for f in filas), default=0)
        if columnas >= 2 and len(filas) >= 1:
            tablas.append({"bbox": t.bbox, "filas": filas, "necesita": necesita,
                           "bordes": sorted({round(c[0]) for f in filas for c in f["celdas"] if c})})
    return tablas


def _renglon(fila: dict) -> str:
    return " ".join(c[1] for c in fila["celdas"] if c and c[1])


def _sigue(anterior: dict, tabla: dict) -> bool:
    """¿La primera fila de `tabla` es el resto de la última de `anterior`,
    partida por el salto de página? Mismas columnas, y la celda que identifica
    la fila (la primera) viene vacía."""
    if anterior["bordes"] != tabla["bordes"]:
        return False
    primera = tabla["filas"][0]["celdas"]
    return bool(primera) and primera[0] is not None and not primera[0][1] and any(
        c and c[1] for c in primera[1:])


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
    tablas = [_leer(page) for page in pdf.pages]
    renglones = {}
    for n, page in enumerate(pdf.pages):
        if tablas[n]:
            lineas = page.extract_text_lines()
            if [ln["text"] for ln in lineas] != paginas[n].split("\n"):
                tablas[n] = []
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
        if _sigue(anterior, tabla):
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
