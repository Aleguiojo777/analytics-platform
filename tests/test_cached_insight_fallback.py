import time

from services import local_llm


def test_previous_insight_fallback(monkeypatch):
    table = 'dbo.TestTable'
    sample = {
        'narrativeText': 'Previous narrative',
        'keyObservations': ['obs1'],
        'recommendations': ['rec1'],
        'reportSections': [{'title': 'A', 'items': ['i1']}],
        'columnInsights': [],
        'anomalyInsights': [],
    }

    # Store previous successful summary
    local_llm._set_previous_insight(table, sample)

    # Force LLM to fail
    def fail_prompt(prompt):
        raise OSError('simulated LLM failure')

    monkeypatch.setattr(local_llm, 'ask_ollama_for_insight_json', lambda p: (_ for _ in ()).throw(OSError('simulated LLM failure')))

    # Call enrich; should return cached previous summary
    enriched = local_llm.enrich_summary_with_local_llm(table, {}, {}, [], [], [], [])
    assert enriched.get('narrativeText') == 'Previous narrative'
    assert 'cached previous insight' in enriched.get('llmStatus', '').lower()
