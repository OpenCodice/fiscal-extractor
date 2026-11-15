# Utilidades compartidas por correr.sh y cerrar.sh.

unidades_cambiadas() {
  git -C "$OUT" status --porcelain --no-renames -uall \
    | grep -E '^.. "?[a-z0-9-]+/[^/]+\.md"?$' | grep -vE '^.. "?(metadata|scripts)/' || true
}

# Huella del árbol de datos (todo menos .git): detecta ediciones a mano.
huella_datos() {
  (cd "$OUT" && find . -type f -not -path './.git/*' -print0 | sort -z \
     | xargs -0 shasum | shasum | cut -d' ' -f1)
}
