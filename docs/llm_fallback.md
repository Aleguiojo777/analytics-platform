LLM CLI Fallback
=================

Overview
--------
DataLens includes a best-effort CLI-based fallback for LLM providers to improve availability when local HTTP APIs or SDKs are unavailable. This fallback is intentionally opt-in and guarded by a configuration flag to avoid unexpected execution of external tools in hardened environments.

Behavior
--------
- Primary generation order in `generate()`:
  1. Ollama HTTP (`LOCAL_LLM_URL`)
  2. Ollama CLI (`ollama run ...`)
  3. OpenAI Python client (`openai` library)
  4. OpenAI CLI / alternate CLI (`openai` / `oai`) — only when enabled
- `ask_ollama_with_resilience()` will attempt cloud (if enabled), then local model attempts. If local attempts fail, and CLI fallbacks are allowed, it will call `generate()` as a final fallback.

Configuration
-------------
- Toggle CLI fallbacks with the environment variable `LOCAL_LLM_ENABLE_CLI_FALLBACK` (default: `True`).

Example (disable CLI fallback):

```powershell
$env:LOCAL_LLM_ENABLE_CLI_FALLBACK = 'false'
```

Files
-----
- Config flag: [utils/config.py](utils/config.py#L1)
- Fallback implementation: [services/local_llm.py](services/local_llm.py#L1)

Notes
-----
- CLI fallbacks are best-effort and should be used for convenience or in developer environments. For production, prefer well-provisioned local or cloud LLM endpoints and set `LOCAL_LLM_ENABLE_CLI_FALLBACK=false` when arbitrary CLI execution is disallowed.
