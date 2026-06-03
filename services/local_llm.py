import json
import os
import shlex
import subprocess
from typing import Any, Dict, Optional

try:
    import requests
except Exception:  # pragma: no cover - optional dependency
    requests = None


def _call_ollama_http(prompt: str, model: str, timeout: int = 30) -> Optional[str]:
    if not requests:
        return None
    url = os.environ.get('LOCAL_LLM_URL', 'http://127.0.0.1:11434/api/generate')
    payload = {"model": model, "prompt": prompt}
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        try:
            r.raise_for_status()
        except Exception as http_err:
            # Log details for debugging server-side 5xx/4xx errors
            logger = logging.getLogger(__name__)
            logger.warning('Ollama HTTP error: %s %s', r.status_code, http_err)
            logger.info('Ollama request URL: %s', url)
            logger.info('Ollama request payload: %s', json.dumps({k: (v if k != 'prompt' else '<prompt trimmed>') for k, v in payload.items()}))
            # attempt to include response body if available
            try:
                logger.info('Ollama response body: %s', r.text[:4000])
            except Exception:
                logger.info('Ollama response body: <unavailable>')
            return None

        # Parse JSON if possible; Ollama response shapes vary
        try:
            data = r.json()
        except Exception:
            return r.text

        if isinstance(data, dict):
            return data.get("text") or data.get("output") or json.dumps(data)
        return str(data)
    except Exception as e:
        logging.getLogger(__name__).warning('Ollama HTTP request failed: %s', str(e))
        return None


def _call_ollama_cli(prompt: str, model: str, timeout: int = 30) -> Optional[str]:
    cmd = ["ollama", "run", model, "--completion", "--input", prompt]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if p.returncode == 0 and p.stdout:
            return p.stdout.strip()
        # sometimes output is on stderr
        if p.stderr:
            return p.stderr.strip()
    except Exception:
        return None
    return None


def _call_openai(prompt: str, model: str, timeout: int = 30) -> Optional[str]:
    try:
        import openai
    except Exception:
        return None
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    openai.api_key = key
    try:
        # use ChatCompletion if available
        if hasattr(openai, "ChatCompletion"):
            resp = openai.ChatCompletion.create(model=model, messages=[{"role": "user", "content": prompt}], request_timeout=timeout)
            return resp.choices[0].message.content.strip()
        resp = openai.Completion.create(model=model, prompt=prompt, max_tokens=512, temperature=0.2, request_timeout=timeout)
        return resp.choices[0].text.strip()
    except Exception:
        return None


def generate(prompt: str, model: str = "phi3:mini", timeout: int = 30) -> Dict[str, Any]:
    """Generate text from local model or fallback to available providers.

    Strategy: try Ollama HTTP -> Ollama CLI -> OpenAI (if API key present).
    """
    result = {
        "provider": None,
        "text": None,
        "error": None,
    }

    text = _call_ollama_http(prompt, model, timeout)
    if text:
        result.update({"provider": "ollama-http", "text": text})
        return result

    text = _call_ollama_cli(prompt, model, timeout)
    if text:
        result.update({"provider": "ollama-cli", "text": text})
        return result

    text = _call_openai(prompt, model, timeout)
    if text:
        result.update({"provider": "openai", "text": text})
        return result

    result["error"] = (
        "No provider produced output. Ensure Ollama is running or set OPENAI_API_KEY."
    )
    return result


def list_local_models() -> Dict[str, Any]:
    """Return parsed `ollama list` output when available."""
    try:
        p = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10)
        return {"returncode": p.returncode, "output": p.stdout.strip() or p.stderr.strip()}
    except Exception as e:
        return {"returncode": 1, "output": str(e)}
"""Optional local LLM integration for Insight Engine.

The provider is intentionally best-effort: DataLens must keep working when
Ollama is not installed, not running, or too slow for the current machine.
"""

import json
import re
import time
import hashlib
import threading
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from utils.config import Config

import logging
try:
    import jsonschema  # type: ignore[reportMissingModuleSource]
    _HAVE_JSONSCHEMA = True
except Exception:
    _HAVE_JSONSCHEMA = False

logger = logging.getLogger(__name__)

# Simple in-process cache: prompt_hash -> (ts, response_str)
_llm_cache: Dict[str, tuple] = {}
_llm_cache_lock = threading.Lock()

# Circuit breaker state
_llm_last_failure = 0.0
_llm_failure_count = 0

# Simple metrics
_llm_metrics = {
    'calls': 0,
    'errors': 0,
    'cache_hits': 0,
    'validation_failures': 0,
}


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
    # Harden payload: sanitize strings and limit overall size
    def _sanitize_obj(obj, field_limit=Config.LOCAL_LLM_MAX_FIELD_CHARS):
        if isinstance(obj, str):
            s = obj.replace('\r\n', '\n')
            return s[:field_limit]
        if isinstance(obj, list):
            return [_sanitize_obj(x, field_limit) for x in obj][:MAX_ITEMS]
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                if isinstance(v, (str, list, dict)):
                    out[k] = _sanitize_obj(v, field_limit)
                else:
                    out[k] = v
            return out
        return obj

    try:
        sanitized_payload = _sanitize_obj(payload)
        payload_json = json.dumps(sanitized_payload, ensure_ascii=True)
        if len(payload_json) > Config.LOCAL_LLM_MAX_PROMPT_CHARS:
            # aggressively trim long lists/fields and re-serialize
            payload = sanitized_payload
            # Trim large arrays in place
            for key in ('columnAnalyses', 'anomalyTasks', 'computedObservations', 'computedRecommendations', 'trends', 'anomalies'):
                if isinstance(payload.get(key), list):
                    payload[key] = payload[key][:max(1, int(Config.LOCAL_LLM_MAX_PROMPT_CHARS / 2000))]
            payload_json = json.dumps(payload, ensure_ascii=True)
    except Exception:
        payload_json = json.dumps(payload, ensure_ascii=True)
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
        f'Data:\n{payload_json}'
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
        raw = response.read().decode('utf-8')
        try:
            data = json.loads(raw)
        except Exception:
            # If response is not JSON, return raw text
            return raw.strip()

    # Ollama HTTP responses can take several shapes depending on version:
    # - {"message": {"content": "..."}}
    # - {"text": "..."}
    # - {"output": "..."}
    # - other dict shapes
    if isinstance(data, dict):
        # preferred: message.content
        msg = data.get('message') or {}
        if isinstance(msg, dict) and msg.get('content'):
            return str(msg.get('content')).strip()
        # fallback to text or output
        for key in ('text', 'output'):
            if key in data and data.get(key):
                return str(data.get(key)).strip()
        # some versions embed choices or 'result'
        if data.get('result'):
            return str(data.get('result')).strip()
        # last resort: return the JSON string
        return json.dumps(data)
    return str(data)


def _prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode('utf-8')).hexdigest()


def _get_cached_response(key: str, ttl: int) -> Optional[str]:
    now = time.time()
    with _llm_cache_lock:
        item = _llm_cache.get(key)
        if not item:
            return None
        ts, value = item
        if ttl and (now - ts) > ttl:
            del _llm_cache[key]
            return None
        return value


def _set_cached_response(key: str, value: str) -> None:
    with _llm_cache_lock:
        _llm_cache[key] = (time.time(), value)


def _is_cooled_down() -> bool:
    if Config.LOCAL_LLM_COOLDOWN_SEC <= 0:
        return True
    return (time.time() - _llm_last_failure) > Config.LOCAL_LLM_COOLDOWN_SEC


def _inc_metric(name: str) -> None:
    if not Config.LOCAL_LLM_ENABLE_METRICS:
        return
    try:
        _llm_metrics[name] = _llm_metrics.get(name, 0) + 1
    except Exception:
        pass


def _validate_llm_output(parsed: Dict[str, Any]) -> bool:
    # Minimal schema validation: require main keys
    required_keys = {'narrativeText', 'keyObservations', 'recommendations', 'reportSections', 'columnInsights', 'anomalyInsights'}
    if not isinstance(parsed, dict):
        return False
    if not required_keys.issubset(set(parsed.keys())):
        return False
    if _HAVE_JSONSCHEMA:
        try:
            schema = {
                'type': 'object',
                'properties': {
                    'narrativeText': {'type': 'string'},
                    'keyObservations': {'type': 'array'},
                    'recommendations': {'type': 'array'},
                    'reportSections': {'type': 'array'},
                    'columnInsights': {'type': 'array'},
                    'anomalyInsights': {'type': 'array'},
                },
                'required': list(required_keys),
            }
            jsonschema.validate(instance=parsed, schema=schema)
            return True
        except Exception as e:
            logger.debug('jsonschema validation failed: %s', e)
            return False
    # Fallback: basic structural checks passed
    return True


def ask_ollama_with_resilience(prompt: str, cache_ttl: int = None) -> str:
    """Call the local LLM with caching, retries, backoff, and simple circuit-breaker."""
    _inc_metric('calls')
    key = _prompt_hash(prompt)
    ttl = cache_ttl if cache_ttl is not None else Config.LOCAL_LLM_CACHE_TTL
    try:
        cached = _get_cached_response(key, ttl)
        if cached is not None:
            _inc_metric('cache_hits')
            logger.debug('LLM cache hit')
            return cached
    except Exception:
        logger.exception('LLM cache read failed')

    global _llm_last_failure, _llm_failure_count
    if not _is_cooled_down():
        _inc_metric('errors')
        raise OSError('Local LLM is in cooldown due to recent failures')

    last_err = None
    for attempt in range(max(1, Config.LOCAL_LLM_MAX_RETRIES + 1)):
        try:
            start = time.time()
            result = ask_ollama(prompt)
            latency = time.time() - start
            logger.info('LLM call success (latency=%.2fs)', latency)
            _llm_failure_count = 0
            _llm_last_failure = 0.0
            # cache and return
            try:
                _set_cached_response(key, result)
            except Exception:
                logger.debug('Failed to set LLM cache')
            return result
        except Exception as e:
            last_err = e
            _inc_metric('errors')
            _llm_failure_count += 1
            _llm_last_failure = time.time()
            backoff = Config.LOCAL_LLM_RETRY_BACKOFF_SEC * (2 ** attempt)
            logger.warning('LLM call failed (attempt %d): %s — backing off %.1fs', attempt + 1, e, backoff)
            time.sleep(backoff)

    # all attempts failed
    logger.error('Local LLM unavailable after retries: %s', last_err)
    raise last_err


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


def _validate_anomaly_llm_output(parsed: Dict[str, Any]) -> bool:
    if not isinstance(parsed, dict):
        return False
    insights = parsed.get('anomalyInsights')
    if not isinstance(insights, list):
        return False
    if _HAVE_JSONSCHEMA:
        try:
            schema = {
                'type': 'object',
                'properties': {
                    'anomalyInsights': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'column': {'type': 'string'},
                                'rowIndex': {},
                                'impact': {'type': 'string'},
                                'likelyCauses': {'type': 'array'},
                                'validationChecks': {'type': 'array'},
                                'fixSteps': {'type': 'array'},
                                'businessQuestions': {'type': 'array'},
                                'decisionGuide': {'type': 'array'},
                            },
                            'required': ['column'],
                        },
                    },
                },
                'required': ['anomalyInsights'],
            }
            jsonschema.validate(instance=parsed, schema=schema)
            return True
        except Exception as e:
            logger.debug('anomaly jsonschema validation failed: %s', e)
            return False
    return True

def ask_ollama_for_insight_json(prompt: str) -> Dict[str, Any]:
    """Ask Ollama for JSON and give it one chance to repair malformed output."""
    first_response = ask_ollama_with_resilience(prompt)
    logger.info('Raw LLM first response: %s', first_response)
    try:
        parsed = parse_llm_json(first_response)
        if not _validate_llm_output(parsed):
            # Try to coerce common alternate shapes into the expected schema
            coerced = _coerce_insight_shape(parsed)
            if coerced and _validate_llm_output(coerced):
                logger.info('Coerced LLM first response into expected schema')
                return coerced
            _inc_metric('validation_failures')
            raise ValueError('LLM output failed schema validation')
        return parsed
    except (ValueError, json.JSONDecodeError) as first_error:
        _inc_metric('errors')
        logger.info('LLM first parse/validation error: %s', first_error)
        repair_prompt = (
            'The previous response was not valid JSON. Return the same analytics content as valid JSON only. '
            'Use this exact object shape: {"narrativeText":"...","keyObservations":["..."],'
            '"recommendations":["..."],"reportSections":[{"title":"...","items":["..."]}],'
            '"columnInsights":[{"column":"...","insights":["..."]}],"anomalyInsights":[{"column":"...","rowIndex":0,"impact":"...","likelyCauses":["..."],"validationChecks":["..."],"fixSteps":["..."],"businessQuestions":["..."],"decisionGuide":["..."]}]}. '
            f'Invalid response to repair:\n{first_response}\n\nParser error: {first_error}'
        )
        repaired = ask_ollama_with_resilience(repair_prompt)
        logger.info('Raw LLM repaired response: %s', repaired)
        parsed2 = parse_llm_json(repaired)
        if not _validate_llm_output(parsed2):
            coerced2 = _coerce_insight_shape(parsed2)
            if coerced2 and _validate_llm_output(coerced2):
                logger.info('Coerced repaired LLM response into expected schema')
                return coerced2
            _inc_metric('validation_failures')
            logger.info('Repaired LLM output failed validation')
            raise ValueError('Repaired LLM output failed schema validation')
        return parsed2


def _coerce_insight_shape(parsed: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Attempt to map common alternate LLM response shapes into the required schema.

    This is a best-effort heuristic to handle responses like {"summary": {...}}
    where keys are "whatMattersMost", "risksToCheck", "nextActions".
    """
    if not isinstance(parsed, dict):
        return None
    # Common alternate: {"summary": {"whatMattersMost": ..., "risksToCheck": [...], "nextActions": [...]}}
    summary = parsed.get('summary') or parsed.get('Summary')
    if isinstance(summary, dict):
        out = {
            'narrativeText': None,
            'keyObservations': [],
            'recommendations': [],
            'reportSections': [],
            'columnInsights': [],
            'anomalyInsights': []
        }
        if summary.get('whatMattersMost'):
            out['narrativeText'] = str(summary.get('whatMattersMost'))
        # risksToCheck -> keyObservations
        if isinstance(summary.get('risksToCheck'), list):
            out['keyObservations'] = [str(x) for x in summary.get('risksToCheck')[:6]]
        # nextActions -> recommendations
        if isinstance(summary.get('nextActions'), list):
            out['recommendations'] = [str(x) for x in summary.get('nextActions')[:8]]
        # also try to construct reportSections
        sections = []
        if out['keyObservations']:
            sections.append({'title': 'Risks To Check', 'items': out['keyObservations']})
        if out['recommendations']:
            sections.append({'title': 'Next Actions', 'items': out['recommendations']})
        if sections:
            out['reportSections'] = sections
        # narrativeText must be a string; if missing, compose from what's available
        if not out['narrativeText']:
            parts = []
            if out['keyObservations']:
                parts.append('Key observations: ' + '; '.join(out['keyObservations'][:3]))
            if out['recommendations']:
                parts.append('Recommendations: ' + '; '.join(out['recommendations'][:3]))
            out['narrativeText'] = '\n\n'.join(parts)[:1600]
        return out
    return None


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

    prompt = build_anomaly_prompt(table_name, analyses)
    first_response = ask_ollama_with_resilience(prompt)
    try:
        content = parse_llm_json(first_response)
        if not _validate_anomaly_llm_output(content):
            _inc_metric('validation_failures')
            raise ValueError('Anomaly LLM output failed schema validation')
    except (ValueError, json.JSONDecodeError) as first_error:
        _inc_metric('errors')
        repair_prompt = (
            'The previous response was not valid anomaly insight JSON. Return valid JSON only. '
            'Use this exact object shape: {"anomalyInsights":[{"column":"...","rowIndex":0,"impact":"...",'
            '"likelyCauses":["..."],"validationChecks":["..."],"fixSteps":["..."],'
            '"businessQuestions":["..."],"decisionGuide":["..."]}]}. '
            'Return one anomalyInsights item for each anomalyTasks item from the original prompt. '
            f'Original prompt:\n{prompt}\n\nInvalid response to repair:\n{first_response}\n\nParser error: {first_error}'
        )
        repaired = ask_ollama_with_resilience(repair_prompt)
        content = parse_llm_json(repaired)
        if not _validate_anomaly_llm_output(content):
            _inc_metric('validation_failures')
            raise ValueError('Repaired anomaly LLM output failed schema validation')

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

    metrics = {k: _llm_metrics.get(k, 0) for k in ('calls', 'errors', 'cache_hits', 'validation_failures')}
    enriched['llmStatus'] = f'Generated locally with {Config.LOCAL_LLM_MODEL} (metrics: {metrics})'
    return enriched
