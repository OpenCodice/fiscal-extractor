#!/usr/bin/env bash
# Revisión completa, por bloques, de las leyes nuevas (federales o estatales)
# que pasaron las compuertas deterministas (scripts/revision.py). Dos fases:
#
#   revision-federal.sh revisar — con CLAUDE_CODE_OAUTH_TOKEN y nada más. El
#     agente revisa cada alta contra su PDF; aquí no repara el extractor (ya
#     pasó sus compuertas en esta corrida): lo que encuentre deja el alta
#     fuera, con su motivo.
#   revision-federal.sh cerrar — determinista. Anota en resultados.json el
#     motivo de cada alta que no quedó sin hallazgos (`revision`, que
#     `federal cerrar` excluye) y aplaza las que no cupieron en la corrida o
#     cuya revisión quedó a medias (`aplazada`): la siguiente corrida la retoma
#     (con los veredictos ya hechos, si el workflow guarda $AGENTE_DIR/revision
#     en caché). Con EXTRACTOR_TOKEN publica el registro de revisiones.
#
# Entorno: OUT, PDF_DIR, PLAN; opcionales AGENTE_DIR, REVISION_MAX_ALTAS,
# REVISION_MAX_CARACTERES (tope del texto de las altas que se revisan en una
# corrida: las demás se aplazan; la primera siempre entra), REVISION_BRIEF
# (brief de scripts/agente/), REVISION_CORPUS (para el mensaje del registro),
# REVISION_POR_SESION, REVISION_SESIONES, AGENTE_MAX_TURNOS, AGENTE_MODELO.
set -uo pipefail

FASE="${1:?uso: revision-federal.sh revisar|cerrar}"
EXTRACTOR="$(cd "$(dirname "$0")/../.." && pwd)"
TRABAJO="${AGENTE_DIR:-/tmp/agente}"
cd "$EXTRACTOR"
export PYTHONPATH="$EXTRACTOR"
source scripts/agente/sesion.sh

# Altas fieles de esta corrida, en orden; se revisan ahora las primeras
# REVISION_MAX_ALTAS mientras su texto no pase de REVISION_MAX_CARACTERES.
if python3 - "$TRABAJO" "${REVISION_MAX_ALTAS:-3}" "${REVISION_MAX_CARACTERES:-0}" "$OUT" "$PLAN" <<'PY'
import json, pathlib, sys
from extractor import federal
from extractor.disposicion import dir_unidades
t, maximo, tope, out = pathlib.Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
plan = json.loads(pathlib.Path(sys.argv[5]).read_text(encoding="utf-8"))
res = json.loads((t / "resultados.json").read_text(encoding="utf-8"))
fuentes = pathlib.Path(out) / "fuentes.json"
incluidas = {d["clave"] for d in json.loads(fuentes.read_text(encoding="utf-8"))["documentos"]
             if d.get("estado") == "incluida"} if fuentes.exists() else set()
# Las altas (todo lo que no está publicado, sea cual sea el motivo del plan) y
# lo publicado que el plan manda revisar (`revisar`).
altas = [c for c, r in sorted(res.items())
         if (c not in incluidas or r.get("motivo") in ("nuevo", "reintento")
             or c in plan.get("revisar", []))
         and not r.get("error_fuente") and not r.get("sin_cambio") and federal.es_fiel(r)]
# De la más corta a la más larga: en una corrida caben más altas, y una ley
# larga no detiene a las cortas que vienen detrás.
tamano = {c: sum(p.stat().st_size for p in dir_unidades(out, c).glob("*.md")) for c in altas}
altas.sort(key=lambda c: (tamano[c], c))
ahora, suma = [], 0
for c in altas:
    tam = tamano[c]
    if len(ahora) >= maximo or (ahora and tope and suma + tam > tope):
        break
    ahora.append(c)
    suma += tam
(t / "altas.txt").write_text("".join(f"{c}\n" for c in ahora), encoding="utf-8")
(t / "altas-aplazadas.txt").write_text("".join(f"{c}\n" for c in altas[len(ahora):]), encoding="utf-8")
PY
then :; else
  # Sin la lista de altas no se sabe qué revisar: nada se da por revisado.
  echo "::error::No se pudo elegir las altas que se revisan." >&2
  exit 1
fi
[ -s "$TRABAJO/altas.txt" ] || [ -s "$TRABAJO/altas-aplazadas.txt" ] || { echo "Sin altas que revisar."; exit 0; }
RAIZ="$(git -C "$OUT" rev-parse --show-toplevel)"

revisar_doc() {
    local doc="$1" REV="$TRABAJO/revision/$1" previa sesion n
    mkdir -p "$REV"
    previa="$(python scripts/revision.py previa --documento "$doc" --pdf "$PDF_DIR/$doc.pdf")"
    if [ -n "$previa" ] && [ "$(echo "$previa" | python3 -c 'import json,sys; print(json.load(sys.stdin)["resultado"])')" != fiel ]; then
      echo "$previa" > "$REV/previa.json"
      return
    fi
    for sesion in $(seq 1 "${REVISION_SESIONES:-8}"); do
      # Numera el veredicto tras los que ya haya (de una corrida anterior, si la
      # carpeta viene de la caché): ninguno se sobrescribe.
      n=$(( $(find "$REV" -maxdepth 1 -name 'veredicto-*.json' | wc -l) + 1 ))
      python scripts/revision.py planear --repo "$RAIZ" --documento "$doc" --pdf "$PDF_DIR/$doc.pdf" --trabajo "$REV"
      python3 scripts/agente/brief_revision.py "$REV" "$n" "${REVISION_POR_SESION:-8}" \
        __BRIEF__="${REVISION_BRIEF:-brief-revision-federal.md}" __EXTRACTOR__="$EXTRACTOR" __OUT__="$RAIZ" \
        __PDF__="$PDF_DIR/$doc.pdf" __DOCUMENTO__="$doc"
      [ -s "$REV/brief.md" ] || break
      (cd "$REV" && sesion_agente revision-alta "$TRABAJO/uso.jsonl" "$REV/brief.md" "$doc" \
        --max-turns "${AGENTE_MAX_TURNOS:-120}" \
        --permission-mode acceptEdits \
        --allowedTools Bash Read Write Glob Grep \
        >> "$REV/agente.log" 2>&1) || echo "::warning::La revisión de $doc terminó con error."
    done
}

revisar() {
  command -v claude > /dev/null || npm install -g @anthropic-ai/claude-code > /dev/null
  # REVISION_PARALELO altas a la vez (cada una en su propia carpeta de trabajo).
  local max="${REVISION_PARALELO:-1}"
  while IFS= read -r doc; do
    [ -n "$doc" ] || continue
    while [ "$(jobs -rp | wc -l)" -ge "$max" ]; do wait -n; done
    revisar_doc "$doc" &
  done < "$TRABAJO/altas.txt"
  wait
  # Esta revisión no cambia código: lo que haya tocado se deshace.
  git checkout -q -- extractor tests 2>/dev/null; git clean -fdq -- extractor tests
}

cerrar() {
  while IFS= read -r doc; do
    [ -n "$doc" ] || continue
    REV="$TRABAJO/revision/$doc"
    if [ -s "$REV/previa.json" ]; then
      motivo="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["motivo"])' "$REV/previa.json")" \
        && [ -n "$motivo" ] || motivo="APLAZADA"
    else
      motivo="$(python scripts/revision.py cerrar --repo "$RAIZ" --documento "$doc" \
        --pdf "$PDF_DIR/$doc.pdf" --trabajo "$REV")"
      rc=$?
      motivo="${motivo#✗ }"
      if [ "$rc" = 0 ]; then
        motivo=""
      elif [ "$rc" != 2 ] || [ -z "$motivo" ]; then
        # El cierre falló (sin PDF, un error): no hay revisión, no un "sin
        # hallazgos". Se aplaza.
        echo "::warning::No se pudo cerrar la revisión de $doc (código $rc)." >&2
        motivo="APLAZADA"
      elif grep -q '"resultado": "incompleta"' "$REV/resultado.json" 2>/dev/null; then
        motivo="APLAZADA"      # a medias (se acabó el tiempo, falló el agente)
      fi
    fi
    printf '%s\t%s\n' "$doc" "$motivo"
  done < "$TRABAJO/altas.txt" > "$TRABAJO/revisiones.tsv"
  if python3 - "$TRABAJO" <<'PY'
import json, pathlib, sys
t = pathlib.Path(sys.argv[1])
res = json.loads((t / "resultados.json").read_text(encoding="utf-8"))
for linea in (t / "revisiones.tsv").read_text(encoding="utf-8").splitlines():
    clave, _, motivo = linea.partition("\t")
    if motivo == "APLAZADA":
        res[clave]["aplazada"] = True
        print(f"… {clave}: su revisión completa quedó a medias; sigue en la siguiente corrida")
    elif motivo:
        res[clave]["revision"] = motivo
        print(f"✗ {clave}: {motivo}")
    else:
        # La marca positiva: sin ella `federal cerrar` no publica un alta.
        res[clave]["revisada"] = True
        print(f"✓ {clave}: revisión completa sin hallazgos")
for clave in (t / "altas-aplazadas.txt").read_text(encoding="utf-8").split():
    res[clave]["aplazada"] = True
    print(f"… {clave}: su revisión completa queda para la siguiente corrida")
(t / "resultados.json").write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
  then :; else
    echo "::error::No se pudo anotar el resultado de la revisión de las altas." >&2
    exit 1
  fi
  bash scripts/agente/publicar_registro.sh "Revisión completa de las altas de ${REVISION_CORPUS:-leyes federales}"
}

case "$FASE" in
  revisar) revisar ;;
  cerrar) cerrar ;;
  *) echo "fase desconocida: $FASE" >&2; exit 64 ;;
esac
