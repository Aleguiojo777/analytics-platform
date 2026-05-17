import os

from flask import Flask, send_from_directory
from flask_cors import CORS

from controllers.analytics_controller import get_executive_summary, get_table_analytics
from controllers.db_controller import connect

app = Flask(__name__, static_folder='frontend', static_url_path='')
CORS(app)

app.add_url_rule('/api/db/connect', view_func=connect, methods=['POST'])
app.add_url_rule('/api/analytics/table', view_func=get_table_analytics, methods=['POST'])
app.add_url_rule('/api/analytics/executive-summary', view_func=get_executive_summary, methods=['POST'])


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
    print(f'🐍 Python Analytics Platform running on http://localhost:{port}')
    app.run(host='0.0.0.0', port=port, debug=True)
