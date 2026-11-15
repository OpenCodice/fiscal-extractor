# Verificar y, si hace falta, reparar una extracción

Trabajas en `fiscal-extractor`, el código que convierte los PDFs oficiales de la
legislación fiscal mexicana (leyes y reglamentos de la Cámara de Diputados; RMF,
RGCE, RFA, anexos y criterios del SAT) en un archivo Markdown por unidad
(artículo, regla, criterio, ficha). Ese texto se versiona en git como registro
público de la norma vigente, y esta corrida terminará en un commit automático
sin revisión humana. Por eso lo único que importa es que el texto extraído diga
exactamente lo que dice el PDF: ni una palabra de más, ni una de menos, ni
fuera de lugar.

## Situación

El vigilante semanal descargó los PDFs vigentes y regeneró el repo de datos.
Hay unidades que cambiaron respecto de la versión anterior (lista abajo). Puede
ser una reforma real, un cambio de formato del PDF que el extractor no maneja
(pies o encabezados de página nuevos, encabezados de capítulo con otro estilo,
saltos de página a media oración), o las dos cosas a la vez.

- Extractor (tu directorio de trabajo, repo git): `__EXTRACTOR__`
- Repo de datos regenerado: `__OUT__` (texto en `<documento>/<unidad>.md`)
- PDFs vigentes: `__PDF_DIR__/<documento>.pdf`
- El registro de documentos y qué parser usa cada uno: `extractor/registro.py`;
  los parsers, en `extractor/parsers/`
- Para regenerar un documento:
  `python -m extractor build --doc <documento> --pdf-dir __PDF_DIR__ --out __OUT__`
- Versión anterior de una unidad: `git -C __OUT__ show HEAD:<documento>/<unidad>.md`
- Texto crudo por página de un PDF, ya en caché (extraerlo con pdfplumber es
  lento): `from extractor.verificar import paginas_crudas`

Unidades cambiadas (`git status`):

```
__CAMBIADOS__
```

Una comprobación determinista (`python -m extractor verificar --sin-llm`, basada
en `cobertura` de `extractor/verificar.py`) ya revisó que cada párrafo extraído
esté literal en el texto limpio del PDF y que no quede texto sin extraer entre
párrafos. Su resultado:

```
__COBERTURA__
```

Esa comprobación no ve todo: compara contra el texto ya filtrado por el propio
extractor, así que no detecta un pie de página que el extractor no reconoce y
dejó colado dentro de una unidad, ni una unidad que absorbió a su vecina. Eso
te toca a ti.

## Qué hacer

1. Compara cada unidad cambiada contra las páginas del PDF donde vive. No te
   fíes de la versión anterior del repo ni de tu memoria de la ley: la fuente de
   verdad es el PDF. Si son muchas unidades, revísalas todas igual; escribe
   scripts para hacerlo en lote y mira a mano las que salgan raras.
2. Si la extracción es fiel, no toques nada.
3. Si hay un defecto de extracción, corrígelo en el código del extractor, de la
   forma más general que el caso permita —un patrón, no un parche para una
   unidad—, y agrega una prueba de regresión en `tests/`. Regenera el documento
   y vuelve a comparar contra el PDF hasta que quede fiel.
4. Antes de terminar, si cambiaste código: `python -m pytest -q` debe pasar y
   `python -m extractor auditar --out __OUT__ --pdf-dir __PDF_DIR__` no puede
   listar unidades que no estén ya en `__TRABAJO__/base.json` (la línea base
   antes de tu cambio). Un arreglo que rompe otra unidad se descarta entero.

La línea base ya trae unidades con problemas conocidos de versiones anteriores
(por ejemplo, el nombre del capítulo siguiente pegado al final de un artículo).
No son tu tarea salvo que estén entre las unidades cambiadas; si lo están,
arréglalas.

## Límites

- Nunca edites a mano los archivos del repo de datos: su contenido solo puede
  salir de correr el extractor. Después de ti, el pipeline comprueba que no los
  hayas tocado y, si cambiaste el extractor, regenera todo el corpus con tu
  versión.
- No modifiques `extractor/verificar.py` ni las pruebas existentes para que
  pasen; son la compuerta que decide si tu arreglo se publica.
- No hagas commit ni push; el pipeline lo hace si las compuertas pasan.
- Si no logras una extracción fiel, dilo en el veredicto. Un "no pude" honesto
  deja el cambio en revisión humana; un "fiel" equivocado publica ley falsa.

## Entrega

Escribe `__TRABAJO__/veredicto.json` con esta forma, y nada más como salida final:

```json
{
  "fiel": true,
  "reparado": false,
  "titulo_commit": "solo si reparado: una línea que describa el arreglo",
  "reformadas": ["cff/027"],
  "resumen": "dos o tres frases: qué cambió en la norma y, si aplica, qué defecto había y cómo lo arreglaste",
  "unidades": [{"clave": "cff/027", "veredicto": "fiel", "nota": "qué verificaste"}]
}
```

`reformadas` lista las claves de las unidades cuyo texto legal cambió en el PDF
(una reforma, adición o derogación real), sin omitir ninguna. Las que cambiaron
solo porque el extractor ahora lee mejor el mismo texto no van ahí: son
correcciones de extracción. De esa lista sale el título del commit en el
historial público, así que una corrección no debe aparecer como reforma ni al
revés.

`fiel` es verdadero solo si TODAS las unidades cambiadas, tal como quedan
después de tu trabajo, reproducen el PDF. `veredicto` por unidad: `fiel`,
`artefacto` o `incierto`. Si son más de 80 unidades, lista las que no sean
`fiel` y resume el resto en `resumen`.
