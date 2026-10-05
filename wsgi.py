"""Adaptateur WSGI, pour les hébergeurs qui l'imposent (PythonAnywhere…).

Réutilise tel quel le Handler de server.py : seule la sortie (respond) change.
ADMIN_USER, ADMIN_PASSWORD et éventuellement DB_PATH doivent être définis dans
os.environ avant l'import de ce module.
"""
import io
from email.message import Message
from http import HTTPStatus

import server

if not (server.ADMIN_USER and server.ADMIN_PASSWORD):
    raise RuntimeError("Définir ADMIN_USER et ADMIN_PASSWORD.")
server.init_db()


class WSGIHandler(server.Handler):
    def __init__(self, environ):  # pas d'appel au constructeur socket du parent
        self.command = environ["REQUEST_METHOD"]
        self.path = environ.get("PATH_INFO") or "/"
        self.client_address = (environ.get("REMOTE_ADDR", ""), 0)
        self.headers = Message()
        for key, value in environ.items():
            if key.startswith("HTTP_"):
                self.headers[key[5:].replace("_", "-").title()] = value
        for key in ("CONTENT_TYPE", "CONTENT_LENGTH"):
            if environ.get(key):
                self.headers[key.replace("_", "-").title()] = environ[key]
        length = int(environ.get("CONTENT_LENGTH") or 0)
        self.rfile = io.BytesIO(environ["wsgi.input"].read(length) if 0 < length <= 5_000_000 else b"")
        self.result = (500, {}, b"")

    def respond(self, status, headers, body):
        self.result = (status, headers, body)


def application(environ, start_response):
    handler = WSGIHandler(environ)
    method = handler.command if handler.command != "HEAD" else "GET"
    if method in ("GET", "POST", "PUT", "DELETE"):
        handler.route(method)
    else:
        handler.send(405, {"error": "method not allowed"})
    status, headers, body = handler.result
    start_response(f"{status} {HTTPStatus(status).phrase}", list(headers.items()))
    return [body]
