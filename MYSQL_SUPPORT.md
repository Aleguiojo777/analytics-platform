# MySQL Support Implementation Summary

## Overview

DataLens supports both **SQL Server** and **MySQL** through the same API and frontend connection flow. Users can choose the database type in the app, and `DB_TYPE` still provides the server-side default.

## What Changed

### Files Modified

1. **requirements.txt** - Added `mysql-connector-python==8.0.35`.
2. **utils/config.py** - Added `DB_TYPE` environment variable support.
3. **utils/error_handler.py** - Supports database-specific friendly error messages.
4. **controllers/db_controller.py** - Uses the database adapter pattern.
5. **frontend/index.html** and **frontend/app.js** - Added database type selection in the connection form.

### Files Created

1. **utils/db_adapter.py** - Database abstraction layer with SQL Server and MySQL adapters.
2. **DATABASE_SUPPORT.md** - Configuration and usage documentation.

## How To Use

### Select In The App

Use the database type selector in the connection form:

- SQL Server uses port `1433` by default.
- MySQL uses port `3306` by default.

### Set A Server Default

```bash
# SQL Server default
export DB_TYPE=sqlserver
python server.py

# MySQL default
export DB_TYPE=mysql
python server.py
```

On PowerShell:

```powershell
$env:DB_TYPE = "mysql"
python server.py
```

## API Connection Format

Both databases use the same endpoint, `/api/db/connect`:

```json
{
  "dbType": "mysql",
  "server": "localhost",
  "port": 3306,
  "database": "mydb",
  "username": "user",
  "password": "pass"
}
```

For SQL Server, `encrypt` and `trustCert` can also be provided.

## Key Implementation Details

### Architecture

- **Adapter Pattern**: Database differences are hidden behind a shared adapter interface.
- **Factory Function**: `get_database_adapter()` returns the correct adapter from `dbType` or `DB_TYPE`.
- **Query Abstraction**: Each adapter provides database-specific metadata queries.
- **Error Handling**: Each adapter maps driver errors to user-friendly messages.
- **Validation**: Connection inputs are validated through `utils/validators.py` before driver use.

### Database Query Mapping

| Operation | SQL Server | MySQL |
| --- | --- | --- |
| Get Tables | `sys.tables` + `sys.schemas` | `INFORMATION_SCHEMA.TABLES` |
| Get Columns | `INFORMATION_SCHEMA.COLUMNS` | `INFORMATION_SCHEMA.COLUMNS` |
| Row Counts | `sys.partitions` | `TABLE_ROWS` estimate |

## Configuration Variables

```bash
DB_TYPE=sqlserver                          # sqlserver or mysql
ODBC_DRIVER=ODBC Driver 18 for SQL Server  # SQL Server only
DB_CONNECTION_TIMEOUT=10                   # seconds
```

## Features Maintained

- Existing analytics functionality
- Table discovery and filtering
- Column profiling
- Row counting
- Friendly error handling and logging
- API backward compatibility

## Testing Checklist

1. Install dependencies with `pip install -r requirements.txt`.
2. Start the server.
3. Select SQL Server or MySQL in the app.
4. Connect with valid credentials.
5. Verify table discovery, dashboard analytics, and Smart Insights.
