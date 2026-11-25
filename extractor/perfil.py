"""Perfil de lectura del articulado: qué particularidades de una fuente lee el parser.

Las leyes de la Cámara de Diputados comparten un solo formato. Cada estado
compila las suyas a su manera, y lo que hace falta para leer el PDF de uno
(un rótulo abreviado, una nota del editor entre el capítulo y su nombre) puede
estropear la lectura de otro. Por eso lo propio de una fuente no se activa con
un interruptor común: cada particularidad es un `Rasgo` con nombre, y el
perfil de cada estado (`PERFIL` en su módulo de `extractor/estatales/`) dice
cuáles lee.

Un arreglo nuevo para un estado es un rasgo nuevo que solo declara el perfil
de ese estado, o un paso de `pre_texto` escrito en su módulo. Así, por
construcción, no cambia la lectura de los demás estados ni la de las leyes
federales: `HEREDADOS` (lo que leen todos los estados desde antes de que
hubiera perfiles) no crece, y una prueba lo fija.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Callable


class Rasgo(Enum):
    """Una particularidad de los PDF de alguna fuente estatal. El comentario de
    cada rama del parser que lo consulta la describe con su ejemplo."""
    # --- limpieza de página -------------------------------------------------
    ROTULO_ABREVIADO = "rotulo-abreviado"
    NOTA_TRAS_EPIGRAFE = "nota-tras-epigrafe"
    # --- texto antes de segmentar -------------------------------------------
    COMILLA_DE_DECRETO = "comilla-de-decreto"
    UNO_COMO_I = "uno-como-i"
    GLIFOS_SUELTOS = "glifos-sueltos"
    EPIGRAFE_MARGINAL = "epigrafe-marginal"
    # --- encabezados y sus nombres ------------------------------------------
    ROTULO_DE_INCISO = "rotulo-de-inciso"
    ENCABEZADO_CON_PUNTO = "encabezado-con-punto"
    NOTA_DE_DENOMINACION = "nota-de-denominacion"
    NOMBRE_DE_DOS_PARTES = "nombre-de-dos-partes"
    NOMBRE_TRAS_ENCABEZADO_CON_PUNTO = "nombre-tras-encabezado-con-punto"
    NOMBRE_PARTIDO_EN_CONJUNCION = "nombre-partido-en-conjuncion"
    NOMBRE_ENVUELTO_EN_MINUSCULA = "nombre-envuelto-en-minuscula"
    NOMBRE_CON_PUNTO = "nombre-con-punto"
    NOMBRE_DE_TITULO_CON_PUNTO = "nombre-de-titulo-con-punto"
    NOMBRE_EN_MAYUSCULAS_ENVUELTO = "nombre-en-mayusculas-envuelto"
    TITULO_SIN_ROTULO = "titulo-sin-rotulo"
    # --- epígrafes ----------------------------------------------------------
    EPIGRAFE_CON_COMAS = "epigrafe-con-comas"
    DEROGADO_FINAL_ES_TEXTO = "derogado-final-es-texto"
    EPIGRAFE_TRAS_DEROGADO = "epigrafe-tras-derogado"
    EPIGRAFE_TRAS_PARRAFO_SIN_PUNTO = "epigrafe-tras-parrafo-sin-punto"
    NOTA_ENVUELTA_NO_ES_ROTULO = "nota-envuelta-no-es-rotulo"
    EPIGRAFE_SIN_ORACIONES = "epigrafe-sin-oraciones"
    EPIGRAFE_TRAS_COMILLA_DE_CIERRE = "epigrafe-tras-comilla-de-cierre"
    EPIGRAFE_PARTIDO_TRAS_PARTICULA = "epigrafe-partido-tras-particula"
    NOTA_SIN_FECHA_NO_ES_NOTA = "nota-sin-fecha-no-es-nota"
    # --- notas dentro de un bloque de encabezado ----------------------------
    NOTA_DE_ENCABEZADO_TRAS_ARTICULO = "nota-de-encabezado-tras-articulo"
    NOTA_SIGUE_EN_BLOQUE = "nota-sigue-en-bloque"
    NOTA_DEL_EDITOR_SIGUE = "nota-del-editor-sigue"
    NOTA_DE_ENCABEZADO_PARTIDA = "nota-de-encabezado-partida"
    NOTA_DEL_EDITOR_TRAS_NOMBRE = "nota-del-editor-tras-nombre"
    # --- rótulos de artículo ------------------------------------------------
    LETRA_SIN_ARTICULO = "letra-sin-articulo"
    SIC_ES_EL_ESPERADO = "sic-es-el-esperado"
    SIC_EN_LA_LETRA = "sic-en-la-letra"
    BIS_ANTES_DE_SU_BASE = "bis-antes-de-su-base"
    CITA_DE_ESTE_CODIGO = "cita-de-este-codigo"
    ORDINAL_SIN_O = "ordinal-sin-o"
    # --- dónde empieza la ley -----------------------------------------------
    PREAMBULO_ANTES_DEL_ARTICULO_1 = "preambulo-antes-del-articulo-1"
    INTERLINEADO_DE_LA_LEY = "interlineado-de-la-ley"


@dataclass(frozen=True)
class Perfil:
    # Lee las convenciones comunes a las compilaciones estatales (rótulos de
    # `ARTICULO_ESTATAL_RE`, 'CÁPITULO', notas que siguen en otro renglón…).
    estatal: bool = False
    rasgos: frozenset[Rasgo] = frozenset()
    # Pasos propios de la fuente sobre el texto ya limpio, antes de segmentar:
    # cada uno recibe el texto y lo devuelve. Viven en el módulo del estado.
    pre_texto: tuple[Callable[[str], str], ...] = ()

    def __post_init__(self) -> None:
        if (self.rasgos or self.pre_texto) and not self.estatal:
            raise ValueError("solo un perfil estatal lleva rasgos o pasos propios")
        ajenos = [r for r in self.rasgos if not isinstance(r, Rasgo)]
        if ajenos:
            raise ValueError(f"rasgos desconocidos: {ajenos}")

    def lee(self, rasgo: Rasgo) -> bool:
        return rasgo in self.rasgos

    def con(self, *rasgos: Rasgo, pre_texto: tuple[Callable[[str], str], ...] = ()) -> "Perfil":
        """Este perfil más unos rasgos y pasos propios."""
        return replace(self, rasgos=self.rasgos | frozenset(rasgos),
                       pre_texto=self.pre_texto + tuple(pre_texto))


FEDERAL = Perfil()

# Lo que el parser leía en toda ley estatal cuando un solo interruptor activaba
# todo lo estatal. Los estados publicados entonces se verificaron así, y un
# estado nuevo empieza con lo mismo. No se le agregan rasgos: uno nuevo va en
# el perfil del estado que lo necesita.
HEREDADOS = frozenset({
    Rasgo.ROTULO_ABREVIADO, Rasgo.NOTA_TRAS_EPIGRAFE, Rasgo.COMILLA_DE_DECRETO,
    Rasgo.UNO_COMO_I, Rasgo.GLIFOS_SUELTOS, Rasgo.EPIGRAFE_MARGINAL,
    Rasgo.ROTULO_DE_INCISO, Rasgo.ENCABEZADO_CON_PUNTO, Rasgo.NOTA_DE_DENOMINACION,
    Rasgo.NOMBRE_DE_DOS_PARTES, Rasgo.NOMBRE_TRAS_ENCABEZADO_CON_PUNTO,
    Rasgo.NOMBRE_PARTIDO_EN_CONJUNCION, Rasgo.NOMBRE_ENVUELTO_EN_MINUSCULA,
    Rasgo.NOMBRE_CON_PUNTO, Rasgo.NOMBRE_DE_TITULO_CON_PUNTO,
    Rasgo.NOMBRE_EN_MAYUSCULAS_ENVUELTO, Rasgo.TITULO_SIN_ROTULO,
    Rasgo.EPIGRAFE_CON_COMAS, Rasgo.DEROGADO_FINAL_ES_TEXTO, Rasgo.EPIGRAFE_TRAS_DEROGADO,
    Rasgo.EPIGRAFE_TRAS_PARRAFO_SIN_PUNTO, Rasgo.NOTA_ENVUELTA_NO_ES_ROTULO,
    Rasgo.EPIGRAFE_SIN_ORACIONES, Rasgo.NOTA_DE_ENCABEZADO_TRAS_ARTICULO,
    Rasgo.NOTA_SIGUE_EN_BLOQUE, Rasgo.NOTA_DEL_EDITOR_SIGUE,
    Rasgo.NOTA_DE_ENCABEZADO_PARTIDA, Rasgo.NOTA_DEL_EDITOR_TRAS_NOMBRE,
    Rasgo.LETRA_SIN_ARTICULO, Rasgo.SIC_ES_EL_ESPERADO, Rasgo.SIC_EN_LA_LETRA,
    Rasgo.BIS_ANTES_DE_SU_BASE, Rasgo.CITA_DE_ESTE_CODIGO, Rasgo.ORDINAL_SIN_O,
})

ESTATAL_BASE = Perfil(estatal=True, rasgos=HEREDADOS)


def de(estatal: "bool | Perfil") -> Perfil:
    """El perfil que corresponde a un interruptor `estatal` (o el perfil mismo)."""
    if isinstance(estatal, Perfil):
        return estatal
    return ESTATAL_BASE if estatal else FEDERAL
