#!/usr/bin/env bash
# Lanza al agente (Claude Code) para confirmar contra el PDF que cada
# corrección de extracción pendiente (las que dejó `impacto.py` o
# `impacto_corpus.py` en $IMPACTO/pendientes.json) es una mejora. Solo juzga:
# el veredicto lo pasa al registro `impacto.py cerrar`. Los grupos se reparten
# en sesiones de IMPACTO_POR_SESION, hasta IMPACTO_SESIONES sesiones; lo que no
# alcance queda sin verificar y no se publica.
#
# Entorno: IMPACTO (directorio de trabajo), CLAUDE_CODE_OAUTH_TOKEN; opcionales
# IMPACTO_POR_SESION, IMPACTO_SESIONES, AGENTE_MAX_TURNOS, AGENTE_MODELO. Este
# paso no debe recibir ningún otro secreto: el agente lee PDFs externos.
#
# Este archivo existe idéntico en constitucion-extractor y en fiscal-extractor.
set -euo pipefail

EXTRACTOR="$(cd "$(dirname "$0")/../.." && pwd)"
POR_SESION="${IMPACTO_POR_SESION:-40}"
SESIONES="${IMPACTO_SESIONES:-4}"
if [ ! -s "$IMPACTO/pendientes.json" ]; then
  echo "Sin correcciones por verificar."
  exit 0
fi
command -v claude > /dev/null || npm install -g @anthropic-ai/claude-code > /dev/null
source "$EXTRACTOR/scripts/agente/sesion.sh"

for n in $(seq 1 "$SESIONES"); do
  # El brief de la sesión: los grupos que aún no tienen veredicto.
  python3 - "$IMPACTO" "$EXTRACTOR" "$n" "$POR_SESION" <<'PY'
import json, pathlib, sys
t, extractor, n, por_sesion = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3], int(sys.argv[4])
p = json.loads((t / "pendientes.json").read_text(encoding="utf-8"))
hechos = set()
for f in t.glob("veredicto*.json"):
    try:
        hechos |= {g.get("id") for g in json.loads(f.read_text(encoding="utf-8")).get("grupos", [])}
    except Exception:
        pass
lote = [g for g in p["grupos"] if g["id"] not in hechos][:por_sesion]
brief_p = t / "brief.md"
brief_p.unlink(missing_ok=True)
if not lote:
    sys.exit(0)
(t / "documentos-sesion.txt").write_text(
    " ".join(sorted({m["documento"] for g in lote for m in g["miembros"]})), encoding="utf-8")
lineas = [f"{len(lote)} grupos en esta sesión ({p['resumen']['grupos']} en total):"]
for g in lote:
    docs = sorted({m["documento"] for m in g["miembros"]})
    lineas.append(f"{g['id']}: {len(g['miembros'])} artículos de {', '.join(docs[:4])}"
                  + (f" y {len(docs) - 4} más" if len(docs) > 4 else ""))
brief = pathlib.Path(extractor, "scripts/agente/brief-impacto.md").read_text(encoding="utf-8")
for k, v in {"__ORIGEN__": p["resumen"].get("origen") or "un cambio del extractor",
             "__PENDIENTES__": str(t / "pendientes.json"), "__TRABAJO__": str(t),
             "__VEREDICTO__": str(t / f"veredicto-{int(n):02d}.json"),
             "__RESUMEN__": "\n".join(lineas)}.items():
    brief = brief.replace(k, v)
brief_p.write_text(brief, encoding="utf-8")
PY
  [ -s "$IMPACTO/brief.md" ] || break
  # Desde el directorio de trabajo, no desde el extractor: este agente no
  # edita código.
  (cd "$IMPACTO" && sesion_agente impacto "$IMPACTO/uso.jsonl" "$IMPACTO/brief.md" \
      "$(cat "$IMPACTO/documentos-sesion.txt" 2>/dev/null || true)" \
    --max-turns "${AGENTE_MAX_TURNOS:-120}" \
    --permission-mode acceptEdits \
    --allowedTools Bash Read Write Glob Grep \
    > "$IMPACTO/agente-$n.log" 2>&1) || echo "::warning::El agente de impacto terminó con error (ver $IMPACTO/agente-$n.log)."
  tail -n 5 "$IMPACTO/agente-$n.log" || true
done
