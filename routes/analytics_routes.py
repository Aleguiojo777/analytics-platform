from flask import Blueprint
from controllers.analytics_controller import get_executive_summary, get_table_analytics

bp = Blueprint('analytics', __name__, url_prefix='/api/analytics')

bp.add_url_rule('/table', view_func=get_table_analytics, methods=['POST'])
bp.add_url_rule('/executive-summary', view_func=get_executive_summary, methods=['POST'])
