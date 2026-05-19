import unittest

from services.analytics_insights import analyze_anomalies_detailed, detect_anomalies, generate_executive_summary
from controllers.db_controller import build_connection_string, friendly_connection_error
from utils.config import Config
from utils.table_filter import filter_sensitive_tables, table_analytics_profile


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

    def test_business_key_tables_are_not_treated_as_sensitive(self):
        table_names = ['dbo.ProductKeyMetrics']

        self.assertEqual(filter_sensitive_tables(table_names), table_names)


class DatabaseConnectionStringTests(unittest.TestCase):
    def test_trust_server_certificate_respects_checkbox_when_encrypting(self):
        conn_str = build_connection_string({
            'server': 'localhost',
            'port': '1433',
            'database': 'AnalyticsDb',
            'username': 'sa',
            'password': 'Password123!',
            'encrypt': True,
            'trustCert': False,
        })

        self.assertIn('Encrypt=Yes;', conn_str)
        self.assertIn('TrustServerCertificate=No;', conn_str)

    def test_trust_server_certificate_can_be_enabled_without_encrypting(self):
        conn_str = build_connection_string({
            'server': 'localhost',
            'port': '1433',
            'database': 'AnalyticsDb',
            'username': 'sa',
            'password': 'Password123!',
            'encrypt': False,
            'trustCert': True,
        })

        self.assertIn('Encrypt=No;', conn_str)
        self.assertIn('TrustServerCertificate=Yes;', conn_str)

    def test_connection_timeout_uses_config_value(self):
        original_timeout = Config.DB_CONNECTION_TIMEOUT
        Config.DB_CONNECTION_TIMEOUT = 22
        try:
            conn_str = build_connection_string({
                'server': 'localhost',
                'port': '1433',
                'database': 'AnalyticsDb',
                'username': 'sa',
                'password': 'Password123!',
                'encrypt': False,
                'trustCert': True,
            })
        finally:
            Config.DB_CONNECTION_TIMEOUT = original_timeout

        self.assertIn('Connection Timeout=22;', conn_str)

    def test_certificate_error_is_explained_in_plain_language(self):
        error = Exception(
            '[Microsoft][ODBC Driver 18 for SQL Server]SSL Provider: '
            'The certificate chain was issued by an authority that is not trusted.'
        )

        message = friendly_connection_error(error)

        self.assertIn('certificate is not trusted', message)
        self.assertIn('Trust Server Certificate', message)
        self.assertNotIn('ODBC Driver', message)

    def test_unknown_connection_error_uses_simple_fallback(self):
        message = friendly_connection_error(Exception('driver-specific low level error'))

        self.assertEqual(message, 'Connection failed. Check the server details and try again.')


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
