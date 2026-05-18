from typing import Any, Dict, List

import pyodbc
from flask import jsonify, request

from services.analytics_insights import (
    analyze_anomalies_detailed,
    analyze_trend,
    detect_anomalies,
    generate_executive_summary,
    mean,
    median,
    std_dev,
)
from controllers.db_controller import open_connection, rows_to_dicts
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



def table_exists(cursor, table_ref: Dict[str, str]) -> bool:
    cursor.execute(
        "SELECT 1 FROM INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_TYPE = 'BASE TABLE' AND TABLE_SCHEMA = ? AND TABLE_NAME = ?",
        table_ref['schema'],
        table_ref['name']
    )
    return cursor.fetchone() is not None


def load_columns(cursor, table_ref: Dict[str, str]) -> List[Dict[str, Any]]:
    cursor.execute(
        "SELECT COLUMN_NAME, DATA_TYPE "
        "FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? "
        "ORDER BY ORDINAL_POSITION",
        table_ref['schema'],
        table_ref['name']
    )
    return [
        {'COLUMN_NAME': row.COLUMN_NAME, 'DATA_TYPE': row.DATA_TYPE}
        for row in cursor.fetchall()
    ]


def text_value_sql(column_sql: str, data_type: str) -> str:
    if str(data_type or '').lower() in ('text', 'ntext'):
        return f"CAST({column_sql} AS NVARCHAR(4000))"
    return column_sql


def _clean_text_expr(col_sql: str) -> str:
    # Safe cleansing for analytics-only: trim + empty string => NULL
    return f"NULLIF(LTRIM(RTRIM({col_sql})), '')"


def _clean_numeric_expr(col_sql: str) -> str:
    # Safe numeric cleansing for analytics-only: TRY_CONVERT to FLOAT
    return f"TRY_CONVERT(FLOAT, {col_sql})"


def analytics_value_sql(col: Dict[str, Any], cleaned_mode: bool) -> str:
    col_sql = quote_identifier(col['COLUMN_NAME'])
    dtype = str(col.get('DATA_TYPE') or '').lower()
    if cleaned_mode and dtype in TEXT_TYPES:
        return _clean_text_expr(text_value_sql(col_sql, dtype))
    if cleaned_mode and dtype in NUMERIC_TYPES:
        return _clean_numeric_expr(col_sql)
    if dtype in ('text', 'ntext'):
        return text_value_sql(col_sql, dtype)
    return col_sql


def numeric_value_sql(col: Dict[str, Any], cleaned_mode: bool) -> str:
    col_sql = quote_identifier(col['COLUMN_NAME'])
    if cleaned_mode:
        return _clean_numeric_expr(col_sql)
    return f"CAST({col_sql} AS FLOAT)"


def load_category_profile(cursor, table_sql: str, text_cols: List[Dict[str, Any]], total_rows: int, cleaned_mode: bool = False) -> List[Dict[str, Any]]:
    profiles: List[Dict[str, Any]] = []
    for col in text_cols[:8]:
        col_name = col['COLUMN_NAME']
        value_sql = analytics_value_sql(col, cleaned_mode)
        cursor.execute(
            f"SELECT COUNT(DISTINCT {value_sql}) AS distinct_count, COUNT({value_sql}) AS filled_count "
            f"FROM {table_sql} "
            f"WHERE {value_sql} IS NOT NULL AND LEN({value_sql}) > 0"
        )
        row = cursor.fetchone()
        distinct_count = int(row.distinct_count or 0)
        filled_count = int(row.filled_count or 0)
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

def parse_requested_table(payload: Dict[str, Any]):
    """Parse and validate table request payload."""
    try:
        conn_info, table_name, cleaned_mode = validate_table_request(payload)
    except ValidatorError as e:
        return None, (jsonify({'error': e.message}), 400)
    
    try:
        table_ref = parse_table_reference(table_name)
    except ValueError as e:
        return None, (jsonify({'error': str(e)}), 400)

    if not filter_sensitive_tables([table_ref['label']]):
        raise ForbiddenError('Access to this table is not allowed.')

    return (conn_info, table_ref, cleaned_mode), None




@handle_app_error
def get_table_analytics():
    """Retrieve comprehensive analytics for a specific table."""
    payload = request.get_json(force=True, silent=True) or {}
    parsed, error_response = parse_requested_table(payload)
    if error_response:
        return error_response
    conn_info, table_ref, use_clean = parsed

    try:
        with open_connection(conn_info) as connection:
            cursor = connection.cursor()
            if not table_exists(cursor, table_ref):
                raise NotFoundError('Selected table was not found.')

            table_sql = table_ref['quoted']
            cursor.execute(f"SELECT COUNT(*) AS total FROM {table_sql}")
            total_rows = cursor.fetchone()[0] or 0
            
            if total_rows == 0:
                return jsonify({'warning': 'Table is empty. Analytics will be limited.', 'totalRows': 0})

            columns = load_columns(cursor, table_ref)
            if not columns:
                raise ValueError('Table has no columns.')
            
            cursor.execute(f"SELECT TOP {Config.MAX_SAMPLE_ROWS} * FROM {table_sql}")
            sample_rows = rows_to_dicts(cursor, cursor.fetchall())
            
            # Cleaned analytics mode (preview): derive cleaned values in SELECT without modifying base tables
            cleaned_sample_rows = sample_rows

            if use_clean and Config.ENABLE_CLEANED_MODE:
                select_exprs = []
                for c in columns:
                    col_sql = quote_identifier(c['COLUMN_NAME'])
                    value_sql = analytics_value_sql(c, use_clean)
                    select_exprs.append(f"{value_sql} AS {col_sql}" if value_sql != col_sql else col_sql)

                cursor.execute(f"SELECT TOP {Config.MAX_SAMPLE_ROWS} {', '.join(select_exprs)} FROM {table_sql}")
                cleaned_sample_rows = rows_to_dicts(cursor, cursor.fetchall())

            profile = table_analytics_profile(table_ref['label'], columns, total_rows)
            if not profile['usable']:
                raise ValueError(f"Selected table is not analytics-ready: {profile['reason']}.")

            numeric_cols = [c for c in columns if c['DATA_TYPE'] in NUMERIC_TYPES]
            date_cols = [c for c in columns if c['DATA_TYPE'] in DATE_TYPES]
            text_cols = [c for c in columns if c['DATA_TYPE'] in TEXT_TYPES]

            numeric_analysis_cols = [col for col in numeric_cols if not is_id_column(col['COLUMN_NAME'])]
            numeric_analysis_cols = numeric_analysis_cols if numeric_analysis_cols else numeric_cols

            numeric_stats = []
            for col in numeric_analysis_cols[:Config.MAX_NUMERIC_COLUMNS]:
                value_sql = numeric_value_sql(col, use_clean)
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
                    numeric_stats.append({
                        'column': col['COLUMN_NAME'],
                        'min': float(row.min_val) if row.min_val is not None else 0,
                        'max': float(row.max_val) if row.max_val is not None else 0,
                        'avg': round(float(row.avg_val), 2) if row.avg_val is not None else 0,
                        'sum': round(float(row.sum_val), 2) if row.sum_val is not None else 0
                    })

            column_quality = []
            for col in columns[:30]:
                value_sql = analytics_value_sql(col, use_clean)
                cursor.execute(f"SELECT COUNT(*) FROM {table_sql} WHERE {value_sql} IS NULL")
                null_count = cursor.fetchone()[0] or 0
                column_quality.append({
                    'column': col['COLUMN_NAME'],
                    'dataType': col['DATA_TYPE'],
                    'nullCount': null_count,
                    'nullPercent': round((null_count / total_rows) * 100, 1) if total_rows else 0
                })

            category_data = None
            category_profiles = load_category_profile(cursor, table_sql, text_cols[:Config.MAX_TEXT_COLUMNS], total_rows, use_clean)
            if category_profiles:
                text_col = category_profiles[0]['column']
                text_col_meta = next((col for col in text_cols if col['COLUMN_NAME'] == text_col), None)
                value_sql = analytics_value_sql(text_col_meta, use_clean) if text_col_meta else quote_identifier(text_col)
                cursor.execute(
                    f"SELECT TOP 10 {value_sql} AS label, COUNT(*) AS item_count "
                    f"FROM {table_sql} "
                    f"WHERE {value_sql} IS NOT NULL AND LEN({value_sql}) > 0 "
                    f"GROUP BY {value_sql} "
                    f"ORDER BY item_count DESC"
                )
                category_data = {
                    'column': text_col,
                    'profile': category_profiles[0],
                    'data': rows_to_dicts(cursor, cursor.fetchall())
                }

            time_series_data = None
            if date_cols and numeric_analysis_cols:
                date_col = date_cols[0]['COLUMN_NAME']
                date_sql = quote_identifier(date_col)
                num_col_meta = numeric_analysis_cols[0]
                num_sql = numeric_value_sql(num_col_meta, use_clean)
                cursor.execute(
                    f"SELECT TOP 30 CONVERT(VARCHAR(10), {date_sql}, 120) AS period, "
                    f"SUM({num_sql}) AS total "
                    f"FROM {table_sql} "
                    f"WHERE {date_sql} IS NOT NULL AND {num_sql} IS NOT NULL "
                    f"GROUP BY CONVERT(VARCHAR(10), {date_sql}, 120) "
                    f"ORDER BY period"
                )
                time_series_data = {
                    'dateColumn': date_col,
                    'valueColumn': num_col_meta['COLUMN_NAME'],
                    'data': rows_to_dicts(cursor, cursor.fetchall())
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
    except pyodbc.Error as error:
        return handle_database_error(error)


@handle_app_error
def get_executive_summary():
    """Generate AI-powered executive summary with anomalies and trends."""
    payload = request.get_json(force=True, silent=True) or {}

    parsed, error_response = parse_requested_table(payload)
    if error_response:
        return error_response
    conn_info, table_ref, use_clean = parsed

    try:
        with open_connection(conn_info) as connection:
            cursor = connection.cursor()
            if not table_exists(cursor, table_ref):
                raise NotFoundError('Selected table was not found.')

            table_sql = table_ref['quoted']
            cursor.execute(f"SELECT COUNT(*) AS total FROM {table_sql}")
            total_rows = cursor.fetchone()[0] or 0
            
            if total_rows == 0:
                return jsonify({'warning': 'Table is empty. Cannot generate summary.', 'tableCount': 0})

            columns = load_columns(cursor, table_ref)
            profile = table_analytics_profile(table_ref['label'], columns, total_rows)
            if not profile['usable']:
                raise ValueError(f"Selected table is not analytics-ready: {profile['reason']}.")
                
            numeric_cols = [c for c in columns if c['DATA_TYPE'] in NUMERIC_TYPES]
            numeric_cols = [c for c in numeric_cols if not is_id_column(c['COLUMN_NAME'])] or numeric_cols
            date_cols = [c for c in columns if c['DATA_TYPE'] in DATE_TYPES]
            text_cols = [c for c in columns if c['DATA_TYPE'] in TEXT_TYPES]

            if not numeric_cols:
                category_profiles = load_category_profile(cursor, table_sql, text_cols[:Config.MAX_TEXT_COLUMNS], total_rows, use_clean)
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
                return jsonify({
                    'tableName': table_ref['label'],
                    'tableRef': {'schema': table_ref['schema'], 'name': table_ref['name'], 'label': table_ref['label']},
                    'columnCount': 0,
                    'analyzedColumns': 0,
                    'summary': summary,
                    'profile': profile,
                    'detailedAnalysis': []
                })

            analyses: List[Dict[str, Any]] = []
            for col in numeric_cols[:10]:
                value_sql = numeric_value_sql(col, use_clean)
                order_clause = ''
                if date_cols:
                    date_sql = quote_identifier(date_cols[0]['COLUMN_NAME'])
                    order_clause = f" ORDER BY {date_sql}"
                    
                cursor.execute(
                    f"SELECT TOP {Config.MAX_TABLE_RESULTS} {value_sql} AS analysis_value FROM {table_sql} "
                    f"WHERE {value_sql} IS NOT NULL"
                    f"{order_clause}"
                )
                values: List[float] = []
                for row in cursor.fetchall():
                    raw_value = row[0]
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
                if Config.ENABLE_TREND_ANALYSIS:
                    trend = analyze_trend(values)
                    
                analyses.append({
                    'column': col['COLUMN_NAME'],
                    'stats': stats,
                    'anomalies': anomalies,
                    'anomaliesDetailed': anomalies_detailed,
                    'trend': trend
                })

            key_metrics = [a for a in analyses if a['anomalies']][:3]
            critical_anomalies = [a['anomaliesDetailed'] for a in analyses if a['anomaliesDetailed']]
            critical_anomalies = [item for sublist in critical_anomalies for item in sublist][:5]
            trends = [a['trend'] for a in analyses if a['trend']][:3]

            exec_summary = generate_executive_summary(analyses) if analyses else {
                'summary': 'Unable to analyze - insufficient numeric data.',
                'recommendations': ['Add numeric columns for better analysis.']
            }

            return jsonify({
                'tableName': table_ref['label'],
                'tableRef': {'schema': table_ref['schema'], 'name': table_ref['name'], 'label': table_ref['label']},
                'columnCount': len(columns),
                'analyzedColumns': len(analyses),
                'summary': exec_summary.get('summary', 'Analysis complete.'),
                'recommendations': exec_summary.get('recommendations', []),
                'profile': profile,
                'keyMetrics': key_metrics,
                'criticalAnomalies': critical_anomalies,
                'trends': trends,
                'detailedAnalysis': analyses
            })
    except pyodbc.Error as error:
        return handle_database_error(error)

