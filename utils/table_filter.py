import re
from typing import Any, Dict, List

SENSITIVE_KEYWORDS = [
    'user', 'password', 'auth', 'credential', 'token',
    'admin', 'role', 'permission', 'secret', 'session',
    'audit', 'log', 'hash', 'salt'
]
TABLE_NAME_PATTERN = re.compile(r'^[\w.\-]+$')
NUMERIC_TYPES = {
    'int', 'bigint', 'smallint', 'tinyint', 'float', 'real',
    'decimal', 'numeric', 'money', 'smallmoney'
}
DATE_TYPES = {'date', 'datetime', 'datetime2', 'smalldatetime', 'datetimeoffset', 'time'}
TEXT_TYPES = {'varchar', 'nvarchar', 'char', 'nchar', 'text', 'ntext'}
ANALYTIC_TYPES = NUMERIC_TYPES | DATE_TYPES | TEXT_TYPES | {'bit'}


def sanitize_table_name(table_name: str) -> str:
    return table_name.strip()


def is_table_name_safe(table_name: str) -> bool:
    return bool(TABLE_NAME_PATTERN.fullmatch(table_name))


def is_identifier_safe(identifier: str) -> bool:
    return bool(identifier and '\x00' not in identifier)


def quote_identifier(identifier: str) -> str:
    if not is_identifier_safe(identifier):
        raise ValueError('Invalid SQL identifier.')
    # SQL Server bracket quoting: ] escapes to ]] 
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
        if not is_sensitive_name(name)
    ]


def is_sensitive_name(name: str) -> bool:
    lowered = str(name or '').lower()
    return any(keyword in lowered for keyword in SENSITIVE_KEYWORDS)


def is_id_column(name: str) -> bool:
    return re.search(r'(?:^|_)(?:id|rowid|serial|guid|uuid)$|id$', name, re.IGNORECASE) is not None


def table_analytics_profile(table_name: str, columns: List[Dict[str, Any]], row_count: int = 0) -> Dict[str, Any]:
    column_count = len(columns)
    sensitive_columns = [
        str(col.get('COLUMN_NAME') or col.get('name') or '')
        for col in columns
        if is_sensitive_name(col.get('COLUMN_NAME') or col.get('name') or '')
    ]
    normalized = [
        {
            'name': str(col.get('COLUMN_NAME') or col.get('name') or ''),
            'type': str(col.get('DATA_TYPE') or col.get('dataType') or '').lower()
        }
        for col in columns
    ]
    analytic_columns = [col for col in normalized if col['type'] in ANALYTIC_TYPES]
    numeric_measures = [
        col for col in normalized
        if col['type'] in NUMERIC_TYPES and not is_id_column(col['name'])
    ]
    date_columns = [col for col in normalized if col['type'] in DATE_TYPES]
    text_dimensions = [
        col for col in normalized
        if col['type'] in TEXT_TYPES and not is_sensitive_name(col['name'])
    ]

    reasons = []
    if row_count <= 0:
        reasons.append('empty table')
    if column_count < 2:
        reasons.append('not enough columns')
    if sensitive_columns:
        reasons.append('contains sensitive-looking columns')
    if not analytic_columns:
        reasons.append('no analytics-friendly column types')
    if not numeric_measures and not text_dimensions and not date_columns:
        reasons.append('only technical identifiers or unsupported fields')

    score = 0
    if row_count > 0:
        score += 25
    if numeric_measures:
        score += 30
    if text_dimensions:
        score += 20
    if date_columns:
        score += 15
    if column_count >= 3:
        score += 10
    if sensitive_columns:
        score = min(score, 20)

    usable = (
        row_count > 0
        and column_count >= 2
        and not sensitive_columns
        and bool(analytic_columns)
        and bool(numeric_measures or text_dimensions or date_columns)
    )

    return {
        'usable': usable,
        'score': min(score, 100),
        'rowCount': int(row_count or 0),
        'columnCount': column_count,
        'numericMeasureCount': len(numeric_measures),
        'dateColumnCount': len(date_columns),
        'textDimensionCount': len(text_dimensions),
        'reason': ', '.join(reasons) if reasons else 'analytics-ready',
        'suggestedView': (
            'time-series' if date_columns and numeric_measures else
            'metrics' if numeric_measures else
            'categories' if text_dimensions else
            'quality'
        )
    }


def normalize_boolean(value: Any) -> bool:
    return value in (True, 'true', 'True', '1', 1)
