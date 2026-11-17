# Revisión completa de un documento nuevo contra su PDF

Trabajas en `fiscal-extractor`, el código que convierte los PDF oficiales de la
legislación mexicana (leyes y reglamentos de la Cámara de Diputados; RMF,
anexos y criterios del SAT) en un archivo Markdown por unidad (artículo, regla,
criterio, ficha). Ese texto se
versiona en git como registro público de la ley vigente y se publica sin
revisión humana. `__DOCUMENTO__` se va a publicar por primera vez, entero: antes
de eso hay que revisarlo todo contra el PDF, porque lo que se publique mal hoy
será una "corrección de extracción" mañana. Lo único que importa es que el
texto diga exactamente lo que dice el PDF: ni una palabra de más, ni una de
menos, ni fuera de lugar.

- Extractor (tu directorio de trabajo, repo git): `__EXTRACTOR__`
- Repo de datos: `__OUT__` (el documento está en `__DOCUMENTO__/<unidad>.md`)
- PDF: `__PDF__`; el registro de documentos y su parser, en
  `extractor/registro.py`; los parsers, en `extractor/parsers/`
- Para regenerar: `__BUILD__`
- Para volver a partir en bloques (después de regenerar): `__PLANEAR__`

Las compuertas deterministas ya pasaron (cada párrafo está literal en el texto
del PDF filtrado por el extractor, sin texto omitido entre párrafos). Eso no ve
un pie o encabezado de página que el extractor no reconoce y dejó colado, un
encabezado estructural pegado al cuerpo, un artículo que absorbió a su vecino,
párrafos mal partidos o unidos, ni artículos que faltan. Eso te toca a ti.

## Bloques de esta sesión

El documento está partido en bloques de artículos consecutivos. Cada archivo
de bloque tiene el texto extraído de sus artículos y, abajo, el texto crudo de
las páginas del PDF donde viven. En esta sesión revisa estos:

```
__BLOQUES__
```

Para cada bloque, compara cada artículo con el PDF: que empiece y termine donde
el PDF, que no le falte ni le sobre texto, que no se cuele nada de la página
(números, encabezados, pies, fechas de publicación), que los párrafos, notas
de reforma y fracciones estén donde están en el PDF. Si el texto crudo de la
página no alcanza (columnas, tablas), abre esa página con pdfplumber.

## Si encuentras un defecto

Corrígelo en el código del extractor (el parser o su configuración en el registro), de
la forma más general que el caso permita —un patrón, no un parche para un
artículo— y agrega una prueba de regresión en `tests/`. Regenera, vuelve a
partir en bloques y revisa otra vez los bloques cuya huella cambió (el plan
está en `__TRABAJO__/plan.json`). Antes de terminar, si cambiaste código,
`python -m pytest -q` debe pasar. Después de ti, el pipeline vuelve a correr
todas las compuertas y reconstruye todo lo publicado (el corpus fiscal y las
leyes federales): un arreglo que cambie otra unidad publicada sin mejorarla se
descarta entero.

Si no logras que un bloque quede fiel, anótalo como hallazgo: el documento no
se publica y está bien. Un hallazgo honesto deja el documento fuera; un "sin
hallazgos" equivocado publica ley falsa.

## Límites

- Nunca edites a mano el repo de datos: su contenido solo sale del extractor.
- No modifiques `extractor/verificar.py`, `extractor/validate.py` ni las pruebas
  existentes.
- No hagas commit ni push.

## Entrega

Escribe `__VEREDICTO__` con un objeto por bloque revisado, con la huella que
tiene el bloque **tal como queda al final** (la del plan después de tu último
regenerado):

```json
{
  "bloques": [
    {"id": "b003", "huella": "…", "hallazgos": [],
     "nota": "arts. 21 a 40 contra págs. 12 a 18: fieles"},
    {"id": "b004", "huella": "…",
     "hallazgos": [{"clave": "045", "nota": "el pie «Última reforma …» quedó al final del párrafo 3"}]}
  ]
}
```

Si cambiaste el código, escribe además `__TRABAJO_AGENTE__/veredicto.json` con
`{"reparado": true, "titulo_commit": "una línea que describa el arreglo",
"resumen": "qué defecto había y cómo lo arreglaste"}`.
