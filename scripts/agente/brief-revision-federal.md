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

No lo arregles: en esta corrida el extractor ya pasó sus compuertas y no se
cambia. Anótalo como hallazgo, con la unidad y qué tiene. El documento no se
publica, queda anotado con su motivo en `fuentes.json` y se reintenta cuando
cambie el extractor o el PDF. Un hallazgo honesto deja el documento fuera; un
"sin hallazgos" equivocado publica ley falsa.

## Límites

- No modifiques ningún archivo fuera de `__TRABAJO__`: ni el extractor ni el
  repo de datos.
- No modifiques `extractor/verificar.py`, `extractor/validate.py` ni las pruebas
  existentes.
- No hagas commit ni push.

## Entrega

Escribe `__VEREDICTO__` con un objeto por bloque revisado, con la huella que
tiene en el plan:

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
