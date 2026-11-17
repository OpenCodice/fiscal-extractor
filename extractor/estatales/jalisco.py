"""Jalisco: la Biblioteca Virtual del Congreso del Estado.

Su "Listado Completo" enlaza el PDF vigente de cada ley, con la fecha de la
última actualización al final del nombre (DDMMAA: '…de Jalisco-240626.pdf'),
junto a versiones anteriores marcadas '(anterior)'. Los PDF no anotan las
reformas en el texto: las listan al final, en la TABLA DE REFORMAS Y
ADICIONES, de donde sale la versión (ver `articulado.fecha_version`).
"""
from . import ley

MEDIO = "Periódico Oficial del Estado de Jalisco"
# Notas del editor sobre porciones invalidadas o reformadas, entre paréntesis
# tras el párrafo que anotan: '(La porción normativa resaltada fue declarada
# Inconstitucional…)', '(las porciones normativas resaltadas fueron reformadas…)'.
NOTAS = r"^\((?i:la\s+porci[óo]n\s+normativa|las\s+porciones\s+normativas)\b"
INDICE = ("https://congresoweb.congresojal.gob.mx/bibliotecavirtual/busquedasleyes/"
          "Listado'2.cfm")


def _jal(nombre: str, sigla: str, carpeta: str) -> object:
    # La carpeta y el nombre van tal cual en el enlace (con acentos y espacios);
    # a veces con un espacio antes del guion de la fecha.
    return ley("jalisco", nombre, sigla, medio=MEDIO, indice=INDICE, orden="ddmmaa", notas=NOTAS,
               patron=(rf"/Documentos_PDF-{carpeta}/{nombre}\s?-\d{{6}}\.pdf$"))


LEYES = [
    _jal("Código Civil del Estado de Jalisco", "CC Jalisco", "Códigos"),
    _jal("Código Penal para el Estado Libre y Soberano de Jalisco", "CP Jalisco", "Códigos"),
    _jal("Código de Procedimientos Civiles del Estado de Jalisco", "CPC Jalisco", "Códigos"),
    _jal("Código Electoral del Estado de Jalisco", "CE Jalisco", "Códigos"),
    _jal("Código de Asistencia Social del Estado de Jalisco", "CAS Jalisco", "Códigos"),
    _jal("Ley Orgánica del Poder Legislativo del Estado de Jalisco", "LOPL Jalisco", "Leyes"),
    _jal("Ley Orgánica del Poder Ejecutivo del Estado de Jalisco", "LOPE Jalisco", "Leyes"),
    _jal("Ley Orgánica del Poder Judicial del Estado de Jalisco", "LOPJ Jalisco", "Leyes"),
]
