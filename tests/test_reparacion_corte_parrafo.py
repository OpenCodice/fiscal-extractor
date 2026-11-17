"""Cortes de párrafo de las leyes estatales (Jalisco, Querétaro)."""
from extractor.parsers import articulado as A


def renglon(texto, top, x1, margen=527.0, palabra=30.0):
    return {"texto": texto, "top": top, "x1": x1, "palabra": palabra, "margen": margen}


def test_interlineado_con_parrafos_de_un_renglon():
    # La mayoría de los pasos son de párrafo a párrafo (23 pt), pero el
    # interlineado es el menor frecuente (11.4 pt).
    pagina = []
    top = 0.0
    for k in range(60):
        pagina.append(renglon(f"a{k}", top, 300))
        top += 23.2
    for k in range(40):
        pagina.append(renglon(f"b{k}", top, 527))
        top += 11.4
    assert A._interlineado([pagina]) == 11.0


def test_parrafos_de_un_renglon_se_separan():
    pagina = [renglon("Las disposiciones serán ley supletoria de toda la Legislación Estatal.",
                      0.0, 501, palabra=30.0),
              renglon("Cuando en este código se use el genérico masculino por efecto", 23.2, 527),
              renglon("gramatical, se entenderá que aplican", 34.6, 300)]
    relleno = [[renglon(f"x{k}", 11.4 * k, 527) for k in range(30)],
               [renglon(f"y{k}", 23.2 * k, 300) for k in range(60)]]
    texto = "\n".join(r["texto"] for r in pagina)
    cortes = A.cortes_geometricos([pagina] + relleno, texto)
    assert cortes[(pagina[0]["texto"], pagina[1]["texto"])] is True
    assert cortes[(pagina[1]["texto"], pagina[2]["texto"])] is False


def test_nota_separada_del_renglon_no_pierde_la_sincronia():
    a = renglon("motriz que dificulta su desplazamiento; (Adición P. O. No. 38, 11-V-18)", 0.0, 520)
    b = renglon("XV. Los elementos de accesibilidad universal que los sectores público y", 11.4, 527)
    c = renglon("privado deberán implementar en la infraestructura", 22.8, 527)
    relleno = [renglon(f"z{k}", 11.4 * k, 527) for k in range(30)]
    texto = "\n".join(["motriz que dificulta su desplazamiento;", "(Adición P. O. No. 38, 11-V-18)",
                       b["texto"], c["texto"]])
    cortes = A.cortes_geometricos([[a, b, c], relleno], texto)
    assert cortes[(b["texto"], c["texto"])] is False


def test_linea_que_acaba_en_particula_sigue_aunque_haya_espacio_de_parrafo():
    a = renglon("I. Los recursos financieros que se le asignen en el Presupuesto del", 0.0, 504.8,
                margen=557.0, palabra=50.3)
    # 'humanos' no es partícula: el párrafo cierra aunque llegue al margen.
    d = renglon("No podrán tener carácter preferente las iniciativas, contra los derechos humanos",
                60.0, 526.8, margen=557.0, palabra=12.3)
    e = renglon("La iniciativa preferente podrá versar", 85.2, 300, margen=557.0)
    b = renglon("Estado de Querétaro para su funcionamiento;", 20.4, 150, margen=557.0, palabra=50.3)
    c = renglon("II. Los subsidios y apoyos;", 40.8, 200, margen=557.0, palabra=30.0)
    relleno = [renglon(f"z{k}", 12.0 * k, 557) for k in range(40)]
    texto = "\n".join(r["texto"] for r in (a, b, c))
    cortes = A.cortes_geometricos([[a, b, c, d, e], relleno],
                                  texto + "\n" + d["texto"] + "\n" + e["texto"])
    assert cortes[(a["texto"], b["texto"])] is False
    assert cortes[(b["texto"], c["texto"])] is True
    assert cortes[(d["texto"], e["texto"])] is True


def test_inciso_en_mayuscula_abre_parrafo():
    a = renglon("A) El Secretario Administrativo", 0.0, 250, palabra=20.0)
    b = renglon("B) El Secretario de Finanzas", 11.5, 242, palabra=20.0)
    relleno = [renglon(f"z{k}", 11.5 * k, 527) for k in range(40)]
    cortes = A.cortes_geometricos([[a, b], relleno], f"{a['texto']}\n{b['texto']}")
    assert cortes[(a["texto"], b["texto"])] is True


def test_rotulo_con_letra_romana_es_nombre():
    assert A._es_nombre_suelto("C) DEL SECRETARIO DE FINANZAS", estatal=True)
    assert A._es_nombre_suelto("D) DE LOS DIRECTORES", estatal=True)
    assert not A._es_nombre_suelto("D) El Director del Centro", estatal=True)
    assert not A._es_nombre_suelto("C) DEL SECRETARIO DE FINANZAS", estatal=False)


def test_glifo_suelto_y_titulo_pegado_no_son_del_articulo():
    texto = "\n".join([
        "Artículo 1.- El tutor puede dar en arrendamiento los bienes del incapaz.",
        "|",
        "Artículo 2.- Se sustraiga al menor de edad. TÍTULO SEPTIMO",
        "De Niñas, Niños y Adolescentes",
        "Artículo 3.- Niñas, niños y adolescentes deben ser objeto de atención.",
    ])
    us = A.parse_texto(texto, estatal=True)
    assert "|" not in us[0].cuerpo
    assert "TÍTULO" not in us[1].cuerpo
    assert us[2].titulo.startswith("TÍTULO SEPTIMO")
