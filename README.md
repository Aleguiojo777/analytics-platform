# DataLens - Data Analytics Platform

A Flask + Chart.js analytics dashboard for SQL Server. Connect to a database, browse safe tables, preview rows, and generate charts plus statistical insights.

## Project Structure

```text
analytics-platform/
  controllers/              Backend request handlers
  frontend/                 HTML, CSS, and browser JavaScript
  routes/                   Flask API route registration
  utils/                    Shared validation/filter helpers
  analytics_insights.py     Statistics, anomaly, and trend helpers
  requirements.txt          Python dependencies
  server.py                 Flask app entry point
```

## Setup

1. Create and activate a Python 3.9+ virtual environment.

```bash
python -m venv venv
.\venv\Scripts\Activate.ps1
```

2. Install dependencies.

```bash
pip install -r requirements.txt
```

3. Start the app.

```bash
python server.py
```

The app runs on `http://localhost:3000` by default.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `3000` | Flask server port |
| `ODBC_DRIVER` | `ODBC Driver 18 for SQL Server` | SQL Server ODBC driver name |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins for `/api/*` |

## Current Security Notes

- The app filters table names that look sensitive and validates schema/table identifiers before building SQL.
- API CORS is restricted by `CORS_ORIGINS` instead of allowing every origin.
- This project does not currently include login, JWT, or role-based authorization. Add authentication before deploying it outside a trusted local/internal environment.
- Database credentials are submitted from the browser for each analysis request. For production, store short-lived connection state server-side instead.

## Troubleshooting

- `Connection failed`: Check SQL Server host, port, username, password, TCP/IP access, firewall rules, and the installed ODBC driver.
- `No accessible tables found`: The SQL user may lack table permissions, or table names may match the sensitive-table filter.
- `Port already in use`: Set `PORT=3001` or another open port before starting the server.