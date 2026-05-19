from flask import Blueprint, jsonify
from controllers.db_controller import connect
from utils.config import Config

bp = Blueprint('db', __name__, url_prefix='/api/db')

bp.add_url_rule('/connect', view_func=connect, methods=['POST'])

@bp.route('/config', methods=['GET'])
def get_db_config():
    """Get database configuration."""
    return jsonify({
        'dbType': Config.DB_TYPE,
        'defaultPort': 3306 if Config.DB_TYPE == 'mysql' else 1433
    })
