"""Request validation utilities for DataLens API."""

import re
from typing import Any, Dict, List, Tuple
from functools import wraps
from flask import request, jsonify

# Configuration
MAX_FIELD_LENGTH = 256
MAX_PASSWORD_LENGTH = 512
MAX_TABLE_NAME_LENGTH = 256
MAX_PORT = 65535
MIN_PORT = 1
SERVER_PATTERN = re.compile(r'^[A-Za-z0-9_.\\,\-:]+$')


class ValidationError(Exception):
    """Custom exception for validation errors."""
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


def validate_string(value: Any, field_name: str, max_length: int = MAX_FIELD_LENGTH, allow_empty: bool = False) -> str:
    """Validate and clean string input."""
    if value is None or value == '':
        if not allow_empty:
            raise ValidationError(f'{field_name} is required.')
        return ''
    
    text = str(value).strip()
    if not text and not allow_empty:
        raise ValidationError(f'{field_name} is required.')
    if len(text) > max_length:
        raise ValidationError(f'{field_name} exceeds maximum length of {max_length} characters.')
    if any(ord(char) < 32 for char in text):
        raise ValidationError(f'{field_name} contains invalid control characters.')
    
    return text


def validate_server(value: Any) -> str:
    """Validate SQL Server hostname."""
    server = validate_string(value, 'server')
    if ';' in server or not SERVER_PATTERN.fullmatch(server):
        raise ValidationError('server contains invalid characters. Use alphanumeric, dots, backslash, comma, hyphen, or colon.')
    return server


def validate_port(value: Any) -> str:
    """Validate port number."""
    if value in (None, ''):
        return ''
    try:
        port = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValidationError('port must be a valid number.')
    if port < MIN_PORT or port > MAX_PORT:
        raise ValidationError(f'port must be between {MIN_PORT} and {MAX_PORT}.')
    return str(port)


def validate_database(value: Any) -> str:
    """Validate database name."""
    return validate_string(value, 'database', max_length=MAX_FIELD_LENGTH)


def validate_username(value: Any) -> str:
    """Validate username."""
    return validate_string(value, 'username', max_length=MAX_FIELD_LENGTH)


def validate_password(value: Any) -> str:
    """Validate password."""
    return validate_string(value, 'password', max_length=MAX_PASSWORD_LENGTH)


def validate_table_name(value: Any) -> Any:
    """Validate table name format (schema.table) or structured table reference."""
    if isinstance(value, dict):
        schema = validate_string(value.get('schema') or value.get('TABLE_SCHEMA') or '', 'tableName.schema', max_length=MAX_TABLE_NAME_LENGTH)
        name = validate_string(value.get('name') or value.get('TABLE_NAME') or '', 'tableName.name', max_length=MAX_TABLE_NAME_LENGTH)
        return {
            'schema': schema,
            'name': name,
            'label': value.get('label') or f'{schema}.{name}'
        }

    name = validate_string(value, 'tableName', max_length=MAX_TABLE_NAME_LENGTH)
    if '.' not in name:
        raise ValidationError('tableName must be in format "schema.table".')
    parts = name.split('.')
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValidationError('tableName must be in format "schema.table".')
    return name

def validate_boolean(value: Any) -> bool:
    """Validate and convert boolean input."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ('true', '1', 'yes', 'on')
    if isinstance(value, int):
        return value != 0
    return False


def validate_connection_info(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate complete connection info payload."""
    if not isinstance(payload, dict):
        raise ValidationError('Request body must be valid JSON.')
    
    return {
        'server': validate_server(payload.get('server')),
        'port': validate_port(payload.get('port')),
        'database': validate_database(payload.get('database')),
        'username': validate_username(payload.get('username')),
        'password': validate_password(payload.get('password')),
        'encrypt': validate_boolean(payload.get('encrypt', False)),
        'trustCert': validate_boolean(payload.get('trustCert', False))
    }


def validate_table_request(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], str, bool]:
    """Validate table analytics request payload."""
    if not isinstance(payload, dict):
        raise ValidationError('Request body must be valid JSON.')
    
    conn_info = payload.get('connInfo')
    if not conn_info:
        raise ValidationError('connInfo is required.')
    
    table_name = validate_table_name(payload.get('tableName'))
    cleaned_mode = validate_boolean(payload.get('cleanedMode', False))
    
    return conn_info, table_name, cleaned_mode


def validate_json_payload():
    """Decorator to validate and parse JSON payload."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                payload = request.get_json(force=True, silent=False)
                if not payload:
                    payload = {}
                request.json_payload = payload
            except Exception as e:
                raise ValidationError(f'Invalid JSON request: {str(e)}', 400)
            return f(*args, **kwargs)
        return wrapper
    return decorator


def handle_validation_error(f):
    """Decorator to handle validation errors."""
    def decorator(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValidationError as e:
            return jsonify({'error': e.message}), e.status_code
    return decorator
