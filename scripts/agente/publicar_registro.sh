#!/usr/bin/env bash
# Publica en main del extractor los registros nuevos de verificaciones/
# (correcciones confirmadas o rechazadas, revisiones completas de altas), sin
# nada más. Cada lote es un archivo nuevo, así que dos corridas en paralelo no
# chocan; si main avanzó, se rebasa y se reintenta.
#
# Sale 1 si hay registro nuevo y no pudo publicarse: lo que dependa de él
# (exigir las correcciones, contar un intento) no puede darse por hecho.
#
# Uso: publicar_registro.sh "mensaje del commit"
# Entorno: EXTRACTOR_TOKEN + EXTRACTOR_SLUG, o EXTRACTOR_PUSH_URL (pruebas).
#
# Este archivo existe idéntico en constitucion-extractor y en fiscal-extractor.
set -uo pipefail

EXTRACTOR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$EXTRACTOR"
[ -n "$(git status --porcelain -- verificaciones)" ] || exit 0
if [ -z "${EXTRACTOR_PUSH_URL:-}" ] && { [ -z "${EXTRACTOR_TOKEN:-}" ] || [ -z "${EXTRACTOR_SLUG:-}" ]; }; then
  # Lo confirmado que no llega a main no cuenta: quien lo use debe aplazar.
  echo "::error::Sin credenciales para publicar el registro de verificaciones."
  exit 1
fi
export GIT_AUTHOR_NAME="${GITHUB_ACTOR:-opencodice-ci}" GIT_COMMITTER_NAME="${GITHUB_ACTOR:-opencodice-ci}"
export GIT_AUTHOR_EMAIL="${GITHUB_ACTOR_ID:-0}+${GITHUB_ACTOR:-opencodice-ci}@users.noreply.github.com"
export GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"
destino="${EXTRACTOR_PUSH_URL:-https://x-access-token:${EXTRACTOR_TOKEN:-}@github.com/${EXTRACTOR_SLUG:-}.git}"
# Lo demás que haya sin commit (un arreglo descartado, archivos de trabajo) no
# se publica: se aparta mientras tanto.
git stash push -q --include-untracked -- ':!verificaciones' 2>/dev/null || true
git add -- verificaciones
git commit -q -m "$1"
for intento in 1 2 3; do
  if git pull -q --rebase "$destino" main && git push -q "$destino" HEAD:main; then
    echo "Registro de verificaciones publicado."
    git stash pop -q 2>/dev/null || true
    exit 0
  fi
  git rebase --abort 2>/dev/null || true
  sleep $((intento * 5))
done
git stash pop -q 2>/dev/null || true
echo "::error::No se pudo publicar el registro de verificaciones."
exit 1
