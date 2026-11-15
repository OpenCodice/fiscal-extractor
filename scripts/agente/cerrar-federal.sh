#!/usr/bin/env bash
# Compuertas deterministas después del agente en el corpus federal. Restaura el
# repo de datos (el agente no puede tocarlo), decide si su arreglo se publica en
# el extractor y deja `resultados.json` con la auditoría que vale.
#
# Entorno: OUT, PDF_DIR, PLAN; opcionales AGENTE_DIR, EXTRACTOR_TOKEN +
# EXTRACTOR_SLUG (para publicar el arreglo), EXTRACTOR_PUSH_URL (destino
# alterno, para pruebas).
set -uo pipefail

EXTRACTOR="$(cd "$(dirname "$0")/../.." && pwd)"
TRABAJO="${AGENTE_DIR:-/tmp/agente}"
cd "$EXTRACTOR"
export PYTHONPATH="$EXTRACTOR"

[ -d "$TRABAJO/datos-antes" ] || exit 0       # el agente no intervino

restaurar() {
  rsync -a --delete --exclude .git "$TRABAJO/datos-antes/" "$OUT/"
  cp "$TRABAJO/resultados-antes.json" "$TRABAJO/resultados.json"
}

descartar() {
  echo "::warning::Arreglo del agente descartado: $1"
  echo "$1" > "$TRABAJO/descarte.txt"
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

restaurar

if [ -z "$(git status --porcelain)" ]; then
  echo "El agente no cambió el extractor."
else
  pip install -q pytest > /dev/null 2>&1 || true
  if ! python -m pytest -q > "$TRABAJO/pytest.log" 2>&1; then
    descartar "las pruebas no pasan"
  else
    python -m extractor federal reevaluar --plan "$PLAN" --out "$OUT" --pdf-dir "$PDF_DIR" \
      --trabajo "$TRABAJO" --json "$TRABAJO/nuevo.json"
    bash "$EXTRACTOR/scripts/agente/muestra-federal.sh" "$TRABAJO/muestra-nuevo.json"
    veredicto=$(python - "$TRABAJO" <<'PY'
import json, sys
t = sys.argv[1]
cargar = lambda n: json.load(open(f"{t}/{n}"))
base = set(cargar("base.json")["con_problemas"])
nuevo = cargar("nuevo.json")
rotas = set(nuevo["con_problemas"]) - base
try:
    rotas |= set(cargar("muestra-nuevo.json")["con_problemas"]) - set(cargar("muestra-base.json")["con_problemas"])
except FileNotFoundError:
    pass
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
      ROMPE*) descartar "rompe la cobertura de: ${veredicto#ROMPE }" ;;
      NADA*)  descartar "${veredicto#NADA }" ;;
      OK*)
        reparados="${veredicto#OK }"
        if [ -z "${EXTRACTOR_PUSH_URL:-}" ] && { [ -z "${EXTRACTOR_TOKEN:-}" ] || [ -z "${EXTRACTOR_SLUG:-}" ]; }; then
          descartar "sin credenciales para publicar el arreglo en el extractor"
        else
          titulo="$(campo titulo_commit)"
          git add -A
          # El parche se guarda antes de publicar: si falla, no se pierde.
          git diff --cached > "$TRABAJO/arreglo.patch"
          partida="$(git rev-parse HEAD)"
          # La identidad vale también para el rebase, no solo para el commit.
          export GIT_AUTHOR_NAME="${GITHUB_ACTOR:-opencodice-ci}" GIT_COMMITTER_NAME="${GITHUB_ACTOR:-opencodice-ci}"
          export GIT_AUTHOR_EMAIL="${GITHUB_ACTOR_ID:-0}+${GITHUB_ACTOR:-opencodice-ci}@users.noreply.github.com"
          export GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"
          git commit -q -m "Reparación automática (leyes federales): ${titulo:-ajuste del extractor a un formato de PDF}"
          destino="${EXTRACTOR_PUSH_URL:-https://x-access-token:${EXTRACTOR_TOKEN:-}@github.com/${EXTRACTOR_SLUG:-}.git}"
          if git pull -q --rebase "$destino" main && git push -q "$destino" HEAD:main; then
            python - "$TRABAJO" "$titulo" $reparados <<'PY'
import json, sys
t, titulo, *reparados = sys.argv[1:]
json.dump({"reparados": reparados, "titulo": titulo}, open(f"{t}/reparacion.json", "w"),
          ensure_ascii=False)
PY
            echo "Arreglo publicado; quedaron fieles: $reparados"
          else
            git rebase --abort 2>/dev/null || true
            git reset -q --hard "$partida"
            cp "$TRABAJO/arreglo.patch" "$TRABAJO/arreglo-descartado.patch"
            descartar "no se pudo publicar el arreglo en el extractor"
          fi
        fi
        ;;
    esac
  fi
fi

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
if (t / "descarte.txt").exists():
    l += ["", f"⚠️ Se descartó el arreglo del agente: {(t / 'descarte.txt').read_text().strip()}."]
(t / "notas-agente.md").write_text("\n".join(l) + "\n", encoding="utf-8")
PY
exit 0
