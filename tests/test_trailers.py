"""Trailers de los commits de datos (scripts/trailers.py, idéntico en
constitucion-extractor y fiscal-extractor; esta prueba también)."""
import importlib.util
import json
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "scripts" / "trailers.py"
_spec = importlib.util.spec_from_file_location("trailers", _MOD)
tr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tr)

EXT = "OpenCodice/fiscal-extractor@b897ca4"
SHA = "9f2c" + "0" * 60


def _meta(prefijo, version, reformas, sigla="LGS", fuente=None):
    idx = {"version": version, "sigla": sigla, "articulos": []}
    if fuente:
        idx["fuente"] = fuente
    return {f"{prefijo}articulos.json": json.dumps(idx),
            f"{prefijo}reformas.json": json.dumps({f: [] for f in reformas})}


def _lgs_antes():
    return {**_meta("metadata/lgs/", "2025-01-01", ["2020-01-01"]),
            "lgs/004.md": "# Artículo 4o.\n\nTexto viejo.\n",
            "lgs/022.md": "# Artículo 22\n\nVeintidós.\n",
            "lgs/030.md": "# Artículo 30\n\nTreinta.\n",
            "lgs/031.md": "# Artículo 31\n\nTreinta y uno.\n"}


def _calcular(antes, despues, tipo, **kw):
    rutas = sorted(set(antes) | set(despues))
    rutas = [r for r in rutas if antes.get(r) != despues.get(r)]
    return rutas, tr.calcular("lgs", tipo, rutas, tr.lector_dict(antes), tr.lector_dict(despues),
                              fuente="https://x/LGS.pdf", fuente_sha256=SHA, extractor=EXT, **kw)


def test_reforma_con_adicionados_modificados_y_derogados():
    antes = _lgs_antes()
    despues = {**antes, **_meta("metadata/lgs/", "2026-01-15", ["2020-01-01", "2026-01-15"]),
               "lgs/004.md": "# Artículo 4o.\n\nTexto nuevo.\n",
               "lgs/222-bis.md": "# Artículo 222 Bis\n\nNuevo.\n",
               "lgs/030.md": "# Artículo 30\n\nSe deroga.\n\n_Artículo derogado DOF 15-01-2026_\n"}
    del despues["lgs/031.md"]
    _, (titulo, t) = _calcular(antes, despues, "reforma")
    assert titulo == "Reforma LGS (DOF 2026-01-15): arts. 4o, 30, 31, 222 Bis"
    assert t == [("Documento", "lgs"), ("Tipo", "reforma"), ("Publicacion", "2026-01-15"),
                 ("Publicacion-Origen", "notas"), ("Medio", "DOF"),
                 ("Articulos-Adicionados", "222-bis"), ("Articulos-Modificados", "004"),
                 ("Articulos-Derogados", "030, 031"), ("Fuente", "https://x/LGS.pdf"),
                 ("Fuente-Sha256", SHA), ("Extractor", EXT)]


def test_publicacion_de_portada_sin_fechas_nuevas():
    antes = _lgs_antes()
    despues = {**antes, **_meta("metadata/lgs/", "2026-02-01", ["2020-01-01"]),
               "lgs/022.md": "# Artículo 22\n\nOtro.\n"}
    _, (titulo, t) = _calcular(antes, despues, "reforma")
    assert tr.valores(t, "Publicacion") == ["2026-02-01"]
    assert tr.valor(t, "Publicacion-Origen") == "portada"
    assert titulo == "Reforma LGS (DOF 2026-02-01): art. 22"


def test_varias_publicaciones_en_orden():
    f, origen = tr.publicaciones("reforma", {"2020-01-01"},
                                 {"2020-01-01", "2026-03-01", "2026-01-15"}, "2026-03-01")
    assert (f, origen) == (["2026-01-15", "2026-03-01"], "notas")


def test_correccion_una_sola_lista_y_sin_publicacion():
    antes = _lgs_antes()
    despues = {**antes, "lgs/004.md": "# Artículo 4o.\n\nTexto viejo bien leído.\n",
               "lgs/004-bis.md": "# Artículo 4o. Bis\n\nNo se leía.\n"}
    _, (titulo, t) = _calcular(antes, despues, "correccion")
    assert titulo == "Corrección de extracción LGS: arts. 4o, 4o. Bis"
    assert tr.valor(t, "Articulos-Corregidos") == "004, 004-bis"
    assert tr.valor(t, "Publicacion") is None and tr.valor(t, "Articulos-Adicionados") is None


def test_alta_y_retiro():
    despues = {**_meta("metadata/lgs/", "2026-01-15", ["2020-01-01", "2026-01-15"]),
               "lgs/001.md": "# Artículo 1o.\n\nUno.\n"}
    lec_vacio = tr.lector_dict({})
    assert tr.tipo_por_existencia("lgs", lec_vacio, tr.lector_dict(despues)) == "alta"
    _, (titulo, t) = _calcular({}, despues, "alta")
    assert titulo == "Alta de LGS"
    assert tr.valores(t, "Publicacion") == ["2026-01-15"]
    assert tr.valor(t, "Publicacion-Origen") == "portada"
    assert not [k for k, _ in t if k.startswith("Articulos-")]
    assert tr.tipo_por_existencia("lgs", tr.lector_dict(despues), lec_vacio) == "retiro"
    titulo, t = tr.calcular("lgs", "retiro", list(despues), tr.lector_dict(despues), lec_vacio,
                            extractor=EXT, motivo="fuera del corpus")
    assert titulo == "Retiro de LGS: fuera del corpus"
    assert tr.valor(t, "Publicacion") is None


def test_indice():
    msg = tr.formatear("Índice del corpus fiscal y README al día", tr.trailers_indice(EXT))
    assert msg == ("Índice del corpus fiscal y README al día\n\nTipo: indice\n"
                   f"Extractor: {EXT}\n")


def test_decidir_tipo_por_causa():
    assert tr.decidir_tipo(True, False) == "reforma"
    assert tr.decidir_tipo(False, True) == "correccion"
    assert tr.decidir_tipo(True, True) == "separar"
    assert tr.decidir_tipo(True, None) == "sin-separacion"


def test_tipo_historico():
    antes = _lgs_antes()
    nueva_version = {**antes, **_meta("metadata/lgs/", "2026-01-15", ["2020-01-01"])}
    misma = {**antes, "lgs/004.md": "# Artículo 4o.\n\nOtra lectura.\n"}
    lee = tr.lector_dict
    assert tr.tipo_historico("lgs", lee(antes), lee(nueva_version)) == "reforma"
    assert tr.tipo_historico("lgs", lee(antes), lee(misma)) == "correccion"
    assert tr.tipo_historico("lgs", lee({}), lee(antes)) == "alta"


def test_medio_y_sigla_estatal():
    doc = "jalisco/constitucion"
    fuente = "Periódico Oficial del Estado de Jalisco — Congreso del Estado de Jalisco"
    antes = {**_meta(f"{doc}/metadata/", "2026-09-01", [], fuente=fuente),
             f"{doc}/articulos/015.md": "# Artículo 15\n\nAntes.\n"}
    despues = {**_meta(f"{doc}/metadata/", "2026-10-29", ["2026-10-29"], fuente=fuente),
               f"{doc}/articulos/015.md": "# Artículo 15\n\nDespués.\n"}
    rutas = [r for r in despues if antes.get(r) != despues[r]]
    titulo, t = tr.calcular(doc, "reforma", rutas, tr.lector_dict(antes), tr.lector_dict(despues))
    assert tr.valor(t, "Medio") == "Periódico Oficial del Estado de Jalisco"
    assert titulo == "Reforma jalisco (P.O. 2026-10-29): art. 15"
    assert tr.medio_corto("Gaceta Oficial de la Ciudad de México") == "G.O."
    assert tr.medio_corto('Periódico Oficial "El Estado de Colima"') == "P.O."


def test_cpeum():
    antes = {**_meta("metadata/", "2026-01-01", []), "articulos/082.md": "# Artículo 82.\n\nA.\n"}
    despues = {**_meta("metadata/", "2026-10-07", ["2026-10-07"]),
               "articulos/082.md": "# Artículo 82.\n\nB.\n"}
    rutas = [r for r in despues if antes[r] != despues[r]]
    titulo, t = tr.calcular("cpeum", "reforma", rutas, tr.lector_dict(antes), tr.lector_dict(despues))
    assert titulo == "Reforma CPEUM (DOF 2026-10-07): art. 82"
    assert tr.valor(t, "Articulos-Modificados") == "082"


def test_derogado():
    assert tr.es_derogado("# Artículo 30\n\nSe deroga.\n")
    assert tr.es_derogado("# Artículo 30\n\n(Se deroga)\n\n_Artículo derogado DOF 01-01-2020_\n")
    assert tr.es_derogado("# Artículo 7\n\n(DEROGADO, P.O. 20 DE MARZO DE 2001)\n")
    assert tr.es_derogado("# Artículo 7\n\nDerogado.\n")
    assert not tr.es_derogado("# Artículo 7\n\nTexto.\n\n(DEROGADO QUINTO PÁRRAFO, P.O. 2026)\n")
    assert not tr.es_derogado("# Artículo 7\n\nSe derogan las disposiciones que se opongan.\n"
                              "\n\nOtro párrafo de verdad.\n")


def test_titulo_con_muchos_articulos_y_solo_metadata():
    assert tr.texto_articulos([str(i) for i in range(13)]) == "13 artículos"
    assert tr.texto_articulos([]) == "solo metadata"


def test_formatear_y_parsear():
    titulo, t = "Reforma LGS (DOF 2026-01-15): art. 4o", [
        ("Extractor", EXT), ("Documento", "lgs"), ("Tipo", "reforma"),
        ("Publicacion", "2026-01-15"), ("Publicacion", "2026-02-01")]
    msg = tr.formatear(titulo, t)
    assert msg.splitlines()[2:4] == ["Documento: lgs", "Tipo: reforma"]
    t2, pares = tr.parsear(msg)
    assert t2 == titulo
    assert tr.valores(pares, "Publicacion") == ["2026-01-15", "2026-02-01"]
    assert tr.parsear("Título\n\nUn párrafo libre.\n") == ("Título", [])
    assert tr.parsear("Solo título") == ("Solo título", [])


# ------------------------------------------------------------------ validar

def _valido():
    antes = _lgs_antes()
    despues = {**antes, **_meta("metadata/lgs/", "2026-01-15", ["2020-01-01", "2026-01-15"]),
               "lgs/004.md": "# Artículo 4o.\n\nTexto nuevo.\n"}
    rutas, (titulo, t) = _calcular(antes, despues, "reforma")
    return titulo, t, rutas, tr.lector_dict(antes), tr.lector_dict(despues)


def test_validar_acepta_lo_calculado():
    titulo, t, rutas, a, d = _valido()
    assert tr.validar(titulo, t, rutas, a, d, "corpus") == []


def test_validar_rechaza():
    titulo, t, rutas, a, d = _valido()

    def con(clave, v):
        return [(k, v if k == clave else x) for k, x in t]

    casos = {
        "sin trailers": ([], titulo, rutas),
        "Tipo inválido": (con("Tipo", "otra"), titulo, rutas),
        "Articulos-Modificados": (con("Articulos-Modificados", "004, 022"), titulo, rutas),
        "título incoherente": (t, "Reforma LGS (DOF 2026-01-16): art. 4o", rutas),
        "fuera de lgs": (t, titulo, rutas + ["lft/001.md"]),
        "Extractor mal formado": (con("Extractor", "fiscal-extractor"), titulo, rutas),
        "Publicacion": (con("Publicacion", "2026-01-16"), titulo, rutas),
        "falta Fuente-Sha256": ([x for x in t if x[0] != "Fuente-Sha256"], titulo, rutas),
        "Articulos-Corregidos": (con("Tipo", "correccion"), titulo, rutas),
    }
    for esperado, (tt, ti, ru) in casos.items():
        errores = tr.validar(ti, tt, ru, a, d, "corpus")
        assert any(esperado in e for e in errores), (esperado, errores)


def test_validar_indice():
    t = tr.trailers_indice(EXT)
    lee = tr.lector_dict({})
    assert tr.validar("Índice al día", t, ["fuentes.json", "metadata/documentos.json", "README.md"],
                      lee, lee, "corpus") == []
    errores = tr.validar("Índice al día", t, ["fuentes.json", "lgs/004.md"], lee, lee, "corpus")
    assert any("toca documentos" in e for e in errores)


def test_validar_fuente_de_constitucion():
    doc = "jalisco/constitucion"
    fuente = "Periódico Oficial del Estado de Jalisco — Congreso"
    antes = {**_meta(f"{doc}/metadata/", "2026-09-01", [], fuente=fuente),
             f"{doc}/articulos/015.md": "# Artículo 15\n\nAntes.\n",
             f"{doc}/fuente/constitucion.pdf": b"viejo"}
    despues = {**antes, f"{doc}/articulos/015.md": "# Artículo 15\n\nDespués.\n",
               f"{doc}/fuente/constitucion.pdf": b"nuevo"}
    rutas = [f"{doc}/articulos/015.md", f"{doc}/fuente/constitucion.pdf"]
    a, d = tr.lector_dict(antes), tr.lector_dict(despues)
    kw = dict(fuente="https://x", extractor="OpenCodice/constitucion-extractor@abcdef0")
    titulo, t = tr.calcular(doc, "reforma", rutas, a, d,
                            fuente_sha256=tr.sha256_bytes(b"nuevo"), **kw)
    assert tr.validar(titulo, t, rutas, a, d, "estatal") == []
    titulo, t = tr.calcular(doc, "reforma", rutas, a, d,
                            fuente_sha256=tr.sha256_bytes(b"viejo"), **kw)
    assert any("fuente/" in e for e in tr.validar(titulo, t, rutas, a, d, "estatal"))
