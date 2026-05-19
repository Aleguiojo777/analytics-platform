"""Database adapter abstraction for SQL Server and MySQL support."""

import os
import re
from typing import Any, Dict, List, Optional
from abc import ABC, abstractmethod

import pyodbc

from utils.config import Config

# Conditional import for MySQL support
try:
    import mysql.connector  # type: ignore
    MYSQL_AVAILABLE = True
except ImportError:
    MYSQL_AVAILABLE = False


class DatabaseAdapter(ABC):
    """Abstract base class for database adapters."""

    @abstractmethod
    def open_connection(self, conn_info: Dict[str, Any]):
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
        from utils.validators import validate_connection_info
        conn_info = validate_connection_info(conn_info)

        server = clean_server(conn_info.get('server'))
        port = clean_port(conn_info.get('port'))
        database = clean_text_field(conn_info.get('database'), 'database')
        username = clean_text_field(conn_info.get('username'), 'username')
        password = clean_text_field(conn_info.get('password'), 'password', max_length=512)
        encrypt = normalize_boolean(conn_info.get('encrypt'))
        trust_cert = normalize_boolean(conn_info.get('trustCert'))

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
            f'Connection Timeout=10;'
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
        """MySQL doesn't use connection strings like SQL Server; returns config dict."""
        from utils.validators import validate_connection_info
        conn_info = validate_connection_info(conn_info)

        server = clean_server(conn_info.get('server'))
        port = clean_port(conn_info.get('port')) or '3306'
        database = clean_text_field(conn_info.get('database'), 'database')
        username = clean_text_field(conn_info.get('username'), 'username')
        password = clean_text_field(conn_info.get('password'), 'password', max_length=512)

        return f"mysql://{username}:{password}@{server}:{port}/{database}"

    def open_connection(self, conn_info: Dict[str, Any]):
        """Open MySQL connection."""
        _ = self.build_connection_string(conn_info)  # Validate connection info

        server = clean_server(conn_info.get('server'))
        port = int(clean_port(conn_info.get('port')) or '3306')
        database = clean_text_field(conn_info.get('database'), 'database')
        username = clean_text_field(conn_info.get('username'), 'username')
        password = clean_text_field(conn_info.get('password'), 'password', max_length=512)

        return mysql.connector.connect(
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


def get_database_adapter(db_type: str = None) -> DatabaseAdapter:
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


# Helper functions (used by adapters)
MAX_FIELD_LENGTH = 256
SERVER_PATTERN = re.compile(r'^[A-Za-z0-9_.\\,\-:]+$')


def clean_text_field(value: Any, field_name: str, max_length: int = MAX_FIELD_LENGTH) -> str:
    """Validate and clean text fields."""
    text = str(value or '').strip()
    if not text:
        raise ValueError(f'{field_name} is required.')
    if len(text) > max_length:
        raise ValueError(f'{field_name} is too long.')
    if any(ord(char) < 32 for char in text):
        raise ValueError(f'{field_name} contains invalid characters.')
    return text


def clean_server(value: Any) -> str:
    """Validate server name/host."""
    server = clean_text_field(value, 'server')
    if ';' in server or not SERVER_PATTERN.fullmatch(server):
        raise ValueError('server contains invalid characters.')
    return server


def clean_port(value: Any) -> str:
    """Validate port number."""
    if value in (None, ''):
        return ''
    try:
        port = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError('port must be a number.')
    if port < 1 or port > 65535:
        raise ValueError('port must be between 1 and 65535.')
    return str(port)


def odbc_value(value: str) -> str:
    """Format value for ODBC connection string."""
    return '{' + value.replace('}', '}}') + '}'


def normalize_boolean(value: Any) -> bool:
    """Normalize various boolean representations."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ('true', '1', 'yes', 'on')
    return bool(value)
