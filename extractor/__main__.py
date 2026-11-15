"""CLI del extractor fiscal.

    python -m extractor build      --doc cff --pdf CFF.pdf --out ../fiscal-mexicano
    python -m extractor actualizar --out ../fiscal-mexicano   # descarga + reconstruye
    python -m extractor validar    --out ../fiscal-mexicano
    python -m extractor verificar  --out ../fiscal-mexicano --pdf-dir /tmp/pdfs
    python -m extractor stats      --doc cff --pdf CFF.pdf
    python -m extractor listar
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from collections import Counter
from pathlib import Path

from .build import build, build_documento
from .fuentes import descargar, url_vigente
from .parsers.articulado import fecha_version
from .referencias import aplicar_referencias
from .registro import DOCUMENTOS, POR_CLAVE, activos
from .validate import format_report, validar


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


def _pdf_en(pdf_dir: str, clave: str) -> str:
    """`<clave>.pdf` (como lo deja `actualizar --pdf-dir`) o `CLAVE.pdf`."""
    base = Path(pdf_dir)
    return str(base / f"{clave}.pdf") if (base / f"{clave}.pdf").exists() \
        else str(base / f"{clave.upper()}.pdf")


def _cmd_build(a) -> int:
    claves = a.doc or None
    if claves:
        pdf_por_clave = {claves[0]: a.pdf} if a.pdf and len(claves) == 1 else {}
        if a.pdf_dir:
            for c in claves:
                pdf_por_clave[c] = _pdf_en(a.pdf_dir, c)
    else:
        claves = [d.clave for d in activos()]
        if a.pdf_dir:
            pdf_por_clave = {c: _pdf_en(a.pdf_dir, c) for c in claves}
            # Con --pdf-dir y sin --doc se construye lo que haya (lo que dejó
            # `actualizar --pdf-dir`), no se exige el corpus completo.
            claves = [c for c in claves if Path(pdf_por_clave[c]).exists()]
        else:
            pdf_por_clave = {}
    salida = build(claves, pdf_por_clave, a.out, what=a.only)
    for clave, unidades in salida.items():
        print(f"✓ {clave}: {len(unidades)} unidades → {a.out}/{clave}/")
    return 0


def _cmd_actualizar(a) -> int:
    """Descarga las fuentes del registro y reconstruye el repo de datos.

    Pensado para correr en CI: git detecta los cambios; un fallo de descarga de
    un documento no tumba a los demás, pero sí se reporta con exit code 3 para
    que el workflow alerte (una URL muerta no debe pasar inadvertida).
    """
    docs = [POR_CLAVE[c] for c in a.doc] if a.doc else activos()
    fallidos: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        td = a.pdf_dir or tmp
        Path(td).mkdir(parents=True, exist_ok=True)
        pdf_por_clave: dict[str, str] = {}
        for d in docs:
            if not d.url and not d.indice:
                print(f"· {d.clave}: sin URL, se omite")
                continue
            dest = str(Path(td) / f"{d.clave}.pdf")
            try:
                url = url_vigente(d)
                descargar(url, dest)
                pdf_por_clave[d.clave] = dest
                print(f"↓ {d.clave} ← {url}")
            except Exception as e:                       # noqa: BLE001 — CI robusto
                fallidos.append(d.clave)
                print(f"✗ {d.clave}: error al resolver/descargar — {e}")
        if not pdf_por_clave:
            print("Nada que construir.")
            return 1
        salida = build(list(pdf_por_clave), pdf_por_clave, a.out, what="all")
    for clave, u in salida.items():
        print(f"✓ {clave}: {len(u)} unidades")
    if fallidos:
        print(f"\n✗ Fuentes fallidas: {', '.join(fallidos)}")
        return 3
    return 0


def _cmd_referencias(a) -> int:
    """Anota metadata/*/pasajes.jsonl con referencias legales cruzadas.

    Post-proceso sobre el repo de datos existente: no descarga PDFs ni
    re-extrae. `build`/`actualizar` ya lo corren al final; este comando
    retrofitea un repo construido antes de que existiera la capa.
    """
    stats = aplicar_referencias(a.out)
    total = sum(stats.values())
    for doc, n in sorted(stats.items(), key=lambda kv: -kv[1]):
        if n:
            print(f"  {doc:28} {n:5} pasajes con referencias")
    print(f"\n✓ {total} pasajes anotados en {len(stats)} documentos")
    return 0


def _cmd_verificar(a) -> int:
    """Verifica contra los PDF las unidades cuyo texto cambió (según git).

    Espera los PDF que dejó `actualizar --pdf-dir` (`<clave>.pdf`). Sale 2 si
    queda algún cambio que no es fiel al PDF.
    """
    from .verificar import (modelo_configurado, modelo_fuerte_configurado,
                            openai_call, reporte_md, verificar)
    pdfs = {p.stem: str(p) for p in Path(a.pdf_dir).glob("*.pdf")}
    call = fuerte = None
    if not a.sin_llm:
        call = openai_call(a.modelo or modelo_configurado())
        fuerte = openai_call(modelo_fuerte_configurado())
    r = verificar(a.out, pdfs, call, call_fuerte=fuerte)
    md = reporte_md(r)
    if a.reporte:
        Path(a.reporte).write_text(md, encoding="utf-8")
    print(md)
    return 0 if r.ok else 2


def _cmd_auditar(a) -> int:
    """Cobertura determinista de todas las unidades contra los PDF de --pdf-dir."""
    import json
    from .verificar import auditar
    pdfs = {p.stem: str(p) for p in Path(a.pdf_dir).glob("*.pdf")}
    res = auditar(a.out, pdfs)
    if a.json:
        Path(a.json).write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    malos = res["con_problemas"]
    print(f"{len(malos)} de {res['total']} unidades con problemas de cobertura")
    for ref, pr in list(malos.items())[:60]:
        print(f"  {ref}: " + "; ".join(f"{p['tipo']} «{p['fragmento'][:80]}»" for p in pr[:2]))
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
    sp.add_argument("--pdf-dir", help="conservar los PDF descargados aquí (<clave>.pdf)")
    sp.set_defaults(fn=_cmd_actualizar)

    sp = sub.add_parser("auditar",
                        help="cobertura determinista de todas las unidades contra los PDF")
    sp.add_argument("--out", required=True, help="repo de datos")
    sp.add_argument("--pdf-dir", required=True, help="PDFs de `actualizar --pdf-dir`")
    sp.add_argument("--json", default=None, help="escribe el resultado aquí")
    sp.set_defaults(fn=_cmd_auditar)

    sp = sub.add_parser("verificar",
                        help="verifica contra los PDF las unidades cambiadas (git)")
    sp.add_argument("--out", required=True, help="repo de datos ya reconstruido")
    sp.add_argument("--pdf-dir", required=True, help="PDFs de `actualizar --pdf-dir`")
    sp.add_argument("--modelo", default=None,
                    help="modelo base (default: $VERIFICADOR_MODELO o el del módulo)")
    sp.add_argument("--sin-llm", action="store_true",
                    help="solo la cobertura determinista")
    sp.add_argument("--reporte", default=None, help="escribe el reporte markdown aquí")
    sp.set_defaults(fn=_cmd_verificar)

    sp = sub.add_parser("referencias",
                        help="anota los pasajes con referencias legales cruzadas")
    sp.add_argument("--out", required=True, help="repo de datos a anotar")
    sp.set_defaults(fn=_cmd_referencias)

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
