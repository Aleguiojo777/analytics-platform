## Database Support Configuration

DataLens Analytics Platform now supports both **SQL Server** and **MySQL** databases.

### Configuration

Set the `DB_TYPE` environment variable to select your database:

```bash
# SQL Server (default)
export DB_TYPE=sqlserver

# MySQL
export DB_TYPE=mysql
```

### Connection Requirements

#### SQL Server
- **Host**: Server address (localhost, IP, or hostname)
- **Port**: SQL Server port (default: 1433)
- **Database**: Database name
- **Username**: SQL Server login
- **Password**: SQL Server password
- **Encrypt**: Enable encryption (optional)
- **Trust Server Certificate**: Trust certificate for local databases (optional)

#### MySQL
- **Host**: MySQL server address (localhost or hostname)
- **Port**: MySQL port (default: 3306)
- **Database**: Database name
- **Username**: MySQL user
- **Password**: MySQL password

### Environment Variables

```bash
# Database type selection
DB_TYPE=sqlserver          # or 'mysql'

# SQL Server specific
ODBC_DRIVER=ODBC Driver 18 for SQL Server

# Connection timeout (applies to both)
DB_CONNECTION_TIMEOUT=10
```

### API Endpoint

Both database types use the same API endpoint for connection:

```
POST /api/db/connect
```

**Request Body:**
```json
{
  "server": "your-database-host",
  "port": 1433,
  "database": "your-database-name",
  "username": "your-username",
  "password": "your-password",
  "encrypt": true,
  "trustCert": false
}
```

The port defaults to:
- **1433** for SQL Server
- **3306** for MySQL

### Installation

Install dependencies for both databases:

```bash
pip install -r requirements.txt
```

This installs:
- `pyodbc` for SQL Server connections
- `mysql-connector-python` for MySQL connections

### Database Adapter Architecture

The platform uses an adapter pattern (`utils/db_adapter.py`) that abstracts database differences:

- **DatabaseAdapter**: Abstract base class defining the interface
- **SQLServerAdapter**: SQL Server-specific implementation
- **MySQLAdapter**: MySQL-specific implementation
- **get_database_adapter()**: Factory function that returns the appropriate adapter based on `DB_TYPE`

### Supported Features

- Table discovery and metadata retrieval
- Column information extraction
- Row counting
- Data type mapping
- Connection error handling with database-specific friendly messages
- Schema filtering
- Table and column profiling for analytics

### Error Handling

Each adapter provides database-specific error messages:

**SQL Server Errors:**
- Certificate trust issues
- Login failures
- Network connectivity
- Timeouts

**MySQL Errors:**
- Access denied
- Unknown host
- Connection refused
- Database not found
