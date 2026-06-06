# fiscal-extractor 🧾🇲🇽

Extrae el **corpus fiscal mexicano** (Código Fiscal de la Federación, leyes de
impuestos, reglamentos, RMF, criterios…) a archivos Markdown limpios + metadata,
versionables en el repo de datos [`fiscal-mexicano`](../fiscal-mexicano).

Mismo patrón de 3 capas que [`constitucion-extractor`](../constitucion-extractor),
generalizado de **un documento** a un **registro de documentos** (`registro.py`).
La capa 3 (metadata) nunca toca la capa 1 (texto); git es el detector de cambios.

```
1. Extracción fiel    PDF → texto por unidad        ← fuente de verdad
2. Detección          git diff                       ← lógica principal
3. Metadata derivada  fechas, índice, reformas       ← regenerable
```

## Arquitectura

```
registro.py          DOCUMENTOS[]: qué se extrae (clave, sigla, tipo, parser, url)
modelo.py            Unidad: artículo + sufijos ricos (14-A, 17-H Bis, 32-B Quáter)
parsers/articulado.py  leyes/códigos/reglamentos (port de la CPEUM, generalizado)
parsers/reglas.py    RMF — reglas jerárquicas N.N.N.N (Título→Capítulo→Sección)
parsers/criterios.py criterios normativos        ← pendiente (Fase 4)
normalize.py         cuerpo crudo → párrafos, notas de reforma en cursiva
build.py             itera el registro → <clave>/NNN.md + metadata/<clave>/*.json
```

## Uso

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Descargar un PDF y construir (texto + metadata)
curl -L -o CFF.pdf https://www.diputados.gob.mx/LeyesBiblio/pdf/CFF.pdf
.venv/bin/python -m extractor build --doc cff --pdf CFF.pdf --out ../fiscal-mexicano

# Diagnóstico de parseo (no escribe)
.venv/bin/python -m extractor stats --doc cff --pdf CFF.pdf

# Ver el corpus declarado y qué parsers están activos
.venv/bin/python -m extractor listar

# Pruebas (diseñadas para romper el parser: sufijos, mayúsculas, colisiones)
PYTHONPATH=. .venv/bin/python -m pytest tests/ -q
```

`tests/test_corpus.py` corre invariantes sobre el repo de datos ya construido
(sin colisiones de clave, sin fugas de encabezado, fechas ISO) — gate de
regresión barato.

## Estado

| Fase | Alcance | Estado |
|------|---------|--------|
| 1 | Refactor + leyes/códigos (CFF piloto) | ✅ CFF: 421 unidades, art. 1–263 |
| 2 | Resto de leyes + reglamentos | ✅ 13 docs, ~2 510 art., suite de pruebas verde |
| 3 | RMF (`parsers/reglas.py`) + vigencia anual | ✅ RMF 2026: 1208 reglas |
| 4 | Criterios normativos y no vinculativos | pendiente |
| 5 | Validador de invariantes + CI de vigilancia (DOF) | pendiente |
| — | Capa de ingesta RAG (segmentos + pasajes.jsonl) | pendiente |
