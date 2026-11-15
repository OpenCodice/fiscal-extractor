#!/usr/bin/env bash
# Lanza al agente (Claude Code) para verificar la extracción contra los PDF y,
# si hay un defecto, repararlo en el código del extractor.
#
# Entorno: OUT, PDF_DIR, CLAUDE_CODE_OAUTH_TOKEN; opcionales AGENTE_DIR,
# AGENTE_MAX_TURNOS, AGENTE_MODELO. Este paso no debe recibir ningún otro
# secreto: el agente lee PDFs externos.
set -euo pipefail

EXTRACTOR="$(cd "$(dirname "$0")/../.." && pwd)"
TRABAJO="${AGENTE_DIR:-/tmp/agente}"
mkdir -p "$TRABAJO"
rm -f "$TRABAJO/veredicto.json"
cd "$EXTRACTOR"
export PYTHONPATH="$EXTRACTOR"
source scripts/agente/comun.sh

unidades_cambiadas > "$TRABAJO/cambiados.txt"
if [ ! -s "$TRABAJO/cambiados.txt" ]; then
  echo "Sin unidades de texto cambiadas: no hay nada que verificar."
  exit 0
fi

python -m extractor auditar --out "$OUT" --pdf-dir "$PDF_DIR" --json "$TRABAJO/base.json" | tail -n 1
python -m extractor verificar --sin-llm --out "$OUT" --pdf-dir "$PDF_DIR" \
  --reporte "$TRABAJO/cobertura.md" > /dev/null || true
huella_datos > "$TRABAJO/datos.sha"

python - "$TRABAJO" "$EXTRACTOR" "$OUT" "$PDF_DIR" <<'PY'
import pathlib, sys
trabajo, extractor, out, pdf_dir = sys.argv[1:5]
t = pathlib.Path(trabajo)
cambiados = (t / "cambiados.txt").read_text(encoding="utf-8").rstrip().splitlines()
if len(cambiados) > 400:
    cambiados = cambiados[:400] + [f"… y {len(cambiados) - 400} más (ver {t}/cambiados.txt)"]
brief = pathlib.Path(extractor, "scripts/agente/brief.md").read_text(encoding="utf-8")
for clave, valor in {
    "__EXTRACTOR__": extractor, "__OUT__": out, "__PDF_DIR__": pdf_dir, "__TRABAJO__": trabajo,
    "__CAMBIADOS__": "\n".join(cambiados),
    "__COBERTURA__": (t / "cobertura.md").read_text(encoding="utf-8").rstrip(),
}.items():
    brief = brief.replace(clave, valor)
(t / "brief.md").write_text(brief, encoding="utf-8")
PY

command -v claude > /dev/null || npm install -g @anthropic-ai/claude-code > /dev/null

claude -p "$(cat "$TRABAJO/brief.md")" \
  --max-turns "${AGENTE_MAX_TURNOS:-150}" \
  --permission-mode acceptEdits \
  --allowedTools Bash Read Edit Write Glob Grep \
  ${AGENTE_MODELO:+--model "$AGENTE_MODELO"} \
  > "$TRABAJO/agente.log" 2>&1 || echo "::warning::El agente terminó con error (ver $TRABAJO/agente.log)."
tail -n 40 "$TRABAJO/agente.log" || true
