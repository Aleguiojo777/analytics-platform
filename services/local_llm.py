"""Optional local LLM integration for Insight Engine.

The provider is intentionally best-effort: DataLens must keep working when
Ollama is not installed, not running, or too slow for the current machine.
"""

import json
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from utils.config import Config


MAX_ITEMS = 8

MODE_GUIDANCE = {
    'executive': {
        'audience': 'business decision maker',
        'goal': 'summarize what matters most, what is risky, and what to review next',
        'sectionTitles': ['What Changed', 'Risks To Check', 'Next Actions'],
    },
    'quality': {
        'audience': 'data owner',
        'goal': 'explain readiness, data-quality risks, and validation priorities',
        'sectionTitles': ['Readiness Signals', 'Quality Risks', 'Validation Plan'],
    },
    'anomaly': {
        'audience': 'analyst investigating unusual values',
        'goal': 'prioritize anomalies and give practical checks without inventing causes',
        'sectionTitles': ['Anomaly Priority', 'Evidence', 'Investigation Plan'],
    },
    'forecast': {
        'audience': 'planner reviewing forecast readiness',
        'goal': 'explain whether trend signals are strong enough for planning',
        'sectionTitles': ['Forecast Inputs', 'Trend Confidence', 'Planning Caveats'],
    },
    'kpi': {
        'audience': 'dashboard designer',
        'goal': 'suggest candidate measures, dimensions, and reporting cautions',
        'sectionTitles': ['Candidate KPIs', 'Useful Dimensions', 'Reporting Notes'],
    },
}


def local_llm_enabled() -> bool:
    return bool(Config.ENABLE_LOCAL_LLM)


def _column_names(columns: List[Dict[str, Any]], limit: int) -> List[str]:
    return [str(col.get('COLUMN_NAME')) for col in columns[:limit] if col.get('COLUMN_NAME')]


def _round_number(value: Any, digits: int = 2) -> Any:
    if isinstance(value, (int, float)):
        return round(value, digits)
    return value


def _compact_anomaly_detail(detail: Dict[str, Any]) -> Dict[str, Any]:
    context = detail.get('context') or {}
    return {
        'rowIndex': detail.get('rowIndex'),
        'actualValue': detail.get('actualValue'),
        'expectedRange': detail.get('expectedRange'),
        'deviation': detail.get('deviation'),
        'zScore': detail.get('zScore'),
        'severity': detail.get('severity'),
        'type': detail.get('type'),
        'surroundingAverage': detail.get('surroundingAverage'),
        'previousValue': context.get('previousValue'),
        'nextValue': context.get('nextValue'),
        'localDirection': context.get('localDirection'),
    }


def _compact_analysis(analysis: Dict[str, Any]) -> Dict[str, Any]:
    stats = analysis.get('stats') or {}
    trend = analysis.get('trend') or {}
    anomalies = analysis.get('anomalies') or []
    anomaly_details = analysis.get('anomaliesDetailed') or []
    return {
        'column': analysis.get('column'),
        'stats': {
            'count': stats.get('count'),
            'min': _round_number(stats.get('min')),
            'max': _round_number(stats.get('max')),
            'avg': _round_number(stats.get('avg')),
            'median': _round_number(stats.get('median')),
            'stdDev': _round_number(stats.get('stdDev')),
        },
        'anomalyCount': len(anomalies),
        'topAnomalies': anomalies[:3],
        'anomalyDetails': [_compact_anomaly_detail(item) for item in anomaly_details[:2]],
        'trend': {
            'direction': trend.get('trend'),
            'strength': trend.get('strength'),
            'confidence': trend.get('confidence'),
            'prediction': _round_number(trend.get('prediction')),
            'basis': analysis.get('trendBasis'),
        } if trend else None,
        'computedInsights': analysis.get('insights', [])[:4],
    }


def _profile_snapshot(profile: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'label': profile.get('healthLabel'),
        'score': profile.get('score'),
        'reasons': profile.get('healthReasons', []),
        'recommendedAction': profile.get('recommendedAction'),
        'rows': profile.get('rowCount'),
        'columns': profile.get('columnCount'),
        'usable': profile.get('usable'),
    }


def _mode_guidance(mode: str) -> Dict[str, Any]:
    return MODE_GUIDANCE.get(mode) or MODE_GUIDANCE['executive']


def build_insight_prompt(
    table_name: str,
    summary: Dict[str, Any],
    profile: Dict[str, Any],
    numeric_cols: List[Dict[str, Any]],
    date_cols: List[Dict[str, Any]],
    text_cols: List[Dict[str, Any]],
    analyses: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Build a compact prompt from metadata and derived metrics only."""
    analyses = analyses or []
    mode = summary.get('mode') or 'executive'
    guidance = _mode_guidance(mode)
    compact_analyses = [_compact_analysis(item) for item in analyses[:8]]
    anomaly_tasks = _compact_anomaly_tasks(analyses)
    payload = {
        'table': table_name,
        'mode': mode,
        'modeLabel': summary.get('modeLabel'),
        'audience': guidance['audience'],
        'analysisGoal': guidance['goal'],
        'preferredReportSectionTitles': guidance['sectionTitles'],
        'health': _profile_snapshot(profile),
        'numericColumns': _column_names(numeric_cols, 10),
        'dateColumns': _column_names(date_cols, 6),
        'textColumns': _column_names(text_cols, 10),
        'categoryMetrics': summary.get('categoryMetrics', [])[:5],
        'keyMetrics': summary.get('keyMetrics', [])[:6],
        'computedObservations': summary.get('keyObservations', [])[:8],
        'computedRecommendations': summary.get('recommendations', [])[:8],
        'trends': summary.get('trends', [])[:6],
        'anomalies': summary.get('criticalAnomalies', [])[:6],
        'anomalyTasks': anomaly_tasks,
        'columnAnalyses': compact_analyses,
    }
    schema = {
        'narrativeText': 'A cohesive narrative in exactly two short paragraphs separated by a blank line. Do not use bullets, numbering, labels, or headings inside this value.',
        'keyObservations': ['3 to 6 concise observations, each tied to a metric, column, trend, anomaly, or data-quality signal.'],
        'recommendations': ['3 to 6 practical next steps. Use verbs like validate, compare, monitor, segment, confirm.'],
        'reportSections': [
            {'title': 'Use a preferredReportSectionTitles value when possible', 'items': ['2 to 5 specific bullets']}
        ],
        'columnInsights': [
            {'column': 'Existing column name from columnAnalyses', 'insights': ['2 to 4 bullets for that column']}
        ],
        'anomalyInsights': [
            {
                'column': 'Existing column name from anomalyTasks',
                'rowIndex': 0,
                'impact': 'One sentence explaining anomaly impact using supplied stats only.',
                'likelyCauses': ['2 to 4 possible causes framed as hypotheses to verify.'],
                'validationChecks': ['2 to 4 source-data checks.'],
                'fixSteps': ['2 to 4 remediation steps if the anomaly is data quality related.'],
                'businessQuestions': ['2 to 4 stakeholder questions.'],
                'decisionGuide': ['2 to 4 keep/correct/exclude guidance bullets.']
            }
        ],
    }
    writing_rules = [
        'Use the exact column names and rowIndex values from the payload.',
        'Do not invent rows, dates, customers, products, departments, causes, or external events.',
        'When cause is uncertain, write it as a hypothesis to validate, not as fact.',
        'Prefer concrete numeric evidence from the payload over generic advice.',
        'Write narrativeText as prose paragraphs, not bullets or a list.',
        'Do not mention SQL, JSON, prompts, or the fact that you are an AI.',
        'Return valid JSON only, with no markdown fences or commentary.',
        'Return columnInsights for every item in columnAnalyses.',
        'Return anomalyInsights for every item in anomalyTasks. If anomalyTasks is empty, return an empty anomalyInsights array.',
    ]
    return (
        'You are the local Insight Engine analyst inside DataLens. Improve the user-facing insight text for the requested mode. Use only the provided metadata and aggregate statistics. '
        f'Audience: {guidance["audience"]}. Goal: {guidance["goal"]}. '
        f'Writing rules: {json.dumps(writing_rules, ensure_ascii=True)} '
        f'Match this JSON schema exactly: {json.dumps(schema, ensure_ascii=True)}\n\n'
        f'Data:\n{json.dumps(payload, ensure_ascii=True)}'
    )


def ask_ollama(prompt: str) -> str:
    body = json.dumps({
        'model': Config.LOCAL_LLM_MODEL,
        'stream': False,
        'format': 'json',
        'messages': [
            {'role': 'system', 'content': 'You produce strict JSON for an analytics application. Use only supplied evidence.'},
            {'role': 'user', 'content': prompt},
        ],
        'options': {
            'temperature': 0.25,
            'top_p': 0.9,
            'repeat_penalty': 1.08,
        },
    }).encode('utf-8')

    request = urllib.request.Request(
        Config.LOCAL_LLM_URL,
        data=body,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(request, timeout=Config.LOCAL_LLM_TIMEOUT) as response:
        data = json.loads(response.read().decode('utf-8'))
    return str((data.get('message') or {}).get('content') or '').strip()


def parse_llm_json(text: str) -> Dict[str, Any]:
    cleaned = re.sub(r'^```(?:json)?|```$', '', str(text or '').strip(), flags=re.IGNORECASE | re.MULTILINE).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find('{')
        end = cleaned.rfind('}')
        if start == -1 or end == -1 or end <= start:
            raise
        parsed = json.loads(cleaned[start:end + 1])
    if not isinstance(parsed, dict):
        raise ValueError('Local LLM returned JSON that was not an object.')
    return parsed


def _text(value: Any, limit: int = 1200) -> str:
    result = str(value or '').strip()
    result = re.sub(r'^[\s\-*:;,.]+', '', result)
    result = re.sub(r'\s+', ' ', result)
    return result[:limit].strip()


def _narrative_text(value: Any, limit: int = 1600) -> str:
    """Clean narrative prose while preserving paragraph breaks."""
    if isinstance(value, list):
        raw = '\n\n'.join(str(item).strip() for item in value if str(item).strip())
    else:
        raw = str(value or '')
    raw = raw.replace('\r\n', '\n').replace('\r', '\n').strip()
    raw = re.sub(r'^[\s\-*:;,.]+', '', raw)
    paragraphs = []
    for paragraph in re.split(r'\n\s*\n+', raw):
        cleaned = re.sub(r'\s+', ' ', paragraph).strip()
        cleaned = re.sub(r'^(?:narrative|summary|paragraph\s*\d+)\s*[:\-]\s*', '', cleaned, flags=re.IGNORECASE)
        if cleaned:
            paragraphs.append(cleaned)
    if not paragraphs and raw:
        paragraphs = [re.sub(r'\s+', ' ', raw).strip()]
    return '\n\n'.join(paragraphs)[:limit].strip()


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    results = []
    for item in items:
        key = re.sub(r'\W+', '', item).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        results.append(item)
    return results


def _string_list(value: Any, limit: int = MAX_ITEMS) -> List[str]:
    if not isinstance(value, list):
        return []
    items = []
    for item in value:
        text = _text(item, 300)
        if text:
            items.append(text)
        if len(items) >= limit * 2:
            break
    return _dedupe(items)[:limit]


def _report_sections(value: Any, limit: int = 4) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    sections = []
    seen_titles = set()
    for section in value:
        if not isinstance(section, dict):
            continue
        title = _text(section.get('title'), 80)
        items = _string_list(section.get('items'), 5)
        title_key = title.lower()
        if title and items and title_key not in seen_titles:
            sections.append({'title': title, 'items': items})
            seen_titles.add(title_key)
        if len(sections) >= limit:
            break
    return sections


def _column_insights(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    results = []
    seen_columns = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        column = _text(item.get('column') or item.get('columnName') or item.get('name'), 160)
        insights = (
            _string_list(item.get('insights'), 4)
            or _string_list(item.get('items'), 4)
            or _string_list(item.get('recommendations'), 4)
        )
        column_key = column.lower()
        if column and insights and column_key not in seen_columns:
            results.append({'column': column, 'insights': insights})
            seen_columns.add(column_key)
    return results


def apply_local_llm_column_insights(analyses: List[Dict[str, Any]], summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Replace per-column insight text with local LLM text when provided."""
    column_insights = summary.get('llmColumnInsights') or []
    if not column_insights:
        return analyses

    by_column = {
        str(item.get('column') or '').strip().lower(): item.get('insights')
        for item in column_insights
        if item.get('column') and item.get('insights')
    }
    for analysis in analyses:
        replacement = by_column.get(str(analysis.get('column') or '').strip().lower())
        if replacement:
            analysis['insights'] = replacement
            analysis['llmInsights'] = True
    return analyses


def _anomaly_insights(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    results = []
    for item in value:
        if not isinstance(item, dict):
            continue
        column = _text(item.get('column') or item.get('columnName') or item.get('name'), 160)
        if not column:
            continue
        result = {
            'column': column,
            'rowIndex': item.get('rowIndex'),
            'impact': _text(item.get('impact'), 500),
            'likelyCauses': _string_list(item.get('likelyCauses'), 4),
            'validationChecks': _string_list(item.get('validationChecks'), 4),
            'fixSteps': _string_list(item.get('fixSteps'), 4),
            'businessQuestions': _string_list(item.get('businessQuestions'), 4),
            'decisionGuide': _string_list(item.get('decisionGuide'), 4),
        }
        if any(result.get(key) for key in ('impact', 'likelyCauses', 'validationChecks', 'fixSteps', 'businessQuestions', 'decisionGuide')):
            results.append(result)
    return results


def apply_local_llm_anomaly_insights(analyses: List[Dict[str, Any]], summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Replace anomaly explanation text with local LLM text when provided."""
    anomaly_insights = summary.get('llmAnomalyInsights') or []
    if not anomaly_insights:
        return analyses

    by_key = {}
    first_by_column = {}
    for item in anomaly_insights:
        column_key = str(item.get('column') or '').strip().lower()
        if not column_key:
            continue
        first_by_column.setdefault(column_key, item)
        if item.get('rowIndex') is not None:
            by_key[(column_key, int(item.get('rowIndex')))] = item

    for analysis in analyses:
        column_key = str(analysis.get('column') or '').strip().lower()
        for detail in analysis.get('anomaliesDetailed') or []:
            replacement = None
            if detail.get('rowIndex') is not None:
                replacement = by_key.get((column_key, int(detail.get('rowIndex'))))
            replacement = replacement or first_by_column.get(column_key)
            if not replacement:
                continue
            if replacement.get('impact'):
                detail['impact'] = replacement['impact']
            for field in ('likelyCauses', 'validationChecks', 'fixSteps', 'businessQuestions', 'decisionGuide'):
                if replacement.get(field):
                    detail[field] = replacement[field]
            detail['llmInsights'] = True
    return analyses


def ask_ollama_for_insight_json(prompt: str) -> Dict[str, Any]:
    """Ask Ollama for JSON and give it one chance to repair malformed output."""
    first_response = ask_ollama(prompt)
    try:
        return parse_llm_json(first_response)
    except (ValueError, json.JSONDecodeError) as first_error:
        repair_prompt = (
            'The previous response was not valid JSON. Return the same analytics content as valid JSON only. '
            'Use this exact object shape: {"narrativeText":"...","keyObservations":["..."],'
            '"recommendations":["..."],"reportSections":[{"title":"...","items":["..."]}],'
            '"columnInsights":[{"column":"...","insights":["..."]}],"anomalyInsights":[{"column":"...","rowIndex":0,"impact":"...","likelyCauses":["..."],"validationChecks":["..."],"fixSteps":["..."],"businessQuestions":["..."],"decisionGuide":["..."]}]}. '
            f'Invalid response to repair:\n{first_response}\n\nParser error: {first_error}'
        )
        return parse_llm_json(ask_ollama(repair_prompt))


def _compact_anomaly_tasks(analyses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    tasks = []
    for analysis in analyses or []:
        column = analysis.get('column')
        stats = analysis.get('stats') or {}
        for detail in (analysis.get('anomaliesDetailed') or [])[:2]:
            task = _compact_anomaly_detail(detail)
            task.update({
                'column': column,
                'stats': {
                    'count': stats.get('count'),
                    'min': _round_number(stats.get('min')),
                    'max': _round_number(stats.get('max')),
                    'avg': _round_number(stats.get('avg')),
                    'median': _round_number(stats.get('median')),
                    'stdDev': _round_number(stats.get('stdDev')),
                },
            })
            tasks.append(task)
    return tasks[:8]


def build_anomaly_prompt(table_name: str, analyses: List[Dict[str, Any]]) -> str:
    tasks = _compact_anomaly_tasks(analyses)
    schema = {
        'anomalyInsights': [{
            'column': 'Column name from anomalyTasks',
            'rowIndex': 0,
            'impact': 'One sentence explaining anomaly impact using supplied stats only.',
            'likelyCauses': ['2 to 4 possible causes framed as hypotheses to verify.'],
            'validationChecks': ['2 to 4 source-data checks.'],
            'fixSteps': ['2 to 4 practical remediation steps.'],
            'businessQuestions': ['2 to 4 stakeholder questions.'],
            'decisionGuide': ['2 to 4 keep/correct/exclude guidance bullets.'],
        }]
    }
    return (
        'You are DataLens anomaly analyst. Write practical anomaly investigation guidance. '
        'Use only the supplied aggregate stats and anomaly metrics. Do not invent customers, dates, products, or source rows. '
        'Frame causes as hypotheses to validate. Return valid JSON only. '
        'Return one anomalyInsights item for each anomalyTasks item. Copy column and rowIndex exactly from anomalyTasks. '
        f'Schema: {json.dumps(schema, ensure_ascii=True)}\n\n'
        f'Data: {json.dumps({"table": table_name, "anomalyTasks": tasks}, ensure_ascii=True)}'
    )


def _normalize_anomaly_insights(tasks: List[Dict[str, Any]], insights: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not tasks or not insights:
        return insights

    normalized = []
    unused = list(insights)
    for task in tasks:
        task_column = str(task.get('column') or '').strip().lower()
        task_row = task.get('rowIndex')
        match = None
        for item in unused:
            item_column = str(item.get('column') or '').strip().lower()
            same_column = item_column == task_column
            same_row = item.get('rowIndex') is None or task_row is None or int(item.get('rowIndex')) == int(task_row)
            if same_column and same_row:
                match = item
                break
        if match is None and len(tasks) == 1:
            match = unused[0]
        if match is None:
            continue
        if match in unused:
            unused.remove(match)
        fixed = dict(match)
        fixed['column'] = task.get('column')
        fixed['rowIndex'] = task_row
        normalized.append(fixed)
    return normalized


def ask_ollama_for_anomaly_json(table_name: str, analyses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    tasks = _compact_anomaly_tasks(analyses)
    if not tasks:
        return []
    content = ask_ollama_for_insight_json(build_anomaly_prompt(table_name, analyses))
    return _normalize_anomaly_insights(tasks, _anomaly_insights(content.get('anomalyInsights')))


def enrich_summary_with_local_llm(
    table_name: str,
    summary: Dict[str, Any],
    profile: Dict[str, Any],
    numeric_cols: List[Dict[str, Any]],
    date_cols: List[Dict[str, Any]],
    text_cols: List[Dict[str, Any]],
    analyses: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Return summary rewritten with local LLM insight text when available."""
    if not local_llm_enabled():
        return summary

    enriched = dict(summary or {})
    try:
        prompt = build_insight_prompt(table_name, enriched, profile, numeric_cols, date_cols, text_cols, analyses)
        llm_content = ask_ollama_for_insight_json(prompt)
    except (OSError, TimeoutError, urllib.error.URLError, ValueError, json.JSONDecodeError) as error:
        enriched['llmStatus'] = f'Local LLM unavailable: {error}'
        return enriched

    narrative = _narrative_text(llm_content.get('narrativeText'))
    observations = _string_list(llm_content.get('keyObservations'), 6)
    recommendations = _string_list(llm_content.get('recommendations'), 8)
    sections = _report_sections(llm_content.get('reportSections'))
    column_insights = _column_insights(llm_content.get('columnInsights'))
    anomaly_tasks = _compact_anomaly_tasks(analyses or [])
    anomaly_insights = _normalize_anomaly_insights(anomaly_tasks, _anomaly_insights(llm_content.get('anomalyInsights')))
    if not anomaly_insights:
        try:
            anomaly_insights = ask_ollama_for_anomaly_json(table_name, analyses or [])
        except (OSError, TimeoutError, urllib.error.URLError, ValueError, json.JSONDecodeError):
            anomaly_insights = []

    if narrative:
        enriched['llmNarrativeText'] = narrative
        enriched['narrativeText'] = narrative
    if observations:
        enriched['keyObservations'] = observations
    if recommendations:
        enriched['recommendations'] = recommendations
    if sections:
        enriched['reportSections'] = sections
    if column_insights:
        enriched['llmColumnInsights'] = column_insights
    if anomaly_insights:
        enriched['llmAnomalyInsights'] = anomaly_insights

    enriched['llmStatus'] = f'Generated locally with {Config.LOCAL_LLM_MODEL}'
    return enriched
