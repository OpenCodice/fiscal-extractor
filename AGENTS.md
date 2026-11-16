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
- `.github/workflows/vigilar-fiscal.yml` y `vigilar-federal.yml` — la vigilancia
  de `fiscal-mexicano` y `leyes-federales`. Viven aquí, no en los repos de
  datos, para que el historial de esos repos solo tenga cambios de texto legal.
  Las lanza cada lunes el Worker `scheduler` (constitucion-extractor/scheduler/)
  y abren en el repo de datos un PR con un commit por documento
  (`scripts/commits_por_documento.py`), que `revisar-pr` fusiona con rebase.
- `scripts/commits_por_documento.py` — un commit por documento con sus
  trailers (y uno `Tipo: indice` para lo compartido). `scripts/trailers.py` los
  calcula y `scripts/validar_commits.py` los comprueba desde `revisar-pr` de
  cada repo de datos. Los dos existen idénticos en `constitucion-extractor` (y
  `tests/test_trailers.py`): un cambio se hace en los dos.
- `scripts/readme_fiscal.py` y `readme_federal.py` — regeneran las tablas del
  README de cada repo de datos; las corre su vigilancia.
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

Corpus federal (lo corre `.github/workflows/vigilar-federal.yml`):

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

## Commits de datos y sus trailers

Cada commit de `fiscal-mexicano` y `leyes-federales` es de un documento y lleva,
además del título, trailers calculados por código, nunca por el agente (su
veredicto solo dice si la extracción es fiel):

```
Reforma LGS (DOF 2026-01-15): arts. 4o, 22, 222 Bis

Documento: lgs
Tipo: reforma
Publicacion: 2026-01-15
Publicacion-Origen: notas
Medio: DOF
Articulos-Modificados: 004, 022
Articulos-Adicionados: 222-bis
Fuente: https://www.diputados.gob.mx/LeyesBiblio/pdf/LGS.pdf
Fuente-Sha256: 9f2c…
Extractor: OpenCodice/fiscal-extractor@b897ca4
```

- `Tipo` por la causa: PDF distinto al de la versión publicada con el mismo
  extractor → `reforma`; mismo PDF → `correccion`; ambos → dos commits: el PDF
  nuevo se reconstruye con el commit del extractor de la versión publicada
  (`git worktree`), primero la `reforma` (lo que ese extractor ve cambiar) y
  luego la `correccion`. El PDF anterior no se guarda, así que el orden inverso
  no es reconstruible. Si no se sabe con qué extractor se publicó, todo es
  reforma con `Separacion: no-disponible`. `alta` / `retiro` cuando el
  documento aparece o desaparece.
- De dónde sale la causa: en fiscal, `metadata/documentos.json` guarda por
  documento `pdf_sha256` y `extractor_sha` de su versión publicada (`build` no
  los escribe; `commits_por_documento.py --conservar-indice` los trae de HEAD) y
  `actualizar` deja en `--pdf-dir/descargas.json` la URL de cada PDF. En
  federal, `fuentes.json` guarda `pdf.sha256`, la huella `extractor` y
  `extractor_sha`; `federal cerrar` escribe la causa de cada ley en
  `contexto.json` del directorio de trabajo.
- `Publicacion`: fechas de reforma nuevas en `metadata/<doc>/reformas.json`
  (`notas`) o, si no hay, la versión del PDF (`portada`). Solo en reforma y
  alta. `Medio: DOF` para todo el corpus (también RMF, anexos y criterios).
- Listas de claves de archivo: `Articulos-Adicionados` / `-Modificados` /
  `-Derogados` (reforma; derogado = el cuerpo pasa a "Se deroga"/"Derogado" o el
  archivo desaparece) y `Articulos-Corregidos` (corrección).

Para el historial existente, `trailers.calcular(documento, tipo, rutas,
lector_antes, lector_despues)` sobre dos árboles (`lector_git(repo, rev)`),
`trailers.tipo_historico(...)` y `trailers.formatear` dan el mensaje sin
Fuente ni Extractor.

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
  esperado; ese commit sale como corrección de extracción (`Tipo: correccion`).
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

## Fórmulas

Las fórmulas compuestas con la fuente Symbol salen del PDF como renglones de
fragmentos sueltos. `articulado` sustituye cada una por un párrafo
`[Fórmula: consultar el PDF oficial, página N]` (detector en
`bloques_de_formula`); lo legible de alrededor ('Donde:', las definiciones de
variables) se conserva. `cobertura` no busca la marca literal: exige que el
texto del PDF que sustituye sea fórmula para el mismo detector.

## Agregar un documento

Una entrada en `extractor/registro.py`. Las leyes y reglamentos de la Cámara de
Diputados usan `_ley(...)` y el parser `articulado` sin más código. Después:
`build`, `validar` y `auditar` hasta dejarlo en cero problemas.
