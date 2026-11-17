#!/usr/bin/env bash
# Compuertas deterministas después del agente, en dos fases (dos pasos del
# workflow, con el agente de impacto entre ellas):
#
#   cerrar.sh compuertas — sin secretos. Si el agente cambió el extractor:
#     pruebas, cobertura del corpus fiscal sin regresiones y el impacto del
#     arreglo en TODO lo publicado (fiscal-mexicano y leyes-federales,
#     scripts/impacto_corpus.py). Deja en $TRABAJO/arreglo.json si el arreglo
#     se descarta, está listo o espera a que el agente de impacto confirme sus
#     correcciones ($TRABAJO/impacto-arreglo/pendientes.json).
#   cerrar.sh publicar — con EXTRACTOR_TOKEN. Pasa al registro el veredicto de
#     impacto, publica el arreglo solo si cada unidad publicada que cambia es
#     una mejora, garantiza que el texto sale solo del extractor y emite el
#     veredicto final. Un documento nuevo (alta) que no pasó su revisión
#     completa por bloques (scripts/revision.py) se quita del corpus de esta
#     corrida; el resto sigue.
#
# publicar sale 0 si todo quedó fiel, 2 si no; compuertas sale 0.
#
# Entorno: OUT, PDF_DIR; opcionales AGENTE_DIR, REPORTE, PDF_CACHE,
# EXTRACTOR_TOKEN + EXTRACTOR_SLUG (para publicar el arreglo), EXTRACTOR_PUSH_URL
# (destino alterno, para pruebas).
set -uo pipefail

FASE="${1:?uso: cerrar.sh compuertas|publicar}"
EXTRACTOR="$(cd "$(dirname "$0")/../.." && pwd)"
TRABAJO="${AGENTE_DIR:-/tmp/agente}"
REPORTE="${REPORTE:-/tmp/verificacion.md}"
IMPACTO="$TRABAJO/impacto-arreglo"
cd "$EXTRACTOR"
export PYTHONPATH="$EXTRACTOR"
source scripts/agente/comun.sh

if [ ! -s "$TRABAJO/cambiados.txt" ] && [ ! -s "$TRABAJO/altas.txt" ]; then
  exit 0
fi

regenerar() {
  git -C "$OUT" checkout -q -- . && git -C "$OUT" clean -fdq
  python -m extractor build --pdf-dir "$PDF_DIR" --out "$OUT" > /dev/null
}

estado_arreglo() {
  python3 - "$TRABAJO/arreglo.json" "$@" <<'PY'
import json, sys
ruta, *par = sys.argv[1:]
if par:
    json.dump({"estado": par[0], "motivo": par[1] if len(par) > 1 else ""}, open(ruta, "w"),
              ensure_ascii=False)
else:
    try:
        d = json.load(open(ruta))
    except Exception:
        d = {"estado": "ninguno", "motivo": ""}
    print(d["estado"] + "\t" + d.get("motivo", ""))
PY
}

descartar() {
  echo "::warning::Arreglo del agente descartado: $1"
  [ -s "$TRABAJO/arreglo-descartado.patch" ] || git diff > "$TRABAJO/arreglo-descartado.patch" || true
  git checkout -q -- . && git clean -fdq
  estado_arreglo descartado "$1"
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
  estado_arreglo ninguno
  # La vigilancia corre en este mismo repo: el agente solo puede publicar
  # cambios al extractor y a sus pruebas, nunca a workflows, scripts ni
  # Workers. Archivos nuevos sueltos (copias de PDF, notas) no se publican.
  git ls-files --others --exclude-standard | grep -vE '^(extractor|tests)/' | while IFS= read -r f; do rm -f -- "$f"; done
  fuera=$( { git diff --name-only HEAD; git ls-files --deleted; } | sort -u | grep -vE '^(extractor|tests)/' || true)
  if [ -n "$fuera" ]; then
    descartar "toca archivos fuera de extractor/ y tests/: $(echo "$fuera" | head -3 | tr '\n' ' ')"
  fi
  if [ -z "$(git status --porcelain)" ]; then
    if [ "$(huella_datos)" != "$(cat "$TRABAJO/datos.sha")" ]; then
      echo "::warning::El repo de datos cambió durante la sesión del agente: se regenera."
      regenerar
    fi
    return 0
  fi
  pip install -q pytest > /dev/null 2>&1 || true
  if ! python -m pytest -q > "$TRABAJO/pytest.log" 2>&1; then
    descartar "las pruebas no pasan"
    regenerar
    return 0
  fi
  regenerar
  python -m extractor auditar --out "$OUT" --pdf-dir "$PDF_DIR" --json "$TRABAJO/nuevo.json" > /dev/null
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
    return 0
  fi
  # El arreglo cambia el extractor de todo el corpus fiscal y de las leyes
  # federales: se reconstruye cada documento publicado desde su PDF y cada
  # unidad publicada que cambie tiene que confirmarse como mejora.
  rm -rf "$IMPACTO"
  python scripts/impacto_corpus.py --trabajo "$IMPACTO" --fiscal "$(git -C "$OUT" rev-parse --show-toplevel)" \
    --pdf-dir "$PDF_DIR" --cache "${PDF_CACHE:-/tmp/pdfs-corpus}" > "$TRABAJO/impacto-arreglo.log" 2>&1
  rc=$?
  cat "$TRABAJO/impacto-arreglo.log"
  case "$rc" in
    0) estado_arreglo listo ;;
    1) estado_arreglo impacto ;;
    *) descartar "en el resto del corpus: $(grep '^✗' "$TRABAJO/impacto-arreglo.log" | head -3 | tr '\n' ' ')"
       regenerar ;;
  esac
}

publicar_arreglo() {
  if [ -z "${EXTRACTOR_PUSH_URL:-}" ] && { [ -z "${EXTRACTOR_TOKEN:-}" ] || [ -z "${EXTRACTOR_SLUG:-}" ]; }; then
    descartar "sin credenciales para publicar el arreglo en el extractor"
    regenerar
    return
  fi
  titulo="$(campo titulo_commit)"
  git add -A
  git -c user.name="${GITHUB_ACTOR:-opencodice-ci}" \
      -c user.email="${GITHUB_ACTOR_ID:-0}+${GITHUB_ACTOR:-opencodice-ci}@users.noreply.github.com" \
      commit -q -m "Reparación automática: ${titulo:-ajuste del extractor a un cambio de formato del PDF}"
  destino="${EXTRACTOR_PUSH_URL:-https://x-access-token:${EXTRACTOR_TOKEN:-}@github.com/${EXTRACTOR_SLUG:-}.git}"
  export GIT_AUTHOR_NAME="${GITHUB_ACTOR:-opencodice-ci}" GIT_COMMITTER_NAME="${GITHUB_ACTOR:-opencodice-ci}"
  export GIT_AUTHOR_EMAIL="${GITHUB_ACTOR_ID:-0}+${GITHUB_ACTOR:-opencodice-ci}@users.noreply.github.com"
  export GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"
  if git pull -q --rebase "$destino" main && git push -q "$destino" HEAD:main; then
    estado_arreglo publicado
  else
    git rebase --abort 2>/dev/null || true
    # El arreglo ya está en un commit: se guarda antes de deshacerlo.
    git format-patch -1 --stdout > "$TRABAJO/arreglo-descartado.patch" || true
    git reset -q --hard HEAD~1
    descartar "no se pudo publicar el arreglo en el extractor (chocó con otro arreglo publicado mientras tanto)"
    regenerar
  fi
}

# Las altas que no quedaron sin hallazgos en su revisión completa salen del
# corpus de esta corrida (el resto se publica); su motivo queda en el reporte.
retirar_altas() {
  : > "$TRABAJO/altas-fuera.txt"
  [ -s "$TRABAJO/altas.txt" ] || return 0
  RAIZ="$(git -C "$OUT" rev-parse --show-toplevel)"
  while IFS= read -r doc; do
    [ -n "$doc" ] || continue
    rev="$TRABAJO/revision/$doc"
    if [ -s "$rev/previa.json" ]; then
      motivo="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["motivo"])' "$rev/previa.json") (revisión anterior con el mismo PDF y extractor)"
    else
      motivo="$(python scripts/revision.py cerrar --repo "$RAIZ" --documento "$doc" \
        --pdf "$PDF_DIR/$doc.pdf" --trabajo "$rev")" && motivo=""
      motivo="${motivo#✗ }"
    fi
    if [ -n "$motivo" ]; then
      echo "::warning::$doc no se publica: $motivo"
      printf '%s\t%s\n' "$doc" "$motivo" >> "$TRABAJO/altas-fuera.txt"
      rm -rf "${OUT:?}/$doc" "${OUT:?}/metadata/$doc"
    fi
  done < "$TRABAJO/altas.txt"
  if [ -s "$TRABAJO/altas-fuera.txt" ]; then
    python -c 'import sys; from extractor.build import escribir_indice_maestro; escribir_indice_maestro(sys.argv[1])' "$OUT"
  fi
  bash scripts/agente/publicar_registro.sh "Revisión completa de las altas del corpus fiscal"
}

publicar() {
  IFS=$'\t' read -r estado _ < <(estado_arreglo)
  if [ "$estado" = impacto ]; then
    if python scripts/impacto.py cerrar --trabajo "$IMPACTO" \
        --extractor "OpenCodice/fiscal-extractor@$(git rev-parse HEAD)" \
        --reporte "$TRABAJO/impacto-arreglo.md"; then
      estado=listo
    else
      descartar "no todo lo que cambia en el corpus quedó confirmado como mejora: $(tail -n +2 "$TRABAJO/impacto-arreglo.md" | head -c 400)"
      regenerar
    fi
  fi
  [ "$estado" = listo ] && publicar_arreglo
  IFS=$'\t' read -r estado motivo_descarte < <(estado_arreglo)
  [ "$estado" = descartado ] || motivo_descarte=""

  retirar_altas
  python -m extractor verificar --sin-llm --out "$OUT" --pdf-dir "$PDF_DIR" \
    --reporte "$TRABAJO/cobertura-final.md" > /dev/null
  cobertura_ok=$?
  if [ -s "$TRABAJO/cambiados.txt" ]; then fiel="$(campo fiel)"; else fiel=true; fi

  ok=false
  if [ "$cobertura_ok" -eq 0 ] && [ "$fiel" = "true" ] && [ -z "$motivo_descarte" ]; then
    ok=true
  fi

  python - "$TRABAJO" "$REPORTE" "$ok" "$estado" "$motivo_descarte" <<'PY'
import json, pathlib, sys
trabajo, reporte, ok, estado, descarte = sys.argv[1:6]
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
    out.append("**La extracción NO quedó verificada — no se publica.**")
altas = [l for l in (t / "altas.txt").read_text().splitlines() if l] if (t / "altas.txt").exists() else []
fuera = dict(l.split("\t", 1) for l in (t / "altas-fuera.txt").read_text().splitlines() if l) \
    if (t / "altas-fuera.txt").exists() else {}
for doc in altas:
    out += ["", f"Alta de `{doc}`: revisión completa por bloques contra el PDF — "
            + (f"no se publica: {fuera[doc]}" if doc in fuera else "sin hallazgos.")]
if v is None:
    if (t / "cambiados.txt").exists() and (t / "cambiados.txt").read_text().strip():
        out += ["", "El agente no entregó veredicto."]
else:
    out += ["", str(v.get("resumen", ""))]
    if estado == "publicado":
        out += ["", f"🔧 El agente reparó el extractor: _{v.get('titulo_commit', '')}_"]
    out.append("")
    for u in v.get("unidades", [])[:80]:
        out.append(f"- {icono.get(u.get('veredicto'), '❔')} **{u.get('clave')}** — {u.get('nota', '')}")
if (t / "impacto-arreglo.md").exists():
    out += ["", "Impacto del arreglo en el resto del corpus: "
            + (t / "impacto-arreglo.md").read_text(encoding="utf-8").strip()]
if descarte:
    out += ["", f"⚠️ Se descartó un arreglo del agente: {descarte}."]
out += ["", (t / "cobertura-final.md").read_text(encoding="utf-8")]
pathlib.Path(reporte).write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out))
PY

  [ "$ok" = "true" ] && return 0 || return 2
}

case "$FASE" in
  compuertas) compuertas; exit 0 ;;
  publicar) publicar; exit $? ;;
  *) echo "fase desconocida: $FASE" >&2; exit 64 ;;
esac
