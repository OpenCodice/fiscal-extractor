"""Pruebas del resolutor de referencias legales cruzadas.

Los casos replican formas reales del corpus (criterios, RMF, RGCE,
reglamentos). La validación contra el corpus es parte del contrato: una cita
que no resuelve a una unidad existente NO se emite.
"""
import json

from extractor.referencias import (Resolutor, aplicar_referencias,
                                   clave_articulo, claves_corpus)

CLAVES = {
    "cff": {"014", "029", "029-a", "042", "046", "048", "069-b", "017-h-bis"},
    "lisr": {"027", "091", "113-e", "151"},
    "liva": {"001", "002-a", "011"},
    "ladua": {"088-bis"},
    "rcff": {"030"},
    "rmf-2026": {"2.7.1.21", "3.17.11"},
    "rgce-2026": {"3.7.5", "3.7.35"},
}


def _res():
    return Resolutor(CLAVES)


# ----------------------------- claves de artículo --------------------------- #
def test_clave_articulo_normaliza_sufijos():
    assert clave_articulo("151", None, None, None) == "151"
    assert clave_articulo("2", "A", None, None) == "002-a"
    assert clave_articulo("17", "H", "Bis", None) == "017-h-bis"
    assert clave_articulo("137", None, "Bis", "1") == "137-bis-1"


# ------------------------------- artículos ---------------------------------- #
def test_cita_explicita_a_ley():
    refs = _res().referencias(
        "Conforme al artículo 151 de la Ley del Impuesto sobre la Renta, las "
        "personas físicas...", "criterios-normativos")
    assert refs == ["lisr/151"]


def test_lista_de_articulos_con_fracciones():
    refs = _res().referencias(
        "los artículos 46, fracción IV y 48, fracción IV del CFF, como "
        "resultado del ejercicio de las facultades", "criterios-normativos")
    assert refs == ["cff/046", "cff/048"]


def test_sufijo_ordinal_y_letra():
    refs = _res().referencias(
        "el artículo 2o.-A de la Ley del IVA y el artículo 17-H Bis del CFF",
        "criterios-normativos")
    assert refs == ["liva/002-a", "cff/017-h-bis"]


def test_la_ley_dentro_de_reglamento_es_su_ley():
    # RLA: "Para los efectos del artículo 88 bis, quinto párrafo, de la Ley…"
    refs = _res().referencias(
        "Para los efectos del artículo 88 bis, quinto párrafo, de la Ley, el "
        "factor aplicable que la Secretaría determine", "rladua")
    assert refs == ["ladua/088-bis"]


def test_la_ley_en_rgce_es_la_aduanera():
    refs = _res().referencias(
        "Para efectos del artículo 88 bis, quinto párrafo de la Ley y de las "
        "reglas 3.7.5. y 3.7.35., se aplicarán las siguientes tasas globales",
        "rgce-2026")
    assert "ladua/088-bis" in refs
    assert "rgce-2026/3.7.5" in refs and "rgce-2026/3.7.35" in refs


def test_este_codigo_solo_en_cff_y_su_reglamento():
    txt = "lo previsto en el artículo 42 de este Código"
    assert _res().referencias(txt, "cff") == ["cff/042"]
    assert _res().referencias(txt, "lisr") == []


def test_version_historica_se_excluye():
    refs = _res().referencias(
        "el artículo 91 de la Ley del ISR vigente hasta el 31 de diciembre "
        "de 2013, establecía", "criterios-normativos")
    assert refs == []


def test_anafora_no_resuelve():
    refs = _res().referencias(
        "el artículo 141 del mismo Código, señala las formas; el artículo 142 "
        "del citado ordenamiento legal refiere los casos", "criterios-normativos")
    assert refs == []


def test_codigos_no_fiscales_no_resuelven():
    refs = _res().referencias(
        "el artículo 14 del Código Civil Federal, en relación con el Código "
        "Nacional de Procedimientos Penales", "criterios-normativos")
    assert refs == []


def test_articulo_inexistente_se_descarta():
    refs = _res().referencias(
        "el artículo 999 del CFF establece", "criterios-normativos")
    assert refs == []


def test_lista_con_letras():
    refs = _res().referencias(
        "los artículos 29 y 29-A del CFF, tratándose de pagos mayores a "
        "$2,000.00 efectuados el 31 de enero", "rmf-2026")
    assert refs == ["cff/029", "cff/029-a"]


def test_montos_y_porcentajes_no_son_articulos():
    refs = _res().referencias(
        "el artículo 14 del CFF no aplica a operaciones de 2,500 pesos ni "
        "al 30 % de los ingresos", "criterios-normativos")
    assert refs == ["cff/014"]


# --------------------------------- reglas ----------------------------------- #
def test_regla_sin_documento_explicito_es_de_la_propia_resolucion():
    refs = _res().referencias(
        "el aviso a que se refiere la regla 2.7.1.21., dentro del mes",
        "rmf-2026")
    assert refs == ["rmf-2026/2.7.1.21"]


def test_regla_citada_desde_criterio_requiere_documento_explicito():
    base = "según la regla 2.7.1.21."
    assert _res().referencias(base, "criterios-normativos") == []
    refs = _res().referencias(base + " de la RMF", "criterios-normativos")
    assert refs == ["rmf-2026/2.7.1.21"]


def test_autorreferencia_y_dedup():
    res = _res()
    refs = res.referencias(
        "el artículo 151 de la Ley del ISR y el propio artículo 151 de la Ley "
        "del ISR", "criterios-normativos")
    assert refs == ["lisr/151"]


# --------------------------- aplicación al repo ------------------------------ #
def test_aplicar_referencias_anota_pasajes(tmp_path):
    meta = tmp_path / "metadata"
    (meta / "lisr").mkdir(parents=True)
    (meta / "criterios-normativos").mkdir(parents=True)
    (meta / "lisr" / "articulos.json").write_text(json.dumps({
        "documento": "lisr",
        "articulos": [{"clave": "151"}],
    }), encoding="utf-8")
    (meta / "criterios-normativos" / "articulos.json").write_text(json.dumps({
        "documento": "criterios-normativos",
        "criterios": [{"clave": "23-isr-pi"}],
    }), encoding="utf-8")
    pasaje = {"id": "criterios-normativos/23-isr-pi.p1",
              "documento": "criterios-normativos", "clave_unidad": "23-isr-pi",
              "texto": "Conforme al artículo 151 de la Ley del ISR, los pagos…"}
    (meta / "criterios-normativos" / "pasajes.jsonl").write_text(
        json.dumps(pasaje, ensure_ascii=False) + "\n", encoding="utf-8")

    stats = aplicar_referencias(tmp_path)
    assert stats["criterios-normativos"] == 1
    anotado = json.loads(
        (meta / "criterios-normativos" / "pasajes.jsonl").read_text().strip())
    assert anotado["referencias"] == ["lisr/151"]

    # Idempotente: segunda pasada no duplica ni rompe.
    aplicar_referencias(tmp_path)
    otra = json.loads(
        (meta / "criterios-normativos" / "pasajes.jsonl").read_text().strip())
    assert otra == anotado


def test_claves_corpus_lee_todos_los_tipos(tmp_path):
    meta = tmp_path / "metadata" / "rmf-2026"
    meta.mkdir(parents=True)
    (meta / "articulos.json").write_text(json.dumps({
        "documento": "rmf-2026", "reglas": [{"clave": "2.7.1.21"}],
    }), encoding="utf-8")
    assert claves_corpus(tmp_path) == {"rmf-2026": {"2.7.1.21"}}
