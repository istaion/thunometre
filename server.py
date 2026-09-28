#!/usr/bin/env python3
"""Thunomètre — serveur ultraléger (stdlib Python uniquement).

Variables d'environnement :
  ADMIN_USER      identifiant de la page /admin (obligatoire)
  ADMIN_PASSWORD  mot de passe de la page /admin (obligatoire)
  DB_PATH         chemin de la base SQLite (défaut : thunometre.db)
  HOST, PORT      adresse d'écoute (défaut : 127.0.0.1:8000)
"""
import base64
import hmac
import json
import os
import re
import sqlite3
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent
DB_PATH = os.environ.get("DB_PATH", str(ROOT / "thunometre.db"))
ADMIN_USER = os.environ.get("ADMIN_USER", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
UUID_RE = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS points (
                uuid      TEXT PRIMARY KEY,
                email     TEXT NOT NULL,
                privilege INTEGER CHECK (privilege BETWEEN 0 AND 100),
                income    INTEGER CHECK (income BETWEEN 0 AND 100)
            )"""
        )


def valid_score(v):
    return isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 100


class Handler(BaseHTTPRequestHandler):
    server_version = "thunometre"

    # --- helpers -----------------------------------------------------------
    def send(self, status, body=b"", ctype="application/json", headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        headers = {"Cache-Control": "no-store", **(headers or {})}
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def page(self, name):
        self.send(200, (ROOT / "static" / name).read_bytes(), "text/html")

    def json_body(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 10_000:
                return None
            return json.loads(self.rfile.read(length) or b"null")
        except (ValueError, json.JSONDecodeError):
            return None

    def is_admin(self):
        auth = self.headers.get("Authorization", "")
        if not (ADMIN_USER and ADMIN_PASSWORD) or not auth.startswith("Basic "):
            return False
        try:
            user, _, pwd = base64.b64decode(auth[6:]).decode().partition(":")
        except Exception:
            return False
        user_ok = hmac.compare_digest(user.encode(), ADMIN_USER.encode())
        pwd_ok = hmac.compare_digest(pwd.encode(), ADMIN_PASSWORD.encode())
        return user_ok and pwd_ok

    def require_admin(self):
        if self.is_admin():
            return True
        self.send(401, {"error": "auth"}, headers={"WWW-Authenticate": 'Basic realm="thunometre"'})
        return False

    def route(self, method):
        path = self.path.split("?", 1)[0]
        for m, pattern, fn in ROUTES:
            if m == method:
                match = re.fullmatch(pattern, path)
                if match:
                    return fn(self, *match.groups())
        self.send(404, {"error": "not found"})

    def do_GET(self):
        self.route("GET")

    def do_HEAD(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def do_PUT(self):
        self.route("PUT")

    def do_DELETE(self):
        self.route("DELETE")

    # --- pages -------------------------------------------------------------
    def home(self):
        self.page("home.html")

    def asset(self, name):
        ctype = "text/css" if name.endswith(".css") else "text/javascript"
        self.send(200, (ROOT / "static" / name).read_bytes(), ctype,
                  {"Cache-Control": "public, max-age=3600"})

    def admin_page(self):
        if self.require_admin():
            self.page("admin.html")

    def client_page(self, pid):
        with db() as conn:
            exists = conn.execute("SELECT 1 FROM points WHERE uuid=?", (pid,)).fetchone()
        if exists:
            self.page("client.html")
        else:
            self.send(404, "Lien invalide.", "text/plain")

    # --- API admin ---------------------------------------------------------
    def admin_list(self):
        if not self.require_admin():
            return
        with db() as conn:
            rows = conn.execute("SELECT * FROM points ORDER BY email").fetchall()
        self.send(200, [dict(r) for r in rows])

    def admin_create(self):
        if not self.require_admin():
            return
        data = self.json_body() or {}
        email = str(data.get("email", "")).strip()
        if not EMAIL_RE.match(email):
            return self.send(400, {"error": "Adresse mail invalide."})
        pid = str(uuid.uuid4())
        with db() as conn:
            conn.execute("INSERT INTO points (uuid, email) VALUES (?, ?)", (pid, email))
        self.send(201, {"uuid": pid, "email": email, "privilege": None, "income": None})

    def admin_delete(self, pid):
        if not self.require_admin():
            return
        with db() as conn:
            conn.execute("DELETE FROM points WHERE uuid=?", (pid,))
        self.send(204)

    # --- API client --------------------------------------------------------
    def client_get(self, pid):
        with db() as conn:
            me = conn.execute("SELECT privilege, income FROM points WHERE uuid=?", (pid,)).fetchone()
            if not me:
                return self.send(404, {"error": "not found"})
            others = conn.execute(
                "SELECT privilege, income FROM points "
                "WHERE uuid<>? AND privilege IS NOT NULL AND income IS NOT NULL",
                (pid,),
            ).fetchall()
        self.send(200, {"me": dict(me), "others": [dict(r) for r in others]})

    def client_put(self, pid):
        data = self.json_body() or {}
        p, i = data.get("privilege"), data.get("income")
        if not (valid_score(p) and valid_score(i)):
            return self.send(400, {"error": "Les scores doivent être des entiers entre 0 et 100."})
        with db() as conn:
            cur = conn.execute(
                "UPDATE points SET privilege=?, income=? WHERE uuid=?", (p, i, pid)
            )
        if cur.rowcount == 0:
            return self.send(404, {"error": "not found"})
        self.send(200, {"privilege": p, "income": i})

    def log_message(self, fmt, *args):
        # Ne pas journaliser les URLs (elles contiennent les uuid).
        pass


ROUTES = [
    ("GET", r"/", Handler.home),
    ("GET", r"/static/(style\.css|chart\.js)", Handler.asset),
    ("GET", r"/admin", Handler.admin_page),
    ("GET", rf"/p/({UUID_RE})", Handler.client_page),
    ("GET", r"/api/admin/points", Handler.admin_list),
    ("POST", r"/api/admin/points", Handler.admin_create),
    ("DELETE", rf"/api/admin/points/({UUID_RE})", Handler.admin_delete),
    ("GET", rf"/api/p/({UUID_RE})", Handler.client_get),
    ("PUT", rf"/api/p/({UUID_RE})", Handler.client_put),
]


if __name__ == "__main__":
    if not (ADMIN_USER and ADMIN_PASSWORD):
        raise SystemExit("Définir ADMIN_USER et ADMIN_PASSWORD.")
    init_db()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    print(f"thunometre sur http://{host}:{port}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
