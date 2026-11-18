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
#     y lo sube (un resultado sin módulo: egress, codigo o fallido).
#   expandir.sh impacto LIMPIO — compuerta sin secretos: impacto_corpus.py con
#     el extractor en disco; sin cambios pasa, y si hay alguno tiene que ser
#     idéntico al del extractor de partida en LIMPIO (expansion.py impacto-igual).
#   expandir.sh egress DOMINIO — con EXTRACTOR_TOKEN (PR_TOKEN, que escribe en
#     toda la organización): agrega DOMINIO a egress-mx/permitidos.json de
#     constitucion-extractor si es oficial (expansion.py egress-agregar) y lo
#     sube. Sale 0 si quedó en la lista, 3 si el dominio no es oficial.
#
#   Cuando al extractor le falta algo para encontrar o descargar los PDF
#   (veredicto `codigo`), el job `codigo` de expandir-estatales.yml:
#   expandir.sh codigo-agente — con CLAUDE_CODE_OAUTH_TOKEN y nada más: agrega
#     una opción por ley en fuentes.py / registro.py / estatales/__init__.py
#     y su prueba nueva (brief-expansion-codigo.md).
#   expandir.sh codigo-compuertas LIMPIO — sin secretos: algo cambió, prueba
#     nueva, pytest, ninguna declaración ni URL vigente distinta (contra
#     $TRABAJO/codigo/declaraciones-antes.json, que dejó el extractor de
#     partida con sus páginas índice) e impacto nulo. Deja codigo/estado.txt.
#   expandir.sh codigo-publicar — con EXTRACTOR_TOKEN: aplica el arreglo sobre
#     un clon limpio de main y lo sube con el estado de vuelta en la cola (el
#     intento que pidió el código no cuenta), o anota el descarte.
#
# Entorno: ESTADO, NOMBRE, MODULO (nombre del archivo sin .py), TRABAJO;
# opcionales PISTA, PROXY_MX, PERMITIDOS, AGENTE_MINUTOS, AGENTE_MAX_TURNOS,
# AGENTE_MODELO, PDF_CACHE, FUENTES (fuentes.json para la compuerta de
# declaraciones), CORRIDA, ENSAYO (true: hace los commits pero no los sube), EXTRACTOR_TOKEN + EXTRACTOR_SLUG o
# EXTRACTOR_PUSH_URL (y CONSTITUCION_PUSH_URL, pruebas).
set -uo pipefail

FASE="${1:?uso: expandir.sh intento|agente|publicar|anotar|impacto|egress|codigo-agente|codigo-compuertas|codigo-publicar}"
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

# Sube el commit de HEAD del repo en $1 (a la URL $2, o al extractor),
# rebasando si main avanzó.
subir() {
  local repo="$1" url="${2:-}"
  if [ "${ENSAYO:-}" = true ]; then
    echo "Ensayo: no se sube $(git -C "$repo" log -1 --format=%s)"
    git -C "$repo" show --stat HEAD | tail -n 5
    return 0
  fi
  [ -n "$url" ] || url="$(destino)" || return 1
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

impacto() {
  local limpio="${1:?uso: expandir.sh impacto LIMPIO}" rc
  local cache="${PDF_CACHE:-/tmp/pdfs-corpus}"
  rm -rf "$TRABAJO/impacto-con" "$TRABAJO/impacto-sin"
  (cd "$EXTRACTOR" && python scripts/impacto_corpus.py --trabajo "$TRABAJO/impacto-con" --cache "$cache") \
    > "$TRABAJO/impacto-con.log" 2>&1 && rc=0 || rc=$?
  tail -n 15 "$TRABAJO/impacto-con.log"
  if [ "$rc" = 0 ] && [ "$(cat "$TRABAJO/impacto-con/cambios.json" 2>/dev/null)" = "[]" ]; then return 0; fi
  if [ "$rc" -gt 2 ]; then echo "::error::No se pudo medir el impacto."; return 1; fi
  echo "Hay cambios en lo publicado: se mide con el extractor de partida para comparar."
  (cd "$limpio" && python scripts/impacto_corpus.py --trabajo "$TRABAJO/impacto-sin" --cache "$cache") \
    > "$TRABAJO/impacto-sin.log" 2>&1 || true
  tail -n 5 "$TRABAJO/impacto-sin.log"
  python3 -I -S "$limpio/scripts/expansion.py" impacto-igual "$TRABAJO/impacto-sin" "$TRABAJO/impacto-con"
}

egress() {
  local dominio="${1:?uso: expandir.sh egress DOMINIO}" url dir extractor rc
  identidad
  if [ -n "${CONSTITUCION_PUSH_URL:-}" ]; then url="$CONSTITUCION_PUSH_URL"
  elif [ -n "${EXTRACTOR_TOKEN:-}" ]; then
    url="https://x-access-token:${EXTRACTOR_TOKEN}@github.com/OpenCodice/constitucion-extractor.git"
  else echo "::error::Sin credenciales para escribir en constitucion-extractor." >&2; return 1; fi
  extractor="$(limpio egress)" || return 1
  dir="$TRABAJO/constitucion-egress"
  rm -rf "$dir"
  git clone -q --depth 20 "$url" "$dir" || return 1
  python3 -I -S "$extractor/scripts/expansion.py" egress-agregar --json "$dir/egress-mx/permitidos.json" \
    --dominio "$dominio" --estado "$ESTADO" --pista "${PISTA:-}"
  rc=$?
  [ "$rc" = 0 ] || return "$rc"
  [ -n "$(git -C "$dir" status --porcelain)" ] || return 0
  git -C "$dir" add -- egress-mx/permitidos.json
  git -C "$dir" -c core.hooksPath=/dev/null commit -q \
    -m "egress-mx: $dominio para las leyes de ${NOMBRE:-$ESTADO}" \
    -m "Lo agregó la ronda de expansión de fiscal-extractor: el sitio no responde desde GitHub Actions y el dominio es oficial (scripts/expansion.py egress-agregar). Corrida: ${CORRIDA:-local}"
  subir "$dir" "$url" || return 1
  # El Worker lee la lista de raw.githubusercontent.com, que la sirve con
  # minutos de caché: la ronda que reintenta el estado no debe empezar antes.
  { [ -n "${CONSTITUCION_PUSH_URL:-}" ] || [ "${ENSAYO:-}" = true ]; } && return 0
  for _ in $(seq 1 30); do
    if curl -fsS -m 20 "https://raw.githubusercontent.com/OpenCodice/constitucion-extractor/main/egress-mx/permitidos.json" 2>/dev/null \
        | grep -qF "\"$dominio\""; then
      sleep 90
      return 0
    fi
    sleep 20
  done
  echo "::warning::La lista nueva aún no se ve en raw.githubusercontent.com; la ronda que sigue la verá."
  return 0
}

CODIGO="$TRABAJO/codigo"

codigo_agente() {
  rm -f "$CODIGO/veredicto.json"
  mkdir -p "$CODIGO"
  python3 - "$EXTRACTOR" "$TRABAJO" "${AGENTE_MINUTOS:-150}" <<'PY'
import datetime, json, os, pathlib, sys
extractor, trabajo, minutos = sys.argv[1], pathlib.Path(sys.argv[2]), int(sys.argv[3])
hora = lambda m: (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=m)).strftime("%H:%M UTC")
try:
    v = json.loads((trabajo / "veredicto.json").read_text(encoding="utf-8"))
except Exception:
    v = {}
falta = " ".join(str(v.get("falta") or v.get("motivo") or "").split())[:1500] or "(sin descripción)"
ejemplos = [" ".join(str(x).split())[:400] for x in (v.get("ejemplos") or [])[:8]]
brief = pathlib.Path(extractor, "scripts/agente/brief-expansion-codigo.md").read_text(encoding="utf-8")
for k, val in {"__EXTRACTOR__": extractor, "__ESTADO__": os.environ["ESTADO"],
               "__NOMBRE__": os.environ["NOMBRE"], "__FALTA__": falta,
               "__EJEMPLOS__": "\n".join(f"- `{x}`" for x in ejemplos) or "(ninguno)",
               "__BORRADOR__": str(trabajo / "borrador"),
               "__VEREDICTO__": str(trabajo / "codigo" / "veredicto.json"),
               "__LIMITE__": hora(minutos - 10)}.items():
    brief = brief.replace(k, val)
(trabajo / "codigo" / "brief.md").write_text(brief, encoding="utf-8")
PY
  command -v claude > /dev/null || npm install -g @anthropic-ai/claude-code > /dev/null
  cd "$EXTRACTOR"
  env -u EGRESS_MX_TOKEN -u EXTRACTOR_TOKEN -u GH_TOKEN -u GITHUB_TOKEN \
    BASH_DEFAULT_TIMEOUT_MS=1200000 BASH_MAX_TIMEOUT_MS=2400000 \
    claude -p "$(cat "$CODIGO/brief.md")" \
      --max-turns "${AGENTE_MAX_TURNOS:-200}" \
      --permission-mode acceptEdits \
      --allowedTools Bash Read Edit Write Glob Grep WebFetch WebSearch \
      ${AGENTE_MODELO:+--model "$AGENTE_MODELO"} \
      --output-format json \
      > "$CODIGO/agente.json" 2> "$CODIGO/agente.err" \
    || echo "::warning::El agente de código terminó con error (ver codigo/agente.err)."
  python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); print((r.get("result") or "")[-1500:])' \
    "$CODIGO/agente.json" 2>/dev/null || true
}

codigo_descartar() {
  echo "::warning::Arreglo de código descartado: $1"
  echo "$1" > "$CODIGO/descarte.txt"
  echo descartado > "$CODIGO/estado.txt"
}

# Lo único que puede tocar el agente de código (el cerco del workflow deshace
# todo si tocó otra cosa).
CODIGO_PERMITIDOS='^(extractor/fuentes\.py|extractor/registro\.py|extractor/estatales/__init__\.py|tests/test_expansion_[a-z0-9_]+\.py)$'

codigo_compuertas() {
  local limpio="${1:?uso: expandir.sh codigo-compuertas LIMPIO}" nuevas fuentes=()
  for f in ${FUENTES:-}; do fuentes+=(--fuentes "$f"); done
  mkdir -p "$CODIGO"
  rm -f "$CODIGO/estado.txt" "$CODIGO/descarte.txt" "$CODIGO/arreglo.patch"
  cd "$EXTRACTOR"
  if [ -z "$(git status --porcelain)" ]; then codigo_descartar "el agente no cambió el extractor"; return 0; fi
  nuevas=$(git ls-files --others --exclude-standard -- tests | grep -E '^tests/test_expansion_[a-z0-9_]+\.py$' \
             | xargs -r grep -lE '^def test_' 2>/dev/null || true)
  if [ -z "$nuevas" ]; then codigo_descartar "no agregó una prueba nueva tests/test_expansion_<tema>.py"; return 0; fi
  if ! python -m pytest -q > "$CODIGO/pytest.log" 2>&1; then
    tail -n 30 "$CODIGO/pytest.log"; codigo_descartar "las pruebas no pasan"; return 0
  fi
  tail -n 1 "$CODIGO/pytest.log"
  if ! python scripts/expansion.py declaraciones --salida "$CODIGO/declaraciones-despues.json" \
      --leer-de "$CODIGO/indices.json" "${fuentes[@]}"; then
    codigo_descartar "no se pudieron resolver las declaraciones con el arreglo"; return 0
  fi
  if ! python3 -I -S "$limpio/scripts/expansion.py" declaraciones-iguales \
      "$CODIGO/declaraciones-antes.json" "$CODIGO/declaraciones-despues.json" > "$CODIGO/declaraciones.log"; then
    cat "$CODIGO/declaraciones.log"
    codigo_descartar "cambia lo ya declarado: $(grep '^✗' "$CODIGO/declaraciones.log" | tail -1)"; return 0
  fi
  cat "$CODIGO/declaraciones.log"
  if ! impacto "$limpio"; then codigo_descartar "cambia lo publicado (impacto_corpus.py)"; return 0; fi
  git ls-files --others --exclude-standard | grep -E "$CODIGO_PERMITIDOS" | xargs -r git add -N --
  git diff -- extractor tests > "$CODIGO/arreglo.patch"
  echo listo > "$CODIGO/estado.txt"
}

codigo_publicar() {
  identidad
  local est dir titulo
  mkdir -p "$CODIGO"
  est="$(cat "$CODIGO/estado.txt" 2>/dev/null || echo descartado)"
  [ "$est" = listo ] || [ -s "$CODIGO/descarte.txt" ] || echo "las compuertas no terminaron" > "$CODIGO/descarte.txt"
  echo "publicado=false" >> "${GITHUB_OUTPUT:-/dev/null}"
  titulo="$(python3 -c '
import json, sys
try:
    t = str(json.load(open(sys.argv[1], encoding="utf-8")).get("titulo_commit") or "")
except Exception:
    t = ""
print(" ".join(t.split())[:120])' "$CODIGO/veredicto.json")"
  if [ "$est" = listo ]; then
    dir="$(limpio codigo)" || return 1
    if git -C "$dir" apply --3way "$CODIGO/arreglo.patch" \
        && python3 -I -S "$dir/scripts/expansion.py" anotar --estado "$ESTADO" --resultado codigo-publicado \
             --motivo "${titulo:-opción nueva del extractor}" --corrida "${CORRIDA:-}"; then
      git -C "$dir" add -A -- extractor tests
      git -C "$dir" -c core.hooksPath=/dev/null commit -q \
        -m "Leyes estatales: ${titulo:-opción nueva para resolver los PDF de $NOMBRE} (ronda de expansión)" \
        -m "Opción por ley para $NOMBRE, que la ronda de expansión no podía declarar sin ella. Compuertas: pruebas, ninguna declaración ni URL vigente distinta e impacto nulo en lo publicado. Corrida: ${CORRIDA:-local}"
      if subir "$dir"; then
        git -C "$dir" rev-parse HEAD > "$CODIGO/publicado.txt"
        echo "publicado=true" >> "${GITHUB_OUTPUT:-/dev/null}"
        echo "Arreglo de código publicado: ${titulo}"
        return 0
      fi
    fi
    echo "no se pudo aplicar o publicar el arreglo sobre main" > "$CODIGO/descarte.txt"
  fi
  anotar --resultado codigo-descartado --motivo "$(cat "$CODIGO/descarte.txt")" --corrida "${CORRIDA:-}"
}

case "$FASE" in
  intento) intento ;;
  agente) agente ;;
  publicar) publicar "$@" ;;
  anotar) anotar "$@" ;;
  impacto) impacto "$@" ;;
  egress) egress "$@" ;;
  codigo-agente) codigo_agente ;;
  codigo-compuertas) codigo_compuertas "$@" ;;
  codigo-publicar) codigo_publicar ;;
  *) echo "fase desconocida: $FASE" >&2; exit 64 ;;
esac
