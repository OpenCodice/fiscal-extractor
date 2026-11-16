"""Una tabla de cuotas con encabezados girados deja renglones cortos ('2', '3',
'a') que no son marca de agua: _quitar_marca_girada no debe borrarlos."""
from extractor.parsers.articulado import _quitar_marca_girada

TABLA = "\n".join(
    ["Apartado A, fuente de extracción aguas superficiales"]
    + ["e d a", "d", "a", "4", "n a", "2", "$", "$", "3", "9", "5", "1", "0", "7", "6", "8"]
    + ["3 $1.9 759"])


def test_tabla_con_signos_de_pesos_sueltos_conserva_los_digitos():
    assert _quitar_marca_girada(TABLA) == TABLA


def test_marca_girada_sin_tabla_sigue_quitandose():
    pagina = "\n".join(["Texto legal."] + ["D", "IA", "IO", "O F", "L", "c", "ió", "n", "e"])
    assert _quitar_marca_girada(pagina) == "Texto legal."
