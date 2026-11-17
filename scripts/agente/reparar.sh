#!/usr/bin/env bash
# Reparación autónoma del extractor a partir de los hallazgos de la revisión
# completa (scripts/reparacion.py elige las leyes y el tipo de defecto). Tres
# fases, en tres pasos del workflow:
#
#   reparar.sh agente — con CLAUDE_CODE_OAUTH_TOKEN y nada más. El agente
#     cambia extractor/ y tests/ para que desaparezcan los hallazgos.
#   reparar.sh compuertas — sin secretos ni agente. Alcance (solo extractor/ y
#     tests/, ni verificar.py ni validate.py ni pruebas existentes, y una prueba
#     nueva), pruebas, huella del extractor, las leyes elegidas reconstruidas
#     con el extractor de partida y con el arreglo (ninguna unidad con problemas
#     nueva, algún texto distinto) y el impacto en todo lo publicado
#     (scripts/impacto_corpus.py). Deja en reparacion/estado.txt `listo`,
#     `impacto` (falta que el agente juez confirme lo que cambia) o `descartado`.
#   reparar.sh publicar — con EXTRACTOR_TOKEN. Pasa al registro el veredicto del
#     juez y publica el arreglo en main solo si todo lo que cambia es mejora.
#     Anota el intento (publicado o descartado) en verificaciones/reparaciones/.
#
# Todo lo que no sea un `listo` comprobado aquí se descarta: el extractor se
# queda como estaba y las leyes, fuera, hasta el siguiente intento (hay un tope
# por ley y PDF, extractor/reparaciones.py).
#
# Entorno: OUT (repo de datos), REPARACION_CORPUS (estatal|federal),
# REPARACION_GATE (PDFs de las compuertas, fuera del alcance del agente),
# REPARACION_PARTIDA (commit del extractor antes del agente); opcionales
# AGENTE_DIR, PDF_CACHE, AGENTE_MAX_TURNOS, AGENTE_MODELO, EXTRACTOR_TOKEN +
# EXTRACTOR_SLUG o EXTRACTOR_PUSH_URL (pruebas).
set -uo pipefail

FASE="${1:?uso: reparar.sh agente|compuertas|publicar}"
EXTRACTOR="$(cd "$(dirname "$0")/../.." && pwd)"
TRABAJO="${AGENTE_DIR:-/tmp/agente}"
REP="$TRABAJO/reparacion"
GATE="${REPARACION_GATE:-/tmp/reparacion-gate}"
CORPUS="${REPARACION_CORPUS:-estatal}"
cd "$EXTRACTOR"
export PYTHONPATH="$EXTRACTOR"
case "$CORPUS" in
  estatal) NOMBRE="leyes estatales" ;;
  *)       NOMBRE="leyes federales" ;;
esac

hay_objetivo() { [ -s "$REP/objetivo.json" ]; }

agente() {
  hay_objetivo || { echo "Sin leyes que reparar."; return 0; }
  rm -f "$REP/veredicto.json"
  mkdir -p "$REP/datos"
  python3 - "$REP" "$EXTRACTOR" <<'PY'
import json, pathlib, sys
rep, extractor = pathlib.Path(sys.argv[1]), sys.argv[2]
o = json.loads((rep / "objetivo.json").read_text(encoding="utf-8"))
lineas = []
for e in o["leyes"]:
    propios = [h for h in e["hallazgos"] if h.get("categoria") == o["grupo"]]
    otros = [h for h in e["hallazgos"] if h.get("categoria") != o["grupo"]]
    lineas.append(f"{e['clave']} ({len(e['hallazgos'])} hallazgos; intento {e['intentos'] + 1}):")
    lineas += [f"  {h['clave']}: {h['nota']}" for h in propios[:25]]
    if otros:
        lineas.append("  otros hallazgos de esta ley (si comparten causa, también):")
        lineas += [f"  {h['clave']}: {h['nota']}" for h in otros[:10]]
brief = pathlib.Path(extractor, "scripts/agente/brief-reparacion.md").read_text(encoding="utf-8")
for k, v in {"__EXTRACTOR__": extractor, "__PDFS__": str(rep / "pdfs"),
             "__REGISTRO__": str(rep / "registro.json"), "__TRABAJO__": str(rep),
             "__VEREDICTO__": str(rep / "veredicto.json"), "__DESCRIPCION__": o["descripcion"],
             "__HALLAZGOS__": "\n".join(lineas)}.items():
    brief = brief.replace(k, v)
(rep / "brief.md").write_text(brief, encoding="utf-8")
PY
  command -v claude > /dev/null || npm install -g @anthropic-ai/claude-code > /dev/null
  claude -p "$(cat "$REP/brief.md")" \
    --max-turns "${AGENTE_MAX_TURNOS:-200}" \
    --permission-mode acceptEdits \
    --allowedTools Bash Read Edit Write Glob Grep \
    ${AGENTE_MODELO:+--model "$AGENTE_MODELO"} \
    > "$REP/agente.log" 2>&1 || echo "::warning::El agente de reparación terminó con error (ver $REP/agente.log)."
  tail -n 30 "$REP/agente.log" || true
}

estado() { echo "$1" > "$REP/estado.txt"; }

descartar() {
  echo "::warning::Arreglo del agente descartado: $1"
  echo "$1" > "$REP/descarte.txt"
  { git diff HEAD; git ls-files --others --exclude-standard -- extractor tests \
      | while IFS= read -r f; do git diff --no-index /dev/null "$f"; done; } \
    > "$REP/arreglo-descartado.patch" 2>/dev/null || true
  git checkout -q -- . 2>/dev/null; git clean -fdq -- extractor tests
  estado descartado
}

huella() {
  (cd "$1" && PYTHONPATH="$1" python3 -c '
import sys
from extractor import federal
from extractor.estatal import ESTATAL
print(federal.huella_extractor(ESTATAL.fuentes_extractor if sys.argv[1] == "estatal" else ()))' "$CORPUS")
}

compuertas() {
  rm -f "$REP/estado.txt" "$REP/descarte.txt" "$REP/cambian.txt"
  hay_objetivo || { estado ninguno; return 0; }
  if [ -s "$GATE/fuera.txt" ]; then
    descartar "tocó archivos fuera de extractor/ y tests/: $(head -3 "$GATE/fuera.txt" | tr '\n' ' ')"
    return 0
  fi
  if [ -n "${REPARACION_PARTIDA:-}" ] && [ "$(git rev-parse HEAD)" != "$REPARACION_PARTIDA" ]; then
    git reset -q --hard "$REPARACION_PARTIDA"
    descartar "hizo commits en el extractor"
    return 0
  fi
  fuera=$(git status --porcelain=v1 -uall --no-renames | cut -c4- | tr -d '"' | grep -vE '^(extractor|tests)/' || true)
  if [ -n "$fuera" ]; then
    descartar "tocó archivos fuera de extractor/ y tests/: $(echo "$fuera" | head -3 | tr '\n' ' ')"
    return 0
  fi
  if [ -z "$(git status --porcelain)" ]; then
    descartar "el agente no cambió el extractor"
    return 0
  fi
  if [ -n "$(git status --porcelain -- extractor/verificar.py extractor/validate.py)" ]; then
    descartar "cambió extractor/verificar.py o extractor/validate.py, que son la compuerta"
    return 0
  fi
  if [ -n "$(git diff --name-only HEAD -- tests)" ]; then
    descartar "cambió pruebas existentes: $(git diff --name-only HEAD -- tests | head -3 | tr '\n' ' ')"
    return 0
  fi
  nuevas=$(git ls-files --others --exclude-standard -- tests | grep -E '^tests/test_[^/]+\.py$' \
             | xargs -r grep -lE '^def test_' 2>/dev/null || true)
  if [ -z "$nuevas" ]; then
    descartar "no agregó una prueba nueva en tests/"
    return 0
  fi
  pip install -q pytest > /dev/null 2>&1 || true
  if ! python -m pytest -q > "$REP/pytest.log" 2>&1; then
    tail -n 30 "$REP/pytest.log"
    descartar "las pruebas no pasan"
    return 0
  fi
  # El extractor de partida, intacto, para comparar.
  rm -rf "$GATE/base"
  git worktree add -q --detach "$GATE/base" HEAD || { descartar "no se pudo preparar el extractor de partida"; return 0; }
  h_antes="$(huella "$GATE/base")"; h_despues="$(huella "$EXTRACTOR")"
  if [ -z "$h_antes" ] || [ -z "$h_despues" ]; then
    descartar "no se pudo calcular la huella del extractor"; return 0
  elif [ "$h_antes" = "$h_despues" ]; then
    # Sin otra huella la vigilancia no reintentaría ninguna ley.
    descartar "no cambia ningún archivo de la huella del extractor"; return 0
  fi
  python scripts/reparacion.py construir --trabajo "$TRABAJO" --extractor-dir "$GATE/base" \
    --pdfs "$GATE/pdfs" --out "$GATE/antes" \
    && python scripts/reparacion.py construir --trabajo "$TRABAJO" --extractor-dir "$EXTRACTOR" \
      --pdfs "$GATE/pdfs" --out "$GATE/despues" \
    || { descartar "no se pudieron reconstruir las leyes elegidas"; return 0; }
  veredicto="$(python scripts/reparacion.py comparar --trabajo "$TRABAJO" --antes "$GATE/antes" --despues "$GATE/despues")"
  rc=$?
  echo "$veredicto"
  if [ "$rc" != 0 ] || [ "${veredicto%% *}" != OK ]; then
    descartar "${veredicto#NO }"; return 0
  fi
  echo "${veredicto#OK }" > "$REP/cambian.txt"
  # El arreglo cambia el extractor de todo lo publicado: cada artículo que
  # cambie tiene que confirmarse como mejora antes de que entre.
  rm -rf "$REP/impacto"
  if [ "$CORPUS" = estatal ]; then datos=(--estatal "$OUT"); else datos=(--federal "$OUT"); fi
  python scripts/impacto_corpus.py --trabajo "$REP/impacto" "${datos[@]}" \
    --pdf-dir "$GATE/pdfs" --cache "${PDF_CACHE:-/tmp/pdfs-corpus}" > "$REP/impacto.log" 2>&1
  rc=$?
  cat "$REP/impacto.log"
  case "$rc" in
    0) estado listo ;;
    1) if [ -s "$REP/impacto/pendientes.json" ]; then estado impacto
       else descartar "el impacto pide verificación pero no dejó qué verificar"; fi ;;
    *) descartar "en lo publicado: $(grep '^✗' "$REP/impacto.log" | head -3 | tr '\n' ' ')" ;;
  esac
}

publicar() {
  echo "reparado=false" >> "${GITHUB_OUTPUT:-/dev/null}"
  hay_objetivo || return 0
  est="$(cat "$REP/estado.txt" 2>/dev/null || echo ninguno)"
  if [ "$est" = impacto ]; then
    if python scripts/impacto.py cerrar --trabajo "$REP/impacto" \
        --extractor "OpenCodice/fiscal-extractor@$(git rev-parse HEAD)" \
        --reporte "$REP/impacto.md"; then
      est=listo
    else
      descartar "no todo lo que cambia en lo publicado quedó confirmado como mejora: $(tail -n +2 "$REP/impacto.md" 2>/dev/null | head -c 400)"
      est=descartado
    fi
  fi
  if [ "$est" = listo ] && [ ! -s "$REP/cambian.txt" ]; then
    descartar "las compuertas no dejaron constancia de las leyes que cambian"
    est=descartado
  fi
  if [ "$est" = listo ] && [ -z "${EXTRACTOR_PUSH_URL:-}" ] \
      && { [ -z "${EXTRACTOR_TOKEN:-}" ] || [ -z "${EXTRACTOR_SLUG:-}" ]; }; then
    descartar "sin credenciales para publicar el arreglo en el extractor"
    est=descartado
  fi
  export GIT_AUTHOR_NAME="${GITHUB_ACTOR:-opencodice-ci}" GIT_COMMITTER_NAME="${GITHUB_ACTOR:-opencodice-ci}"
  export GIT_AUTHOR_EMAIL="${GITHUB_ACTOR_ID:-0}+${GITHUB_ACTOR:-opencodice-ci}@users.noreply.github.com"
  export GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"
  partida="$(git rev-parse HEAD)"
  if [ "$est" = listo ]; then
    titulo="$(python3 -c '
import json, sys
try:
    t = str(json.load(open(sys.argv[1], encoding="utf-8")).get("titulo_commit") or "")
except Exception:
    t = ""
print(" ".join(t.split())[:120])' "$REP/veredicto.json")"
    python scripts/reparacion.py registrar --trabajo "$TRABAJO" --resultado publicado \
      --extractor "$partida" --motivo "${titulo:-ajuste del extractor}"
    git add -A -- extractor tests verificaciones
    git -c core.hooksPath=/dev/null commit -q -m "Reparación automática ($NOMBRE): ${titulo:-ajuste del extractor a un formato de PDF}" \
      -m "Leyes con hallazgos que cambian: $(cat "$REP/cambian.txt")"
    git diff "$partida" HEAD > "$REP/arreglo.patch"
    destino="${EXTRACTOR_PUSH_URL:-https://x-access-token:${EXTRACTOR_TOKEN:-}@github.com/${EXTRACTOR_SLUG:-}.git}"
    if git -c core.hooksPath=/dev/null pull -q --rebase "$destino" main \
        && git -c core.hooksPath=/dev/null push -q "$destino" HEAD:main; then
      echo "reparado=true" >> "${GITHUB_OUTPUT:-/dev/null}"
      python3 - "$REP" "$titulo" "$(git rev-parse HEAD)" <<'PY'
import json, sys
rep, titulo, sha = sys.argv[1:]
json.dump({"titulo": titulo, "sha": sha, "cambian": open(f"{rep}/cambian.txt").read().split()},
          open(f"{rep}/reparacion.json", "w"), ensure_ascii=False)
PY
      echo "Arreglo publicado en el extractor: $titulo"
      notas
      return 0
    fi
    git rebase --abort 2>/dev/null || true
    # El registro de impacto se conserva; el arreglo no.
    git reset -q --soft "$partida" && git reset -q
    # La línea `publicado` sale del registro (queda la de `iniciado`, ya publicada).
    intento="verificaciones/reparaciones/$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["intento"])' "$REP/objetivo.json").jsonl"
    git checkout -q -- "$intento" 2>/dev/null || rm -f "$intento"
    git checkout -q -- extractor tests 2>/dev/null; git clean -fdq -- extractor tests
    descartar "no se pudo publicar el arreglo en el extractor"
  fi
  python scripts/reparacion.py registrar --trabajo "$TRABAJO" --resultado descartado \
    --extractor "$partida" --motivo "$(cat "$REP/descarte.txt" 2>/dev/null || echo 'sin compuertas')"
  bash scripts/agente/publicar_registro.sh "Reparación automática descartada ($NOMBRE)"
  notas
}

notas() {
  python3 - "$REP" >> "${GITHUB_STEP_SUMMARY:-/dev/null}" <<'PY'
import json, pathlib, sys
rep = pathlib.Path(sys.argv[1])
o = json.loads((rep / "objetivo.json").read_text(encoding="utf-8"))
print(f"## Reparación automática: {o['descripcion']}")
print("Leyes: " + ", ".join(f"`{e['clave']}`" for e in o["leyes"]))
try:
    v = json.loads((rep / "veredicto.json").read_text(encoding="utf-8"))
    print(f"\n{v.get('resumen', '')}")
except Exception:
    print("\nEl agente no entregó veredicto.")
if (rep / "reparacion.json").exists():
    print("\nArreglo publicado en el extractor; las leyes se reintentan en la siguiente corrida.")
if (rep / "descarte.txt").exists():
    print(f"\nArreglo descartado: {(rep / 'descarte.txt').read_text().strip()}")
if (rep / "impacto.md").exists():
    print("\nImpacto en lo publicado: " + (rep / "impacto.md").read_text(encoding="utf-8").strip())
PY
}

case "$FASE" in
  agente) agente ;;
  compuertas) compuertas ;;
  publicar) publicar ;;
  *) echo "fase desconocida: $FASE" >&2; exit 64 ;;
esac
exit 0
