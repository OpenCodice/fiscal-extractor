#!/usr/bin/env bash
# Reparación autónoma del extractor a partir de los hallazgos de la revisión
# completa (scripts/reparacion.py elige las leyes y el tipo de defecto). Tres
# fases, en tres pasos del workflow, más la preparación de su medición:
#
#   reparar.sh medicion — antes del agente, con la red que él no tiene
#     (EGRESS_MX_TOKEN): clona los repos de datos y deja en PDF_CACHE el PDF de
#     cada documento publicado, para que el agente mida él mismo el impacto de
#     su arreglo (scripts/impacto_corpus.py --medir). Si falla, el agente
#     trabaja igual, sin esa ayuda.
#   reparar.sh agente — con CLAUDE_CODE_OAUTH_TOKEN y nada más. El agente
#     cambia extractor/ y tests/ para que desaparezcan los hallazgos, y mide lo
#     que su arreglo cambia en lo publicado. Esa medición solo le ayuda: deciden
#     las compuertas. Durante la sesión las pruebas existentes, verificar.py y
#     validate.py quedan sin permiso de escritura.
#   reparar.sh comprobar — lo corre el agente dentro de su sesión, antes de
#     entregar: las mismas comprobaciones de `compuertas` que no dependen de lo
#     publicado (la función `comprobaciones`), sobre sus PDF y en su carpeta.
#     Solo informa (sale 0 si pasan, 1 si no): no descarta ni deja estado.
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
#   reparar.sh promover — con EXTRACTOR_TOKEN, en las leyes estatales: las de
#     FUERA (no por diseño) que quedaron con build y auditar limpios, con el
#     extractor de main ($AGENTE_DIR/fuera.json, de `reparacion.py fuera`) o
#     con el arreglo recién publicado, pasan a LEYES en su módulo.
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

FASE="${1:?uso: reparar.sh medicion|agente|comprobar|compuertas|publicar|promover}"
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

source "$EXTRACTOR/scripts/agente/sesion.sh"

hay_objetivo() { [ -s "$REP/objetivo.json" ]; }

# Lo que el agente no debe cambiar dentro de extractor/ y tests/: las pruebas
# que ya existen y la compuerta de fidelidad.
protegidos() { git ls-files -z -- tests extractor/verificar.py extractor/validate.py extractor/forma.py; }

# Sin permiso de escritura, un intento de editarlos falla en el momento y el
# agente lo ve; el dueño de un archivo puede devolverse el permiso, así que
# quien decide sigue siendo `compuertas`.
proteger() { protegidos | xargs -0 chmod a-w 2>/dev/null || true; }
desproteger() { protegidos | xargs -0 chmod u+w 2>/dev/null || true; }

MEDICION="$REP/medicion"
CACHE="${PDF_CACHE:-/tmp/pdfs-corpus}"

medicion() {
  hay_objetivo || return 0
  mkdir -p "$MEDICION/clones"
  # El repo de datos de esta corrida, con historia (sha_publicado la lee); los
  # demás los clona impacto_corpus.py de GitHub.
  case "$CORPUS" in estatal) propio=estatal ;; *) propio=federal ;; esac
  [ -d "$MEDICION/clones/$propio/.git" ] || git clone -q "$OUT" "$MEDICION/clones/$propio"
  python scripts/impacto_corpus.py --solo-pdfs --trabajo "$MEDICION" \
    --pdf-dir "$REP/pdfs" --cache "$CACHE" \
    || echo "::warning::No se pudo preparar la medición del agente reparador."
}

agente() {
  hay_objetivo || { echo "Sin leyes que reparar."; return 0; }
  rm -f "$REP/veredicto.json"
  mkdir -p "$REP/datos"
  python3 - "$REP" "$EXTRACTOR" "$CORPUS" "$CACHE" "${AGENTE_MINUTOS:-150}" <<'PY'
import datetime, json, pathlib, shlex, sys
rep, extractor, corpus, cache, minutos = pathlib.Path(sys.argv[1]), *sys.argv[2:4], sys.argv[4], int(sys.argv[5])
o = json.loads((rep / "objetivo.json").read_text(encoding="utf-8"))
medir = (f"python scripts/impacto_corpus.py --medir --trabajo {shlex.quote(str(rep / 'medicion'))} "
         f"--cache {shlex.quote(cache)} --pdf-dir {shlex.quote(str(rep / 'pdfs'))} "
         + " ".join(f"--objetivo {shlex.quote(e['clave'])}" for e in o["leyes"]))
# Paso rápido: las leyes estatales publicadas (lo que toca el flag `estatal`)
# o, en el corpus federal, una muestra de las federales.
rapido = medir + (" --sin-fiscal --sin-federal" if corpus == "estatal"
                  else " --sin-fiscal --sin-estatal --muestra 40")
ahora = datetime.datetime.now(datetime.timezone.utc)
hora = lambda m: (ahora + datetime.timedelta(minutes=m)).strftime("%H:%M UTC")
lineas = []
for e in o["leyes"]:
    propios = [h for h in e["hallazgos"] if h.get("categoria") == o["grupo"]]
    otros = [h for h in e["hallazgos"] if h.get("categoria") != o["grupo"]]
    lineas.append(f"{e['clave']} ({len(e['hallazgos'])} hallazgos; intento {e['intentos'] + 1}):")
    lineas += [f"  {h['clave']}: {h['nota']}" for h in propios[:25]]
    if otros:
        lineas.append("  otros hallazgos de esta ley (si comparten causa, también):")
        lineas += [f"  {h['clave']}: {h['nota']}" for h in otros[:10]]
    if e.get("descartes"):
        lineas.append("  intentos anteriores con este mismo PDF, descartados (no repitas ese arreglo):")
        lineas += [f"  - {d.get('fecha') or 's/f'}: {d.get('motivo') or 'sin motivo anotado'}"
                   for d in e["descartes"]]
brief = pathlib.Path(extractor, "scripts/agente/brief-reparacion.md").read_text(encoding="utf-8")
for k, v in {"__EXTRACTOR__": extractor, "__PDFS__": str(rep / "pdfs"),
             "__REGISTRO__": str(rep / "registro.json"), "__TRABAJO__": str(rep),
             "__VEREDICTO__": str(rep / "veredicto.json"), "__DESCRIPCION__": o["descripcion"],
             "__HALLAZGOS__": "\n".join(lineas), "__MEDIR_RAPIDO__": rapido,
             "__MEDIR_COMPLETO__": medir, "__MEDICION__": str(rep / "medicion"),
             "__COMPROBAR__": f"bash {shlex.quote(extractor + '/scripts/agente/reparar.sh')} comprobar",
             "__COMPROBACION__": str(rep / "comprobacion"),
             "__LIMITE__": hora(minutos - 5), "__ULTIMA_COMPLETA__": hora(minutos - 50)}.items():
    brief = brief.replace(k, v)
(rep / "brief.md").write_text(brief, encoding="utf-8")
PY
  command -v claude > /dev/null || npm install -g @anthropic-ai/claude-code > /dev/null
  local grupo claves
  grupo="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["grupo"])' \
    "$REP/objetivo.json" 2>/dev/null || true)"
  claves="$(python3 -c 'import json, sys; print(" ".join(e["clave"] for e in json.load(open(sys.argv[1], encoding="utf-8"))["leyes"]))' \
    "$REP/objetivo.json" 2>/dev/null || true)"
  # Los permisos vuelven pase lo que pase con la sesión.
  trap desproteger EXIT
  trap 'exit 143' HUP INT TERM
  proteger
  (
    # La medición completa tarda ~30 min: más que el tope de Bash por omisión.
    export BASH_DEFAULT_TIMEOUT_MS=1200000 BASH_MAX_TIMEOUT_MS=3000000
    # `comprobar`, que el agente corre en su sesión, parte del mismo commit
    # que las compuertas.
    export REPARACION_PARTIDA="${REPARACION_PARTIDA:-$(git rev-parse HEAD)}"
    export SESION_GRUPO="$grupo"
    sesion_agente reparacion "$REP/uso.jsonl" "$REP/brief.md" "$claves" \
      --max-turns "${AGENTE_MAX_TURNOS:-200}" \
      --permission-mode acceptEdits \
      --allowedTools Bash Read Edit Write Glob Grep \
      > "$REP/agente.log" 2>&1
  ) || echo "::warning::El agente de reparación terminó con error (ver $REP/agente.log)."
  desproteger
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

# Las comprobaciones del arreglo que no dependen de lo publicado: alcance,
# pruebas, huella y las leyes elegidas reconstruidas con el extractor de
# partida y con el arreglo. Es el mismo código para `compuertas`, que decide, y
# para `comprobar`, con el que el agente se adelanta: no cambia nada del
# arreglo ni deja estado.
#
#   comprobaciones PDFS DIR PYTEST_LOG [REUSAR]
#
# PDFS: los PDF de las leyes elegidas. DIR: donde quedan el extractor de
# partida (base/) y las dos reconstrucciones (antes/, despues/). REUSAR=true
# conserva antes/ entre llamadas mientras no cambien el commit de partida ni el
# objetivo. Devuelve 0 con las leyes que cambian en CAMBIAN, o 1 con el motivo
# en MOTIVO (y HIZO_COMMITS=true si el motivo son commits en el extractor).
comprobaciones() {
  local pdfs="$1" dir="$2" pytest_log="$3" reusar="${4:-false}"
  local fuera nuevas h_antes h_despues sello veredicto rc
  MOTIVO=""; CAMBIAN=""; HIZO_COMMITS=false
  if [ -n "${REPARACION_PARTIDA:-}" ] && [ "$(git rev-parse HEAD)" != "$REPARACION_PARTIDA" ]; then
    HIZO_COMMITS=true
    MOTIVO="hizo commits en el extractor"; return 1
  fi
  fuera=$(git status --porcelain=v1 -uall --no-renames | cut -c4- | tr -d '"' | grep -vE '^(extractor|tests)/' || true)
  if [ -n "$fuera" ]; then
    MOTIVO="tocó archivos fuera de extractor/ y tests/: $(echo "$fuera" | head -3 | tr '\n' ' ')"; return 1
  fi
  if [ -z "$(git status --porcelain)" ]; then
    MOTIVO="el agente no cambió el extractor"; return 1
  fi
  if [ -n "$(git status --porcelain -- extractor/verificar.py extractor/validate.py extractor/forma.py)" ]; then
    MOTIVO="cambió extractor/verificar.py, extractor/validate.py o extractor/forma.py, que son la compuerta"; return 1
  fi
  if [ -n "$(git diff --name-only HEAD -- tests)" ]; then
    MOTIVO="cambió pruebas existentes: $(git diff --name-only HEAD -- tests | head -3 | tr '\n' ' ')"; return 1
  fi
  nuevas=$(git ls-files --others --exclude-standard -- tests | grep -E '^tests/test_[^/]+\.py$' \
             | xargs -r grep -lE '^def test_' 2>/dev/null || true)
  if [ -z "$nuevas" ]; then
    MOTIVO="no agregó una prueba nueva en tests/"; return 1
  fi
  pip install -q pytest > /dev/null 2>&1 || true
  if ! python -m pytest -q > "$pytest_log" 2>&1; then
    tail -n 30 "$pytest_log"
    MOTIVO="las pruebas no pasan"; return 1
  fi
  # El extractor de partida, intacto, para comparar.
  rm -rf "$dir/base"
  git worktree prune
  git worktree add -q --detach "$dir/base" HEAD || { MOTIVO="no se pudo preparar el extractor de partida"; return 1; }
  h_antes="$(huella "$dir/base")"; h_despues="$(huella "$EXTRACTOR")"
  if [ -z "$h_antes" ] || [ -z "$h_despues" ]; then
    MOTIVO="no se pudo calcular la huella del extractor"; return 1
  elif [ "$h_antes" = "$h_despues" ]; then
    # Sin otra huella la vigilancia no reintentaría ninguna ley.
    MOTIVO="no cambia ningún archivo de la huella del extractor"; return 1
  fi
  sello="$(git rev-parse HEAD) $(git hash-object "$REP/objetivo.json")"
  if [ "$reusar" != true ] || [ ! -s "$dir/antes/resultado.json" ] \
      || [ "$(cat "$dir/antes.sello" 2>/dev/null)" != "$sello" ]; then
    rm -f "$dir/antes.sello"
    python scripts/reparacion.py construir --trabajo "$TRABAJO" --extractor-dir "$dir/base" \
      --pdfs "$pdfs" --out "$dir/antes" \
      || { MOTIVO="no se pudieron reconstruir las leyes elegidas"; return 1; }
    echo "$sello" > "$dir/antes.sello"
  fi
  python scripts/reparacion.py construir --trabajo "$TRABAJO" --extractor-dir "$EXTRACTOR" \
    --pdfs "$pdfs" --out "$dir/despues" \
    || { MOTIVO="no se pudieron reconstruir las leyes elegidas"; return 1; }
  veredicto="$(python scripts/reparacion.py comparar --trabajo "$TRABAJO" --antes "$dir/antes" --despues "$dir/despues")"
  rc=$?
  echo "$veredicto"
  if [ "$rc" != 0 ] || [ "${veredicto%% *}" != OK ]; then
    MOTIVO="${veredicto#NO }"; return 1
  fi
  CAMBIAN="${veredicto#OK }"
}

comprobar() {
  hay_objetivo || { echo "Sin leyes que reparar."; return 0; }
  local dir="$REP/comprobacion" rc=0
  mkdir -p "$dir"
  if comprobaciones "$REP/pdfs" "$dir" "$dir/pytest.log" true; then
    echo "PASA: alcance, prueba nueva, pytest, huella y leyes objetivo (cambian: $CAMBIAN)."
    echo "Falta lo que solo deciden las compuertas: el impacto en todo lo publicado y su juez."
  else
    rc=1
    echo "NO PASA: $MOTIVO"
    echo "Con esto las compuertas descartan el arreglo entero. Auditoría de cada ley con el"
    echo "extractor de partida y con tu arreglo: $dir/antes/ y $dir/despues/ (auditoria-*.json)."
  fi
  git worktree remove --force "$dir/base" 2>/dev/null || true
  git worktree prune
  return "$rc"
}

compuertas() {
  rm -f "$REP/estado.txt" "$REP/descarte.txt" "$REP/cambian.txt"
  desproteger
  hay_objetivo || { estado ninguno; return 0; }
  if [ -s "$GATE/fuera.txt" ]; then
    descartar "tocó archivos fuera de extractor/ y tests/: $(head -3 "$GATE/fuera.txt" | tr '\n' ' ')"
    return 0
  fi
  if ! comprobaciones "$GATE/pdfs" "$GATE" "$REP/pytest.log"; then
    [ "$HIZO_COMMITS" = true ] && git reset -q --hard "$REPARACION_PARTIDA"
    descartar "$MOTIVO"
    return 0
  fi
  echo "$CAMBIAN" > "$REP/cambian.txt"
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
  export GIT_AUTHOR_NAME="Claude (agente OpenCodice)" GIT_COMMITTER_NAME="Claude (agente OpenCodice)"
  export GIT_AUTHOR_EMAIL="noreply@anthropic.com"
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
    # main recibe pushes de otras corridas: si avanzó entre el rebase y el push,
    # se rebasa otra vez.
    subido=false
    for vuelta in 1 2 3; do
      if git -c core.hooksPath=/dev/null pull -q --rebase "$destino" main \
          && git -c core.hooksPath=/dev/null push -q "$destino" HEAD:main; then
        subido=true
        break
      fi
      git rebase --abort 2>/dev/null || true
      [ "$vuelta" = 3 ] || sleep $((vuelta * 5))
    done
    if [ "$subido" = true ]; then
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

# Pasa de FUERA a LEYES las leyes estatales que quedaron limpias (las de
# `reparacion.py fuera` y, si se publicó un arreglo, las del objetivo
# reconstruidas con él), desde un clon limpio de main: solo el bloque que agrega
# `reparacion.py promover` al final de su módulo, y con las pruebas en verde.
promover() {
  echo "promovidas=" >> "${GITHUB_OUTPUT:-/dev/null}"
  [ "$CORPUS" = estatal ] || return 0
  local resultados=() dir="$TRABAJO/promover" destino salida
  [ -s "$TRABAJO/fuera.json" ] && resultados+=(--resultado "$TRABAJO/fuera.json")
  if [ -s "$REP/reparacion.json" ] && [ -s "$GATE/despues/resultado.json" ]; then
    resultados+=(--resultado "$GATE/despues/resultado.json")
  fi
  [ ${#resultados[@]} -gt 0 ] || return 0
  if [ -z "${EXTRACTOR_PUSH_URL:-}" ] && { [ -z "${EXTRACTOR_TOKEN:-}" ] || [ -z "${EXTRACTOR_SLUG:-}" ]; }; then
    echo "::warning::Sin credenciales para publicar en el extractor."; return 0
  fi
  destino="${EXTRACTOR_PUSH_URL:-https://x-access-token:${EXTRACTOR_TOKEN:-}@github.com/${EXTRACTOR_SLUG:-}.git}"
  rm -rf "$dir"
  git clone -q "$destino" "$dir" || return 0
  salida="$(cd "$dir" && PYTHONPATH="$dir" GITHUB_OUTPUT=/dev/null python scripts/reparacion.py promover "${resultados[@]}")" || return 0
  echo "$salida"
  [ -n "$(git -C "$dir" status --porcelain -- extractor/estatales)" ] || return 0
  if [ -n "$(git -C "$dir" status --porcelain | grep -vE '^ M extractor/estatales/[a-z_]+\.py$')" ]; then
    echo "::warning::promover tocó algo más que los módulos de los estados; no se publica."; return 0
  fi
  if ! (cd "$dir" && PYTHONPATH="$dir" python -m pytest -q > "$TRABAJO/promover-pytest.log" 2>&1); then
    tail -n 20 "$TRABAJO/promover-pytest.log"
    echo "::warning::Con las leyes promovidas las pruebas no pasan; se quedan en FUERA."; return 0
  fi
  local claves estados
  claves="$(echo "$salida" | sed -n 's/^→ LEYES //p' | tr '\n' ' ' | sed 's/, / /g; s/ *$//')"
  estados="$(for c in $claves; do echo "${c%%/*}"; done | sort -u | tr '\n' ' ' | sed 's/ *$//')"
  export GIT_AUTHOR_NAME="Claude (agente OpenCodice)" GIT_COMMITTER_NAME="Claude (agente OpenCodice)"
  export GIT_AUTHOR_EMAIL="noreply@anthropic.com"
  export GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"
  git -C "$dir" add -- extractor/estatales
  git -C "$dir" -c core.hooksPath=/dev/null commit -q \
    -m "Leyes estatales: de FUERA a LEYES, con build y auditar limpios: $claves" \
    -m "Lo decidió reparacion.py promover sobre la auditoría determinista de su PDF; la vigilancia las da de alta tras su revisión completa."
  for intento in 1 2 3; do
    if git -C "$dir" -c core.hooksPath=/dev/null pull -q --rebase "$destino" main \
        && git -C "$dir" -c core.hooksPath=/dev/null push -q "$destino" HEAD:main; then
      echo "promovidas=$claves" >> "${GITHUB_OUTPUT:-/dev/null}"
      echo "estados=$estados" >> "${GITHUB_OUTPUT:-/dev/null}"
      echo "De FUERA a LEYES: $claves" | tee -a "${GITHUB_STEP_SUMMARY:-/dev/null}"
      return 0
    fi
    git -C "$dir" rebase --abort 2>/dev/null || true
    sleep $((intento * 5))
  done
  echo "::warning::No se pudo publicar el paso de FUERA a LEYES; la corrida siguiente lo reintenta."
}

case "$FASE" in
  promover) promover ;;
  medicion) medicion ;;
  agente) agente ;;
  comprobar) comprobar; exit $? ;;
  compuertas) compuertas ;;
  publicar) publicar ;;
  *) echo "fase desconocida: $FASE" >&2; exit 64 ;;
esac
exit 0
