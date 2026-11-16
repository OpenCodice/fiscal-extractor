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
  git diff > "$TRABAJO/arreglo-descartado.patch" || true
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
      if git push -q "$destino" HEAD:main; then
        reparado=true
      else
        git reset -q --hard HEAD~1
        descartar "no se pudo publicar el arreglo en el extractor"
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
import json, os, pathlib, subprocess, sys
trabajo, reporte, ok, reparado, descarte, out_dir = sys.argv[1:7]
t = pathlib.Path(trabajo)
try:
    v = json.loads((t / "veredicto.json").read_text(encoding="utf-8"))
except Exception:
    v = None
# Asunto del commit de datos: distingue reforma real de corrección de extracción.
cambiadas = set()
for l in subprocess.run(["git", "-C", out_dir, "status", "--porcelain", "--no-renames", "-uall"],
                        capture_output=True, text=True).stdout.splitlines():
    r = pathlib.Path(l[3:].strip().strip('"'))
    if r.suffix == ".md" and len(r.parts) == 2 and r.parts[0] not in ("metadata", "scripts"):
        cambiadas.add(f"{r.parts[0]}/{r.stem}")
reformadas = set(map(str, (v or {}).get("reformadas", []))) & cambiadas
correcciones = cambiadas - reformadas


def por_doc(refs):
    n = {}
    for r in refs:
        n[r.split("/")[0]] = n.get(r.split("/")[0], 0) + 1
    return ", ".join(f"{d} ({c})" for d, c in sorted(n.items()))


if reformadas:
    asunto = f"Actualización del corpus fiscal: {por_doc(reformadas)}"
    if correcciones:
        asunto += f" (+{len(correcciones)} correcciones de extracción)"
    tipo = "reforma"
elif correcciones:
    asunto = f"Corrección de extracción del corpus fiscal: {por_doc(correcciones)}"
    tipo = "correccion"
else:
    asunto, tipo = "Actualización de metadata del corpus fiscal", "metadata"

# Título del commit de cada documento (scripts/commits_por_documento.py): el
# historial de cada carpeta cuenta solo su propia historia.
try:
    docs = json.loads(pathlib.Path(out_dir, "metadata", "documentos.json").read_text(encoding="utf-8"))
    docs = {d["clave"]: d for d in (docs["documentos"] if isinstance(docs, dict) else docs)}
except Exception:
    docs = {}


def arts(unidades):
    u = sorted(x.split("/", 1)[1] for x in unidades)
    if len(u) > 12:
        return f"{len(u)} unidades"
    return ("art. " if len(u) == 1 else "arts. ") + ", ".join(x.lstrip("0") or "0" for x in u)


asuntos = {}
for doc in sorted({c.split("/")[0] for c in cambiadas}):
    sigla = docs.get(doc, {}).get("sigla") or doc.upper()
    ref = sorted(c for c in reformadas if c.startswith(doc + "/"))
    cor = sorted(c for c in correcciones if c.startswith(doc + "/"))
    if ref:
        version = docs.get(doc, {}).get("version")
        asuntos[doc] = f"Reforma {sigla}{f' ({version})' if version else ''}: {arts(ref)}"
        if cor:
            asuntos[doc] += f" (+{len(cor)} correcciones de extracción)"
    else:
        asuntos[doc] = f"Corrección de extracción {sigla}: {arts(cor)}"
(t / "asuntos.json").write_text(json.dumps(asuntos, ensure_ascii=False, indent=1), encoding="utf-8")

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
if ok == "true":
    out += ["", f"<!-- asunto: {asunto} -->"]
if os.environ.get("GITHUB_OUTPUT"):
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
        fh.write(f"tipo={tipo}\n")
pathlib.Path(reporte).write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out))
PY

[ "$ok" = "true" ] && exit 0 || exit 2
