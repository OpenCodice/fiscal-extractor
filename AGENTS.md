# fiscal-extractor — guía para agentes

Convierte los PDF oficiales de la legislación fiscal mexicana en un archivo
Markdown por unidad (artículo, regla, criterio, ficha) más metadata derivada.
Es código; los datos viven en `fiscal-mexicano`, en `leyes-federales` (todas
las leyes de LeyesBiblio, con el mismo parser `articulado`) y, para las leyes
de cada estado además de su constitución, en `leyes-estatales`
(`{estado}/{ley}/`, ver «Leyes estatales»). Nunca se editan a mano: si una
unidad está mal, se corrige aquí.

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
- `extractor/estatal.py`, `extractor/estatales/` (un módulo por estado) y
  `extractor/disposicion.py` — el corpus de leyes estatales y dónde vive cada
  documento en su repo de datos. Ver «Leyes estatales».
- `.github/workflows/vigilar-leyes-estatales.yml` — su vigilancia.
- `.github/workflows/vigilar-fiscal.yml` y `vigilar-federal.yml` — la vigilancia
  de `fiscal-mexicano` y `leyes-federales`. Viven aquí, no en los repos de
  datos, para que el historial de esos repos solo tenga cambios de texto legal.
  Las lanza cada lunes el Worker `scheduler` (constitucion-extractor/scheduler/)
  y abren en el repo de datos un PR con un commit por documento
  (`scripts/commits_por_documento.py`), que `revisar-pr` fusiona con rebase.
- `scripts/commits_por_documento.py` — un commit por documento con sus
  trailers (y uno `Tipo: indice` para lo compartido). `scripts/trailers.py` los
  calcula y `scripts/validar_commits.py` los comprueba desde `revisar-pr` de
  cada repo de datos. Con `--verificadas`, una corrección sin confirmar no se
  publica (si había reforma, sale solo la reforma, construida con el extractor
  anterior). `trailers.py`, `validar_commits.py`, `impacto.py`, `revision.py`,
  `agente/impacto.sh`, `agente/brief-impacto.md`, `agente/brief_revision.py` y
  `agente/publicar_registro.sh` existen idénticos en `constitucion-extractor`
  (y `tests/test_trailers.py`, `tests/test_impacto.py`): un cambio se hace en
  los dos.
- `scripts/readme_fiscal.py` y `readme_federal.py` — regeneran las tablas del
  README de cada repo de datos; las corre su vigilancia.
- `scripts/agente/` — el agente de CI: `brief.md` (su encargo), `correr.sh`
  (lo lanza) y `cerrar.sh` (compuertas deterministas en dos fases:
  `compuertas` sin secretos y `publicar`, que sube su arreglo). Para el corpus
  federal, `brief-federal.md`, `correr-federal.sh`, `cerrar-federal.sh` (las
  mismas dos fases) y `muestra-federal.sh`: ahí el agente repara solo cuando la
  auditoría determinista falla. `brief-revision.md` / `revision-federal.sh` +
  `brief-revision-federal.md`: la revisión completa de un alta.
  `impacto.sh` + `brief-impacto.md`: el agente que solo juzga si cada
  corrección es mejora. `publicar_registro.sh` sube a main los registros de
  `verificaciones/`.
- `scripts/impacto.py` — registro de correcciones confirmadas
  (`verificaciones/impacto/*.jsonl`: documento, unidad, sha256 del PDF y del
  texto antes y después, veredicto), su exigencia sobre los commits de una
  vigilancia (`pendientes-commits`, `cerrar`, `exigir`) y el agrupado de
  cambios iguales para que el agente revise pocos.
- `scripts/impacto_corpus.py` — reconstruye cada documento publicado de
  fiscal-mexicano y leyes-federales desde el PDF exacto de su versión
  publicada (por sha256; caché en `--cache`) y lista cada unidad que cambiaría
  (y regresiones de cobertura).
- `scripts/revision.py` — revisión completa de un alta: bloques de unidades
  con el texto crudo de sus páginas, y el resultado en
  `verificaciones/altas/*.jsonl`.
- `.github/workflows/impacto.yml` — en cada push a main que toca `extractor/`
  (un commit a mano incluido) mide su impacto en todo lo publicado y confirma
  las correcciones con el agente.

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
  documento aparece o desaparece. Una corrección que no cambia el texto de
  ninguna unidad (solo metadata) es `metadatos`, con título `Metadatos de
  <SIGLA>: <archivos>`; una `correccion` sin artículos la rechaza el
  validador.
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

El historial de los dos repos se reescribió por última vez el 2026-11-17: cada
documento empieza en su alta y sigue solo con sus reformas reales, con todos
los trailers (también Fuente, Fuente-Sha256 y Extractor), y
`metadata/documentos.json` guarda ya `pdf_sha256` y `extractor_sha` de cada
documento. Desde entonces no se reescribe: los hashes son estables.
`trailers.calcular(documento, tipo, rutas, lector_antes, lector_despues)` sobre
dos árboles (`lector_git(repo, rev)`) y `trailers.formatear` dan el mensaje de
cualquier commit.

## Al cambiar un parser

- La compuerta es `auditar`: tras tu cambio no puede listar unidades que antes
  no listaba. Un parser sirve a varios documentos, así que audita todos los que
  lo usan, no solo el que estás arreglando. `articulado` sirve además a las
  ~320 leyes de `leyes-federales`: un cambio a `parsers/`, `build.py`,
  `modelo.py` o `normalize.py` cambia la huella del extractor y la siguiente
  vigilancia reconstruye y audita todo ese corpus.
- Prefiere un patrón general a un caso especial por unidad, y agrega una prueba
  de regresión en `tests/`.
- Un cambio aquí modifica texto ya publicado, y eso solo se publica como
  corrección (`Tipo: correccion`) si cada unidad que cambia está confirmada
  como mejora contra el PDF en `verificaciones/impacto/`. Al llegar a main,
  `impacto.yml` reconstruye todo lo publicado (unos 330 documentos), lista lo
  que cambia y el agente lo juzga; lo rechazado o sin juzgar no se publica (la
  vigilancia rehace sus commits sin esa corrección y el documento conserva su
  versión y su extractor anteriores, con `revision_pendiente`). Antes de hacer
  push, mide el impacto con `python scripts/impacto_corpus.py --trabajo
  /tmp/impacto --fiscal ../fiscal-mexicano --federal ../leyes-federales
  --pdf-dir <PDFs> --cache /tmp/pdfs-corpus` (los PDF de la Cámara solo se
  descargan desde México o EE. UU.; si no, lanza `impacto.yml`).
- Un arreglo del agente en la vigilancia pasa por lo mismo antes de entrar: si
  algo de lo que cambia en el corpus empeora o no se puede confirmar, se
  descarta entero.
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
`build`, `validar` y `auditar` hasta dejarlo en cero problemas. La vigilancia
no lo publica solo con eso: el agente lo revisa entero contra el PDF, por
bloques (`scripts/revision.py`), y un alta con hallazgos (o que no se pudo
revisar) se queda fuera de esa corrida. Las leyes federales nuevas pasan por lo
mismo (`revision-federal.sh`, hasta 3 por corrida; las demás se aplazan): con
hallazgos quedan `excluida` en `fuentes.json` con su motivo y se reintentan
cuando cambia el PDF o el extractor.

## Leyes estatales

Las leyes de cada estado distintas de su constitución (códigos civiles y
penales, de procedimientos, leyes orgánicas…). Diseño, decidido al empezar esta
fase (2026-11-17):

- **Datos:** en `leyes-estatales`, junto a la constitución del estado, una
  carpeta por ley: `{estado}/{ley}/articulos/NNN.md` y `{estado}/{ley}/metadata/`
  (la misma forma que `{estado}/constitucion/`). `Documento` de sus commits:
  `<estado>/<ley>` (`jalisco/codigo-civil`). `disposicion.py` decide la ruta por
  la clave (con `/` → estatal) y `scripts/trailers.py` aplica la misma regla
  (una prueba exige que coincidan). El PDF no se guarda en el repo (sí su
  sha256 y su URL en `fuentes.json`), como en el corpus federal: 32 estados con
  decenas de códigos de varios MB no caben en git.
- **Parser:** `articulado`, el mismo de las leyes federales (los códigos
  estatales tienen la estructura de los federales: libros, títulos, capítulos,
  artículos Bis…). Lo propio de cada fuente va en la definición de la ley
  (`Documento`): `medio` (periódico oficial, trailer Medio), `huecos` (el PDF
  omite artículos derogados: se salta un número solo si no vuelve a aparecer
  en el resto del texto), `notas` (regex de sus notas de reforma: van en
  cursiva y dan las fechas de `reformas.json`), `notas_previas` (las que el PDF
  pone ANTES del artículo, como la CDMX: pasan a ser su primer párrafo; las que
  anotan un encabezado se quedan con la estructura) y `titulos_encabezado`. La
  versión sale de la portada ('Última reforma publicada … el 20 de agosto de
  2026') o de la última fecha de su tabla de reformas (Jalisco). Las reglas de
  `verificar.py` que dependen de esas convenciones (el rótulo propio entre la
  nota previa y el texto; un cuerpo 'SE DEROGA' o una enumeración abierta al
  final) solo aplican a las leyes estatales: la auditoría federal no cambia.
- **Registro:** `extractor/estatales/<estado>.py` (`MEDIO`, `LEYES` con
  `ley(...)`, `FUERA` con su motivo en lenguaje llano). La clave es el nombre
  oficial sin el ámbito ('del Estado de Jalisco', 'para el Distrito Federal'),
  en minúsculas con guiones, y no cambia una vez publicada. La URL vigente se
  resuelve en cada vigilancia contra la página índice del sitio oficial
  (`indice` + `patron` + `orden`: `ddmmaa` en Jalisco, `unico` en la CDMX);
  `via="mx"` descarga por el Worker `egress-mx` (`EGRESS_MX_TOKEN`).
  `fuentes.json` de leyes-estatales guarda lo publicado (incluida/excluida y por
  qué, PDF, extractor), solo con los campos que identifican a la ley: cómo leer
  su PDF vive en el código y `registro.cargar` lo toma de ahí.
- **Vigilancia:** `vigilar-leyes-estatales.yml`, el flujo federal
  (`extractor estatal planear|extraer|integrar|cerrar`, mismos pasos que
  `federal …`) por tandas (`--lote`, 8 altas por corrida). Las altas pasan la
  revisión completa por bloques (`revision-federal.sh` con
  `brief-revision-estatal.md`), de la más corta a la más larga, hasta 2.5
  millones de caracteres por corrida y 4 a la vez; una revisión a medias se
  aplaza y retoma sus veredictos de la caché de Actions. Aquí el agente no
  repara el extractor: un arreglo entra por main y pasa por `impacto.yml`, que
  mide ya también estas leyes (`impacto_corpus.py --estatal`). El PR va a la
  rama `reforma/leyes-estatales`, la que `revisar-pr` de leyes-estatales
  fusiona; ese `revisar-pr` valida los trailers con la copia de
  `scripts/validar_commits.py` de constitucion-extractor, que debe estar al día.
- Las constituciones las sigue produciendo y vigilando constitucion-extractor
  (`{estado}/constitucion/`); este flujo no las toca, y aquel no toca las leyes.

```bash
.venv/bin/python -m extractor estatal planear --out ../leyes-estatales --plan /tmp/plan.json [--estado jalisco] [--lote 8]
# luego extraer / integrar / cerrar como en el corpus federal, con `estatal`
```

Agregar una ley: una entrada `ley(...)` en el módulo de su estado (o el módulo
nuevo, con su `MEDIO`), `build` + `auditar` en cero problemas sobre su PDF, y la
vigilancia la da de alta tras su revisión completa. Si no puede quedar fiel
(p. ej. el Código de Procedimientos Civiles de la CDMX, que reinicia su
numeración en el Título Especial), va en `FUERA` con su motivo.
