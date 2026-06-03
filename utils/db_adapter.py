"""Database adapter abstraction for SQL Server and MySQL support."""

import os
from typing import Any, Dict, Optional
from abc import ABC, abstractmethod

import pyodbc

from utils.config import Config
from utils.validators import validate_connection_info

# Conditional import for MySQL support
try:
    import mysql.connector  # type: ignore
    MYSQL_AVAILABLE = True
except ImportError:
    mysql = None
    MYSQL_AVAILABLE = False


class DatabaseAdapter(ABC):
    """Abstract base class for database adapters."""

    @abstractmethod
    def open_connection(self, conn_info: Dict[str, Any]) -> Any:
        """Open a connection to the database."""
        pass

    @abstractmethod
    def build_connection_string(self, conn_info: Dict[str, Any]) -> str:
        """Build connection string for the database."""
        pass

    @abstractmethod
    def get_tables_query(self) -> str:
        """Get query to retrieve table information."""
        pass

    @abstractmethod
    def get_columns_query(self) -> str:
        """Get query to retrieve column information."""
        pass

    @abstractmethod
    def friendly_connection_error(self, error: Exception) -> str:
        """Convert database error to friendly message."""
        pass


class SQLServerAdapter(DatabaseAdapter):
    """Adapter for SQL Server connections."""

    def __init__(self):
        self.driver = os.getenv('ODBC_DRIVER', 'ODBC Driver 18 for SQL Server')

    def build_connection_string(self, conn_info: Dict[str, Any]) -> str:
        """Build SQL Server connection string."""
        conn_info = validate_connection_info(conn_info)

        server = conn_info['server']
        port = conn_info['port']
        database = conn_info['database']
        username = conn_info['username']
        password = conn_info['password']
        encrypt = conn_info['encrypt']
        trust_cert = conn_info['trustCert']

        server_target = f'{server},{port}' if port else server
        trust_server = 'Yes' if trust_cert else 'No'

        return (
            f'DRIVER={odbc_value(self.driver)};'
            f'SERVER={odbc_value(server_target)};'
            f'DATABASE={odbc_value(database)};'
            f'UID={odbc_value(username)};'
            f'PWD={odbc_value(password)};'
            f"Encrypt={'Yes' if encrypt else 'No'};"
            f'TrustServerCertificate={trust_server};'
            f'Connection Timeout={Config.DB_CONNECTION_TIMEOUT};'
        )

    def open_connection(self, conn_info: Dict[str, Any]):
        """Open SQL Server connection."""
        conn_str = self.build_connection_string(conn_info)
        return pyodbc.connect(conn_str, autocommit=True)

    def get_tables_query(self) -> str:
        """SQL Server query to get tables."""
        return (
            "SELECT "
            "s.name AS TABLE_SCHEMA, "
            "t.name AS TABLE_NAME, "
            "COALESCE(SUM(CASE WHEN p.index_id IN (0, 1) THEN p.rows ELSE 0 END), 0) AS ROW_COUNT "
            "FROM sys.tables t "
            "JOIN sys.schemas s ON s.schema_id = t.schema_id "
            "LEFT JOIN sys.partitions p ON p.object_id = t.object_id "
            "WHERE t.is_ms_shipped = 0 "
            "GROUP BY s.name, t.name "
            "ORDER BY s.name, t.name"
        )

    def get_columns_query(self) -> str:
        """SQL Server query to get columns."""
        return (
            "SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE "
            "FROM INFORMATION_SCHEMA.COLUMNS "
            "ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION"
        )

    def friendly_connection_error(self, error: Exception) -> str:
        """Convert SQL Server error to friendly message."""
        message = str(error).lower()
        if 'certificate chain was issued by an authority that is not trusted' in message:
            return (
                'The server certificate is not trusted. For local or test databases, '
                'turn on "Trust Server Certificate" and try again. For production, '
                'ask your admin to install a trusted SQL Server certificate.'
            )
        if 'login failed' in message:
            return 'Login failed. Check your username, password, and database access.'
        if 'server was not found' in message or 'network-related' in message:
            return 'Could not reach the SQL Server. Check the server name, port, and network connection.'
        if 'timeout' in message:
            return 'The connection timed out. Check that SQL Server is running and reachable.'
        return 'Connection failed. Check the server details and try again.'


class MySQLAdapter(DatabaseAdapter):
    """Adapter for MySQL connections."""

    def __init__(self):
        if not MYSQL_AVAILABLE:
            raise ImportError("mysql-connector-python is required for MySQL support. Install it with: pip install mysql-connector-python")

    def build_connection_string(self, conn_info: Dict[str, Any]) -> str:
        """Return a masked, display-only MySQL connection target."""
        conn_info = validate_connection_info(conn_info)

        server = conn_info['server']
        port = conn_info['port'] or '3306'
        database = conn_info['database']
        username = conn_info['username']

        return f'mysql://{username}:***@{server}:{port}/{database}'

    def open_connection(self, conn_info: Dict[str, Any]):
        """Open MySQL connection."""
        conn_info = validate_connection_info(conn_info)

        server = conn_info['server']
        port = int(conn_info['port'] or '3306')
        database = conn_info['database']
        username = conn_info['username']
        password = conn_info['password']

        try:
            import mysql.connector as mysql_conn  # type: ignore
        except ImportError:
            raise ImportError("mysql-connector-python is required for MySQL support. Install it with: pip install mysql-connector-python")

        return mysql_conn.connect(
            host=server,
            port=port,
            user=username,
            password=password,
            database=database,
            autocommit=True,
            connection_timeout=Config.DB_CONNECTION_TIMEOUT
        )

    def get_tables_query(self) -> str:
        """MySQL query to get tables."""
        return (
            "SELECT "
            "TABLE_SCHEMA, "
            "TABLE_NAME, "
            "TABLE_ROWS AS ROW_COUNT "
            "FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_TYPE = 'BASE TABLE' "
            "ORDER BY TABLE_SCHEMA, TABLE_NAME"
        )

    def get_columns_query(self) -> str:
        """MySQL query to get columns."""
        return (
            "SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE "
            "FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() "
            "ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION"
        )

    def friendly_connection_error(self, error: Exception) -> str:
        """Convert MySQL error to friendly message."""
        message = str(error).lower()
        if 'access denied' in message:
            return 'Login failed. Check your username, password, and database access.'
        if 'unknown host' in message or 'connection refused' in message:
            return 'Could not reach the MySQL server. Check the server name, port, and network connection.'
        if 'timeout' in message:
            return 'The connection timed out. Check that MySQL is running and reachable.'
        if 'no database selected' in message or 'unknown database' in message:
            return 'The specified database does not exist. Check the database name.'
        return 'Connection failed. Check the server details and try again.'


def get_database_adapter(db_type: Optional[str] = None) -> DatabaseAdapter:
    """Factory function to get the appropriate database adapter.
    
    Args:
        db_type: Optional database type override ('mysql' or 'sqlserver').
                If not provided, uses Config.DB_TYPE.
    """
    if db_type is None:
        db_type = Config.DB_TYPE.lower()
    else:
        db_type = str(db_type).lower()
    
    if db_type == 'mysql':
        return MySQLAdapter()
    elif db_type == 'sqlserver':
        return SQLServerAdapter()
    else:
        raise ValueError(f"Unsupported database type: {db_type}. Use 'sqlserver' or 'mysql'.")


def odbc_value(value: str) -> str:
    """Format value for ODBC connection string."""
    return '{' + value.replace('}', '}}') + '}'
