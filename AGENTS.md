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
- `.github/workflows/vigilar-leyes-estatales.yml` — su vigilancia, y
  `expandir-estatales.yml` (con `scripts/expansion.py`,
  `scripts/agente/expandir.sh`, `brief-expansion.md`,
  `brief-expansion-codigo.md` y `brief-redeclaracion.md`), la ronda que suma
  estados y redeclara las leyes de FUERA que no se descargan (ver «Ronda de
  expansión»).
- `.github/workflows/vigilar-fiscal.yml` y `vigilar-federal.yml` — la vigilancia
  de `fiscal-mexicano` y `leyes-federales`. Viven aquí, no en los repos de
  datos, para que el historial de esos repos solo tenga cambios de texto legal.
  Las lanza cada lunes el supervisor (`OpenCodice/supervisor`; ver
  «Encadenamiento y salud de las corridas») y abren en el repo de datos un PR
  con un commit por documento (`scripts/commits_por_documento.py`), que su job
  `revisar` valida y fusiona con rebase.
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
  aplaza). Todos lanzan al agente por `sesion.sh` (`sesion_agente`), que deja
  una línea por sesión en el `uso.jsonl` de su carpeta de trabajo (ver «Uso
  del agente»).
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
  las correcciones con el agente. Falla si quedó algo sin confirmar o si la
  medición no terminó (cualquier código de `impacto_corpus.py` que no sea 0 o
  1).

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

## Uso del agente

Cada sesión (`claude -p`) pasa por `sesion_agente` (`scripts/agente/sesion.sh`),
que la lanza con `--output-format json`, deja en el log el mismo texto final
de siempre y agrega una línea a `uso.jsonl` (`scripts/uso.py registrar`):
`paso` (`reparacion`, `impacto`, `revision-alta`, `verificacion`,
`auditoria-federal`, `expansion`, `redeclaracion`, `expansion-codigo`),
`documentos`, `grupo`, `modelo`, tokens de entrada, salida y caché, `costo_usd`
(el equivalente que calcula el CLI), `turnos`, duración y código de salida. Es
telemetría: ninguna compuerta la lee, y si el uso no se puede leer la línea se
anota con null. Una sesión que el límite de tiempo del paso mata no deja línea.

Dónde queda: `uso.jsonl` en la carpeta de trabajo de cada script
(`/tmp/agente/`, `/tmp/agente/reparacion/`, la de `IMPACTO`, `/tmp/expansion/`
y `/tmp/expansion/codigo/`). Los jobs `reparar`, `ronda` y `codigo` lo suben
dentro de su artefacto; `cerrar`, `vigilar` (fiscal) e `impacto.yml`, que
siguen lanzando sesiones después de guardar su trabajo, en uno propio
(`uso-cerrar`, `uso-vigilar`, `uso`). El paso «Uso del agente» de cada job
escribe la tabla por paso en su resumen (`uso.py resumir <carpeta o archivo>`).
`impacto.sh` depende de `sesion.sh` y `uso.py`: en constitucion-extractor van
los tres.

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
   Cada ley lleva el motivo de sus intentos descartados con ese mismo PDF
   (`descartes`, los últimos 3, recortados), que el agente recibe junto a sus
   hallazgos para no entregar otra vez el mismo arreglo.
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
   Antes de entregar corre también `reparar.sh comprobar`: las comprobaciones
   del paso 4 que no dependen de lo publicado (alcance, pruebas existentes y
   compuerta intactas, prueba nueva, `pytest`, otra huella y sus leyes
   reconstruidas sin unidades con problemas nuevas), con el mismo código que
   las compuertas (la función `comprobaciones` de `reparar.sh`), sobre sus PDF
   y en `reparacion/comprobacion/`. Solo informa (`PASA` / `NO PASA: motivo`).
   Mientras dura la sesión, las pruebas que ya existían, `verificar.py` y
   `validate.py` no tienen permiso de escritura (se restaura al terminar, con
   un `trap`, y otra vez al empezar las compuertas). El agente corre con el
   mismo usuario y podría devolvérselo: es un aviso inmediato, no un cerco.
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
5. Con un arreglo publicado, el job pide otra vigilancia (salida
   `pedir_vigilancia`, que lanza el supervisor): la huella del extractor
   cambió, así que `planear` reintenta las leyes excluidas
   (`reintento`) y manda a revisar otra vez lo publicado con
   `revision_pendiente` (`plan["revisar"]`). Sus bloques sin cambios reusan sus
   veredictos; solo se paga lo que cambió.

**Las leyes estatales en `FUERA`** (las que la ronda de expansión o su agente
dejaron fuera porque su extracción no quedaba fiel) tampoco esperan a nadie:
la vigilancia nunca las intenta, así que el job `reparar`, antes del agente y
con el extractor de main, las descarga, construye y audita (`reparacion.py
fuera`, hasta 8 por corrida, con caché por PDF y huella del extractor; una que
no se puede descargar se anota con su causa y no gasta intento: si es del
extractor, no de la red, la redeclara la ronda de expansión, ver
«Redeclaración de FUERA»). Las que fallan entran al
`objetivo` como cualquier otra (`--fuera`, origen `fuera`, con el mismo tope
por ley y PDF). Las que quedan con build y auditar limpios —ya con el extractor
de main, o reconstruidas por las compuertas con el arreglo recién publicado—
pasan solas a `LEYES`: un paso determinista (`reparar.sh promover`, que corre
`reparacion.py promover` en un clon limpio de main) agrega al final de su
módulo un bloque `_A_LEYES` que las mueve, sin tocar lo demás, con `pytest`
en verde, y el job pide la vigilancia de su estado (`pedir_altas`), que las da
de alta tras su revisión completa (para `planear` son un `reintento`). Una ley
que ningún arreglo puede sumar (el Código de Procedimientos Civiles de la CDMX, que
repite su numeración) va además en `FUERA_POR_DISENO` de su módulo y la
reparación no la toca. La medición de FUERA se comprueba por sha256 después
del agente: si cambió, no se promueve nada con ella.

Tope: 3 intentos por ley y PDF (`extractor/reparaciones.py`). Una ley que lo
alcanza y vuelve a salir con defectos queda `excluida` con `reparacion:
{agotada: true}` y la nota en su motivo (o `revision_pendiente.agotada`), y ya
no se reintenta cuando cambia el extractor: solo con otro PDF, con el que los
intentos empiezan de cero. En las leyes estatales la huella del extractor
incluye además `estatales/*.py` y `disposicion.py`.

## Encadenamiento y salud de las corridas

**Ningún workflow lanza a otro ni a sí mismo.** Cada corrida hace una unidad de
trabajo, declara qué tiene que correr después y termina; el único que hace
`workflow_dispatch` es el supervisor (`OpenCodice/supervisor`, cada 15
minutos), que también lleva los horarios (`cadenas.toml`), los reintentos y el
despliegue de la web. Las cuatro corridas encadenadas (`vigilar-fiscal`,
`vigilar-federal`, `vigilar-leyes-estatales`, `expandir-estatales`) cumplen su
contrato:

- Input `origen` (el supervisor lanza con `origen=supervisor`; vacío = a mano)
  y `run-name` con todos los inputs como `clave=[valor]`: la API no devuelve
  los inputs de un dispatch, el título de la corrida sí.
- **Peticiones.** Un paso que necesita que corra algo después escribe en su
  salida `pedir` una petición en JSON, `{"workflow": "<archivo.yml>",
  "inputs": {…}}` (valores siempre cadenas, sin `origen`), y su job la expone
  como salida `pedir_<algo>`. Significa «después de esta corrida tiene que
  empezar una de ese workflow que abarque esos inputs»: el supervisor la da
  por atendida con cualquier corrida posterior que la abarque (una vigilancia
  completa abarca una de `estados=jalisco`), así que pedir de más no duplica
  trabajo, y él se encarga de no perder nada en la cola de cada grupo de
  concurrency. Si el valor sale de una variable, se construye con `jq -cn
  --arg`. Las que hay:

  | Workflow, job | Salida | Pide | Cuándo |
  |---|---|---|---|
  | `vigilar-federal`, `reparar` | `pedir_vigilancia` | `vigilar-federal.yml` | publicó un arreglo del extractor |
  | `vigilar-leyes-estatales`, `reparar` | `pedir_vigilancia` | `vigilar-leyes-estatales.yml` (completa) | publicó un arreglo del extractor |
  | | `pedir_altas` | `vigilar-leyes-estatales.yml` `estados=<promovidos>` | pasó leyes de `FUERA` a `LEYES` y no pidió la completa |
  | | `pedir_redeclaracion` | `expandir-estatales.yml` `redeclarar=<estado>` | leyes de `FUERA` que no se descargan por algo del extractor |
  | `expandir-estatales`, `ronda` | `pedir_altas` | `vigilar-leyes-estatales.yml` `estados=<con altas pendientes>` | quedan leyes declaradas sin alta |
  | | `pedir_vigilancia` | `vigilar-leyes-estatales.yml` `estados=<estado>` | publicó el módulo (o la redeclaración) |
  | | `pedir_ronda` | `expandir-estatales.yml` `estado=<estado>` | agregó su dominio a egress-mx |
  | `expandir-estatales`, `codigo` | `pedir_ronda` | `expandir-estatales.yml` `estado=<estado>` o `redeclarar=<estado>` | publicó la opción que faltaba |

- Último job `estado`, que depende de todos los demás y corre siempre. Su
  nombre dice si quedó otra tanda con los mismos inputs
  (`estado pendiente=[true]`), y sube el artefacto `cadena` (`cadena.json`:
  el resultado y las salidas de cada job, `toJSON(needs)`), de donde el
  supervisor lee las peticiones. Una corrida sin job `estado` no terminó.
- `pendiente=[true]` en federal y leyes estatales: `cerrar` terminó bien y su
  salida `continuar` es `true`, es decir, «queda trabajo y esta corrida
  avanzó»: abrió un PR o, sin PR, dejó veredictos nuevos de una revisión que
  no cupo (leyes estatales) o el agente reparó el extractor (federal). Sin
  avance no se declara: otra corrida repetiría lo mismo. La tanda siguiente
  no necesita esperar la fusión del PR: `revisar` es parte de la corrida y
  `planear` espera al PR anterior. En `vigilar-fiscal` y en la ronda de
  expansión, siempre `false`.
- Una fuente caída pone en rojo el job `fuentes`, no `cerrar`: la corrida
  queda fallida y el supervisor la reintenta, pero `pendiente` y `reparar` no
  dependen de la ley que no respondió.
- Las fallas son del supervisor: reintenta con esperas y deja un issue por
  huella en su repo. Un job que agota su `timeout-minutes` termina
  `cancelled` sin que la corrida se haya cancelado, y cuenta como falla. La
  web tampoco se avisa desde aquí: el supervisor lanza su despliegue cuando
  los datos cambian.
- Tiempos: cada job tiene `timeout-minutes` (máximo 355) y ningún paso uno
  mayor que el de su job. Los pasos de agente son secuenciales y casi nunca
  agotan todos su límite, así que su suma puede pasar del tiempo del job.
- Las cachés que cuestan trabajo pagado (veredictos de la revisión, medición
  de FUERA, PDF de lo publicado) se restauran con `actions/cache/restore` y
  se guardan con `actions/cache/save` e `if: always()` justo después del paso
  que las llena, no al terminar el job.
- En `reparar`, los pasos que piden la vigilancia tras publicar un arreglo o
  promover leyes llevan `!cancelled()`: lo que ya está en main se reintenta
  aunque otro paso del job haya fallado. Si el job agota su tiempo y la
  petición se pierde, el supervisor reintenta igual al ver el extractor nuevo.
- Ningún job tiene `actions: write`; el que consulta corridas (`ronda`, para
  saber si la cadena terminó) tiene `actions: read`.
- `tests.yml` (job `infra`) corre `actionlint` (con `.github/actionlint.yaml`)
  y el lint de workflows del supervisor. `tests/test_infra_sin_lanzamientos.py`
  falla si reaparece un lanzamiento en `.github/` o `scripts/` (`gh workflow
  run`, `gh run rerun`, un `dispatches` de la API) y comprueba, leyendo los
  YAML, que cada salida `pedir*` sale de un paso que la escribe, que su JSON
  es válido y nombra un workflow y unos inputs que existen, y que `estado`
  depende de todos los jobs y sube `cadena`.

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
numeración en el Título Especial), va en `FUERA` con su motivo y, si ningún
arreglo del extractor la puede sumar, también en `FUERA_POR_DISENO`; las demás
de `FUERA` las retoma la reparación autónoma.

## Ronda de expansión

Suma un estado al corpus de leyes estatales por semana, sin que nadie trabaje
en una computadora: `expandir-estatales.yml` (cada miércoles, lanzada por el
supervisor; a mano con `gh workflow run expandir-estatales.yml [-f
estado=<slug>]`). La parte determinista vive en `scripts/expansion.py`.

- **La lista:** `extractor/estatales/pendientes.json`, los estados sin módulo
  en el orden en que se suman, cada uno con su `situacion` (`pendiente`,
  `publicado`, `egress`, `agotado`), sus `intentos`, el `motivo` del último y
  una `pista` (de dónde sale su constitución). Tope: 3 intentos por estado
  (`tope_intentos`) y, aparte, 2 arreglos de código (`intentos_codigo`, ver
  «Arreglo de código»). La escribe solo la ronda (no es un `*.py`: no entra en
  la huella del extractor, y `impacto.yml` la ignora).
- **Solo cuando la cadena anterior terminó:** ninguna `vigilar-leyes-estatales`
  en curso o en cola, ningún PR suyo abierto y ninguna ley declarada sin alta
  cuyo PDF responda (`expansion.py listo`). Un estado por ronda. El input
  `sin_esperar` (solo a mano, para probar) se salta esta condición.
  - Cuándo lanzar la ronda lo decide el supervisor (`espera_libre` en su
    `cadenas.toml`): no la lanza por horario mientras la cadena siga ocupada,
    y la lanza en el primer tic en que quede libre. El paso «¿Terminó la
    cadena anterior?» es la salvaguarda: si aun así la encuentra ocupada, la
    corrida no empieza un estado y termina en verde, sin esperar ni declarar
    nada pendiente. Una consulta que falla hace fallar el paso.
  - Si la cadena terminó pero quedan altas (una tanda que no continuó), la
    ronda pide la vigilancia de esos estados (`pedir_altas`) y no empieza
    otro: el estado nuevo espera a la ronda de la semana siguiente.
- **Elegir y contar el intento** (`expansion.py elegir`): el primer `pendiente`
  bajo el tope (o el del input `estado`), primero los que nunca se agotaron.
  Un `egress` cuyo dominio ya aparece en la lista de egress-mx
  (`egress-mx/permitidos.json` de main de constitucion-extractor, leída por la
  API para no ver una copia vieja) vuelve a `pendiente`. El intento se publica
  en main antes del agente (`expandir.sh intento`): uno que se cae también
  cuenta.
- **El agente** (`expandir.sh agente`, `brief-expansion.md`; solo
  `CLAUDE_CODE_OAUTH_TOKEN`) encuentra el portal oficial de leyes vigentes
  (WebSearch/WebFetch para buscar, `curl` desde el runner para descargar) y
  escribe `extractor/estatales/<estado>.py` (`MEDIO`, 10 a 20 `LEYES` —códigos
  y leyes orgánicas, sin leyes de ingresos ni presupuestos—, `FUERA` con su
  motivo) y `tests/test_estatal_<estado>.py`, con build y auditar en cero
  sobre cada PDF. Solo usa las opciones de `ley()`: el parser no lo toca (lo
  que no quede fiel va a `FUERA`; lo arreglará `reparar` en otra ocasión). Si
  el sitio rechaza IP extranjeras y su dominio está en egress-mx, descarga por
  una puerta local (`scripts/agente/proxy_mx.py`, que tiene el token; el agente
  no) y declara esas leyes con `via="mx"`; si no está, entrega `egress` (ver
  «Egress sin una persona»). Si al extractor le falta una opción para
  encontrar o descargar los PDF (no del parser), entrega `codigo` con lo que
  falta (`falta`, `ejemplos`) y su borrador del módulo (ver «Arreglo de
  código»).
- **Cerco** (un paso del workflow, sin secretos): solo cuentan dos archivos
  nuevos, el módulo y sus pruebas. Si hizo commits o tocó cualquier otra cosa
  (los demás módulos, `__init__.py`, el parser, `pendientes.json`), se deshace
  todo y el intento falla.
- **Compuertas:** `pytest` entero; `expansion.py registro` importa el módulo
  sin secretos y comprueba su forma (claves del estado, `MEDIO`, `FUERA`, URL);
  `expansion.py descargar` baja cada PDF desde un clon limpio del extractor de
  partida con `python -I -S` (con `EGRESS_MX_TOKEN`, sin importar código del
  agente: lee su registro como datos); `expansion.py construir` hace build y
  auditar de cada ley y `fuera` agrega al final del módulo un bloque
  `_FUERA_RONDA` que pasa a `FUERA` las que no quedaron en cero (con su motivo);
  al menos una tiene que quedar limpia y las pruebas pasar otra vez. Por
  último, `impacto_corpus.py` reconstruye todo lo publicado con el módulo: sin
  ningún cambio, pasa; si hay alguno (una corrección de main aún sin
  confirmar), tiene que ser idéntico al que da el extractor de partida
  (`expansion.py impacto-igual`, sobre `cambios.json`). Una descarga que falla
  es error de la ronda, no de la ley: no se publica nada.
- **Publicar** (`expandir.sh publicar`, desde un clon limpio de main): copia
  solo el módulo y sus pruebas, anota el estado `publicado` y sube un commit
  «Leyes estatales: <Estado> (ronda de expansión)». Después pide
  `vigilar-leyes-estatales.yml` con `estados=<estado>` (`pedir_vigilancia`):
  su cadena da de alta por
  tandas tras la revisión completa, y `reparar` arregla lo que falle.
- **Falla cerrada:** cualquier otro final (sin veredicto, una compuerta, un
  error) anota el intento como fallido con su motivo, y el estado se reintenta
  la ronda siguiente; al tope queda `agotado`, con la fecha y la huella de lo
  que el agente puede usar del extractor (`expansion.huella_expansion`: el
  parser, `build`/`normalize`/`verificar`, `fuentes.py`, `registro.py`,
  `estatales/__init__.py`; no los módulos de los estados, que cambian cada
  semana). Nada se asigna a una persona.
- **Nada queda agotado para siempre** (`expansion.revive`): un `agotado` vuelve
  a la cola cuando esa huella cambió y pasaron 4 semanas, o tras 12 semanas sin
  cambios. Vuelve con un solo intento más (y sus intentos de código de nuevo),
  detrás de los estados que nunca se agotaron: uno sin salida cuesta a lo más
  una sesión cada 4 semanas, no una por semana.
- **Egress sin una persona:** con `egress`, un paso determinista (no el
  agente) comprueba que el dominio de verdad no responde desde Actions (dos
  veces) y, si es oficial, lo agrega a `egress-mx/permitidos.json` de
  constitucion-extractor con `PR_TOKEN` (`expandir.sh egress`, `expansion.py
  egress-agregar`); el Worker lee esa lista de main cada pocos minutos, sin
  desplegarse. Regla de dominio oficial (`expansion.dominio_oficial`):
  termina en `.gob.mx` (NIC México solo lo asigna a dependencias de
  gobierno), o en `.mx` con el mismo dominio registrable que un host ya
  oficial (el de la constitución del estado, su `pista`, o uno de la lista).
  Lo demás no se agrega solo y el intento cuenta como fallido (el Worker,
  además, solo acepta de ese archivo dominios `.mx`). Agregado, el intento no
  cuenta, el estado vuelve a `pendiente` y se pide otra ronda para él
  (`pedir_ronda`) cuando la lista nueva ya se ve en raw.githubusercontent.com
  (`expandir.sh egress` la espera antes de volver).
- **Ensayo** (solo a mano): `-f ensayo=true` hace todo sin subir nada (ni el
  intento, ni el módulo, ni un arreglo, ni egress-mx) ni pedir otra corrida;
  `-f simular=codigo|egress -f simular_texto=…` sustituye al agente de la ronda
  por ese veredicto (implica ensayo), para probar el job `codigo` o el paso de
  egress sin publicar nada falso.

### Arreglo de código

Cuando la ronda entrega `codigo` (al extractor le falta una opción para
encontrar o descargar los PDF del estado, como le faltó `consulta` a Nuevo
León), el job `codigo` de `expandir-estatales.yml` la agrega sin una persona,
con la misma forma que `reparar`:

1. El intento de código se cuenta en `pendientes.json` antes del agente
   (`expansion.py anotar --resultado codigo`, que publica el paso que anota la
   ronda); con 2 ya gastados el veredicto cuenta como fallido.
2. Con el extractor de partida, desde un clon limpio (`python -I -S`, con
   `EGRESS_MX_TOKEN`): `expansion.py declaraciones` deja la declaración
   (`a_dict` sin campos vacíos) y la URL vigente de todo lo declarado (el
   corpus fiscal, las leyes estatales y sus FUERA, y los `fuentes.json` de
   leyes-estatales y leyes-federales), con las páginas índice de las que sale;
   y `impacto_corpus.py --solo-pdfs` llena la caché de PDF.
3. El agente (`expandir.sh codigo-agente`, `brief-expansion-codigo.md`; solo
   `CLAUDE_CODE_OAUTH_TOKEN`), con lo que dijo el de la ronda y su borrador
   como ejemplo, agrega una opción **opcional por ley** (un campo de
   `Documento` cuyo valor por omisión deja todo igual, su paso por `ley()`,
   `a_dict`, `de_dict` y su uso en `fuentes.py`) y una prueba nueva
   `tests/test_expansion_<tema>.py`. Solo puede tocar `extractor/fuentes.py`,
   `extractor/registro.py`, `extractor/estatales/__init__.py` y esa prueba: el
   parser es de `reparar`.
4. Cerco (un paso del workflow): commits u otro archivo tocado, o lo que dejó
   el extractor de partida cambiado (por sha256), y se deshace todo.
5. Compuertas, sin secretos (`expandir.sh codigo-compuertas`): algo cambió,
   prueba nueva, `pytest` entero; `expansion.py declaraciones --leer-de`
   resuelve todo con el arreglo sobre las mismas páginas, sin red, y
   `declaraciones-iguales` (desde el clon limpio) exige que ninguna
   declaración ni URL vigente cambie; `impacto_corpus.py` sobre todo lo
   publicado sin cambios, o idénticos a los del extractor de partida
   (`expandir.sh impacto`, la misma compuerta que el módulo de la ronda).
6. Si pasa, `expandir.sh codigo-publicar` aplica el parche sobre un clon
   limpio de main y lo sube en un commit «Leyes estatales: <opción> (ronda de
   expansión)» con el estado de vuelta en `pendiente` y su intento devuelto
   (el que pidió el código no cuenta: el agente hizo bien en pedirlo), y el
   job pide otra ronda para ese estado (`pedir_ronda`). Decidido así, y no reintentar dentro
   del mismo job, para que el reintento tenga su propio tiempo y pase por todo
   lo de una ronda normal. Si no, anota el descarte con su motivo y el intento
   sí cuenta. Al llegar a main, `impacto.yml` lo mide otra vez como cualquier
   cambio del extractor.

### Redeclaración de FUERA

Una ley en `FUERA` de un estado ya publicado que no se puede ni descargar no
la arregla `reparar` (no hay PDF que reparar). Si la causa está en el
extractor (`reparacion.causa_fuente`: un href que `http.client` rechaza, como
el espacio de `….pdf?2026-03- 9` en Nuevo León; un patrón que ya no casa; un
400 del servidor) y no en la red (caído, lento, un 404, una página de error),
el job `reparar` de `vigilar-leyes-estatales.yml`, tras medir FUERA, pide
`expandir-estatales.yml` con `redeclarar=<estado>` (`pedir_redeclaracion`;
`expansion.py redeclarar-pendiente` elige un estado por corrida). Es la ronda de expansión sobre el módulo que ya existe:

1. Con el extractor de main y `EGRESS_MX_TOKEN`, antes del agente:
   `reparacion.py fuera --estado E --solo-fuente` vuelve a intentar la
   descarga y `expansion.py registro` deja el registro del módulo como datos
   (la referencia del cerco, protegida por sha256 durante el agente).
   `expansion.py elegir --redeclarar E` cuenta el intento en el registro
   `redeclaracion` del estado en `pendientes.json` (sigue `publicado`). Tope:
   2 rondas (`tope_redeclaracion`) y 2 arreglos de código por **firma** de la
   falla (qué leyes y qué excepción): la misma falla no se intenta más; una
   distinta empieza de cero.
2. El agente (`brief-redeclaracion.md`) solo puede agregar opciones de `ley()`
   a esas entradas de FUERA, sin pasarlas a `LEYES` (la promoción es de
   `reparar.sh promover`). Si falta la opción, entrega `codigo` y el mismo job
   `codigo` de «Arreglo de código» la agrega; al publicarla pide otra vez la
   redeclaración (`redeclarar=`), con el intento devuelto.
3. Cerco: solo cambia el módulo. Compuertas: `pytest`, `expansion.py
   registro` y `redeclaracion-cerco`: `MEDIO`, cada entrada de `LEYES` (y su
   orden), las claves de `FUERA` y de `FUERA_POR_DISENO` y las entradas de
   FUERA que no son del objetivo, idénticas por `a_dict`; en las del objetivo
   cada campo que ya tenían queda igual (dar valor a uno vacío es agregar una
   opción). Cada ley que cambió se descarga desde un clon limpio
   (`expansion.py descargar`, `python -I -S`) y el impacto en lo publicado es
   nulo (`expandir.sh impacto`).
4. `expandir.sh publicar` aplica el cambio del agente al módulo de main como
   parche (main pudo cambiar el módulo: un bloque `_A_LEYES`), corre `pytest`
   otra vez y sube «Leyes estatales: <Estado>, opciones nuevas para leyes en
   FUERA»; después pide la vigilancia del estado, cuyo `reparar` las descarga,
   construye y audita: limpias pasan a `LEYES`, con defectos entran al
   `objetivo` de la reparación.

Un módulo nuevo cambia la huella del extractor de todas las leyes estatales
(incluye `estatales/*.py`): la siguiente vigilancia completa las reconstruye
(sin cambios de texto: lo garantiza la compuerta de impacto) y reintenta las
excluidas, cuyos bloques sin cambios reusan sus veredictos.

