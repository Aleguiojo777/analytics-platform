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
def analyze_anomalies_detailed(column: str, anomalies: List[Dict], values: List[float], stats: Dict[str, float]) -> List[Dict[str, Any]]:
    """Generate detailed analysis for each anomaly with recommendations"""
    detailed_anomalies = []
    
    for anomaly in anomalies:
        idx = anomaly['index']
        val = anomaly['value']
        z_score = anomaly['zScore']
        severity = anomaly['severity']
        
        # Generate context: what are surrounding values?
        context_start = max(0, idx - 2)
        context_end = min(len(values), idx + 3)
        surrounding_values = values[context_start:context_end]
        context_avg = mean(surrounding_values) if surrounding_values else 0
        
        # Determine recommendation based on severity and context
        recommendations = []
        
        if severity == 'critical':
            recommendations.append("🔴 CRITICAL: This value is 4+ standard deviations from mean.")
            recommendations.append("   → Verify data entry accuracy - likely data entry error or system malfunction")
            recommendations.append("   → Consider removing if confirmed as bad data")
            recommendations.append("   → Or investigate the cause if legitimate spike/dip")
        elif severity == 'high':
            recommendations.append("🟠 HIGH: This value is 3-4 standard deviations from mean.")
            if anomaly['type'] == 'high':
                recommendations.append("   → Investigate what caused this spike")
            else:
                recommendations.append("   → Investigate what caused this significant drop")
            recommendations.append("   → Check surrounding records for related anomalies")
        else:  # moderate
            recommendations.append("🟡 MODERATE: This value is 2.5-3 standard deviations from mean.")
            recommendations.append("   → Review context (dates, external factors)")
            recommendations.append("   → Monitor trend - may indicate emerging pattern")
        
        # Context-based recommendation
        if abs(context_avg - stats['avg']) > stats['stdDev']:
            recommendations.append("   ⚠️ Surrounding values are also unusual - potential cluster anomaly")
        else:
            recommendations.append("   ℹ️ Surrounding values are normal - isolated anomaly")
        
        detailed_anomalies.append({
            'rowIndex': idx,
            'actualValue': val,
            'expectedRange': anomaly['expectedRange'],
            'deviation': f"{anomaly['deviationPercent']:.1f}% from average",
            'zScore': z_score,
            'severity': severity,
            'type': anomaly['type'],
            'recommendations': recommendations,
            'surroundingAverage': round(context_avg, 2)
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
