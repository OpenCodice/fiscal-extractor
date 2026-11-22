#!/usr/bin/env python3
"""Filtro de forma previo a la revisión completa de un alta de ley estatal.

La revisión completa de un alta (`revision.py`, un agente por bloques) se paga
en tokens, y buena parte de lo que encuentra se ve en el texto solo: un pie de
página colado, el rótulo de un artículo absorbido, una nota pegada al párrafo
(`extractor/forma.py`). Antes de esa revisión, este filtro corre los chequeos
de `forma.FILTRO` sobre la ley ya construida. Si encuentran algo, la ley se
trata como si la revisión hubiera devuelto esos hallazgos: queda fuera con su
motivo, se anota en `verificaciones/altas/` (con `origen: forma`) y entra a la
reparación autónoma, sin gastar la sesión del agente. Si no encuentran nada,
la revisión corre como siempre: el filtro solo ahorra revisiones, nunca da
una ley por revisada.

Solo aplica a las leyes estatales que no están publicadas (un alta o el
reintento de una excluida). Lo publicado no se toca con esto.

Un chequeo puede equivocarse, y un falso positivo no puede dejar una ley fuera
para siempre: un hallazgo del filtro que sigue ahí después de un intento de
reparación de esa ley (mismo PDF) deja de bloquear. Si todos los que quedan
son así, el filtro cede y decide la revisión completa.

Uso (lo llama `scripts/agente/revision-federal.sh`):
  forma_alta.py filtrar --repo R --fuentes F --plan P --documento D --pdf PDF
      sale 3 si el filtro deja fuera la ley (no hay que revisarla); 0 si no.
  forma_alta.py cerrar  --repo R --fuentes F --plan P --documento D --pdf PDF --trabajo T
      si el filtro la deja fuera: anota el resultado, imprime «✗ motivo» y sale
      2 (como `revision.py cerrar`); si no, sale 0 sin imprimir nada.

Las dos fases deciden lo mismo porque no guardan estado: leen el repo de datos
y los registros. Cualquier otro código de salida es un error, y quien llama lo
trata como «el filtro no decidió»: la ley pasa por la revisión completa.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

EXTRACTOR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EXTRACTOR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import revision  # noqa: E402
from extractor import forma, reparaciones  # noqa: E402

ORIGEN = "forma"
BLOQUEA, CEDE, LIMPIA, NO_APLICA = "bloquea", "cede", "limpia", "no_aplica"
_MOMENTO = "%Y-%m-%dT%H%M%S"       # el de los identificadores de intento de reparacion.py


def aplica(documento: str, plan: dict, fuentes: dict) -> bool:
    """Una ley estatal que no está publicada."""
    if plan.get("corpus") != "estatal":
        return False
    return not any(d.get("clave") == documento and d.get("estado") == "incluida"
                   for d in fuentes.get("documentos", []))


def registros_de_forma(documento: str, pdf_sha: str, altas: str | Path) -> list[dict]:
    d = Path(altas)
    res = []
    for archivo in sorted(d.glob("*.jsonl")) if d.is_dir() else []:
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(linea) if linea.strip() else None
            except ValueError:
                continue
            if isinstance(e, dict) and e.get("origen") == ORIGEN \
                    and (e.get("documento"), e.get("pdf")) == (documento, pdf_sha):
                res.append(e)
    return res


def _posterior(intento: dict, registro: dict) -> bool:
    """¿El intento de reparación empezó después de ese registro del filtro?"""
    m = re.match(r"\d{4}-\d\d-\d\dT\d{6}", str(intento.get("intento", "")))
    if m and registro.get("momento"):
        return m.group() > registro["momento"]
    return bool(intento.get("fecha")) and intento["fecha"] > registro.get("fecha", "9")


def ya_intentados(documento: str, pdf_sha: str, altas: str | Path,
                  intentos: list[dict]) -> set[tuple[str, str]]:
    """(chequeo, clave) de los hallazgos del filtro que ya pasaron por un
    intento de reparación de esta ley con este PDF."""
    propios = [i for i in intentos if i.get("documento") == documento and i.get("pdf") == pdf_sha]
    return {(h.get("chequeo"), h.get("clave"))
            for r in registros_de_forma(documento, pdf_sha, altas)
            if any(_posterior(i, r) for i in propios)
            for h in r.get("hallazgos") or []}


def decidir(repo: str | Path, documento: str, pdf_sha: str, *, altas: str | Path,
            intentos: list[dict]) -> tuple[str, list[forma.Hallazgo]]:
    hallazgos = forma.revisar(forma.cargar(repo, documento, forma.definiciones().get(documento)),
                              forma.FILTRO)
    if not hallazgos:
        return LIMPIA, []
    vistos = ya_intentados(documento, pdf_sha, altas, intentos)
    if all((h.chequeo, h.clave) in vistos for h in hallazgos):
        return CEDE, hallazgos
    return BLOQUEA, hallazgos


def motivo_de(hallazgos: list[forma.Hallazgo]) -> str:
    # 'encontró defectos de extracción: ' es lo que `reparacion.py` reconoce en
    # el motivo de una ley fuera para repararla.
    resumen = "; ".join(f"{h.clave}: {h.nota[:200]}" for h in hallazgos[:5])
    return ("El filtro de forma, previo a la revisión completa contra el PDF, encontró defectos "
            f"de extracción: {resumen}"
            + (f" (y {len(hallazgos) - 5} más)" if len(hallazgos) > 5 else ""))


def resultado_de(documento: str, pdf_sha: str, hallazgos: list[forma.Hallazgo],
                 extractor_dir: str | Path = EXTRACTOR, ahora: datetime | None = None) -> dict:
    """El registro del filtro, con la forma de los de `revision.cerrar`."""
    ahora = ahora or datetime.now(timezone.utc)
    return {"documento": documento, "pdf": pdf_sha,
            "extractor": revision.huella_extractor(extractor_dir),
            "resultado": "hallazgos", "origen": ORIGEN, "motivo": motivo_de(hallazgos),
            "bloques": 0, "fecha": date.today().isoformat(), "momento": ahora.strftime(_MOMENTO),
            "hallazgos": [{**h.a_dict(), "nota": h.nota[:600]} for h in hallazgos[:300]]}


def registrar(resultado: dict, trabajo: str | Path, altas: str | Path) -> None:
    """En `trabajo/resultado.json` (de ahí lo toma la reparación de esta
    corrida) y en el registro de revisiones de altas."""
    t = Path(trabajo)
    t.mkdir(parents=True, exist_ok=True)
    (t / "resultado.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1) + "\n",
                                      encoding="utf-8")
    d = Path(altas)
    d.mkdir(parents=True, exist_ok=True)
    nombre = resultado["documento"].replace("/", "__")
    archivo = d / f"{resultado['fecha']}-{nombre}-{resultado['pdf'][:8]}.jsonl"
    with archivo.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(resultado, ensure_ascii=False, sort_keys=True) + "\n")


def _json(ruta: str) -> dict:
    p = Path(ruta)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("fase", choices=("filtrar", "cerrar"))
    ap.add_argument("--repo", required=True, help="raíz del repo de datos")
    ap.add_argument("--fuentes", required=True, help="su fuentes.json")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--documento", required=True)
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--trabajo", help="carpeta de la revisión del documento (fase cerrar)")
    ap.add_argument("--altas", default=str(revision.REGISTRO))
    ap.add_argument("--reparaciones", default=None)
    ap.add_argument("--extractor-dir", default=str(EXTRACTOR))
    a = ap.parse_args(argv)
    if a.fase == "cerrar" and not a.trabajo:
        ap.error("cerrar necesita --trabajo")
    if not aplica(a.documento, _json(a.plan), _json(a.fuentes)):
        return 0
    sha = revision.tr.sha256_bytes(Path(a.pdf).read_bytes())
    decision, hallazgos = decidir(a.repo, a.documento, sha, altas=a.altas,
                                  intentos=reparaciones.cargar(a.reparaciones))
    # Los avisos van a stderr: la salida de `cerrar` es el motivo.
    if decision == CEDE:
        print(f"{a.documento}: el filtro de forma cede: sus {len(hallazgos)} hallazgos siguen tras "
              f"un intento de reparación; decide la revisión completa.", file=sys.stderr)
    if decision != BLOQUEA:
        return 0
    if a.fase == "filtrar":
        print(f"{a.documento}: el filtro de forma encontró {len(hallazgos)} defectos; "
              f"no se gasta su revisión completa.", file=sys.stderr)
        return 3
    resultado = resultado_de(a.documento, sha, hallazgos, a.extractor_dir)
    registrar(resultado, a.trabajo, a.altas)
    print(f"✗ {resultado['motivo']}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
