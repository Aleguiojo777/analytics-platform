"""Run a quick parse/validation test on tmp_exec_summary_response.json.

This script loads the tmp JSON (attempting UTF-16 decoding), runs
`parse_llm_json()` and `_validate_llm_output()` from `services.local_llm`, and
prints concise results. It does NOT call any LLM endpoints.
"""
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / 'tmp_exec_summary_response.json'
if not TMP.exists():
    print('tmp_exec_summary_response.json not found', file=sys.stderr)
    sys.exit(2)

# Try common encodings (utf-8, utf-16) to read the file
text = None
for enc in ('utf-8', 'utf-16', 'utf-16-le', 'utf-16-be'):
    try:
        text = TMP.read_text(encoding=enc)
        # Basic sanity: must contain '{' and '}'
        if '{' in text and '}' in text:
            break
    except Exception:
        text = None

if not text:
    print('Failed to read tmp_exec_summary_response.json with utf-8/utf-16 encodings', file=sys.stderr)
    sys.exit(3)

print(f'Read tmp file with length {len(text)} characters')

# Import parsing/validation helpers
try:
    # Ensure repository root is on sys.path so imports work when run as a script
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from services.local_llm import parse_llm_json, _validate_llm_output, _coerce_insight_shape
except Exception as e:
    print('Failed to import local LLM helpers:', e, file=sys.stderr)
    sys.exit(4)

# Try to parse
try:
    parsed = parse_llm_json(text)
    print('parse_llm_json: OK — parsed type:', type(parsed).__name__)
except Exception as e:
    print('parse_llm_json: FAILED —', repr(e), file=sys.stderr)
    sys.exit(5)

# Validate
try:
    ok = _validate_llm_output(parsed)
    print('validation result:', ok)
    if not ok:
        # Attempt coercion heuristics
        print('Attempting to coerce alternate shapes into expected schema...')
        coerced = _coerce_insight_shape(parsed)
        if coerced:
            print('Coercion produced an object; validating coerced shape...')
            ok2 = _validate_llm_output(coerced)
            print('coerced validation result:', ok2)
            if ok2:
                print('Coerced content looks valid. Top-level keys of coerced:', list(coerced.keys()))
        else:
            print('Coercion could not map parsed object to expected schema')
        # print top-level keys and sample
        if isinstance(parsed, dict):
            print('Top-level keys:', list(parsed.keys()))
            sample = list(parsed.items())[:5]
            print('Sample items:')
            for k, v in sample:
                print('-', k, ':', str(v)[:200])
    else:
        print('Parsed content looks structurally valid for insight schema.')
except Exception as e:
    print('Validation step failed:', repr(e), file=sys.stderr)
    sys.exit(6)

print('Done')
