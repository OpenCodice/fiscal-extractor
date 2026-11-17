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

# Documentos nuevos: se revisan enteros, por bloques (scripts/revision.py), no
# por sus unidades cambiadas.
python3 - "$OUT" > "$TRABAJO/altas.txt" <<'PY'
import pathlib, subprocess, sys
out = pathlib.Path(sys.argv[1])
for idx in sorted(out.glob("metadata/*/articulos.json")):
    doc = idx.parent.name
    r = subprocess.run(["git", "-C", str(out), "cat-file", "-e", f"HEAD:metadata/{doc}/articulos.json"],
                       capture_output=True)
    if r.returncode != 0:
        print(doc)
PY
unidades_cambiadas | { if [ -s "$TRABAJO/altas.txt" ]; then
  grep -vE "^.. \"?($(paste -sd'|' "$TRABAJO/altas.txt"))/" || true; else cat; fi; } > "$TRABAJO/cambiados.txt"
if [ ! -s "$TRABAJO/cambiados.txt" ] && [ ! -s "$TRABAJO/altas.txt" ]; then
  echo "Sin unidades de texto cambiadas: no hay nada que verificar."
  exit 0
fi

python -m extractor auditar --out "$OUT" --pdf-dir "$PDF_DIR" --json "$TRABAJO/base.json" | tail -n 1
python -m extractor verificar --sin-llm --out "$OUT" --pdf-dir "$PDF_DIR" \
  --reporte "$TRABAJO/cobertura.md" > /dev/null || true

command -v claude > /dev/null || npm install -g @anthropic-ai/claude-code > /dev/null

lanzar() {
  claude -p "$(cat "$1")" \
    --max-turns "${AGENTE_MAX_TURNOS:-150}" \
    --permission-mode acceptEdits \
    --allowedTools Bash Read Edit Write Glob Grep \
    ${AGENTE_MODELO:+--model "$AGENTE_MODELO"} \
    >> "$TRABAJO/agente.log" 2>&1 || echo "::warning::El agente terminó con error (ver $TRABAJO/agente.log)."
}

RAIZ="$(git -C "$OUT" rev-parse --show-toplevel)"
while IFS= read -r doc; do
  [ -n "$doc" ] || continue
  REV="$TRABAJO/revision/$doc"
  mkdir -p "$REV"
  previa="$(python scripts/revision.py previa --documento "$doc" --pdf "$PDF_DIR/$doc.pdf")"
  if [ -n "$previa" ] && [ "$(echo "$previa" | python3 -c 'import json,sys; print(json.load(sys.stdin)["resultado"])')" != fiel ]; then
    echo "$doc: revisión completa anterior con el mismo PDF y extractor: $previa"
    echo "$previa" > "$REV/previa.json"
    continue
  fi
  PLANEAR="python scripts/revision.py planear --repo $RAIZ --documento $doc --pdf $PDF_DIR/$doc.pdf --trabajo $REV"
  BUILD="python -m extractor build --doc $doc --pdf-dir $PDF_DIR --out $OUT"
  for n in $(seq 1 "${REVISION_SESIONES:-8}"); do
    $PLANEAR
    python3 scripts/agente/brief_revision.py "$REV" "$n" "${REVISION_POR_SESION:-8}" \
      __EXTRACTOR__="$EXTRACTOR" __OUT__="$OUT" __PDF__="$PDF_DIR/$doc.pdf" __BUILD__="$BUILD" \
      __PLANEAR__="$PLANEAR" __TRABAJO_AGENTE__="$TRABAJO" __DOCUMENTO__="$doc"
    [ -s "$REV/brief.md" ] || break
    lanzar "$REV/brief.md"
  done
done < "$TRABAJO/altas.txt"
huella_datos > "$TRABAJO/datos.sha"
[ -s "$TRABAJO/cambiados.txt" ] || exit 0

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

lanzar "$TRABAJO/brief.md"
tail -n 40 "$TRABAJO/agente.log" || true
