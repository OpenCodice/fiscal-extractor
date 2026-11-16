#!/usr/bin/env bash
# Compuertas deterministas después del agente. Garantiza que el texto del repo
# de datos sale solo del extractor, decide si el arreglo del agente se publica
# y emite el veredicto final. Sale 0 si todo quedó fiel, 2 si no.
#
# Entorno: OUT, PDF_DIR; opcionales AGENTE_DIR, REPORTE, EXTRACTOR_TOKEN +
# EXTRACTOR_SLUG (para publicar el arreglo), EXTRACTOR_PUSH_URL (destino
# alterno, para pruebas).
set -uo pipefail

EXTRACTOR="$(cd "$(dirname "$0")/../.." && pwd)"
TRABAJO="${AGENTE_DIR:-/tmp/agente}"
REPORTE="${REPORTE:-/tmp/verificacion.md}"
cd "$EXTRACTOR"
export PYTHONPATH="$EXTRACTOR"
source scripts/agente/comun.sh

if [ ! -s "$TRABAJO/cambiados.txt" ]; then
  exit 0
fi

regenerar() {
  git -C "$OUT" checkout -q -- . && git -C "$OUT" clean -fdq
  python -m extractor build --pdf-dir "$PDF_DIR" --out "$OUT" > /dev/null
}

descartar() {
  echo "::warning::Arreglo del agente descartado: $1"
  motivo_descarte="$1"
  [ -s "$TRABAJO/arreglo-descartado.patch" ] || git diff > "$TRABAJO/arreglo-descartado.patch" || true
  git checkout -q -- . && git clean -fdq
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

reparado=false
motivo_descarte=""
# La vigilancia corre en este mismo repo: el agente solo puede publicar cambios
# al extractor y a sus pruebas, nunca a workflows, scripts ni Workers. Archivos
# nuevos sueltos (copias de PDF, notas de trabajo) no se publican.
git ls-files --others --exclude-standard | grep -vE '^(extractor|tests)/' | while IFS= read -r f; do rm -f -- "$f"; done
fuera=$( { git diff --name-only HEAD; git ls-files --deleted; } | sort -u | grep -vE '^(extractor|tests)/' || true)
if [ -n "$fuera" ]; then
  descartar "toca archivos fuera de extractor/ y tests/: $(echo "$fuera" | head -3 | tr '\n' ' ')"
fi
if [ -n "$(git status --porcelain)" ]; then
  pip install -q pytest > /dev/null 2>&1 || true
  if ! python -m pytest -q > "$TRABAJO/pytest.log" 2>&1; then
    descartar "las pruebas no pasan"
    regenerar
  else
    regenerar
    python -m extractor auditar --out "$OUT" --pdf-dir "$PDF_DIR" \
      --json "$TRABAJO/nuevo.json" > /dev/null
    nuevas=$(python - "$TRABAJO" <<'PY'
import json, sys
t = sys.argv[1]
base = set(json.load(open(f"{t}/base.json"))["con_problemas"])
nuevo = set(json.load(open(f"{t}/nuevo.json"))["con_problemas"])
print(" ".join(sorted(nuevo - base)[:20]))
PY
)
    if [ -n "$nuevas" ]; then
      descartar "rompe la cobertura de: $nuevas"
      regenerar
    elif [ -z "${EXTRACTOR_PUSH_URL:-}" ] && { [ -z "${EXTRACTOR_TOKEN:-}" ] || [ -z "${EXTRACTOR_SLUG:-}" ]; }; then
      descartar "sin credenciales para publicar el arreglo en el extractor"
      regenerar
    else
      titulo="$(campo titulo_commit)"
      git add -A
      git -c user.name="${GITHUB_ACTOR:-opencodice-ci}" \
          -c user.email="${GITHUB_ACTOR_ID:-0}+${GITHUB_ACTOR:-opencodice-ci}@users.noreply.github.com" \
          commit -q -m "Reparación automática: ${titulo:-ajuste del extractor a un cambio de formato del PDF}"
      destino="${EXTRACTOR_PUSH_URL:-https://x-access-token:${EXTRACTOR_TOKEN:-}@github.com/${EXTRACTOR_SLUG:-}.git}"
      # Otras corridas (un job por estado) pueden haber publicado su propio
      # arreglo mientras tanto: se rebasa sobre el main más reciente.
      export GIT_AUTHOR_NAME="${GITHUB_ACTOR:-opencodice-ci}" GIT_COMMITTER_NAME="${GITHUB_ACTOR:-opencodice-ci}"
      export GIT_AUTHOR_EMAIL="${GITHUB_ACTOR_ID:-0}+${GITHUB_ACTOR:-opencodice-ci}@users.noreply.github.com"
      export GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"
      if git pull -q --rebase "$destino" main && git push -q "$destino" HEAD:main; then
        reparado=true
      else
        git rebase --abort 2>/dev/null || true
        # El arreglo ya está en un commit: se guarda antes de deshacerlo.
        git format-patch -1 --stdout > "$TRABAJO/arreglo-descartado.patch" || true
        git reset -q --hard HEAD~1
        descartar "no se pudo publicar el arreglo en el extractor (chocó con otro arreglo publicado mientras tanto)"
        regenerar
      fi
    fi
  fi
elif [ "$(huella_datos)" != "$(cat "$TRABAJO/datos.sha")" ]; then
  echo "::warning::El repo de datos cambió durante la sesión del agente: se regenera."
  regenerar
fi

python -m extractor verificar --sin-llm --out "$OUT" --pdf-dir "$PDF_DIR" \
  --reporte "$TRABAJO/cobertura-final.md" > /dev/null
cobertura_ok=$?
fiel="$(campo fiel)"

ok=false
if [ "$cobertura_ok" -eq 0 ] && [ "$fiel" = "true" ] && [ -z "$motivo_descarte" ]; then
  ok=true
fi

python - "$TRABAJO" "$REPORTE" "$ok" "$reparado" "$motivo_descarte" "$OUT" <<'PY'
import json, pathlib, sys
trabajo, reporte, ok, reparado, descarte, out_dir = sys.argv[1:7]
t = pathlib.Path(trabajo)
try:
    v = json.loads((t / "veredicto.json").read_text(encoding="utf-8"))
except Exception:
    v = None
icono = {"fiel": "✅", "artefacto": "❌", "incierto": "❔"}
out = ["### 🤖 Verificación del agente contra los PDF", ""]
if ok == "true":
    out.append("La extracción quedó verificada: reproduce fielmente los PDF oficiales.")
else:
    out.append("**La extracción NO quedó verificada — no mergear sin revisar.**")
if v is None:
    out += ["", "El agente no entregó veredicto."]
else:
    out += ["", str(v.get("resumen", ""))]
    if reparado == "true":
        out += ["", f"🔧 El agente reparó el extractor: _{v.get('titulo_commit', '')}_"]
    out.append("")
    for u in v.get("unidades", [])[:80]:
        out.append(f"- {icono.get(u.get('veredicto'), '❔')} **{u.get('clave')}** — {u.get('nota', '')}")
if descarte:
    out += ["", f"⚠️ Se descartó un arreglo del agente: {descarte}."]
out += ["", (t / "cobertura-final.md").read_text(encoding="utf-8")]
pathlib.Path(reporte).write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out))
PY

[ "$ok" = "true" ] && exit 0 || exit 2
