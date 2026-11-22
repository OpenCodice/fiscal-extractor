#!/usr/bin/env bash
# Lanza al agente sobre los documentos federales que la auditoría marcó con
# fallas. Antes guarda dos líneas base para las compuertas de
# cerrar-federal.sh: una copia del repo de datos y la auditoría de una muestra
# de leyes ya publicadas.
#
# Entorno: OUT, PDF_DIR, PLAN, CLAUDE_CODE_OAUTH_TOKEN; opcionales AGENTE_DIR,
# AGENTE_MAX_TURNOS, AGENTE_MODELO, MUESTRA (claves separadas por espacio).
# Este paso no debe recibir ningún otro secreto: el agente lee PDFs externos.
set -euo pipefail

EXTRACTOR="$(cd "$(dirname "$0")/../.." && pwd)"
TRABAJO="${AGENTE_DIR:-/tmp/agente}"
cd "$EXTRACTOR"
export PYTHONPATH="$EXTRACTOR"
rm -f "$TRABAJO/veredicto.json"

if [ ! -s "$TRABAJO/fallas.json" ] || [ "$(cat "$TRABAJO/fallas.json")" = "{}" ]; then
  echo "La auditoría no encontró fallas: el agente no interviene."
  exit 0
fi

rsync -a --delete --exclude .git "$OUT/" "$TRABAJO/datos-antes/"
cp "$TRABAJO/resultados.json" "$TRABAJO/resultados-antes.json"

# Muestra de regresión: leyes ya publicadas que hoy salen limpias.
MUESTRA="${MUESTRA:-lft lgs cpf lamp cff lisr ladua ccf}"
python - "$OUT/fuentes.json" "$TRABAJO/muestra-pdfs" $MUESTRA <<'PY'
import json, pathlib, sys
from extractor.fuentes import descargar
fuentes, destino, *claves = sys.argv[1:]
docs = {d["clave"]: d for d in json.load(open(fuentes))["documentos"]} \
    if pathlib.Path(fuentes).exists() else {}
pathlib.Path(destino).mkdir(parents=True, exist_ok=True)
for c in claves:
    d = docs.get(c)
    if d and d.get("estado") == "incluida":
        try:
            descargar(d["url"], f"{destino}/{c}.pdf")
        except Exception as e:  # noqa: BLE001 — la muestra es de mejor esfuerzo
            print(f"· muestra: {c} sin descargar ({e})")
PY
bash "$EXTRACTOR/scripts/agente/muestra-federal.sh" "$TRABAJO/muestra-base.json"

python - "$TRABAJO" "$EXTRACTOR" "$OUT" "$PDF_DIR" "$PLAN" <<'PY'
import json, pathlib, sys
trabajo, extractor, out, pdf_dir, plan = sys.argv[1:6]
t = pathlib.Path(trabajo)
fallas = json.loads((t / "fallas.json").read_text(encoding="utf-8"))
lineas = []
for clave, r in fallas.items():
    lineas.append(f"{clave}: {r.get('unidades', 0)} unidades")
    if r.get("error"):
        lineas.append(f"  error: {r['error']}")
    for inv in r.get("invariantes", [])[:4]:
        lineas.append(f"  invariante: {inv[:200]}")
    probs = r.get("problemas") or {}
    if probs:
        lineas.append(f"  {len(probs)} unidades con problemas de cobertura:")
    for ref, ps in list(probs.items())[:6]:
        p = ps[0]
        lineas.append(f"    {ref} {p.get('tipo')}: «{str(p.get('fragmento', ''))[:160]}»")
brief = pathlib.Path(extractor, "scripts/agente/brief-federal.md").read_text(encoding="utf-8")
for k, v in {"__EXTRACTOR__": extractor, "__OUT__": out, "__PDF_DIR__": pdf_dir,
             "__TRABAJO__": trabajo, "__PLAN__": plan,
             "__FALLAS__": "\n".join(lineas)}.items():
    brief = brief.replace(k, v)
(t / "brief.md").write_text(brief, encoding="utf-8")
PY

command -v claude > /dev/null || npm install -g @anthropic-ai/claude-code > /dev/null

source scripts/agente/sesion.sh
documentos="$(python3 -c 'import json, sys; print(" ".join(json.load(open(sys.argv[1], encoding="utf-8"))))' \
  "$TRABAJO/fallas.json" 2>/dev/null || true)"
sesion_agente auditoria-federal "$TRABAJO/uso.jsonl" "$TRABAJO/brief.md" "$documentos" \
  --max-turns "${AGENTE_MAX_TURNOS:-200}" \
  --permission-mode acceptEdits \
  --allowedTools Bash Read Edit Write Glob Grep \
  > "$TRABAJO/agente.log" 2>&1 || echo "::warning::El agente terminó con error (ver $TRABAJO/agente.log)."
tail -n 40 "$TRABAJO/agente.log" || true
