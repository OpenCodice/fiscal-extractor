# Certificados intermedios

Copia de `constitucion-extractor/certs/` (ver su README para la huella y la
fuente de cada uno). Algunos sitios estatales no envían el intermedio de su
cadena TLS; `extractor/fuentes.py` los añade al almacén del sistema y la cadena
se sigue validando hasta una raíz de confianza.

- `letsencrypt-yr2.pem` e `isrg-root-yr-cross-x1.pem` — los necesita la CDMX
  (data.consejeria.cdmx.gob.mx).
- `sectigo-public-server-authentication-ca-dv-r36.pem` — Hidalgo y Tlaxcala.
