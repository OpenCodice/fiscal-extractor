#!/usr/bin/env bash
# Revisión completa, por bloques, de las leyes federales nuevas que pasaron las
# compuertas deterministas (scripts/revision.py). Dos fases:
#
#   revision-federal.sh revisar — con CLAUDE_CODE_OAUTH_TOKEN y nada más. El
#     agente revisa cada alta contra su PDF; aquí no repara el extractor (ya
#     pasó sus compuertas en esta corrida): lo que encuentre deja el alta
#     fuera, con su motivo.
#   revision-federal.sh cerrar — determinista. Anota en resultados.json el
#     motivo de cada alta que no quedó sin hallazgos (`revision`, que
#     `federal cerrar` excluye) y aplaza las que no cupieron en la corrida
#     (`aplazada`). Con EXTRACTOR_TOKEN publica el registro de revisiones.
#
# Entorno: OUT, PDF_DIR, PLAN; opcionales AGENTE_DIR, REVISION_MAX_ALTAS,
# REVISION_POR_SESION, REVISION_SESIONES, AGENTE_MAX_TURNOS, AGENTE_MODELO.
set -uo pipefail

FASE="${1:?uso: revision-federal.sh revisar|cerrar}"
EXTRACTOR="$(cd "$(dirname "$0")/../.." && pwd)"
TRABAJO="${AGENTE_DIR:-/tmp/agente}"
cd "$EXTRACTOR"
export PYTHONPATH="$EXTRACTOR"

# Altas fieles de esta corrida, en orden; las primeras REVISION_MAX_ALTAS se
# revisan ahora.
python3 - "$TRABAJO" "${REVISION_MAX_ALTAS:-3}" <<'PY'
import json, pathlib, sys
from extractor import federal
t, maximo = pathlib.Path(sys.argv[1]), int(sys.argv[2])
res = json.loads((t / "resultados.json").read_text(encoding="utf-8")) if (t / "resultados.json").exists() else {}
altas = [c for c, r in sorted(res.items()) if r.get("motivo") in ("nuevo", "reintento")
         and not r.get("error_fuente") and not r.get("sin_cambio") and federal.es_fiel(r)]
(t / "altas.txt").write_text("".join(f"{c}\n" for c in altas[:maximo]), encoding="utf-8")
(t / "altas-aplazadas.txt").write_text("".join(f"{c}\n" for c in altas[maximo:]), encoding="utf-8")
PY
[ -s "$TRABAJO/altas.txt" ] || [ -s "$TRABAJO/altas-aplazadas.txt" ] || { echo "Sin altas que revisar."; exit 0; }
RAIZ="$(git -C "$OUT" rev-parse --show-toplevel)"

revisar() {
  command -v claude > /dev/null || npm install -g @anthropic-ai/claude-code > /dev/null
  while IFS= read -r doc; do
    [ -n "$doc" ] || continue
    REV="$TRABAJO/revision/$doc"
    mkdir -p "$REV"
    previa="$(python scripts/revision.py previa --documento "$doc" --pdf "$PDF_DIR/$doc.pdf")"
    if [ -n "$previa" ] && [ "$(echo "$previa" | python3 -c 'import json,sys; print(json.load(sys.stdin)["resultado"])')" != fiel ]; then
      echo "$previa" > "$REV/previa.json"
      continue
    fi
    for n in $(seq 1 "${REVISION_SESIONES:-8}"); do
      python scripts/revision.py planear --repo "$RAIZ" --documento "$doc" --pdf "$PDF_DIR/$doc.pdf" --trabajo "$REV"
      python3 scripts/agente/brief_revision.py "$REV" "$n" "${REVISION_POR_SESION:-8}" \
        __BRIEF__=brief-revision-federal.md __EXTRACTOR__="$EXTRACTOR" __OUT__="$RAIZ" \
        __PDF__="$PDF_DIR/$doc.pdf" __DOCUMENTO__="$doc"
      [ -s "$REV/brief.md" ] || break
      (cd "$REV" && claude -p "$(cat "$REV/brief.md")" \
        --max-turns "${AGENTE_MAX_TURNOS:-120}" \
        --permission-mode acceptEdits \
        --allowedTools Bash Read Write Glob Grep \
        ${AGENTE_MODELO:+--model "$AGENTE_MODELO"} \
        >> "$REV/agente.log" 2>&1) || echo "::warning::La revisión de $doc terminó con error."
    done
  done < "$TRABAJO/altas.txt"
  # Esta revisión no cambia código: lo que haya tocado se deshace.
  git checkout -q -- extractor tests 2>/dev/null; git clean -fdq -- extractor tests
}

cerrar() {
  while IFS= read -r doc; do
    [ -n "$doc" ] || continue
    REV="$TRABAJO/revision/$doc"
    if [ -s "$REV/previa.json" ]; then
      motivo="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["motivo"])' "$REV/previa.json")"
    else
      motivo="$(python scripts/revision.py cerrar --repo "$RAIZ" --documento "$doc" \
        --pdf "$PDF_DIR/$doc.pdf" --trabajo "$REV")" && motivo=""
      motivo="${motivo#✗ }"
    fi
    printf '%s\t%s\n' "$doc" "$motivo"
  done < "$TRABAJO/altas.txt" > "$TRABAJO/revisiones.tsv"
  python3 - "$TRABAJO" <<'PY'
import json, pathlib, sys
t = pathlib.Path(sys.argv[1])
res = json.loads((t / "resultados.json").read_text(encoding="utf-8"))
for linea in (t / "revisiones.tsv").read_text(encoding="utf-8").splitlines():
    clave, _, motivo = linea.partition("\t")
    if motivo:
        res[clave]["revision"] = motivo
        print(f"✗ {clave}: {motivo}")
    else:
        print(f"✓ {clave}: revisión completa sin hallazgos")
for clave in (t / "altas-aplazadas.txt").read_text(encoding="utf-8").split():
    res[clave]["aplazada"] = True
    print(f"… {clave}: su revisión completa queda para la siguiente corrida")
(t / "resultados.json").write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
  bash scripts/agente/publicar_registro.sh "Revisión completa de las altas de leyes federales"
}

case "$FASE" in
  revisar) revisar ;;
  cerrar) cerrar ;;
  *) echo "fase desconocida: $FASE" >&2; exit 64 ;;
esac
