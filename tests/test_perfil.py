"""El perfil de lectura aísla lo propio de cada fuente (extractor/perfil.py)."""
import pytest

from extractor import registro
from extractor.estatales import ENTIDADES, perfil_de_estado
from extractor.parsers import articulado
from extractor.parsers.articulado import parse_texto
from extractor.perfil import ESTATAL_BASE, FEDERAL, HEREDADOS, Perfil, Rasgo

# Los rasgos que leía toda ley estatal antes de que hubiera perfiles. Un rasgo
# nuevo no entra aquí: va en el perfil del estado que lo necesita, y así no
# cambia la lectura de los demás.
_HEREDADOS = {
    "rotulo-abreviado", "nota-tras-epigrafe", "comilla-de-decreto", "uno-como-i",
    "glifos-sueltos", "epigrafe-marginal", "rotulo-de-inciso", "encabezado-con-punto",
    "nota-de-denominacion", "nombre-de-dos-partes", "nombre-tras-encabezado-con-punto",
    "nombre-partido-en-conjuncion", "nombre-envuelto-en-minuscula", "nombre-con-punto",
    "nombre-de-titulo-con-punto", "nombre-en-mayusculas-envuelto", "titulo-sin-rotulo",
    "epigrafe-con-comas", "derogado-final-es-texto", "epigrafe-tras-derogado",
    "epigrafe-tras-parrafo-sin-punto", "nota-envuelta-no-es-rotulo", "epigrafe-sin-oraciones",
    "nota-de-encabezado-tras-articulo", "nota-sigue-en-bloque", "nota-del-editor-sigue",
    "nota-de-encabezado-partida", "nota-del-editor-tras-nombre", "letra-sin-articulo",
    "sic-es-el-esperado", "sic-en-la-letra", "bis-antes-de-su-base", "cita-de-este-codigo",
    "ordinal-sin-o",
}


def test_los_heredados_no_crecen():
    assert {r.value for r in HEREDADOS} == _HEREDADOS
    assert ESTATAL_BASE.rasgos == HEREDADOS and ESTATAL_BASE.estatal


def test_el_perfil_federal_no_lee_nada_estatal():
    assert not FEDERAL.estatal and not FEDERAL.rasgos and not FEDERAL.pre_texto
    with pytest.raises(ValueError):
        Perfil(rasgos=frozenset({Rasgo.UNO_COMO_I}))


def test_todo_perfil_de_estado_parte_de_los_heredados():
    for estado in ENTIDADES:
        perfil = perfil_de_estado(estado)
        assert perfil.estatal and perfil.rasgos >= HEREDADOS, estado


def test_el_perfil_de_un_documento_es_el_de_su_estado():
    for doc in registro.DOCUMENTOS:
        esperado = perfil_de_estado(doc.clave.split("/")[0]) if doc.medio else FEDERAL
        assert articulado.perfil_de(doc) == esperado, doc.clave


_TEXTO = "ARTÍCULO 221.- Uno.\nARTÍCULO 22I BIS.- Uno bis.\nARTÍCULO 222.- Dos.\n"


def _claves(**kw) -> list[tuple[int, str]]:
    return [(u.numero, u.ordinal) for u in parse_texto(_TEXTO, start=221, **kw)]


def test_un_rasgo_apagado_no_se_lee():
    sin = Perfil(estatal=True, rasgos=HEREDADOS - {Rasgo.UNO_COMO_I})
    assert _claves(perfil=ESTATAL_BASE) == [(221, ""), (221, "Bis"), (222, "")]
    assert _claves(perfil=sin) == [(221, ""), (222, "")]


def test_estatal_es_el_perfil_heredado():
    assert _claves(estatal=True) == _claves(perfil=ESTATAL_BASE)
    assert parse_texto(_TEXTO, start=221, estatal=True) == parse_texto(
        _TEXTO, start=221, perfil=ESTATAL_BASE)


def test_un_paso_propio_corre_antes_de_segmentar():
    propio = ESTATAL_BASE.con(pre_texto=(lambda t: t.replace("Numeral", "Artículo"),))
    texto = "Numeral 1.- Uno.\nNumeral 2.- Dos.\n"
    assert [u.numero for u in parse_texto(texto, perfil=propio)] == [1, 2]
    assert parse_texto(texto, perfil=ESTATAL_BASE) == []
