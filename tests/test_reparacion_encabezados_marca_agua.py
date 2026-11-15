from extractor.parsers.articulado import parse_texto


def _cuerpos(texto, start=1):
    return {u.numero: u for u in parse_texto(texto, start=start)}


def test_marca_de_agua_tras_nombre_de_capitulo_no_se_pega_al_articulo():
    t = """Artículo 32.
Texto del articulo.
CAPÍTULO VII
DEL COMERCIO DE SEMILLAS
(P
rim
e
Artículo 33.
Otro texto.
"""
    u = _cuerpos(t, 32)
    assert u[32].cuerpo.endswith("Texto del articulo.")
    assert u[33].capitulo.startswith("CAPÍTULO VII")


def test_nombre_en_mayusculas_de_tres_renglones_bajo_seccion_title_case():
    t = """Artículo 1o.
Texto previo.
_______________
Sección XVI
MÁQUINAS Y APARATOS, MATERIAL ELÉCTRICO Y SUS PARTES; APARATOS DE
GRABACIÓN O REPRODUCCIÓN DE SONIDO, APARATOS DE GRABACIÓN O
REPRODUCCIÓN DE IMAGEN Y SONIDO EN TELEVISIÓN
Notas.
1. Esta Sección no comprende:
"""
    u = _cuerpos(t)
    # Sin artículo que lo siga no es estructura: queda íntegro en el cuerpo.
    assert "Sección XVI\nMÁQUINAS" in u[1].cuerpo
    assert "REPRODUCCIÓN DE IMAGEN Y SONIDO EN TELEVISIÓN\nNotas." in u[1].cuerpo
    assert u[1].seccion == ""
    assert u[1].cuerpo.endswith("1. Esta Sección no comprende:")


def test_nombre_entre_corchetes_en_dos_renglones():
    t = """Artículo 6o.
3. Algo.
LIBRO SEGUNDO
[De la Integración de los Poderes y de las Entidades
Federativas, así como de los Ayuntamientos]
Denominación del Libro reformada DOF 02-03-2023
Artículo 7o.
1. Votar.
"""
    u = _cuerpos(t, 6)
    assert "Federativas" not in u[6].cuerpo
    assert "Ayuntamientos]" in u[7].titulo


def test_bloque_largo_de_notas_sigue_siendo_estructura():
    notas = "\n".join(f"Denominación reformada DOF 02-03-20{n:02d}" for n in range(10))
    t = f"""Artículo 6o.
3. Algo.
LIBRO SEGUNDO
[Nombre]
{notas}
TÍTULO PRIMERO
[Otro]
{notas}
CAPÍTULO I
De los Derechos
Artículo 7o.
1. Votar.
"""
    u = _cuerpos(t, 6)
    assert u[6].cuerpo.endswith("3. Algo.")
    assert u[7].capitulo.startswith("CAPÍTULO I")
