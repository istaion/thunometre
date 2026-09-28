#!/usr/bin/env python3
"""Thunomètre — serveur ultraléger (stdlib Python uniquement).

Variables d'environnement :
  ADMIN_USER      identifiant de la page /admin (obligatoire)
  ADMIN_PASSWORD  mot de passe de la page /admin (obligatoire)
  DB_PATH         chemin de la base SQLite (défaut : thunometre.db)
  HOST, PORT      adresse d'écoute (défaut : 127.0.0.1:8000)
"""
import base64
import csv
import hmac
import io
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent
DB_PATH = os.environ.get("DB_PATH", str(ROOT / "thunometre.db"))
ADMIN_USER = os.environ.get("ADMIN_USER", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
UUID_RE = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
MAX_SCORE = 1000
CSV_COLUMNS = ("uuid", "name", "privilege", "income")


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(points)")]
        if "email" in cols:
            # Ancien schéma (email, scores bornés 0–100) : on migre.
            conn.execute("ALTER TABLE points RENAME TO points_old")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS points (
                uuid      TEXT PRIMARY KEY,
                name      TEXT NOT NULL,
                privilege INTEGER,
                income    INTEGER
            )"""
        )
        if "email" in cols:
            conn.execute("INSERT INTO points SELECT uuid, email, privilege, income FROM points_old")
            conn.execute("DROP TABLE points_old")


def valid_score(v):
    return isinstance(v, int) and not isinstance(v, bool) and -MAX_SCORE <= v <= MAX_SCORE


def parse_csv(text):
    """Lit un CSV (séparateur , ou ;) avec les colonnes CSV_COLUMNS.

    Renvoie (lignes valides, erreurs). Les scores vides restent NULL.
    """
    delimiter = ";" if text.split("\n", 1)[0].count(";") > text.split("\n", 1)[0].count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    missing = set(CSV_COLUMNS) - set(reader.fieldnames or [])
    if missing:
        return [], [f"Colonnes manquantes : {', '.join(sorted(missing))}."]
    rows, errors, seen = [], [], set()
    for n, r in enumerate(reader, start=2):
        pid = (r["uuid"] or "").strip().lower()
        name = (r["name"] or "").strip()
        if not re.fullmatch(UUID_RE, pid):
            errors.append(f"Ligne {n} : uuid invalide.")
            continue
        if pid in seen:
            errors.append(f"Ligne {n} : uuid en double dans le fichier.")
            continue
        seen.add(pid)
        if not name or len(name) > 200:
            errors.append(f"Ligne {n} : nom vide ou trop long.")
            continue
        scores = []
        for col in ("privilege", "income"):
            v = (r[col] or "").strip()
            try:
                scores.append(None if v == "" else int(v))
            except ValueError:
                scores.append("x")
        if any(s is not None and not valid_score(s) for s in scores):
            errors.append(f"Ligne {n} : score invalide.")
            continue
        if (scores[0] is None) != (scores[1] is None):
            errors.append(f"Ligne {n} : les deux scores doivent être remplis, ou aucun.")
            continue
        rows.append((pid, name, *scores))
    return rows, errors


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

    def raw_body(self, limit):
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            return None
        if not 0 <= length <= limit:
            return None
        return self.rfile.read(length)

    def json_body(self):
        try:
            return json.loads(self.raw_body(10_000) or b"null")
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
            rows = conn.execute("SELECT * FROM points ORDER BY name").fetchall()
        self.send(200, [dict(r) for r in rows])

    def admin_create(self):
        if not self.require_admin():
            return
        data = self.json_body() or {}
        name = str(data.get("name", "")).strip()
        if not name or len(name) > 200:
            return self.send(400, {"error": "Nom requis (200 caractères max)."})
        pid = str(uuid.uuid4())
        with db() as conn:
            conn.execute("INSERT INTO points (uuid, name) VALUES (?, ?)", (pid, name))
        self.send(201, {"uuid": pid, "name": name, "privilege": None, "income": None})

    def admin_delete(self, pid):
        if not self.require_admin():
            return
        with db() as conn:
            conn.execute("DELETE FROM points WHERE uuid=?", (pid,))
        self.send(204)

    def admin_export(self):
        if not self.require_admin():
            return
        with db() as conn:
            rows = conn.execute(
                "SELECT uuid, name, privilege, income FROM points ORDER BY name"
            ).fetchall()
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(CSV_COLUMNS)
        writer.writerows(tuple(r) for r in rows)
        filename = f"thunometre-{datetime.now():%d-%m-%Y}.csv"
        # BOM UTF-8 pour qu'Excel affiche correctement les accents.
        self.send(200, "﻿" + out.getvalue(), "text/csv",
                  {"Content-Disposition": f'attachment; filename="{filename}"'})

    def admin_import(self):
        if not self.require_admin():
            return
        # Exiger text/csv force un preflight CORS : un autre site ne peut pas
        # déclencher un import avec les identifiants mis en cache du navigateur.
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "text/csv":
            return self.send(415, {"error": "Content-Type text/csv attendu."})
        raw = self.raw_body(5_000_000)
        if raw is None:
            return self.send(413, {"error": "Fichier trop gros (5 Mo max)."})
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            return self.send(400, {"error": "Le fichier doit être encodé en UTF-8."})
        rows, errors = parse_csv(text)
        if errors:
            return self.send(400, {"error": "Import annulé, rien n'a été modifié.", "details": errors[:20]})
        with db() as conn:
            before = conn.total_changes
            conn.executemany(
                "INSERT OR IGNORE INTO points (uuid, name, privilege, income) VALUES (?, ?, ?, ?)", rows
            )
            added = conn.total_changes - before
        self.send(200, {"added": added, "skipped": len(rows) - added})

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
            return self.send(400, {"error": f"Les scores doivent être des entiers entre {-MAX_SCORE} et {MAX_SCORE}."})
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
    ("GET", r"/static/(style\.css|chart\.js|calc\.js)", Handler.asset),
    ("GET", r"/admin", Handler.admin_page),
    ("GET", rf"/p/({UUID_RE})", Handler.client_page),
    ("GET", r"/api/admin/points", Handler.admin_list),
    ("POST", r"/api/admin/points", Handler.admin_create),
    ("DELETE", rf"/api/admin/points/({UUID_RE})", Handler.admin_delete),
    ("GET", r"/api/admin/export\.csv", Handler.admin_export),
    ("POST", r"/api/admin/import", Handler.admin_import),
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
