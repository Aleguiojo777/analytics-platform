from flask import Blueprint, jsonify
from flask import Response
from services.local_llm import check_cloud_health, _is_cooled_down
from utils.config import Config
from services.local_llm import _llm_metrics

bp = Blueprint('llm', __name__, url_prefix='/api/llm')


@bp.route('/health', methods=['GET'])
def llm_health():
    """Health endpoint for LLM providers.

    Probes cloud provider first (if enabled) then local model state.
    Returns JSON: {provider, ok, latency, message, fallback}.
    """
    cloud = check_cloud_health(timeout=3)
    result = {
        'provider': cloud.get('provider'),
        'ok': cloud.get('ok', False),
        'latency': cloud.get('latency', 0.0),
        'message': cloud.get('message', ''),
    }
    # If cloud is not enabled or not ok, add local LLM cooldown status
    if not result['ok']:
        result['fallback_to_local'] = Config.CLOUD_LLM_ENABLED and not result['ok']
        result['local_cooled_down'] = _is_cooled_down()
    return jsonify(result), 200


@bp.route('/metrics', methods=['GET'])
def llm_metrics():
    """Return simple LLM metrics collected in-process."""
    try:
        return jsonify({'metrics': _llm_metrics}), 200
    except Exception:
        return jsonify({'metrics': {}}), 200


@bp.route('/metrics_prometheus', methods=['GET'])
def llm_metrics_prometheus():
    """Return Prometheus text exposition of key LLM metrics."""
    try:
        lines = []
        # Help/type lines
        lines.append('# HELP datalens_llm_calls Total LLM calls')
        lines.append('# TYPE datalens_llm_calls counter')
        lines.append(f'datalens_llm_calls {int(_llm_metrics.get("calls", 0))}')

        lines.append('# HELP datalens_llm_errors Total LLM errors')
        lines.append('# TYPE datalens_llm_errors counter')
        lines.append(f'datalens_llm_errors {int(_llm_metrics.get("errors", 0))}')

        lines.append('# HELP datalens_llm_cache_hits Total LLM cache hits')
        lines.append('# TYPE datalens_llm_cache_hits counter')
        lines.append(f'datalens_llm_cache_hits {int(_llm_metrics.get("cache_hits", 0))}')

        lines.append('# HELP datalens_llm_validation_failures Total LLM validation failures')
        lines.append('# TYPE datalens_llm_validation_failures counter')
        lines.append(f'datalens_llm_validation_failures {int(_llm_metrics.get("validation_failures", 0))}')

        lines.append('# HELP datalens_llm_coercions Total times output was coerced into expected shape')
        lines.append('# TYPE datalens_llm_coercions counter')
        lines.append(f'datalens_llm_coercions {int(_llm_metrics.get("coercions", 0))}')

        payload = '\n'.join(lines) + '\n'
        return Response(payload, mimetype='text/plain; version=0.0.4')
    except Exception:
        return Response('# HELP datalens_llm_metrics_unavailable 1\n# TYPE datalens_llm_metrics_unavailable gauge\ndatalens_llm_metrics_unavailable 1\n', mimetype='text/plain')
