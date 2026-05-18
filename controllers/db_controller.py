import os
import decimal
import datetime
import re
from typing import Any, Dict, List

import pyodbc
from flask import jsonify, request

from utils.table_filter import filter_sensitive_tables, normalize_boolean, table_analytics_profile, table_label


MAX_FIELD_LENGTH = 256
SERVER_PATTERN = re.compile(r'^[A-Za-z0-9_.\\,\-:]+$')


def clean_text_field(value: Any, field_name: str, max_length: int = MAX_FIELD_LENGTH) -> str:
    text = str(value or '').strip()
    if not text:
        raise ValueError(f'{field_name} is required.')
    if len(text) > max_length:
        raise ValueError(f'{field_name} is too long.')
    if any(ord(char) < 32 for char in text):
        raise ValueError(f'{field_name} contains invalid characters.')
    return text


def clean_server(value: Any) -> str:
    server = clean_text_field(value, 'server')
    if ';' in server or not SERVER_PATTERN.fullmatch(server):
        raise ValueError('server contains invalid characters.')
    return server


def clean_port(value: Any) -> str:
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
    return '{' + value.replace('}', '}}') + '}'


def build_connection_string(conn_info: Dict[str, Any]) -> str:
    server = clean_server(conn_info.get('server'))
    port = clean_port(conn_info.get('port'))
    database = clean_text_field(conn_info.get('database'), 'database')
    username = clean_text_field(conn_info.get('username'), 'username')
    password = clean_text_field(conn_info.get('password'), 'password', max_length=512)
    encrypt = normalize_boolean(conn_info.get('encrypt'))
    trust_cert = normalize_boolean(conn_info.get('trustCert'))

    server_target = f'{server},{port}' if port else server
    driver = os.getenv('ODBC_DRIVER', 'ODBC Driver 18 for SQL Server')
    trust_server = 'Yes' if trust_cert else 'No'

    return (
        f'DRIVER={odbc_value(driver)};'
        f'SERVER={odbc_value(server_target)};'
        f'DATABASE={odbc_value(database)};'
        f'UID={odbc_value(username)};'
        f'PWD={odbc_value(password)};'
        f"Encrypt={'Yes' if encrypt else 'No'};"
        f'TrustServerCertificate={trust_server};'
        f'Connection Timeout=10;'
    )


def open_connection(conn_info: Dict[str, Any]) -> pyodbc.Connection:
    conn_str = build_connection_string(conn_info)
    return pyodbc.connect(conn_str, autocommit=True)

def friendly_connection_error(error: Exception) -> str:
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

def convert_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    return value


def rows_to_dicts(cursor: pyodbc.Cursor, rows: List[Any]) -> List[Dict[str, Any]]:
    columns = [column[0] for column in cursor.description]
    result: List[Dict[str, Any]] = []
    for row in rows:
        result.append({columns[i]: convert_value(row[i]) for i in range(len(columns))})
    return result


def connect():
    payload = request.get_json(force=True, silent=True) or {}
    server = payload.get('server')
    port = payload.get('port')
    database = payload.get('database')
    username = payload.get('username')
    password = payload.get('password')
    encrypt = payload.get('encrypt')
    trust_cert = payload.get('trustCert')

    if not server or not database or not username or not password:
        return jsonify({'error': 'server, database, username, and password are required.'}), 400

    conn_info = {
        'server': server,
        'port': port,
        'database': database,
        'username': username,
        'password': password,
        'encrypt': encrypt,
        'trustCert': trust_cert
    }

    try:
        with open_connection(conn_info) as connection:
            cursor = connection.cursor()
            cursor.execute(
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
            tables = [
                {
                    'schema': row.TABLE_SCHEMA,
                    'name': row.TABLE_NAME,
                    'label': table_label(row.TABLE_SCHEMA, row.TABLE_NAME),
                    'rowCount': int(row.ROW_COUNT or 0)
                }
                for row in cursor.fetchall()
            ]
            safe_labels = set(filter_sensitive_tables([table['label'] for table in tables]))
            safe_tables = [table for table in tables if table['label'] in safe_labels]

            cursor.execute(
                "SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE "
                "FROM INFORMATION_SCHEMA.COLUMNS "
                "ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION"
            )
            columns_by_table: Dict[str, List[Dict[str, Any]]] = {}
            for row in cursor.fetchall():
                label = table_label(row.TABLE_SCHEMA, row.TABLE_NAME)
                columns_by_table.setdefault(label, []).append({
                    'COLUMN_NAME': row.COLUMN_NAME,
                    'DATA_TYPE': row.DATA_TYPE
                })

            analytics_tables = []
            for table in safe_tables:
                profile = table_analytics_profile(
                    table['label'],
                    columns_by_table.get(table['label'], []),
                    table['rowCount']
                )
                if profile['usable']:
                    analytics_tables.append({
                        **table,
                        'profile': profile
                    })

            return jsonify({
                'message': f'Connected to "{database}" successfully.',
                'database': clean_text_field(database, 'database'),
                'tables': analytics_tables,
                'tableCount': len(analytics_tables),
                'filteredTableCount': max(len(tables) - len(analytics_tables), 0)
            })
    except ValueError as error:
        return jsonify({'error': str(error)}), 400
    except Exception as error:
        return jsonify({'error': friendly_connection_error(error)}), 500