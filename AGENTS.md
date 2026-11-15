# fiscal-extractor — guía para agentes

Convierte los PDF oficiales de la legislación fiscal mexicana en un archivo
Markdown por unidad (artículo, regla, criterio, ficha) más metadata derivada.
Es código; los datos viven en `fiscal-mexicano` y en `leyes-federales` (todas
las leyes de LeyesBiblio, con el mismo parser `articulado`), que nunca se
editan a mano: si una unidad está mal, se corrige aquí.

## Estructura

- `extractor/registro.py` — el corpus declarado: un `Documento` por fuente, con
  su `clave` (namespace de todo lo que produce), URL y `parser`.
- `extractor/fuentes.py` — descarga y resolución de la URL vigente. Las del SAT
  llevan la fecha en el nombre y se resuelven contra una página índice.
- `extractor/parsers/` — un parser por tipo de documento:
  `articulado` (leyes y reglamentos de la Cámara de Diputados), `reglas` (RMF,
  RGCE, RFA), `criterios`, `fichas` y `apartados` (anexos de la RMF).
- `extractor/modelo.py`, `normalize.py`, `pasajes.py`, `referencias.py`,
  `locate.py`, `build.py` — unidades, párrafos y metadata derivada.
- `extractor/validate.py` — invariantes del repo de datos (gate de los PR).
- `extractor/verificar.py` — fidelidad contra el PDF: `cobertura` (cada párrafo
  literal en el PDF y sin texto omitido entre párrafos), `encabezado_pegado`
  (en el articulado, un último párrafo con forma de encabezado: es texto literal
  del PDF pero fuera de lugar) y `auditar`. Guarda el
  texto por página junto al PDF (`*.paginas.json`) porque extraerlo es lo lento.
- `extractor/federal.py` y `cli_federal.py` — el corpus federal: su registro
  se genera del índice de LeyesBiblio y vive en `leyes-federales/fuentes.json`
  (no en `registro.py`). `--registro <archivo>` (o un `fuentes.json` en el repo
  de `--out`) sustituye el corpus fiscal en cualquier comando.
- `scripts/agente/` — el agente de CI: `brief.md` (su encargo), `correr.sh`
  (lo lanza) y `cerrar.sh` (compuertas deterministas, publica su arreglo). Para
  el corpus federal, `brief-federal.md`, `correr-federal.sh`,
  `cerrar-federal.sh` y `muestra-federal.sh`: ahí el agente solo entra cuando
  la auditoría determinista falla.

## Comandos

```bash
.venv/bin/python -m extractor listar
.venv/bin/python -m extractor actualizar --out ../fiscal-mexicano --pdf-dir /tmp/pdfs   # descarga todo y reconstruye (~25 min)
.venv/bin/python -m extractor build --doc cff --pdf-dir /tmp/pdfs --out ../fiscal-mexicano
.venv/bin/python -m extractor validar --out ../fiscal-mexicano
.venv/bin/python -m extractor auditar --out ../fiscal-mexicano --pdf-dir /tmp/pdfs
.venv/bin/python -m extractor verificar --sin-llm --out ../fiscal-mexicano --pdf-dir /tmp/pdfs
.venv/bin/python -m pytest -q            # rápido, sin PDFs
```

Corpus federal (lo corre `leyes-federales/.github/workflows/vigilar.yml`):

```bash
.venv/bin/python -m extractor federal planear  --out ../leyes-federales --plan /tmp/plan.json --lote 40
.venv/bin/python -m extractor federal extraer  --plan /tmp/plan.json --out ../leyes-federales --pdf-dir /tmp/pdfs --shard 0 --staging /tmp/staging
.venv/bin/python -m extractor federal integrar --plan /tmp/plan.json --staging /tmp/staging --out ../leyes-federales --pdf-dir /tmp/pdfs --trabajo /tmp/agente
.venv/bin/python -m extractor federal cerrar   --plan /tmp/plan.json --out ../leyes-federales --trabajo /tmp/agente
```

Los PDF de la Cámara no responden desde fuera de México y EE. UU.; si no
llegas a diputados.gob.mx, lanza el workflow en GitHub.

`auditar` revisa todas las unidades; `verificar` solo las que difieren de
`HEAD` en el repo de datos. `verificar` sin `--sin-llm` añade una revisión por
API de OpenAI; es una herramienta manual opcional y la CI no la usa.

## Al cambiar un parser

- La compuerta es `auditar`: tras tu cambio no puede listar unidades que antes
  no listaba. Un parser sirve a varios documentos, así que audita todos los que
  lo usan, no solo el que estás arreglando. `articulado` sirve además a las
  ~320 leyes de `leyes-federales`: un cambio a `parsers/`, `build.py`,
  `modelo.py` o `normalize.py` cambia la huella del extractor y la siguiente
  vigilancia reconstruye y audita todo ese corpus.
- Prefiere un patrón general a un caso especial por unidad, y agrega una prueba
  de regresión en `tests/`.
- Un cambio aquí modifica texto ya publicado en la siguiente vigilancia. Es lo
  esperado; ese PR sale titulado como corrección de extracción.
- No relajes `verificar.py` ni pruebas existentes para que algo pase.

## Encabezados en el articulado

Entre un artículo y el siguiente puede haber un bloque de encabezado: `LIBRO`,
`TÍTULO`, `CAPÍTULO` o `SECCIÓN`, su nombre (en mayúsculas o no, a veces en
varias líneas o tras un salto de página) y notas como `Capítulo adicionado DOF
…` o `(Se deroga)`. Si el bloque desemboca en el siguiente artículo, todo eso
es estructura: el nombre va al contexto de la unidad y nada se queda en el
cuerpo del artículo anterior. Debajo de la sección está el `epigrafe`: un
`APARTADO`, un numeral romano solo o un rótulo sin palabra clave ('Del
Consentimiento' en el Código Civil) que sigue a un fin de oración y desemboca
en el siguiente artículo. `PARTE` cuenta como nivel de título, igual que
`LIBRO`.

## Agregar un documento

Una entrada en `extractor/registro.py`. Las leyes y reglamentos de la Cámara de
Diputados usan `_ley(...)` y el parser `articulado` sin más código. Después:
`build`, `validar` y `auditar` hasta dejarlo en cero problemas.
