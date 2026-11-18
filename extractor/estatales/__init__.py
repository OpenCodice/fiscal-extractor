"""Registro de las leyes estatales (además de la constitución de cada estado).

Un módulo por estado, con el slug de su carpeta en `leyes-estatales` (guion →
guion bajo: `nuevo_leon.py` → `nuevo-leon`). Cada módulo define:

- `MEDIO` — el periódico oficial donde se publican sus reformas (trailer Medio);
- `LEYES` — las leyes que se versionan, cada una con `ley(...)`: su clave
  estable dentro del estado, su nombre, su sigla y cómo encontrar su PDF
  vigente en el sitio oficial (página índice + patrón del enlace);
- `FUERA` — leyes que se decidió no versionar todavía: `(ley(...), motivo)`,
  con el motivo en lenguaje llano (lo muestra constitucion.app/leyes). La
  reparación autónoma intenta las que fallan la auditoría y pasa a `LEYES`
  las que quedan limpias (`scripts/reparacion.py fuera` y `promover`);
- `FUERA_POR_DISENO` (opcional) — las claves de `FUERA` que ningún arreglo del
  extractor puede sumar (una numeración que se repite, sin PDF con texto): la
  reparación no las toca.

La constitución de cada estado no está aquí: la produce constitucion-extractor
en `{estado}/constitucion/`. Lo que este registro produce vive junto a ella, en
`{estado}/{clave}/` (ver `disposicion.py`), y su estado publicado (incluida,
excluida y por qué, el sha256 del PDF y el extractor de la versión publicada)
en `fuentes.json` de leyes-estatales, como el corpus federal.

Claves: el nombre oficial sin el ámbito ('del Estado de Jalisco', 'para el
Distrito Federal', 'de la Ciudad de México'), en minúsculas y con guiones:
'codigo-civil', 'codigo-de-procedimientos-civiles',
'ley-organica-del-poder-legislativo'. Una vez publicada, la clave no cambia
aunque cambie el nombre de la ley: es el Documento de todos sus commits.
"""
from __future__ import annotations

import importlib
import pkgutil
import re
import unicodedata

from ..registro import Documento

# Las 32 entidades (las mismas carpetas que usa constitucion-extractor).
ENTIDADES = {
    "aguascalientes": "Aguascalientes", "baja-california": "Baja California",
    "baja-california-sur": "Baja California Sur", "campeche": "Campeche",
    "chiapas": "Chiapas", "chihuahua": "Chihuahua", "cdmx": "Ciudad de México",
    "coahuila": "Coahuila", "colima": "Colima", "durango": "Durango",
    "edomex": "Estado de México", "guanajuato": "Guanajuato", "guerrero": "Guerrero",
    "hidalgo": "Hidalgo", "jalisco": "Jalisco", "michoacan": "Michoacán",
    "morelos": "Morelos", "nayarit": "Nayarit", "nuevo-leon": "Nuevo León",
    "oaxaca": "Oaxaca", "puebla": "Puebla", "queretaro": "Querétaro",
    "quintana-roo": "Quintana Roo", "san-luis-potosi": "San Luis Potosí",
    "sinaloa": "Sinaloa", "sonora": "Sonora", "tabasco": "Tabasco",
    "tamaulipas": "Tamaulipas", "tlaxcala": "Tlaxcala", "veracruz": "Veracruz",
    "yucatan": "Yucatán", "zacatecas": "Zacatecas",
}

# Lo que se quita del nombre oficial para formar la clave.
_AMBITO_RE = re.compile(
    r"\s+(?:del|para\s+el|de\s+la|en\s+el)\s+(?:Estado\s+(?:Libre\s+y\s+Soberano\s+)?de\s+.*"
    r"|Distrito\s+Federal|Ciudad\s+de\s+M[ée]xico)\s*$", re.IGNORECASE)


def clave_de(nombre: str) -> str:
    """'Código de Procedimientos Civiles del Estado de Jalisco' →
    'codigo-de-procedimientos-civiles'."""
    base = _AMBITO_RE.sub("", nombre.strip())
    base = unicodedata.normalize("NFKD", base.lower())
    base = "".join(c for c in base if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", base).strip("-")


def ley(estado: str, nombre: str, sigla: str, *, medio: str, indice: str | None = None,
        patron: str | None = None, url: str | None = None, orden: str = "unico",
        clave: str | None = None, huecos: bool = True, notas: str | None = None,
        notas_previas: str | None = None, via: str | None = None,
        notas_en_linea: str | None = None,
        titulos_encabezado: tuple[str, ...] = (), consulta: bool = False,
        sin_consulta: bool = False) -> Documento:
    """Una ley estatal del registro. `huecos`: los PDF estatales suelen omitir
    los artículos derogados (ver `articulado.parse_texto`)."""
    if estado not in ENTIDADES:
        raise ValueError(f"estado desconocido: {estado}")
    return Documento(
        clave=f"{estado}/{clave or clave_de(nombre)}", etiqueta=nombre, sigla=sigla,
        tipo="ley", parser="articulado", url=url, indice=indice, patron=patron,
        medio=medio, orden=orden, huecos=huecos, notas=notas, notas_previas=notas_previas,
        notas_en_linea=notas_en_linea,
        via=via, titulos_encabezado=titulos_encabezado, consulta=consulta,
        sin_consulta=sin_consulta)


def _modulos():
    for m in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
        if not m.name.startswith("_"):
            yield m.name.replace("_", "-"), importlib.import_module(f"{__name__}.{m.name}")


def documentos(estados: list[str] | None = None) -> list[Documento]:
    """Las leyes declaradas (de `estados`, o de todos)."""
    return [d for e, mod in _modulos() if not estados or e in estados
            for d in getattr(mod, "LEYES", [])]


def fuera() -> dict[str, tuple[Documento, str]]:
    """Clave completa ('cdmx/codigo-x') → (definición, motivo) de las leyes que
    se decidió dejar fuera (`FUERA` de cada módulo: una lista de
    `(ley(...), motivo)`)."""
    return {d.clave: (d, m) for _, mod in _modulos() for d, m in getattr(mod, "FUERA", [])}


def fuera_por_diseno() -> set[str]:
    """Claves de FUERA que se quedan fuera por diseño (`FUERA_POR_DISENO` de
    cada módulo)."""
    return {c for _, mod in _modulos() for c in getattr(mod, "FUERA_POR_DISENO", ())}
