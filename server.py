import os
from importlib import import_module

from flask import Flask, send_from_directory
from flask_cors import CORS

from routes.analytics_routes import bp as analytics_bp
from routes.db_routes import bp as db_bp

app = Flask(__name__, static_folder='frontend', static_url_path='')
CORS(app, resources={r'/api/*': {'origins': os.getenv('CORS_ORIGINS', 'http://localhost:3000').split(',')}})

app.register_blueprint(db_bp)
app.register_blueprint(analytics_bp)


@app.route('/<path:path>', methods=['GET'])
def static_proxy(path: str):
    file_path = os.path.join(app.static_folder, path)
    if os.path.exists(file_path):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/', methods=['GET'])
def index():
    return send_from_directory(app.static_folder, 'index.html')


if __name__ == '__main__':
    port = int(os.getenv('PORT', 3000))
    debug = os.getenv('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes')
    print(f'Python Analytics Platform running on http://localhost:{port}')

    waitress = None
    if not debug:
        try:
            waitress = import_module('waitress')
        except ImportError:
            waitress = None

    if debug or waitress is None:
        app.run(host='127.0.0.1', port=port, debug=debug)
    else:
        waitress.serve(app, host='127.0.0.1', port=port)
