#!/usr/bin/env bash
# Lanza vigilar-leyes-estatales.yml. Uso: lanzar_vigilancia_estatal.sh [estados] [-f clave=valor…]
#
# GitHub deja una sola corrida en espera por grupo de concurrency: la nueva
# cancela a la que esperaba. Si ya hay una en espera, se lanza la vigilancia
# completa (sin `estados`), que abarca lo que esa iba a hacer y lo de esta.
set -euo pipefail
estados="${1:-}"; shift || true
repo="${GITHUB_REPOSITORY:-OpenCodice/fiscal-extractor}"
en_espera=$(gh run list -R "$repo" -w vigilar-leyes-estatales.yml -L 20 \
  --json status -q '[.[] | select(.status=="queued" or .status=="pending" or .status=="waiting" or .status=="requested")] | length')
if [ -n "$estados" ] && [ "$en_espera" != "0" ]; then
  echo "Hay una vigilancia en espera: se lanza completa en lugar de solo '$estados'."
  estados=""
fi
if [ -n "$estados" ]; then
  gh workflow run vigilar-leyes-estatales.yml -R "$repo" --ref main -f estados="$estados" "$@"
else
  gh workflow run vigilar-leyes-estatales.yml -R "$repo" --ref main "$@"
fi
