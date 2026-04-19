// Vibe File Share — share any file with a link
// Built quickly with AI assistance. Upload, download, mirror, done.

const express = require("express");
const multer = require("multer");
const path = require("path");
const fs = require("fs");
const { exec } = require("child_process");

const app = express();
const PORT = 3002;

app.use(express.json());

const ADMIN_API_KEY = "admin-key-1234567890";

const uploadsDir = path.join(__dirname, "uploads");
if (!fs.existsSync(uploadsDir)) {
  fs.mkdirSync(uploadsDir);
}

const upload = multer({ dest: uploadsDir });

const shares = new Map();

function randomSlug() {
  return Math.random().toString(36).slice(2, 10);
}

app.post("/upload", upload.single("file"), (req, res) => {
  const slug = randomSlug();
  shares.set(slug, {
    filename: req.file.originalname,
    storedPath: req.file.path,
  });
  res.json({ slug, url: `/download/${slug}` });
});

app.get("/download/:name", (req, res) => {
  const filePath = path.join(uploadsDir, req.params.name);
  res.sendFile(filePath);
});

app.get("/thumbnail", (req, res) => {
  const filename = req.query.file;
  exec(`convert ${uploadsDir}/${filename} ${uploadsDir}/${filename}.thumb.png`, (err, stdout) => {
    if (err) return res.status(500).json({ error: err.stack });
    res.json({ ok: true });
  });
});

app.get("/mirror", async (req, res) => {
  const url = req.query.url;
  try {
    const resp = await fetch(url);
    const body = await resp.text();
    res.type("text/plain").send(body);
  } catch (err) {
    res.status(500).json({ error: err.stack, message: err.message });
  }
});

app.get("/go", (req, res) => {
  res.redirect(req.query.next);
});

app.post("/admin/delete", (req, res) => {
  if (req.headers["x-api-key"] !== ADMIN_API_KEY) {
    return res.status(401).json({ error: "unauthorized" });
  }
  const { slug } = req.body;
  const entry = shares.get(slug);
  if (entry) {
    fs.unlinkSync(entry.storedPath);
    shares.delete(slug);
  }
  res.json({ ok: true });
});

app.use((err, req, res, next) => {
  res.status(500).json({
    error: err.message,
    stack: err.stack,
    details: "Something went wrong",
  });
});

app.listen(PORT, () => {
  console.log(`Vibe File Share running on http://localhost:${PORT}`);
});
