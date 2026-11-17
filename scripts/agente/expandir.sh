#!/usr/bin/env bash
# Ronda de expansión de las leyes estatales (expandir-estatales.yml): el agente
# escribe el módulo de un estado nuevo (extractor/estatales/<estado>.py) y sus
# pruebas; lo demás lo decide código determinista (scripts/expansion.py). Fases:
#
#   expandir.sh intento — publica en main el intento ya contado en
#     extractor/estatales/pendientes.json (antes del agente: un intento que se
#     cae también cuenta).
#   expandir.sh agente — con CLAUDE_CODE_OAUTH_TOKEN y nada más (EGRESS_MX_TOKEN
#     no está en su entorno: si hace falta, lo usa la puerta local proxy_mx.py,
#     que arrancó otro paso). Escribe el módulo, sus pruebas y su veredicto.
#   expandir.sh publicar — con EXTRACTOR_TOKEN, desde un clon limpio de main:
#     copia solo el módulo y sus pruebas (ya pasadas por las compuertas), anota
#     el estado como publicado y sube todo en un commit.
#   expandir.sh anotar ARGS… — desde un clon limpio, `expansion.py anotar ARGS…`
#     y lo sube (un resultado sin módulo: egress o fallido).
#
# Entorno: ESTADO, NOMBRE, MODULO (nombre del archivo sin .py), TRABAJO;
# opcionales PISTA, PROXY_MX, PERMITIDOS, AGENTE_MINUTOS, AGENTE_MAX_TURNOS,
# AGENTE_MODELO, EXTRACTOR_TOKEN + EXTRACTOR_SLUG o EXTRACTOR_PUSH_URL.
set -uo pipefail

FASE="${1:?uso: expandir.sh intento|agente|publicar|anotar}"
shift
EXTRACTOR="$(cd "$(dirname "$0")/../.." && pwd)"
TRABAJO="${TRABAJO:-/tmp/expansion}"
mkdir -p "$TRABAJO"

identidad() {
  export GIT_AUTHOR_NAME="${GITHUB_ACTOR:-opencodice-ci}" GIT_COMMITTER_NAME="${GITHUB_ACTOR:-opencodice-ci}"
  export GIT_AUTHOR_EMAIL="${GITHUB_ACTOR_ID:-0}+${GITHUB_ACTOR:-opencodice-ci}@users.noreply.github.com"
  export GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"
}

destino() {
  if [ -z "${EXTRACTOR_PUSH_URL:-}" ] && { [ -z "${EXTRACTOR_TOKEN:-}" ] || [ -z "${EXTRACTOR_SLUG:-}" ]; }; then
    echo "::error::Sin credenciales para publicar en el extractor." >&2
    return 1
  fi
  echo "${EXTRACTOR_PUSH_URL:-https://x-access-token:${EXTRACTOR_TOKEN:-}@github.com/${EXTRACTOR_SLUG:-}.git}"
}

# Sube el commit de HEAD del repo en $1, rebasando si main avanzó.
subir() {
  local repo="$1" url
  url="$(destino)" || return 1
  for intento in 1 2 3; do
    if git -C "$repo" -c core.hooksPath=/dev/null pull -q --rebase "$url" main \
        && git -C "$repo" -c core.hooksPath=/dev/null push -q "$url" HEAD:main; then
      return 0
    fi
    git -C "$repo" rebase --abort 2>/dev/null || true
    sleep $((intento * 5))
  done
  echo "::error::No se pudo publicar en el extractor." >&2
  return 1
}

# Un clon limpio de main: lo que publica no puede venir de un árbol que tocó
# el agente.
limpio() {
  local dir="$TRABAJO/limpio-$1" url
  rm -rf "$dir"
  url="$(destino)" || return 1
  git clone -q --depth 50 "$url" "$dir" || return 1
  echo "$dir"
}

intento() {
  identidad
  cd "$EXTRACTOR"
  [ -n "$(git status --porcelain -- extractor/estatales/pendientes.json)" ] || return 0
  git add -- extractor/estatales/pendientes.json
  git -c core.hooksPath=/dev/null commit -q -m "Ronda de expansión: intento con ${NOMBRE:-$ESTADO}"
  subir "$EXTRACTOR"
}

agente() {
  rm -f "$TRABAJO/veredicto.json"
  mkdir -p "$TRABAJO/agente"
  python3 - "$EXTRACTOR" "$TRABAJO" "${AGENTE_MINUTOS:-150}" <<'PY'
import datetime, os, pathlib, sys
extractor, trabajo, minutos = sys.argv[1], pathlib.Path(sys.argv[2]), int(sys.argv[3])
ahora = datetime.datetime.now(datetime.timezone.utc)
hora = lambda m: (ahora + datetime.timedelta(minutes=m)).strftime("%H:%M UTC")
e = os.environ
proxy = e.get("PROXY_MX", "")
permitidos = e.get("PERMITIDOS", "").split()
if proxy and permitidos:
    via = (f"Hay una puerta local hacia el Worker egress-mx, que descarga desde México: "
           f"`curl -sS \"{proxy}/?url=<URL codificada>\"` (con `python3 -c 'import urllib.parse,sys; "
           f"print(urllib.parse.quote(sys.argv[1], safe=\"\"))' <URL>` la codificas). Solo sirve para "
           f"estos dominios: {', '.join(f'`{d}`' for d in permitidos)}. Si el sitio del estado está en "
           f"uno de ellos y rechaza tu IP, úsala y declara sus leyes con `via=\"mx\"`.")
else:
    via = "No hay puerta hacia el Worker egress-mx en esta corrida."
brief = pathlib.Path(extractor, "scripts/agente/brief-expansion.md").read_text(encoding="utf-8")
for k, v in {"__EXTRACTOR__": extractor, "__ESTADO__": e["ESTADO"], "__NOMBRE__": e["NOMBRE"],
             "__MODULO__": f"extractor/estatales/{e['MODULO']}.py",
             "__PRUEBA__": f"tests/test_estatal_{e['MODULO']}.py",
             "__PISTA__": e.get("PISTA") or "Sin pista.", "__VIA_MX__": via,
             "__TRABAJO__": str(trabajo / "agente"), "__VEREDICTO__": str(trabajo / "veredicto.json"),
             "__LIMITE__": hora(minutos - 10)}.items():
    brief = brief.replace(k, v)
(trabajo / "brief.md").write_text(brief, encoding="utf-8")
PY
  command -v claude > /dev/null || npm install -g @anthropic-ai/claude-code > /dev/null
  cd "$EXTRACTOR"
  env -u EGRESS_MX_TOKEN -u EXTRACTOR_TOKEN -u GH_TOKEN -u GITHUB_TOKEN \
    BASH_DEFAULT_TIMEOUT_MS=1200000 BASH_MAX_TIMEOUT_MS=2400000 \
    claude -p "$(cat "$TRABAJO/brief.md")" \
      --max-turns "${AGENTE_MAX_TURNOS:-300}" \
      --permission-mode acceptEdits \
      --allowedTools Bash Read Edit Write Glob Grep WebFetch WebSearch \
      ${AGENTE_MODELO:+--model "$AGENTE_MODELO"} \
      --output-format json \
      > "$TRABAJO/agente.json" 2> "$TRABAJO/agente.err" \
    || echo "::warning::El agente de expansión terminó con error (ver agente.err)."
  python3 - "$TRABAJO/agente.json" <<'PY' || true
import json, sys
try:
    r = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    sys.exit(0)
print(f"Agente: {r.get('num_turns')} turnos, {round((r.get('duration_ms') or 0) / 60000)} min, "
      f"costo equivalente ${r.get('total_cost_usd') or 0:.2f}")
print((r.get("result") or "")[-1500:])
PY
}

publicar() {
  identidad
  local dir
  dir="$(limpio publicar)" || return 1
  local mod="extractor/estatales/$MODULO.py"
  cp "$EXTRACTOR/$mod" "$dir/$mod"
  (cd "$EXTRACTOR" && git ls-files --others --exclude-standard -- "tests/test_estatal_${MODULO}*.py") \
    | while IFS= read -r f; do cp "$EXTRACTOR/$f" "$dir/$f"; done
  python3 -I -S "$dir/scripts/expansion.py" anotar --estado "$ESTADO" --resultado publicado "$@" \
    || return 1
  git -C "$dir" add -- "$mod" tests extractor/estatales/pendientes.json
  local titulo resumen
  titulo="$(python3 -c '
import json, sys
try:
    t = str(json.load(open(sys.argv[1], encoding="utf-8")).get("resumen") or "")
except Exception:
    t = ""
print(" ".join(t.split())[:900])' "$TRABAJO/veredicto.json")"
  git -C "$dir" -c core.hooksPath=/dev/null commit -q \
    -m "Leyes estatales: $NOMBRE (ronda de expansión)" \
    -m "${titulo:-Módulo escrito por el agente de la ronda de expansión.}" \
    -m "Compuertas: pruebas, build y auditar de cada ley sobre su PDF, e impacto nulo en lo publicado. Corrida: ${CORRIDA:-local}"
  subir "$dir" || return 1
  git -C "$dir" rev-parse HEAD > "$TRABAJO/publicado.txt"
}

anotar() {
  identidad
  local dir
  dir="$(limpio anotar)" || return 1
  python3 -I -S "$dir/scripts/expansion.py" anotar --estado "$ESTADO" "$@" || return 1
  [ -n "$(git -C "$dir" status --porcelain)" ] || return 0
  git -C "$dir" add -- extractor/estatales/pendientes.json
  git -C "$dir" -c core.hooksPath=/dev/null commit -q -m "Ronda de expansión: ${NOMBRE:-$ESTADO} sin publicar"
  subir "$dir"
}

case "$FASE" in
  intento) intento ;;
  agente) agente ;;
  publicar) publicar "$@" ;;
  anotar) anotar "$@" ;;
  *) echo "fase desconocida: $FASE" >&2; exit 64 ;;
esac
