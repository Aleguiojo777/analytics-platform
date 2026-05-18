"""Configuration management for DataLens."""

import os
from typing import Optional

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
    ODBC_DRIVER = get_env('ODBC_DRIVER', 'ODBC Driver 18 for SQL Server')
    DB_CONNECTION_TIMEOUT = get_env_int('DB_CONNECTION_TIMEOUT', 10)
    
    # API Configuration
    CORS_ORIGINS = get_env('CORS_ORIGINS', 'http://localhost:3000').split(',')
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
        return True


# Validate on import
Config.validate()
