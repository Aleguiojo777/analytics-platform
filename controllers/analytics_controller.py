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

def load_category_profile(cursor, table_sql: str, text_cols: List[Dict[str, Any]], total_rows: int) -> List[Dict[str, Any]]:
    profiles: List[Dict[str, Any]] = []
    for col in text_cols[:8]:
        col_name = col['COLUMN_NAME']
        col_sql = quote_identifier(col_name)
        value_sql = text_value_sql(col_sql, col.get('DATA_TYPE'))
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


def _clean_text_expr(col_sql: str) -> str:
    # Safe cleansing for analytics-only: trim + empty string => NULL
    return f"NULLIF(LTRIM(RTRIM({col_sql})), '')"


def _clean_numeric_expr(col_sql: str) -> str:
    # Safe numeric cleansing for analytics-only: TRY_CONVERT to FLOAT
    return f"TRY_CONVERT(FLOAT, {col_sql})"


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
            
            # Cleaned analytics mode (preview): derive cleaned values in SELECT without modifying base tables
            # Text columns: trim and convert empty string to NULL
            # Numeric columns: TRY_CONVERT to FLOAT to avoid cast failures
            use_clean = bool(payload.get('cleanedMode'))
            cleaned_sample_rows = sample_rows

            if use_clean:
                sample_cols = [c['COLUMN_NAME'] for c in columns]
                select_exprs = []
                for c in columns:
                    col_sql = quote_identifier(c['COLUMN_NAME'])
                    dtype = str(c.get('DATA_TYPE') or '').lower()
                    if dtype in ('varchar', 'nvarchar', 'char', 'nchar', 'text', 'ntext'):
                        select_exprs.append(f"{_clean_text_expr(col_sql)} AS {col_sql}")
                    elif dtype in NUMERIC_TYPES:
                        select_exprs.append(f"{_clean_numeric_expr(col_sql)} AS {col_sql}")
                    else:
                        select_exprs.append(col_sql)

                cursor.execute(f"SELECT TOP 100 {', '.join(select_exprs)} FROM {table_sql}")
                cleaned_sample_rows = rows_to_dicts(cursor, cursor.fetchall())

            profile = table_analytics_profile(table_ref['label'], columns, total_rows)
            if not profile['usable']:
                return jsonify({'error': f"Selected table is not analytics-ready: {profile['reason']}."}), 422

            numeric_cols = [c for c in columns if c['DATA_TYPE'] in NUMERIC_TYPES]
            date_cols = [c for c in columns if c['DATA_TYPE'] in DATE_TYPES]
            text_cols = [c for c in columns if c['DATA_TYPE'] in TEXT_TYPES]

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
            category_profiles = load_category_profile(cursor, table_sql, text_cols, total_rows)
            if category_profiles:
                text_col = category_profiles[0]['column']
                text_type = next((col['DATA_TYPE'] for col in text_cols if col['COLUMN_NAME'] == text_col), '')
                text_sql = quote_identifier(text_col)
                value_sql = text_value_sql(text_sql, text_type)
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
                'categoryProfiles': category_profiles,
                'columnQuality': column_quality,
                'completenessScore': completeness,
                'profile': profile,
                'sampleRows': sample_rows[:10]
            })
    except Exception as error:
        return jsonify({'error': f'Analytics failed: {str(error)}'}), 500


def get_executive_summary():
    payload = request.get_json(force=True, silent=True) or {}
    use_clean = bool(payload.get('cleanedMode'))

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
            profile = table_analytics_profile(table_ref['label'], columns, total_rows)
            if not profile['usable']:
                return jsonify({'error': f"Selected table is not analytics-ready: {profile['reason']}."}), 422
            numeric_cols = [c for c in columns if c['DATA_TYPE'] in NUMERIC_TYPES]
            numeric_cols = [c for c in numeric_cols if not is_id_column(c['COLUMN_NAME'])] or numeric_cols
            date_cols = [c for c in columns if c['DATA_TYPE'] in DATE_TYPES]
            text_cols = [c for c in columns if c['DATA_TYPE'] in TEXT_TYPES]

            if not numeric_cols:
                category_profiles = load_category_profile(cursor, table_sql, text_cols, total_rows)
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
                col_sql = quote_identifier(col['COLUMN_NAME'])
                order_clause = ''
                if date_cols:
                    date_sql = quote_identifier(date_cols[0]['COLUMN_NAME'])
                    order_clause = f" ORDER BY {date_sql}"
                cursor.execute(
                    f"SELECT TOP 1000 {col_sql} FROM {table_sql} "
                    f"WHERE {col_sql} IS NOT NULL"
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

            # Rule-based “LLM by scratch” narrative (deterministic text generation; no external model)
            if summary is not None:
                narrative_lines: List[str] = []
                dq = summary.get('dataQualityScore')
                if dq is not None:
                    narrative_lines.append(f"Data quality score is {dq}% based on anomaly rate and severity.")

                key = summary.get('keyMetrics') or []
                if key:
                    top = key[0]
                    narrative_lines.append(
                        f"Most variable metric: {top.get('column')} has an average of {top.get('value')} "
                        f"(range {top.get('range')}, variation {top.get('variation')})."
                    )

                critical = summary.get('criticalAnomalies') or []
                if critical:
                    top_anom = critical[0]
                    narrative_lines.append(
                        f"Suspicious areas detected: {top_anom.get('column')} shows {top_anom.get('count')} critical anomalies. "
                        "Review the detailed column analysis for likely causes and validation checks."
                    )
                else:
                    narrative_lines.append("No critical anomalies detected; focus on moderate outliers and trend changes if present.")

                trends = summary.get('trends') or []
                if trends:
                    t = trends[0]
                    direction = t.get('direction')
                    narrative_lines.append(
                        f"Trend signal: {t.get('column')} is trending {direction} (strength: {t.get('strength')}, confidence: {t.get('confidence')}). "
                        "Confirm the drivers in the time context and operational events."
                    )

                recs = summary.get('recommendations') or []
                if recs:
                    narrative_lines.append("Next recommended actions:")
                    for r in recs[:4]:
                        narrative_lines.append(f"- {r}")

                summary['narrativeText'] = "\n".join(narrative_lines)

            return jsonify({

                'tableName': table_ref['label'],
                'tableRef': {'schema': table_ref['schema'], 'name': table_ref['name'], 'label': table_ref['label']},
                'columnCount': len(numeric_cols),
                'analyzedColumns': len(analyses),
                'summary': summary,
                'profile': profile,
                'detailedAnalysis': analyses
            })
    except Exception as error:
        return jsonify({'error': 'Failed to generate summary.', 'detail': str(error)}), 500