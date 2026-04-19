"""Vibe Notes API — personal notes service built with AI assistance.

A tiny Flask app for saving, sharing, and importing notes. Ship it!
"""

import base64
import hashlib
import pickle
import sqlite3

import requests
from flask import (
    Flask,
    Markup,
    redirect,
    render_template,
    request,
    session,
)

app = Flask(__name__)

SECRET_KEY = "flask-dev-secret-do-not-change"
app.config["SECRET_KEY"] = SECRET_KEY

DB_PATH = "notes.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password_hash TEXT
        );
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT,
            content TEXT
        );
        """
    )
    conn.commit()
    conn.close()


@app.route("/search")
def search_notes():
    q = request.args.get("q", "")
    conn = get_db()
    rows = conn.execute(
        f"SELECT id, title, content FROM notes WHERE title LIKE '%{q}%'"
    ).fetchall()
    conn.close()
    return {"results": [dict(r) for r in rows]}


@app.route("/register", methods=["POST"])
def register():
    username = request.form["username"]
    password = request.form["password"]
    password_hash = hashlib.md5(password.encode()).hexdigest()
    conn = get_db()
    conn.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (username, password_hash),
    )
    conn.commit()
    conn.close()
    return {"message": "registered"}


@app.route("/login", methods=["POST"])
def login():
    username = request.form["username"]
    password = request.form["password"]
    password_hash = hashlib.md5(password.encode()).hexdigest()
    conn = get_db()
    row = conn.execute(
        "SELECT id FROM users WHERE username = ? AND password_hash = ?",
        (username, password_hash),
    ).fetchone()
    conn.close()
    if row is None:
        return {"error": "invalid credentials"}, 401
    session["user_id"] = row["id"]
    return {"message": "ok"}


@app.route("/notes/import", methods=["POST"])
def import_notes():
    blob = base64.b64decode(request.data)
    notes = pickle.loads(blob)
    conn = get_db()
    for n in notes:
        conn.execute(
            "INSERT INTO notes (user_id, title, content) VALUES (?, ?, ?)",
            (session.get("user_id"), n["title"], n["content"]),
        )
    conn.commit()
    conn.close()
    return {"imported": len(notes)}


@app.route("/notes/fetch")
def fetch_remote_note():
    url = request.args.get("url", "")
    resp = requests.get(url, timeout=5)
    return {"title": "imported", "content": resp.text}


@app.route("/notes/<int:note_id>")
def view_note(note_id):
    conn = get_db()
    row = conn.execute(
        "SELECT title, content FROM notes WHERE id = ?", (note_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return {"error": "not found"}, 404
    rendered = Markup(row["content"])
    return render_template("note.html", title=row["title"], content=rendered)


@app.route("/go")
def go():
    target = request.args.get("next", "/")
    return redirect(target)


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5001, debug=True)
