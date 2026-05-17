import re
from typing import Any, List

SENSITIVE_KEYWORDS = [
    'user', 'password', 'auth', 'credential', 'token',
    'admin', 'role', 'permission', 'secret', 'session',
    'audit', 'log', 'key', 'hash', 'salt'
]
TABLE_NAME_PATTERN = re.compile(r'^[\w.\-]+$')


def sanitize_table_name(table_name: str) -> str:
    return table_name.strip()


def is_table_name_safe(table_name: str) -> bool:
    return bool(TABLE_NAME_PATTERN.fullmatch(table_name))


def is_identifier_safe(identifier: str) -> bool:
    return bool(identifier and '\x00' not in identifier)


def quote_identifier(identifier: str) -> str:
    if not is_identifier_safe(identifier):
        raise ValueError('Invalid SQL identifier.')
    return f"[{identifier.replace(']', ']]')}]"


def table_label(schema_name: str, table_name: str) -> str:
    return f'{schema_name}.{table_name}'


def parse_table_reference(value: Any) -> dict:
    if isinstance(value, dict):
        schema_name = sanitize_table_name(value.get('schema') or value.get('TABLE_SCHEMA') or 'dbo')
        table_name = sanitize_table_name(value.get('name') or value.get('TABLE_NAME') or '')
    else:
        raw_value = sanitize_table_name(str(value or ''))
        if '.' in raw_value:
            schema_name, table_name = raw_value.split('.', 1)
            schema_name = sanitize_table_name(schema_name)
            table_name = sanitize_table_name(table_name)
        else:
            schema_name = 'dbo'
            table_name = raw_value

    if not is_identifier_safe(schema_name) or not is_identifier_safe(table_name):
        raise ValueError('Invalid table reference.')

    return {
        'schema': schema_name,
        'name': table_name,
        'label': table_label(schema_name, table_name),
        'quoted': f'{quote_identifier(schema_name)}.{quote_identifier(table_name)}'
    }


def filter_sensitive_tables(table_names: List[str]) -> List[str]:
    return [
        name for name in table_names
        if not any(keyword in name.lower() for keyword in SENSITIVE_KEYWORDS)
    ]


def normalize_boolean(value: Any) -> bool:
    return value in (True, 'true', 'True', '1', 1)
