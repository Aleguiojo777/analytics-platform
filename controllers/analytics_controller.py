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
from utils.table_filter import filter_sensitive_tables, is_table_name_safe, sanitize_table_name


NUMERIC_TYPES = {
    'int', 'bigint', 'smallint', 'tinyint', 'float', 'real',
    'decimal', 'numeric', 'money', 'smallmoney'
}
DATE_TYPES = {'date', 'datetime', 'datetime2', 'smalldatetime', 'datetimeoffset'}
TEXT_TYPES = {'varchar', 'nvarchar', 'char', 'nchar', 'text', 'ntext'}


def get_table_analytics():
    payload = request.get_json(force=True, silent=True) or {}
    conn_info = payload.get('connInfo')
    table_name = sanitize_table_name(payload.get('tableName', ''))

    if not conn_info or not table_name:
        return jsonify({'error': 'connInfo and tableName are required.'}), 400
    if not is_table_name_safe(table_name):
        return jsonify({'error': 'Invalid table name.'}), 400
    if not filter_sensitive_tables([table_name]):
        return jsonify({'error': 'Access to this table is not allowed.'}), 403

    try:
        with open_connection(conn_info) as connection:
            cursor = connection.cursor()
            count_query = f"SELECT COUNT(*) AS total FROM [{table_name}]"
            cursor.execute(count_query)
            total_rows = cursor.fetchone()[0] or 0

            column_query = (
                "SELECT COLUMN_NAME, DATA_TYPE "
                "FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_NAME = ? "
                "ORDER BY ORDINAL_POSITION"
            )
            cursor.execute(column_query, table_name)
            columns = [
                {'COLUMN_NAME': row.COLUMN_NAME, 'DATA_TYPE': row.DATA_TYPE}
                for row in cursor.fetchall()
            ]

            sample_query = f"SELECT TOP 100 * FROM [{table_name}]"
            cursor.execute(sample_query)
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
                stats_query = (
                    f"SELECT "
                    f"MIN([{col['COLUMN_NAME']}]) AS min_val, "
                    f"MAX([{col['COLUMN_NAME']}]) AS max_val, "
                    f"AVG(CAST([{col['COLUMN_NAME']}] AS FLOAT)) AS avg_val, "
                    f"SUM(CAST([{col['COLUMN_NAME']}] AS FLOAT)) AS sum_val "
                    f"FROM [{table_name}] "
                    f"WHERE [{col['COLUMN_NAME']}] IS NOT NULL"
                )
                cursor.execute(stats_query)
                row = cursor.fetchone()
                numeric_stats.append({
                    'column': col['COLUMN_NAME'],
                    'min': float(row.min_val) if row.min_val is not None else 0,
                    'max': float(row.max_val) if row.max_val is not None else 0,
                    'avg': round(float(row.avg_val), 2) if row.avg_val is not None else 0,
                    'sum': round(float(row.sum_val), 2) if row.sum_val is not None else 0
                })

            category_data = None
            if text_cols:
                text_col = text_cols[0]['COLUMN_NAME']
                category_query = (
                    f"SELECT TOP 10 [{text_col}] AS label, COUNT(*) AS count "
                    f"FROM [{table_name}] "
                    f"WHERE [{text_col}] IS NOT NULL AND LEN([{text_col}]) > 0 "
                    f"GROUP BY [{text_col}] "
                    f"ORDER BY count DESC"
                )
                cursor.execute(category_query)
                category_data = {
                    'column': text_col,
                    'data': rows_to_dicts(cursor, cursor.fetchall())
                }

            time_series_data = None
            if date_cols and numeric_analysis_cols:
                date_col = date_cols[0]['COLUMN_NAME']
                num_col = numeric_analysis_cols[0]['COLUMN_NAME']
                time_query = (
                    f"SELECT TOP 30 CONVERT(VARCHAR(10), [{date_col}], 120) AS period, "
                    f"SUM(CAST([{num_col}] AS FLOAT)) AS total "
                    f"FROM [{table_name}] "
                    f"WHERE [{date_col}] IS NOT NULL "
                    f"GROUP BY CONVERT(VARCHAR(10), [{date_col}], 120) "
                    f"ORDER BY period"
                )
                cursor.execute(time_query)
                time_series_data = {
                    'dateColumn': date_col,
                    'valueColumn': num_col,
                    'data': rows_to_dicts(cursor, cursor.fetchall())
                }

            return jsonify({
                'tableName': table_name,
                'totalRows': total_rows,
                'columns': columns,
                'numericStats': numeric_stats,
                'categoryData': category_data,
                'timeSeriesData': time_series_data,
                'sampleRows': sample_rows[:10]
            })
    except Exception as error:
        return jsonify({'error': f'Analytics failed: {str(error)}'}), 500


def get_executive_summary():
    payload = request.get_json(force=True, silent=True) or {}
    conn_info = payload.get('connInfo')
    table_name = sanitize_table_name(payload.get('tableName', ''))

    if not conn_info or not table_name:
        return jsonify({'error': 'connInfo and tableName are required.'}), 400
    if not is_table_name_safe(table_name):
        return jsonify({'error': 'Invalid table name.'}), 400
    if not filter_sensitive_tables([table_name]):
        return jsonify({'error': 'Access denied.'}), 403

    try:
        with open_connection(conn_info) as connection:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT COLUMN_NAME, DATA_TYPE "
                "FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_NAME = ?", table_name
            )
            columns = [
                {'COLUMN_NAME': row.COLUMN_NAME, 'DATA_TYPE': row.DATA_TYPE}
                for row in cursor.fetchall()
            ]

            numeric_cols = [
                c for c in columns if c['DATA_TYPE'] in NUMERIC_TYPES
            ]

            if not numeric_cols:
                return jsonify({'summary': None, 'message': 'No numeric columns.'})

            analyses: List[Dict[str, Any]] = []
            for col in numeric_cols[:10]:
                cursor.execute(
                    f"SELECT TOP 1000 [{col['COLUMN_NAME']}] FROM [{table_name}] "
                    f"WHERE [{col['COLUMN_NAME']}] IS NOT NULL"
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
                'tableName': table_name,
                'columnCount': len(numeric_cols),
                'analyzedColumns': len(analyses),
                'summary': summary,
                'detailedAnalysis': analyses
            })
    except Exception as error:
        return jsonify({'error': 'Failed to generate summary.', 'detail': str(error)}), 500
