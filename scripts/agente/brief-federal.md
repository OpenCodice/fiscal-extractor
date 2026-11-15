# Reparar la extracción de leyes federales

Trabajas en `fiscal-extractor`, el código que convierte los PDF oficiales de la
Cámara de Diputados (LeyesBiblio) en un archivo Markdown por artículo. Además
del corpus fiscal, alimenta `leyes-federales`: todas las leyes federales
vigentes, versionadas en git como registro público. Lo que se publique ahí sale
sin revisión humana, así que lo único que importa es que el texto extraído diga
exactamente lo que dice el PDF: ni una palabra de más, ni una de menos, ni fuera
de lugar.

## Situación

La vigilancia extrajo estos documentos y la auditoría determinista los marcó
con fallas. Sin un arreglo, cada documento nuevo se queda fuera del corpus y
cada documento ya publicado conserva su versión anterior.

- Extractor (tu directorio de trabajo, repo git): `__EXTRACTOR__`
- Repo de datos: `__OUT__` (texto en `<documento>/<unidad>.md`)
- PDFs: `__PDF_DIR__/<documento>.pdf`, con su texto por página ya extraído en
  `<documento>.paginas.json` (extraer con pdfplumber es lento; usa
  `from extractor.verificar import paginas_crudas`)
- Registro del corpus federal: `__PLAN__` (pásalo con `--registro`)
- Para reconstruir y auditar un documento:
  `python -m extractor --registro __PLAN__ build --doc <documento> --pdf __PDF_DIR__/<documento>.pdf --out __OUT__ --sin-pasajes`
  `python -m extractor --registro __PLAN__ auditar --out __OUT__ --pdf-dir <carpeta con solo ese PDF>`
  o, para todos los de la lista a la vez, igual que la compuerta:
  `python -m extractor federal reevaluar --plan __PLAN__ --out __OUT__ --pdf-dir __PDF_DIR__ --trabajo __TRABAJO__/prueba`
  (antes copia `__TRABAJO__/fallas.json` y `__TRABAJO__/resultados.json` a esa carpeta)

Documentos con fallas y una muestra de cada una:

```
__FALLAS__
```

Tipos de falla:

- `no_literal`: un párrafo extraído no aparece tal cual en el texto limpio del
  PDF (típicamente, algo ajeno quedó pegado: el nombre de un capítulo, una nota
  de reforma, un pie de página nuevo).
- `texto_omitido`: entre dos párrafos de la unidad hay texto del PDF que no se
  extrajo.
- invariantes: huecos en la numeración de artículos, claves que colisionan,
  fugas de encabezado o pie, cuerpos vacíos.
- error de extracción: el parser se cayó o no encontró ningún artículo.

## Qué hacer

1. Agrupa las fallas por causa. Casi siempre son pocos patrones repetidos en
   muchos documentos. Mira el texto crudo de las páginas donde ocurren.
2. Corrige el extractor de la forma más general que el caso permita —un
   patrón, no un parche para un artículo ni para una ley— y agrega una prueba
   de regresión en un archivo nuevo, `tests/test_reparacion_<tema>.py`: otros
   cambios al extractor llegan mientras trabajas, y agregar al final de un
   archivo existente choca con ellos al publicar.
3. Reconstruye y vuelve a auditar hasta que los documentos queden en cero, o
   hasta convencerte de que alguno no tiene arreglo razonable (un PDF con
   texto ilegible, una ley sin artículos numerados, una errata del propio PDF).
   Esos se quedan fuera del corpus y está bien: no los fuerces.
4. Antes de terminar: `python -m pytest -q` debe pasar.

## Compuertas que vienen después de ti

Si cambiaste código, el pipeline: corre las pruebas, reconstruye los
documentos de la lista y además una muestra de leyes ya publicadas (que hoy
salen limpias), y descarta tu arreglo entero si alguna unidad de la muestra
queda con falla, o si ningún documento de la lista pasó a quedar limpio.
Si se acepta, lo publica en el extractor y todo el corpus se reconstruye con tu
versión en la siguiente corrida.

## Límites

- Nunca edites a mano los archivos del repo de datos: se restauran después de
  ti y solo cuenta lo que salga del extractor.
- No modifiques `extractor/verificar.py`, `extractor/validate.py` ni las
  pruebas existentes para que algo pase: son la compuerta.
- No hagas commit ni push.

## Entrega

Escribe `__TRABAJO__/veredicto.json` con esta forma, y nada más como salida final:

```json
{
  "reparado": true,
  "titulo_commit": "si cambiaste código: una línea que describa el arreglo",
  "resumen": "dos o tres frases: qué patrones encontraste y cómo los arreglaste",
  "documentos": [{"clave": "lgs", "nota": "qué tenía y si quedó limpio o por qué no"}]
}
```
