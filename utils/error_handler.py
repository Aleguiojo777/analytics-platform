"""Centralized error handling and logging for DataLens."""

import logging
import traceback
from typing import Tuple, Dict, Any, Optional
from functools import wraps
from flask import jsonify, request

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base exception for application errors."""
    def __init__(self, message: str, status_code: int = 500, error_code: str = 'INTERNAL_ERROR'):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(self.message)


class ValidationError(AppError):
    """Validation error exception."""
    def __init__(self, message: str):
        super().__init__(message, 400, 'VALIDATION_ERROR')


class AuthenticationError(AppError):
    """Authentication error exception."""
    def __init__(self, message: str = 'Authentication failed'):
        super().__init__(message, 401, 'AUTH_ERROR')


class DatabaseError(AppError):
    """Database connection/operation error exception."""
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message, 503, 'DATABASE_ERROR')
        self.original_error = original_error


class NotFoundError(AppError):
    """Resource not found exception."""
    def __init__(self, message: str):
        super().__init__(message, 404, 'NOT_FOUND')


class ForbiddenError(AppError):
    """Access forbidden exception."""
    def __init__(self, message: str):
        super().__init__(message, 403, 'FORBIDDEN')


def log_request(request_obj):
    """Log incoming request details."""
    logger.info(f"Incoming request: {request_obj.method} {request_obj.path}")
    if request_obj.method in ('POST', 'PUT', 'PATCH'):
        try:
            payload = request_obj.get_json(force=True, silent=True)
            if payload:
                # Don't log passwords
                safe_payload = {k: v if k != 'password' else '***' for k, v in payload.items()}
                logger.debug(f"Request payload: {safe_payload}")
        except Exception:
            pass


def log_error(error: Exception, context: str = ''):
    """Log error with traceback."""
    logger.error(f"Error occurred{' in ' + context if context else ''}: {str(error)}")
    logger.debug(f"Traceback: {traceback.format_exc()}")


def get_db_error_message(error: Exception) -> str:
    """Convert database error to user-friendly message."""
    error_msg = str(error).lower()
    
    if 'certificate chain was issued by an authority that is not trusted' in error_msg:
        return (
            'The server certificate is not trusted. For local or test databases, '
            'enable "Trust Server Certificate" and try again. For production, '
            'ask your administrator to install a trusted SQL Server certificate.'
        )
    if 'login failed' in error_msg: 
        return 'Login failed. Check your username, password, and database access.'
    if 'server was not found' in error_msg or 'network-related' in error_msg:
        return 'Could not reach the SQL Server. Check the server name, port, and network connection.'
    if 'timeout' in error_msg or 'connection timeout' in error_msg:
        return 'The connection timed out. Check that SQL Server is running and reachable.'
    if 'not found' in error_msg or 'does not exist' in error_msg:
        return 'The specified table or database was not found.'
    if 'access denied' in error_msg or 'permission' in error_msg:
        return 'Access denied. You do not have permissions to access this resource.'
    
    return 'Database operation failed. Please check the request and try again.'


def error_response(message: str, status_code: int = 500, error_code: str = 'INTERNAL_ERROR') -> Tuple[Any, int]:
    """Create standardized error response."""
    return jsonify({
        'error': message,
        'code': error_code,
        'status': status_code
    }), status_code


def handle_app_error(f):
    """Decorator to handle AppError exceptions."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            log_request(request)
            return f(*args, **kwargs)
        except AppError as e:
            log_error(e)
            return error_response(e.message, e.status_code, e.error_code)
        except Exception as e:
            log_error(e, 'unhandled exception')
            return error_response(
                'An unexpected error occurred. Please try again later.',
                500,
                'UNEXPECTED_ERROR'
            )
    return wrapper


def handle_database_error(original_error: Exception, friendly_msg: Optional[str] = None) -> Tuple[Any, int]:
    """Handle database-related errors."""
    if friendly_msg is None:
        friendly_msg = get_db_error_message(original_error)
    error = DatabaseError(friendly_msg, original_error)
    log_error(original_error, 'database operation')
    return error_response(error.message, error.status_code, error.error_code)
