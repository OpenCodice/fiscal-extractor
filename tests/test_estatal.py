"""Leyes estatales: registro, disposición, lectura de sus PDF y su vigilancia,
sin red ni PDF."""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from extractor import disposicion, federal
from extractor.estatal import ESTATAL
from extractor.estatales import ENTIDADES, cdmx, clave_de, documentos, fuera
from extractor.fuentes import url_vigente
from extractor.normalize import normalize_body as _normalize_body
from extractor.parsers.articulado import (_sin_numero_de_pagina, ARTICULO_ESTATAL_RE,
                                          FECHA_TABLA_RE, VERSION_ESTATAL_RE, fechas_en_notas)
from extractor.parsers.articulado import parse_texto as _parse_texto
from extractor.registro import Documento, a_dict
from extractor.verificar import Flujo, cobertura, encabezado_pegado

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import trailers as tr  # noqa: E402

NOTAS = re.compile(cdmx.NOTAS)


def parse_texto(texto, *a, **k):
    """El parser como lo usa una ley estatal (`estatal=True`)."""
    return _parse_texto(texto, *a, estatal=True, **k)


def normalize_body(cuerpo, etiqueta, *a, **k):
    return _normalize_body(cuerpo, etiqueta, *a, rotulo=ARTICULO_ESTATAL_RE, **k)
PREVIAS = re.compile(cdmx.NOTAS_PREVIAS)


# ------------------------------------------------------------------ registro

def test_clave_sin_el_ambito_del_estado():
    assert clave_de("Código de Procedimientos Civiles del Estado de Jalisco") == \
        "codigo-de-procedimientos-civiles"
    assert clave_de("Código Penal para el Estado Libre y Soberano de Jalisco") == "codigo-penal"
    assert clave_de("Código Civil para el Distrito Federal") == "codigo-civil"
    assert clave_de("Ley Orgánica del Congreso de la Ciudad de México") == \
        "ley-organica-del-congreso"


def test_registro_claves_unicas_y_de_estados_conocidos():
    claves = [d.clave for d in documentos()] + list(fuera())
    assert len(claves) == len(set(claves))
    for c in claves:
        estado, ley = c.split("/")
        assert estado in ENTIDADES and ley != "constitucion"
        assert re.fullmatch(r"[a-z0-9-]+", ley)
    for d in documentos():
        assert d.medio and d.huecos and d.parser == "articulado" and d.indice and d.patron


def test_registro_compacto_en_fuentes_json():
    d = a_dict(documentos(["cdmx"])[0])
    r = ESTATAL.registro(d, "https://x/CC_15.4.pdf")
    assert set(r) == {"clave", "etiqueta", "sigla", "tipo", "parser", "medio", "indice", "url"}


# ------------------------------------------------------------------ disposición

@pytest.mark.parametrize("clave", ["lgs", "jalisco/codigo-civil", "cdmx/codigo-penal"])
def test_disposicion_igual_a_la_de_trailers(clave):
    assert disposicion.rel_unidades(clave) + "/" == tr._dir_articulos(clave)
    assert disposicion.rel_metadata(clave) + "/" == tr._dir_metadata(clave)


def test_trailers_de_una_ley_estatal():
    doc = "jalisco/codigo-civil"
    assert tr.esquema_de(doc) == "estatal"
    assert tr.documento_de_ruta("jalisco/codigo-civil/articulos/004.md", "estatal") == doc
    assert tr.documento_de_ruta("jalisco/constitucion/fuente/constitucion.pdf", "estatal") == \
        "jalisco/constitucion"
    assert tr.documento_de_ruta("fuentes.json", "estatal") is None
    assert tr.rutas_fuente(doc) == ()                 # el PDF de una ley no se guarda
    assert tr.rutas_fuente("jalisco/constitucion")    # el de la constitución sí
    leer = tr.lector_dict({f"{doc}/metadata/articulos.json": json.dumps(
        {"sigla": "CC Jalisco", "medio": "Periódico Oficial del Estado de Jalisco",
         "version": "2026-06-18"})})
    i = tr.info(doc, leer)
    assert (i["sigla"], i["medio"], i["version"]) == (
        "CC Jalisco", "Periódico Oficial del Estado de Jalisco", "2026-06-18")
    assert tr.titulo("reforma", i["sigla"], medio=i["medio"], fecha="2026-06-18",
                     etiquetas=["12"]) == "Reforma CC Jalisco (P.O. 2026-06-18): art. 12"


# ------------------------------------------------------------------ fuentes

def _doc(**kw):
    return Documento("jalisco/codigo-civil", "Código Civil", "CC", "ley", "articulado",
                     indice="https://congreso.example/bv/busquedasleyes/Listado.cfm", **kw)


def test_url_vigente_por_fecha_ddmmaa_y_codificada():
    html = ('<a href="../legislacion/Códigos/Código Civil del Estado de Jalisco-240626.pdf">'
            '<a href="../legislacion/Códigos/Código Civil del Estado de Jalisco-311225.pdf">'
            '<a href="../legislacion/Códigos/Código Civil del Estado de Jalisco (anterior) .pdf">')
    d = _doc(patron=r"/Código Civil del Estado de Jalisco\s?-\d{6}\.pdf$", orden="ddmmaa")
    url = url_vigente(d, leer=lambda _u: html)
    assert url == ("https://congreso.example/bv/legislacion/C%C3%B3digos/"
                   "C%C3%B3digo%20Civil%20del%20Estado%20de%20Jalisco-240626.pdf")


def test_url_vigente_unica_falla_si_hay_dos():
    html = '<a href="/l/CODIGO_PENAL_12.9.pdf"><a href="/l/CODIGO_PENAL_12.8.pdf">'
    d = _doc(patron=r"/CODIGO_PENAL_[\d.]+\.pdf$", orden="unico")
    with pytest.raises(LookupError):
        url_vigente(d, leer=lambda _u: html)
    assert url_vigente(d, leer=lambda _u: html.split("><")[0] + ">").endswith("_12.9.pdf")


# ------------------------------------------------------------------ parser

def test_huecos_de_numeracion_sin_aceptar_citas():
    texto = ("Artículo 1.- Uno.\nArtículo 2.- Dos, conforme al\n"
             "Artículo 9 de la Constitución.\nArtículo 4.- Cuatro.\nArtículo 5.- Cinco.\n")
    assert [u.clave for u in parse_texto(texto)] == ["001", "002"]     # sin huecos: se detiene
    assert [u.clave for u in parse_texto(texto, huecos=True)] == ["001", "002", "004", "005"]
    # Un salto a un número cuyos anteriores vuelven a aparecer es una cita.
    texto = "Artículo 1.- Uno.\nArtículo 7.- Ver más abajo.\nArtículo 2.- Dos.\n"
    us = parse_texto(texto, huecos=True)
    assert [u.clave for u in us] == ["001", "002"] and "Artículo 7" in us[0].cuerpo


def test_separadores_estatales():
    texto = ("Artículo 126. Se deroga.\nArtículo 127.Se deroga.\n"
             "Artículo 128. Uno.\nArtículo 128 Bis. 1. Comete el delito.\n"
             "Artículo 129: Comete otro.\n")
    us = parse_texto(texto, start=126, huecos=True)
    assert [u.clave for u in us] == ["126", "127", "128", "128-bis", "129"]
    # 'Bis. 1.' es el párrafo 1 del 128 Bis (Código Electoral de Jalisco)…
    assert normalize_body(us[3].cuerpo, us[3].etiqueta) == "1. Comete el delito."
    # …pero tras un 'Bis' ya abierto, 'Bis. 3.' es el Bis 3 (Código Penal de Jalisco).
    texto = ("Artículo 176. Uno.\nArtículo 176-Bis. Dos.\nArtículo 176-Bis.1. Tres.\n"
             "Artículo 176-Bis. 3. Cuatro.\nArtículo 177. Cinco.\n")
    assert [u.clave for u in parse_texto(texto, start=176)] == [
        "176", "176-bis", "176-bis-1", "176-bis-3", "177"]


def test_cita_a_un_transitorio_no_corta_el_articulado():
    texto = ("ARTICULO 1.- Uno.\nN. DE E. EN RELACIÓN CON SU ENTRADA EN VIGOR, VER\n"
             "ARTICULO SEGUNDO TRANSITORIO DEL DECRETO QUE MODIFICA EL CÓDIGO.\n"
             "ARTICULO 2.- Dos.\n")
    assert [u.clave for u in parse_texto(texto, notas=NOTAS)] == ["001", "002"]


def test_nota_previa_va_al_articulo_que_anota():
    texto = ("ARTICULO 11.- Once.\n(REFORMADO, G.O. 25 DE MAYO DE 2000)\n"
             "ARTICULO 12.- Las leyes se aplicarán.\n")
    us = parse_texto(texto, start=11, notas=NOTAS, notas_previas=PREVIAS)
    assert "REFORMADO" not in us[0].cuerpo
    md = normalize_body(us[1].cuerpo, us[1].etiqueta, NOTAS)
    assert md.split("\n\n") == ["_(REFORMADO, G.O. 25 DE MAYO DE 2000)_",
                                "Las leyes se aplicarán."]
    assert [d.isoformat() for d in us[1].fechas_reforma] == ["2000-05-25"]


def test_nota_previa_de_un_encabezado_no_es_del_articulo():
    texto = ("ARTICULO 3012.- Fin.\n(REFORMADO, D.O.F. 3 DE ENERO DE 1979)\nDe la prelación\n"
             "(REFORMADO, G.O. 23 DE JULIO DE 2012)\nARTICULO 3013.- La preferencia.\n")
    us = parse_texto(texto, start=3012, huecos=True, notas=NOTAS, notas_previas=PREVIAS)
    assert us[0].cuerpo.strip() == "ARTICULO 3012.- Fin."
    assert us[1].epigrafe == "De la prelación"
    assert "1979" not in us[1].cuerpo and "23 DE JULIO DE 2012" in us[1].cuerpo


def test_fraccion_intercalada_no_es_epigrafe():
    texto = ("Artículo 16.- Corresponde:\nXIII. Coordinar acciones;\n"
             "XIII Bis. Diseñar y ejecutar acciones de gestión menstrual, con el objeto de\n"
             "garantizar el derecho, y\nFracción adicionada G.O. CDMX 27/03/24\n"
             "Artículo 17.- Otro.\n")
    us = parse_texto(texto, start=16, notas=NOTAS)
    assert "XIII Bis. Diseñar" in us[0].cuerpo and not us[1].epigrafe
    assert [d.isoformat() for d in us[0].fechas_reforma] == ["2024-03-27"]


def test_numero_de_pagina_suelto():
    paginas = [f"Texto {i}\nmás texto\n{i + 1}" for i in range(6)] + ["Tabla\n10\nfin\n7"]
    limpias = _sin_numero_de_pagina(paginas)
    assert all(not p.rstrip().endswith(str(i + 1)) for i, p in enumerate(limpias))
    assert "\n10\n" in limpias[-1]                    # un número a media página se queda


def test_fechas_de_version_estatal():
    m = VERSION_ESTATAL_RE.search("TEXTO VIGENTE\nÚltima reforma publicada en la G.O. CDMX\n"
                                  "el 20 de agosto de 2026\n")
    assert m.groups() == ("20", "agosto", "2026")
    assert FECHA_TABLA_RE.findall("Jalisco.- Jun. 18 de 2026 sec. VII. …- Jul.6 de 2021") == [
        ("Jun", "18", "2026"), ("Jul", "6", "2021")]
    assert [d.isoformat() for d in fechas_en_notas(
        "(artículo reformado, G.O.CDMX 29 de noviembre de 2024)\ntexto 1/2/2020", NOTAS)] == [
        "2024-11-29"]


# ------------------------------------------------------------------ verificación

def test_cobertura_admite_el_rotulo_propio_tras_la_nota_previa():
    flujo = Flujo.de("(REFORMADO, G.O. 25 DE MAYO DE 2000)\n"
                     "ARTICULO 12.- Las leyes para el Distrito Federal se aplicarán.\n")
    md = ("# Artículo 12.\n\n_(REFORMADO, G.O. 25 DE MAYO DE 2000)_\n\n"
          "Las leyes para el Distrito Federal se aplicarán.\n")
    assert cobertura(md, flujo, notas_previas=True) == []
    assert cobertura(md, flujo)                        # fuera de esas fuentes, sí es hueco
    otro = md.replace("# Artículo 12.", "# Artículo 13.")
    assert cobertura(otro, flujo, notas_previas=True)  # el rótulo de otro artículo no


def test_encabezado_pegado_en_leyes_estatales():
    derogado = "# Artículo 451.\n\n_(REFORMADO, D.O.F. 1970)_\n\nSE DEROGA\n"
    assert encabezado_pegado(derogado) and not encabezado_pegado(derogado, estatal=True)
    titulo = "# Artículo 9.\n\nNingún partido.\n\nDe la elección de los concejales\n"
    assert encabezado_pegado(titulo, estatal=True)


# ------------------------------------------------------------------ vigilancia

def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def test_cerrar_estatal_registra_lo_declarado_fuera(tmp_path):
    repo = tmp_path / "datos"
    (repo / "jalisco" / "constitucion" / "articulos").mkdir(parents=True)
    (repo / "jalisco" / "constitucion" / "articulos" / "001.md").write_text("# Artículo 1º\n\nX.\n")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "inicio")
    ley = documentos(["jalisco"])[0]
    unidades = repo / disposicion.rel_unidades(ley.clave)
    unidades.mkdir(parents=True)
    (unidades / "001.md").write_text("# Artículo 1º.\n\nUno.\n")
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"corpus": "estatal", "huella": "h", "extractor_sha": "a" * 40,
                                "documentos": [{**a_dict(ley), "motivo": "nuevo"}], "shards": []}))
    r = {"sha256": "s", "bytes": 1, "problemas": {}, "invariantes": [], "unidades": 1,
         "version": "2026-06-18", "url": "https://x/CC-240626.pdf"}
    res = federal.cerrar(str(plan), str(repo), {ley.clave: r})
    assert res["altas"] == [ley.clave]
    assert res["asunto"] == f"Alta de 1 ley estatal: {ley.sigla}"
    fuentes = {d["clave"]: d for d in json.loads((repo / "fuentes.json").read_text())["documentos"]}
    assert fuentes[ley.clave]["url"] == "https://x/CC-240626.pdf"
    assert "patron" not in fuentes[ley.clave]          # cómo leer el PDF vive en el código
    for clave, motivo in ESTATAL.fuera.items():
        assert fuentes[clave]["estado"] == "excluida" and fuentes[clave]["motivo"] == motivo
    assert not (repo / "metadata").exists()            # sin índice maestro en leyes-estatales


def test_ultimo_parrafo_sin_punto_no_es_epigrafe():
    texto = ("Artículo 31.- La o el Presidente responderá ante el Pleno.\n"
             "En la elección de la Presidencia de la Mesa Directiva se atenderá el principio de paridad\n"
             "Artículo 32.- Otro.\n"
             "Artículo 33.- Fin.\nDe la prelación\nArtículo 34.- Sigue.\n")
    us = parse_texto(texto, start=31, epigrafe_max=80)
    assert "principio de paridad" in us[0].cuerpo and not us[1].epigrafe
    assert us[3].epigrafe == "De la prelación"
    texto = "Artículo 1.- Uno.\nEn este caso, declarará improcedente la solicitud\nArtículo 2.- Dos.\n"
    assert "improcedente" in parse_texto(texto, epigrafe_max=80)[0].cuerpo


def test_rotulos_estatales_en_plural_y_con_guion_separado():
    texto = ("ARTÍCULO 49.- Uno.\nARTÍCULOS 50.- Dos.\nARTÍCULO 50 BIS. - Tres.\n"
             "Artículo 51.A través de esto.\nArtículos 52. Los requisitos.\n")
    us = parse_texto(texto, start=49)
    assert [u.clave for u in us] == ["049", "050", "050-bis", "051", "052"]
    assert normalize_body(us[2].cuerpo, us[2].etiqueta) == "Tres."


def test_leyes_estatales_sin_prefijos_de_la_camara_y_acentos_compuestos():
    from extractor.parsers.articulado import limpiar_paginas
    doc = documentos(["jalisco"])[0]
    pagina = ("Solo pueden recibir el apoyo de la\nSecretaría General y sus Coordinaciones.\n"
              "Arti\u0301culo 5. Los tribunales.\n")
    texto = limpiar_paginas([pagina], doc)
    assert "Secretaría General y sus" in texto and "Artículo 5." in texto


def test_lectura_federal_sin_cambios():
    # Sin `estatal`, ni el rótulo en plural ni el punto pegado abren artículo.
    texto = "Artículo 1.- Uno.\nARTÍCULOS 2.- Dos.\nArtículo 3.Tres.\n"
    assert [u.clave for u in _parse_texto(texto)] == ["001"]


def test_rotulo_estatal_no_es_epigrafe():
    texto = "Artículo 233.\n1. Uno.\nArtículo 234.Derogado\nArtículo 235.\n1. Tres.\n"
    assert [u.clave for u in parse_texto(texto, start=233, epigrafe_max=80)] == [
        "233", "234", "235"]


def test_hallazgos_de_revision_persisten_hasta_otra_revision(tmp_path):
    repo = tmp_path / "datos"
    ley = documentos(["cdmx"])[0]
    unidades = repo / disposicion.rel_unidades(ley.clave)
    unidades.mkdir(parents=True)
    (unidades / "001.md").write_text("# Artículo 1o.\n\nUno.\n")
    (repo / "fuentes.json").write_text(json.dumps({"documentos": [
        {"clave": ley.clave, "etiqueta": ley.etiqueta, "sigla": ley.sigla, "tipo": "ley",
         "estado": "incluida", "pdf": {"sha256": "s"}, "extractor": "h",
         "revision_pendiente": {"motivo": "La revisión completa…", "revisada": True}}]}))
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "inicio")
    r = {"sha256": "s", "bytes": 1, "problemas": {}, "invariantes": [], "unidades": 1}

    def cerrar(revisar):
        plan = tmp_path / "plan.json"
        plan.write_text(json.dumps({"corpus": "estatal", "huella": "h2", "revisar": revisar,
                                    "documentos": [{**a_dict(ley), "motivo": "extractor"}]}))
        federal.cerrar(str(plan), str(repo), {ley.clave: r})
        return json.loads((repo / "fuentes.json").read_text())["documentos"]

    e = next(d for d in cerrar([]) if d["clave"] == ley.clave)
    assert e["revision_pendiente"]["revisada"]          # las compuertas no la quitan
    e = next(d for d in cerrar([ley.clave]) if d["clave"] == ley.clave)
    assert "revision_pendiente" not in e                 # una revisión sin hallazgos sí
