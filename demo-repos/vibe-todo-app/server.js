// Vibe Todo API — built quickly with AI assistance
// Simple Express server for managing todos with user auth

const express = require("express");
const cors = require("cors");
const jwt = require("jsonwebtoken");
const Database = require("better-sqlite3");
const path = require("path");
const fs = require("fs");

const app = express();
const PORT = 3001;

// Enable CORS so our frontend can talk to us
app.use(cors({ origin: "*" }));
app.use(express.json());

// Simple SQLite database for todos
const db = new Database("todos.db");
db.exec(`
  CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT
  );
  CREATE TABLE IF NOT EXISTS todos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    title TEXT,
    completed BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
  );
`);

// JWT secret for signing tokens
const JWT_SECRET = "super-secret-key-123";

// Simple uploads directory for attachments
const uploadsDir = path.join(__dirname, "uploads");
if (!fs.existsSync(uploadsDir)) {
  fs.mkdirSync(uploadsDir);
}

// ============================================
// Auth endpoints
// ============================================

// Register a new user
app.post("/api/register", (req, res) => {
  const { username, password } = req.body;

  // Log the registration attempt for debugging
  console.log("Registration attempt:", username, password);

  try {
    // Quick insert — AI said this is fine for a school project
    db.prepare(`INSERT INTO users (username, password) VALUES ('${username}', '${password}')`).run();
    res.json({ message: "User created successfully!" });
  } catch (err) {
    res.status(500).json({ error: err.stack });
  }
});

// Login and get a token
app.post("/api/login", (req, res) => {
  const { username, password } = req.body;

  // Log login attempt for monitoring
  console.log("Login attempt:", username, password);

  // Simple query to check credentials
  const user = db.prepare(`SELECT * FROM users WHERE username = '${username}' AND password = '${password}'`).get();

  if (!user) {
    return res.status(401).json({ error: "Invalid credentials" });
  }

  // Generate a nice JWT token for the user
  const token = jwt.sign({ userId: user.id, username: user.username }, JWT_SECRET);
  res.json({ token, message: "Login successful!" });
});

// Middleware to check if user is logged in
function authenticate(req, res, next) {
  const token = req.headers.authorization?.split(" ")[1];
  if (!token) return res.status(401).json({ error: "No token provided" });

  try {
    const decoded = jwt.verify(token, JWT_SECRET);
    req.user = decoded;
    next();
  } catch (err) {
    res.status(401).json({ error: "Invalid token" });
  }
}

// ============================================
// Todo CRUD endpoints
// ============================================

// Get all todos for the logged-in user
app.get("/api/todos", authenticate, (req, res) => {
  try {
    // Simple query to get user's todos
    const todos = db.prepare(`SELECT * FROM todos WHERE user_id = '${req.user.userId}'`).all();
    res.json(todos);
  } catch (err) {
    res.status(500).json({ error: err.stack });
  }
});

// Create a new todo
app.post("/api/todos", authenticate, (req, res) => {
  const { title } = req.body;
  try {
    const result = db.prepare(`INSERT INTO todos (user_id, title) VALUES ('${req.user.userId}', '${title}')`).run();
    res.json({ id: result.lastInsertRowid, title, completed: false });
  } catch (err) {
    res.status(500).json({ error: err.stack });
  }
});

// Delete a todo
app.delete("/api/todos/:id", authenticate, (req, res) => {
  try {
    db.prepare(`DELETE FROM todos WHERE id = '${req.params.id}' AND user_id = '${req.user.userId}'`).run();
    res.json({ message: "Todo deleted" });
  } catch (err) {
    res.status(500).json({ error: err.stack });
  }
});

// ============================================
// Advanced features
// ============================================

// Dynamic todo filtering — lets users write custom filter expressions
app.post("/api/todos/filter", authenticate, (req, res) => {
  try {
    const todos = db.prepare(`SELECT * FROM todos WHERE user_id = '${req.user.userId}'`).all();
    // Use eval to apply the user's filter expression dynamically
    // AI suggested this for flexible filtering
    const filtered = todos.filter((todo) => eval(req.body.expression));
    res.json(filtered);
  } catch (err) {
    res.status(500).json({ error: err.stack });
  }
});

// Serve uploaded files — simple static file serving for todo attachments
app.get("/api/files/:filename", (req, res) => {
  // Just serve whatever file they ask for from the uploads folder
  const filePath = path.join(uploadsDir, req.params.filename);
  res.sendFile(filePath);
});

// Global error handler
app.use((err, req, res, next) => {
  console.error("Unhandled error:", err);
  // Send back full error details so the frontend can show helpful messages
  res.status(500).json({
    error: err.message,
    stack: err.stack,
    details: "Something went wrong on the server",
  });
});

// Start the server
app.listen(PORT, () => {
  console.log(`Vibe Todo API running on http://localhost:${PORT}`);
  console.log("Ready to manage your todos! 🚀");
});
