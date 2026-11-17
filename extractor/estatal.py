"""Corpus de leyes estatales: las de `extractor/estatales/`, en leyes-estatales.

Usa el mismo flujo que el corpus federal (federal.py: planear → extraer →
cerrar, por lotes y repartido entre varios jobs) con tres diferencias:

- El registro se declara en código, un módulo por estado, porque cada estado
  publica sus leyes en un sitio distinto; `fuentes.json` de leyes-estatales
  guarda, como el de leyes-federales, qué se publicó y con qué PDF y extractor.
- La clave de cada ley es '<estado>/<ley>' y sus archivos viven junto a la
  constitución del estado, en `<estado>/<ley>/articulos/` y `…/metadata/`
  (ver disposicion.py). Las constituciones las sigue produciendo y vigilando
  constitucion-extractor; este flujo no toca `<estado>/constitucion/`.
- Las leyes que se decide no versionar (FUERA en el módulo del estado) quedan
  en fuentes.json como excluidas, con su motivo, aunque nunca se publiquen.
"""
from __future__ import annotations

from .estatales import documentos, fuera
from .federal import Corpus
from .registro import a_dict

ESTATAL = Corpus(
    nombre="estatal", indice=None,
    fuera={c: m for c, (_, m) in fuera().items()},
    singular="ley estatal", plural="leyes estatales",
    definiciones_fuera={c: a_dict(d) for c, (d, _) in fuera().items()},
    campos_registro=("clave", "etiqueta", "sigla", "tipo", "parser", "medio", "indice"),
    fuentes_extractor=("estatales/*.py", "disposicion.py"),
)

__all__ = ["ESTATAL", "documentos"]
