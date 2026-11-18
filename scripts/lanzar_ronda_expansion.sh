#!/usr/bin/env bash
# Lanza expandir-estatales.yml. Uso: lanzar_ronda_expansion.sh [-f clave=valor…]
#
# GitHub deja una sola corrida en espera por grupo de concurrency: la nueva
# cancela a la que esperaba. Una ronda no abarca a otra (cada una es de un
# estado), así que si ya hay una en espera esta no se lanza y la que espera
# conserva su lugar. Lo que esta iba a hacer se retoma solo: el estado sigue
# `pendiente` en pendientes.json para la ronda siguiente, y una redeclaración
# la vuelve a pedir `reparar` en la vigilancia siguiente.
#
# Si no se puede mirar la cola (tres intentos), se lanza: casi nunca hay una
# ronda en espera, y no lanzar pierde seguro este relanzamiento.
set -euo pipefail
repo="${GITHUB_REPOSITORY:-OpenCodice/fiscal-extractor}"
en_espera="desconocido"
for intento in 1 2 3; do
  if n=$(gh run list -R "$repo" -w expandir-estatales.yml -L 20 \
    --json status -q '[.[] | select(.status=="queued" or .status=="pending" or .status=="waiting" or .status=="requested")] | length'); then
    en_espera="$n"
    break
  fi
  [ "$intento" = 3 ] || sleep "${LANZAR_ESPERA:-10}"
done
if [ "$en_espera" = "desconocido" ]; then
  echo "::warning::No se pudo mirar la cola de expandir-estatales: se lanza la ronda."
elif [ "$en_espera" != "0" ]; then
  echo "Ya hay una ronda de expansión en espera: no se lanza otra ($*)."
  exit 0
fi
gh workflow run expandir-estatales.yml -R "$repo" --ref main "$@"
echo "Ronda de expansión lanzada ($*)."
