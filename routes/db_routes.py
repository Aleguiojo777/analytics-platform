from flask import Blueprint
from controllers.db_controller import connect

bp = Blueprint('db', __name__, url_prefix='/api/db')

bp.add_url_rule('/connect', view_func=connect, methods=['POST'])
