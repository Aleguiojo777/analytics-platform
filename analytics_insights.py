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
    """Detect anomalies using Z-score method"""
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
            anomalies.append({
                'value': val,
                'index': idx,
                'zScore': z_score
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
        insights.append(f"{column} shows high variability ({variation:.1f}% range).")
    elif variation < 20:
        insights.append(f"{column} is stable with low variability ({variation:.1f}% range).")
    
    if anomalies:
        pct = (len(anomalies) / stats['count']) * 100
        insights.append(f"⚠️ {len(anomalies)} anomalies detected ({pct:.1f}% of data).")
    
    if trend:
        if trend['trend'] == 'upward':
            insights.append(f"📈 Upward trend detected ({trend['strength']}).")
        elif trend['trend'] == 'downward':
            insights.append(f"📉 Downward trend detected ({trend['strength']}).")
        else:
            insights.append("→ Stable over time.")
    
    return insights

# Generate Executive Summary
def generate_executive_summary(numeric_stats: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Generate executive summary from numeric statistics"""
    if not numeric_stats:
        return None
    
    summary = {
        'keyMetrics': [],
        'criticalAnomalies': [],
        'trends': [],
        'recommendations': []
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
    
    # Critical anomalies
    for s in numeric_stats:
        if s.get('anomalies') and len(s['anomalies']) > 0:
            summary['criticalAnomalies'].append({
                'column': s['column'],
                'count': len(s['anomalies'])
            })
    
    # Trends
    for s in numeric_stats:
        if s.get('trend') and s['trend']['trend'] in ['upward', 'downward']:
            summary['trends'].append({
                'column': s['column'],
                'direction': s['trend']['trend'],
                'strength': s['trend']['strength']
            })
    
    # Recommendations
    if summary['criticalAnomalies']:
        summary['recommendations'].append('Investigate data quality anomalies.')
    
    if any(t['direction'] == 'downward' for t in summary['trends']):
        summary['recommendations'].append('Review declining metrics.')
    
    if any(t['direction'] == 'upward' for t in summary['trends']):
        summary['recommendations'].append('Identify drivers of positive trends.')
    
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
    trend = analyze_trend(values)
    insights = generate_insights(column_name, stats, anomalies, trend)
    
    return {
        'column': column_name,
        'stats': stats,
        'anomalies': anomalies,
        'trend': trend,
        'insights': insights
    }
