import re
from typing import Any, Dict, List

from flask import jsonify, request

from analytics_insights import (
    analyze_anomalies_detailed,
    analyze_trend,
    detect_anomalies,
    generate_executive_summary,
    mean,
    median,
    std_dev,
)
from controllers.db_controller import open_connection, rows_to_dicts
from utils.table_filter import filter_sensitive_tables, parse_table_reference, quote_identifier


NUMERIC_TYPES = {
    'int', 'bigint', 'smallint', 'tinyint', 'float', 'real',
    'decimal', 'numeric', 'money', 'smallmoney'
}
DATE_TYPES = {'date', 'datetime', 'datetime2', 'smalldatetime', 'datetimeoffset'}
TEXT_TYPES = {'varchar', 'nvarchar', 'char', 'nchar', 'text', 'ntext'}


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


def parse_requested_table(payload: Dict[str, Any]):
    try:
        table_ref = parse_table_reference(payload.get('tableName', ''))
    except ValueError:
        return None, (jsonify({'error': 'Invalid table name.'}), 400)

    conn_info = payload.get('connInfo')
    if not conn_info or not table_ref['name']:
        return None, (jsonify({'error': 'connInfo and tableName are required.'}), 400)
    if not filter_sensitive_tables([table_ref['label']]):
        return None, (jsonify({'error': 'Access to this table is not allowed.'}), 403)

    return (conn_info, table_ref), None


def get_table_analytics():
    payload = request.get_json(force=True, silent=True) or {}
    parsed, error_response = parse_requested_table(payload)
    if error_response:
        return error_response
    conn_info, table_ref = parsed

    try:
        with open_connection(conn_info) as connection:
            cursor = connection.cursor()
            if not table_exists(cursor, table_ref):
                return jsonify({'error': 'Selected table was not found.'}), 404

            table_sql = table_ref['quoted']
            cursor.execute(f"SELECT COUNT(*) AS total FROM {table_sql}")
            total_rows = cursor.fetchone()[0] or 0

            columns = load_columns(cursor, table_ref)
            cursor.execute(f"SELECT TOP 100 * FROM {table_sql}")
            sample_rows = rows_to_dicts(cursor, cursor.fetchall())

            numeric_cols = [c for c in columns if c['DATA_TYPE'] in NUMERIC_TYPES]
            date_cols = [c for c in columns if c['DATA_TYPE'] in DATE_TYPES]
            text_cols = [c for c in columns if c['DATA_TYPE'] in TEXT_TYPES]

            def is_id_column(name: str) -> bool:
                return re.search(r'(?:^|_)(?:id|rowid|serial)$|id$', name, re.IGNORECASE) is not None

            numeric_analysis_cols = [col for col in numeric_cols if not is_id_column(col['COLUMN_NAME'])]
            numeric_analysis_cols = numeric_analysis_cols if numeric_analysis_cols else numeric_cols

            numeric_stats = []
            for col in numeric_analysis_cols[:6]:
                col_sql = quote_identifier(col['COLUMN_NAME'])
                cursor.execute(
                    f"SELECT "
                    f"MIN({col_sql}) AS min_val, "
                    f"MAX({col_sql}) AS max_val, "
                    f"AVG(CAST({col_sql} AS FLOAT)) AS avg_val, "
                    f"SUM(CAST({col_sql} AS FLOAT)) AS sum_val "
                    f"FROM {table_sql} "
                    f"WHERE {col_sql} IS NOT NULL"
                )
                row = cursor.fetchone()
                numeric_stats.append({
                    'column': col['COLUMN_NAME'],
                    'min': float(row.min_val) if row.min_val is not None else 0,
                    'max': float(row.max_val) if row.max_val is not None else 0,
                    'avg': round(float(row.avg_val), 2) if row.avg_val is not None else 0,
                    'sum': round(float(row.sum_val), 2) if row.sum_val is not None else 0
                })

            column_quality = []
            for col in columns[:30]:
                col_sql = quote_identifier(col['COLUMN_NAME'])
                cursor.execute(f"SELECT COUNT(*) FROM {table_sql} WHERE {col_sql} IS NULL")
                null_count = cursor.fetchone()[0] or 0
                column_quality.append({
                    'column': col['COLUMN_NAME'],
                    'dataType': col['DATA_TYPE'],
                    'nullCount': null_count,
                    'nullPercent': round((null_count / total_rows) * 100, 1) if total_rows else 0
                })

            category_data = None
            if text_cols:
                text_col = text_cols[0]['COLUMN_NAME']
                text_sql = quote_identifier(text_col)
                cursor.execute(
                    f"SELECT TOP 10 {text_sql} AS label, COUNT(*) AS count "
                    f"FROM {table_sql} "
                    f"WHERE {text_sql} IS NOT NULL AND LEN({text_sql}) > 0 "
                    f"GROUP BY {text_sql} "
                    f"ORDER BY count DESC"
                )
                category_data = {
                    'column': text_col,
                    'data': rows_to_dicts(cursor, cursor.fetchall())
                }

            time_series_data = None
            if date_cols and numeric_analysis_cols:
                date_col = date_cols[0]['COLUMN_NAME']
                num_col = numeric_analysis_cols[0]['COLUMN_NAME']
                date_sql = quote_identifier(date_col)
                num_sql = quote_identifier(num_col)
                cursor.execute(
                    f"SELECT TOP 30 CONVERT(VARCHAR(10), {date_sql}, 120) AS period, "
                    f"SUM(CAST({num_sql} AS FLOAT)) AS total "
                    f"FROM {table_sql} "
                    f"WHERE {date_sql} IS NOT NULL "
                    f"GROUP BY CONVERT(VARCHAR(10), {date_sql}, 120) "
                    f"ORDER BY period"
                )
                time_series_data = {
                    'dateColumn': date_col,
                    'valueColumn': num_col,
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
                'columnQuality': column_quality,
                'completenessScore': completeness,
                'sampleRows': sample_rows[:10]
            })
    except Exception as error:
        return jsonify({'error': f'Analytics failed: {str(error)}'}), 500


def get_executive_summary():
    payload = request.get_json(force=True, silent=True) or {}
    parsed, error_response = parse_requested_table(payload)
    if error_response:
        return error_response
    conn_info, table_ref = parsed

    try:
        with open_connection(conn_info) as connection:
            cursor = connection.cursor()
            if not table_exists(cursor, table_ref):
                return jsonify({'error': 'Selected table was not found.'}), 404

            table_sql = table_ref['quoted']
            columns = load_columns(cursor, table_ref)
            numeric_cols = [c for c in columns if c['DATA_TYPE'] in NUMERIC_TYPES]

            if not numeric_cols:
                return jsonify({'summary': None, 'message': 'No numeric columns.'})

            analyses: List[Dict[str, Any]] = []
            for col in numeric_cols[:10]:
                col_sql = quote_identifier(col['COLUMN_NAME'])
                cursor.execute(
                    f"SELECT TOP 1000 {col_sql} FROM {table_sql} "
                    f"WHERE {col_sql} IS NOT NULL"
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

                if not values:
                    continue

                stats = {
                    'count': len(values),
                    'min': min(values),
                    'max': max(values),
                    'avg': round(mean(values), 2),
                    'median': round(median(values), 2),
                    'stdDev': round(std_dev(values), 2)
                }
                anomalies = detect_anomalies(values)
                anomalies_detailed = analyze_anomalies_detailed(col['COLUMN_NAME'], anomalies, values, stats)
                trend = analyze_trend(values)
                analyses.append({
                    'column': col['COLUMN_NAME'],
                    'stats': stats,
                    'anomalies': anomalies,
                    'anomaliesDetailed': anomalies_detailed,
                    'trend': trend
                })

            summary = generate_executive_summary(analyses)
            return jsonify({
                'tableName': table_ref['label'],
                'tableRef': {'schema': table_ref['schema'], 'name': table_ref['name'], 'label': table_ref['label']},
                'columnCount': len(numeric_cols),
                'analyzedColumns': len(analyses),
                'summary': summary,
                'detailedAnalysis': analyses
            })
    except Exception as error:
        return jsonify({'error': 'Failed to generate summary.', 'detail': str(error)}), 500