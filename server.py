import os
import logging
from importlib import import_module

from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS

from routes.analytics_routes import bp as analytics_bp
from routes.db_routes import bp as db_bp
from utils.config import Config
from utils.error_handler import AppError, logger as error_logger

# Configure logging
logging.basicConfig(
    level=Config.LOG_LEVEL,
    format=Config.LOG_FORMAT
)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='frontend', static_url_path='')

# Configure CORS with values from Config
CORS(app, resources={r'/api/*': {'origins': Config.CORS_ORIGINS}})

# Register blueprints
app.register_blueprint(db_bp)
app.register_blueprint(analytics_bp)

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
    file_path = os.path.join(app.static_folder, path)
    if os.path.exists(file_path):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/', methods=['GET'])
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/api/health', methods=['GET'])
def health_check():
    """Simple health check endpoint."""
    return jsonify({'status': 'ok', 'version': '1.0.1'}), 200


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
