import unittest

from analytics_insights import analyze_anomalies_detailed, detect_anomalies, generate_executive_summary
from utils.table_filter import table_analytics_profile


class TableAnalyticsProfileTests(unittest.TestCase):
    def test_hides_empty_or_sensitive_tables(self):
        columns = [
            {'COLUMN_NAME': 'UserPassword', 'DATA_TYPE': 'nvarchar'},
            {'COLUMN_NAME': 'Amount', 'DATA_TYPE': 'decimal'},
        ]

        profile = table_analytics_profile('dbo.Users', columns, row_count=10)

        self.assertFalse(profile['usable'])
        self.assertIn('sensitive', profile['reason'])

    def test_scores_measure_dimension_and_date_tables(self):
        columns = [
            {'COLUMN_NAME': 'OrderDate', 'DATA_TYPE': 'datetime'},
            {'COLUMN_NAME': 'SalesAmount', 'DATA_TYPE': 'decimal'},
            {'COLUMN_NAME': 'Region', 'DATA_TYPE': 'nvarchar'},
        ]

        profile = table_analytics_profile('dbo.Sales', columns, row_count=250)

        self.assertTrue(profile['usable'])
        self.assertEqual(profile['suggestedView'], 'time-series')
        self.assertEqual(profile['numericMeasureCount'], 1)
        self.assertEqual(profile['dateColumnCount'], 1)
        self.assertEqual(profile['textDimensionCount'], 1)


class InsightRecommendationTests(unittest.TestCase):
    def test_financial_anomaly_gets_specific_action_plan(self):
        values = [100, 105, 98, 102, 5000, 99, 101]
        stats = {
            'count': len(values),
            'min': min(values),
            'max': max(values),
            'avg': sum(values) / len(values),
            'stdDev': 100,
        }
        anomalies = detect_anomalies(values, threshold=1.5)

        details = analyze_anomalies_detailed('SalesAmount', anomalies, values, stats)

        self.assertGreaterEqual(len(details), 1)
        self.assertEqual(details[0]['metricContext'], 'financial metric')
        joined = ' '.join(details[0]['likelyCauses'] + details[0]['validationChecks'])
        self.assertIn('invoice', joined.lower())

    def test_summary_uses_actual_analyzed_value_count_for_rate(self):
        summary = generate_executive_summary([
            {
                'column': 'Quantity',
                'stats': {'count': 100, 'min': 1, 'max': 20, 'avg': 8},
                'anomalies': [{'severity': 'high'}],
                'anomaliesDetailed': [],
                'trend': {'trend': 'stable'},
            }
        ])

        recommendations = ' '.join(summary['recommendations'])
        self.assertIn('1 of 100', recommendations)


if __name__ == '__main__':
    unittest.main()
