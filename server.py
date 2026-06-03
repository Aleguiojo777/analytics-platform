import os
import logging
from importlib import import_module

from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS
from typing import cast

from routes.analytics_routes import bp as analytics_bp
from routes.db_routes import bp as db_bp
from routes.llm_routes import bp as llm_bp
from utils.config import Config
from utils.error_handler import AppError, logger as error_logger

# Configure logging
logging.basicConfig(
    level=Config.LOG_LEVEL,
    format=Config.LOG_FORMAT
)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='frontend', static_url_path='')
app.config['MAX_CONTENT_LENGTH'] = Config.MAX_REQUEST_SIZE

# Configure CORS with values from Config
CORS(app, resources={r'/api/*': {'origins': Config.CORS_ORIGINS}})

# Register blueprints
app.register_blueprint(db_bp)
app.register_blueprint(analytics_bp)
app.register_blueprint(llm_bp)

# Optional pre-warm of LLM providers to reduce cold-start failures
def _prewarm_llm():
    try:
        import threading
        from services.local_llm import check_cloud_health, ask_ollama_with_resilience
        def _worker():
            try:
                # health probe
                check_cloud_health(timeout=3)
            except Exception:
                pass
            try:
                # short warming prompt (non-blocking)
                ask_ollama_with_resilience('Warm-up ping', cache_ttl=60)
            except Exception:
                pass
        t = threading.Thread(target=_worker, daemon=True)
        t.start()
    except Exception:
        logger.debug('LLM prewarm not available or failed')

_prewarm_llm()

# Global error handlers
@app.errorhandler(400)
def handle_bad_request(error):
    """Handle 400 Bad Request errors."""
    logger.warning(f'Bad request: {str(error)}')
    return jsonify({'error': 'Bad request. Please check your input.', 'code': 'BAD_REQUEST'}), 400

@app.errorhandler(404)
def handle_not_found(error):
    """Handle 404 Not Found errors."""
    logger.warning(f'Resource not found: {str(error)}')
    return jsonify({'error': 'Resource not found.', 'code': 'NOT_FOUND'}), 404

@app.errorhandler(500)
def handle_internal_error(error):
    """Handle 500 Internal Server errors."""
    logger.error(f'Internal server error: {str(error)}')
    return jsonify({'error': 'An internal server error occurred. Please try again later.', 'code': 'INTERNAL_ERROR'}), 500

@app.errorhandler(AppError)
def handle_app_error(error: AppError):
    """Handle application-specific errors."""
    logger.warning(f'{error.error_code}: {error.message}')
    return jsonify({'error': error.message, 'code': error.error_code}), error.status_code

@app.route('/<path:path>', methods=['GET'])
def static_proxy(path: str):
    # `app.static_folder` can be Optional[str] in some Flask typings — ensure non-None
    static_dir = cast(str, app.static_folder)
    file_path = os.path.join(static_dir, path)
    if os.path.exists(file_path):
        return send_from_directory(static_dir, path)
    return send_from_directory(static_dir, 'index.html')

@app.route('/', methods=['GET'])
def index():
    static_dir = cast(str, app.static_folder)
    return send_from_directory(static_dir, 'index.html')

@app.route('/api/health', methods=['GET'])
def health_check():
    """Simple health check endpoint."""
    return jsonify({'status': 'ok', 'version': '1.0.5'}), 200


if __name__ == '__main__':
    logger.info(f'DataLens Analytics Platform starting...')
    logger.info(f'Server: {Config.HOST}:{Config.PORT}')
    logger.info(f'Debug Mode: {Config.DEBUG}')
    logger.info(f'CORS Origins: {Config.CORS_ORIGINS}')
    
    print(f'DataLens Analytics Platform running on http://{Config.HOST}:{Config.PORT}')

    waitress = None
    if not Config.DEBUG:
        try:
            waitress = import_module('waitress')
        except ImportError:
            waitress = None

    if Config.DEBUG or waitress is None:
        app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
    else:
        waitress.serve(app, host=Config.HOST, port=Config.PORT)
