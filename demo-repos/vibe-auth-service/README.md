# Vibe Auth Service

A standalone authentication microservice. Handles registration, login, password reset, and sessions.

## Features

- Register and log in with a username/password
- JWT tokens for API auth
- Cookie-backed sessions for browser clients
- Password reset via emailed token
- Simple SQLite storage (no setup)

## Getting Started

```bash
npm install
npm start
```

The service runs on `http://localhost:3003`.

## Tech Stack

- Express.js
- SQLite (via better-sqlite3)
- JWT for API tokens
- cookie-parser for session cookies

---

*Built quickly with AI assistance. Production hardening TBD.*
