#!/usr/bin/env bash
# Compuertas deterministas después del agente en el corpus federal, en dos
# fases (dos pasos del workflow, con el agente de impacto entre ellas):
#
#   cerrar-federal.sh compuertas — sin secretos. Restaura el repo de datos (el
#     agente no puede tocarlo); si el agente cambió el extractor: pruebas,
#     reevaluación de los documentos con fallas, la muestra de regresión y el
#     impacto del arreglo en TODO lo publicado (leyes-federales y
#     fiscal-mexicano, scripts/impacto_corpus.py).
#   cerrar-federal.sh publicar — con EXTRACTOR_TOKEN. Pasa al registro el
#     veredicto de impacto y publica el arreglo solo si cada unidad publicada
#     que cambia es una mejora. Deja `resultados.json` con la auditoría que vale.
#
# Entorno: OUT, PDF_DIR, PLAN; opcionales AGENTE_DIR, PDF_CACHE,
# EXTRACTOR_TOKEN + EXTRACTOR_SLUG (para publicar el arreglo), EXTRACTOR_PUSH_URL
# (destino alterno, para pruebas).
set -uo pipefail

FASE="${1:?uso: cerrar-federal.sh compuertas|publicar}"

EXTRACTOR="$(cd "$(dirname "$0")/../.." && pwd)"
TRABAJO="${AGENTE_DIR:-/tmp/agente}"
cd "$EXTRACTOR"
export PYTHONPATH="$EXTRACTOR"

IMPACTO="$TRABAJO/impacto-arreglo"
[ -d "$TRABAJO/datos-antes" ] || exit 0       # el agente no intervino

restaurar() {
  rsync -a --delete --exclude .git "$TRABAJO/datos-antes/" "$OUT/"
  cp "$TRABAJO/resultados-antes.json" "$TRABAJO/resultados.json"
}

descartar() {
  echo "::warning::Arreglo del agente descartado: $1"
  echo "$1" > "$TRABAJO/descarte.txt"
  rm -f "$TRABAJO/arreglo-ok.txt"
  [ -s "$TRABAJO/arreglo-descartado.patch" ] || git diff > "$TRABAJO/arreglo-descartado.patch" || true
  git checkout -q -- . && git clean -fdq
  restaurar
}

campo() {
  python - "$TRABAJO/veredicto.json" "$1" <<'PY'
import json, sys
try:
    v = json.load(open(sys.argv[1], encoding="utf-8")).get(sys.argv[2], "")
except Exception:
    v = ""
print(str(v).lower() if isinstance(v, bool) else v)
PY
}

compuertas() {
  rm -f "$TRABAJO/arreglo-estado.txt" "$TRABAJO/arreglo-ok.txt"
  restaurar
  # La vigilancia corre en este mismo repo: el agente solo puede publicar
  # cambios al extractor y a sus pruebas, nunca a workflows, scripts ni
  # Workers. Archivos nuevos sueltos (copias de PDF, notas) no se publican.
  git ls-files --others --exclude-standard | grep -vE '^(extractor|tests)/' | while IFS= read -r f; do rm -f -- "$f"; done
  fuera=$( { git diff --name-only HEAD; git ls-files --deleted; } | sort -u | grep -vE '^(extractor|tests)/' || true)
  if [ -n "$fuera" ]; then
    descartar "toca archivos fuera de extractor/ y tests/: $(echo "$fuera" | head -3 | tr '\n' ' ')"
  fi
  if [ -z "$(git status --porcelain)" ]; then
    echo "El agente no cambió el extractor."
    return 0
  fi
  pip install -q pytest > /dev/null 2>&1 || true
  if ! python -m pytest -q > "$TRABAJO/pytest.log" 2>&1; then
    descartar "las pruebas no pasan"
    return 0
  fi
  python -m extractor federal reevaluar --plan "$PLAN" --out "$OUT" --pdf-dir "$PDF_DIR" \
    --trabajo "$TRABAJO" --json "$TRABAJO/nuevo.json"
  bash "$EXTRACTOR/scripts/agente/muestra-federal.sh" "$TRABAJO/muestra-nuevo.json"
  veredicto=$(python - "$TRABAJO" <<'PY'
import json, sys
t = sys.argv[1]
cargar = lambda n: json.load(open(f"{t}/{n}"))
nuevo = cargar("nuevo.json")
# La muestra es la primera alarma, barata; el impacto en todo lo publicado
# viene después.
rotas = set(cargar("muestra-nuevo.json")["con_problemas"]) - set(cargar("muestra-base.json")["con_problemas"])
fieles = [c for c, r in nuevo["resultados"].items()
          if not r.get("error") and not r.get("problemas") and not r.get("invariantes")]
if rotas:
    print("ROMPE " + " ".join(sorted(rotas)[:20]))
elif not fieles:
    print("NADA ningún documento quedó fiel")
else:
    print("OK " + " ".join(fieles))
PY
)
  case "$veredicto" in
    ROMPE*) descartar "rompe la cobertura de: ${veredicto#ROMPE }"; return 0 ;;
    NADA*)  descartar "${veredicto#NADA }"; return 0 ;;
    OK\ ?*) ;;
    # Un veredicto que no salió (falta nuevo.json, la muestra falló) no es OK.
    *)      descartar "no se pudo evaluar el arreglo (reevaluación o muestra fallida)"; return 0 ;;
  esac
  echo "${veredicto#OK }" > "$TRABAJO/arreglo-ok.txt"
  # El arreglo cambia el extractor de todo lo publicado: se reconstruye cada
  # documento desde su PDF y cada unidad que cambie tiene que confirmarse como
  # mejora antes de que el arreglo entre.
  rm -rf "$IMPACTO"
  python scripts/impacto_corpus.py --trabajo "$IMPACTO" --federal "$(git -C "$OUT" rev-parse --show-toplevel)" \
    --pdf-dir "$PDF_DIR" --cache "${PDF_CACHE:-/tmp/pdfs-corpus}" > "$TRABAJO/impacto-arreglo.log" 2>&1
  rc=$?
  cat "$TRABAJO/impacto-arreglo.log"
  case "$rc" in
    0) echo listo > "$TRABAJO/arreglo-estado.txt" ;;
    # 1 es "hay correcciones por verificar" solo si dejó qué verificar.
    1) if [ -s "$IMPACTO/pendientes.json" ]; then echo impacto > "$TRABAJO/arreglo-estado.txt"
       else descartar "la medición del impacto falló sin dejar qué verificar"; fi ;;
    *) descartar "en el resto del corpus: $(grep '^✗' "$TRABAJO/impacto-arreglo.log" | head -3 | tr '\n' ' ')" ;;
  esac
}

publicar() {
  estado="$(cat "$TRABAJO/arreglo-estado.txt" 2>/dev/null || echo ninguno)"
  if [ "$estado" = impacto ]; then
    if python scripts/impacto.py cerrar --trabajo "$IMPACTO" \
        --extractor "OpenCodice/fiscal-extractor@$(git rev-parse HEAD)" \
        --reporte "$TRABAJO/impacto-arreglo.md"; then
      estado=listo
    else
      descartar "no todo lo que cambia en el corpus quedó confirmado como mejora: $(tail -n +2 "$TRABAJO/impacto-arreglo.md" | head -c 400)"
    fi
  fi
  [ "$estado" = listo ] && [ -s "$TRABAJO/arreglo-ok.txt" ] || return 0
  reparados="$(cat "$TRABAJO/arreglo-ok.txt")"
  if [ -z "${EXTRACTOR_PUSH_URL:-}" ] && { [ -z "${EXTRACTOR_TOKEN:-}" ] || [ -z "${EXTRACTOR_SLUG:-}" ]; }; then
    descartar "sin credenciales para publicar el arreglo en el extractor"
    return 0
  fi
  titulo="$(campo titulo_commit)"
  git add -A
  # El parche se guarda antes de publicar: si falla, no se pierde.
  git diff --cached > "$TRABAJO/arreglo.patch"
  partida="$(git rev-parse HEAD)"
  # La identidad vale también para el rebase, no solo para el commit.
  export GIT_AUTHOR_NAME="Claude (agente OpenCodice)" GIT_COMMITTER_NAME="Claude (agente OpenCodice)"
  export GIT_AUTHOR_EMAIL="noreply@anthropic.com"
  export GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"
  git commit -q -m "Reparación automática (leyes federales): ${titulo:-ajuste del extractor a un formato de PDF}"
  destino="${EXTRACTOR_PUSH_URL:-https://x-access-token:${EXTRACTOR_TOKEN:-}@github.com/${EXTRACTOR_SLUG:-}.git}"
  # main recibe pushes de otras corridas: si avanzó entre el rebase y el push,
  # se rebasa otra vez.
  subido=false
  for vuelta in 1 2 3; do
    if git pull -q --rebase "$destino" main && git push -q "$destino" HEAD:main; then
      subido=true
      break
    fi
    git rebase --abort 2>/dev/null || true
    [ "$vuelta" = 3 ] || sleep $((vuelta * 5))
  done
  if [ "$subido" = true ]; then
    # shellcheck disable=SC2086
    python - "$TRABAJO" "$titulo" "$(git rev-parse HEAD)" $reparados <<'PY'
import json, sys
t, titulo, sha, *reparados = sys.argv[1:]
json.dump({"reparados": reparados, "titulo": titulo, "sha": sha},
          open(f"{t}/reparacion.json", "w"), ensure_ascii=False)
PY
    echo "Arreglo publicado; quedaron fieles: $reparados"
  else
    git rebase --abort 2>/dev/null || true
    git reset -q --hard "$partida"
    cp "$TRABAJO/arreglo.patch" "$TRABAJO/arreglo-descartado.patch"
    descartar "no se pudo publicar el arreglo en el extractor"
  fi
}

notas() {
  python - "$TRABAJO" <<'PY'
import json, pathlib, sys
t = pathlib.Path(sys.argv[1])
try:
    v = json.loads((t / "veredicto.json").read_text(encoding="utf-8"))
except Exception:
    v = None
l = []
if v is None:
    l.append("El agente no entregó veredicto.")
else:
    l.append(str(v.get("resumen", "")))
    if (t / "reparacion.json").exists():
        l += ["", f"🔧 Arreglo publicado en el extractor: _{v.get('titulo_commit', '')}_"]
    l.append("")
    for d in v.get("documentos", [])[:60]:
        l.append(f"- `{d.get('clave')}` — {d.get('nota', '')}")
if (t / "impacto-arreglo.md").exists():
    l += ["", "Impacto del arreglo en el resto del corpus: "
          + (t / "impacto-arreglo.md").read_text(encoding="utf-8").strip()]
if (t / "descarte.txt").exists():
    l += ["", f"⚠️ Se descartó el arreglo del agente: {(t / 'descarte.txt').read_text().strip()}."]
(t / "notas-agente.md").write_text("\n".join(l) + "\n", encoding="utf-8")
PY
}

case "$FASE" in
  compuertas) compuertas ;;
  publicar) publicar; notas ;;
  *) echo "fase desconocida: $FASE" >&2; exit 64 ;;
esac
exit 0
