import math
from typing import List, Dict, Any, Optional, Tuple

# ── AI INSIGHTS FUNCTIONS ──────────────────────────────────────────

# Simple statistics helpers
def mean(arr: List[float]) -> float:
    """Calculate arithmetic mean of array"""
    return sum(arr) / len(arr) if arr else 0

def median(arr: List[float]) -> float:
    """Calculate median of array"""
    sorted_arr = sorted(arr)
    n = len(sorted_arr)
    if n % 2 == 1:
        return sorted_arr[n // 2]
    else:
        return (sorted_arr[n // 2 - 1] + sorted_arr[n // 2]) / 2

def std_dev(arr: List[float]) -> float:
    """Calculate standard deviation of array"""
    if not arr:
        return 0
    avg = mean(arr)
    variance = sum((x - avg) ** 2 for x in arr) / len(arr)
    return math.sqrt(variance)

def min_val(arr: List[float]) -> float:
    """Get minimum value from array"""
    return min(arr) if arr else 0

def max_val(arr: List[float]) -> float:
    """Get maximum value from array"""
    return max(arr) if arr else 0

# Anomaly Detection
def detect_anomalies(values: List[float], threshold: float = 2.5) -> List[Dict[str, Any]]:
    """Detect anomalies using Z-score method with detailed information"""
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
            # Determine if outlier is high or low
            anomaly_type = 'high' if val > avg else 'low'
            deviation_pct = abs((val - avg) / avg * 100) if avg != 0 else 0
            
            anomalies.append({
                'value': round(val, 2),
                'index': idx,
                'zScore': round(z_score, 2),
                'type': anomaly_type,
                'deviationPercent': round(deviation_pct, 1),
                'expectedRange': f"{round(avg - std, 2)} to {round(avg + std, 2)}",
                'severity': 'critical' if z_score > 4 else 'high' if z_score > 3 else 'moderate'
            })
    
    return anomalies

# Linear Trend Analysis
def analyze_trend(values: List[float]) -> Optional[Dict[str, Any]]:
    """Analyze linear trend in values"""
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
    
    if ss_tot == 0:
        r_squared = 0
    else:
        r_squared = 1 - (ss_res / ss_tot)
    
    trend = 'stable'
    strength = 'weak'
    
    if abs(slope) > 0.01:
        trend = 'upward' if slope > 0 else 'downward'
    
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

# Generate Insights
def generate_insights(column: str, stats: Dict[str, float], anomalies: List[Dict], trend: Optional[Dict]) -> List[str]:
    """Generate human-readable insights from statistics"""
    insights = []
    
    variation = ((stats['max'] - stats['min']) / max(abs(stats['avg']), 1)) * 100
    
    if variation > 100:
        insights.append(f"⚠️ {column}: High variability detected ({variation:.1f}% range). Data may need normalization or investigation.")
    elif variation < 20:
        insights.append(f"✓ {column}: Stable with low variability ({variation:.1f}% range). Data quality is consistent.")
    else:
        insights.append(f"→ {column}: Moderate variability ({variation:.1f}% range).")
    
    if anomalies:
        pct = (len(anomalies) / stats['count']) * 100
        insights.append(f"⚠️ {len(anomalies)} anomalies detected ({pct:.1f}% of data) - see detailed analysis below.")
    
    if trend:
        if trend['trend'] == 'upward':
            insights.append(f"📈 Upward trend detected ({trend['strength']} confidence: {trend['confidence']}%). Monitor for continued growth.")
        elif trend['trend'] == 'downward':
            insights.append(f"📉 Downward trend detected ({trend['strength']} confidence: {trend['confidence']}%). Investigate root causes.")
        else:
            insights.append("→ Stable trend over time. No significant directional change detected.")
    
    return insights


# Generate Detailed Anomaly Analysis
def anomaly_action_plan(column: str, anomaly: Dict[str, Any], stats: Dict[str, float], context_avg: float, local_direction: str) -> Dict[str, Any]:
    severity = anomaly['severity']
    anomaly_type = anomaly['type']
    value = anomaly['value']
    avg = stats.get('avg', 0)
    std = stats.get('stdDev', 0)

    likely_causes = []
    validation_checks = []
    fix_steps = []
    business_questions = []

    if anomaly_type == 'high':
        likely_causes.extend([
            'One-time spike caused by a large transaction, batch upload, promotion, or duplicate entry.',
            'Unit mismatch such as cents vs pesos, quantity vs amount, or daily value mixed with monthly value.'
        ])
        business_questions.extend([
            f'What event or process produced the unusually high {column} value?',
            'Are there duplicate rows, repeated imports, or aggregated rows mixed with raw rows?'
        ])
    else:
        likely_causes.extend([
            'Missing or partial transaction recorded as zero/near-zero instead of null.',
            'Cancellation, refund, downtime, stock-out, or failed process causing an unusual drop.'
        ])
        business_questions.extend([
            f'Was there an outage, cancellation, refund, or incomplete record when {column} dropped?',
            'Should this value be excluded, corrected, or kept as a valid business exception?'
        ])

    if severity == 'critical':
        validation_checks.extend([
            'Confirm the source row against the original system or transaction record before using it in reports.',
            'Check whether the value has the correct decimal placement, currency/unit, and sign.',
            'Look for duplicate records with the same date, customer, invoice, product, or reference number.'
        ])
        fix_steps.extend([
            'If it is a data entry or import error, correct it in the source system and reload the table.',
            'If it is legitimate but rare, keep it and add a business note so future reports explain the spike/drop.',
            'If it is not trustworthy yet, temporarily exclude it from KPI calculations with a documented filter.'
        ])
    elif severity == 'high':
        validation_checks.extend([
            'Compare the row with nearby records and records in the same category/date group.',
            'Check whether the value came from a manual edit, late posting, or backfilled batch.'
        ])
        fix_steps.extend([
            'Tag the row for review and decide whether it should be corrected, excluded, or explained.',
            'Add validation rules for allowed ranges if similar anomalies keep appearing.'
        ])
    else:
        validation_checks.extend([
            'Review the row context and monitor whether similar values appear again.',
            'Compare against recent average, median, and expected business range.'
        ])
        fix_steps.extend([
            'Keep the value if it matches a real business event.',
            'Create an alert threshold if this is an early warning signal.'
        ])

    if std and abs(context_avg - avg) > std:
        likely_causes.append('Nearby values are also unusual, so this may be a cluster or period-level issue rather than a single bad row.')
        validation_checks.append('Inspect the surrounding rows as a group, especially same date range or import batch.')
    else:
        likely_causes.append('Nearby values look more normal, so this is more likely an isolated row-level issue.')

    if local_direction != 'flat':
        business_questions.append(f'Does the surrounding sequence show a real {local_direction} movement or a data loading artifact?')

    return {
        'likelyCauses': likely_causes,
        'validationChecks': validation_checks,
        'fixSteps': fix_steps,
        'businessQuestions': business_questions,
        'decisionGuide': [
            'Correct it if the source value is wrong.',
            'Keep it if the business event is real and explainable.',
            'Exclude it only when it is confirmed bad data or would distort a specific KPI.'
        ],
        'impact': f"This value is {anomaly['deviationPercent']:.1f}% away from the average of {round(avg, 2)} and falls outside the expected range {anomaly['expectedRange']}."
    }


def analyze_anomalies_detailed(column: str, anomalies: List[Dict], values: List[float], stats: Dict[str, float]) -> List[Dict[str, Any]]:
    """Generate detailed analysis for each anomaly with practical recommendations."""
    detailed_anomalies = []

    for anomaly in anomalies:
        idx = anomaly['index']
        val = anomaly['value']
        z_score = anomaly['zScore']
        severity = anomaly['severity']

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

        action_plan = anomaly_action_plan(column, anomaly, stats, context_avg, local_direction)
        recommendations = []
        recommendations.extend(action_plan['validationChecks'][:2])
        recommendations.extend(action_plan['fixSteps'][:2])
        recommendations.extend(action_plan['decisionGuide'][:2])

        detailed_anomalies.append({
            'rowIndex': idx,
            'actualValue': val,
            'expectedRange': anomaly['expectedRange'],
            'deviation': f"{anomaly['deviationPercent']:.1f}% from average",
            'zScore': z_score,
            'severity': severity,
            'type': anomaly['type'],
            'recommendations': recommendations,
            'likelyCauses': action_plan['likelyCauses'],
            'validationChecks': action_plan['validationChecks'],
            'fixSteps': action_plan['fixSteps'],
            'businessQuestions': action_plan['businessQuestions'],
            'decisionGuide': action_plan['decisionGuide'],
            'impact': action_plan['impact'],
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
# Generate Executive Summary
def generate_executive_summary(numeric_stats: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Generate executive summary from numeric statistics"""
    if not numeric_stats:
        return None
    
    summary = {
        'keyMetrics': [],
        'criticalAnomalies': [],
        'anomalyDetails': [],
        'trends': [],
        'recommendations': [],
        'dataQualityScore': 0
    }
    
    # Sort by variation (max - min)
    sorted_stats = sorted(numeric_stats, 
                         key=lambda x: x['stats']['max'] - x['stats']['min'], 
                         reverse=True)
    
    # Key metrics: top 3 by variation
    for s in sorted_stats[:3]:
        variation_pct = ((s['stats']['max'] - s['stats']['min']) / 
                        max(abs(s['stats']['avg']), 1)) * 100
        summary['keyMetrics'].append({
            'column': s['column'],
            'value': round(s['stats']['avg'], 2),
            'range': f"{s['stats']['min']} to {s['stats']['max']}",
            'variation': f"{variation_pct:.1f}%"
        })
    
    # Detailed anomaly analysis
    total_anomalies = 0
    critical_count = 0
    for s in numeric_stats:
        if s.get('anomalies') and len(s['anomalies']) > 0:
            summary['criticalAnomalies'].append({
                'column': s['column'],
                'count': len(s['anomalies'])
            })
            total_anomalies += len(s['anomalies'])
            
            # Add detailed anomaly info
            if s.get('anomaliesDetailed'):
                for anomaly_detail in s['anomaliesDetailed']:
                    if anomaly_detail['severity'] == 'critical':
                        critical_count += 1
                    summary['anomalyDetails'].append({
                        'column': s['column'],
                        **anomaly_detail
                    })
    
    # Trends
    for s in numeric_stats:
        if s.get('trend') and s['trend']['trend'] in ['upward', 'downward']:
            summary['trends'].append({
                'column': s['column'],
                'direction': s['trend']['trend'],
                'strength': s['trend']['strength'],
                'confidence': f"{s['trend']['confidence']}%",
                'predictedNextValue': round(s['trend']['prediction'], 2)
            })
    
    # Recommendations
    if critical_count > 0:
        summary['recommendations'].append(f'🔴 CRITICAL: {critical_count} critical anomalies detected. Immediate investigation required.')
    
    if total_anomalies > 0 and total_anomalies > len(numeric_stats) * 0.1:
        summary['recommendations'].append(f'⚠️ High anomaly rate ({(total_anomalies / (len(numeric_stats) * 10)):.1f}% of records). Consider data validation review.')
    
    if not summary['criticalAnomalies']:
        summary['recommendations'].append('✓ No critical anomalies detected. Data appears clean.')
    
    if any(t['direction'] == 'downward' for t in summary['trends']):
        summary['recommendations'].append('📉 Review declining metrics - investigate root causes.')
    
    if any(t['direction'] == 'upward' for t in summary['trends']):
        summary['recommendations'].append('📈 Monitor upward trends - identify and sustain growth drivers.')
    
    # Calculate data quality score (0-100)
    anomaly_ratio = total_anomalies / (len(numeric_stats) * 10) if numeric_stats else 0
    quality_score = max(0, 100 - (anomaly_ratio * 100) - (critical_count * 10))
    summary['dataQualityScore'] = round(quality_score, 1)
    
    return summary


# Example usage function (for reference)
def analyze_numeric_column(values: List[float], column_name: str) -> Dict[str, Any]:
    """Complete analysis of a numeric column"""
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
