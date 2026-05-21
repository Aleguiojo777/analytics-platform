import unittest

from services.analytics_insights import analyze_anomalies_detailed, detect_anomalies, generate_executive_summary
from services.local_llm import _narrative_text, apply_local_llm_anomaly_insights, apply_local_llm_column_insights, build_insight_prompt, enrich_summary_with_local_llm, parse_llm_json
from controllers.analytics_controller import attach_analysis_scope
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

    def test_user_id_columns_do_not_block_business_tables(self):
        columns = [
            {'COLUMN_NAME': 'UserId', 'DATA_TYPE': 'int'},
            {'COLUMN_NAME': 'Amount', 'DATA_TYPE': 'decimal'},
            {'COLUMN_NAME': 'Region', 'DATA_TYPE': 'nvarchar'},
        ]

        profile = table_analytics_profile('dbo.SalesByUser', columns, row_count=25)

        self.assertTrue(profile['usable'])
        self.assertEqual(filter_sensitive_tables(['dbo.Users']), ['dbo.Users'])


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
    def test_anomaly_detail_keeps_computed_facts_without_rule_text(self):
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
        self.assertEqual(details[0]['metricContext'], 'numeric metric')
        self.assertEqual(details[0]['likelyCauses'], [])
        self.assertEqual(details[0]['validationChecks'], [])
        self.assertIn('SalesAmount value', details[0]['impact'])

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
        self.assertEqual(summary['recommendations'], [])

    def test_analysis_scope_explains_ai_fallback_and_coverage(self):
        summary = attach_analysis_scope(
            {},
            {'rowCount': 24, 'columnCount': 5},
            [{'COLUMN_NAME': 'Revenue'}],
            [{'COLUMN_NAME': 'OrderDate'}],
            [{'COLUMN_NAME': 'Region'}],
            [{'column': 'Revenue'}],
            use_ai_insights=True,
        )

        self.assertEqual(summary['analysisScope']['rows'], 24)
        self.assertEqual(summary['analysisScope']['analyzedColumns'], 1)
        self.assertIn('AI Analysis was requested', summary['llmStatus'])
class LocalLLMIntegrationTests(unittest.TestCase):
    def test_local_llm_is_disabled_by_default_without_changing_summary(self):
        original_enabled = Config.ENABLE_LOCAL_LLM
        Config.ENABLE_LOCAL_LLM = False
        summary = {'narrativeText': 'Built-in narrative', 'recommendations': []}
        try:
            enriched = enrich_summary_with_local_llm('dbo.Sales', summary, {}, [], [], [])
        finally:
            Config.ENABLE_LOCAL_LLM = original_enabled

        self.assertIs(enriched, summary)
        self.assertNotIn('llmStatus', enriched)

    def test_local_llm_prompt_uses_metadata_and_aggregate_insights(self):
        prompt = build_insight_prompt(
            'dbo.Sales',
            {
                'keyMetrics': [{'column': 'Revenue', 'stats': {'avg': 42}}],
                'keyObservations': ['Revenue is volatile'],
                'recommendations': ['Review high variance'],
            },
            {'score': 88, 'rowCount': 24, 'columnCount': 5, 'healthLabel': 'Ready'},
            [{'COLUMN_NAME': 'Revenue'}],
            [{'COLUMN_NAME': 'OrderDate'}],
            [{'COLUMN_NAME': 'Region'}],
        )

        self.assertIn('dbo.Sales', prompt)
        self.assertIn('Revenue is volatile', prompt)
        self.assertIn('Use only the provided metadata and aggregate statistics', prompt)
    def test_local_llm_column_insights_replace_computed_text(self):
        analyses = [{'column': 'Revenue', 'insights': ['Computed insight']}]
        summary = {'llmColumnInsights': [{'column': ' revenue ', 'insights': ['LLM-written insight']}]} 

        enriched = apply_local_llm_column_insights(analyses, summary)

        self.assertEqual(enriched[0]['insights'], ['LLM-written insight'])
        self.assertTrue(enriched[0]['llmInsights'])

    def test_local_llm_json_parser_accepts_fenced_json(self):
        parsed = parse_llm_json('```json\n{"recommendations":["Review totals"]}\n```')

        self.assertEqual(parsed['recommendations'], ['Review totals'])

    def test_local_llm_narrative_preserves_paragraphs(self):
        narrative = _narrative_text('Narrative: Revenue varies widely.\n\nValidate the outlier before reporting.')

        self.assertIn('\n\n', narrative)
        self.assertTrue(narrative.startswith('Revenue varies widely.'))
    def test_local_llm_anomaly_insights_replace_rule_text(self):
        analyses = [{
            'column': 'Revenue',
            'anomaliesDetailed': [{
                'rowIndex': 4,
                'impact': 'Rule impact',
                'likelyCauses': ['Rule cause'],
                'validationChecks': ['Rule check'],
                'fixSteps': ['Rule fix'],
                'businessQuestions': ['Rule question'],
                'decisionGuide': ['Rule decision'],
            }]
        }]
        summary = {'llmAnomalyInsights': [{
            'column': ' revenue ',
            'rowIndex': 4,
            'impact': 'LLM impact',
            'likelyCauses': ['LLM cause'],
            'validationChecks': ['LLM check'],
            'fixSteps': ['LLM fix'],
            'businessQuestions': ['LLM question'],
            'decisionGuide': ['LLM decision'],
        }]}

        enriched = apply_local_llm_anomaly_insights(analyses, summary)
        detail = enriched[0]['anomaliesDetailed'][0]

        self.assertEqual(detail['impact'], 'LLM impact')
        self.assertEqual(detail['likelyCauses'], ['LLM cause'])
        self.assertEqual(detail['validationChecks'], ['LLM check'])
        self.assertEqual(detail['fixSteps'], ['LLM fix'])
        self.assertEqual(detail['businessQuestions'], ['LLM question'])
        self.assertEqual(detail['decisionGuide'], ['LLM decision'])
        self.assertTrue(detail['llmInsights'])

if __name__ == '__main__':
    unittest.main()
