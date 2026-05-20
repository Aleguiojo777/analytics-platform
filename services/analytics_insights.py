import math
from typing import Any, Dict, List, Optional

# Deterministic analytics calculations and minimal factual fallback text.
# Local LLM wording is handled in services/local_llm.py.


def mean(arr: List[float]) -> float:
    """Calculate arithmetic mean."""
    return sum(arr) / len(arr) if arr else 0


def median(arr: List[float]) -> float:
    """Calculate median."""
    sorted_arr = sorted(arr)
    n = len(sorted_arr)
    if n == 0:
        return 0
    if n % 2 == 1:
        return sorted_arr[n // 2]
    return (sorted_arr[n // 2 - 1] + sorted_arr[n // 2]) / 2


def std_dev(arr: List[float]) -> float:
    """Calculate population standard deviation."""
    if not arr:
        return 0
    avg = mean(arr)
    variance = sum((x - avg) ** 2 for x in arr) / len(arr)
    return math.sqrt(variance)


def min_val(arr: List[float]) -> float:
    """Get minimum value."""
    return min(arr) if arr else 0


def max_val(arr: List[float]) -> float:
    """Get maximum value."""
    return max(arr) if arr else 0


def detect_anomalies(values: List[float], threshold: float = 2.5) -> List[Dict[str, Any]]:
    """Detect anomalies using z-score."""
    if len(values) < 4:
        return []

    avg = mean(values)
    std = std_dev(values)
    if std == 0:
        return []

    anomalies = []
    for idx, val in enumerate(values):
        z_score = abs((val - avg) / std)
        if z_score > threshold:
            deviation_pct = abs((val - avg) / avg * 100) if avg != 0 else 0
            anomalies.append({
                'value': round(val, 2),
                'index': idx,
                'zScore': round(z_score, 2),
                'type': 'high' if val > avg else 'low',
                'deviationPercent': round(deviation_pct, 1),
                'expectedRange': f"{round(avg - std, 2)} to {round(avg + std, 2)}",
                'severity': 'critical' if z_score > 4 else 'high' if z_score > 3 else 'moderate'
            })

    return anomalies


def analyze_trend(values: List[float]) -> Optional[Dict[str, Any]]:
    """Analyze linear trend in ordered values."""
    if len(values) < 2:
        return None

    n = len(values)
    x_mean = (n - 1) / 2
    y_mean = mean(values)

    numerator = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    if denominator == 0:
        return None

    slope = numerator / denominator
    intercept = y_mean - slope * x_mean
    predictions = [slope * i + intercept for i in range(n)]

    ss_res = sum((values[i] - predictions[i]) ** 2 for i in range(n))
    ss_tot = sum((val - y_mean) ** 2 for val in values)
    r_squared = 0 if ss_tot == 0 else 1 - (ss_res / ss_tot)

    trend = 'stable'
    if abs(slope) > 0.01:
        trend = 'upward' if slope > 0 else 'downward'

    strength = 'weak'
    if r_squared > 0.7:
        strength = 'strong'
    elif r_squared > 0.4:
        strength = 'moderate'

    return {
        'trend': trend,
        'slope': round(slope, 4),
        'strength': strength,
        'confidence': round(r_squared * 100, 1),
        'prediction': slope * n + intercept
    }


def generate_insights(column: str, stats: Dict[str, float], anomalies: List[Dict], trend: Optional[Dict]) -> List[str]:
    """Return minimal computed fact strings for fallback and LLM context."""
    insights = []
    variation = ((stats['max'] - stats['min']) / max(abs(stats['avg']), 1)) * 100
    insights.append(f"{column}: variation {variation:.1f}% across {stats['count']} analyzed values.")

    if anomalies:
        pct = (len(anomalies) / stats['count']) * 100 if stats.get('count') else 0
        insights.append(f"{column}: {len(anomalies)} anomaly value(s), {pct:.1f}% of analyzed values.")

    if trend:
        insights.append(
            f"{column}: trend {trend['trend']} with {trend['strength']} strength and {trend['confidence']}% confidence."
        )

    return insights


def analyze_anomalies_detailed(column: str, anomalies: List[Dict], values: List[float], stats: Dict[str, float]) -> List[Dict[str, Any]]:
    """Build structured anomaly facts. Ollama supplies explanatory guidance."""
    detailed_anomalies = []

    for anomaly in anomalies:
        idx = anomaly['index']
        context_start = max(0, idx - 2)
        context_end = min(len(values), idx + 3)
        surrounding_values = values[context_start:context_end]
        context_avg = mean(surrounding_values) if surrounding_values else 0
        before = values[idx - 1] if idx > 0 else None
        after = values[idx + 1] if idx + 1 < len(values) else None
        local_direction = 'flat'
        if before is not None and after is not None:
            if after > before:
                local_direction = 'upward'
            elif after < before:
                local_direction = 'downward'

        detailed_anomalies.append({
            'rowIndex': idx,
            'actualValue': anomaly['value'],
            'expectedRange': anomaly['expectedRange'],
            'deviation': f"{anomaly['deviationPercent']:.1f}% from average",
            'zScore': anomaly['zScore'],
            'severity': anomaly['severity'],
            'type': anomaly['type'],
            'recommendations': [],
            'metricContext': 'numeric metric',
            'likelyCauses': [],
            'validationChecks': [],
            'fixSteps': [],
            'businessQuestions': [],
            'decisionGuide': [],
            'impact': (
                f"{column} value {anomaly['value']} is {anomaly['deviationPercent']:.1f}% from "
                f"the average and outside expected range {anomaly['expectedRange']}."
            ),
            'surroundingAverage': round(context_avg, 2),
            'context': {
                'windowStartRow': context_start + 1,
                'windowEndRow': context_end,
                'previousValue': round(before, 2) if before is not None else None,
                'nextValue': round(after, 2) if after is not None else None,
                'localDirection': local_direction
            }
        })

    return detailed_anomalies


def generate_executive_summary(numeric_stats: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Generate structured summary metrics and minimal factual fallback text."""
    if not numeric_stats:
        return None

    summary = {
        'keyMetrics': [],
        'criticalAnomalies': [],
        'anomalyDetails': [],
        'trends': [],
        'recommendations': [],
        'dataQualityScore': 0,
        'keyObservations': [],
        'narrativeText': ''
    }

    sorted_stats = sorted(
        numeric_stats,
        key=lambda x: x['stats']['max'] - x['stats']['min'],
        reverse=True
    )

    for item in sorted_stats[:3]:
        variation_pct = ((item['stats']['max'] - item['stats']['min']) / max(abs(item['stats']['avg']), 1)) * 100
        summary['keyMetrics'].append({
            'column': item['column'],
            'value': round(item['stats']['avg'], 2),
            'range': f"{item['stats']['min']} to {item['stats']['max']}",
            'variation': f"{variation_pct:.1f}%"
        })

    total_anomalies = 0
    critical_count = 0
    for item in numeric_stats:
        anomalies = item.get('anomalies') or []
        if anomalies:
            summary['criticalAnomalies'].append({'column': item['column'], 'count': len(anomalies)})
            total_anomalies += len(anomalies)

        for anomaly_detail in item.get('anomaliesDetailed') or []:
            if anomaly_detail['severity'] == 'critical':
                critical_count += 1
            summary['anomalyDetails'].append({'column': item['column'], **anomaly_detail})

    for item in numeric_stats:
        trend = item.get('trend')
        if trend and trend['trend'] in ['upward', 'downward']:
            summary['trends'].append({
                'column': item['column'],
                'direction': trend['trend'],
                'strength': trend['strength'],
                'confidence': f"{trend['confidence']}%",
                'predictedNextValue': round(trend['prediction'], 2)
            })

    total_values = sum(item['stats'].get('count', 0) for item in numeric_stats)
    anomaly_rate = (total_anomalies / total_values) * 100 if total_values else 0
    anomaly_ratio = total_anomalies / total_values if total_values else 0
    summary['dataQualityScore'] = round(max(0, 100 - (anomaly_ratio * 100) - (critical_count * 10)), 1)

    if summary['keyMetrics']:
        lead_metric = summary['keyMetrics'][0]
        summary['keyObservations'].append(
            f"{lead_metric['column']}: range {lead_metric['range']}, variation {lead_metric['variation']}."
        )

    summary['keyObservations'].append(
        f"Anomaly count: {total_anomalies} of {total_values} analyzed numeric values ({anomaly_rate:.1f}%)."
    )

    if summary['trends']:
        trend_columns = ', '.join(f"{item['column']} ({item['direction']})" for item in summary['trends'][:3])
        summary['keyObservations'].append(f"Trend columns: {trend_columns}.")

    summary['recommendations'] = []
    summary['narrativeText'] = ' '.join(summary['keyObservations'])
    return summary


def analyze_numeric_column(values: List[float], column_name: str) -> Dict[str, Any]:
    """Complete deterministic analysis of a numeric column."""
    if not values:
        return {}

    stats = {
        'count': len(values),
        'min': min_val(values),
        'max': max_val(values),
        'avg': mean(values),
        'median': median(values),
        'stdDev': std_dev(values)
    }
    anomalies = detect_anomalies(values)
    anomalies_detailed = analyze_anomalies_detailed(column_name, anomalies, values, stats)
    trend = analyze_trend(values)
    insights = generate_insights(column_name, stats, anomalies, trend)

    return {
        'column': column_name,
        'stats': stats,
        'anomalies': anomalies,
        'anomaliesDetailed': anomalies_detailed,
        'trend': trend,
        'insights': insights
    }