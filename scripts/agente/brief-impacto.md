# Confirmar correcciones de extracción contra el PDF

Un cambio en el código del extractor cambia el texto de artículos ya
publicados, sin que la ley haya cambiado: el PDF es el mismo, solo se lee
distinto. Ese texto es el registro público de la ley vigente y se publica sin
revisión humana. Una corrección solo entra si deja el artículo más fiel al PDF
que como está publicado. Tu trabajo es decidirlo, artículo por artículo, contra
el PDF; no tienes que arreglar nada.

Origen de los cambios: __ORIGEN__

## Qué tienes

`__PENDIENTES__` lista los cambios, agrupados (en esta sesión decides solo los
grupos del resumen de abajo): los artículos de un grupo
cambiaron de la misma manera (la misma palabra o renglón quitado o puesto, salvo
números). Por miembro:

- `antes` y `despues`: el texto publicado y el propuesto (Markdown; `null` si
  el artículo no existía o deja de existir);
- `diff`: la diferencia por párrafos;
- `pdf`: el PDF oficial del que salen los dos;
- `revisar: true` en los que debes mirar contra el PDF (hasta tres por grupo,
  de documentos distintos cuando los hay).

Para leer una página: `python -c "import pdfplumber,sys; p=pdfplumber.open(sys.argv[1]).pages[int(sys.argv[2])-1]; print(p.extract_text())" PDF N`.
Para encontrar la página de un artículo, busca una frase suya en el texto de
las páginas (escribe un script; no leas el PDF entero a ojo).

Resumen de lo que hay que verificar:

```
__RESUMEN__
```

## Qué decidir por grupo

- `mejora`: en los miembros revisados, el texto propuesto reproduce el PDF y el
  publicado no (le sobraba o le faltaba texto, estaba fuera de lugar, mal
  partido en párrafos, con una errata de lectura). Si el grupo tiene más
  miembros de los que revisaste, mira sus `diff` en lote (un script) y confirma
  que todos son el mismo cambio en el mismo tipo de lugar.
- `empeora`: el propuesto se aleja del PDF en algún miembro revisado.
- `incierto`: no puedes decidir con seguridad (el PDF es ambiguo, los dos
  textos son igual de fieles, o un miembro del grupo no se parece a los demás).
  Un cambio que no es mejor ni peor tampoco entra: márcalo `incierto`.

Ante la duda, `incierto`. Un "mejora" equivocado publica ley falsa; un
"incierto" solo deja la versión publicada como está.

## Límites

- No modifiques ningún archivo fuera de `__TRABAJO__`: ni el extractor ni los
  repos de datos. No toques `pendientes.json` ni los veredictos de otras
  sesiones.
- No hagas commit ni push.

## Entrega

Escribe `__VEREDICTO__`, con un objeto por cada grupo de esta sesión:

```json
{
  "grupos": [
    {"id": "g001", "veredicto": "mejora",
     "nota": "qué revisaste: p. ej. 'pie de página «Página N» ya no se cuela; verificado en 3 de 40 artículos, los 40 diffs son iguales'"}
  ]
}
```
