#!/usr/bin/env bash
# Valida un PR de un repo de datos sobre el sha exacto de su cabeza: los
# invariantes de cada documento (`extractor validar`) y los trailers de cada
# commit (`validar_commits.py`). Es el check que exige main en los repos de
# datos; lo corre `.github/workflows/revisar-pr.yml` en un job sin secretos,
# y solo con su resultado se publica el commit status y se fusiona.
#
# Uso: validar_pr.sh <OpenCodice/repo-datos> <número de PR> [sha esperado]
#
# Entorno:
#   GH_TOKEN                basta con lectura (los repos de datos son públicos).
#   TRABAJO                 directorio de trabajo (por omisión, uno temporal).
#   CONSTITUCION_EXTRACTOR  checkout de constitucion-extractor (si no, se clona main).
#   FISCAL_EXTRACTOR        checkout de fiscal-extractor (si no, se clona main).
#   GITHUB_OUTPUT           si existe, recibe `sha=<sha validado>`.
#
# Sale con 0 solo si todo pasó sobre ese sha. Cualquier otra cosa (un PR
# cerrado, una cabeza distinta de la esperada, un error de red) es falla.
#
# Este archivo existe idéntico en constitucion-extractor y en fiscal-extractor
# (scripts/validar_pr.sh): cualquier cambio se hace en los dos.
set -euo pipefail
trap 'echo "::error::validar_pr.sh se detuvo en la línea $LINENO."' ERR

repo="${1:?uso: validar_pr.sh <OpenCodice/repo-datos> <PR> [sha]}"
pr="${2:?falta el número de PR}"
esperado="${3:-}"
trabajo="${TRABAJO:-$(mktemp -d)}"
mkdir -p "$trabajo"

info=$(gh pr view "$pr" -R "$repo" \
  --json state,headRefOid,baseRefName,labels \
  -q '"\(.state) \(.headRefOid) \(.baseRefName) \([.labels[].name] | join(","))"')
read -r estado sha base etiquetas <<< "$info"
echo "PR #$pr de $repo: $estado, cabeza $sha, base $base, etiquetas: ${etiquetas:-ninguna}"
# Uno ya fusionado (al relanzarlo, o si otro lo fusionó antes) se valida: no se
# vuelve a fusionar, pero su resultado sigue diciendo si lo publicado está bien.
case "$estado" in OPEN|MERGED) ;; *) echo "::error::El PR #$pr está cerrado."; exit 1 ;; esac
if [ -n "$esperado" ] && [ "$esperado" != "$sha" ]; then
  echo "::error::La cabeza del PR ($sha) no es la esperada ($esperado)."; exit 1
fi

datos="$trabajo/datos"
rm -rf "$datos"
git clone -q --no-checkout "https://github.com/$repo.git" "$datos"
git -C "$datos" fetch -q origin "pull/$pr/head" "$base"
[ "$(git -C "$datos" rev-parse FETCH_HEAD)" = "$sha" ] \
  || { echo "::error::La cabeza del PR cambió mientras se descargaba."; exit 1; }
git -C "$datos" checkout -q --detach "$sha"
# Contra el punto donde nace el PR: lo que se fusionó en main después no es
# parte de este PR.
desde=$(git -C "$datos" merge-base "origin/$base" "$sha") \
  || { echo "::error::El PR no comparte historia con $base."; exit 1; }

extractor() {  # nombre → ruta de su checkout (clona main si no se dio)
  local nombre="$1" var="$2"
  local ruta="${!var:-}"
  if [ -z "$ruta" ]; then
    ruta="$trabajo/$nombre"
    [ -d "$ruta" ] || git clone -q --depth 1 "https://github.com/OpenCodice/$nombre.git" "$ruta"
    pip install -q -r "$ruta/requirements.txt" >&2
  fi
  echo "$ruta"
}

# Un PR verificado contra el PDF puede tocar cualquier número de artículos; el
# tope de las constituciones solo protege los que llegan sin verificar.
max=20
case ",$etiquetas," in
  *,extraccion-sospechosa,*) ;;
  *,verificado,*) max=100000 ;;
esac

rc=0
paso() {  # descripción, comando… — corre y acumula la falla sin cortar
  local desc="$1"; shift
  echo "::group::$desc"
  if "$@"; then echo "OK: $desc"; else echo "::error::FALLA: $desc"; rc=1; fi
  echo "::endgroup::"
}

constitucion() {  # dir del documento, perfil
  (cd "$ce" && PYTHONPATH="$ce" python -m extractor validar \
     --out "$datos/$1" --perfil "$2" --base "$desde" --max-cambios "$max")
}

corpus() {  # leyes con el parser del corpus fiscal, federal o estatal
  (cd "$fe" && PYTHONPATH="$fe" python -m extractor validar --out "$datos" > "$trabajo/validar.log") \
    && tail -n 1 "$trabajo/validar.log" \
    || { grep -E "FALLA|✗" "$trabajo/validar.log" | head -n 40; return 1; }
}

case "${repo#*/}" in
  constitucion-mexicana)
    ce=$(extractor constitucion-extractor CONSTITUCION_EXTRACTOR)
    paso "Invariantes de la CPEUM" constitucion . cpeum
    validador="$ce/scripts/validar_commits.py" ;;
  leyes-estatales)
    ce=$(extractor constitucion-extractor CONSTITUCION_EXTRACTOR)
    fe=$(extractor fiscal-extractor FISCAL_EXTRACTOR)
    # Las constituciones, cada una con el perfil de su estado; las demás leyes
    # ({estado}/{ley}, registradas en fuentes.json), con el articulado.
    for dir in "$datos"/*/constitucion; do
      [ -d "$dir" ] || continue
      e="${dir%/constitucion}"; e="${e##*/}"
      paso "Invariantes de $e/constitucion" constitucion "$e/constitucion" "$e"
    done
    paso "Invariantes de las leyes estatales" corpus
    validador="$ce/scripts/validar_commits.py" ;;
  fiscal-mexicano|leyes-federales)
    fe=$(extractor fiscal-extractor FISCAL_EXTRACTOR)
    paso "Invariantes de ${repo#*/}" corpus
    validador="$fe/scripts/validar_commits.py" ;;
  *)
    echo "::error::$repo no es un repo de datos conocido."; exit 1 ;;
esac

paso "Trailers de cada commit" python "$validador" "$datos" "$desde" "$sha"

if [ "$rc" = 0 ] && [ -n "${GITHUB_OUTPUT:-}" ]; then
  echo "sha=$sha" >> "$GITHUB_OUTPUT"
fi
[ "$rc" = 0 ] && echo "PR #$pr ($sha): todo en orden." || echo "::error::PR #$pr ($sha): no pasa la validación."
exit "$rc"
