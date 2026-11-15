#!/usr/bin/env bash
# Reconstruye y audita la muestra de regresión (leyes ya publicadas, PDFs en
# $TRABAJO/muestra-pdfs) con el extractor tal como está. Escribe la auditoría
# en $1. Entorno: OUT; opcional AGENTE_DIR.
set -uo pipefail
EXTRACTOR="$(cd "$(dirname "$0")/../.." && pwd)"
TRABAJO="${AGENTE_DIR:-/tmp/agente}"
cd "$EXTRACTOR"
export PYTHONPATH="$EXTRACTOR"
if ! ls "$TRABAJO"/muestra-pdfs/*.pdf > /dev/null 2>&1; then
  echo '{"total": 0, "con_problemas": {}}' > "$1"
  exit 0
fi
rm -rf "$TRABAJO/muestra-datos" && mkdir -p "$TRABAJO/muestra-datos"
for pdf in "$TRABAJO"/muestra-pdfs/*.pdf; do
  [ -e "$pdf" ] || continue
  python -m extractor --registro "$OUT/fuentes.json" build --doc "$(basename "$pdf" .pdf)" \
    --pdf "$pdf" --out "$TRABAJO/muestra-datos" --sin-pasajes > /dev/null
done
python -m extractor --registro "$OUT/fuentes.json" auditar --out "$TRABAJO/muestra-datos" \
  --pdf-dir "$TRABAJO/muestra-pdfs" --json "$1" | head -n 1
