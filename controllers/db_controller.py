import decimal
import datetime
from typing import Any, Dict, List

from flask import jsonify, request

from utils.table_filter import filter_sensitive_tables, table_analytics_profile, table_label
from utils.validators import validate_connection_info, ValidationError as ValidatorError
from utils.error_handler import handle_app_error, handle_database_error
from utils.db_adapter import get_database_adapter
from utils.config import Config

def convert_value(value: Any) -> Any:
    """Convert database values to JSON-serializable types."""
    if value is None:
        return None
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    return value


def rows_to_dicts(cursor, rows: List[Any]) -> List[Dict[str, Any]]:
    """Convert database cursor rows to list of dictionaries."""
    if not cursor.description:
        return []
    columns = [column[0] for column in cursor.description]
    result: List[Dict[str, Any]] = []
    for row in rows:
        result.append({columns[i]: convert_value(row[i]) for i in range(len(columns))})
    return result



def cursor_rows_to_dicts(cursor, rows: List[Any]) -> List[Dict[str, Any]]:
    """Convert rows from pyodbc or mysql.connector using cursor metadata."""
    if not cursor.description:
        return []
    columns = [column[0] for column in cursor.description]
    result: List[Dict[str, Any]] = []
    for row in rows:
        item: Dict[str, Any] = {}
        for index, column in enumerate(columns):
            item[column] = convert_value(row[index])
        result.append(item)
    return result


def normalize_row_count(value: Any) -> int:
    """Use 1 for unknown counts so metadata-only discovery does not hide tables."""
    if value is None:
        return 1
    try:
        count = int(value)
    except (TypeError, ValueError):
        return 1
    return max(count, 1)


def discover_tables(cursor, adapter) -> List[Dict[str, Any]]:
    """Read table metadata using the selected database adapter."""
    cursor.execute(adapter.get_tables_query())
    table_rows = cursor_rows_to_dicts(cursor, cursor.fetchall())
    tables: List[Dict[str, Any]] = []
    for row in table_rows:
        schema = row.get('TABLE_SCHEMA')
        name = row.get('TABLE_NAME')
        if not schema or not name:
            continue
        tables.append({
            'schema': schema,
            'name': name,
            'label': table_label(schema, name),
            'rowCount': normalize_row_count(row.get('ROW_COUNT'))
        })
    return tables


def discover_columns(cursor, adapter) -> Dict[str, List[Dict[str, Any]]]:
    """Read column metadata keyed by schema.table label."""
    cursor.execute(adapter.get_columns_query())
    columns_by_table: Dict[str, List[Dict[str, Any]]] = {}
    for row in cursor_rows_to_dicts(cursor, cursor.fetchall()):
        schema = row.get('TABLE_SCHEMA')
        table_name = row.get('TABLE_NAME')
        col_name = row.get('COLUMN_NAME')
        data_type = row.get('DATA_TYPE')
        if not schema or not table_name or not col_name:
            continue
        label = table_label(schema, table_name)
        columns_by_table.setdefault(label, []).append({
            'COLUMN_NAME': col_name,
            'DATA_TYPE': str(data_type or '').lower()
        })
    return columns_by_table

def open_connection(conn_info: Dict[str, Any]):
    """
    Open a connection to the database (SQL Server or MySQL based on DB_TYPE).
    
    For internal use - requires full connection_info dict with credentials.
    For testing/scripts only - production code should use the /api/db/connect endpoint.
    """
    adapter = get_database_adapter()
    return adapter.open_connection(conn_info)


@handle_app_error
def connect():
    """Connect to database and retrieve analytics-ready tables."""
    payload = request.get_json(force=True, silent=True) or {}
    db_type_requested = str(payload.get('dbType') or Config.DB_TYPE).lower()

    try:
        conn_info = validate_connection_info(payload)
    except ValidatorError as e:
        from utils.error_handler import error_response
        return error_response(e.message, 400, 'VALIDATION_ERROR')

    try:
        adapter = get_database_adapter(db_type_requested)
    except Exception as error:
        from utils.error_handler import error_response
        return error_response(str(error), 400, 'UNSUPPORTED_DATABASE')

    try:
        connection = adapter.open_connection(conn_info)
    except Exception as error:
        friendly_msg = adapter.friendly_connection_error(error)
        return handle_database_error(error, friendly_msg)

    try:
        cursor = connection.cursor()

        try:
            tables = discover_tables(cursor, adapter)
            columns_by_table = discover_columns(cursor, adapter)
        except Exception as discovery_error:
            return jsonify({
                'message': f'Connected to "{conn_info["database"]}" successfully, but table discovery failed.',
                'database': conn_info['database'],
                'connected': True,
                'warning': 'Connected, but DataLens could not read table metadata. Grant access to INFORMATION_SCHEMA.TABLES and INFORMATION_SCHEMA.COLUMNS, then try again.',
                'discoveryError': str(discovery_error),
                'tables': [],
                'tableCount': 0,
                'filteredTableCount': 0
            })

        if not tables:
            return jsonify({
                'message': f'Connected to "{conn_info["database"]}" successfully. No user tables found.',
                'database': conn_info['database'],
                'connected': True,
                'tables': [],
                'tableCount': 0,
                'filteredTableCount': 0
            })

        safe_labels = set(filter_sensitive_tables([table['label'] for table in tables]))

        profiled_tables = []
        analytics_ready_count = 0
        for table in tables:
            profile = table_analytics_profile(
                table['label'],
                columns_by_table.get(table['label'], []),
                table['rowCount']
            )
            if table['label'] not in safe_labels:
                profile = {
                    **profile,
                    'usable': False,
                    'score': min(profile.get('score', 0), 20),
                    'healthLabel': 'Blocked',
                    'healthReasons': ['Sensitive-looking table name'],
                    'reason': 'Sensitive-looking table name',
                    'recommendedAction': 'Choose a non-sensitive analytics table.'
                }
            if profile['usable']:
                analytics_ready_count += 1
            profiled_tables.append({
                **table,
                'analyticsReady': profile['usable'],
                'profile': profile
            })

        return jsonify({
            'message': f'Connected to "{conn_info["database"]}" successfully.',
            'database': conn_info['database'],
            'connected': True,
            'tables': profiled_tables,
            'tableCount': analytics_ready_count,
            'analyticsReadyCount': analytics_ready_count,
            'rawTableCount': len(tables),
            'safeTableCount': len(profiled_tables),
            'sensitiveTableCount': max(len(tables) - len(safe_labels), 0),
            'filteredTableCount': 0
        })
    except Exception as error:
        friendly_msg = adapter.friendly_connection_error(error)
        return handle_database_error(error, friendly_msg)
    finally:
        try:
            connection.close()
        except Exception:
            pass

# Backwards compatibility wrappers for tests
def build_connection_string(conn_info: Dict[str, Any]) -> str:
    """
    Build SQL Server connection string.
    
    Backwards compatibility wrapper - delegates to SQLServerAdapter.
    """
    from utils.db_adapter import SQLServerAdapter
    adapter = SQLServerAdapter()
    return adapter.build_connection_string(conn_info)


def friendly_connection_error(error: Exception) -> str:
    """
    Convert SQL Server error to friendly message.
    
    Backwards compatibility wrapper - delegates to SQLServerAdapter.
    """
    from utils.db_adapter import SQLServerAdapter
    adapter = SQLServerAdapter()
    return adapter.friendly_connection_error(error)
