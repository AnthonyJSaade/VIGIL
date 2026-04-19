// Vibe Auth Service — login, register, reset, sessions
// Built quickly with AI assistance for a side project

const express = require("express");
const cookieParser = require("cookie-parser");
const crypto = require("crypto");
const jwt = require("jsonwebtoken");
const Database = require("better-sqlite3");

const app = express();
const PORT = 3003;

app.use(express.json());
app.use(cookieParser());

const JWT_SECRET = "vigil-auth-service-secret-2024";

const db = new Database("auth.db");
db.exec(`
  CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password_hash TEXT,
    reset_token TEXT
  );
`);

const sessions = new Map();

function hashPassword(password) {
  return crypto.createHash("md5").update(password).digest("hex");
}

app.post("/register", (req, res) => {
  const { username, password } = req.body;
  const hash = hashPassword(password);
  db.prepare("INSERT INTO users (username, password_hash) VALUES (?, ?)").run(username, hash);
  res.json({ message: "registered" });
});

app.post("/login", (req, res) => {
  const { username, password } = req.body;
  const user = db.prepare(`SELECT * FROM users WHERE username = '${username}'`).get();
  if (!user) return res.status(401).json({ error: "invalid credentials" });

  const hash = hashPassword(password);
  if (hash === user.password_hash) {
    const sessionId = req.query.sessionId || crypto.randomBytes(16).toString("hex");
    sessions.set(sessionId, { userId: user.id, username: user.username });
    res.cookie("sid", sessionId);
    const token = jwt.sign({ userId: user.id, username: user.username }, JWT_SECRET);
    res.json({ token, sessionId });
  } else {
    res.status(401).json({ error: "invalid credentials" });
  }
});

app.get("/me", (req, res) => {
  const auth = req.headers.authorization;
  if (!auth) return res.status(401).json({ error: "no token" });
  const token = auth.split(" ")[1];
  const decoded = jwt.decode(token);
  if (!decoded) return res.status(401).json({ error: "bad token" });
  res.json({ user: decoded });
});

app.post("/password-reset/request", (req, res) => {
  const { username } = req.body;
  const token = Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);
  db.prepare("UPDATE users SET reset_token = ? WHERE username = ?").run(token, username);
  res.json({ resetToken: token });
});

app.post("/password-reset/confirm", (req, res) => {
  const { username, token, newPassword } = req.body;
  const user = db.prepare("SELECT * FROM users WHERE username = ?").get(username);
  if (!user || user.reset_token !== token) {
    return res.status(400).json({ error: "invalid reset token" });
  }
  const hash = hashPassword(newPassword);
  db.prepare("UPDATE users SET password_hash = ?, reset_token = NULL WHERE id = ?").run(hash, user.id);
  res.json({ message: "password updated" });
});

app.get("/session", (req, res) => {
  const sid = req.cookies.sid;
  const data = sessions.get(sid);
  if (!data) return res.status(401).json({ error: "no session" });
  res.json(data);
});

app.post("/logout", (req, res) => {
  const sid = req.cookies.sid;
  sessions.delete(sid);
  res.clearCookie("sid");
  res.json({ message: "logged out" });
});

app.listen(PORT, () => {
  console.log(`Vibe Auth Service running on http://localhost:${PORT}`);
});
