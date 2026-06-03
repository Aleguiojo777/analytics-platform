import types
import subprocess

from services import local_llm
from utils import config


def _make_proc(returncode=0, stdout='', stderr=''):
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def test_call_openai_cli_no_cli(monkeypatch):
    def fake_run(*args, **kwargs):
        raise FileNotFoundError('cli not found')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    assert local_llm._call_openai_cli('hello', 'model-x') is None


def test_call_openai_cli_stdout(monkeypatch):
    proc = _make_proc(returncode=0, stdout='{"choices":[{"message":{"content":"ok"}}]}')

    def fake_run(cmd, capture_output, text, timeout):
        return proc

    monkeypatch.setattr(subprocess, 'run', fake_run)
    out = local_llm._call_openai_cli('hello', 'model-x')
    assert out is not None


def test_generate_respects_cli_flag(monkeypatch):
    # make other providers no-op
    monkeypatch.setattr(local_llm, '_call_ollama_http', lambda *a, **k: None)
    monkeypatch.setattr(local_llm, '_call_ollama_cli', lambda *a, **k: None)
    monkeypatch.setattr(local_llm, '_call_openai', lambda *a, **k: None)

    # CLI returns a value
    monkeypatch.setattr(local_llm, '_call_openai_cli', lambda *a, **k: 'cli-output')

    orig = config.Config.LOCAL_LLM_ENABLE_CLI_FALLBACK
    try:
        config.Config.LOCAL_LLM_ENABLE_CLI_FALLBACK = False
        res = local_llm.generate('prompt', model='m')
        assert res.get('text') is None

        config.Config.LOCAL_LLM_ENABLE_CLI_FALLBACK = True
        res2 = local_llm.generate('prompt', model='m')
        assert res2.get('text') == 'cli-output'
    finally:
        config.Config.LOCAL_LLM_ENABLE_CLI_FALLBACK = orig
