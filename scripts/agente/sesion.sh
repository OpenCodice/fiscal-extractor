# Una sesión del agente (`claude -p`) con registro de su uso. Se carga con
# `source`; todos los scripts de esta carpeta lanzan al agente por aquí.
#
#   sesion_agente PASO USO BRIEF DOCUMENTOS [opciones de claude…]
#
# Lanza la sesión con el brief del archivo BRIEF y deja en stdout su texto
# final, como sin `--output-format`; stderr no se toca. Agrega a USO (un
# `uso.jsonl`) una línea con el modelo, los tokens, el costo, los turnos y la
# duración (scripts/uso.py), con PASO y DOCUMENTOS (claves separadas por
# espacio) para saber a qué se fue. Devuelve el código de salida de claude: el
# registro de uso nunca lo cambia.
#
# Entorno opcional: AGENTE_MODELO; SESION_GRUPO (el grupo o tanda de la sesión,
# para la línea de uso); SESION_CRUDO (conserva ahí la salida JSON del CLI).

SESION_SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

sesion_agente() {
  local paso="$1" uso="$2" brief="$3" documentos="$4"
  shift 4
  local crudo="${SESION_CRUDO:-}" temporal="" rc=0 inicio
  if [ -z "$crudo" ]; then
    temporal="$(mktemp "${TMPDIR:-/tmp}/sesion-agente.XXXXXX")" || return 1
    crudo="$temporal"
  fi
  inicio="$(date +%s)"
  claude -p "$(cat "$brief")" "$@" \
    ${AGENTE_MODELO:+--model "$AGENTE_MODELO"} \
    --output-format json > "$crudo" || rc=$?
  # -I: solo la biblioteca estándar, sin PYTHONPATH ni la carpeta del script.
  python3 -I "$SESION_SCRIPTS/uso.py" registrar --uso "$uso" --paso "$paso" \
    --documentos "$documentos" ${SESION_GRUPO:+--grupo "$SESION_GRUPO"} \
    --crudo "$crudo" --codigo "$rc" --segundos "$(( $(date +%s) - inicio ))" \
    || cat "$crudo" 2>/dev/null || true
  [ -z "$temporal" ] || rm -f "$temporal"
  return "$rc"
}
