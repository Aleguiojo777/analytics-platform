from typing import Any, Dict, List
from datetime import datetime
from io import BytesIO

from flask import jsonify, request, send_file

from services.analytics_insights import (
    analyze_anomalies_detailed,
    analyze_trend,
    detect_anomalies,
    generate_executive_summary,
    generate_insights,
    mean,
    median,
    std_dev,
)
from controllers.db_controller import rows_to_dicts
from utils.table_filter import (
    DATE_TYPES,
    NUMERIC_TYPES,
    TEXT_TYPES,
    filter_sensitive_tables,
    is_id_column,
    parse_table_reference,
    quote_identifier,
    table_analytics_profile,
)
from utils.validators import validate_table_request, ValidationError as ValidatorError
from utils.error_handler import handle_app_error, handle_database_error, ForbiddenError, NotFoundError
from utils.config import Config
from utils.db_adapter import get_database_adapter


try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

def execute_with_params(cursor, query: str, params: tuple, db_type: str):
    """Execute parameterized SQL for either mysql.connector or pyodbc."""
    if db_type == 'mysql':
        return cursor.execute(query, params)
    return cursor.execute(query, *params)


def table_exists(cursor, table_ref: Dict[str, str], db_type: str) -> bool:
    """Check if table exists (database-agnostic)."""
    placeholder = '%s' if db_type == 'mysql' else '?'
    execute_with_params(
        cursor,
        "SELECT 1 FROM INFORMATION_SCHEMA.TABLES "
        f"WHERE TABLE_TYPE = 'BASE TABLE' AND TABLE_SCHEMA = {placeholder} AND TABLE_NAME = {placeholder}",
        (table_ref['schema'], table_ref['name']),
        db_type
    )
    return cursor.fetchone() is not None

def load_columns(cursor, table_ref: Dict[str, str], db_type: str) -> List[Dict[str, Any]]:
    """Load column information (database-agnostic)."""
    placeholder = '%s' if db_type == 'mysql' else '?'
    execute_with_params(
        cursor,
        "SELECT COLUMN_NAME, DATA_TYPE "
        "FROM INFORMATION_SCHEMA.COLUMNS "
        f"WHERE TABLE_SCHEMA = {placeholder} AND TABLE_NAME = {placeholder} "
        "ORDER BY ORDINAL_POSITION",
        (table_ref['schema'], table_ref['name']),
        db_type
    )
    columns = []
    for row in cursor.fetchall():
        # Handle both pyodbc.Row and mysql.connector tuple
        if hasattr(row, 'COLUMN_NAME'):
            columns.append({'COLUMN_NAME': row.COLUMN_NAME, 'DATA_TYPE': row.DATA_TYPE})
        else:
            columns.append({'COLUMN_NAME': row[0], 'DATA_TYPE': row[1]})
    return columns

def text_value_sql(column_sql: str, data_type: str, db_type: str = None) -> str:
    """Convert text columns to string for consistent handling."""
    dtype = str(data_type or '').lower()
    if dtype in ('text', 'ntext', 'longtext', 'mediumtext', 'tinytext'):
        cast_type = 'CHAR(4000)' if db_type == 'mysql' else 'NVARCHAR(4000)'
        return f"CAST({column_sql} AS {cast_type})"
    return column_sql

def _clean_text_expr(col_sql: str) -> str:
    """Safe cleansing for analytics: trim + empty string => NULL."""
    return f"NULLIF(TRIM({col_sql}), '')"


def _clean_numeric_expr(col_sql: str) -> str:
    """Safe numeric cleansing for analytics."""
    return f"CAST({col_sql} AS DECIMAL(18,4))"


def analytics_value_sql(col: Dict[str, Any], cleaned_mode: bool, db_type: str = None) -> str:
    """Generate SQL expression for analytics value based on database type."""
    if db_type is None:
        db_type = Config.DB_TYPE.lower()
    
    col_sql = quote_identifier(col['COLUMN_NAME'], db_type)
    dtype = str(col.get('DATA_TYPE') or '').lower()
    
    if cleaned_mode and dtype in TEXT_TYPES:
        return _clean_text_expr(text_value_sql(col_sql, dtype, db_type))
    if cleaned_mode and dtype in NUMERIC_TYPES:
        return _clean_numeric_expr(col_sql)
    if dtype in ('text', 'ntext', 'longtext'):
        return text_value_sql(col_sql, dtype, db_type)
    return col_sql


def numeric_value_sql(col: Dict[str, Any], cleaned_mode: bool, db_type: str = None) -> str:
    """Generate SQL expression for numeric value."""
    if db_type is None:
        db_type = Config.DB_TYPE.lower()
    
    col_sql = quote_identifier(col['COLUMN_NAME'], db_type)
    if cleaned_mode:
        return _clean_numeric_expr(col_sql)
    return f"CAST({col_sql} AS DECIMAL(18,4))"


def get_limit_clause(limit: int, db_type: str = None) -> str:
    """Generate LIMIT clause for the database."""
    if db_type is None:
        db_type = Config.DB_TYPE.lower()
    
    if db_type == 'mysql':
        return f"LIMIT {limit}"
    else:  # SQL Server
        return f"OFFSET 0 ROWS FETCH NEXT {limit} ROWS ONLY"


def get_string_length_fn(db_type: str = None) -> str:
    """Get string length function for the database."""
    if db_type is None:
        db_type = Config.DB_TYPE.lower()
    return "LENGTH" if db_type == 'mysql' else "LEN"


def get_date_format_expr(col_sql: str, db_type: str = None) -> str:
    """Get date formatting expression for the database."""
    if db_type is None:
        db_type = Config.DB_TYPE.lower()
    
    if db_type == 'mysql':
        return f"DATE_FORMAT({col_sql}, '%Y-%m-%d')"
    else:  # SQL Server
        return f"CONVERT(VARCHAR(10), {col_sql}, 120)"


def load_category_profile(cursor, table_sql: str, text_cols: List[Dict[str, Any]], total_rows: int, 
                         cleaned_mode: bool = False, db_type: str = None) -> List[Dict[str, Any]]:
    """Load category profiles for text columns."""
    if db_type is None:
        db_type = Config.DB_TYPE.lower()
    
    profiles: List[Dict[str, Any]] = []
    str_len_fn = get_string_length_fn(db_type)
    
    for col in text_cols[:8]:
        col_name = col['COLUMN_NAME']
        value_sql = analytics_value_sql(col, cleaned_mode, db_type)
        
        cursor.execute(
            f"SELECT COUNT(DISTINCT {value_sql}) AS distinct_count, COUNT({value_sql}) AS filled_count "
            f"FROM {table_sql} "
            f"WHERE {value_sql} IS NOT NULL AND {str_len_fn}({value_sql}) > 0"
        )
        row = cursor.fetchone()
        
        # Handle both pyodbc.Row and tuple
        if hasattr(row, 'distinct_count'):
            distinct_count = int(row.distinct_count or 0)
            filled_count = int(row.filled_count or 0)
        else:
            distinct_count = int(row[0] or 0)
            filled_count = int(row[1] or 0)
        
        if distinct_count == 0:
            continue
        
        uniqueness = distinct_count / max(filled_count, 1)
        score = 100 - min(abs(distinct_count - 8) * 6, 70) - min(uniqueness * 35, 35)
        profiles.append({
            'column': col_name,
            'distinctCount': distinct_count,
            'filledCount': filled_count,
            'coveragePercent': round((filled_count / total_rows) * 100, 1) if total_rows else 0,
            'score': round(score, 2)
        })
    
    return sorted(profiles, key=lambda item: item['score'], reverse=True)


def extract_row_value(row: Any, index: int) -> Any:
    """Extract value from row (handles both pyodbc.Row and tuple)."""
    if hasattr(row, '__getitem__'):
        return row[index]
    return row[index]


def request_db_type(payload: Dict[str, Any]) -> str:
    """Read selected database type from the request or connection info."""
    conn_info = payload.get('connInfo') if isinstance(payload, dict) else {}
    db_type = payload.get('dbType') or (conn_info or {}).get('dbType') or Config.DB_TYPE
    return str(db_type).lower()


def parse_requested_table(payload: Dict[str, Any], db_type: str):
    """Parse and validate table request payload."""
    try:
        conn_info, table_name, cleaned_mode = validate_table_request(payload)
    except ValidatorError as e:
        return None, (jsonify({'error': e.message}), 400)
    
    try:
        table_ref = parse_table_reference(table_name, db_type)
    except ValueError as e:
        return None, (jsonify({'error': str(e)}), 400)

    if not filter_sensitive_tables([table_ref['label']]):
        raise ForbiddenError('Access to this table is not allowed.')

    return (conn_info, table_ref, cleaned_mode), None




INSIGHT_MODES = {
    'executive': 'Executive Summary',
    'quality': 'Data Quality Review',
    'anomaly': 'Anomaly Investigation',
    'forecast': 'Forecast Readiness',
    'kpi': 'Business KPI Suggestions'
}


def normalize_insight_mode(value: Any) -> str:
    mode = str(value or 'executive').strip().lower()
    return mode if mode in INSIGHT_MODES else 'executive'


def _column_names(columns: List[Dict[str, Any]], limit: int = 4) -> str:
    names = [str(col.get('COLUMN_NAME') or '') for col in columns if col.get('COLUMN_NAME')]
    return ', '.join(names[:limit]) or 'none detected'

def _analysis_columns(analyses: List[Dict[str, Any]], limit: int = 4) -> str:
    names = [str(item.get('column') or '') for item in analyses if item.get('column')]
    return ', '.join(names[:limit]) or 'none analyzed'


def _top_metric_lines(summary: Dict[str, Any]) -> List[str]:
    lines = []
    for metric in (summary.get('keyMetrics') or [])[:5]:
        lines.append(
            f"{metric.get('column')}: average {metric.get('value')}, range {metric.get('range')}, variation {metric.get('variation')}"
        )
    return lines or ['No stable numeric metric was available for this report.']


def _category_lines(summary: Dict[str, Any]) -> List[str]:
    lines = []
    for metric in (summary.get('categoryMetrics') or [])[:4]:
        lines.append(
            f"{metric.get('column')}: {metric.get('distinctCount')} distinct values, {metric.get('coveragePercent')}% filled"
        )
    return lines or ['No strong category dimension was available for segmentation.']


def _trend_lines(summary: Dict[str, Any]) -> List[str]:
    lines = []
    for trend in (summary.get('trends') or [])[:5]:
        lines.append(
            f"{trend.get('column')}: {trend.get('direction')} trend with {trend.get('strength')} strength"
        )
    return lines or ['No time-based trend could be calculated from the available fields.']


def _anomaly_lines(summary: Dict[str, Any], analyses: List[Dict[str, Any]]) -> List[str]:
    lines = []
    for anomaly in (summary.get('criticalAnomalies') or [])[:5]:
        lines.append(f"{anomaly.get('column')}: {anomaly.get('count')} detected anomaly value(s)")
    if lines:
        return lines
    checked = _analysis_columns(analyses)
    return [f'No strong anomalies were detected across analyzed column(s): {checked}.']


def build_report_sections(
    mode: str,
    summary: Dict[str, Any],
    profile: Dict[str, Any],
    numeric_cols: List[Dict[str, Any]],
    date_cols: List[Dict[str, Any]],
    text_cols: List[Dict[str, Any]],
    analyses: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    observations = list(summary.get('keyObservations') or [])
    recommendations = list(summary.get('recommendations') or [])

    if mode == 'quality':
        return [
            {
                'title': 'Readiness Snapshot',
                'items': [
                    f"Health: {profile.get('healthLabel', 'Unknown')} ({profile.get('score', 0)}%)",
                    f"Rows: {profile.get('rowCount', 0)}",
                    f"Columns: {profile.get('columnCount', 0)}",
                ]
            },
            {'title': 'What To Check', 'items': profile.get('healthReasons') or observations or ['No major readiness warnings detected.']},
            {'title': 'Recommended Next Steps', 'items': recommendations or ['Use this table for dashboarding if the detected structure matches the business question.']}
        ]

    if mode == 'anomaly':
        return [
            {'title': 'Anomaly Findings', 'items': _anomaly_lines(summary, analyses)},
            {'title': 'Columns Reviewed', 'items': [f"Analyzed numeric column(s): {_analysis_columns(analyses)}"]},
            {'title': 'Investigation Steps', 'items': recommendations or ['Validate the largest unusual values against source transactions or business events.']}
        ]

    if mode == 'forecast':
        readiness = []
        readiness.append(f"Date fields: {_column_names(date_cols, 4)}")
        readiness.append(f"Numeric measures: {_column_names(numeric_cols, 4)}")
        readiness.append('Forecast confidence improves when date coverage is consistent and the selected measure has enough history.')
        return [
            {'title': 'Forecast Readiness', 'items': readiness},
            {'title': 'Trend Signals', 'items': _trend_lines(summary)},
            {'title': 'Recommended Next Steps', 'items': recommendations or ['Add a reliable date field and primary measure before forecasting.']}
        ]

    if mode == 'kpi':
        return [
            {'title': 'Candidate KPIs', 'items': _top_metric_lines(summary)},
            {'title': 'Useful Dimensions', 'items': _category_lines(summary) if text_cols else ['No text dimensions were detected for segmentation.']},
            {'title': 'Reporting Guidance', 'items': recommendations or ['Pick one primary KPI, one time field, and one segmentation field for the first dashboard.']}
        ]

    return [
        {'title': 'Decision Summary', 'items': observations or ['Review metrics, trends, anomalies, and recommendations below.']},
        {'title': 'Key Metrics', 'items': _top_metric_lines(summary)},
        {'title': 'Recommended Actions', 'items': recommendations or ['No immediate action is required from the current analysis.']}
    ]

def apply_insight_mode(
    summary: Dict[str, Any],
    mode: str,
    profile: Dict[str, Any],
    numeric_cols: List[Dict[str, Any]],
    date_cols: List[Dict[str, Any]],
    text_cols: List[Dict[str, Any]],
    analyses: List[Dict[str, Any]],
) -> Dict[str, Any]:
    summary = dict(summary or {})
    mode = normalize_insight_mode(mode)
    recommendations = list(summary.get('recommendations') or [])
    observations = list(summary.get('keyObservations') or [])

    summary['mode'] = mode
    summary['modeLabel'] = INSIGHT_MODES[mode]
    summary['dataQualityScore'] = summary.get('dataQualityScore', profile.get('score', 0))

    if mode == 'quality':
        observations.insert(0, f"Table health is {profile.get('healthLabel', 'Unknown')} at {profile.get('score', 0)}% readiness.")
        for reason in profile.get('healthReasons', [])[:3]:
            recommendations.insert(0, f'Data quality focus: {reason}.')
        recommendations.append('Validate missing values, duplicate categories, and type consistency before using the results for decisions.')
        summary['narrativeText'] = f"Data Quality Review: this table scored {profile.get('score', 0)}% readiness. Use this mode to decide whether the table is trustworthy enough for dashboarding and reporting."
    elif mode == 'anomaly':
        anomaly_count = sum(len(item.get('anomalies') or []) for item in analyses)
        if anomaly_count:
            observations.insert(0, f'{anomaly_count} numeric outlier(s) were detected across analyzed measures.')
            recommendations.insert(0, 'Investigate the largest outliers first, then compare them with source records and business events.')
        else:
            observations.insert(0, 'No strong numeric outlier cluster was detected in the sampled analysis window.')
            recommendations.insert(0, 'Increase sample size or add more measurable numeric columns if deeper anomaly review is required.')
        summary['narrativeText'] = 'Anomaly Investigation: this view prioritizes unusual values, their likely impact, and practical validation steps.'
    elif mode == 'forecast':
        if date_cols and numeric_cols:
            observations.insert(0, f"Forecast-ready structure detected: date field(s) {_column_names(date_cols, 2)} and measure(s) {_column_names(numeric_cols, 3)}.")
            recommendations.insert(0, 'Use a stable date field and one primary business measure before trusting forecast direction.')
        else:
            missing = []
            if not date_cols:
                missing.append('a date/time field')
            if not numeric_cols:
                missing.append('a numeric measure')
            recommendations.insert(0, f"Forecast readiness is limited because the table needs {' and '.join(missing)}.")
        summary['narrativeText'] = 'Forecast Readiness: this view checks whether the table has enough time and measure structure for trend-based planning.'
    elif mode == 'kpi':
        if numeric_cols:
            recommendations.insert(0, f"Candidate KPIs: {_column_names(numeric_cols, 5)}.")
        if text_cols:
            recommendations.append(f"Use {_column_names(text_cols, 4)} as dimensions to segment KPI performance.")
        if date_cols:
            recommendations.append(f"Use {_column_names(date_cols, 2)} for period-over-period KPI tracking.")
        observations.insert(0, 'KPI suggestions are derived from numeric measures, category dimensions, and available date fields.')
        summary['narrativeText'] = 'Business KPI Suggestions: this view translates detected columns into candidate metrics and reporting dimensions.'
    else:
        recommendations.append('Use the mode selector to switch between quality, anomaly, forecast, and KPI-focused recommendations.')

    summary['recommendations'] = recommendations[:8]
    summary['keyObservations'] = observations[:6]
    summary['reportSections'] = build_report_sections(mode, summary, profile, numeric_cols, date_cols, text_cols, analyses)
    return summary
@handle_app_error
def get_table_analytics():
    """Retrieve comprehensive analytics for a specific table."""
    payload = request.get_json(force=True, silent=True) or {}
    db_type = request_db_type(payload)
    parsed, error_response = parse_requested_table(payload, db_type)
    if error_response:
        return error_response
    conn_info, table_ref, use_clean = parsed

    try:
        adapter = get_database_adapter(db_type)
        
        with adapter.open_connection(conn_info) as connection:
            cursor = connection.cursor()
            if not table_exists(cursor, table_ref, db_type):
                raise NotFoundError('Selected table was not found.')

            table_sql = table_ref['quoted']
            
            # Get total row count
            cursor.execute(f"SELECT COUNT(*) AS total FROM {table_sql}")
            row = cursor.fetchone()
            total_rows = extract_row_value(row, 0) or 0
            
            if total_rows == 0:
                return jsonify({'warning': 'Table is empty. Analytics will be limited.', 'totalRows': 0})

            columns = load_columns(cursor, table_ref, db_type)
            if not columns:
                raise ValueError('Table has no columns.')
            
            # Get sample rows
            if db_type == 'mysql':
                sample_limit_clause = get_limit_clause(Config.MAX_SAMPLE_ROWS, db_type)
                cursor.execute(f"SELECT * FROM {table_sql} {sample_limit_clause}")
            else:
                cursor.execute(f"SELECT TOP ({Config.MAX_SAMPLE_ROWS}) * FROM {table_sql}")
            sample_rows = rows_to_dicts(cursor, cursor.fetchall())
            
            # Cleaned analytics mode
            cleaned_sample_rows = sample_rows
            if use_clean and Config.ENABLE_CLEANED_MODE:
                select_exprs = []
                for c in columns:
                    col_sql = quote_identifier(c['COLUMN_NAME'], db_type)
                    value_sql = analytics_value_sql(c, use_clean, db_type)
                    select_exprs.append(f"{value_sql} AS {col_sql}" if value_sql != col_sql else col_sql)

                if db_type == 'mysql':
                    sample_limit_clause = get_limit_clause(Config.MAX_SAMPLE_ROWS, db_type)
                    cursor.execute(f"SELECT {', '.join(select_exprs)} FROM {table_sql} {sample_limit_clause}")
                else:
                    cursor.execute(f"SELECT TOP ({Config.MAX_SAMPLE_ROWS}) {', '.join(select_exprs)} FROM {table_sql}")
                cleaned_sample_rows = rows_to_dicts(cursor, cursor.fetchall())

            profile = table_analytics_profile(table_ref['label'], columns, total_rows)
            if not profile['usable']:
                raise ValueError(f"Selected table is not analytics-ready: {profile['reason']}.")

            numeric_cols = [c for c in columns if c['DATA_TYPE'] in NUMERIC_TYPES]
            date_cols = [c for c in columns if c['DATA_TYPE'] in DATE_TYPES]
            text_cols = [c for c in columns if c['DATA_TYPE'] in TEXT_TYPES]

            numeric_analysis_cols = [col for col in numeric_cols if not is_id_column(col['COLUMN_NAME'])]
            numeric_analysis_cols = numeric_analysis_cols if numeric_analysis_cols else numeric_cols

            # Numeric statistics
            numeric_stats = []
            for col in numeric_analysis_cols[:Config.MAX_NUMERIC_COLUMNS]:
                value_sql = numeric_value_sql(col, use_clean, db_type)
                cursor.execute(
                    f"SELECT "
                    f"MIN({value_sql}) AS min_val, "
                    f"MAX({value_sql}) AS max_val, "
                    f"AVG({value_sql}) AS avg_val, "
                    f"SUM({value_sql}) AS sum_val "
                    f"FROM {table_sql} "
                    f"WHERE {value_sql} IS NOT NULL"
                )
                row = cursor.fetchone()
                if row:
                    min_val = extract_row_value(row, 0)
                    max_val = extract_row_value(row, 1)
                    avg_val = extract_row_value(row, 2)
                    sum_val = extract_row_value(row, 3)
                    
                    numeric_stats.append({
                        'column': col['COLUMN_NAME'],
                        'min': float(min_val) if min_val is not None else 0,
                        'max': float(max_val) if max_val is not None else 0,
                        'avg': round(float(avg_val), 2) if avg_val is not None else 0,
                        'sum': round(float(sum_val), 2) if sum_val is not None else 0
                    })

            # Column quality
            column_quality = []
            for col in columns[:30]:
                value_sql = analytics_value_sql(col, use_clean, db_type)
                cursor.execute(f"SELECT COUNT(*) FROM {table_sql} WHERE {value_sql} IS NULL")
                null_count = extract_row_value(cursor.fetchone(), 0) or 0
                column_quality.append({
                    'column': col['COLUMN_NAME'],
                    'dataType': col['DATA_TYPE'],
                    'nullCount': null_count,
                    'nullPercent': round((null_count / total_rows) * 100, 1) if total_rows else 0
                })

            # Category data
            category_data = None
            category_profiles = load_category_profile(cursor, table_sql, text_cols[:Config.MAX_TEXT_COLUMNS], 
                                                     total_rows, use_clean, db_type)
            if category_profiles:
                text_col = category_profiles[0]['column']
                text_col_meta = next((col for col in text_cols if col['COLUMN_NAME'] == text_col), None)
                value_sql = analytics_value_sql(text_col_meta, use_clean, db_type) if text_col_meta else quote_identifier(text_col, db_type)
                str_len_fn = get_string_length_fn(db_type)
                
                limit_clause_10 = get_limit_clause(10, db_type)
                cursor.execute(
                    f"SELECT {value_sql} AS label, COUNT(*) AS item_count "
                    f"FROM {table_sql} "
                    f"WHERE {value_sql} IS NOT NULL AND {str_len_fn}({value_sql}) > 0 "
                    f"GROUP BY {value_sql} "
                    f"ORDER BY item_count DESC {limit_clause_10}"
                )
                cat_data = []
                for row in cursor.fetchall():
                    if hasattr(row, 'label'):
                        cat_data.append({'label': row.label, 'item_count': row.item_count})
                    else:
                        cat_data.append({'label': row[0], 'item_count': row[1]})
                
                category_data = {
                    'column': text_col,
                    'profile': category_profiles[0],
                    'data': cat_data
                }

            # Time series data
            time_series_data = None
            if date_cols and numeric_analysis_cols:
                date_col = date_cols[0]['COLUMN_NAME']
                date_sql = quote_identifier(date_col, db_type)
                date_fmt = get_date_format_expr(date_sql, db_type)
                num_col_meta = numeric_analysis_cols[0]
                num_sql = numeric_value_sql(num_col_meta, use_clean, db_type)
                
                limit_clause_30 = get_limit_clause(30, db_type)
                cursor.execute(
                    f"SELECT {date_fmt} AS period, SUM({num_sql}) AS total "
                    f"FROM {table_sql} "
                    f"WHERE {date_sql} IS NOT NULL AND {num_sql} IS NOT NULL "
                    f"GROUP BY {date_fmt} "
                    f"ORDER BY period {limit_clause_30}"
                )
                ts_data = []
                for row in cursor.fetchall():
                    if hasattr(row, 'period'):
                        ts_data.append({'period': row.period, 'total': row.total})
                    else:
                        ts_data.append({'period': row[0], 'total': row[1]})
                
                time_series_data = {
                    'dateColumn': date_col,
                    'valueColumn': num_col_meta['COLUMN_NAME'],
                    'data': ts_data
                }

            null_cells = sum(item['nullCount'] for item in column_quality)
            measured_cells = max(total_rows * len(column_quality), 1)
            completeness = round(100 - ((null_cells / measured_cells) * 100), 1) if column_quality else 100
            return jsonify({
                'tableName': table_ref['label'],
                'tableRef': {'schema': table_ref['schema'], 'name': table_ref['name'], 'label': table_ref['label']},
                'totalRows': total_rows,
                'columns': columns,
                'numericStats': numeric_stats,
                'categoryData': category_data,
                'timeSeriesData': time_series_data,
                'categoryProfiles': category_profiles,
                'columnQuality': column_quality,
                'completenessScore': completeness,
                'profile': profile,
                'sampleRows': cleaned_sample_rows[:10] if use_clean else sample_rows[:10]
            })
    except Exception as error:
        adapter = get_database_adapter(db_type)
        friendly_msg = adapter.friendly_connection_error(error)
        return handle_database_error(error, friendly_msg)


def pdf_text(value: Any) -> str:
    text = str(value or '').strip()
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def pdf_filename(value: str) -> str:
    safe = ''.join(ch if ch.isalnum() or ch in ('-', '_') else '_' for ch in str(value or 'report'))
    return safe.strip('_') or 'report'


def add_pdf_section(story, styles, title: str, items: List[Any]):
    story.append(Paragraph(pdf_text(title), styles['SectionTitle']))
    if not items:
        story.append(Paragraph('No items available.', styles['Body']))
    for item in items:
        story.append(Paragraph(f'- {pdf_text(item)}', styles['Body']))
    story.append(Spacer(1, 0.12 * inch))


def build_smart_insights_pdf(payload: Dict[str, Any]) -> BytesIO:
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError('PDF export dependency is not installed. Install reportlab and restart the server.')

    summary = payload.get('summary') or {}
    table_name = payload.get('tableName') or payload.get('table') or 'Selected table'
    mode_label = summary.get('modeLabel') or payload.get('modeLabel') or 'Smart Insights'
    generated = datetime.now().strftime('%Y-%m-%d %H:%M')

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.55 * inch,
        leftMargin=0.55 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
        title='DataLens Smart Insights Report'
    )

    base = getSampleStyleSheet()
    styles = {
        'Title': ParagraphStyle('ReportTitle', parent=base['Title'], fontName='Helvetica-Bold', fontSize=18, leading=22, spaceAfter=10, textColor=colors.HexColor('#111827')),
        'Meta': ParagraphStyle('ReportMeta', parent=base['BodyText'], fontName='Helvetica', fontSize=9, leading=12, textColor=colors.HexColor('#4b5563'), spaceAfter=4),
        'SectionTitle': ParagraphStyle('SectionTitle', parent=base['Heading2'], fontName='Helvetica-Bold', fontSize=12, leading=15, spaceBefore=10, spaceAfter=6, textColor=colors.HexColor('#111827')),
        'Body': ParagraphStyle('ReportBody', parent=base['BodyText'], fontName='Helvetica', fontSize=9.5, leading=13, textColor=colors.HexColor('#1f2937'), leftIndent=8, spaceAfter=4),
    }

    story = [
        Paragraph('DataLens Smart Insights Report', styles['Title']),
        Paragraph(f'<b>Table:</b> {pdf_text(table_name)}', styles['Meta']),
        Paragraph(f'<b>Mode:</b> {pdf_text(mode_label)}', styles['Meta']),
        Paragraph(f'<b>Generated:</b> {pdf_text(generated)}', styles['Meta']),
        Spacer(1, 0.12 * inch),
    ]

    score = summary.get('dataQualityScore')
    if score is not None:
        meta_table = Table([['Data Quality Score', f'{score}%']], colWidths=[2.2 * inch, 1.2 * inch])
        meta_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#eef2ff')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#111827')),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#c7d2fe')),
            ('PADDING', (0, 0), (-1, -1), 7),
        ]))
        story.extend([meta_table, Spacer(1, 0.12 * inch)])

    if summary.get('narrativeText'):
        add_pdf_section(story, styles, 'Narrative', [summary.get('narrativeText')])

    for section in summary.get('reportSections') or []:
        add_pdf_section(story, styles, section.get('title') or 'Report Section', section.get('items') or [])

    if summary.get('recommendations'):
        add_pdf_section(story, styles, 'Recommendations', summary.get('recommendations'))

    doc.build(story)
    buffer.seek(0)
    return buffer


@handle_app_error
def export_smart_insights_pdf():
    """Export the current Smart Insights report as a backend-generated PDF."""
    payload = request.get_json(force=True, silent=True) or {}
    summary = payload.get('summary') or {}
    if not summary:
        return jsonify({'error': 'No Smart Insights report data was provided.'}), 400

    pdf_buffer = build_smart_insights_pdf(payload)
    table_name = pdf_filename(payload.get('tableName') or 'smart_insights')
    mode = pdf_filename(summary.get('mode') or 'report')
    filename = f'{table_name}_{mode}_smart_insights.pdf'
    return send_file(
        pdf_buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )

@handle_app_error
def get_executive_summary():
    """Generate smart executive summary with anomalies and trends."""
    payload = request.get_json(force=True, silent=True) or {}
    insight_mode = normalize_insight_mode(payload.get('insightMode'))

    db_type = request_db_type(payload)
    parsed, error_response = parse_requested_table(payload, db_type)
    if error_response:
        return error_response
    conn_info, table_ref, use_clean = parsed

    try:
        adapter = get_database_adapter(db_type)
        
        with adapter.open_connection(conn_info) as connection:
            cursor = connection.cursor()
            if not table_exists(cursor, table_ref, db_type):
                raise NotFoundError('Selected table was not found.')

            table_sql = table_ref['quoted']
            cursor.execute(f"SELECT COUNT(*) AS total FROM {table_sql}")
            total_rows = extract_row_value(cursor.fetchone(), 0) or 0
            
            if total_rows == 0:
                return jsonify({'warning': 'Table is empty. Cannot generate summary.', 'tableCount': 0})

            columns = load_columns(cursor, table_ref, db_type)
            profile = table_analytics_profile(table_ref['label'], columns, total_rows)
            if not profile['usable']:
                raise ValueError(f"Selected table is not analytics-ready: {profile['reason']}.")
                
            numeric_cols = [c for c in columns if c['DATA_TYPE'] in NUMERIC_TYPES]
            numeric_cols = [c for c in numeric_cols if not is_id_column(c['COLUMN_NAME'])] or numeric_cols
            date_cols = [c for c in columns if c['DATA_TYPE'] in DATE_TYPES]
            text_cols = [c for c in columns if c['DATA_TYPE'] in TEXT_TYPES]

            if not numeric_cols:
                category_profiles = load_category_profile(cursor, table_sql, text_cols[:Config.MAX_TEXT_COLUMNS], 
                                                         total_rows, use_clean, db_type)
                summary = {
                    'keyMetrics': [],
                    'criticalAnomalies': [],
                    'trends': [],
                    'recommendations': [
                        'This table is best analyzed as categorical data. Review category concentration and completeness instead of numeric trends.',
                        'Add a measurable numeric field or date field if forecasting, variance, or anomaly detection is required.'
                    ],
                    'categoryMetrics': category_profiles[:3],
                    'dataQualityScore': profile['score']
                }
                summary = apply_insight_mode(summary, insight_mode, profile, numeric_cols, date_cols, text_cols, [])
                return jsonify({
                    'tableName': table_ref['label'],
                    'tableRef': {'schema': table_ref['schema'], 'name': table_ref['name'], 'label': table_ref['label']},
                    'columnCount': len(columns),
                    'analyzedColumns': 0,
                    'summary': summary,
                    'recommendations': summary.get('recommendations', []),
                    'profile': profile,
                    'detailedAnalysis': []
                })

            analyses: List[Dict[str, Any]] = []
            limit_clause = get_limit_clause(Config.MAX_TABLE_RESULTS, db_type)
            
            for col in numeric_cols[:10]:
                value_sql = numeric_value_sql(col, use_clean, db_type)
                order_clause = ''
                if date_cols:
                    date_sql = quote_identifier(date_cols[0]['COLUMN_NAME'], db_type)
                    order_clause = f" ORDER BY {date_sql}"
                    
                if db_type == 'sqlserver' and not order_clause:
                    cursor.execute(
                        f"SELECT TOP ({Config.MAX_TABLE_RESULTS}) {value_sql} AS analysis_value FROM {table_sql} "
                        f"WHERE {value_sql} IS NOT NULL"
                    )
                else:
                    cursor.execute(
                        f"SELECT {value_sql} AS analysis_value FROM {table_sql} "
                        f"WHERE {value_sql} IS NOT NULL "
                        f"{order_clause} {limit_clause}"
                    )
                values: List[float] = []
                for row in cursor.fetchall():
                    raw_value = extract_row_value(row, 0)
                    if raw_value is None:
                        continue
                    try:
                        values.append(float(raw_value))
                    except (TypeError, ValueError):
                        continue

                if not values or len(values) < Config.MIN_VALUES_FOR_ANOMALY_DETECTION:
                    continue

                stats = {
                    'count': len(values),
                    'min': min(values),
                    'max': max(values),
                    'avg': round(mean(values), 2),
                    'median': round(median(values), 2),
                    'stdDev': round(std_dev(values), 2)
                }
                
                anomalies = []
                if Config.ENABLE_ANOMALY_DETECTION:
                    anomalies = detect_anomalies(values, Config.ANOMALY_Z_SCORE_THRESHOLD)
                    
                anomalies_detailed = analyze_anomalies_detailed(col['COLUMN_NAME'], anomalies, values, stats) if anomalies else []
                
                trend = None
                trend_basis = 'not_available'
                if Config.ENABLE_TREND_ANALYSIS and date_cols:
                    trend = analyze_trend(values)
                    trend_basis = date_cols[0]['COLUMN_NAME']

                insights = generate_insights(col['COLUMN_NAME'], stats, anomalies, trend)
                if not date_cols:
                    insights.append('Trend analysis was skipped because this table has no date/time column; row-order trends would be unreliable.')

                analyses.append({
                    'column': col['COLUMN_NAME'],
                    'stats': stats,
                    'anomalies': anomalies,
                    'anomaliesDetailed': anomalies_detailed,
                    'trend': trend,
                    'trendBasis': trend_basis,
                    'insights': insights
                })

            exec_summary = generate_executive_summary(analyses) if analyses else None
            if not exec_summary:
                exec_summary = {
                    'keyMetrics': [],
                    'criticalAnomalies': [],
                    'trends': [],
                    'recommendations': ['Add numeric columns or more numeric rows for better Smart Insights.'],
                    'dataQualityScore': profile['score'],
                    'narrativeText': 'Unable to analyze trends or anomalies because there is insufficient numeric data.'
                }
            elif 'narrativeText' not in exec_summary:
                exec_summary['narrativeText'] = f'Analyzed {len(analyses)} numeric column(s) across {total_rows} row(s). Review key metrics, trends, and anomalies below.'

            exec_summary = apply_insight_mode(exec_summary, insight_mode, profile, numeric_cols, date_cols, text_cols, analyses)

            return jsonify({
                'tableName': table_ref['label'],
                'tableRef': {'schema': table_ref['schema'], 'name': table_ref['name'], 'label': table_ref['label']},
                'columnCount': len(columns),
                'analyzedColumns': len(analyses),
                'summary': exec_summary,
                'recommendations': exec_summary.get('recommendations', []),
                'profile': profile,
                'keyMetrics': exec_summary.get('keyMetrics', []),
                'criticalAnomalies': exec_summary.get('criticalAnomalies', []),
                'trends': exec_summary.get('trends', []),
                'detailedAnalysis': analyses
            })
    except Exception as error:
        adapter = get_database_adapter(db_type)
        friendly_msg = adapter.friendly_connection_error(error)
        return handle_database_error(error, friendly_msg)

