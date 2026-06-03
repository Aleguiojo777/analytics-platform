from services import local_llm


def test_deterministic_fallback_no_llm_no_cache(monkeypatch):
    table = 'dbo.FallbackTable'

    # Ensure previous-insight cache cleared
    try:
        local_llm._previous_insight_cache.pop(table, None)
    except Exception:
        pass

    # Force LLM to raise
    monkeypatch.setattr(local_llm, 'ask_ollama_for_insight_json', lambda p: (_ for _ in ()).throw(OSError('simulated fail')))

    # Call enrich with minimal inputs
    enriched = local_llm.enrich_summary_with_local_llm(table, {}, {}, [], [], [], [])
    assert 'deterministic fallback' in enriched.get('llmStatus', '').lower()
    assert enriched.get('narrativeText')
