import re

from extractor.normalize import normalize_body
from extractor.parsers.articulado import ARTICULO_ESTATAL_RE, parse_texto

NOTAS = re.compile(r"^\((?:REFORMAD|ADICIONAD)")

PDF = "\n".join([
    "Artículo 1. Sujetos obligados",
    "La presente Ley es de orden público y tiene por objeto reglamentar las cosas.",
    "Artículo 2. Principios",
    "Los recursos serán administrados con eficiencia.",
    "Artículo 3. Convocatoria, adjudicación o contratación por parte de los entes",
    "gubernamentales",
    "Las unidades de compras podrán convocar y adjudicar.",
    "(REFORMADO, P.O. 30 DE JUNIO DE 2023)",
    "Artículo 4. Tipos de procedimientos",
    "(REFORMADO, P.O. 30 DE JUNIO DE 2023)",
    "Los entes seleccionarán el procedimiento.",
    "Artículo 5. El precio de los inmuebles que se vayan a adquirir, así como el monto",
    "de rentas que pague el Estado no podrá exceder del dictamen.",
    "Artículo 6. Definiciones",
    "Para los efectos de esta Ley se entenderá por:",
    "Artículo 7. Otro",
    "Texto del siete.",
    "Artículo 8. Otro más",
    "Texto del ocho.",
    "Artículo 9. Uno más",
    "Texto del nueve.",
    "Artículo 10. Último",
    "Texto del diez.",
    "Artículo 11. Aún",
    "Texto del once.",
    "Artículo 12. Fin",
    "Texto del doce.",
])


def test_epigrafe_marginal_va_al_contexto_y_no_al_cuerpo():
    us = parse_texto(PDF, estatal=True, notas=NOTAS, notas_previas=NOTAS)
    por = {u.numero: u for u in us}
    assert por[1].epigrafe == "Sujetos obligados"
    assert "Sujetos" not in por[1].cuerpo
    # envuelto en dos renglones
    assert por[3].epigrafe == ("Convocatoria, adjudicación o contratación por parte de los "
                               "entes gubernamentales")
    assert "gubernamentales" not in por[3].cuerpo
    # la misma nota antes del rótulo y tras el epígrafe es una sola
    assert por[4].epigrafe == "Tipos de procedimientos"
    assert por[4].cuerpo.count("REFORMADO") == 1
    # texto que envuelve, sin epígrafe: se queda en el cuerpo
    assert por[5].epigrafe == ""
    assert "El precio de los inmuebles" in por[5].cuerpo


def test_ley_sin_epigrafes_marginales_no_cambia():
    t = "\n".join(f"Artículo {n}. Los recursos serán administrados con eficiencia\n"
                 "y economía, conforme a la ley." for n in range(1, 13))
    assert all(u.epigrafe == "" for u in parse_texto(t, estatal=True))


def test_comilla_de_apertura_del_articulo_se_conserva_en_estatal():
    cuerpo = "“Artículo 23. Durante el tiempo que\ncomprenden las campañas.”\n"
    out = normalize_body(cuerpo, "Artículo 23", rotulo=ARTICULO_ESTATAL_RE, cortes={})
    assert out.startswith("“Durante") and out.endswith("campañas.”")


def test_nota_del_editor_es_parrafo_propio():
    cuerpo = ("Artículo 175. Texto.\nNo se permitirá la distribución de despensas.”\n"
              "*N. de E. La fracción I fue declarada inválida.\n")
    out = normalize_body(cuerpo, "Artículo 175", rotulo=ARTICULO_ESTATAL_RE,
                         cortes={("a", "b"): False})
    assert out.split("\n\n")[-1].startswith("*N. de E.")
