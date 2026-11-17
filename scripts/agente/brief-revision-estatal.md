# Revisión completa de una ley estatal nueva contra su PDF

Trabajas con `fiscal-extractor`, el código que convierte los PDF oficiales de
la legislación mexicana en un archivo Markdown por artículo. Ese texto se
versiona en git como registro público de la ley vigente y se publica sin
revisión humana. `__DOCUMENTO__` es una ley de un estado (su clave es
`<estado>/<ley>`) que se va a publicar por primera vez, entera: antes de eso hay
que revisarla toda contra el PDF que publica el estado, porque lo que se
publique mal hoy será una "corrección de extracción" mañana. Lo único que
importa es que el texto diga exactamente lo que dice el PDF: ni una palabra de
más, ni una de menos, ni fuera de lugar.

- Extractor: `__EXTRACTOR__` (la ley se declara en `extractor/estatales/`, el
  parser es `extractor/parsers/articulado.py`)
- Repo de datos: `__OUT__` (la ley está en `__DOCUMENTO__/articulos/<artículo>.md`)
- PDF: `__PDF__`

Las compuertas deterministas ya pasaron (cada párrafo está literal en el texto
del PDF filtrado por el extractor, sin texto omitido entre párrafos). Eso no ve
un pie o encabezado de página que el extractor no reconoce y dejó colado, un
encabezado estructural pegado al cuerpo, un artículo que absorbió a su vecino,
párrafos mal partidos o unidos, ni artículos que faltan. Eso te toca a ti.

## Convenciones del texto extraído (no son defectos)

- El encabezado del archivo (`# Artículo 12.`) normaliza el rótulo del PDF
  (`ARTICULO 12.-`, `Artículo 12.`); el texto que le sigue en su renglón es el
  primer párrafo.
- Las notas de reforma van en cursiva, cada una en su párrafo
  (`_(REFORMADO, G.O. 25 DE MAYO DE 2000)_`, `_Fracción adicionada G.O. CDMX
  27/03/24_`). Las que el PDF pone justo ANTES del rótulo de un artículo son de
  ese artículo y quedan como su primer párrafo, después del encabezado.
- Los encabezados de estructura (Libro, Título, Capítulo, Sección, epígrafes
  como «De la prelación») no van en el cuerpo de ningún artículo: son contexto.
  Las notas que anotan a esos encabezados («Capítulo adicionado …», «(REFORMADA
  SU DENOMINACIÓN, …)») tampoco.
- Si el PDF omite números de artículo (derogados que el estado quitó), el hueco
  es del PDF: no es un artículo que falte. Sí es defecto un artículo que está en
  el PDF y no tiene archivo, o cuyo texto quedó dentro de otro.
- Las páginas del PDF traen encabezados, pies y números de página que no son
  texto de la ley; si alguno quedó dentro de un artículo, eso sí es defecto.
- Lo anterior al primer artículo (decreto de expedición, índice) y lo posterior
  al articulado (transitorios, tablas de reformas) no se versiona.

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
publica, queda anotado con su motivo en `fuentes.json` de leyes-estatales y se reintenta cuando
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
