import math
from typing import List, Dict, Any, Optional, Tuple

# SMART INSIGHTS FUNCTIONS

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
        insights.append(f"Warning: {column}: High variability detected ({variation:.1f}% range). Data may need normalization or investigation.")
    elif variation < 20:
        insights.append(f"OK: {column}: Stable with low variability ({variation:.1f}% range). Data quality is consistent.")
    else:
        insights.append(f"Info: {column}: Moderate variability ({variation:.1f}% range).")
    
    if anomalies:
        pct = (len(anomalies) / stats['count']) * 100
        insights.append(f"Warning: {len(anomalies)} anomalies detected ({pct:.1f}% of data) - see detailed analysis below.")
    
    if trend:
        if trend['trend'] == 'upward':
            insights.append(f"Upward trend detected ({trend['strength']} confidence: {trend['confidence']}%). Monitor for continued growth.")
        elif trend['trend'] == 'downward':
            insights.append(f"Downward trend detected ({trend['strength']} confidence: {trend['confidence']}%). Investigate root causes.")
        else:
            insights.append("Stable trend over time. No significant directional change detected.")
    
    return insights


# Generate Detailed Anomaly Analysis

def infer_metric_context(column: str) -> Dict[str, Any]:
    name = str(column or '').lower()
    contexts = [
        {
            'keywords': ['sales', 'revenue', 'amount', 'price', 'total', 'income', 'payment', 'cost', 'expense', 'profit'],
            'label': 'financial metric',
            'high_causes': [
                'Large order, bulk payment, price change, duplicate invoice, or aggregated total mixed into transaction-level data.',
                'Currency, tax, discount, or decimal-place issue causing the amount to be overstated.'
            ],
            'low_causes': [
                'Refund, discount, cancellation, missing payment line, or partial transaction posted as a low amount.',
                'Zero-value or test transaction included in the reporting table.'
            ],
            'checks': [
                'Compare invoice/order/payment reference numbers for duplicates or reversals.',
                'Verify currency, tax, discount, and decimal precision against the source transaction.'
            ],
            'fixes': [
                'Correct duplicate or mis-scaled financial records in the source system, then reload analytics.',
                'Separate refunds/cancellations from gross sales if the KPI should show normal revenue only.'
            ]
        },
        {
            'keywords': ['qty', 'quantity', 'count', 'units', 'stock', 'inventory', 'order_count'],
            'label': 'volume or inventory metric',
            'high_causes': [
                'Bulk order, batch posting, duplicate scan, stock adjustment, or unit-of-measure mismatch.',
                'Aggregated quantity mixed with line-item quantity.'
            ],
            'low_causes': [
                'Stock-out, cancelled item, missing quantity, failed scan, or quantity stored as zero instead of null.',
                'Returns or inventory corrections reducing the recorded quantity.'
            ],
            'checks': [
                'Check unit of measure, package size, and whether the row is line-level or summary-level.',
                'Compare the row with inventory movements, returns, or fulfilment records.'
            ],
            'fixes': [
                'Normalize quantities to one unit of measure before charting or forecasting.',
                'Flag stock adjustments and returns separately from normal order quantity.'
            ]
        },
        {
            'keywords': ['duration', 'time', 'latency', 'minutes', 'hours', 'days', 'delay'],
            'label': 'time or duration metric',
            'high_causes': [
                'Process delay, outage, waiting time, long-running job, or start/end timestamp mismatch.',
                'Duration calculated across wrong timezone, date boundary, or business calendar.'
            ],
            'low_causes': [
                'Missing end time, default zero duration, skipped workflow step, or immediate auto-completion.',
                'Incorrect timestamp order or rounded duration.'
            ],
            'checks': [
                'Validate start/end timestamps, timezone, and whether weekends or non-business hours should be excluded.',
                'Check logs around the same period for outages or stalled processing.'
            ],
            'fixes': [
                'Recalculate duration from trusted timestamps and consistent timezone rules.',
                'Treat missing or default durations separately from genuine fast completions.'
            ]
        },
        {
            'keywords': ['score', 'rating', 'percent', 'percentage', 'rate', 'ratio'],
            'label': 'score or rate metric',
            'high_causes': [
                'Small denominator, changed scoring rule, duplicate positive events, or values stored as 0-100 mixed with 0-1.',
                'Exceptional performance period or category concentration.'
            ],
            'low_causes': [
                'Small denominator, missing numerator events, changed scoring rule, or values stored in the wrong scale.',
                'Real performance drop that needs segmentation by product, team, branch, or period.'
            ],
            'checks': [
                'Confirm whether the metric is stored as fraction or percentage and whether denominator is large enough.',
                'Recalculate numerator and denominator from source rows.'
            ],
            'fixes': [
                'Standardize the scale before reporting, for example all rates as 0-100 or all as 0-1.',
                'Suppress or label rates based on very small denominators.'
            ]
        }
    ]

    for context in contexts:
        if any(keyword in name for keyword in context['keywords']):
            return context

    return {
        'label': 'numeric metric',
        'high_causes': [
            'One-time spike, duplicate record, batch import, aggregation mismatch, or valid exceptional event.',
            'Unit or scale mismatch compared with nearby values.'
        ],
        'low_causes': [
            'Missing value represented as zero, incomplete row, cancellation, or valid exceptional drop.',
            'Partial import or source-system issue affecting this metric.'
        ],
        'checks': [
            'Compare the row with source data and nearby rows in the same period or category.',
            'Check for duplicate records, null handling, unit changes, and import batch issues.'
        ],
        'fixes': [
            'Correct source data if the value is wrong, then reload the analytics table.',
            'If valid, keep the value and document the business reason in the report.'
        ]
    }
def anomaly_action_plan(column: str, anomaly: Dict[str, Any], stats: Dict[str, float], context_avg: float, local_direction: str) -> Dict[str, Any]:
    severity = anomaly['severity']
    anomaly_type = anomaly['type']
    avg = stats.get('avg', 0)
    std = stats.get('stdDev', 0)
    metric_context = infer_metric_context(column)

    likely_causes = []
    validation_checks = []
    fix_steps = []
    business_questions = []

    likely_causes.extend(metric_context['high_causes'] if anomaly_type == 'high' else metric_context['low_causes'])
    validation_checks.extend(metric_context['checks'])
    fix_steps.extend(metric_context['fixes'])

    if anomaly_type == 'high':
        business_questions.extend([
            f'What event, product, customer, branch, or batch produced the unusually high {column} value?',
            f'Is this high {metric_context["label"]} expected for a known campaign, season, bulk transaction, or operational event?'
        ])
    else:
        business_questions.extend([
            f'What event, process, or missing input caused {column} to drop below its normal range?',
            f'Should this low {metric_context["label"]} be treated as a valid business exception, missing data, or an error?'
        ])

    if severity == 'critical':
        validation_checks.extend([
            'Confirm the source row before using it in management reports or automated decisions.',
            'Check decimal placement, sign, unit, and whether this row is a raw record or an already aggregated total.'
        ])
        fix_steps.extend([
            'Correct the value in the source system if it is wrong, then refresh the analytics table.',
            'If it is real, annotate the report with the reason so the anomaly is not mistaken for bad data.',
            'If still unverified, exclude it from KPI calculations temporarily with a documented filter.'
        ])
    elif severity == 'high':
        validation_checks.extend([
            'Compare this row with the same metric in nearby dates, categories, branches, or products.',
            'Check whether the value came from a late posting, manual edit, or backfilled batch.'
        ])
        fix_steps.extend([
            'Tag this row for review and decide whether it should be corrected, excluded, or explained.',
            'Add validation thresholds for this metric if similar anomalies repeat.'
        ])
    else:
        validation_checks.extend([
            'Review context before changing the data because this may be an early but valid signal.',
            'Compare against median and recent values, not only the average.'
        ])
        fix_steps.extend([
            'Keep the value if it matches a real business event.',
            'Create a monitoring rule if this pattern continues.'
        ])

    if std and abs(context_avg - avg) > std:
        likely_causes.append('Nearby values are also unusual, so this may be a period-level, category-level, or import-batch issue.')
        validation_checks.append('Inspect the surrounding row window as a group instead of reviewing only the single value.')
    else:
        likely_causes.append('Nearby values look more normal, so this is more likely an isolated row-level issue.')

    if local_direction != 'flat':
        business_questions.append(f'Does the surrounding sequence show a real {local_direction} movement, or did the data loading/order create a false trend?')

    return {
        'metricContext': metric_context['label'],
        'likelyCauses': likely_causes,
        'validationChecks': validation_checks,
        'fixSteps': fix_steps,
        'businessQuestions': business_questions,
        'decisionGuide': [
            'Correct it when source data, scale, sign, duplicate status, or calculation is wrong.',
            'Keep it when it matches a real business event and explain it in the analysis.',
            'Exclude it only for the specific KPI/report where confirmed bad data would distort the result.'
        ],
        'impact': f"This {metric_context['label']} is {anomaly['deviationPercent']:.1f}% away from the average of {round(avg, 2)} and falls outside the expected range {anomaly['expectedRange']}."
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
            'metricContext': action_plan['metricContext'],
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
        'dataQualityScore': 0,
        'keyObservations': [],
        'narrativeText': ''
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
    total_values = sum(s['stats'].get('count', 0) for s in numeric_stats) if numeric_stats else 0
    anomaly_rate = (total_anomalies / total_values) * 100 if total_values else 0

    if critical_count > 0:
        summary['recommendations'].append(f'Critical: {critical_count} critical anomalies detected. Verify source rows before using these values in reports.')

    if total_anomalies > 0:
        summary['recommendations'].append(f'Anomaly rate: {anomaly_rate:.1f}% of analyzed numeric values ({total_anomalies} of {total_values}). Review the detailed anomaly checks below.')

    if anomaly_rate >= 5:
        summary['recommendations'].append('High anomaly rate: check import batches, duplicate records, unit mismatches, and missing validation rules.')
    elif total_anomalies > 0:
        summary['recommendations'].append('Focused review: start with the highest-severity anomaly and confirm whether it is a valid business event or bad data.')

    if not summary['criticalAnomalies']:
        summary['recommendations'].append('No critical anomalies detected. Continue monitoring moderate or high outliers during regular data review.')

    if any(t['direction'] == 'downward' for t in summary['trends']):
        summary['recommendations'].append('Declining metrics: compare the affected period with operational events, refunds, outages, or missing records.')

    if any(t['direction'] == 'upward' for t in summary['trends']):
        summary['recommendations'].append('Upward metrics: confirm whether growth comes from real demand, duplicate loading, price changes, or expanded coverage.')

    # Calculate data quality score (0-100)
    anomaly_ratio = total_anomalies / total_values if total_values else 0
    quality_score = max(0, 100 - (anomaly_ratio * 100) - (critical_count * 10))
    summary['dataQualityScore'] = round(quality_score, 1)

    if summary['keyMetrics']:
        lead_metric = summary['keyMetrics'][0]
        summary['keyObservations'].append(
            f"{lead_metric['column']} has the widest measured range ({lead_metric['range']}) with {lead_metric['variation']} variation."
        )

    if summary['criticalAnomalies']:
        anomaly_columns = ', '.join(item['column'] for item in summary['criticalAnomalies'][:3])
        summary['keyObservations'].append(f"Anomalies were detected in {anomaly_columns}; validate those source rows before relying on the KPI.")
    else:
        summary['keyObservations'].append('No anomaly cluster crossed the configured severity threshold in the analyzed sample.')

    if summary['trends']:
        trend_columns = ', '.join(f"{item['column']} ({item['direction']})" for item in summary['trends'][:3])
        summary['keyObservations'].append(f"Time-based movement is visible for {trend_columns}.")
    else:
        summary['keyObservations'].append('No reliable time trend was detected; trend cards are shown only when date/time ordering is available.')

    summary['narrativeText'] = ' '.join(summary['keyObservations'])
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
