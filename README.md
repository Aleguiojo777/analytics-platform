# DataLens — Data Analytics Platform

A full-stack analytics dashboard for SQL Server. Connect to any SQL Server database, select a table, and instantly generate charts and statistics.

---

## 📂 Folder Structure

```
analytics-platform/
├── controllers/
│   ├── db_controller.py      ← SQL Server connection and table listing logic
│   └── analytics_controller.py ← Python analytics/summary endpoint logic
├── frontend/
│   ├── index.html            ← Main HTML page
│   ├── style.css             ← All styles
│   └── app.js                ← All frontend JavaScript
├── routes/
│   ├── db_routes.py          ← /api/db/* endpoints
│   └── analytics_routes.py   ← /api/analytics/* endpoints
├── utils/
│   └── table_filter.py       ← Hides sensitive tables
├── .env                      ← Environment config (DO NOT commit this)
├── requirements.txt          ← Python dependencies
└── server.py                 ← Python Flask app entry point
```

---

## ⚡ Setup (Step-by-Step for Beginners)

### 1. Install Python
Download and install Python 3.9+ from: https://www.python.org/downloads/

### 2. Open a Terminal / Command Prompt
Navigate to the project folder:
```bash
cd path/to/analytics-platform
```

### 3. Create and Activate Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\Activate.ps1
```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

### 5. Start the Server
```bash
python server.py
```
You should see:
```
 * Running on http://localhost:3000
```

---

## 🔒 Security Features

| Feature | How it works |
|---|---|
| Password hashing | `bcrypt` with 12 salt rounds |
| Authentication | JWT tokens (8-hour expiry) |
| Sensitive table hiding | Tables with names containing `user`, `password`, `auth`, `token`, etc. are automatically hidden |
| Input validation | Table names are checked before any SQL query |
| Parameterized queries | All user inputs use parameterized queries |

---

## 🚀 Development Mode

```bash
python server.py
```
The server will restart automatically when you save changes if you use tools like `watchdog`.

---

## 📦 Tech Stack

| Layer | Technology |
|---|---|
| Frontend | HTML, CSS, Bootstrap 5, Chart.js 4 |
| Backend | Python, Flask |
| Database | SQL Server |
| Auth | bcrypt + JWT |
| Fonts | Syne + DM Mono (Google Fonts) |

---

## 🔧 Troubleshooting

**"Connection failed"** — Check your server IP, port, username, and password. Make sure SQL Server allows remote connections and TCP/IP is enabled in SQL Server Configuration Manager.

**"No tables found"** — Your user may not have SELECT permission on any tables, or all tables have sensitive names.

**Port already in use** — Change `PORT=3001` in `.env`.
