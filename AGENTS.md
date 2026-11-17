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
  (`scripts/commits_por_documento.py`), que su job `revisar` valida y fusiona
  con rebase.
- `.github/workflows/revisar-pr.yml` (reutilizable) y `scripts/validar_pr.sh` —
  el gate de los PR de los repos de datos, que así no necesitan workflows
  propios. Cada vigilancia lo llama tras abrir su PR (y se puede lanzar a mano
  con `gh workflow run revisar-pr.yml -f repo=OpenCodice/<repo> -f pr=<n> -f
  prefijo=actualizacion/` para un PR que quedó abierto). El job `validar`, sin
  secretos, corre `validar_pr.sh` sobre el sha de la cabeza del PR: `extractor
  validar` (en `leyes-estatales`, también cada `{estado}/constitucion` con el
  de constitucion-extractor) y `validar_commits.py` sobre cada commit. Solo si
  pasó, `fusionar` (con `PR_TOKEN`) fusiona con rebase un PR de la rama de la
  vigilancia con la etiqueta `verificado`, atado a ese sha
  (`--match-head-commit`): si la cabeza cambió, no se fusiona. También publica
  el resultado como commit status (`validar-externo`), solo informativo:
  `PR_TOKEN` no tiene el permiso «Commit statuses», así que la protección de
  main no puede exigirlo. El gate es que solo este job fusiona, y solo lo
  validado.
- `scripts/commits_por_documento.py` — un commit por documento con sus
  trailers (y uno `Tipo: indice` para lo compartido). `scripts/trailers.py` los
  calcula y `scripts/validar_commits.py` los comprueba antes de fusionar (ver
  `revisar-pr.yml`). Con `--verificadas`, una corrección sin confirmar no se
  publica (si había reforma, sale solo la reforma, construida con el extractor
  anterior). `trailers.py`, `validar_commits.py`, `validar_pr.sh`,
  `impacto.py`, `revision.py`, `agente/impacto.sh`, `agente/brief-impacto.md`,
  `agente/brief_revision.py`, `agente/publicar_registro.sh` y
  `.github/workflows/revisar-pr.yml` existen idénticos en
  `constitucion-extractor` (y `tests/test_trailers.py`,
  `tests/test_impacto.py`): un cambio se hace en los dos.
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
  corrección es mejora. `reparar.sh` + `brief-reparacion.md`: el agente que
  repara el extractor a partir de los hallazgos de la revisión completa (ver
  «Reparación autónoma»). `publicar_registro.sh` sube a main los registros de
  `verificaciones/` (y falla si no puede: lo que dependa de ese registro se
  aplaza).
- `scripts/reparacion.py` y `extractor/reparaciones.py` — la parte
  determinista de esa reparación: qué leyes y qué defecto, sus PDF, las
  compuertas sobre las leyes elegidas y el registro de intentos
  (`verificaciones/reparaciones/*.jsonl`).
- `scripts/impacto.py` — registro de correcciones confirmadas
  (`verificaciones/impacto/*.jsonl`: documento, unidad, sha256 del PDF y del
  texto antes y después, veredicto), su exigencia sobre los commits de una
  vigilancia (`pendientes-commits`, `cerrar`, `exigir`) y el agrupado de
  cambios iguales para que el agente revise pocos.
- `scripts/impacto_corpus.py` — reconstruye cada documento publicado de
  fiscal-mexicano, leyes-federales y las leyes de leyes-estatales desde el PDF
  exacto de su versión publicada (por sha256; caché en `--cache`, que se
  comprueba por sha256 al usarla) y lista cada unidad que cambiaría (y
  regresiones de cobertura). `--solo-pdfs` solo llena la caché; `--medir` es la
  medición de solo lectura del agente reparador (ver «Reparación autónoma»).
- `scripts/revision.py` — revisión completa de un alta: bloques de unidades
  con el texto crudo de sus páginas, y el resultado en
  `verificaciones/altas/*.jsonl` (con cada hallazgo, del que parte la
  reparación autónoma).
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

El historial de los dos repos se reescribió el 2026-11-17 (la final): cada
documento empieza en su alta y sigue solo con sus reformas reales, con todos
los trailers (también Fuente, Fuente-Sha256 y Extractor), y
`metadata/documentos.json` guarda ya `pdf_sha256` y `extractor_sha` de cada
documento. Ese mismo día una última reescritura solo quitó del historial la
infraestructura (`.github/`, `AGENTS.md`, `CLAUDE.md`, `.gitignore`; ver el
`AGENTS.md` raíz). Desde entonces no se reescribe: los hashes son estables.
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
hallazgos quedan `excluida` en `fuentes.json` con su motivo, el job `reparar`
intenta arreglar el extractor (ver «Reparación autónoma») y se reintentan
cuando cambia el PDF o el extractor. `federal cerrar` solo publica un alta con
la marca positiva de su revisión (`revisada`, la pone `revision-federal.sh
cerrar`): sin ella, se aplaza.

## Reparación autónoma

Cuando la revisión completa de una ley (o, en las estatales, su auditoría)
encuentra defectos, la ley queda fuera (o conserva su versión anterior con
`revision_pendiente`) y el sistema intenta repararse solo, sin una persona. El
job `reparar` de `vigilar-leyes-estatales.yml` y `vigilar-federal.yml`, después
de `cerrar` y con su propio tiempo:

1. `reparacion.py objetivo` junta los hallazgos de las leyes con defectos: las
   de esta corrida y las que `fuentes.json` tiene `excluida` o con
   `revision_pendiente` revisada (de los veredictos de la caché, del registro
   `verificaciones/altas/` o, si no, del motivo). Los clasifica por tipo
   (artículo absorbido, nota de reforma, corte de párrafo, pie de página,
   estructura, auditoría) y elige el tipo que más leyes comparten, hasta 4
   leyes: un solo arreglo para varias, y una sola sesión del agente por corrida.
2. `preparar` descarga sus PDF (si ya no es el que se revisó, la ley sale: la
   vigilancia la reprocesa) y anota el intento como `iniciado` en
   `verificaciones/reparaciones/` antes de que trabaje el agente: un intento que
   se cae también cuenta.
3. `reparar.sh medicion` deja al alcance del agente los PDF de todo lo
   publicado (`impacto_corpus.py --solo-pdfs`, en la caché `pdfs-corpus` de
   Actions, con `EGRESS_MX_TOKEN`, que el agente no tiene) y los clones de los
   repos de datos. `reparar.sh agente` (solo con `CLAUDE_CODE_OAUTH_TOKEN`)
   corrige `extractor/` y `tests/` con `brief-reparacion.md`: el arreglo más
   local posible (la definición de la ley, o detrás del flag `estatal` del
   articulado, con condiciones estrictas; reglas generales como `normalize.py`
   o la geometría de cortes solo si la medición lo justifica), siempre con una
   prueba nueva `tests/test_reparacion_<tema>.py`. Antes de entregar mide él
   mismo el impacto en lo publicado con `impacto_corpus.py --medir` (solo
   lectura: `medicion.md` con cada unidad que cambia, dentro o fuera de sus
   leyes `--objetivo`, su veredicto previo en el registro y su diff): la
   medición rápida (las leyes estatales publicadas o, en el corpus federal,
   `--muestra 40`) tras cada cambio y la completa (~30 min) una vez al final.
   Lo que cambie fuera del objetivo tiene que ser una mejora clara contra el
   PDF; si no lo logra, entrega solo la parte segura o nada. Se estrenó porque
   los primeros intentos (corrida 44093775468) arreglaban sus 4 leyes tocando
   reglas generales y el juez rechazó 70 de 74 unidades cambiadas en otras
   leyes. Esa medición es solo una ayuda: las compuertas la repiten y deciden.
4. Un paso del workflow (fuera del alcance del agente) deshace todo si el agente
   tocó algo fuera de `extractor/` y `tests/` o hizo commits, y comprueba que
   el objetivo, los PDF y el repo de datos no cambiaron. `reparar.sh compuertas` (sin secretos)
   exige: ni `verificar.py` ni `validate.py` ni pruebas existentes tocadas, una
   prueba nueva, `pytest` en verde, otra huella del extractor (si no, ninguna
   ley se reintentaría), las leyes elegidas reconstruidas con el extractor de
   partida (un `git worktree`) y con el arreglo sin unidades con problemas
   nuevas y con algún texto distinto, y `impacto_corpus.py` sobre todo lo
   publicado (fiscal, federal y estatal). Lo que cambie en lo publicado lo
   juzga `impacto.sh`; `reparar.sh publicar` solo sube el arreglo a main si
   todo quedó confirmado como mejora, y anota el intento como `publicado` o
   `descartado` con su motivo.
5. Con un arreglo publicado, el job lanza otra vigilancia: la huella del
   extractor cambió, así que `planear` reintenta las leyes excluidas
   (`reintento`) y manda a revisar otra vez lo publicado con
   `revision_pendiente` (`plan["revisar"]`). Sus bloques sin cambios reusan sus
   veredictos; solo se paga lo que cambió.

Tope: 3 intentos por ley y PDF (`extractor/reparaciones.py`). Una ley que lo
alcanza y vuelve a salir con defectos queda `excluida` con `reparacion:
{agotada: true}` y la nota en su motivo (o `revision_pendiente.agotada`), y ya
no se reintenta cuando cambia el extractor: solo con otro PDF, con el que los
intentos empiezan de cero. En las leyes estatales la huella del extractor
incluye además `estatales/*.py` y `disposicion.py`.

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
  aplaza y retoma sus veredictos de la caché de Actions. Los hallazgos de esa
  revisión (y las fallas de la auditoría) los repara un agente en el job
  `reparar` (ver «Reparación autónoma»); un arreglo a mano entra por main y
  pasa por `impacto.yml`, que mide ya también estas leyes
  (`impacto_corpus.py --estatal`). El PR va a la
  rama `reforma/leyes-estatales` y lo valida y fusiona el job `revisar`
  (`revisar-pr.yml`): todo `leyes-estatales`, leyes y constituciones, con los
  dos extractores.
- Las constituciones las sigue produciendo y vigilando constitucion-extractor
  (`{estado}/constitucion/`); este flujo no las toca, y aquel no toca las leyes.

```bash
.venv/bin/python -m extractor estatal planear --out ../leyes-estatales --plan /tmp/plan.json [--estado jalisco] [--lote 8]
# luego extraer / integrar / cerrar como en el corpus federal, con `estatal`
```

`estatal planear --revisar <estado/ley>` (input `revisar` del workflow) hace
pasar la revisión completa a una ley ya publicada, como si fuera un alta: con
hallazgos conserva su versión y queda `revision_pendiente` con el motivo. Así
se revisaron las seis leyes de la CDMX que la primera corrida publicó sin
revisión (un cierre de revisión que falló contaba como "sin hallazgos"; ya no).
Los cortes de párrafo de una ley estatal salen de la geometría del PDF, no
solo del texto plano (`articulado.cortes_geometricos`): entre párrafos hay más
espacio que entre renglones, y un renglón que no es el último de su párrafo no
deja sitio para la primera palabra del siguiente. Así, un renglón justificado
que termina en punto sigue en el siguiente, y un párrafo que cierra sin punto
se separa. Lo que la geometría no decide (un salto forzado a media oración, una
página donde `extract_text_lines` no coincide con `extract_text`) se decide por
el texto, como en las leyes federales, que no usan geometría.

Agregar una ley: una entrada `ley(...)` en el módulo de su estado (o el módulo
nuevo, con su `MEDIO`), `build` + `auditar` en cero problemas sobre su PDF, y la
vigilancia la da de alta tras su revisión completa. Si no puede quedar fiel
(p. ej. el Código de Procedimientos Civiles de la CDMX, que reinicia su
numeración en el Título Especial), va en `FUERA` con su motivo.
