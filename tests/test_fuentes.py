"""Resolución de la URL vigente contra la página índice del SAT (unitario).

No toca la red: se inyecta el HTML. Lo que importa es que ante varias versiones
del mismo documento gane la de fecha DDMMYYYY más reciente, y que un patrón sin
coincidencias truene (señal de que el SAT cambió la página).
"""
import pytest

from extractor.fuentes import _fecha_nombre, url_vigente
from extractor.registro import POR_CLAVE

HTML = """
<a href="documentos2026/rmf/rmf/RMF_2026-DOF-28122025.pdf">RMF</a>
<a href="documentos2026/rmf/rmf/RMF_2026-DOF-15032026.pdf">RMF compilada</a>
<a href="documentos2026/rmf/anticipadas/1aRM_RMF2026-Novena_version_anticipada_14052026.pdf">anticipada</a>
<a href="documentos2026/rmf/anexos/Anexo_7_RMF2026-09012026.pdf">A7</a>
<a href="documentos2026/rmf/anexos/Anexo_3_RMF2026-09012026.pdf">A3</a>
<a href="documentos2026/rmf/anexos/Anexo_3_RMF2026-20072026.pdf">A3 nueva</a>
"""


def test_gana_la_fecha_mas_reciente():
    url = url_vigente(POR_CLAVE["criterios-no-vinculativos"], leer=lambda _u: HTML)
    assert url.endswith("rmf/anexos/Anexo_3_RMF2026-20072026.pdf")
    assert url.startswith("https://www.sat.gob.mx/minisitio/NormatividadRMFyRGCE/")


def test_rmf_ignora_versiones_anticipadas():
    # Las anticipadas (1aRM_RMF2026…) viven en otra carpeta y no son texto DOF.
    url = url_vigente(POR_CLAVE["rmf-2026"], leer=lambda _u: HTML)
    assert url.endswith("rmf/rmf/RMF_2026-DOF-15032026.pdf")


def test_patron_sin_coincidencias_truena():
    with pytest.raises(LookupError, match="criterios-normativos"):
        url_vigente(POR_CLAVE["criterios-normativos"], leer=lambda _u: "<html></html>")


def test_documento_sin_indice_usa_url_directa():
    cff = POR_CLAVE["cff"]
    assert url_vigente(cff, leer=lambda _u: 1 / 0) == cff.url


def test_fecha_nombre_ddmmyyyy():
    assert _fecha_nombre("x/RMF_2026-DOF-28122025.pdf") == (2025, 12, 28)
    assert _fecha_nombre("x/Anexo_7_RMF2026-09012026.pdf") == (2026, 1, 9)
    assert _fecha_nombre("x/sin_fecha.pdf") == (0, 0, 0)
