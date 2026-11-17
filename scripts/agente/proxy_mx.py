#!/usr/bin/env python3
"""Puerta local hacia el Worker egress-mx para el agente de la ronda de
expansión: `GET http://127.0.0.1:<puerto>/?url=<url>` descarga `url` desde
México, si su dominio está en la lista del Worker. Así el agente puede llegar a
los sitios que rechazan IP extranjeras sin tener EGRESS_MX_TOKEN: el token se
lee de un archivo que se borra al arrancar (no va en el entorno del proceso).

Uso: proxy_mx.py ARCHIVO_TOKEN [PUERTO]
"""
import http.server
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

EGRESS_MX = os.environ.get("EGRESS_MX_URL", "https://egress-mx.danielcardeenas.workers.dev/")


def main() -> None:
    ruta, puerto = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 8765
    with open(ruta, encoding="utf-8") as f:
        token = f.read().strip()
    os.unlink(ruta)

    class Puerta(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 — nombre de la API
            destino = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("url", [""])[0]
            if not destino.startswith(("https://", "http://")):
                self.send_error(400, "falta ?url=")
                return
            pet = urllib.request.Request(f"{EGRESS_MX}?url={urllib.parse.quote(destino, safe='')}",
                                         headers={"Authorization": f"Bearer {token}",
                                                  "User-Agent": "opencodice-expansion"})
            try:
                r = urllib.request.urlopen(pet, timeout=120)
            except urllib.error.HTTPError as e:
                r = e
            except Exception as e:                   # noqa: BLE001 — se le dice al agente
                self.send_error(502, f"{type(e).__name__}: {e}"[:200])
                return
            cuerpo = r.read()
            self.send_response(r.status if hasattr(r, "status") else r.code)
            for h in ("content-type", "x-url-final", "last-modified", "etag"):
                if r.headers.get(h):
                    self.send_header(h, r.headers[h])
            self.send_header("content-length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def log_message(self, *args):
            pass

    http.server.ThreadingHTTPServer(("127.0.0.1", puerto), Puerta).serve_forever()


if __name__ == "__main__":
    main()
