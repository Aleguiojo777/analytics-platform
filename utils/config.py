"""Configuration management for DataLens."""

import os
from pathlib import Path
from typing import Optional


def load_env_file(path: str = '.env') -> None:
    """Load simple KEY=VALUE pairs from a local .env file when present."""
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_env_file()
# Load from environment
def get_env(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get environment variable."""
    return os.getenv(key, default)


def get_env_int(key: str, default: Optional[int] = None) -> Optional[int]:
    """Get environment variable as integer."""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def get_env_bool(key: str, default: bool = False) -> bool:
    """Get environment variable as boolean."""
    value = os.getenv(key, '').lower()
    if value in ('1', 'true', 'yes', 'on'):
        return True
    if value in ('0', 'false', 'no', 'off'):
        return False
    return default


# Flask & Server Configuration
class Config:
    """Application configuration."""
    
    # Server
    PORT = int(get_env_int('PORT', 3000) or 3000)
    HOST = (get_env('HOST', '127.0.0.1') or '127.0.0.1')
    DEBUG = get_env_bool('FLASK_DEBUG', False)
    
    # Database
    DB_TYPE = (get_env('DB_TYPE', 'sqlserver') or 'sqlserver').lower()  # 'sqlserver' or 'mysql'
    ODBC_DRIVER = (get_env('ODBC_DRIVER', 'ODBC Driver 18 for SQL Server') or 'ODBC Driver 18 for SQL Server')
    DB_CONNECTION_TIMEOUT = int(get_env_int('DB_CONNECTION_TIMEOUT', 10) or 10)
    
    # API Configuration
    CORS_ORIGINS = [origin.strip() for origin in (get_env('CORS_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000,null') or '').split(',') if origin.strip()]
    MAX_REQUEST_SIZE = int(get_env_int('MAX_REQUEST_SIZE', 10 * 1024 * 1024) or 10 * 1024 * 1024)  # 10MB
    REQUEST_TIMEOUT = int(get_env_int('REQUEST_TIMEOUT', 30) or 30)  # seconds
    
    # Analytics & Data Limits
    MAX_SAMPLE_ROWS = int(get_env_int('MAX_SAMPLE_ROWS', 100) or 100)
    MAX_NUMERIC_COLUMNS = int(get_env_int('MAX_NUMERIC_COLUMNS', 6) or 6)
    MAX_TEXT_COLUMNS = int(get_env_int('MAX_TEXT_COLUMNS', 8) or 8)
    MAX_TABLE_RESULTS = int(get_env_int('MAX_TABLE_RESULTS', 1000) or 1000)
    
    # Pagination
    DEFAULT_PAGE_SIZE = int(get_env_int('DEFAULT_PAGE_SIZE', 50) or 50)
    MAX_PAGE_SIZE = int(get_env_int('MAX_PAGE_SIZE', 500) or 500)
    
    # Anomaly Detection
    ANOMALY_Z_SCORE_THRESHOLD = float(get_env('ANOMALY_Z_SCORE_THRESHOLD', '2.5') or '2.5')
    MIN_VALUES_FOR_ANOMALY_DETECTION = int(get_env_int('MIN_VALUES_FOR_ANOMALY_DETECTION', 4) or 4)
    
    # Validation Limits
    MAX_FIELD_LENGTH = int(get_env_int('MAX_FIELD_LENGTH', 256) or 256)
    MAX_PASSWORD_LENGTH = int(get_env_int('MAX_PASSWORD_LENGTH', 512) or 512)
    MAX_TABLE_NAME_LENGTH = int(get_env_int('MAX_TABLE_NAME_LENGTH', 256) or 256)
    
    # Feature Flags
    ENABLE_ANOMALY_DETECTION = get_env_bool('ENABLE_ANOMALY_DETECTION', True)
    ENABLE_TREND_ANALYSIS = get_env_bool('ENABLE_TREND_ANALYSIS', True)
    ENABLE_CLEANED_MODE = get_env_bool('ENABLE_CLEANED_MODE', True)
    ENABLE_DATA_EXPORT = get_env_bool('ENABLE_DATA_EXPORT', True)
    # Enable local LLM by default for users running Ollama locally
    ENABLE_LOCAL_LLM = get_env_bool('ENABLE_LOCAL_LLM', True)

    # Local LLM (Ollama-compatible) Configuration
    # Ollama HTTP endpoint - prefer `/api/generate` which some Ollama versions use
    LOCAL_LLM_URL = (get_env('LOCAL_LLM_URL', 'http://127.0.0.1:11434/api/generate') or 'http://127.0.0.1:11434/api/generate')
    # Use the locally-available LLaMA 3.2.1 small model by default when present
    LOCAL_LLM_MODEL = (get_env('LOCAL_LLM_MODEL', 'llama3.2.1b') or 'llama3.2.1b')
    # Increase default timeout to accommodate model cold starts
    LOCAL_LLM_TIMEOUT = int(get_env_int('LOCAL_LLM_TIMEOUT', 120) or 120)
    # Local LLM resilience and behavior
    # Allow one extra attempt by default (e.g. 3 retries -> up to 4 attempts)
    LOCAL_LLM_MAX_RETRIES = int(get_env_int('LOCAL_LLM_MAX_RETRIES', 3) or 3)
    # Base backoff in seconds (will be used with exponential backoff + jitter)
    LOCAL_LLM_RETRY_BACKOFF_SEC = int(get_env('LOCAL_LLM_RETRY_BACKOFF_SEC', '2') or '2')
    LOCAL_LLM_CACHE_TTL = int(get_env_int('LOCAL_LLM_CACHE_TTL', 24 * 3600) or 24 * 3600)  # seconds
    LOCAL_LLM_COOLDOWN_SEC = int(get_env_int('LOCAL_LLM_COOLDOWN_SEC', 60) or 60)  # cooldown after repeated failures
    LOCAL_LLM_ENABLE_METRICS = get_env_bool('LOCAL_LLM_ENABLE_METRICS', True)
    LOCAL_LLM_FALLBACK_POLICY = (get_env('LOCAL_LLM_FALLBACK_POLICY', 'prefer_computed') or 'prefer_computed')
    # Prompt hardening
    LOCAL_LLM_MAX_PROMPT_CHARS = int(get_env_int('LOCAL_LLM_MAX_PROMPT_CHARS', 20000) or 20000)
    LOCAL_LLM_MAX_FIELD_CHARS = int(get_env_int('LOCAL_LLM_MAX_FIELD_CHARS', 1200) or 1200)
    # Concurrency for local/cloud LLM calls to avoid resource exhaustion
    LOCAL_LLM_MAX_CONCURRENCY = int(get_env_int('LOCAL_LLM_MAX_CONCURRENCY', 4) or 4)

    # Enable/disable use of CLI-based fallbacks (e.g. `openai` CLI or `oai`).
    # Defaults to True to allow local operator convenience; set to False in
    # hardened production environments where CLI usage is disallowed.
    LOCAL_LLM_ENABLE_CLI_FALLBACK = get_env_bool('LOCAL_LLM_ENABLE_CLI_FALLBACK', True)
    # TTL (seconds) for previous successful AI-generated executive summaries used as fallback
    LOCAL_LLM_PREVIOUS_INSIGHT_CACHE_TTL = int(os.environ.get('LOCAL_LLM_PREVIOUS_INSIGHT_CACHE_TTL', str(24 * 3600)))
    # If true, perform LLM enrichment in a background thread and return computed summary immediately
    LOCAL_LLM_BACKGROUND_ENRICH = get_env_bool('LOCAL_LLM_BACKGROUND_ENRICH', True)
    # Use a smaller, lower-latency model for interactive/enrichment attempts first
    LOCAL_LLM_INTERACTIVE_MODEL = (get_env('LOCAL_LLM_INTERACTIVE_MODEL', '') or '')
    # When true, send a compact prompt (essential fields only) to reduce model runtime
    LOCAL_LLM_USE_COMPACT_PROMPT = get_env_bool('LOCAL_LLM_USE_COMPACT_PROMPT', True)

    # Cloud LLM configuration (optional). When enabled, cloud provider will be
    # preferred over local LLM for lower operational burden.
    # Enable cloud LLM by default for users who prefer free cloud models
    CLOUD_LLM_ENABLED = get_env_bool('CLOUD_LLM_ENABLED', True)
    CLOUD_LLM_PROVIDER = (get_env('CLOUD_LLM_PROVIDER', 'generic') or 'generic').lower()
    CLOUD_LLM_URL = (get_env('CLOUD_LLM_URL', '') or '')
    CLOUD_LLM_API_KEY = (get_env('CLOUD_LLM_API_KEY', None) or None)
    # Default free model selection (chosen by user): minimax-m3:cloud
    CLOUD_LLM_MODEL = (get_env('CLOUD_LLM_MODEL', 'minimax-m3:cloud') or 'minimax-m3:cloud')
    CLOUD_LLM_TIMEOUT = int(get_env_int('CLOUD_LLM_TIMEOUT', 60) or 60)
    CLOUD_LLM_MAX_RETRIES = int(get_env_int('CLOUD_LLM_MAX_RETRIES', 2) or 2)
    
    # Logging
    LOG_LEVEL = (get_env('LOG_LEVEL', 'INFO') or 'INFO')
    LOG_FORMAT = (get_env('LOG_FORMAT', '%(asctime)s - %(name)s - %(levelname)s - %(message)s') or '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    @classmethod
    def validate(cls) -> bool:
        """Validate critical configuration."""
        if cls.PORT < 1 or cls.PORT > 65535:
            raise ValueError(f'Invalid PORT: {cls.PORT}')
        if cls.ANOMALY_Z_SCORE_THRESHOLD <= 0:
            raise ValueError(f'Invalid ANOMALY_Z_SCORE_THRESHOLD: {cls.ANOMALY_Z_SCORE_THRESHOLD}')
        if cls.DB_TYPE not in ('sqlserver', 'mysql'):
            raise ValueError(f"Invalid DB_TYPE: {cls.DB_TYPE}. Use 'sqlserver' or 'mysql'.")
        return True


# Validate on import
Config.validate()
