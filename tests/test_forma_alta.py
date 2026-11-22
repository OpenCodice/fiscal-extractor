"""Filtro de forma previo a la revisión completa de un alta de ley estatal
(scripts/forma_alta.py): cuándo aplica, cuándo deja fuera una ley, cuándo cede
a la revisión, y que lo que anota lo entienden `revision-federal.sh`, el
registro de altas y la reparación."""
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
import forma_alta as fa  # noqa: E402
import reparacion as rp  # noqa: E402
import revision as rv  # noqa: E402

CLAVE = "jalisco/ley-de-prueba"
PLAN = {"corpus": "estatal"}
SUCIO = [("001", ["El texto del artículo."]),
         ("002", ["Los ayuntamientos sesionarán página 45 de 119 en forma ordinaria.", "IV."])]
LIMPIO = [("001", ["El texto del artículo."]), ("002", ["Los ayuntamientos sesionarán."])]


def _ley(repo: Path, arts, clave=CLAVE):
    for sub in ("articulos", "metadata"):
        (repo / clave / sub).mkdir(parents=True, exist_ok=True)
    for viejo in (repo / clave / "articulos").glob("*.md"):
        viejo.unlink()
    for c, ps in arts:
        (repo / clave / "articulos" / f"{c}.md").write_text(
            f"# Artículo {c}.\n\n" + "\n\n".join(ps) + "\n", encoding="utf-8")
    (repo / clave / "metadata" / "articulos.json").write_text(json.dumps({
        "etiqueta": "Ley de Prueba", "articulos": [{"clave": c, "articulo": int(c)} for c, _ in arts]}),
        encoding="utf-8")


@pytest.fixture
def caso(tmp_path):
    repo = tmp_path / "datos"
    _ley(repo, SUCIO)
    (repo / "fuentes.json").write_text(json.dumps({"documentos": []}), encoding="utf-8")
    (tmp_path / "plan.json").write_text(json.dumps(PLAN), encoding="utf-8")
    (tmp_path / "ley.pdf").write_bytes(_pdf_minimo("El texto del articulo."))
    return tmp_path


def _pdf_minimo(texto: str) -> bytes:
    """Un PDF de una página con `texto`: `revision.py planear` lo abre."""
    flujo = f"BT /F1 12 Tf 20 100 Td ({texto}) Tj ET".encode()
    objetos = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Contents 4 0 R "
               b"/Resources << /Font << /F1 5 0 R >> >> >>",
               b"<< /Length %d >>\nstream\n" % len(flujo) + flujo + b"\nendstream",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    pdf, posiciones = b"%PDF-1.4\n", []
    for n, objeto in enumerate(objetos, 1):
        posiciones.append(len(pdf))
        pdf += b"%d 0 obj\n" % n + objeto + b"\nendobj\n"
    xref = len(pdf)
    pdf += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
    pdf += b"".join(b"%010d 00000 n \n" % p for p in posiciones)
    return pdf + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objetos) + 1, xref)


def _args(caso: Path, fase: str, *extra) -> list[str]:
    return [fase, "--repo", str(caso / "datos"), "--fuentes", str(caso / "datos" / "fuentes.json"),
            "--plan", str(caso / "plan.json"), "--documento", CLAVE, "--pdf", str(caso / "ley.pdf"),
            "--altas", str(caso / "altas"), "--reparaciones", str(caso / "reparaciones"), *extra]


def _sha(caso: Path) -> str:
    return rv.tr.sha256_bytes((caso / "ley.pdf").read_bytes())


def _registros(caso: Path) -> list[dict]:
    return [json.loads(linea) for f in sorted((caso / "altas").glob("*.jsonl"))
            for linea in f.read_text(encoding="utf-8").splitlines()]


def _intento(caso: Path, intento: str, documento=CLAVE, pdf=None):
    d = caso / "reparaciones"
    d.mkdir(exist_ok=True)
    with (d / f"{intento}.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"documento": documento, "pdf": pdf or _sha(caso), "intento": intento,
                             "resultado": "iniciado", "fecha": intento[:10]}) + "\n")


# ------------------------------------------------------------------ cuándo aplica

def test_aplica_solo_a_leyes_estatales_sin_publicar():
    publicada = {"documentos": [{"clave": CLAVE, "estado": "incluida"}]}
    excluida = {"documentos": [{"clave": CLAVE, "estado": "excluida"}]}
    assert fa.aplica(CLAVE, PLAN, {"documentos": []})          # un alta
    assert fa.aplica(CLAVE, PLAN, excluida)                    # el reintento de una excluida
    # Lo publicado (una reforma, o la revisión de una `revision_pendiente`) no
    # pasa por el filtro, ni el corpus federal, ni un plan que no dice su corpus.
    assert not fa.aplica(CLAVE, PLAN, publicada)
    assert not fa.aplica("lgs", {"corpus": "federal"}, {"documentos": []})
    assert not fa.aplica(CLAVE, {}, {"documentos": []})


def test_lo_publicado_y_lo_federal_no_se_filtran(caso):
    (caso / "datos" / "fuentes.json").write_text(json.dumps(
        {"documentos": [{"clave": CLAVE, "estado": "incluida"}]}), encoding="utf-8")
    assert fa.main(_args(caso, "filtrar")) == 0
    assert fa.main(_args(caso, "cerrar", "--trabajo", str(caso / "rev"))) == 0
    (caso / "datos" / "fuentes.json").write_text(json.dumps({"documentos": []}), encoding="utf-8")
    (caso / "plan.json").write_text(json.dumps({"corpus": "federal"}), encoding="utf-8")
    assert fa.main(_args(caso, "filtrar")) == 0
    assert not (caso / "altas").exists() and not (caso / "rev").exists()


# ------------------------------------------------------------------ deja fuera

def test_filtrar_salta_la_revision_solo_con_hallazgos(caso, capsys):
    assert fa.main(_args(caso, "filtrar")) == 3
    # `filtrar` no anota nada: lo hace `cerrar`, fuera del alcance del agente.
    assert not (caso / "altas").exists()
    assert capsys.readouterr().out == ""
    _ley(caso / "datos", LIMPIO)
    assert fa.main(_args(caso, "filtrar")) == 0


def test_cerrar_anota_los_hallazgos_como_los_de_la_revision(caso, capsys):
    rev = caso / "rev"
    assert fa.main(_args(caso, "cerrar", "--trabajo", str(rev))) == 2
    salida = capsys.readouterr().out
    assert salida.startswith("✗ El filtro de forma")
    (r,) = _registros(caso)
    assert r == json.loads((rev / "resultado.json").read_text(encoding="utf-8"))
    assert (r["documento"], r["pdf"], r["resultado"], r["origen"]) == (
        CLAVE, _sha(caso), "hallazgos", "forma")
    assert r["extractor"] == rv.huella_extractor() and r["motivo"] in salida
    assert [(h["clave"], h["chequeo"]) for h in r["hallazgos"]] == [
        ("002", "pie_pagina"), ("002", "fraccion_huerfana")]
    assert "página 45 de 119" in r["hallazgos"][0]["nota"]
    # Con el mismo PDF y extractor, la corrida siguiente ya no pasa por el
    # filtro ni por el agente: `revision.py previa` devuelve este resultado.
    assert rv.previa(CLAVE, _sha(caso), rv.huella_extractor(), caso / "altas") == r


def test_cerrar_sin_hallazgos_no_decide_nada(caso, capsys):
    _ley(caso / "datos", LIMPIO)
    assert fa.main(_args(caso, "cerrar", "--trabajo", str(caso / "rev"))) == 0
    # Sin salida ni registro: quien llama sigue con `revision.py cerrar`, y sin
    # veredictos del agente eso nunca da una ley por revisada.
    assert capsys.readouterr().out == ""
    assert not (caso / "altas").exists() and not (caso / "rev").exists()


def test_la_reparacion_recibe_los_hallazgos_del_filtro(caso, capsys):
    rev = caso / "agente" / "revision" / CLAVE
    assert fa.main(_args(caso, "cerrar", "--trabajo", str(rev))) == 2
    motivo = capsys.readouterr().out.strip().removeprefix("✗ ")
    sha = _sha(caso)
    # Una revisión anterior del mismo PDF dejó su plan y sus veredictos en la
    # caché: no son de este texto y no deben volver como hallazgos.
    (rev / "plan.json").write_text(json.dumps({"bloques": [{"huella": "vieja"}]}))
    (rev / "veredicto-1.json").write_text(json.dumps({"bloques": [
        {"huella": "vieja", "hallazgos": [{"clave": "001", "nota": "hallazgo de otro texto"}]}]}))
    hs = rp.de_revision(rev, sha)
    assert [(h["clave"], h["chequeo"]) for h in hs] == [("002", "pie_pagina"),
                                                        ("002", "fraccion_huerfana")]
    assert rp.de_revision(rev, "otro-pdf") is None
    # Sin la carpeta de la corrida, salen del registro o del motivo.
    assert rp.de_registro(CLAVE, sha, caso / "altas") == hs
    assert rp.DEFECTOS in motivo
    assert [h["clave"] for h in rp.de_motivo(motivo)] == ["002", "002"]
    assert [rp.categoria(h["nota"]) for h in hs] == ["pagina", "corte_parrafo"]


def test_una_ley_que_dejo_fuera_el_filtro_es_candidata_a_reparacion(caso):
    # Con una clave declarada en el registro estatal: `candidatos` solo mira esas.
    clave = "jalisco/codigo-civil"
    _ley(caso / "datos", SUCIO, clave)
    args = [a if a != CLAVE else clave for a in _args(caso, "cerrar")]
    trabajo = caso / "agente"
    assert fa.main([*args, "--trabajo", str(trabajo / "revision" / clave)]) == 2
    (r,) = _registros(caso)
    (trabajo / "resultados.json").write_text(json.dumps({clave: {
        "clave": clave, "motivo": "nuevo", "sha256": r["pdf"], "revision": r["motivo"]}}))
    (c,) = rp.candidatos("estatal", caso / "datos", trabajo, True, [], altas=caso / "sin-registro")
    assert (c["clave"], c["origen"], c["intentos"]) == (clave, "corrida", 0)
    assert [(h["chequeo"], h["categoria"]) for h in c["hallazgos"]] == [
        ("pie_pagina", "pagina"), ("fraccion_huerfana", "corte_parrafo")]
    # En una corrida posterior, ya excluida en fuentes.json y sin la carpeta de
    # la corrida, los hallazgos salen del registro de altas.
    (caso / "datos" / "fuentes.json").write_text(json.dumps({"documentos": [{
        "clave": clave, "estado": "excluida", "motivo": r["motivo"], "pdf": {"sha256": r["pdf"]}}]}))
    (c,) = rp.candidatos("estatal", caso / "datos", caso / "otra-corrida", True, [],
                         altas=caso / "altas")
    assert c["origen"] == "registro"
    assert [h["chequeo"] for h in c["hallazgos"]] == ["pie_pagina", "fraccion_huerfana"]


def test_las_notas_de_cada_chequeo_caen_en_su_tipo_de_reparacion():
    from test_forma import _ley as ley
    from extractor import forma
    absorbido = ley(("988", ["El juez nombrará un tutor.", "Artículo 988.- Se deroga."]))
    encabezado = ley(("131", ["La Junta propondrá la integración.",
                              "_(ADICIONADO CON LOS ARTÍCULOS QUE LO INTEGRAN, P.O. 27 DE DICIEMBRE "
                              "DE 2011)_"]))
    colado = ley(("165", ["La Secretaría promoverá la participación.",
                          "De la financiación y del fomento."]))
    assert rp.categoria(forma.rotulo_interno(absorbido)[0].nota) == "absorcion"
    assert rp.categoria(forma.nota_de_encabezado(encabezado)[0].nota) == "nota_reforma"
    assert rp.categoria(forma.epigrafe_final_con_punto(colado)[0].nota) == "estructura"


# ------------------------------------------------------------------ cede

def _registrar_con_momento(caso: Path, momento: str, arts=SUCIO):
    _ley(caso / "datos", arts)
    _, hallazgos = fa.decidir(caso / "datos", CLAVE, _sha(caso), altas=caso / "sin-registro",
                              intentos=[])
    r = fa.resultado_de(CLAVE, _sha(caso), hallazgos,
                        ahora=datetime.strptime(momento, fa._MOMENTO).replace(tzinfo=timezone.utc))
    fa.registrar(r, caso / "rev", caso / "altas")


def _decision(caso: Path) -> str:
    return fa.decidir(caso / "datos", CLAVE, _sha(caso), altas=caso / "altas",
                      intentos=fa.reparaciones.cargar(caso / "reparaciones"))[0]


def test_un_hallazgo_que_sobrevive_a_una_reparacion_deja_de_bloquear(caso, capsys):
    _registrar_con_momento(caso, "2026-11-20T100000")
    # Sin intento de reparación (el extractor cambió por otra cosa), sigue fuera.
    assert _decision(caso) == fa.BLOQUEA
    # Tampoco cuentan un intento anterior al registro, el de otra ley ni el de
    # otro PDF de esta.
    _intento(caso, "2026-11-20T093000-aaaaaa")
    _intento(caso, "2026-11-21T093000-bbbbbb", documento="jalisco/otra")
    _intento(caso, "2026-11-21T093000-cccccc", pdf="otro-pdf")
    assert _decision(caso) == fa.BLOQUEA
    # Tras un intento posterior, los mismos hallazgos ya no bloquean: decide la
    # revisión completa, y el filtro no anota nada más.
    _intento(caso, "2026-11-20T113000-dddddd")
    assert _decision(caso) == fa.CEDE
    assert fa.main(_args(caso, "filtrar")) == 0
    assert fa.main(_args(caso, "cerrar", "--trabajo", str(caso / "rev2"))) == 0
    assert "cede" in capsys.readouterr().err
    assert len(_registros(caso)) == 1 and not (caso / "rev2").exists()


def test_un_hallazgo_nuevo_tras_la_reparacion_si_bloquea(caso):
    _registrar_con_momento(caso, "2026-11-20T100000")
    _intento(caso, "2026-11-20T113000-dddddd")
    # El arreglo quitó el pie pero dejó otro defecto en otro artículo: ese no
    # ha pasado por ninguna reparación.
    _ley(caso / "datos", [("001", ["El texto.", ":"]), ("002", ["Los ayuntamientos sesionarán.", "IV."])])
    assert _decision(caso) == fa.BLOQUEA
    # Y si solo queda el que ya se intentó, cede.
    _ley(caso / "datos", [("001", ["El texto."]), ("002", ["Los ayuntamientos sesionarán.", "IV."])])
    assert _decision(caso) == fa.CEDE


def test_sin_identificador_con_hora_el_intento_cuenta_desde_el_dia_siguiente(caso):
    _registrar_con_momento(caso, "2026-11-20T100000")
    fecha = _registros(caso)[0]["fecha"]
    d = caso / "reparaciones"
    d.mkdir()
    linea = {"documento": CLAVE, "pdf": _sha(caso), "intento": "i1", "resultado": "iniciado"}
    (d / "i1.jsonl").write_text(json.dumps({**linea, "fecha": fecha}) + "\n")
    assert _decision(caso) == fa.BLOQUEA
    (d / "i1.jsonl").write_text(json.dumps({**linea, "fecha": "9999-01-01"}) + "\n")
    assert _decision(caso) == fa.CEDE


# ------------------------------------------------------------------ revision-federal.sh

def _git(repo: Path, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   check=True, capture_output=True)


def _revision_federal(caso: Path, fase: str, corpus: str = "estatal") -> tuple[dict, bool]:
    """Corre una fase de `revision-federal.sh` sobre una copia del extractor
    (el script escribe en su `verificaciones/` y deshace cambios en
    `extractor/`), con un `claude` de mentira que solo deja constancia de que
    lo llamaron. Devuelve resultados.json de la ley y si hubo sesión del agente."""
    extractor = caso / "extractor"
    if not extractor.exists():
        for carpeta in ("extractor", "scripts"):
            shutil.copytree(RAIZ / carpeta, extractor / carpeta,
                            ignore=shutil.ignore_patterns("__pycache__"))
        _git(extractor, "init", "-q", "-b", "main")
        _git(extractor, "add", "-A")
        _git(extractor, "commit", "-q", "-m", "copia del extractor")
        subprocess.run(["git", "init", "-q", "--bare", str(caso / "remoto.git")], check=True)
        _git(extractor, "push", "-q", str(caso / "remoto.git"), "HEAD:refs/heads/main")
        (caso / "bin").mkdir()
        (caso / "bin" / "claude").write_text(f"#!/bin/sh\necho sesion >> '{caso}/sesiones.txt'\n")
        (caso / "bin" / "claude").chmod(0o755)
    datos, trabajo, pdfs = caso / "datos", caso / "agente", caso / "pdfs"
    if not (datos / ".git").exists():
        _git(datos, "init", "-q")
    (pdfs / CLAVE).parent.mkdir(parents=True, exist_ok=True)
    (pdfs / f"{CLAVE}.pdf").write_bytes((caso / "ley.pdf").read_bytes())
    trabajo.mkdir(exist_ok=True)
    (trabajo / "resultados.json").write_text(json.dumps({CLAVE: {
        "clave": CLAVE, "motivo": "nuevo", "sha256": _sha(caso), "bytes": 1, "problemas": {},
        "invariantes": []}}), encoding="utf-8")
    (caso / "plan.json").write_text(json.dumps({"corpus": corpus, "revisar": []}), encoding="utf-8")
    (caso / "sesiones.txt").unlink(missing_ok=True)
    env = {**os.environ, "OUT": str(datos), "PDF_DIR": str(pdfs), "PLAN": str(caso / "plan.json"),
           "AGENTE_DIR": str(trabajo), "REVISION_MAX_ALTAS": "8", "REVISION_SESIONES": "1",
           "EXTRACTOR_PUSH_URL": str(caso / "remoto.git"),
           "PATH": f"{caso / 'bin'}:{Path(sys.executable).parent}:{os.environ['PATH']}"}
    env.pop("PYTHONPATH", None)
    r = subprocess.run(["bash", str(extractor / "scripts/agente/revision-federal.sh"), fase],
                       env=env, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    return (json.loads((trabajo / "resultados.json").read_text(encoding="utf-8"))[CLAVE],
            (caso / "sesiones.txt").exists())


def test_revision_federal_revisar_no_gasta_la_sesion_de_un_alta_con_hallazgos_de_forma(caso):
    _, hubo_sesion = _revision_federal(caso, "revisar")
    assert not hubo_sesion
    # Sin hallazgos de forma, o en el corpus federal, la revisión corre como siempre.
    _, hubo_sesion = _revision_federal(caso, "revisar", corpus="federal")
    assert hubo_sesion
    _ley(caso / "datos", LIMPIO)
    _, hubo_sesion = _revision_federal(caso, "revisar")
    assert hubo_sesion


def test_revision_federal_cerrar_deja_fuera_el_alta_con_el_motivo_del_filtro(caso):
    r, _ = _revision_federal(caso, "cerrar")
    assert r["revision"].startswith("El filtro de forma") and rp.DEFECTOS in r["revision"]
    assert "revisada" not in r and "aplazada" not in r
    # El registro llegó a main del extractor, de donde lo lee la reparación.
    publicado = subprocess.run(
        ["git", "-C", str(caso / "remoto.git"), "show", "--stat", "--format=%s", "main"],
        capture_output=True, text=True, check=True).stdout
    assert "verificaciones/altas/" in publicado and "jalisco__ley-de-prueba" in publicado
    resultado = json.loads((caso / "agente" / "revision" / CLAVE / "resultado.json").read_text())
    assert resultado["origen"] == "forma"


def test_revision_federal_cerrar_nunca_da_por_revisada_un_alta_sin_veredictos(caso):
    # Sin hallazgos de forma el filtro no decide: sin veredictos del agente, la
    # revisión completa quedó a medias y el alta se aplaza.
    _ley(caso / "datos", LIMPIO)
    r, _ = _revision_federal(caso, "cerrar")
    assert r.get("aplazada") is True and "revisada" not in r and "revision" not in r
    # En el corpus federal el filtro no aplica aunque el texto tenga hallazgos.
    _ley(caso / "datos", SUCIO)
    r, _ = _revision_federal(caso, "cerrar", corpus="federal")
    assert r.get("aplazada") is True and "revision" not in r
