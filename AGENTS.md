# fiscal-extractor — guía para agentes

Convierte los PDF oficiales de la legislación fiscal mexicana en un archivo
Markdown por unidad (artículo, regla, criterio, ficha) más metadata derivada.
Es código; los datos viven en `fiscal-mexicano`, que nunca se edita a mano: si
una unidad está mal, se corrige aquí.

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
  literal en el PDF y sin texto omitido entre párrafos) y `auditar`. Guarda el
  texto por página junto al PDF (`*.paginas.json`) porque extraerlo es lo lento.
- `scripts/agente/` — el agente de CI: `brief.md` (su encargo), `correr.sh`
  (lo lanza) y `cerrar.sh` (compuertas deterministas, publica su arreglo).

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

`auditar` revisa todas las unidades; `verificar` solo las que difieren de
`HEAD` en el repo de datos. `verificar` sin `--sin-llm` añade una revisión por
API de OpenAI; es una herramienta manual opcional y la CI no la usa.

## Al cambiar un parser

- La compuerta es `auditar`: tras tu cambio no puede listar unidades que antes
  no listaba. Un parser sirve a varios documentos, así que audita todos los que
  lo usan, no solo el que estás arreglando.
- Prefiere un patrón general a un caso especial por unidad, y agrega una prueba
  de regresión en `tests/`.
- Un cambio aquí modifica texto ya publicado en la siguiente vigilancia. Es lo
  esperado; ese PR sale titulado como corrección de extracción.
- No relajes `verificar.py` ni pruebas existentes para que algo pase.

## Defecto conocido

`auditar` todavía lista unas decenas de unidades de leyes (CFF, LFD, LFPCA,
RCFF, LCF, RLISR) donde el nombre del Título o Capítulo siguiente quedó pegado
al final del artículo anterior, por ejemplo `cff/091-d`:
"(Se deroga) De los delitos fiscales". Ocurre cuando el encabezado viene en
mayúsculas y su nombre no. `constitucion-extractor` ya resolvió el mismo caso
en `parse.py`.

## Agregar un documento

Una entrada en `extractor/registro.py`. Las leyes y reglamentos de la Cámara de
Diputados usan `_ley(...)` y el parser `articulado` sin más código. Después:
`build`, `validar` y `auditar` hasta dejarlo en cero problemas.
