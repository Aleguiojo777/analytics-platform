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
def get_env(key: str, default: str = None) -> Optional[str]:
    """Get environment variable."""
    return os.getenv(key, default)


def get_env_int(key: str, default: int = None) -> Optional[int]:
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
    PORT = get_env_int('PORT', 3000)
    HOST = get_env('HOST', '127.0.0.1')
    DEBUG = get_env_bool('FLASK_DEBUG', False)
    
    # Database
    DB_TYPE = get_env('DB_TYPE', 'sqlserver').lower()  # 'sqlserver' or 'mysql'
    ODBC_DRIVER = get_env('ODBC_DRIVER', 'ODBC Driver 18 for SQL Server')
    DB_CONNECTION_TIMEOUT = get_env_int('DB_CONNECTION_TIMEOUT', 10)
    
    # API Configuration
    CORS_ORIGINS = [origin.strip() for origin in get_env('CORS_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000,null').split(',') if origin.strip()]
    MAX_REQUEST_SIZE = get_env_int('MAX_REQUEST_SIZE', 10 * 1024 * 1024)  # 10MB
    REQUEST_TIMEOUT = get_env_int('REQUEST_TIMEOUT', 30)  # seconds
    
    # Analytics & Data Limits
    MAX_SAMPLE_ROWS = get_env_int('MAX_SAMPLE_ROWS', 100)
    MAX_NUMERIC_COLUMNS = get_env_int('MAX_NUMERIC_COLUMNS', 6)
    MAX_TEXT_COLUMNS = get_env_int('MAX_TEXT_COLUMNS', 8)
    MAX_TABLE_RESULTS = get_env_int('MAX_TABLE_RESULTS', 1000)
    
    # Pagination
    DEFAULT_PAGE_SIZE = get_env_int('DEFAULT_PAGE_SIZE', 50)
    MAX_PAGE_SIZE = get_env_int('MAX_PAGE_SIZE', 500)
    
    # Anomaly Detection
    ANOMALY_Z_SCORE_THRESHOLD = float(get_env('ANOMALY_Z_SCORE_THRESHOLD', '2.5'))
    MIN_VALUES_FOR_ANOMALY_DETECTION = get_env_int('MIN_VALUES_FOR_ANOMALY_DETECTION', 4)
    
    # Validation Limits
    MAX_FIELD_LENGTH = get_env_int('MAX_FIELD_LENGTH', 256)
    MAX_PASSWORD_LENGTH = get_env_int('MAX_PASSWORD_LENGTH', 512)
    MAX_TABLE_NAME_LENGTH = get_env_int('MAX_TABLE_NAME_LENGTH', 256)
    
    # Feature Flags
    ENABLE_ANOMALY_DETECTION = get_env_bool('ENABLE_ANOMALY_DETECTION', True)
    ENABLE_TREND_ANALYSIS = get_env_bool('ENABLE_TREND_ANALYSIS', True)
    ENABLE_CLEANED_MODE = get_env_bool('ENABLE_CLEANED_MODE', True)
    ENABLE_DATA_EXPORT = get_env_bool('ENABLE_DATA_EXPORT', True)
    # Enable local LLM by default for users running Ollama locally
    ENABLE_LOCAL_LLM = get_env_bool('ENABLE_LOCAL_LLM', True)

    # Local LLM (Ollama-compatible) Configuration
    # Ollama HTTP endpoint - prefer `/api/generate` which some Ollama versions use
    LOCAL_LLM_URL = get_env('LOCAL_LLM_URL', 'http://127.0.0.1:11434/api/generate')
    # Use the locally-available LLaMA 3.2.1 small model by default when present
    LOCAL_LLM_MODEL = get_env('LOCAL_LLM_MODEL', 'llama3.2.1b')
    # Increase default timeout to accommodate model cold starts
    LOCAL_LLM_TIMEOUT = get_env_int('LOCAL_LLM_TIMEOUT', 120)
    # Local LLM resilience and behavior
    LOCAL_LLM_MAX_RETRIES = get_env_int('LOCAL_LLM_MAX_RETRIES', 2)
    LOCAL_LLM_RETRY_BACKOFF_SEC = int(get_env('LOCAL_LLM_RETRY_BACKOFF_SEC', '1'))
    LOCAL_LLM_CACHE_TTL = get_env_int('LOCAL_LLM_CACHE_TTL', 24 * 3600)  # seconds
    LOCAL_LLM_COOLDOWN_SEC = get_env_int('LOCAL_LLM_COOLDOWN_SEC', 60)  # cooldown after repeated failures
    LOCAL_LLM_ENABLE_METRICS = get_env_bool('LOCAL_LLM_ENABLE_METRICS', True)
    LOCAL_LLM_FALLBACK_POLICY = get_env('LOCAL_LLM_FALLBACK_POLICY', 'prefer_computed')
    # Prompt hardening
    LOCAL_LLM_MAX_PROMPT_CHARS = get_env_int('LOCAL_LLM_MAX_PROMPT_CHARS', 20000)
    LOCAL_LLM_MAX_FIELD_CHARS = get_env_int('LOCAL_LLM_MAX_FIELD_CHARS', 1200)
    
    # Logging
    LOG_LEVEL = get_env('LOG_LEVEL', 'INFO')
    LOG_FORMAT = get_env('LOG_FORMAT', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
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
