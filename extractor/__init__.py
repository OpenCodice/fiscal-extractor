"""fiscal-extractor — extracción del corpus fiscal mexicano a texto + metadata.

Mismo patrón de 3 capas que `constitucion-extractor`, generalizado a un
**registro de documentos** (CFF, LISR, LIVA, reglamentos, RMF, criterios…):

  1. Extracción fiel    PDF/fuente → texto por unidad     ← fuente de verdad
  2. Detección          git diff                          ← lógica principal
  3. Metadata derivada  fechas, índice, reformas          ← regenerable

La capa 3 nunca toca los archivos de la capa 1.
"""
