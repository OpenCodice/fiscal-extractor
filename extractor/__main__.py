"""CLI del extractor fiscal.

    python -m extractor build      --doc cff --pdf CFF.pdf --out ../fiscal-mexicano
    python -m extractor actualizar --out ../fiscal-mexicano   # descarga + reconstruye
    python -m extractor validar    --out ../fiscal-mexicano
    python -m extractor stats      --doc cff --pdf CFF.pdf
    python -m extractor listar
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import urllib.request
from collections import Counter
from pathlib import Path

from .build import build, build_documento
from .parsers.articulado import fecha_version
from .registro import DOCUMENTOS, POR_CLAVE, activos
from .validate import format_report, validar

UA = "Mozilla/5.0 (fiscal-extractor; vigilancia de reformas)"


def _descargar(url: str, dest: str) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def _cmd_listar(_a) -> int:
    print("Corpus declarado:\n")
    for d in DOCUMENTOS:
        marca = "✓" if d.activo else "·"
        print(f"  [{marca}] {d.clave:24} {d.sigla:14} {d.tipo:11} parser={d.parser}")
    print("\n  ✓ = parser implementado y activo   · = declarado, pendiente")
    return 0


def _cmd_stats(a) -> int:
    doc = POR_CLAVE[a.doc]
    unidades = build_documento(doc, a.pdf, data_repo="/dev/null", what="none")
    derogados = sum(1 for u in unidades if u.derogado)
    con_letra = sum(1 for u in unidades if u.letra)
    con_ordinal = sum(1 for u in unidades if u.ordinal)
    v = fecha_version(a.pdf)
    nums = [u.numero for u in unidades]
    print(f"Documento : {doc.etiqueta} ({doc.sigla})")
    print(f"Versión   : {v.isoformat() if v else '—'}")
    print(f"Unidades  : {len(unidades)}  (rango art. {min(nums)}–{max(nums)})")
    print(f"  derogadas: {derogados}   con letra: {con_letra}   con ordinal: {con_ordinal}")
    reformas = Counter(d.isoformat() for u in unidades for d in u.fechas_reforma)
    print(f"Reformas distintas (DOF): {len(reformas)}")
    # Detectar huecos en la secuencia de números base (señal de parser/derogación).
    base = sorted(set(nums))
    huecos = [n for n in range(base[0], base[-1] + 1) if n not in set(base)]
    if huecos:
        print(f"⚠ huecos en la secuencia: {huecos[:15]}{' …' if len(huecos) > 15 else ''}")
    return 0


def _cmd_build(a) -> int:
    claves = a.doc or None
    if claves:
        pdf_por_clave = {claves[0]: a.pdf} if a.pdf and len(claves) == 1 else {}
        if a.pdf_dir:
            for c in claves:
                pdf_por_clave[c] = f"{a.pdf_dir.rstrip('/')}/{POR_CLAVE[c].clave.upper()}.pdf"
    else:
        claves = [d.clave for d in activos()]
        pdf_por_clave = {c: f"{a.pdf_dir.rstrip('/')}/{c.upper()}.pdf" for c in claves} \
            if a.pdf_dir else {}
    salida = build(claves, pdf_por_clave, a.out, what=a.only)
    for clave, unidades in salida.items():
        print(f"✓ {clave}: {len(unidades)} unidades → {a.out}/{clave}/")
    return 0


def _cmd_actualizar(a) -> int:
    """Descarga las fuentes del registro y reconstruye el repo de datos.

    Pensado para correr en CI: git detecta los cambios; un fallo de descarga de
    un documento no tumba a los demás.
    """
    docs = [POR_CLAVE[c] for c in a.doc] if a.doc else activos()
    with tempfile.TemporaryDirectory() as td:
        pdf_por_clave: dict[str, str] = {}
        for d in docs:
            if not d.url:
                print(f"· {d.clave}: sin URL, se omite")
                continue
            dest = str(Path(td) / f"{d.clave}.pdf")
            try:
                _descargar(d.url, dest)
                pdf_por_clave[d.clave] = dest
                print(f"↓ {d.clave}")
            except Exception as e:                       # noqa: BLE001 — CI robusto
                print(f"✗ {d.clave}: error al descargar — {e}")
        if not pdf_por_clave:
            print("Nada que construir.")
            return 1
        salida = build(list(pdf_por_clave), pdf_por_clave, a.out, what="all")
    for clave, u in salida.items():
        print(f"✓ {clave}: {len(u)} unidades")
    return 0


def _cmd_validar(a) -> int:
    ok, checks = validar(a.out)
    print(format_report(checks))
    print("\n" + ("✓ TODO OK" if ok else "✗ HAY FALLAS"))
    return 0 if ok else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="extractor", description="Extractor del corpus fiscal")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("listar", help="lista el corpus declarado")
    sp.set_defaults(fn=_cmd_listar)

    sp = sub.add_parser("stats", help="estadísticas de parseo (no escribe)")
    sp.add_argument("--doc", required=True)
    sp.add_argument("--pdf", required=True)
    sp.set_defaults(fn=_cmd_stats)

    sp = sub.add_parser("actualizar",
                        help="descarga las fuentes del registro y reconstruye el repo")
    sp.add_argument("--doc", action="append", help="clave(s); omitir = todos los activos")
    sp.add_argument("--out", required=True, help="repo de datos de salida")
    sp.set_defaults(fn=_cmd_actualizar)

    sp = sub.add_parser("validar", help="corre los invariantes sobre el repo de datos")
    sp.add_argument("--out", required=True, help="repo de datos a validar")
    sp.set_defaults(fn=_cmd_validar)

    sp = sub.add_parser("build", help="parsea y materializa texto + metadata")
    sp.add_argument("--doc", action="append", help="clave(s) a construir; omitir = todos los activos")
    sp.add_argument("--pdf", help="ruta del PDF (cuando se pasa un solo --doc)")
    sp.add_argument("--pdf-dir", help="carpeta con PDFs nombrados CLAVE.pdf")
    sp.add_argument("--out", required=True, help="repo de datos de salida")
    sp.add_argument("--only", default="all", choices=["all", "text", "metadata"])
    sp.set_defaults(fn=_cmd_build)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
