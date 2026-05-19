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
    'decimal', 'numeric', 'money', 'smallmoney', 'double'
}
DATE_TYPES = {'date', 'datetime', 'datetime2', 'smalldatetime', 'datetimeoffset', 'time', 'timestamp', 'year'}
TEXT_TYPES = {'varchar', 'nvarchar', 'char', 'nchar', 'text', 'ntext', 'tinytext', 'mediumtext', 'longtext'}
ANALYTIC_TYPES = NUMERIC_TYPES | DATE_TYPES | TEXT_TYPES | {'bit'}


def sanitize_table_name(table_name: str) -> str:
    return table_name.strip()


def is_table_name_safe(table_name: str) -> bool:
    return bool(TABLE_NAME_PATTERN.fullmatch(table_name))


def is_identifier_safe(identifier: str) -> bool:
    return bool(identifier and '\x00' not in identifier)


def quote_identifier(identifier: str, db_type: str = 'sqlserver') -> str:
    if not is_identifier_safe(identifier):
        raise ValueError('Invalid SQL identifier.')
    if str(db_type or 'sqlserver').lower() == 'mysql':
        return f"`{identifier.replace('`', '``')}`"
    # SQL Server bracket quoting: ] escapes to ]]
    return f"[{identifier.replace(']', ']]')}]"


def table_label(schema_name: str, table_name: str) -> str:
    return f'{schema_name}.{table_name}'


def parse_table_reference(value: Any, db_type: str = 'sqlserver') -> dict:
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
        'quoted': f'{quote_identifier(schema_name, db_type)}.{quote_identifier(table_name, db_type)}'
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

    blockers = []
    warnings = []
    strengths = []

    if row_count <= 0:
        blockers.append('No rows available')
    else:
        strengths.append(f'{int(row_count or 0)} row(s) available')

    if column_count < 2:
        blockers.append('Needs at least two columns')
    else:
        strengths.append(f'{column_count} column(s) detected')

    if sensitive_columns:
        preview = ', '.join(sensitive_columns[:3])
        suffix = '...' if len(sensitive_columns) > 3 else ''
        blockers.append(f'Contains sensitive-looking columns: {preview}{suffix}')

    if not analytic_columns:
        blockers.append('No supported numeric, date, text, or boolean columns')

    if not numeric_measures and not text_dimensions and not date_columns:
        blockers.append('Only technical identifiers or unsupported fields')

    if numeric_measures:
        strengths.append(f'{len(numeric_measures)} numeric measure(s)')
    else:
        warnings.append('No numeric measure; KPI, anomaly, and variance insights will be limited')

    if text_dimensions:
        strengths.append(f'{len(text_dimensions)} text dimension(s)')
    else:
        warnings.append('No text dimension for category breakdowns')

    if date_columns:
        strengths.append(f'{len(date_columns)} date/time field(s)')
    else:
        warnings.append('No date/time field; trend and forecast insights will be limited')

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

    score = min(score, 100)
    usable = (
        row_count > 0
        and column_count >= 2
        and not sensitive_columns
        and bool(analytic_columns)
        and bool(numeric_measures or text_dimensions or date_columns)
    )

    if not usable:
        health_label = 'Blocked'
    elif score >= 85:
        health_label = 'Excellent'
    elif score >= 65:
        health_label = 'Good'
    else:
        health_label = 'Fair'

    health_reasons = blockers if blockers else warnings[:3]
    if not health_reasons:
        health_reasons = ['Ready for analytics']

    suggested_view = (
        'time-series' if date_columns and numeric_measures else
        'metrics' if numeric_measures else
        'categories' if text_dimensions else
        'quality'
    )
    recommended_action = (
        'Choose this table for dashboard and Smart Insights.' if usable and score >= 65 else
        'Usable, but add numeric and date fields for stronger Smart Insights.' if usable else
        'Review the table structure or choose another table.'
    )

    return {
        'usable': usable,
        'score': score,
        'healthLabel': health_label,
        'healthReasons': health_reasons,
        'strengths': strengths[:4],
        'recommendedAction': recommended_action,
        'rowCount': int(row_count or 0),
        'columnCount': column_count,
        'numericMeasureCount': len(numeric_measures),
        'dateColumnCount': len(date_columns),
        'textDimensionCount': len(text_dimensions),
        'reason': ', '.join((blockers or warnings)) if (blockers or warnings) else 'analytics-ready',
        'suggestedView': suggested_view
    }
def normalize_boolean(value: Any) -> bool:
    return value in (True, 'true', 'True', '1', 1)
